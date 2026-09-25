from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .catalogo import validar_classificacao


CENTAVO = Decimal("0.01")
ALIQUOTA_IBS_UF_2026 = Decimal("0.1000")
ALIQUOTA_IBS_MUNICIPIO_2026 = Decimal("0.0000")
ALIQUOTA_CBS_2026 = Decimal("0.9000")


def _decimal(valor):
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or 0))


def arredondar_monetario(valor):
    return _decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_base_operacao_padrao(
    *, valor_produtos, desconto, valor_pis, valor_cofins, valor_icms, valor_fcp
):
    base = (
        _decimal(valor_produtos)
        - _decimal(desconto)
        - _decimal(valor_pis)
        - _decimal(valor_cofins)
        - _decimal(valor_icms)
        - _decimal(valor_fcp)
    )
    base = arredondar_monetario(base)
    if base < 0:
        raise ValueError("Base IBS/CBS negativa no recorte fiscal padrao")
    return base


@dataclass(frozen=True)
class CalculoIbsCbs:
    cst: str
    cclass_trib: str
    base: Decimal
    aliquota_ibs_uf: Decimal
    valor_ibs_uf: Decimal
    aliquota_ibs_municipio: Decimal
    valor_ibs_municipio: Decimal
    valor_ibs: Decimal
    aliquota_cbs: Decimal
    valor_cbs: Decimal


def calcular_ibs_cbs_padrao(*, valor_operacao, cst, cclass_trib, modelo):
    classificacao = validar_classificacao(cst, cclass_trib, modelo)
    base = arredondar_monetario(valor_operacao)
    if base < 0:
        raise ValueError("Base IBS/CBS negativa no recorte fiscal padrao")
    valor_ibs_uf = arredondar_monetario(base * ALIQUOTA_IBS_UF_2026 / Decimal("100"))
    valor_ibs_municipio = arredondar_monetario(
        base * ALIQUOTA_IBS_MUNICIPIO_2026 / Decimal("100")
    )
    valor_cbs = arredondar_monetario(base * ALIQUOTA_CBS_2026 / Decimal("100"))
    return CalculoIbsCbs(
        cst=classificacao.cst,
        cclass_trib=classificacao.cclass_trib,
        base=base,
        aliquota_ibs_uf=ALIQUOTA_IBS_UF_2026,
        valor_ibs_uf=valor_ibs_uf,
        aliquota_ibs_municipio=ALIQUOTA_IBS_MUNICIPIO_2026,
        valor_ibs_municipio=valor_ibs_municipio,
        valor_ibs=arredondar_monetario(valor_ibs_uf + valor_ibs_municipio),
        aliquota_cbs=ALIQUOTA_CBS_2026,
        valor_cbs=valor_cbs,
    )


def totalizar_calculos(calculos):
    calculos = tuple(calculos)
    return {
        "base": sum((item.base for item in calculos), Decimal("0.00")),
        "valor_ibs_uf": sum((item.valor_ibs_uf for item in calculos), Decimal("0.00")),
        "valor_ibs_municipio": sum(
            (item.valor_ibs_municipio for item in calculos), Decimal("0.00")
        ),
        "valor_ibs": sum((item.valor_ibs for item in calculos), Decimal("0.00")),
        "valor_cbs": sum((item.valor_cbs for item in calculos), Decimal("0.00")),
    }
