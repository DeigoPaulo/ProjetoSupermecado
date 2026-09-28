from decimal import Decimal, InvalidOperation

from django import forms


def formatar_decimal_sem_zeros(numero):
    """Remove zeros somente da parte fracionária de um número decimal."""
    if numero == 0:
        return "0"
    texto = format(numero, "f")
    if "." not in texto:
        return texto
    inteiro, decimal = texto.split(".", 1)
    decimal = decimal.rstrip("0")
    return inteiro if not decimal else f"{inteiro}.{decimal}"


def _decimal_sem_zeros(valor):
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not numero.is_finite():
        return None
    return formatar_decimal_sem_zeros(numero)


class QuantidadeNumberInput(forms.NumberInput):
    """Encurta somente valores numéricos iniciais, preservando dados submetidos."""

    def format_value(self, value):
        if isinstance(value, (Decimal, int, float)) and not isinstance(value, bool):
            formatado = _decimal_sem_zeros(value)
            if formatado is not None:
                return formatado
        return super().format_value(value)


def aplicar_select2(form, campos, placeholder="Pesquise ou selecione", ajax_urls=None):
    ajax_urls = ajax_urls or {}
    for campo in campos:
        if campo not in form.fields:
            continue
        widget = form.fields[campo].widget
        classes = widget.attrs.get("class", "").split()
        if "select2-field" not in classes:
            classes.append("select2-field")
        widget.attrs["class"] = " ".join(classes).strip()
        widget.attrs.setdefault("data-placeholder", placeholder)
        if campo in ajax_urls:
            widget.attrs["data-ajax-url"] = ajax_urls[campo]
            widget.attrs.setdefault("data-minimum-input-length", "0")
