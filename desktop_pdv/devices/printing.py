from __future__ import annotations

import ctypes
import platform
from ctypes import wintypes


class ErroImpressao(RuntimeError):
    pass


def _linha(texto: str = "", largura: int = 48) -> str:
    return str(texto or "")[:largura]


def _colunas(esquerda: str, direita: str, largura: int = 48) -> str:
    esquerda = str(esquerda or "")
    direita = str(direita or "")
    espacos = max(1, largura - len(esquerda) - len(direita))
    return _linha(f"{esquerda}{' ' * espacos}{direita}", largura)


def montar_texto_cupom(payload: dict, largura: int = 48) -> str:
    venda = payload.get("venda", {})
    linhas = [
        _linha(venda.get("empresa", "SUPERMERCADO"), largura).center(largura),
        _linha(venda.get("filial", ""), largura).center(largura),
        "-" * largura,
        _colunas(f"VENDA #{venda.get('id', '')}", venda.get("data", "")[:19], largura),
        _linha(f"OPERADOR: {venda.get('operador', '')}", largura),
        _linha(f"CLIENTE: {venda.get('cliente', 'Cliente avulso')}", largura),
        "-" * largura,
    ]
    for item in payload.get("itens", []):
        linhas.append(_linha(f"{item.get('sequencia', '')} {item.get('produto', '')}", largura))
        detalhe = f"{item.get('quantidade', '0')} x R$ {item.get('preco_unitario', '0,00')}"
        linhas.append(_colunas(detalhe, f"R$ {item.get('total', '0,00')}", largura))
    linhas.extend(
        [
            "-" * largura,
            _colunas("SUBTOTAL", f"R$ {venda.get('total_bruto', '0,00')}", largura),
            _colunas("DESCONTOS", f"R$ {venda.get('desconto', '0,00')}", largura),
            _colunas("TOTAL", f"R$ {venda.get('total_liquido', '0,00')}", largura),
            "-" * largura,
            "PAGAMENTOS",
        ]
    )
    for pagamento in payload.get("pagamentos", []):
        linhas.append(_colunas(pagamento.get("forma", ""), f"R$ {pagamento.get('valor', '0,00')}", largura))
        if pagamento.get("nsu"):
            linhas.append(_linha(f"NSU: {pagamento['nsu']}", largura))
    rodape = payload.get("impressao", {}).get("mensagem_rodape", "")
    linhas.extend(["-" * largura, _linha(rodape, largura).center(largura), "", ""])
    return "\n".join(linhas)


def montar_cupom_escpos(payload: dict, cortar: bool = True) -> bytes:
    texto = montar_texto_cupom(payload).encode("cp850", errors="replace")
    comandos = [b"\x1b@", texto, b"\n\n"]
    if payload.get("gaveta", {}).get("abrir"):
        comandos.append(montar_pulso_gaveta_escpos(inicializar=False))
    if cortar:
        comandos.append(b"\x1dV\x42\x00")
    return b"".join(comandos)


def montar_pulso_gaveta_escpos(inicializar: bool = True) -> bytes:
    comandos = []
    if inicializar:
        comandos.append(b"\x1b@")
    comandos.append(b"\x1bp\x00\x19\xfa")
    return b"".join(comandos)


def imprimir_raw_windows(impressora: str, dados: bytes, titulo: str = "Cupom PDV") -> int:
    if platform.system() != "Windows":
        raise ErroImpressao("Impressao RAW esta disponivel somente no app Windows.")
    if not impressora.strip():
        raise ErroImpressao("Nenhuma impressora foi configurada para o cupom.")
    if not dados:
        raise ErroImpressao("O cupom esta vazio.")

    class DocInfo(ctypes.Structure):
        _fields_ = [("pDocName", wintypes.LPWSTR), ("pOutputFile", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR)]

    spooler = ctypes.WinDLL("winspool.drv", use_last_error=True)
    handle = wintypes.HANDLE()
    spooler.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), wintypes.LPVOID]
    spooler.OpenPrinterW.restype = wintypes.BOOL
    if not spooler.OpenPrinterW(impressora, ctypes.byref(handle), None):
        raise ErroImpressao(f"Nao foi possivel abrir a impressora {impressora}: {ctypes.WinError(ctypes.get_last_error())}")
    documento_iniciado = pagina_iniciada = False
    try:
        info = DocInfo(titulo, None, "RAW")
        if not spooler.StartDocPrinterW(handle, 1, ctypes.byref(info)):
            raise ErroImpressao(f"Nao foi possivel iniciar o cupom: {ctypes.WinError(ctypes.get_last_error())}")
        documento_iniciado = True
        if not spooler.StartPagePrinter(handle):
            raise ErroImpressao(f"Nao foi possivel iniciar a pagina: {ctypes.WinError(ctypes.get_last_error())}")
        pagina_iniciada = True
        buffer = ctypes.create_string_buffer(dados)
        escritos = wintypes.DWORD()
        if not spooler.WritePrinter(handle, buffer, len(dados), ctypes.byref(escritos)) or escritos.value != len(dados):
            raise ErroImpressao(f"Falha ao enviar dados para {impressora}.")
        return escritos.value
    finally:
        if pagina_iniciada:
            spooler.EndPagePrinter(handle)
        if documento_iniciado:
            spooler.EndDocPrinter(handle)
        spooler.ClosePrinter(handle)
