import re

from django.core.exceptions import ValidationError


# Fonte estrutural oficial do Portal Nacional da NF-e, arquivada:
# docs/evidencias/nfe_2026_09_10/schemas_010f.zip
# PL_010f_v1.04/leiauteNFe_v4.00.xsd, NF-e/NFC-e 4.00, campo YA02.
# ZIP SHA-256: b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998.
# XSD raiz SHA-256: adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df.
# O XSD limita tPag a [0-9]{2}; o catálogo semântico está no MOC 7.0
# Anexo I, página 62, arquivado no mesmo diretório como moc_anexo_i.pdf.
# Auditoria detalhada em docs/DIAGNOSTICO_NFCE_PAGAMENTOS_XSD_010F.md.
TPAG_SUPORTADOS_LEIAUTE = frozenset({
    "01", "02", "03", "04", "05", "10", "11", "12",
    "13", "15", "16", "17", "18", "19", "90", "99",
})

ERRO_TPAG_FORMATO = "Informe o tPag com 2 dígitos."
ERRO_TPAG_DESCONHECIDO = (
    "Código fiscal tPag não é reconhecido pelo leiaute fiscal vigente."
)


def validar_configuracao_tpag(codigo, descricao="", *, permitir_vazio=True):
    """Normaliza e valida tPag/xPag contra o leiaute fiscal vigente."""
    codigo = (codigo or "").strip()
    descricao = (descricao or "").strip()
    erros = {}

    if not codigo:
        if not permitir_vazio:
            erros["codigo_fiscal_tpag"] = ERRO_TPAG_FORMATO
        if descricao:
            erros["descricao_fiscal_xpag"] = (
                "xPag só pode ser informado quando tPag for 99."
            )
    elif not re.fullmatch(r"[0-9]{2}", codigo):
        erros["codigo_fiscal_tpag"] = ERRO_TPAG_FORMATO
    elif codigo not in TPAG_SUPORTADOS_LEIAUTE:
        erros["codigo_fiscal_tpag"] = ERRO_TPAG_DESCONHECIDO

    if codigo == "99" and not descricao:
        erros["descricao_fiscal_xpag"] = "Informe xPag quando tPag for 99."
    elif codigo and codigo != "99" and descricao:
        erros["descricao_fiscal_xpag"] = (
            "xPag só pode ser informado quando tPag for 99."
        )

    if erros:
        raise ValidationError(erros)
    return codigo, descricao
