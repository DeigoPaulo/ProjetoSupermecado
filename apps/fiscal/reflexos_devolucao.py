"""Conferência aritmética de impactos declarados; não é motor tributário.

O chamador deve fornecer itens e rateio íntegros, atuais e autorizados.
Este formulário não busca documentos, persiste dados nem autoriza emissão.
Os deltas são assinados e informados pelo responsável: nenhuma incidência,
proporção, redução ou regra de arredondamento é inferida do valor comercial.
"""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.auditoria.models import LogAuditoria
from apps.clientes.escopo import empresa_id_do_usuario
from .models import RascunhoDevolucaoFornecedor, RateioDevolucaoFornecedor, ReflexosBasesDevolucaoFornecedor
from .devolucao_fornecedor import _hash_conteudo_revisao
from .rateio_devolucao import RateioDevolucaoForm, validar_composicao_atual

from .devolucao_fornecedor import TRIBUTOS_MEMORIA_CALCULO
from .rateio_devolucao import COMPONENTES


LIMITE = Decimal("9999999999999.99")


class ReflexosBasesDevolucaoForm(forms.Form):
    fundamentacao = forms.CharField(min_length=10, max_length=4000, widget=forms.Textarea)

    def __init__(self, *args, itens, linhas_rateio, **kwargs):
        super().__init__(*args, **kwargs)
        self.itens = list(itens)
        self.rateio = list(linhas_rateio)
        self.resultado = None
        for item in self.itens:
            for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
                prefixo = f"item_{item.pk}_{tributo}"
                for componente in COMPONENTES:
                    self.fields[f"{prefixo}_{componente}"] = forms.DecimalField(
                        label=f"nItem {item.numero_item_xml} · {rotulo} · impacto de {componente}",
                        max_digits=15, decimal_places=2, min_value=-LIMITE,
                        max_value=LIMITE, localize=True,
                    )
                self.fields[f"{prefixo}_base_final"] = forms.DecimalField(
                    label=f"nItem {item.numero_item_xml} · {rotulo} · base final declarada",
                    max_digits=15, decimal_places=2, min_value=0,
                    max_value=LIMITE, localize=True,
                )
        for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
            self.fields[f"total_base_{tributo}"] = forms.DecimalField(
                label=f"Total declarado das bases de {rotulo}", max_digits=15,
                decimal_places=2, min_value=0, max_value=LIMITE, localize=True,
            )

    def clean(self):
        dados = super().clean()
        if self.errors:
            return dados
        ids = [item.pk for item in self.itens]
        rateio_ids = [linha.get("item_memoria_id") for linha in self.rateio]
        if not ids or len(set(ids)) != len(ids) or len(set(rateio_ids)) != len(rateio_ids) or set(ids) != set(rateio_ids):
            raise forms.ValidationError("Os itens da memória e do rateio precisam corresponder integralmente, sem duplicidade.")
        por_id = {linha["item_memoria_id"]: linha for linha in self.rateio}
        totais = {tributo: Decimal("0") for tributo, _ in TRIBUTOS_MEMORIA_CALCULO}
        linhas = []
        for item in self.itens:
            origem = por_id[item.pk]
            if origem.get("item_rascunho_id") != item.item_rascunho_id or str(origem.get("numero_item_xml")) != str(item.numero_item_xml):
                raise forms.ValidationError("O vínculo do item com o rateio divergiu.")
            tributos = {}
            for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
                prefixo = f"item_{item.pk}_{tributo}"
                base = getattr(item, f"base_{tributo}")
                impactos = {campo: dados[f"{prefixo}_{campo}"] for campo in COMPONENTES}
                final = dados[f"{prefixo}_base_final"]
                if base + sum(impactos.values(), Decimal("0")) != final:
                    raise forms.ValidationError(f"nItem {item.numero_item_xml}: base anterior e impactos de {rotulo} não conferem com a base final.")
                totais[tributo] += final
                tributos[tributo] = {
                    "base_anterior": format(base, ".2f"), "base_final": format(final, ".2f"),
                    "impactos": {campo: format(valor, ".2f") for campo, valor in impactos.items()},
                }
            linhas.append({"item_memoria_id": item.pk, "item_rascunho_id": item.item_rascunho_id,
                           "numero_item_xml": item.numero_item_xml, "tributos": tributos})
        for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
            if totais[tributo] != dados[f"total_base_{tributo}"]:
                raise forms.ValidationError(f"O total declarado das bases de {rotulo} diverge dos itens.")
        self.resultado = {
            "contrato": "supplier_return_tax_base_impacts_draft_v1",
            "fundamentacao": dados["fundamentacao"], "itens": linhas,
            "totais_bases": {campo: format(valor, ".2f") for campo, valor in totais.items()},
            "permite_emissao": False,
        }
        return dados


def validar_rateio_atual(rascunho, rateio):
    """Somente leitura; o serviço de escrita mantém o bloqueio do rascunho."""
    if rascunho.status != "APROVADO":
        raise ValidationError("A preparação precisa estar aprovada.")
    ficha = rateio.composicao
    if ficha.rascunho_id != rascunho.pk:
        raise ValidationError("Rateio de outra preparação.")
    memoria, revisao = validar_composicao_atual(rascunho, ficha)
    if ficha.rateios.filter(versao__gt=rateio.versao).exists():
        raise ValidationError("O rateio foi superado por uma versão mais recente.")
    snapshot = rateio.conteudo_snapshot
    if _hash_conteudo_revisao(snapshot) != rateio.conteudo_sha256:
        raise ValidationError("O rateio perdeu a integridade.")
    if (snapshot.get("composicao_id") != ficha.pk
        or snapshot.get("composicao_sha256") != ficha.conteudo_sha256
        or snapshot.get("revisao_sha256") != revisao.conteudo_sha256
        or snapshot.get("memoria_sha256") != memoria.conteudo_sha256
        or snapshot.get("permite_emissao") is not False):
        raise ValidationError("Os vínculos do rateio perderam a integridade.")
    itens = list(memoria.itens.order_by("item_rascunho_id"))
    try:
        dados = {"criterio": snapshot["criterio"]}
        for linha in snapshot["itens"]:
            for campo in COMPONENTES:
                dados[f"{campo}_{linha['item_memoria_id']}"] = Decimal(linha[campo])
        form = RateioDevolucaoForm(dados, itens=itens, totais=ficha.conteudo_snapshot["dados"])
        if not form.is_valid() or form.linhas != snapshot["itens"]:
            raise ValidationError("Os itens ou totais do rateio divergiram.")
    except (KeyError, TypeError, ArithmeticError, ValueError) as exc:
        raise ValidationError("Conteúdo do rateio inválido.") from exc
    return itens


def registrar_reflexos(rascunho, *, rateio_id, dados, responsavel):
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para registrar reflexos nas bases.")
    try:
        rateio_id = int(rateio_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Selecione um rateio válido.") from exc
    with transaction.atomic():
        rascunho = RascunhoDevolucaoFornecedor.objects.select_for_update().select_related("entrada_compra__filial").get(pk=rascunho.pk)
        empresa_id = empresa_id_do_usuario(responsavel)
        if empresa_id is not None and empresa_id != rascunho.entrada_compra.filial.empresa_id:
            raise ValidationError("Preparação de outra empresa.")
        rateio = RateioDevolucaoFornecedor.objects.select_related("composicao__memoria__parametrizacao__parecer").filter(pk=rateio_id, composicao__rascunho=rascunho).first()
        if not rateio:
            raise ValidationError("Rateio não pertence à preparação.")
        itens = validar_rateio_atual(rascunho, rateio)
        form = ReflexosBasesDevolucaoForm(dados, itens=itens, linhas_rateio=rateio.conteudo_snapshot["itens"])
        if not form.is_valid():
            raise ValidationError([erro for erros in form.errors.values() for erro in erros])
        conteudo = {**form.resultado, "contrato": "supplier_return_tax_base_impacts_v1",
                    "rascunho_id": rascunho.pk, "rateio_id": rateio.pk,
                    "rateio_sha256": rateio.conteudo_sha256,
                    "memoria_sha256": rateio.composicao.memoria.conteudo_sha256}
        sha = _hash_conteudo_revisao(conteudo)
        existente = rateio.reflexos.filter(conteudo_sha256=sha).first()
        if existente:
            return existente, False
        registro = ReflexosBasesDevolucaoFornecedor.objects.create(
            rateio=rateio, versao=(rateio.reflexos.aggregate(v=Max("versao"))["v"] or 0) + 1,
            conteudo_snapshot=conteudo, conteudo_sha256=sha, responsavel=responsavel,
        )
        LogAuditoria.objects.create(usuario=responsavel, modulo="fiscal", acao="REFLEXOS_DEVOLUCAO",
            descricao=f"Reflexos {registro.pk} do rateio {rateio.pk} registrados.",
            objeto_tipo="ReflexosBasesDevolucaoFornecedor", objeto_id=str(registro.pk))
        return registro, True
