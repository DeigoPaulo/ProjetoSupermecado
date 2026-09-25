from dataclasses import dataclass


VERSAO_CATALOGO = "IT_2025_002_v1.60_2026-06-23"
FONTE_OFICIAL = (
    "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?"
    "tipoConteudo=%2FNJarYc9nus%3D"
)
FONTE_DADOS_ABERTOS = (
    "https://piloto-cbs.tributos.gov.br/servico/calculadora-consumo/api/"
    "calculadora/dados-abertos/classificacoes-tributarias/cbs-ibs"
)
DATA_CONSULTA = "2026-09-24"


class ClassificacaoIbsCbsInvalida(ValueError):
    pass


@dataclass(frozen=True)
class ClassificacaoIbsCbs:
    cst: str
    cclass_trib: str
    descricao: str
    modelos: frozenset[str]
    suportada: bool
    causa_bloqueio: str = ""


# O catalogo e intencionalmente minimo. Cada entrada foi confrontada com os dados
# abertos oficiais na data acima; ausencia no mapa nunca significa permissao.
CLASSIFICACOES = {
    ("000", "000001"): ClassificacaoIbsCbs(
        cst="000",
        cclass_trib="000001",
        descricao="Situacoes tributadas integralmente pelo IBS e CBS",
        modelos=frozenset({"55", "65"}),
        suportada=True,
    ),
    ("000", "000003"): ClassificacaoIbsCbs(
        cst="000",
        cclass_trib="000003",
        descricao="Regime automotivo - projetos incentivados (art. 311)",
        modelos=frozenset({"55"}),
        suportada=False,
        causa_bloqueio="regime automotivo especial nao implementado",
    ),
}


def validar_classificacao(cst, cclass_trib, modelo):
    cst = str(cst or "").strip()
    cclass_trib = str(cclass_trib or "").strip()
    modelo = str(modelo or "").strip()
    prefixo = "cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual"
    if len(cst) != 3 or not cst.isdigit():
        raise ClassificacaoIbsCbsInvalida(f"{prefixo}: CST IBS/CBS invalido")
    if len(cclass_trib) != 6 or not cclass_trib.isdigit():
        raise ClassificacaoIbsCbsInvalida(f"{prefixo}: cClassTrib IBS/CBS invalido")
    if cst == "620":
        raise ClassificacaoIbsCbsInvalida(f"{prefixo}: tributacao monofasica nao implementada")
    classificacao = CLASSIFICACOES.get((cst, cclass_trib))
    if classificacao is None:
        raise ClassificacaoIbsCbsInvalida(
            f"{prefixo}: CST {cst} e cClassTrib {cclass_trib} nao catalogados no recorte"
        )
    if modelo not in classificacao.modelos:
        raise ClassificacaoIbsCbsInvalida(
            f"{prefixo}: cClassTrib {cclass_trib} incompativel com o modelo {modelo}"
        )
    if not classificacao.suportada:
        raise ClassificacaoIbsCbsInvalida(
            f"{prefixo}: {classificacao.causa_bloqueio or 'classificacao especial'}"
        )
    return classificacao
