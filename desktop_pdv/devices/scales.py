from __future__ import annotations

from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
import socket


class ErroBalanca(Exception):
    pass


def _inteiro_limitado(valor, padrao, minimo, maximo):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = padrao
    return min(maximo, max(minimo, numero))


def normalizar_configuracao_balanca(configuracao: dict | None) -> dict:
    configuracao = configuracao or {}
    leitura_automatica = bool(configuracao.get("leitura_automatica"))
    return {
        "contrato": configuracao.get("contrato") or "pdv_scale_v1",
        "opcional": bool(configuracao.get("opcional", True)),
        "habilitada": bool(configuracao.get("habilitada")),
        "protocolo": configuracao.get("protocolo") or "NAO_CONFIGURADO",
        "porta": configuracao.get("porta") or "",
        "modelo": configuracao.get("modelo") or "",
        "leitura_automatica": leitura_automatica,
        "unidade_padrao": configuracao.get("unidade_padrao") or "KG",
        "precisao_decimal": _inteiro_limitado(configuracao.get("precisao_decimal"), 3, 0, 6),
        "timeout_ms": _inteiro_limitado(configuracao.get("timeout_ms"), 3000, 200, 10000),
        "baudrate": _inteiro_limitado(configuracao.get("baudrate"), 9600, 300, 921600),
        "bytesize": _inteiro_limitado(configuracao.get("bytesize"), 8, 5, 8),
        "paridade": str(configuracao.get("paridade") or "N").strip().upper()[:1],
        "stopbits": str(configuracao.get("stopbits") or "1").strip(),
        "comando_leitura": str(configuracao.get("comando_leitura") or ""),
        "terminador": str(configuracao.get("terminador") or "\\r\\n"),
        "fator_conversao": str(configuracao.get("fator_conversao") or "1"),
        "fallback_manual": bool(configuracao.get("fallback_manual", True)),
        "status_operacional": configuracao.get("status_operacional") or ("habilitada" if leitura_automatica else "manual"),
    }


def _peso_simulado():
    valor = os.environ.get("SUPERMERCADO_PDV_PESO_SIMULADO", "").strip()
    if not valor:
        return None
    try:
        peso = Decimal(valor.replace(",", "."))
    except InvalidOperation as exc:
        raise ErroBalanca("Peso simulado invalido.") from exc
    if peso <= 0:
        raise ErroBalanca("Peso simulado deve ser maior que zero.")
    return peso


def _sequencia_bytes(valor: str) -> bytes:
    if not valor:
        return b""
    try:
        return valor.encode("utf-8").decode("unicode_escape").encode("latin-1")
    except (UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise ErroBalanca("Comando ou terminador da balanca invalido.") from exc


def extrair_peso_resposta(resposta: bytes | str, *, precisao=3, fator_conversao="1") -> str:
    if isinstance(resposta, bytes):
        texto = resposta.decode("ascii", errors="ignore")
    else:
        texto = str(resposta or "")
    texto = texto.strip()
    if not texto:
        raise ErroBalanca("A balanca nao retornou dados.")
    if re.search(r"(?:^|[,;\s])(?:US|UNSTABLE|INSTAVEL)(?:$|[,;\s])", texto.upper()):
        raise ErroBalanca("A balanca informou peso instavel; aguarde a estabilizacao.")
    if re.search(r"(?:^|[,;\s])(?:OL|OVERLOAD|SOBRECARGA)(?:$|[,;\s])", texto.upper()):
        raise ErroBalanca("A balanca informou sobrecarga.")
    candidatos = re.findall(r"[+-]?\d+(?:[.,]\d+)?", texto)
    if not candidatos:
        raise ErroBalanca("A resposta da balanca nao contem um peso reconhecivel.")
    preferenciais = [valor for valor in candidatos if "." in valor or "," in valor]
    valor_bruto = (preferenciais or candidatos)[-1]
    try:
        peso = Decimal(valor_bruto.replace(",", "."))
        fator = Decimal(str(fator_conversao).replace(",", "."))
    except InvalidOperation as exc:
        raise ErroBalanca("Peso ou fator de conversao invalido.") from exc
    peso *= fator
    if peso <= 0:
        raise ErroBalanca("A balanca retornou peso zerado ou negativo.")
    return f"{peso:.{precisao}f}"


def _abrir_serial(config):
    try:
        import serial
    except ImportError as exc:
        raise ErroBalanca("Driver serial indisponivel. Instale a dependencia pyserial no app desktop.") from exc
    paridades = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}
    stopbits = {
        "1": serial.STOPBITS_ONE,
        "1.5": serial.STOPBITS_ONE_POINT_FIVE,
        "2": serial.STOPBITS_TWO,
    }
    if config["paridade"] not in paridades or config["stopbits"] not in stopbits:
        raise ErroBalanca("Paridade ou stop bits da balanca serial invalidos.")
    try:
        return serial.Serial(
            port=config["porta"],
            baudrate=config["baudrate"],
            bytesize=config["bytesize"],
            parity=paridades[config["paridade"]],
            stopbits=stopbits[config["stopbits"]],
            timeout=config["timeout_ms"] / 1000,
            write_timeout=config["timeout_ms"] / 1000,
        )
    except (serial.SerialException, OSError) as exc:
        raise ErroBalanca(f"Nao foi possivel abrir a balanca serial em {config['porta']}: {exc}") from exc


def _ler_serial(config) -> bytes:
    if not config["porta"]:
        raise ErroBalanca("Informe a porta serial da balanca.")
    comando = _sequencia_bytes(config["comando_leitura"])
    terminador = _sequencia_bytes(config["terminador"])
    conexao = _abrir_serial(config)
    try:
        if comando:
            conexao.write(comando)
            conexao.flush()
        return conexao.read_until(terminador, 256) if terminador else conexao.read(256)
    except (OSError, TimeoutError) as exc:
        raise ErroBalanca(f"Falha durante a leitura serial da balanca: {exc}") from exc
    finally:
        conexao.close()


def _endereco_tcp(porta: str):
    endereco = str(porta or "").strip()
    if ":" not in endereco:
        raise ErroBalanca("Informe a balanca TCP/IP no formato endereco:porta.")
    host, porta_texto = endereco.rsplit(":", 1)
    try:
        numero_porta = int(porta_texto)
    except ValueError as exc:
        raise ErroBalanca("A porta TCP/IP da balanca deve ser numerica.") from exc
    if not host.strip() or not 1 <= numero_porta <= 65535:
        raise ErroBalanca("Endereco ou porta TCP/IP da balanca invalido.")
    return host.strip(), numero_porta


def _ler_tcp(config) -> bytes:
    host, porta = _endereco_tcp(config["porta"])
    comando = _sequencia_bytes(config["comando_leitura"])
    timeout = config["timeout_ms"] / 1000
    try:
        with socket.create_connection((host, porta), timeout=timeout) as conexao:
            conexao.settimeout(timeout)
            if comando:
                conexao.sendall(comando)
            return conexao.recv(256)
    except (OSError, TimeoutError) as exc:
        raise ErroBalanca(f"Nao foi possivel ler a balanca TCP/IP em {host}:{porta}: {exc}") from exc


def _ler_arquivo(config) -> bytes:
    caminho = Path(config["porta"]).expanduser()
    if not str(config["porta"]).strip():
        raise ErroBalanca("Informe o caminho do arquivo texto da balanca.")
    try:
        if caminho.stat().st_size > 64 * 1024:
            raise ErroBalanca("Arquivo da balanca excede o limite de 64 KB.")
        return caminho.read_bytes()
    except ErroBalanca:
        raise
    except OSError as exc:
        raise ErroBalanca(f"Nao foi possivel ler o arquivo da balanca: {exc}") from exc


def _ler_driver_fisico(config) -> bytes:
    protocolo = str(config["protocolo"]).upper()
    if protocolo == "SERIAL":
        return _ler_serial(config)
    if protocolo == "TCP_IP":
        return _ler_tcp(config)
    if protocolo == "ARQUIVO_TXT":
        return _ler_arquivo(config)
    raise ErroBalanca(f"Protocolo {protocolo} exige um adaptador especifico do fabricante.")


def ler_peso_balanca(configuracao: dict | None) -> dict:
    config = normalizar_configuracao_balanca(configuracao)
    if not config["habilitada"]:
        return {
            "status": "manual",
            "mensagem": "Balanca desabilitada para este terminal.",
            "fallback_manual": config["fallback_manual"],
            "unidade": config["unidade_padrao"],
        }
    if not config["leitura_automatica"]:
        return {
            "status": "manual",
            "mensagem": "Balanca sem protocolo automatico configurado.",
            "fallback_manual": config["fallback_manual"],
            "unidade": config["unidade_padrao"],
        }

    peso_simulado = _peso_simulado()
    if peso_simulado is not None:
        casas = config["precisao_decimal"]
        return {
            "status": "ok",
            "peso": f"{peso_simulado:.{casas}f}",
            "unidade": config["unidade_padrao"],
            "protocolo": config["protocolo"],
            "porta": config["porta"],
            "simulado": True,
        }

    try:
        resposta = _ler_driver_fisico(config)
        peso = extrair_peso_resposta(
            resposta,
            precisao=config["precisao_decimal"],
            fator_conversao=config["fator_conversao"],
        )
    except ErroBalanca as erro:
        return {
            "status": "erro",
            "mensagem": str(erro),
            "fallback_manual": config["fallback_manual"],
            "unidade": config["unidade_padrao"],
            "protocolo": config["protocolo"],
            "porta": config["porta"],
        }
    return {
        "status": "ok",
        "peso": peso,
        "unidade": config["unidade_padrao"],
        "protocolo": config["protocolo"],
        "porta": config["porta"],
        "simulado": False,
    }
