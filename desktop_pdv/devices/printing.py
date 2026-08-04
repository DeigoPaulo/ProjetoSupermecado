from __future__ import annotations

import ctypes
import platform
import textwrap
from ctypes import wintypes
from datetime import datetime
from decimal import Decimal, InvalidOperation


class ErroImpressao(RuntimeError):
    pass


def _linha(texto: str = "", largura: int = 48) -> str:
    return str(texto or "")[:largura]


def _colunas(esquerda: str, direita: str, largura: int = 48) -> str:
    esquerda = str(esquerda or "")
    direita = str(direita or "")
    espacos = max(1, largura - len(esquerda) - len(direita))
    return _linha(f"{esquerda}{' ' * espacos}{direita}", largura)


def _centralizar(texto: str, largura: int) -> list[str]:
    return [linha.center(largura) for linha in textwrap.wrap(str(texto or ""), largura) or [""]]


def _quebrar(texto: str, largura: int) -> list[str]:
    return textwrap.wrap(str(texto or ""), largura, break_long_words=True, break_on_hyphens=False) or [""]


def _decimal(valor) -> Decimal:
    texto = str(valor or "0").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0")


def _data_hora_br(valor: str) -> str:
    try:
        data = datetime.fromisoformat(str(valor or "").replace("Z", "+00:00"))
    except ValueError:
        return str(valor or "")[:19]
    return data.strftime("%d/%m/%Y %H:%M")


def _largura_cupom(payload: dict, largura: int | None = None) -> int:
    if largura:
        return largura
    return 40 if payload.get("impressao", {}).get("modelo_papel") == "58MM" else 56


def montar_texto_cupom(payload: dict, largura: int | None = None) -> str:
    largura = _largura_cupom(payload, largura)
    venda = payload.get("venda", {})
    pagamentos = payload.get("pagamentos", [])
    total_pago = _decimal(venda.get("total_pago"))
    if not venda.get("total_pago"):
        total_pago = sum((_decimal(item.get("valor")) for item in pagamentos), Decimal("0"))
    total_liquido = _decimal(venda.get("total_liquido"))
    troco_informado = _decimal(venda.get("troco"))
    troco = max(Decimal("0"), troco_informado if venda.get("troco") else total_pago - total_liquido)
    separador = "-" * largura
    linhas = []
    linhas.extend(_centralizar(venda.get("empresa", "SUPERMERCADO"), largura))
    if venda.get("filial"):
        linhas.extend(_centralizar(venda["filial"], largura))
    if venda.get("endereco"):
        linhas.extend(_centralizar(venda["endereco"], largura))
    identificacao = "  ".join(
        parte
        for parte in [
            f"CNPJ: {venda.get('cnpj')}" if venda.get("cnpj") else "",
            f"TEL: {venda.get('telefone')}" if venda.get("telefone") else "",
        ]
        if parte
    )
    if identificacao:
        linhas.extend(_centralizar(identificacao, largura))
    linhas.extend([separador, "CUPOM NAO FISCAL - USO INTERNO".center(largura), separador])
    linhas.append(_linha("COD DESCRICAO", largura))
    linhas.append(_colunas("QTD x VL.UNIT.", "TOTAL", largura))
    for item in payload.get("itens", []):
        codigo = str(item.get("codigo_barras") or item.get("sequencia") or "")
        prefixo = f"{codigo} "
        descricao_largura = max(1, largura - len(prefixo))
        descricao = _quebrar(item.get("produto", ""), descricao_largura)
        linhas.append(_linha(prefixo + descricao[0], largura))
        linhas.extend(_linha(" " * len(prefixo) + parte, largura) for parte in descricao[1:])
        detalhe = f"{item.get('quantidade', '0')} x R$ {item.get('preco_unitario', '0,00')}"
        linhas.append(_colunas(detalhe, f"R$ {item.get('total', '0,00')}", largura))
    linhas.extend(
        [
            separador,
            _colunas("QTD. TOTAL DE ITENS:", str(venda.get("quantidade_total", len(payload.get("itens", [])))), largura),
            _colunas("VALOR TOTAL:", f"R$ {venda.get('total_liquido', '0,00')}", largura),
            separador,
            "FORMA DE PAGAMENTO",
        ]
    )
    for pagamento in pagamentos:
        linhas.append(_colunas(pagamento.get("forma", ""), f"R$ {pagamento.get('valor', '0,00')}", largura))
        if pagamento.get("nsu"):
            linhas.append(_linha(f"NSU: {pagamento['nsu']}", largura))
        if pagamento.get("codigo_autorizacao"):
            linhas.append(_linha(f"AUTORIZACAO: {pagamento['codigo_autorizacao']}", largura))
    if total_pago:
        linhas.append(_colunas("VALOR RECEBIDO:", f"R$ {total_pago:.2f}".replace(".", ","), largura))
    if troco:
        linhas.append(_colunas("TROCO:", f"R$ {troco:.2f}".replace(".", ","), largura))
    linhas.extend(
        [
            separador,
            _colunas("DATA:", _data_hora_br(venda.get("data", "")), largura),
            _colunas("OPERADOR:", venda.get("operador", ""), largura),
            _colunas("CAIXA:", f"#{venda.get('caixa', '')}", largura),
            _colunas("DOCUMENTO:", str(venda.get("id", "")), largura),
            separador,
        ]
    )
    rodape = payload.get("impressao", {}).get("mensagem_rodape", "")
    if rodape:
        linhas.extend(_centralizar(rodape, largura))
    linhas.extend(["NAO E DOCUMENTO FISCAL".center(largura), "=" * largura, "", ""])
    return "\n".join(linhas)


def montar_texto_comanda_entrega(payload: dict, largura: int | None = None) -> str:
    largura = _largura_cupom(payload, largura)
    pedido = payload.get("pedido", {})
    separador = "-" * largura
    linhas = []
    linhas.extend(_centralizar(pedido.get("empresa", "SUPERMERCADO"), largura))
    if pedido.get("filial"):
        linhas.extend(_centralizar(pedido["filial"], largura))
    linhas.extend(["=" * largura, _centralizar(f"COMANDA DE ENTREGA #{pedido.get('id', '')}", largura)[0], "=" * largura])
    linhas.append(_colunas("DATA:", _data_hora_br(pedido.get("criado_em", "")), largura))
    linhas.append(_colunas("STATUS:", pedido.get("status", ""), largura))
    linhas.extend([separador, "CLIENTE", _linha(pedido.get("cliente", ""), largura)])
    if pedido.get("telefone"):
        linhas.append(_linha(f"TELEFONE: {pedido['telefone']}", largura))
    linhas.append("ENDERECO:")
    endereco = pedido.get("endereco", "")
    if pedido.get("bairro"):
        endereco = f"{endereco} - {pedido['bairro']}"
    linhas.extend(_quebrar(endereco, largura))
    linhas.extend([separador, "ITENS PARA ENTREGA"])
    for indice, item in enumerate(payload.get("itens", []), start=1):
        descricao = f"{indice:02d} {item.get('produto', '')}"
        linhas.extend(_quebrar(descricao, largura))
        quantidade = f"QTD: {item.get('quantidade', '0')} {item.get('unidade', '')}".strip()
        linhas.append(_linha(quantidade, largura))
    linhas.extend([separador, _colunas("TOTAL:", f"R$ {pedido.get('total', '0,00')}", largura)])
    pagamento = pedido.get("pagamento", "Pendente")
    linhas.append(_colunas("PAGAMENTO:", pagamento, largura))
    if pedido.get("forma_pagamento"):
        linhas.append(_linha(f"FORMA: {pedido['forma_pagamento']}", largura))
    if pedido.get("referencia_pagamento"):
        linhas.extend(_quebrar(f"REFERENCIA: {pedido['referencia_pagamento']}", largura))
    if pedido.get("observacoes"):
        linhas.extend([separador, "OBSERVACOES"])
        linhas.extend(_quebrar(pedido["observacoes"], largura))
    linhas.extend([separador, "ENTREGADOR: __________________________", "ASSINATURA: __________________________", "", ""])
    return "\n".join(linhas)
def _agrupar_chave_acesso(chave: str) -> str:
    digitos = "".join(caractere for caractere in str(chave or "") if caractere.isdigit())
    return " ".join(digitos[indice:indice + 4] for indice in range(0, len(digitos), 4))


def montar_texto_danfe_nfce(payload: dict, largura: int | None = None) -> str:
    largura = _largura_cupom(payload, largura)
    venda = payload.get("venda", {})
    fiscal = payload.get("fiscal", {})
    chave = "".join(caractere for caractere in str(fiscal.get("chave_acesso", "")) if caractere.isdigit())
    if len(chave) != 44:
        raise ErroImpressao("NFC-e sem chave de acesso valida com 44 digitos.")
    if not str(fiscal.get("qrcode_url", "")).strip():
        raise ErroImpressao("NFC-e sem QR Code oficial para impressao.")
    separador = "-" * largura
    linhas = []
    linhas.extend(_centralizar(venda.get("empresa", "SUPERMERCADO"), largura))
    if venda.get("filial"):
        linhas.extend(_centralizar(venda["filial"], largura))
    if venda.get("endereco"):
        linhas.extend(_centralizar(venda["endereco"], largura))
    identificacao = "  ".join(parte for parte in [f"CNPJ: {venda.get('cnpj')}" if venda.get("cnpj") else "", f"TEL: {venda.get('telefone')}" if venda.get("telefone") else ""] if parte)
    if identificacao:
        linhas.extend(_centralizar(identificacao, largura))
    linhas.extend([separador, "DOCUMENTO AUXILIAR DA NOTA FISCAL".center(largura), "DE CONSUMIDOR ELETRONICA - NFC-e".center(largura)])
    if fiscal.get("contingencia"):
        linhas.extend([separador, "EMITIDA EM CONTINGENCIA".center(largura), "PENDENTE DE AUTORIZACAO".center(largura)])
    linhas.extend([separador, _linha("COD DESCRICAO", largura), _colunas("QTD x VL.UNIT.", "TOTAL R$", largura)])
    for item in payload.get("itens", []):
        codigo = str(item.get("codigo_barras") or item.get("sequencia") or "")
        prefixo = f"{codigo} "
        descricao = _quebrar(item.get("produto", ""), max(1, largura - len(prefixo)))
        linhas.append(_linha(prefixo + descricao[0], largura))
        linhas.extend(_linha(" " * len(prefixo) + parte, largura) for parte in descricao[1:])
        detalhe = f"{item.get('quantidade', '0')} x R$ {item.get('preco_unitario', '0,00')}"
        linhas.append(_colunas(detalhe, f"R$ {item.get('total', '0,00')}", largura))
    linhas.extend([separador, _colunas("QTD. TOTAL DE ITENS:", str(venda.get("quantidade_total", len(payload.get("itens", [])))), largura), _colunas("VALOR TOTAL:", f"R$ {venda.get('total_bruto', '0,00')}", largura), _colunas("DESCONTOS:", f"R$ {venda.get('desconto', '0,00')}", largura), _colunas("VALOR A PAGAR:", f"R$ {venda.get('total_liquido', '0,00')}", largura), separador, "FORMA DE PAGAMENTO"])
    for pagamento in payload.get("pagamentos", []):
        linhas.append(_colunas(pagamento.get("forma", ""), f"R$ {pagamento.get('valor', '0,00')}", largura))
    consumidor = fiscal.get("consumidor_documento")
    linhas.extend([separador, f"CONSUMIDOR: {fiscal.get('consumidor_tipo', '')} {consumidor}" if consumidor else "CONSUMIDOR NAO IDENTIFICADO", _centralizar(f"NFC-e n. {fiscal.get('numero', '')} Serie {fiscal.get('serie', '')}", largura)[0], _centralizar(_data_hora_br(fiscal.get("emitido_em") or venda.get("data", "")), largura)[0], _linha(f"PROTOCOLO: {fiscal.get('protocolo') or 'PENDENTE EM CONTINGENCIA'}", largura), separador, "CHAVE DE ACESSO".center(largura)])
    linhas.extend(_centralizar(_agrupar_chave_acesso(chave), largura))
    linhas.extend([separador, "Consulte pela chave ou leia o QR Code".center(largura)])
    if fiscal.get("url_consulta"):
        linhas.extend(_centralizar(fiscal["url_consulta"], largura))
    linhas.extend([separador, "Tributos incidentes conforme legislacao".center(largura), "aplicavel.".center(largura), "", ""])
    return "\n".join(linhas)


def montar_qrcode_escpos(conteudo: str) -> bytes:
    dados = str(conteudo or "").encode("utf-8")
    if not dados:
        raise ErroImpressao("Conteudo do QR Code fiscal ausente.")
    if len(dados) > 7000:
        raise ErroImpressao("Conteudo do QR Code fiscal excede o limite ESC/POS.")
    tamanho = len(dados) + 3
    armazenar = b"\x1d(k" + bytes([tamanho & 0xFF, (tamanho >> 8) & 0xFF]) + b"1P0" + dados
    return b"".join([b"\x1d(k\x04\x001A2\x00", b"\x1d(k\x03\x001C\x06", b"\x1d(k\x03\x001E1", armazenar, b"\x1d(k\x03\x001Q0"])


def montar_danfe_nfce_escpos(payload: dict, cortar: bool = True) -> bytes:
    texto = montar_texto_danfe_nfce(payload).encode("cp850", errors="replace")
    qrcode = montar_qrcode_escpos(payload.get("fiscal", {}).get("qrcode_url", ""))
    comandos = [b"\x1b@", b"\x1bM\x01", b"\x1bt\x02", texto, b"\n", b"\x1ba\x01", qrcode, b"\n\n", b"\x1ba\x00"]
    if payload.get("gaveta", {}).get("abrir"):
        comandos.append(montar_pulso_gaveta_escpos(inicializar=False))
    if cortar:
        comandos.append(b"\x1dV\x42\x00")
    return b"".join(comandos)

def montar_cupom_escpos(payload: dict, cortar: bool = True) -> bytes:
    if payload.get("tipo") == "danfe_nfce":
        return montar_danfe_nfce_escpos(payload, cortar=cortar)
    if payload.get("tipo") == "comanda_entrega":
        texto = montar_texto_comanda_entrega(payload).encode("cp850", errors="replace")
    else:
        texto = montar_texto_cupom(payload).encode("cp850", errors="replace")
    comandos = [b"\x1b@", b"\x1bM\x01", b"\x1bt\x02", texto, b"\n\n"]
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
