from decimal import Decimal, InvalidOperation

from django import template

from apps.core_forms import formatar_decimal_sem_zeros


register = template.Library()


@register.filter
def quantidade_br(valor):
    if valor in (None, ""):
        return "0"
    try:
        numero = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return valor

    if not numero.is_finite():
        return valor
    return formatar_decimal_sem_zeros(numero).replace(".", ",")


@register.filter
def quantidade_input(valor):
    """Formata quantidade para o valor técnico de um input HTML number."""
    if valor in (None, ""):
        return ""
    try:
        numero = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return valor
    if not numero.is_finite():
        return valor
    return formatar_decimal_sem_zeros(numero)


@register.filter
def peso_br(valor):
    """Formata medições em kg com três casas fixas."""
    if valor in (None, ""):
        return "0,000"
    try:
        numero = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return valor
    if not numero.is_finite():
        return valor
    return format(numero, ".3f").replace(".", ",")
