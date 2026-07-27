from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


PREFIXO_DPAPI = "dpapi:v1:"
_ENTROPIA = b"SupermercadoPDV|terminal-key|v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class ErroProtecaoSegredo(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob(dados: bytes):
    buffer = ctypes.create_string_buffer(dados)
    return _DataBlob(len(dados), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _exigir_windows() -> None:
    if os.name != "nt":
        raise ErroProtecaoSegredo("A protecao DPAPI esta disponivel somente no Windows.")


def proteger_segredo(segredo: str) -> str:
    _exigir_windows()
    dados = str(segredo or "").encode("utf-8")
    if not dados:
        raise ErroProtecaoSegredo("Segredo vazio nao pode ser protegido.")
    entrada, entrada_buffer = _blob(dados)
    entropia, entropia_buffer = _blob(_ENTROPIA)
    saida = _DataBlob()
    descricao = "Supermercado PDV - chave do terminal"
    sucesso = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(entrada),
        descricao,
        ctypes.byref(entropia),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(saida),
    )
    if not sucesso:
        raise ErroProtecaoSegredo(f"Falha ao proteger a chave do terminal (Windows {ctypes.get_last_error()}).")
    try:
        protegido = ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)
        del entrada_buffer, entropia_buffer
    return PREFIXO_DPAPI + base64.b64encode(protegido).decode("ascii")


def desproteger_segredo(valor: str) -> str:
    _exigir_windows()
    texto = str(valor or "").strip()
    if not texto.startswith(PREFIXO_DPAPI):
        raise ErroProtecaoSegredo("Formato da chave protegida nao reconhecido.")
    try:
        protegido = base64.b64decode(texto[len(PREFIXO_DPAPI) :], validate=True)
    except (ValueError, TypeError) as exc:
        raise ErroProtecaoSegredo("Chave protegida corrompida.") from exc
    entrada, entrada_buffer = _blob(protegido)
    entropia, entropia_buffer = _blob(_ENTROPIA)
    saida = _DataBlob()
    sucesso = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(entrada),
        None,
        ctypes.byref(entropia),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(saida),
    )
    if not sucesso:
        raise ErroProtecaoSegredo(
            "A chave do terminal nao pode ser aberta por este usuario do Windows."
        )
    try:
        segredo = ctypes.string_at(saida.pbData, saida.cbData).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ErroProtecaoSegredo("A chave protegida esta corrompida.") from exc
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)
        del entrada_buffer, entropia_buffer
    if not segredo:
        raise ErroProtecaoSegredo("A chave protegida esta vazia.")
    return segredo
