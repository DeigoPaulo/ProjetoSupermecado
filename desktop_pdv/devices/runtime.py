from __future__ import annotations

import ctypes
import hashlib
import os
from contextlib import contextmanager
from ctypes import wintypes


_ERROR_ALREADY_EXISTS = 183


class InstanciaPdvEmUso(RuntimeError):
    pass


def nome_mutex_terminal(terminal_id: str) -> str:
    identificador = str(terminal_id or "").strip()
    if not identificador:
        raise ValueError("Identificador do terminal ausente para instancia unica.")
    resumo = hashlib.sha256(identificador.encode("utf-8")).hexdigest()[:32]
    return rf"Local\SupermercadoPDV-{resumo}"


@contextmanager
def instancia_unica_terminal(terminal_id: str):
    if os.name != "nt":
        yield
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    nome = nome_mutex_terminal(terminal_id)
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, nome)
    erro = ctypes.get_last_error()
    if not handle:
        raise OSError(erro, "Nao foi possivel reservar a instancia do PDV.")
    if erro == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise InstanciaPdvEmUso(
            "Este terminal PDV ja esta aberto nesta sessao do Windows."
        )
    try:
        yield
    finally:
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)
