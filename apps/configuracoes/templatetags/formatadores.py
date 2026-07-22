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

    if numero == numero.to_integral_value():
        return f"{numero:.0f}"
    return f"{numero:.3f}".replace(".", ",")
