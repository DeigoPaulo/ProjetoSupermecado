from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class ErroLeitorCartao(RuntimeError):
    pass


class _ScardIoRequest(ctypes.Structure):
    _fields_ = [("dwProtocol", wintypes.DWORD), ("cbPciLength", wintypes.DWORD)]


class WindowsPcsc:
    SCARD_SCOPE_USER = 0
    SCARD_SHARE_SHARED = 2
    SCARD_PROTOCOL_T0 = 1
    SCARD_PROTOCOL_T1 = 2
    SCARD_LEAVE_CARD = 0
    SCARD_S_SUCCESS = 0

    def __init__(self):
        if os.name != "nt":
            raise ErroLeitorCartao("Leitor PC/SC disponivel somente no Windows.")
        try:
            self.api = ctypes.WinDLL("winscard.dll")
        except OSError as erro:
            raise ErroLeitorCartao("Servico de cartao inteligente do Windows indisponivel.") from erro

    @staticmethod
    def _check(resultado: int, mensagem: str) -> None:
        if resultado != WindowsPcsc.SCARD_S_SUCCESS:
            codigo = ctypes.c_uint32(resultado).value
            raise ErroLeitorCartao(f"{mensagem} (PC/SC 0x{codigo:08X}).")

    def listar_leitores(self) -> list[str]:
        contexto = ctypes.c_void_p()
        self._check(self.api.SCardEstablishContext(self.SCARD_SCOPE_USER, None, None, ctypes.byref(contexto)), "Nao foi possivel iniciar o leitor")
        try:
            tamanho = wintypes.DWORD(0)
            resultado = self.api.SCardListReadersW(contexto, None, None, ctypes.byref(tamanho))
            self._check(resultado, "Nenhum leitor PC/SC foi encontrado")
            buffer = ctypes.create_unicode_buffer(tamanho.value)
            self._check(self.api.SCardListReadersW(contexto, None, buffer, ctypes.byref(tamanho)), "Nao foi possivel listar os leitores")
            return [nome for nome in buffer[: tamanho.value].split("\x00") if nome]
        finally:
            self.api.SCardReleaseContext(contexto)

    def ler_uid(self, leitor_preferido: str = "") -> str:
        contexto = ctypes.c_void_p()
        cartao = ctypes.c_void_p()
        protocolo = wintypes.DWORD()
        self._check(self.api.SCardEstablishContext(self.SCARD_SCOPE_USER, None, None, ctypes.byref(contexto)), "Nao foi possivel iniciar o leitor")
        conectado = False
        try:
            tamanho = wintypes.DWORD(0)
            self._check(self.api.SCardListReadersW(contexto, None, None, ctypes.byref(tamanho)), "Nenhum leitor PC/SC foi encontrado")
            buffer = ctypes.create_unicode_buffer(tamanho.value)
            self._check(self.api.SCardListReadersW(contexto, None, buffer, ctypes.byref(tamanho)), "Nao foi possivel listar os leitores")
            leitores = [nome for nome in buffer[: tamanho.value].split("\x00") if nome]
            if not leitores:
                raise ErroLeitorCartao("Nenhum leitor PC/SC foi encontrado.")
            leitor = next((nome for nome in leitores if leitor_preferido.lower() in nome.lower()), leitores[0]) if leitor_preferido else leitores[0]
            resultado = self.api.SCardConnectW(
                contexto,
                leitor,
                self.SCARD_SHARE_SHARED,
                self.SCARD_PROTOCOL_T0 | self.SCARD_PROTOCOL_T1,
                ctypes.byref(cartao),
                ctypes.byref(protocolo),
            )
            self._check(resultado, "Aproxime um cartao compativel do leitor")
            conectado = True
            comando = (ctypes.c_ubyte * 5)(0xFF, 0xCA, 0x00, 0x00, 0x00)
            resposta = (ctypes.c_ubyte * 258)()
            tamanho_resposta = wintypes.DWORD(len(resposta))
            pci = _ScardIoRequest(protocolo.value, ctypes.sizeof(_ScardIoRequest))
            self._check(
                self.api.SCardTransmit(cartao, ctypes.byref(pci), comando, len(comando), None, resposta, ctypes.byref(tamanho_resposta)),
                "O leitor nao conseguiu obter o identificador do cartao",
            )
            dados = bytes(resposta[: tamanho_resposta.value])
            if len(dados) < 3 or dados[-2:] != b"\x90\x00":
                raise ErroLeitorCartao("Cartao lido, mas o identificador NFC nao foi disponibilizado.")
            uid = dados[:-2].hex().upper()
            if not uid:
                raise ErroLeitorCartao("O cartao nao retornou um identificador.")
            return uid
        finally:
            if conectado:
                self.api.SCardDisconnect(cartao, self.SCARD_LEAVE_CARD)
            self.api.SCardReleaseContext(contexto)


def ler_uid_pcsc(leitor_preferido: str = "", api=None) -> str:
    backend = api or WindowsPcsc()
    uid = backend.ler_uid(leitor_preferido)
    token = "".join(str(uid).split()).upper()
    if not token or len(token) > 128 or any(caractere not in "0123456789ABCDEF" for caractere in token):
        raise ErroLeitorCartao("Identificador invalido retornado pelo leitor.")
    return token
