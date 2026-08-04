from barcode import Code128
from barcode.errors import BarcodeError
from barcode.writer import SVGWriter
from django import template
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter
def barcode_svg(value):
    codigo = str(value or "").strip()
    if not codigo:
        return ""

    try:
        svg = Code128(codigo, writer=SVGWriter()).render(
            {
                "write_text": False,
                "module_height": 9.0,
                "module_width": 0.22,
                "quiet_zone": 1.5,
            }
        ).decode("utf-8")
    except (BarcodeError, TypeError, ValueError):
        return ""

    svg = svg[svg.find("<svg") :]
    svg = svg.replace(
        "<svg ",
        '<svg class="label-barcode-svg" aria-hidden="true" focusable="false" ',
        1,
    )
    return mark_safe(svg)
