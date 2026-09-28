from decimal import Decimal, ROUND_HALF_UP


CENTAVOS = Decimal("0.01")
PRECISAO_CUSTO = Decimal("0.000001")


def quantizar_moeda(valor):
    """Consolida valores comerciais e financeiros no limite de centavos."""
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def quantizar_custo(valor):
    """Limita custos gerenciais a seis casas sem reduzi-los a centavos."""
    return Decimal(valor).quantize(PRECISAO_CUSTO, rounding=ROUND_HALF_UP)
