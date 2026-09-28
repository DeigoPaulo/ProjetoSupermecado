from decimal import Decimal, InvalidOperation

from django import template


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
    if numero == 0:
        return "0"
    return format(numero, "f").rstrip("0").rstrip(".").replace(".", ",")


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
    if numero == 0:
        return "0"
    return format(numero, "f").rstrip("0").rstrip(".")
