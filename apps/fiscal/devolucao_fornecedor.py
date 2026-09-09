"""Pré-diagnóstico documental da devolução de compra ao fornecedor.

O contrato é deliberadamente somente leitura: não escolhe tributação, não cria
DocumentoFiscal e não movimenta estoque. Ele apenas separa evidências presentes
na entrada das decisões que continuam dependentes do contador e do caso real.
"""

from django.core.exceptions import ObjectDoesNotExist

from apps.compras.models import StatusEntradaCompra

from .pacote_contabil import analisar_xml_nfe


CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR = "supplier_return_fiscal_preparation_v1"


def _digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _documento_dfe_da_entrada(entrada):
    try:
        return entrada.documento_dfe_recebido
    except ObjectDoesNotExist:
        return None


def preparar_devolucao_fornecedor(entrada):
    """Expõe fatos e bloqueios sem gerar ou transmitir uma NF-e de devolução."""
    chave_entrada = _digitos(entrada.chave_acesso_xml)
    cnpj_fornecedor = _digitos(entrada.fornecedor.cnpj)
    cnpj_filial = _digitos(entrada.filial.cnpj or entrada.filial.empresa.cnpj)
    documento_dfe = _documento_dfe_da_entrada(entrada)
    xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
    analise = analisar_xml_nfe(xml_origem)

    verificacoes = [
        {
            "codigo": "entrada_finalizada",
            "rotulo": "Entrada de compra finalizada",
            "ok": entrada.status == StatusEntradaCompra.FINALIZADA,
            "detalhe": "A preparação fiscal só parte de mercadoria efetivamente recebida.",
        },
        {
            "codigo": "chave_original",
            "rotulo": "Chave da NF-e original válida",
            "ok": len(chave_entrada) == 44,
            "detalhe": chave_entrada or "A entrada não possui chave de 44 dígitos.",
        },
        {
            "codigo": "xml_original",
            "rotulo": "XML autorizado original preservado",
            "ok": bool(xml_origem) and not analise["erro"],
            "detalhe": (
                "XML integral disponível no DF-e vinculado."
                if xml_origem and not analise["erro"]
                else "Importe ou vincule o DF-e com o XML integral antes de apurar a devolução."
            ),
        },
        {
            "codigo": "modelo_original",
            "rotulo": "Documento original é NF-e modelo 55",
            "ok": analise["modelo"] == "55",
            "detalhe": f"Modelo encontrado: {analise['modelo'] or 'não identificado'}.",
        },
        {
            "codigo": "vinculo_xml",
            "rotulo": "XML e entrada representam a mesma NF-e",
            "ok": bool(chave_entrada) and analise["chave_acesso"] == chave_entrada,
            "detalhe": "A chave do XML integral deve ser idêntica à chave registrada na compra.",
        },
        {
            "codigo": "fornecedor_identificado",
            "rotulo": "Fornecedor corresponde ao emitente original",
            "ok": len(cnpj_fornecedor) == 14 and analise["emitente_cnpj"] == cnpj_fornecedor,
            "detalhe": "O CNPJ cadastrado deve coincidir com o emitente do XML original.",
        },
        {
            "codigo": "filial_identificada",
            "rotulo": "Filial corresponde ao destinatário original",
            "ok": len(cnpj_filial) == 14 and analise["destinatario_cnpj"] == cnpj_filial,
            "detalhe": "O CNPJ da filial deve coincidir com o destinatário do XML original.",
        },
        {
            "codigo": "itens_fiscais",
            "rotulo": "Itens fiscais originais disponíveis",
            "ok": bool(analise["itens"]),
            "detalhe": f"{len(analise['itens'])} item(ns) localizado(s) no XML integral.",
        },
    ]
    bloqueios_documentais = [item["rotulo"] for item in verificacoes if not item["ok"]]
    decisoes_pendentes = [
        "Selecionar os itens e as quantidades efetivamente devolvidos, sem exceder a entrada.",
        "Definir a natureza da operação e o CFOP com o contador para o caso concreto.",
        "Revisar por item ICMS, ICMS-ST, FCP, IPI, PIS, COFINS, cBenef e demais valores do XML original.",
        "Definir frete, transportador, volumes e motivo operacional da devolução, quando aplicáveis.",
        "Obter revisão fiscal antes de gerar XML, reservar numeração ou escolher Focus/SEFAZ direta.",
    ]

    return {
        "contrato": CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR,
        "estado": "BASE_DOCUMENTAL_DISPONIVEL" if not bloqueios_documentais else "INCOMPLETA",
        "permite_emissao": False,
        "permite_transmissao": False,
        "documento_planejado": {
            "modelo": "55",
            "finalidade": "4",
            "chave_referenciada": chave_entrada,
            "cfop": None,
            "tributacao": None,
        },
        "verificacoes": verificacoes,
        "bloqueios_documentais": bloqueios_documentais,
        "decisoes_pendentes": decisoes_pendentes,
        "itens_xml_original": analise["itens"],
    }
