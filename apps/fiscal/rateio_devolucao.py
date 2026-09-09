"""Rateio comercial explicitamente informado, sem incidência tributária automática."""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.auditoria.models import LogAuditoria
from apps.clientes.escopo import empresa_id_do_usuario
from .devolucao_fornecedor import _hash_conteudo_revisao, _validar_integridade_memoria_calculo
from .models import RascunhoDevolucaoFornecedor, RevisaoComposicaoDevolucaoFornecedor, RevisaoMemoriaCalculoDevolucaoFornecedor, RateioDevolucaoFornecedor

COMPONENTES = ("frete", "seguro", "despesas", "desconto")


class RateioDevolucaoForm(forms.Form):
    criterio = forms.CharField(label="Critério do rateio informado", min_length=10, max_length=1000, widget=forms.Textarea)

    def __init__(self, *args, itens, totais, **kwargs):
        super().__init__(*args, **kwargs)
        self.itens = list(itens)
        self.totais = totais
        self.linhas = []
        for item in self.itens:
            for componente in COMPONENTES:
                self.fields[f"{componente}_{item.pk}"] = forms.DecimalField(
                    label=f"nItem {item.numero_item_xml} · {componente}",
                    max_digits=15, decimal_places=2, min_value=0, localize=True,
                )

    def clean(self):
        dados = super().clean()
        if self.errors:
            return dados
        if not self.itens:
            raise forms.ValidationError("Não há itens para ratear.")
        somas = {campo: Decimal("0.00") for campo in COMPONENTES}
        linhas = []
        for item in self.itens:
            valores = {campo: dados[f"{campo}_{item.pk}"] for campo in COMPONENTES}
            total = item.valor_operacao + valores["frete"] + valores["seguro"] + valores["despesas"] - valores["desconto"]
            if total < 0 or total > Decimal("9999999999999.99"):
                raise forms.ValidationError(f"Total comercial inválido no nItem {item.numero_item_xml}.")
            for campo in COMPONENTES:
                somas[campo] += valores[campo]
            linhas.append({
                "item_memoria_id": item.pk, "item_rascunho_id": item.item_rascunho_id,
                "numero_item_xml": item.numero_item_xml,
                "base": format(item.valor_operacao, ".2f"), "total": format(total, ".2f"),
                **{campo: format(valor, ".2f") for campo, valor in valores.items()},
            })
        for campo in COMPONENTES:
            if somas[campo] != Decimal(self.totais[campo]):
                raise forms.ValidationError(f"A soma de {campo} não confere com a composição aprovada.")
        if sum((Decimal(linha["total"]) for linha in linhas), Decimal("0")) != Decimal(self.totais["total"]):
            raise forms.ValidationError("A soma dos totais dos itens não confere com a composição aprovada.")
        self.linhas = linhas
        return dados


def registrar_rateio(rascunho, *, composicao_id, dados, responsavel):
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para registrar rateio.")
    try:
        composicao_id = int(composicao_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Selecione uma composição válida.") from exc
    with transaction.atomic():
        rascunho = RascunhoDevolucaoFornecedor.objects.select_for_update().select_related("entrada_compra__filial").get(pk=rascunho.pk)
        empresa_id = empresa_id_do_usuario(responsavel)
        if empresa_id is not None and empresa_id != rascunho.entrada_compra.filial.empresa_id:
            raise ValidationError("Preparação de outra empresa.")
        if rascunho.status != "APROVADO":
            raise ValidationError("A preparação precisa estar aprovada.")
        ficha = rascunho.composicoes.select_related("memoria__parametrizacao__parecer").filter(pk=composicao_id).first()
        if not ficha:
            raise ValidationError("Composição não pertence à preparação.")
        memoria = ficha.memoria
        if rascunho.composicoes.filter(versao__gt=ficha.versao).exists() or rascunho.memorias_calculo.filter(versao__gt=memoria.versao).exists():
            raise ValidationError("A composição ou memória foi superada.")
        revisao = RevisaoComposicaoDevolucaoFornecedor.objects.filter(composicao=ficha, decisao="APROVAR").first()
        base = RevisaoMemoriaCalculoDevolucaoFornecedor.objects.filter(memoria=memoria, decisao="APROVAR").first()
        if not revisao or not base:
            raise ValidationError("A composição e a memória precisam estar aprovadas.")
        for objeto in (ficha, revisao, base):
            if _hash_conteudo_revisao(objeto.conteudo_snapshot) != objeto.conteudo_sha256:
                raise ValidationError("A composição ou sua revisão perdeu a integridade.")
        if (
            ficha.conteudo_snapshot.get("rascunho_id") != rascunho.pk
            or ficha.conteudo_snapshot.get("memoria_id") != memoria.pk
            or ficha.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256
            or ficha.conteudo_snapshot.get("revisao_sha256") != base.conteudo_sha256
            or revisao.conteudo_snapshot.get("composicao_id") != ficha.pk
            or revisao.conteudo_snapshot.get("composicao_sha256") != ficha.conteudo_sha256
            or base.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256
        ):
            raise ValidationError("Os vínculos da composição perderam a integridade.")
        _validar_integridade_memoria_calculo(rascunho, memoria)
        form = RateioDevolucaoForm(dados, itens=memoria.itens.order_by("item_rascunho_id"), totais=ficha.conteudo_snapshot["dados"])
        if not form.is_valid():
            raise ValidationError([erro for erros in form.errors.values() for erro in erros])
        conteudo = {
            "contrato": "supplier_return_commercial_allocation_v1", "composicao_id": ficha.pk,
            "composicao_sha256": ficha.conteudo_sha256, "revisao_sha256": revisao.conteudo_sha256,
            "memoria_sha256": memoria.conteudo_sha256, "criterio": form.cleaned_data["criterio"],
            "itens": form.linhas, "permite_emissao": False,
        }
        sha = _hash_conteudo_revisao(conteudo)
        existente = ficha.rateios.filter(conteudo_sha256=sha).first()
        if existente:
            return existente, False
        rateio = RateioDevolucaoFornecedor.objects.create(composicao=ficha, versao=(ficha.rateios.aggregate(v=Max("versao"))["v"] or 0) + 1, conteudo_snapshot=conteudo, conteudo_sha256=sha, responsavel=responsavel)
        LogAuditoria.objects.create(usuario=responsavel, modulo="fiscal", acao="RATEIO_DEVOLUCAO", descricao=f"Rateio {rateio.pk} da composição {ficha.pk} registrado.", objeto_tipo="RateioDevolucaoFornecedor", objeto_id=str(rateio.pk))
        return rateio, True
