from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation

from devices.printing import ErroImpressao


def _ascii(valor: object, limite: int = 80) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", errors="ignore").decode("ascii")
    return " ".join(texto.replace("^", " ").replace("~", " ").split())[:limite]


def _inteiro(valor: object, padrao: int, minimo: int, maximo: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = padrao
    return min(maximo, max(minimo, numero))


def _decimal(valor: object, padrao: str) -> Decimal:
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(padrao)


def _dots(mm: object, dpi: int) -> int:
    return max(1, int((_decimal(mm, "1") * dpi / Decimal("25.4")).quantize(Decimal("1"))))


def _preco(valor: object) -> str:
    return f"R$ {_decimal(valor, '0'):.2f}".replace(".", ",")


def _validar_payload(payload: dict) -> tuple[dict, list[dict], int]:
    if not isinstance(payload, dict):
        raise ErroImpressao("Payload de etiquetas invalido.")
    modelo = payload.get("modelo") or {}
    itens = payload.get("itens") or []
    if not isinstance(modelo, dict) or not isinstance(itens, list) or not itens:
        raise ErroImpressao("Informe modelo e ao menos um item para imprimir etiquetas.")
    dpi = _inteiro(payload.get("dpi"), 203, 100, 1200)
    return modelo, itens[:500], dpi


def montar_etiquetas_zpl(payload: dict) -> bytes:
    modelo, itens, dpi = _validar_payload(payload)
    largura = _dots(modelo.get("largura_mm", 110), dpi)
    altura = _dots(modelo.get("altura_mm", 30), dpi)
    velocidade = _inteiro(payload.get("velocidade"), 4, 1, 14)
    densidade = _inteiro(payload.get("densidade"), 8, 0, 30)
    blocos: list[str] = []
    for item in itens:
        copias = _inteiro(item.get("copias"), 1, 1, 100)
        nome = _ascii(item.get("nome"), 60)
        codigo = _ascii(item.get("codigo"), 40)
        preco = _preco(item.get("preco"))
        barcode_height = max(28, min(80, altura // 4))
        blocos.append(
            "\n".join(
                [
                    "^XA",
                    f"^PW{largura}",
                    f"^LL{altura}",
                    f"^PR{velocidade}",
                    f"^MD{densidade}",
                    f"^FO20,15^A0N,28,24^FB{max(80, largura - 40)},2,2,L^FD{nome}^FS",
                    f"^FO20,{max(72, altura // 3)}^A0N,46,40^FD{preco}^FS",
                    f"^FO20,{max(125, altura - barcode_height - 28)}^BY2^BCN,{barcode_height},Y,N,N,A^FD{codigo}^FS",
                    f"^PQ{copias}",
                    "^XZ",
                ]
            )
        )
    return ("\n".join(blocos) + "\n").encode("ascii")


def montar_etiquetas_epl(payload: dict) -> bytes:
    modelo, itens, dpi = _validar_payload(payload)
    largura = _dots(modelo.get("largura_mm", 110), dpi)
    altura = _dots(modelo.get("altura_mm", 30), dpi)
    gap = _dots(modelo.get("gap_vertical_mm", 2), dpi)
    velocidade = _inteiro(payload.get("velocidade"), 4, 1, 6)
    densidade = _inteiro(payload.get("densidade"), 8, 0, 15)
    blocos: list[str] = []
    for item in itens:
        copias = _inteiro(item.get("copias"), 1, 1, 100)
        nome = _ascii(item.get("nome"), 45).replace('"', "")
        codigo = _ascii(item.get("codigo"), 30).replace('"', "")
        preco = _preco(item.get("preco"))
        blocos.append(
            "\n".join(
                [
                    "N",
                    f"q{largura}",
                    f"Q{altura},{gap}",
                    f"S{velocidade}",
                    f"D{densidade}",
                    f'A20,15,0,3,1,1,N,"{nome}"',
                    f'A20,{max(55, altura // 3)},0,5,2,2,N,"{preco}"',
                    f'B20,{max(105, altura - 90)},0,1,2,4,55,B,"{codigo}"',
                    f"P{copias}",
                ]
            )
        )
    return ("\n".join(blocos) + "\n").encode("ascii")


def montar_etiquetas_ppla(payload: dict) -> bytes:
    modelo, itens, dpi = _validar_payload(payload)
    largura = _dots(modelo.get("largura_mm", 110), dpi)
    altura = _dots(modelo.get("altura_mm", 30), dpi)
    velocidade = _inteiro(payload.get("velocidade"), 4, 1, 6)
    densidade = _inteiro(payload.get("densidade"), 8, 0, 15)
    blocos: list[str] = []
    for item in itens:
        copias = _inteiro(item.get("copias"), 1, 1, 100)
        nome = _ascii(item.get("nome"), 45).replace('"', "")
        codigo = _ascii(item.get("codigo"), 30).replace('"', "")
        preco = _preco(item.get("preco"))
        blocos.append(
            "\n".join(
                [
                    "\x02L",
                    f"D{densidade}",
                    f"S{velocidade}",
                    f"q{largura}",
                    f"Q{altura},0",
                    f'121100001000015{nome}',
                    f'191100002000{max(55, altura // 3):03d}{preco}',
                    f'1E1100002000{max(105, altura - 90):03d}{codigo}',
                    f"Q{copias}",
                    "E",
                ]
            )
        )
    return ("\n".join(blocos) + "\n").encode("ascii")


def montar_etiquetas_nativas(payload: dict) -> bytes:
    linguagem = _ascii(payload.get("linguagem"), 10).upper()
    if linguagem == "ZPL":
        return montar_etiquetas_zpl(payload)
    if linguagem in {"EPL", "PPLB"}:
        return montar_etiquetas_epl(payload)
    if linguagem == "PPLA":
        return montar_etiquetas_ppla(payload)
    raise ErroImpressao("Selecione ZPL, EPL, PPLA ou PPLB para impressao nativa de etiquetas.")
