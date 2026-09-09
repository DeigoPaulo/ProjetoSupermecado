"""Ficha logística informada; não gera XML nem movimentações."""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.clientes.escopo import empresa_id_do_usuario
from apps.auditoria.models import LogAuditoria
from .models import (
    RascunhoDevolucaoFornecedor, TransporteDevolucaoFornecedor,
    DecisaoRevisaoMemoriaCalculoFornecedor, RevisaoMemoriaCalculoDevolucaoFornecedor,
)
from .devolucao_fornecedor import _hash_conteudo_revisao, _validar_integridade_memoria_calculo
from .pacote_contabil import analisar_xml_nfe


def documento_numerico_valido(documento):
    if len(documento) not in (11, 14) or not documento.isascii() or not documento.isdigit() or len(set(documento)) == 1:
        return False
    base = documento[:-2]
    for _ in range(2):
        pesos = list(range(len(base) + 1, 1, -1)) if len(documento) == 11 else ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if len(base) == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
        base += str(0 if resto < 2 else 11 - resto)
    return base == documento


def validar_transporte_proprio(dados, *, remetente, destinatario):
    documento = dados.get("documento")
    modalidade = dados.get("modalidade")
    if not documento or modalidade not in ("3", "4"):
        return
    referencia = remetente if modalidade == "3" else destinatario
    if not documento_numerico_valido(referencia):
        raise ValidationError("Documento de referência do transporte próprio inválido no XML original.")
    tamanho = 8 if len(documento) == 14 else 11
    if len(documento) != len(referencia) or documento[:tamanho] != referencia[:tamanho]:
        raise ValidationError("O transportador do transporte próprio deve corresponder ao " + ("remetente." if modalidade == "3" else "destinatário."))


class TransporteDevolucaoForm(forms.Form):
    def clean_documento(self):
        documento = self.cleaned_data["documento"]
        if documento and not documento_numerico_valido(documento):
            raise forms.ValidationError("CPF/CNPJ do transportador possui dígitos verificadores inválidos.")
        return documento

    modalidade = forms.ChoiceField(label="Modalidade do frete", choices=[
        ("", "Selecione"), ("0", "Contratado pelo remetente"),
        ("1", "Contratado pelo destinatário"), ("2", "Contratado por terceiros"),
        ("3", "Transporte próprio do remetente"), ("4", "Transporte próprio do destinatário"),
        ("9", "Sem ocorrência de transporte"),
    ])
    nome = forms.CharField(label="Nome do transportador", max_length=60, required=False)
    documento = forms.RegexField(r"^(?:[0-9]{11}|[0-9]{14})$", label="CPF/CNPJ do transportador (somente números)", required=False)
    inscricao_estadual = forms.CharField(label="Inscrição estadual", max_length=14, required=False)
    endereco = forms.CharField(label="Endereço", max_length=60, required=False)
    municipio = forms.CharField(label="Município", max_length=60, required=False)
    uf = forms.ChoiceField(label="UF", required=False, choices=[("", "Selecione")] + [(uf, uf) for uf in "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()])
    quantidade_volumes = forms.IntegerField(label="Quantidade de volumes (zero quando não houver)", min_value=0, max_value=999999999)
    especie = forms.CharField(label="Espécie dos volumes", max_length=60, required=False)
    marca = forms.CharField(label="Marca dos volumes", max_length=60, required=False)
    numeracao = forms.CharField(label="Numeração dos volumes", max_length=60, required=False)
    peso_liquido = forms.DecimalField(label="Peso líquido (kg)", min_value=Decimal("0"), max_digits=15, decimal_places=3, localize=True)
    peso_bruto = forms.DecimalField(label="Peso bruto (kg)", min_value=Decimal("0"), max_digits=15, decimal_places=3, localize=True)
    observacao = forms.CharField(label="Observação logística", max_length=500, required=False, widget=forms.Textarea)

    def clean(self):
        dados = super().clean()
        if dados.get("modalidade") == "9" and any(dados.get(c) for c in ("nome", "documento", "inscricao_estadual", "endereco", "municipio", "uf")):
            raise forms.ValidationError("Sem ocorrência de transporte não permite informar transportador.")
        if dados.get("documento") and not dados.get("nome"):
            self.add_error("nome", "Informe o nome do transportador identificado.")
        liquido, bruto = dados.get("peso_liquido"), dados.get("peso_bruto")
        if liquido is not None and bruto is not None and liquido > bruto:
            self.add_error("peso_bruto", "O peso bruto não pode ser inferior ao líquido.")
        if dados.get("quantidade_volumes") == 0 and any(dados.get(c) for c in ("especie", "marca", "numeracao", "peso_liquido", "peso_bruto")):
            raise forms.ValidationError("Sem volumes, deixe os dados dos volumes vazios e os pesos zerados.")
        return dados


def registrar_transporte(rascunho, *, dados, responsavel):
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para registrar transporte fiscal.")
    form = TransporteDevolucaoForm(dados)
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
        revisao = RevisaoMemoriaCalculoDevolucaoFornecedor.objects.filter(memoria=memoria, decisao=DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR).first() if memoria else None
        if not revisao:
            raise ValidationError("A memória mais recente precisa estar aprovada por outro responsável.")
        if _hash_conteudo_revisao(revisao.conteudo_snapshot) != revisao.conteudo_sha256 or revisao.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256:
            raise ValidationError("A revisão da memória perdeu a integridade.")
        _validar_integridade_memoria_calculo(rascunho, memoria)
        origem = analisar_xml_nfe(rascunho.entrada_compra.documento_dfe_recebido.xml_conteudo)
        # A devolução inverte os papéis da nota original: comprador remete ao fornecedor.
        validar_transporte_proprio(form.cleaned_data, remetente=origem["destinatario_cnpj"], destinatario=origem["emitente_cnpj"])
        conteudo = {
            "contrato": "supplier_return_transport_v1",
            "rascunho_id": rascunho.pk, "memoria_id": memoria.pk,
            "memoria_sha256": memoria.conteudo_sha256, "revisao_sha256": revisao.conteudo_sha256,
            "dados": {chave: format(valor, ".3f") if isinstance(valor, Decimal) else valor for chave, valor in form.cleaned_data.items()},
        }
        sha = _hash_conteudo_revisao(conteudo)
        existente = rascunho.transportes.filter(conteudo_sha256=sha).first()
        if existente:
            return existente, False
        ficha = TransporteDevolucaoFornecedor.objects.create(
            rascunho=rascunho, memoria=memoria,
            versao=(rascunho.transportes.aggregate(v=Max("versao"))["v"] or 0) + 1,
            conteudo_snapshot=conteudo, conteudo_sha256=sha, responsavel=responsavel,
        )
        LogAuditoria.objects.create(usuario=responsavel, modulo="fiscal", acao="TRANSPORTE_DEVOLUCAO", descricao=f"Ficha de transporte {ficha.pk} registrada sem emissão.", objeto_tipo="TransporteDevolucaoFornecedor", objeto_id=str(ficha.pk))
        return ficha, True
