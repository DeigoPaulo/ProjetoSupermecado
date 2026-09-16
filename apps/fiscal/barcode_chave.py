"""Code 128 híbrido C/A para a chave de acesso NF-e/NFC-e."""

import base64

from barcode.codex import Code128, code128
from barcode.writer import SVGWriter
from django.core.exceptions import ValidationError

from .chave_acesso import normalizar_chave_acesso


CONTRATO_BARCODE_CHAVE_FISCAL = "fiscal_access_key_code128_ca_v1"


class Code128ChaveFiscal(Code128):
    """Restringe a alternância da chave fiscal aos conjuntos C e A."""

    def _maybe_switch_charset(self, pos):
        caractere = self.code[pos]
        proximos = self.code[pos : pos + 10]
        digitos_seguidos = 0
        for item in proximos:
            if not item.isdigit():
                break
            digitos_seguidos += 1

        codigos = []
        if self._charset == "C" and not caractere.isdigit():
            codigos = self._new_charset("A")
            if len(self._buffer) == 1:
                codigos.append(self._convert(self._buffer[0]))
                self._buffer = ""
        elif self._charset == "A" and digitos_seguidos > 3:
            codigos = self._new_charset("C")
        return codigos

    def _build(self):
        codigos = [code128.START_CODES[self._charset]]
        for posicao, caractere in enumerate(self.code):
            codigos.extend(self._maybe_switch_charset(posicao))
            codigo = self._convert(caractere)
            if codigo is not None:
                codigos.append(codigo)
        if len(self._buffer) == 1:
            codigos.extend(self._new_charset("A"))
            codigos.append(self._convert(self._buffer[0]))
            self._buffer = ""
        return self._try_to_optimize(codigos)


def _chave_valida(valor):
    chave = normalizar_chave_acesso(str(valor or ""))
    if not chave:
        raise ValidationError("Chave de acesso inválida para gerar o código de barras.")
    return chave


def codigos_code128_chave(valor):
    """Expõe os símbolos antes do checksum para regressão do contrato C/A."""
    return Code128ChaveFiscal(_chave_valida(valor), writer=SVGWriter()).encoded


def gerar_codigo_barras_chave_data_uri(valor):
    chave = _chave_valida(valor)
    svg = Code128ChaveFiscal(chave, writer=SVGWriter()).render({
        "write_text": False,
        "module_height": 10.0,
        "module_width": 0.18,
        "quiet_zone": 1.5,
    })
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
