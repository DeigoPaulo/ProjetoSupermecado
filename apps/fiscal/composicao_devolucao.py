"""Conferência aritmética comercial; não representa o vNF nem cálculo tributário."""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.clientes.escopo import empresa_id_do_usuario
from apps.auditoria.models import LogAuditoria
from .models import RascunhoDevolucaoFornecedor, ComposicaoDevolucaoFornecedor, RevisaoMemoriaCalculoDevolucaoFornecedor
from .models import RevisaoComposicaoDevolucaoFornecedor
from .devolucao_fornecedor import _hash_conteudo_revisao, _validar_integridade_memoria_calculo


class ComposicaoDevolucaoForm(forms.Form):
    valor_base = forms.DecimalField(label="Valor da operação na memória aprovada", max_digits=15, decimal_places=2, min_value=0, localize=True)
    frete = forms.DecimalField(label="Frete a acrescentar", max_digits=15, decimal_places=2, min_value=0, localize=True)
    seguro = forms.DecimalField(label="Seguro a acrescentar", max_digits=15, decimal_places=2, min_value=0, localize=True)
    despesas = forms.DecimalField(label="Outras despesas a acrescentar", max_digits=15, decimal_places=2, min_value=0, localize=True)
    desconto = forms.DecimalField(label="Desconto a deduzir", max_digits=15, decimal_places=2, min_value=0, localize=True)
    total = forms.DecimalField(label="Total comercial declarado", max_digits=15, decimal_places=2, min_value=0, localize=True)
    criterio = forms.CharField(label="Justificativa da composição", min_length=10, max_length=1000, widget=forms.Textarea)
    confirmar_componentes = forms.BooleanField(label="Confirmo que os acréscimos e descontos informados ainda não estão incluídos no valor base.")

    def clean(self):
        dados = super().clean()
        campos = ("valor_base", "frete", "seguro", "despesas", "desconto", "total")
        if all(campo in dados for campo in campos):
            esperado = dados["valor_base"] + dados["frete"] + dados["seguro"] + dados["despesas"] - dados["desconto"]
            if esperado != dados["total"]:
                raise forms.ValidationError("O total declarado deve ser base + frete + seguro + despesas − desconto.")
        return dados


def registrar_composicao(rascunho, *, dados, responsavel):
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para registrar composição da devolução.")
    form = ComposicaoDevolucaoForm(dados)
    if not form.is_valid():
        raise ValidationError([erro for erros in form.errors.values() for erro in erros])
    with transaction.atomic():
        rascunho = RascunhoDevolucaoFornecedor.objects.select_for_update().select_related("entrada_compra__filial").get(pk=rascunho.pk)
        empresa_id = empresa_id_do_usuario(responsavel)
        if empresa_id is not None and empresa_id != rascunho.entrada_compra.filial.empresa_id:
            raise ValidationError("Preparação de outra empresa.")
        if rascunho.status != "APROVADO":
            raise ValidationError("A preparação precisa estar aprovada.")
        memoria = rascunho.memorias_calculo.select_related("parametrizacao__parecer").order_by("-versao").first()
        revisao = RevisaoMemoriaCalculoDevolucaoFornecedor.objects.filter(memoria=memoria, decisao="APROVAR").first() if memoria else None
        if not revisao:
            raise ValidationError("A memória mais recente precisa estar aprovada.")
        if _hash_conteudo_revisao(revisao.conteudo_snapshot) != revisao.conteudo_sha256 or revisao.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256:
            raise ValidationError("A revisão da memória perdeu a integridade.")
        _validar_integridade_memoria_calculo(rascunho, memoria)
        if form.cleaned_data["valor_base"] != Decimal(memoria.totais_snapshot["valor_operacao"]):
            raise ValidationError("O valor base diverge do total da operação na memória aprovada.")
        conteudo = {
            "contrato": "supplier_return_commercial_composition_v1",
            "rascunho_id": rascunho.pk, "memoria_id": memoria.pk,
            "memoria_sha256": memoria.conteudo_sha256, "revisao_sha256": revisao.conteudo_sha256,
            "dados": {chave: format(valor, ".2f") if isinstance(valor, Decimal) else valor for chave, valor in form.cleaned_data.items()},
            "permite_emissao": False,
        }
        sha = _hash_conteudo_revisao(conteudo)
        existente = rascunho.composicoes.filter(conteudo_sha256=sha).first()
        if existente:
            return existente, False
        ficha = ComposicaoDevolucaoFornecedor.objects.create(
            rascunho=rascunho, memoria=memoria,
            versao=(rascunho.composicoes.aggregate(v=Max("versao"))["v"] or 0) + 1,
            conteudo_snapshot=conteudo, conteudo_sha256=sha, responsavel=responsavel,
        )
        LogAuditoria.objects.create(usuario=responsavel, modulo="fiscal", acao="COMPOSICAO_DEVOLUCAO", descricao=f"Composição comercial {ficha.pk} registrada para conferência contábil.", objeto_tipo="ComposicaoDevolucaoFornecedor", objeto_id=str(ficha.pk))
        return ficha, True


class RevisaoComposicaoForm(forms.Form):
    decisao = forms.ChoiceField(label="Decisão", choices=[("", "Selecione"), ("APROVAR", "Aprovar composição"), ("DEVOLVER_CORRECAO", "Devolver para correção")])
    justificativa = forms.CharField(label="Justificativa", min_length=10, max_length=1000, widget=forms.Textarea)
    reflexos_icms = forms.CharField(label="Efeitos sobre ICMS, ICMS-ST e FCP", max_length=2000, required=False, widget=forms.Textarea)
    reflexos_ipi = forms.CharField(label="Efeitos sobre IPI", max_length=2000, required=False, widget=forms.Textarea)
    reflexos_pis_cofins = forms.CharField(label="Efeitos sobre PIS e COFINS", max_length=2000, required=False, widget=forms.Textarea)
    reflexos_ibs_cbs = forms.CharField(label="Efeitos sobre IBS e CBS", max_length=2000, required=False, widget=forms.Textarea)
    fundamentacao = forms.CharField(label="Fundamentação da orientação contábil", max_length=4000, required=False, widget=forms.Textarea)

    def clean(self):
        dados = super().clean()
        if dados.get("decisao") == "APROVAR":
            for campo in ("reflexos_icms", "reflexos_ipi", "reflexos_pis_cofins", "reflexos_ibs_cbs", "fundamentacao"):
                if len(dados.get(campo, "")) < 10:
                    self.add_error(campo, "Registre a orientação explícita, inclusive quando não houver efeito.")
        return dados


def revisar_composicao(rascunho, *, composicao_id, dados, revisor):
    if not has_role(revisor, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para revisar composição.")
    form = RevisaoComposicaoForm(dados)
    if not form.is_valid():
        raise ValidationError([erro for erros in form.errors.values() for erro in erros])
    try:
        composicao_id = int(composicao_id)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Selecione uma composição válida.") from exc
    with transaction.atomic():
        rascunho = RascunhoDevolucaoFornecedor.objects.select_for_update().select_related("entrada_compra__filial").get(pk=rascunho.pk)
        empresa_id = empresa_id_do_usuario(revisor)
        if empresa_id is not None and empresa_id != rascunho.entrada_compra.filial.empresa_id:
            raise ValidationError("Preparação de outra empresa.")
        if rascunho.status != "APROVADO":
            raise ValidationError("A preparação precisa estar aprovada.")
        ficha = rascunho.composicoes.select_related("memoria__parametrizacao__parecer").filter(pk=composicao_id).first()
        if not ficha:
            raise ValidationError("Composição não pertence à preparação.")
        if ficha.responsavel_id == revisor.pk:
            raise ValidationError("A composição exige revisão por outro responsável.")
        if RevisaoComposicaoDevolucaoFornecedor.objects.filter(composicao=ficha).exists():
            raise ValidationError("A composição já possui decisão imutável.")
        if rascunho.composicoes.filter(versao__gt=ficha.versao).exists() or rascunho.memorias_calculo.filter(versao__gt=ficha.memoria.versao).exists():
            raise ValidationError("A composição ou sua memória foi superada por nova versão.")
        memoria = ficha.memoria
        base = RevisaoMemoriaCalculoDevolucaoFornecedor.objects.filter(memoria=memoria, decisao="APROVAR").first()
        if not base or _hash_conteudo_revisao(base.conteudo_snapshot) != base.conteudo_sha256 or base.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256:
            raise ValidationError("Revisão da memória ausente ou sem integridade.")
        snapshot = ficha.conteudo_snapshot
        if (
            _hash_conteudo_revisao(snapshot) != ficha.conteudo_sha256
            or snapshot.get("rascunho_id") != rascunho.pk
            or snapshot.get("memoria_id") != memoria.pk
            or snapshot.get("memoria_sha256") != memoria.conteudo_sha256
            or snapshot.get("revisao_sha256") != base.conteudo_sha256
        ):
            raise ValidationError("A composição perdeu a integridade.")
        _validar_integridade_memoria_calculo(rascunho, memoria)
        conteudo = {
            "contrato": "supplier_return_commercial_review_v1",
            "composicao_id": ficha.pk, "composicao_sha256": ficha.conteudo_sha256,
            "memoria_sha256": memoria.conteudo_sha256, "revisor_id": revisor.pk,
            "dados": form.cleaned_data, "permite_emissao": False,
        }
        revisao = RevisaoComposicaoDevolucaoFornecedor.objects.create(
            composicao=ficha, decisao=form.cleaned_data["decisao"], revisor=revisor,
            conteudo_snapshot=conteudo, conteudo_sha256=_hash_conteudo_revisao(conteudo),
        )
        LogAuditoria.objects.create(usuario=revisor, modulo="fiscal", acao="REVISAO_COMPOSICAO_DEVOLUCAO", descricao=f"Revisão {revisao.pk} da composição {ficha.pk}: {revisao.decisao}.", objeto_tipo="RevisaoComposicaoDevolucaoFornecedor", objeto_id=str(revisao.pk))
        return revisao
