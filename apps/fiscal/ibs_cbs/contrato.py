from datetime import date


CONTRATO = "fiscal_ibs_cbs_go_crt3_standard_v1"
INICIO_HOMOLOGACAO_CRT3 = date(2026, 7, 1)
INICIO_PRODUCAO_CRT3 = date(2026, 8, 3)
MODELOS_SUPORTADOS = frozenset({"55", "65"})


def emissao_ibs_cbs_obrigatoria(*, uf, crt, modelo, ambiente, data_emissao):
    if str(uf or "").upper() != "GO" or str(crt or "") != "3":
        return False
    if str(modelo or "") not in MODELOS_SUPORTADOS:
        return False
    limite = (
        INICIO_PRODUCAO_CRT3
        if str(ambiente or "").upper() == "PRODUCAO"
        else INICIO_HOMOLOGACAO_CRT3
    )
    return data_emissao >= limite
