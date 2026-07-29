from __future__ import annotations

import argparse
import base64
import hashlib
import io
import hmac
import html
import json
import os
import shutil
import sys
import threading

import qrcode

from decimal import Decimal, InvalidOperation
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from version import APP_VERSION
from devices.printers import ErroDescobertaImpressoras, listar_impressoras_windows
from devices.labels import montar_etiquetas_nativas
from devices.printing import ErroImpressao, imprimir_raw_windows, montar_cupom_escpos, montar_pulso_gaveta_escpos
from devices.scales import ler_peso_balanca, normalizar_configuracao_balanca
from devices.secrets import ErroProtecaoSegredo, desproteger_segredo, proteger_segredo
from devices.runtime import instancia_unica_terminal
from devices.events import EventLog
from devices.tef import (
    AdaptadorTefIndisponivel,
    capacidades_adaptador_tef,
    criar_adaptador_tef,
    validar_resposta_documento_pinpad,
    validar_resposta_tef,
)

APP_DIR = Path(__file__).resolve().parent


def caminho_recurso(relativo: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return base / relativo

_SYNC_EVENTOS_LOCK = threading.Lock()


def _sincronizacao_eventos_exclusiva(func):
    def wrapper(*args, **kwargs):
        if not _SYNC_EVENTOS_LOCK.acquire(blocking=False):
            return {"status": "ocupado", "enviados": 0, "mensagem": "Sincronizacao de eventos ja em andamento."}
        try:
            return func(*args, **kwargs)
        finally:
            _SYNC_EVENTOS_LOCK.release()
    return wrapper



class TerminalRecusado(RuntimeError):
    pass


class ServidorPdvIndisponivel(RuntimeError):
    pass


def normalizar_valor_tef(valor) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise ValueError("Informe o valor do pagamento.")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        valor_decimal = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError("Informe um valor monetario valido.") from exc
    if not valor_decimal.is_finite() or valor_decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    valor_centavos = valor_decimal.quantize(Decimal("0.01"))
    if valor_centavos != valor_decimal:
        raise ValueError("O valor nao pode ter fracao menor que um centavo.")
    return format(valor_centavos, ".2f")


def gerar_qr_code_data_url(conteudo: str) -> str:
    conteudo = str(conteudo or "").strip()
    if not conteudo:
        raise ValueError("Conteudo PIX ausente para gerar o QR Code.")
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(conteudo)
    qr.make(fit=True)
    imagem = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def caminho_configuracao() -> Path:
    caminho_informado = (
        os.environ.get("DEIGO_PDV_CONFIG", "").strip()
        or os.environ.get("SUPERMERCADO_PDV_CONFIG", "").strip()
    )
    if caminho_informado:
        return Path(caminho_informado).expanduser().resolve()
    config_desenvolvimento = APP_DIR / "config.json"
    if config_desenvolvimento.exists():
        return config_desenvolvimento
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    novo = local_app_data / "DeigoPDV" / "config.json"
    legado = local_app_data / "SupermercadoPDV" / "config.json"
    if legado.exists() and not novo.exists():
        novo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legado, novo)
    return novo


def carregar_configuracao() -> dict:
    config_path = caminho_configuracao()
    if not config_path.exists():
        raise RuntimeError("Terminal ainda nao ativado.")
    with config_path.open(encoding="utf-8") as arquivo:
        config = json.load(arquivo)

    chave_protegida = str(config.get("terminal_chave_protegida") or "").strip()
    chave_legada = str(config.get("terminal_chave") or "").strip()
    migrar_chave_legada = bool(chave_legada)
    if chave_protegida:
        try:
            config["terminal_chave"] = desproteger_segredo(chave_protegida)
        except ErroProtecaoSegredo as exc:
            raise RuntimeError(f"Nao foi possivel abrir a chave protegida do terminal: {exc}") from exc

    tef = dict(config.get("tef") or {})
    tef_protegida = str(tef.get("configuracao_protegida") or "").strip()
    tef_legada = tef.get("configuracao")
    migrar_tef_legada = bool(tef_legada)
    if tef_protegida:
        try:
            configuracao_tef = json.loads(desproteger_segredo(tef_protegida))
        except (ErroProtecaoSegredo, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Nao foi possivel abrir a configuracao TEF protegida: {exc}") from exc
        if not isinstance(configuracao_tef, dict):
            raise RuntimeError("A configuracao TEF protegida possui formato invalido.")
        tef["configuracao"] = configuracao_tef
    if tef:
        config["tef"] = tef

    obrigatorios = ("servidor_base_url", "terminal_id", "terminal_chave")
    ausentes = [campo for campo in obrigatorios if not str(config.get(campo, "")).strip()]
    if ausentes:
        raise RuntimeError(f"Configuracao incompleta: {', '.join(ausentes)}.")
    config["servidor_base_url"] = config["servidor_base_url"].rstrip("/")
    config["_credencial_protegida"] = bool(chave_protegida or migrar_chave_legada)
    config["_tef_configuracao_protegida"] = bool(tef_protegida or migrar_tef_legada or not tef.get("configuracao"))
    if migrar_chave_legada or migrar_tef_legada:
        salvar_configuracao(config)
    return config


def salvar_configuracao(config: dict) -> None:
    config_path = caminho_configuracao()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    persistida = dict(config)
    persistida.pop("_credencial_protegida", None)
    persistida.pop("_tef_configuracao_protegida", None)

    chave = str(persistida.pop("terminal_chave", "") or "").strip()
    if chave:
        try:
            persistida["terminal_chave_protegida"] = proteger_segredo(chave)
        except ErroProtecaoSegredo as exc:
            raise RuntimeError(f"Nao foi possivel proteger a chave do terminal: {exc}") from exc
    if not str(persistida.get("terminal_chave_protegida") or "").strip():
        raise RuntimeError("Chave do terminal ausente na configuracao.")

    if "tef" in persistida:
        tef = dict(persistida.get("tef") or {})
        configuracao_tef = tef.pop("configuracao", None)
        if configuracao_tef:
            try:
                serializada = json.dumps(configuracao_tef, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                tef["configuracao_protegida"] = proteger_segredo(serializada)
            except (TypeError, ErroProtecaoSegredo) as exc:
                raise RuntimeError(f"Nao foi possivel proteger a configuracao TEF: {exc}") from exc
        else:
            tef.pop("configuracao_protegida", None)
        persistida["tef"] = tef

    temporario = config_path.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(persistida, arquivo, ensure_ascii=True, indent=2)
    temporario.replace(config_path)
    config["_credencial_protegida"] = True
    config["_tef_configuracao_protegida"] = True


def caminho_log_dispositivos() -> Path:
    return caminho_configuracao().parent / "devices.log.jsonl"


def caminho_bootstrap_cache() -> Path:
    return caminho_configuracao().parent / "bootstrap_cache.json"


def salvar_bootstrap_cache(bootstrap: dict) -> None:
    cache = dict(bootstrap or {})
    cache["cache_salvo_em"] = datetime.now(timezone.utc).isoformat()
    caminho = caminho_bootstrap_cache()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(cache, arquivo, ensure_ascii=True, indent=2)
    temporario.replace(caminho)


def carregar_bootstrap_cache() -> dict:
    with caminho_bootstrap_cache().open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def bootstrap_permite_modo_offline(bootstrap: dict) -> bool:
    terminal = bootstrap.get("terminal", {}) if isinstance(bootstrap, dict) else {}
    recursos = bootstrap.get("recursos", {}) if isinstance(bootstrap, dict) else {}
    sincronizacao = bootstrap.get("sincronizacao", {}) if isinstance(bootstrap, dict) else {}
    return bool(
        terminal.get("permite_modo_offline")
        or recursos.get("modo_offline_permitido")
        or sincronizacao.get("modo_offline_permitido")
    )


def bootstrap_cache_dentro_validade(bootstrap: dict, config: dict, agora: datetime | None = None) -> bool:
    salvo_em = str((bootstrap or {}).get("cache_salvo_em") or "").strip()
    if not salvo_em:
        return False
    try:
        instante = datetime.fromisoformat(salvo_em.replace("Z", "+00:00"))
        limite_horas = int((config or {}).get("offline_cache_max_hours") or 24)
    except (TypeError, ValueError):
        return False
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    limite_horas = max(1, min(limite_horas, 168))
    agora = agora or datetime.now(timezone.utc)
    idade_segundos = (agora - instante.astimezone(timezone.utc)).total_seconds()
    return -300 <= idade_segundos <= limite_horas * 3600


def montar_pagina_contingencia(bootstrap: dict) -> str:
    terminal = bootstrap.get("terminal", {}) if isinstance(bootstrap, dict) else {}
    nome_terminal = html.escape(str(terminal.get("nome") or "Terminal PDV"))
    cache_salvo_em = html.escape(str(bootstrap.get("cache_salvo_em") or "Nao informado"))
    mensagem = html.escape(str(bootstrap.get("mensagem_conexao") or "Servidor local indisponivel."))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDV aguardando servidor</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Arial, sans-serif; color: #fff; background: #06245c; }}
    main {{ width: min(760px, calc(100% - 48px)); text-align: center; }}
    .status {{ display: inline-flex; align-items: center; gap: 9px; padding: 8px 12px; border: 1px solid #ffd37a; border-radius: 6px; color: #ffe2a6; background: rgba(255, 174, 0, .12); font-size: 13px; font-weight: 700; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: #ffb020; box-shadow: 0 0 0 6px rgba(255, 176, 32, .14); }}
    h1 {{ margin: 26px 0 10px; font-size: 44px; line-height: 1.08; }}
    .terminal {{ margin: 0; color: #bcd2ff; font-size: 18px; font-weight: 700; }}
    .message {{ margin: 28px auto 0; max-width: 620px; color: #e7efff; font-size: 17px; line-height: 1.55; }}
    .safety {{ margin: 18px auto 0; max-width: 620px; padding-top: 18px; border-top: 1px solid rgba(255,255,255,.22); color: #bcd2ff; line-height: 1.5; }}
    .actions {{ display: flex; justify-content: center; gap: 12px; margin-top: 30px; }}
    button {{ min-width: 240px; min-height: 50px; border: 0; border-radius: 7px; color: #063179; background: #fff; font-size: 16px; font-weight: 800; cursor: pointer; }}
    button.secondary {{ border: 1px solid rgba(255,255,255,.55); color: #fff; background: rgba(255,255,255,.08); }}
    button:disabled {{ opacity: .62; cursor: wait; }}
    kbd {{ margin-left: 8px; padding: 3px 6px; border: 1px solid #b7c8e8; border-radius: 4px; background: #edf3ff; font: inherit; font-size: 12px; }}
    .detail {{ min-height: 22px; margin-top: 15px; color: #ffe2a6; font-size: 13px; font-weight: 700; }}
    footer {{ margin-top: 34px; color: #91addf; font-size: 12px; }}
    @media (max-width: 600px) {{ h1 {{ font-size: 34px; }} main {{ width: min(100% - 28px, 760px); }} .actions {{ flex-direction: column; }} button {{ width: 100%; }} }}
  </style>
</head>
<body>
  <main>
    <span class="status"><span class="dot"></span>AGUARDANDO SERVIDOR LOCAL</span>
    <h1>PDV temporariamente indisponivel</h1>
    <p class="terminal">{nome_terminal}</p>
    <p class="message">A conexao com o servidor da loja foi interrompida. Verifique a rede interna ou o computador servidor e tente novamente.</p>
    <p class="safety">Por seguranca, novas vendas, pagamentos e alteracoes de estoque permanecem bloqueados ate a licenca e os dados operacionais serem validados novamente.</p>
    <div class="actions">
      <button id="retry" type="button">Tentar novamente <kbd>F5</kbd></button>
      <button class="secondary" id="exit" type="button">Sair do aplicativo <kbd>Ctrl+Q</kbd></button>
    </div>
    <p class="detail" id="detail">{mensagem}</p>
    <footer>Ultima configuracao autorizada: {cache_salvo_em}</footer>
  </main>
  <script>
    const button = document.getElementById('retry');
    const exitButton = document.getElementById('exit');
    const detail = document.getElementById('detail');
    async function reconnect() {{
      if (!window.SupermercadoDesktop || !window.SupermercadoDesktop.reconnect) {{ detail.textContent = 'A ponte local ainda esta iniciando. Tente novamente.'; return; }}
      button.disabled = true;
      detail.textContent = 'Validando terminal e licenca no servidor...';
      try {{
        const result = await window.SupermercadoDesktop.reconnect();
        if (result.status === 'ok') {{ detail.textContent = 'Conexao restabelecida. Abrindo o caixa...'; window.location.replace(result.url); return; }}
        detail.textContent = result.mensagem || 'O servidor ainda nao respondeu.';
      }} catch (error) {{ detail.textContent = 'Nao foi possivel restabelecer a conexao.'; }}
      button.disabled = false;
      button.focus();
    }}
    async function exitApplication() {{
      if (!window.SupermercadoDesktop || !window.SupermercadoDesktop.closeApplication) {{ detail.textContent = 'A ponte local ainda esta iniciando. Tente novamente.'; return; }}
      if (!window.confirm('Fechar o aplicativo PDV?')) return;
      exitButton.disabled = true;
      detail.textContent = 'Encerrando o aplicativo...';
      try {{ await window.SupermercadoDesktop.closeApplication(); }}
      catch (error) {{ exitButton.disabled = false; detail.textContent = 'Nao foi possivel fechar o aplicativo.'; }}
    }}
    button.addEventListener('click', reconnect);
    exitButton.addEventListener('click', exitApplication);
    document.addEventListener('keydown', function (event) {{
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'q') {{ event.preventDefault(); exitApplication(); return; }}
      if (event.key === 'F5' || (event.key === 'Enter' && document.activeElement !== exitButton)) {{ event.preventDefault(); reconnect(); }}
    }});
    button.focus();
  </script>
</body>
</html>"""

def _event_log() -> EventLog:
    return EventLog(caminho_log_dispositivos())


def registrar_evento_dispositivo(tipo: str, payload: dict) -> None:
    try:
        _event_log().append(tipo, payload)
    except OSError:
        return


def listar_eventos_dispositivo(limite: int = 50) -> dict:
    try:
        return _event_log().listar(limite)
    except OSError as erro:
        return {"status": "erro", "mensagem": str(erro), "eventos": [], "total": 0}


def validar_terminal(config: dict) -> dict:
    requisicao = Request(
        f"{config['servidor_base_url']}/pdv/api/terminal/bootstrap/",
        headers={
            "Accept": "application/json",
            "X-Terminal-ID": config["terminal_id"],
            "X-Terminal-Key": config["terminal_chave"],
            "X-PDV-Version": APP_VERSION,
        },
    )
    try:
        with urlopen(requisicao, timeout=15) as resposta:
            return json.load(resposta)
    except HTTPError as erro:
        try:
            detalhe = json.load(erro)
            mensagem = detalhe.get("mensagem", str(erro))
        except (ValueError, AttributeError):
            mensagem = str(erro)
        raise TerminalRecusado(f"Terminal recusado pelo servidor: {mensagem}") from erro
    except URLError as erro:
        raise ServidorPdvIndisponivel(f"Servidor PDV indisponivel: {erro.reason}") from erro


def obter_bootstrap_operacional(config: dict) -> dict:
    try:
        bootstrap = validar_terminal(config)
    except ServidorPdvIndisponivel as erro:
        try:
            bootstrap = carregar_bootstrap_cache()
        except (FileNotFoundError, OSError, json.JSONDecodeError) as cache_erro:
            raise RuntimeError("Servidor PDV indisponivel e nao existe bootstrap offline autorizado.") from cache_erro
        if not bootstrap_permite_modo_offline(bootstrap):
            raise RuntimeError("Servidor PDV indisponivel e o terminal nao permite modo offline.") from erro
        if not bootstrap_cache_dentro_validade(bootstrap, config):
            registrar_evento_dispositivo("bootstrap", {"status": "cache_expirado", "cache_salvo_em": bootstrap.get("cache_salvo_em")})
            raise RuntimeError("Servidor PDV indisponivel e o bootstrap offline autorizado expirou.") from erro
        bootstrap = dict(bootstrap)
        bootstrap["status_conexao"] = "offline"
        bootstrap["mensagem_conexao"] = str(erro)
        registrar_evento_dispositivo(
            "bootstrap",
            {
                "status": "offline",
                "mensagem": str(erro),
                "cache_salvo_em": bootstrap.get("cache_salvo_em"),
            },
        )
        return bootstrap
    salvar_bootstrap_cache(bootstrap)
    return bootstrap


@_sincronizacao_eventos_exclusiva
def sincronizar_eventos_dispositivo(config: dict, limite: int = 100) -> dict:
    try:
        cursor = int(config.get("diagnostico_eventos_sincronizados") or 0)
    except (TypeError, ValueError):
        cursor = 0
    try:
        lote = _event_log().pendentes(cursor, limite)
    except OSError as erro:
        return {"status": "erro", "mensagem": str(erro), "enviados": 0, "pendentes": 0, "total": 0}

    eventos = lote["eventos"]
    if not eventos:
        if lote["cursor_reiniciado"]:
            config_atualizada = dict(config)
            config_atualizada["diagnostico_eventos_sincronizados"] = lote["cursor"]
            salvar_configuracao(config_atualizada)
            config["diagnostico_eventos_sincronizados"] = lote["cursor"]
        return {"status": "ok", "enviados": 0, "pendentes": 0, "total": lote["total"]}

    requisicao = Request(
        f"{config['servidor_base_url']}/pdv/api/terminal/device-events/",
        data=json.dumps({"eventos": eventos}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Terminal-ID": config["terminal_id"],
            "X-Terminal-Key": config["terminal_chave"],
            "X-PDV-Version": APP_VERSION,
        },
        method="POST",
    )
    try:
        with urlopen(requisicao, timeout=8) as resposta:
            retorno = json.load(resposta)
    except (HTTPError, URLError, TimeoutError, OSError) as erro:
        return {
            "status": "erro",
            "mensagem": str(erro),
            "enviados": 0,
            "pendentes": lote["pendentes"],
            "total": lote["total"],
        }

    processados = int(retorno.get("processados", retorno.get("recebidos", 0)) or 0)
    if retorno.get("status") != "ok" or processados != len(eventos):
        return {
            "status": "erro",
            "mensagem": "O servidor nao confirmou o lote completo de diagnosticos.",
            "enviados": 0,
            "pendentes": lote["pendentes"],
            "total": lote["total"],
        }

    novo_cursor = lote["proximo_cursor"]
    config_atualizada = dict(config)
    config_atualizada["diagnostico_eventos_sincronizados"] = novo_cursor
    try:
        salvar_configuracao(config_atualizada)
        compactacao = _event_log().compactar_confirmados(novo_cursor)
        if compactacao["compactado"]:
            novo_cursor = compactacao["cursor"]
            config_atualizada["diagnostico_eventos_sincronizados"] = novo_cursor
            salvar_configuracao(config_atualizada)
    except (OSError, RuntimeError) as erro:
        return {
            "status": "erro",
            "mensagem": str(erro),
            "enviados": len(eventos),
            "pendentes": max(lote["total"] - lote["proximo_cursor"], 0),
            "total": lote["total"],
        }

    config["diagnostico_eventos_sincronizados"] = novo_cursor
    total_atual = compactacao["total"]
    return {
        "status": "ok",
        "enviados": len(eventos),
        "pendentes": max(total_atual - novo_cursor, 0),
        "total": total_atual,
        "compactados": compactacao["removidos"],
    }


def intervalo_sincronizacao_eventos(config: dict) -> int:
    try:
        intervalo = int(config.get("diagnostico_sync_interval_seconds") or 60)
    except (TypeError, ValueError):
        intervalo = 60
    return max(15, min(intervalo, 3600))


def sincronizar_eventos_periodicamente(config: dict, parar: threading.Event) -> None:
    intervalo = intervalo_sincronizacao_eventos(config)
    while not parar.wait(intervalo):
        sincronizar_eventos_dispositivo(config)


def verificar_versao(bootstrap: dict) -> dict:
    aplicativo = bootstrap.get("aplicativo", {})
    pacote = aplicativo.get("pacote", {}) if isinstance(aplicativo, dict) else {}
    return {
        "instalada": APP_VERSION,
        "vigente": aplicativo.get("versao_vigente", APP_VERSION),
        "atualizacao_disponivel": bool(aplicativo.get("atualizacao_disponivel", False)),
        "atualizacao_obrigatoria": bool(aplicativo.get("atualizacao_obrigatoria", False)),
        "politica_atualizacao": aplicativo.get("politica_atualizacao", {}),
        "pacote_disponivel": bool(pacote.get("disponivel", False)),
        "pacote_nome": Path(str(pacote.get("nome") or "")).name,
        "pacote_sha256": str(pacote.get("sha256") or "").lower(),
        "pacote_url": str(pacote.get("url") or ""),
    }


def preparar_atualizacao(config: dict, situacao: dict) -> dict:
    if not situacao.get("pacote_disponivel"):
        raise RuntimeError("O pacote de atualizacao ainda nao foi publicado.")
    nome = situacao.get("pacote_nome") or "DeigoPDV.exe"
    sha_esperado = situacao.get("pacote_sha256", "")
    if len(sha_esperado) != 64:
        raise RuntimeError("O pacote publicado nao possui SHA-256 valido.")
    pasta = caminho_configuracao().parent / "updates"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome
    temporario = destino.with_suffix(destino.suffix + ".part")
    requisicao = Request(
        situacao["pacote_url"],
        headers={
            "Accept": "application/octet-stream",
            "X-Terminal-ID": config["terminal_id"],
            "X-Terminal-Key": config["terminal_chave"],
            "X-PDV-Version": APP_VERSION,
        },
        method="GET",
    )
    digest = hashlib.sha256()
    try:
        with urlopen(requisicao, timeout=60) as resposta, temporario.open("wb") as arquivo:
            while True:
                bloco = resposta.read(1024 * 1024)
                if not bloco:
                    break
                digest.update(bloco)
                arquivo.write(bloco)
    except (HTTPError, URLError, TimeoutError, OSError) as erro:
        temporario.unlink(missing_ok=True)
        raise RuntimeError(f"Nao foi possivel baixar a atualizacao: {erro}") from erro
    sha_recebido = digest.hexdigest()
    if not hmac.compare_digest(sha_recebido, sha_esperado):
        temporario.unlink(missing_ok=True)
        raise RuntimeError("A atualizacao baixada falhou na verificacao SHA-256.")
    temporario.replace(destino)
    registrar_evento_dispositivo(
        "atualizacao",
        {"status": "preparada", "versao": situacao["vigente"], "arquivo": nome, "sha256": sha_recebido},
    )
    return {"status": "ok", "arquivo": str(destino), "sha256": sha_recebido, "versao": situacao["vigente"]}


def avisar_atualizacao(situacao: dict, config: dict | None = None) -> None:
    if not situacao["atualizacao_disponivel"]:
        return
    from tkinter import messagebox

    mensagem = (
        f"Versao instalada: {situacao['instalada']}\n"
        f"Versao vigente: {situacao['vigente']}\n\n"
        "O pacote publicado exige autorizacao previa do admin master para este terminal."
    )
    baixar = bool(
        config
        and situacao.get("pacote_disponivel")
        and messagebox.askyesno(
            "Atualizacao do PDV",
            mensagem + "\n\nDeseja baixar e verificar o pacote agora? A instalacao continuara manual.",
        )
    )
    if baixar:
        resultado = preparar_atualizacao(config, situacao)
        messagebox.showinfo("Atualizacao preparada", f"Pacote verificado em:\n{resultado['arquivo']}")
        if situacao["atualizacao_obrigatoria"]:
            raise RuntimeError("Atualizacao obrigatoria preparada; instale o pacote antes de abrir o PDV.")
    elif situacao["atualizacao_obrigatoria"]:
        messagebox.showerror("Atualizacao obrigatoria", mensagem)
        raise RuntimeError("Atualizacao obrigatoria do PDV Desktop.")
    else:
        messagebox.showwarning("Atualizacao disponivel", mensagem)


def ativar_terminal(config_atual: dict | None = None) -> dict:
    import tkinter as tk
    from tkinter import messagebox, ttk

    resultado: dict = {}
    raiz = tk.Tk()
    raiz.title("Ativar Deigo PDV")
    raiz.geometry("520x330")
    raiz.resizable(False, False)
    icone = caminho_recurso("assets/deigo-pdv.ico")
    if icone.exists():
        raiz.iconbitmap(default=str(icone))

    corpo = ttk.Frame(raiz, padding=24)
    corpo.pack(fill="both", expand=True)
    ttk.Label(corpo, text="Ativacao do Deigo PDV", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    ttk.Label(corpo, text="Informe a credencial gerada pelo admin master no ERP.").pack(anchor="w", pady=(2, 18))

    campos = [
        ("Servidor", "servidor_base_url", False),
        ("Identificador do terminal", "terminal_id", False),
        ("Chave de ativacao", "terminal_chave", True),
    ]
    entradas: dict[str, ttk.Entry] = {}
    for rotulo, nome, secreto in campos:
        ttk.Label(corpo, text=rotulo).pack(anchor="w")
        entrada = ttk.Entry(corpo, show="*" if secreto else "")
        entrada.insert(0, str((config_atual or {}).get(nome, "")))
        entrada.pack(fill="x", pady=(2, 10))
        entradas[nome] = entrada

    status = ttk.Label(corpo, text="")
    status.pack(anchor="w")

    def confirmar() -> None:
        config = {nome: entrada.get().strip() for nome, entrada in entradas.items()}
        config.update({"tela_cheia": True, "permitir_redimensionar": False})
        if not all(config[nome] for _, nome, _ in campos):
            messagebox.showwarning("Dados incompletos", "Preencha servidor, identificador e chave.", parent=raiz)
            return
        config["servidor_base_url"] = config["servidor_base_url"].rstrip("/")
        status.configure(text="Validando licenca no servidor...")
        raiz.update_idletasks()
        try:
            validar_terminal(config)
        except RuntimeError as erro:
            status.configure(text="")
            messagebox.showerror("Ativacao recusada", str(erro), parent=raiz)
            return
        salvar_configuracao(config)
        resultado.update(config)
        raiz.destroy()

    ttk.Button(corpo, text="Validar e ativar", command=confirmar).pack(anchor="e", pady=(8, 0))
    raiz.protocol("WM_DELETE_WINDOW", raiz.destroy)
    raiz.mainloop()
    if not resultado:
        raise RuntimeError("Ativacao cancelada.")
    return resultado


class PonteLocal:
    """Contrato inicial exposto ao JavaScript da mesma tela web do PDV."""

    def __init__(self, bootstrap: dict, config: dict | None = None):
        self.bootstrap = bootstrap
        self.config = dict(config or {})
        self._tef_operacoes = {}
        self._tef_pagamentos_pendentes = {}
        self._adaptador_tef = None
        self._janela = None

    def vincular_janela(self, janela) -> None:
        self._janela = janela

    def closeApplication(self) -> dict:
        if self._janela is None:
            return {"status": "erro", "mensagem": "Janela do aplicativo indisponivel."}

        threading.Timer(0.15, self._janela.destroy).start()
        return {"status": "ok", "mensagem": "Encerrando o PDV."}

    def _reutilizar_operacao_tef(self, operacao: str, chave: str, assinatura: tuple) -> dict | None:
        if not chave:
            return None
        registro = self._tef_operacoes.get((operacao, chave))
        if not registro:
            return None
        if registro["assinatura"] != assinatura:
            return {
                "status": "erro",
                "aprovado": False,
                "estornado": False,
                "mensagem": "Chave de idempotencia reutilizada com dados diferentes.",
            }
        resultado = dict(registro["resultado"])
        resultado["reutilizado"] = True
        return resultado

    def _guardar_operacao_tef(self, operacao: str, chave: str, assinatura: tuple, resultado: dict) -> None:
        if not chave:
            return
        if len(self._tef_operacoes) >= 200:
            self._tef_operacoes.pop(next(iter(self._tef_operacoes)))
        self._tef_operacoes[(operacao, chave)] = {
            "assinatura": assinatura,
            "resultado": dict(resultado),
        }

    def status(self) -> dict:
        return {
            "status": "ok",
            "ambiente": "desktop",
            "status_conexao": self.bootstrap.get("status_conexao", "online"),
            "terminal": self.bootstrap.get("terminal", {}),
            "recursos": self.bootstrap.get("recursos", {}),
            "dispositivos": self.bootstrap.get("dispositivos", {}),
            "aplicativo": self.bootstrap.get("aplicativo", {}),
            "sincronizacao_eventos": {
                "contrato": "pdv_device_event_queue_v1",
                "periodica": True,
                "intervalo_segundos": intervalo_sincronizacao_eventos(self.config),
            },
            "seguranca_local": {
                "contrato": "pdv_local_secret_v1",
                "credencial_protegida": bool(self.config.get("_credencial_protegida")),
                "configuracao_tef_protegida": bool(self.config.get("_tef_configuracao_protegida")),
                "mecanismo": "WINDOWS_DPAPI",
                "contrato_instancia": "pdv_single_instance_v1",
                "instancia_unica_por_terminal": True,
            },
        }

    def reconnect(self) -> dict:
        if not self.config:
            return {"status": "erro", "mensagem": "Configuracao do terminal indisponivel para reconexao."}
        try:
            bootstrap = validar_terminal(self.config)
        except TerminalRecusado as erro:
            registrar_evento_dispositivo("bootstrap", {"status": "recusado", "mensagem": str(erro)})
            return {"status": "bloqueado", "mensagem": str(erro)}
        except (ServidorPdvIndisponivel, TimeoutError, OSError) as erro:
            return {"status": "offline", "mensagem": str(erro)}
        salvar_bootstrap_cache(bootstrap)
        self.bootstrap = bootstrap
        sincronizar_eventos_dispositivo(self.config)
        registrar_evento_dispositivo("bootstrap", {"status": "reconectado"})
        return {"status": "ok", "url": f"{self.config['servidor_base_url']}/pdv/"}

    def listar_impressoras(self) -> dict:
        try:
            impressoras = listar_impressoras_windows()
        except ErroDescobertaImpressoras as erro:
            return {"status": "erro", "mensagem": str(erro), "impressoras": []}
        return {
            "status": "ok",
            "impressoras": impressoras,
            "total": len(impressoras),
            "padrao": next((item["nome"] for item in impressoras if item["padrao"]), None),
        }

    def listar_eventos_dispositivos(self, limite: int = 50) -> dict:
        return listar_eventos_dispositivo(limite)

    def deviceLogs(self, limite: int = 50) -> dict:
        return self.listar_eventos_dispositivos(limite)

    def homologar_dispositivos(self, opcoes: dict | None = None) -> dict:
        opcoes = opcoes if isinstance(opcoes, dict) else {}
        verificacoes = []

        def adicionar(codigo, nome, status, mensagem, detalhes=None):
            verificacoes.append(
                {
                    "codigo": codigo,
                    "nome": nome,
                    "status": status,
                    "mensagem": mensagem,
                    "detalhes": detalhes or {},
                }
            )

        try:
            impressoras = listar_impressoras_windows()
        except ErroDescobertaImpressoras as erro:
            impressoras = []
            adicionar("impressora", "Impressoras", "erro", str(erro))
        else:
            gaveta_config = self.configuracao_gaveta()
            impressora_configurada = gaveta_config["impressora_padrao"]
            encontrada = next(
                (item for item in impressoras if item["nome"].casefold() == impressora_configurada.casefold()),
                None,
            )
            if impressora_configurada and not encontrada:
                adicionar(
                    "impressora",
                    "Impressoras",
                    "erro",
                    f"A impressora configurada '{impressora_configurada}' nao esta instalada.",
                    {"total_instaladas": len(impressoras), "configurada": impressora_configurada},
                )
            elif encontrada and encontrada.get("offline"):
                adicionar(
                    "impressora",
                    "Impressoras",
                    "erro",
                    f"A impressora configurada '{impressora_configurada}' esta offline.",
                    {"total_instaladas": len(impressoras), "configurada": impressora_configurada},
                )
            elif impressoras and impressora_configurada:
                adicionar(
                    "impressora",
                    "Impressoras",
                    "ok",
                    f"{len(impressoras)} impressora(s) encontrada(s) no Windows.",
                    {
                        "total_instaladas": len(impressoras),
                        "configurada": impressora_configurada,
                        "padrao": next((item["nome"] for item in impressoras if item.get("padrao")), ""),
                    },
                )
            elif impressoras:
                adicionar(
                    "impressora",
                    "Impressoras",
                    "atencao",
                    f"{len(impressoras)} impressora(s) encontrada(s), sem uma impressora de gaveta para comparar.",
                    {
                        "total_instaladas": len(impressoras),
                        "padrao": next((item["nome"] for item in impressoras if item.get("padrao")), ""),
                    },
                )
            else:
                adicionar("impressora", "Impressoras", "atencao", "Nenhuma impressora instalada foi encontrada.")

        balanca = self.configuracao_balanca()
        if not balanca["habilitada"]:
            adicionar("balanca", "Balanca", "nao_aplicavel", "Balanca desabilitada para este terminal.")
        elif opcoes.get("ler_balanca"):
            leitura = self.ler_peso_balanca()
            adicionar(
                "balanca",
                "Balanca",
                "ok" if leitura.get("status") == "ok" else "erro",
                leitura.get("mensagem") or (
                    f"Peso lido: {leitura.get('peso')} {leitura.get('unidade')}"
                    if leitura.get("status") == "ok"
                    else "A balanca nao confirmou a leitura."
                ),
                leitura,
            )
        elif balanca["leitura_automatica"] and balanca["porta"]:
            adicionar(
                "balanca",
                "Balanca",
                "atencao",
                "Configuracao pronta; execute a leitura com peso conhecido para homologar fisicamente.",
                {"protocolo": balanca["protocolo"], "porta": balanca["porta"], "modelo": balanca["modelo"]},
            )
        else:
            adicionar("balanca", "Balanca", "erro", "Balanca habilitada sem protocolo automatico e porta configurados.")

        gaveta = self.configuracao_gaveta()
        if not gaveta["habilitada"]:
            adicionar("gaveta", "Gaveta", "nao_aplicavel", "Gaveta desabilitada para este terminal.")
        elif not gaveta["impressora_padrao"]:
            adicionar("gaveta", "Gaveta", "erro", "Gaveta habilitada sem impressora configurada para o pulso.")
        elif opcoes.get("acionar_gaveta"):
            resultado_gaveta = self.abrir_gaveta({"motivo": "homologacao_dispositivos"})
            adicionar(
                "gaveta",
                "Gaveta",
                "ok" if resultado_gaveta.get("status") == "ok" else "erro",
                resultado_gaveta.get("mensagem") or "Pulso enviado; confirme a abertura fisica da gaveta.",
                resultado_gaveta,
            )
        else:
            adicionar(
                "gaveta",
                "Gaveta",
                "atencao",
                "Configuracao pronta; autorize o pulso para confirmar a abertura fisica.",
                {"impressora": gaveta["impressora_padrao"]},
            )

        tef = self.configuracao_tef()
        provedor = str(tef.get("provedor") or "NAO_CONFIGURADO").upper()
        if provedor == "NAO_CONFIGURADO":
            adicionar("tef", "TEF", "atencao", "Nenhum provedor TEF foi configurado para este terminal.")
        else:
            adicionar(
                "tef",
                "TEF",
                "atencao",
                "Contrato configurado; a transacao de teste deve ser feita no ambiente de homologacao da adquirente.",
                {"provedor": provedor, "modo": tef.get("modo_integracao") or "SIMULADO"},
            )

        status = "ok"
        if any(item["status"] == "erro" for item in verificacoes):
            status = "erro"
        elif any(item["status"] == "atencao" for item in verificacoes):
            status = "atencao"
        resultado = {
            "status": status,
            "contrato": "pdv_device_homologation_v1",
            "mensagem": (
                "Pre-homologacao concluida sem pendencias."
                if status == "ok"
                else "Pre-homologacao concluida com pendencias para revisar."
            ),
            "verificacoes": verificacoes,
            "homologacao_fisica_concluida": False,
        }
        registrar_evento_dispositivo(
            "homologacao_dispositivos",
            {
                "status": status,
                "mensagem": resultado["mensagem"],
                "contrato": resultado["contrato"],
                "verificacoes": verificacoes,
                "homologacao_fisica_concluida": False,
            },
        )
        return resultado

    def runDeviceDiagnostics(self, opcoes: dict | None = None) -> dict:
        return self.homologar_dispositivos(opcoes)

    def configuracao_balanca(self) -> dict:
        dispositivos = self.bootstrap.get("dispositivos", {})
        return normalizar_configuracao_balanca(dispositivos.get("balanca"))

    def ler_peso_balanca(self) -> dict:
        resultado = ler_peso_balanca(self.configuracao_balanca())
        if resultado.get("status") != "ok":
            registrar_evento_dispositivo(
                "balanca",
                {
                    "status": resultado.get("status"),
                    "mensagem": resultado.get("mensagem", ""),
                    "protocolo": resultado.get("protocolo", self.configuracao_balanca().get("protocolo")),
                    "porta": resultado.get("porta", self.configuracao_balanca().get("porta")),
                    "fallback_manual": resultado.get("fallback_manual"),
                },
            )
        return resultado

    def imprimir_venda(self, payload: dict) -> dict:
        impressao = payload.get("impressao", {}) if isinstance(payload, dict) else {}
        impressora = str(impressao.get("impressora_padrao", "")).strip()
        try:
            vias = int(impressao.get("numero_vias", 1))
        except (TypeError, ValueError):
            vias = 1
        vias = min(3, max(1, vias))
        try:
            dados = montar_cupom_escpos(payload)
            if len(dados) > 256 * 1024:
                raise ErroImpressao("Cupom excede o limite local de 256 KB.")
            total_bytes = sum(imprimir_raw_windows(impressora, dados, f"Venda {payload.get('venda', {}).get('id', '')}") for _ in range(vias))
        except (ErroImpressao, AttributeError, TypeError) as erro:
            return {"status": "erro", "mensagem": str(erro), "impresso": False}
        return {"status": "ok", "impresso": True, "impressora": impressora, "vias": vias, "bytes": total_bytes}

    def printSale(self, payload: dict) -> dict:
        return self.imprimir_venda(payload)

    def configuracao_gaveta(self) -> dict:
        dispositivos = self.bootstrap.get("dispositivos", {})
        gaveta = dispositivos.get("gaveta") if isinstance(dispositivos, dict) else {}
        gaveta = gaveta if isinstance(gaveta, dict) else {}
        return {
            "contrato": gaveta.get("contrato") or "pdv_cash_drawer_v1",
            "opcional": bool(gaveta.get("opcional", True)),
            "habilitada": bool(gaveta.get("habilitada", False)),
            "impressora_padrao": str(gaveta.get("impressora_padrao") or "").strip(),
            "abrir_em_dinheiro": bool(gaveta.get("abrir_em_dinheiro", False)),
            "abrir_em_movimento_caixa": bool(gaveta.get("abrir_em_movimento_caixa", False)),
            "bloqueia_venda_se_indisponivel": bool(gaveta.get("bloqueia_venda_se_indisponivel", False)),
        }

    def abrir_gaveta(self, payload: dict | None = None) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        config = self.configuracao_gaveta()
        motivo = str(payload.get("motivo") or "manual").strip()[:80]
        impressora = str(payload.get("impressora") or config["impressora_padrao"]).strip()
        if not config["habilitada"]:
            resultado = {
                "status": "manual",
                "acionada": False,
                "motivo": motivo,
                "mensagem": "Gaveta desabilitada para este terminal.",
            }
            registrar_evento_dispositivo("gaveta", resultado)
            return resultado
        if not impressora:
            resultado = {
                "status": "manual",
                "acionada": False,
                "motivo": motivo,
                "mensagem": "Nenhuma impressora configurada para acionar a gaveta.",
            }
            registrar_evento_dispositivo("gaveta", resultado)
            return resultado
        try:
            bytes_enviados = imprimir_raw_windows(impressora, montar_pulso_gaveta_escpos(), f"Gaveta PDV - {motivo}")
        except ErroImpressao as erro:
            resultado = {
                "status": "erro",
                "acionada": False,
                "motivo": motivo,
                "impressora": impressora,
                "mensagem": str(erro),
            }
            registrar_evento_dispositivo("gaveta", resultado)
            return resultado
        resultado = {
            "status": "ok",
            "acionada": True,
            "motivo": motivo,
            "impressora": impressora,
            "bytes": bytes_enviados,
        }
        registrar_evento_dispositivo("gaveta", resultado)
        return resultado

    def openCashDrawer(self, payload: dict | None = None) -> dict:
        return self.abrir_gaveta(payload)

    def imprimir_etiquetas(self, payload: dict) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        impressora = str(payload.get("impressora_padrao", "")).strip()
        linguagem = str(payload.get("linguagem", "")).upper()
        itens = payload.get("itens") if isinstance(payload.get("itens"), list) else []
        total_copias = 0
        for item in itens:
            if not isinstance(item, dict):
                continue
            try:
                total_copias += int(item.get("copias") or 1)
            except (TypeError, ValueError):
                continue
        evidencia = {
            "impressora": impressora,
            "linguagem": linguagem,
            "itens": len(itens),
            "copias": total_copias,
            "contrato": str(payload.get("contrato") or ""),
        }
        try:
            if not impressora:
                raise ErroImpressao("Nenhuma impressora foi configurada para o lote de etiquetas.")
            dados = montar_etiquetas_nativas(payload)
            if len(dados) > 2 * 1024 * 1024:
                raise ErroImpressao("Lote de etiquetas excede o limite local de 2 MB.")
            total_bytes = imprimir_raw_windows(impressora, dados, "Etiquetas de gondola")
        except (ErroImpressao, AttributeError, TypeError) as erro:
            resultado = {"status": "erro", "mensagem": str(erro), "impresso": False}
            registrar_evento_dispositivo("etiquetas", {**evidencia, **resultado})
            return resultado
        resultado = {
            "status": "ok",
            "impresso": True,
            "impressora": impressora,
            "linguagem": linguagem,
            "bytes": total_bytes,
            "itens": len(itens),
            "copias": total_copias,
        }
        registrar_evento_dispositivo("etiquetas", {**evidencia, "status": "ok", "impresso": True, "bytes": total_bytes})
        return resultado

    def printLabels(self, payload: dict) -> dict:
        return self.imprimir_etiquetas(payload)

    def readScale(self) -> dict:
        return self.ler_peso_balanca()

    def scaleConfig(self) -> dict:
        return self.configuracao_balanca()

    def configuracao_tef(self) -> dict:
        return self.bootstrap.get("tef", {})

    def _obter_adaptador_tef(self):
        if self._adaptador_tef is None:
            self._adaptador_tef = criar_adaptador_tef(self.config, self.configuracao_tef())
        return self._adaptador_tef

    def _registrar_retorno_tef(self, evento: str, resultado: dict, payload: dict) -> None:
        campos = (
            "status",
            "mensagem",
            "mensagem_processadora",
            "provedor",
            "modo",
            "tipo",
            "valor",
            "transacao_externa_id",
            "estorno_transacao_id",
            "nsu",
            "codigo_autorizacao",
            "pix_simulado",
        )
        evidencia = {campo: resultado[campo] for campo in campos if resultado.get(campo) not in (None, "")}
        evidencia.setdefault("status", "erro")
        evidencia.setdefault("tipo", str((payload or {}).get("tipo") or "").strip().upper())
        evidencia.setdefault("valor", str((payload or {}).get("valor") or "").strip())
        registrar_evento_dispositivo(evento, evidencia)

    def tefCapabilities(self) -> dict:
        provedor = str(self.configuracao_tef().get("provedor") or "NAO_CONFIGURADO").upper()
        try:
            capacidades = capacidades_adaptador_tef(self._obter_adaptador_tef())
            return {"status": "ok", "provedor": provedor, **capacidades}
        except Exception as exc:
            return {
                "status": "erro",
                "provedor": provedor,
                "contrato": "pdv_tef_capabilities_v1",
                "captura_documento_consumidor": False,
                "mensagem": str(exc),
            }

    def captureConsumerDocument(self, payload: dict | None = None) -> dict:
        payload = dict(payload or {})
        tipo = str(payload.get("tipo") or "AUTO").strip().upper()
        if tipo not in {"AUTO", "CPF", "CNPJ"}:
            return {"status": "erro", "mensagem": "Tipo de documento invalido."}
        try:
            adaptador = self._obter_adaptador_tef()
            if not capacidades_adaptador_tef(adaptador)["captura_documento_consumidor"]:
                raise AdaptadorTefIndisponivel(
                    "O pinpad configurado nao oferece captura de CPF/CNPJ. Digite o documento manualmente."
                )
            resultado = validar_resposta_documento_pinpad(
                adaptador.capturar_documento({"tipo": tipo})
            )
        except Exception as exc:
            resultado = {"status": "erro", "mensagem": str(exc)}
        # Documento pessoal nunca e persistido no diagnostico local do equipamento.
        registrar_evento_dispositivo(
            "tef_documento_consumidor",
            {
                "status": resultado.get("status", "erro"),
                "tipo": resultado.get("tipo", tipo),
                "origem": resultado.get("origem", "pinpad"),
                "simulado": bool(resultado.get("simulado")),
            },
        )
        return resultado
    def processPayment(self, payload: dict) -> dict:
        payload = dict(payload or {})
        tef = self.configuracao_tef()
        provedor = str(tef.get("provedor") or "NAO_CONFIGURADO").upper()
        tipo = str(payload.get("tipo") or "").strip().upper()
        tipos_permitidos = {
            str(item).strip().upper()
            for item in (tef.get("tipos_pagamento") or ["CREDITO", "DEBITO", "PIX", "VALE_ALIMENTACAO", "VALE_REFEICAO"])
            if str(item).strip()
        }
        try:
            valor = normalizar_valor_tef(payload.get("valor"))
            if not tipo:
                raise ValueError("Informe o tipo do pagamento.")
            if tipo not in tipos_permitidos:
                raise ValueError("Tipo de pagamento nao habilitado para este terminal.")
            adaptador = self._obter_adaptador_tef()
        except (ValueError, AdaptadorTefIndisponivel) as exc:
            resultado = {
                "status": "erro",
                "mensagem": str(exc),
                "aprovado": False,
                "provedor": provedor,
                "tipo": tipo,
            }
            self._registrar_retorno_tef("tef", resultado, payload)
            return resultado

        chave = str(payload.get("idempotency_key") or "").strip()[:120]
        assinatura = (provedor, tipo, valor)
        reutilizado = self._reutilizar_operacao_tef("pagamento", chave, assinatura)
        if reutilizado:
            return reutilizado

        requisicao = {**payload, "tipo": tipo, "valor": valor}
        try:
            resultado = validar_resposta_tef(adaptador.processar(requisicao), "pagamento")
        except Exception as exc:
            resultado = {
                "status": "erro",
                "mensagem": f"Falha no driver TEF: {exc}",
                "aprovado": False,
                "provedor": provedor,
                "tipo": tipo,
                "valor": valor,
            }
        resultado.setdefault("provedor", provedor)
        resultado.setdefault("tipo", tipo)
        resultado.setdefault("valor", valor)
        if resultado.get("pix_qr_code") and not resultado.get("pix_qr_code_image"):
            resultado["pix_qr_code_image"] = gerar_qr_code_data_url(resultado["pix_qr_code"])

        self._guardar_operacao_tef("pagamento", chave, assinatura, resultado)
        if resultado.get("status") == "pending":
            self._tef_pagamentos_pendentes[resultado["transacao_externa_id"]] = {
                "chave_idempotencia": chave,
                "assinatura": assinatura,
                "ultimo_status": "pending",
            }
        self._registrar_retorno_tef("tef", resultado, requisicao)
        return resultado

    def checkPayment(self, payload: dict) -> dict:
        payload = dict(payload or {})
        transacao = str(payload.get("transacao_externa_id") or "").strip()
        if not transacao:
            return {"status": "erro", "aprovado": False, "mensagem": "Transacao PIX ausente para consulta."}
        try:
            adaptador = self._obter_adaptador_tef()
            resultado = validar_resposta_tef(adaptador.consultar(payload), "consulta")
        except Exception as exc:
            resultado = {
                "status": "erro",
                "aprovado": False,
                "mensagem": f"Falha na consulta TEF: {exc}",
                "transacao_externa_id": transacao,
            }
            self._registrar_retorno_tef("tef", resultado, payload)
            return resultado

        registro = self._tef_pagamentos_pendentes.get(transacao)
        status_anterior = registro.get("ultimo_status") if registro else None
        status_atual = resultado.get("status")
        if status_atual == "ok" and registro:
            self._guardar_operacao_tef(
                "pagamento",
                registro["chave_idempotencia"],
                registro["assinatura"],
                resultado,
            )
        if registro:
            registro["ultimo_status"] = status_atual
        if status_atual != status_anterior:
            self._registrar_retorno_tef("tef", resultado, payload)
        return resultado

    def refundPayment(self, payload: dict) -> dict:
        payload = dict(payload or {})
        tef = self.configuracao_tef()
        provedor = str(tef.get("provedor") or "NAO_CONFIGURADO").upper()
        tipo = str(payload.get("tipo") or "").strip().upper()
        transacao = str(payload.get("transacao_externa_id") or "").strip()
        try:
            valor = normalizar_valor_tef(payload.get("valor"))
            if not transacao:
                raise ValueError("Informe a transacao original do estorno.")
            adaptador = self._obter_adaptador_tef()
        except (ValueError, AdaptadorTefIndisponivel) as exc:
            resultado = {
                "status": "erro",
                "mensagem": str(exc),
                "estornado": False,
                "provedor": provedor,
                "tipo": tipo,
            }
            self._registrar_retorno_tef("tef_estorno", resultado, payload)
            return resultado

        chave = str(payload.get("idempotency_key") or "").strip()[:120]
        assinatura = (provedor, tipo, valor, transacao)
        reutilizado = self._reutilizar_operacao_tef("estorno", chave, assinatura)
        if reutilizado:
            return reutilizado

        requisicao = {**payload, "tipo": tipo, "valor": valor, "transacao_externa_id": transacao}
        try:
            resultado = validar_resposta_tef(adaptador.estornar(requisicao), "estorno")
        except Exception as exc:
            resultado = {
                "status": "erro",
                "mensagem": f"Falha no driver TEF: {exc}",
                "estornado": False,
                "provedor": provedor,
                "tipo": tipo,
                "valor": valor,
                "transacao_externa_id": transacao,
            }
        resultado.setdefault("provedor", provedor)
        resultado.setdefault("tipo", tipo)
        resultado.setdefault("valor", valor)
        resultado.setdefault("transacao_externa_id", transacao)
        self._guardar_operacao_tef("estorno", chave, assinatura, resultado)
        self._registrar_retorno_tef("tef_estorno", resultado, requisicao)
        return resultado

def executar(reconfigurar: bool = False) -> None:
    try:
        config_atual = carregar_configuracao()
    except (RuntimeError, json.JSONDecodeError):
        config_atual = None

    if reconfigurar and config_atual:
        terminal_atual = config_atual["terminal_id"]
        with instancia_unica_terminal(terminal_atual):
            config = ativar_terminal(config_atual)
            if config["terminal_id"] == terminal_atual:
                _executar_interface_pdv(config)
            else:
                with instancia_unica_terminal(config["terminal_id"]):
                    _executar_interface_pdv(config)
        return

    config = ativar_terminal(config_atual) if config_atual is None else config_atual
    with instancia_unica_terminal(config["terminal_id"]):
        _executar_interface_pdv(config)


def _executar_interface_pdv(config: dict) -> None:
    bootstrap = obter_bootstrap_operacional(config)
    sincronizar_eventos_dispositivo(config)
    avisar_atualizacao(verificar_versao(bootstrap), config)
    parar_sincronizacao = threading.Event()
    thread_sincronizacao = threading.Thread(
        target=sincronizar_eventos_periodicamente,
        args=(config, parar_sincronizacao),
        name="pdv-device-events-sync",
        daemon=True,
    )
    url_pdv = f"{config['servidor_base_url']}/pdv/"
    import webview

    ponte = PonteLocal(bootstrap, config)
    conteudo = {"html": montar_pagina_contingencia(bootstrap)} if bootstrap.get("status_conexao") == "offline" else {"url": url_pdv}
    janela = webview.create_window(
        "Deigo PDV",
        js_api=ponte,
        fullscreen=bool(config.get("tela_cheia", True)),
        resizable=bool(config.get("permitir_redimensionar", False)),
        min_size=(1024, 700),
        **conteudo,
    )
    ponte.vincular_janela(janela)
    janela.events.loaded += lambda: janela.evaluate_js(
        "window.SupermercadoDesktop = {"
        "printSale: function(payload) { return window.pywebview.api.imprimir_venda(payload); },"
        "printLabels: function(payload) { return window.pywebview.api.imprimir_etiquetas(payload); },"
        "processPayment: function(payload) { return window.pywebview.api.processPayment(payload); },"
        "checkPayment: function(payload) { return window.pywebview.api.checkPayment(payload); },"
        "refundPayment: function(payload) { return window.pywebview.api.refundPayment(payload); },"
        "tefCapabilities: function() { return window.pywebview.api.tefCapabilities(); },"
        "captureConsumerDocument: function(payload) { return window.pywebview.api.captureConsumerDocument(payload); },"
        "readScale: function() { return window.pywebview.api.readScale(); },"
        "scaleConfig: function() { return window.pywebview.api.scaleConfig(); },"
        "deviceLogs: function(limite) { return window.pywebview.api.deviceLogs(limite); },"
        "runDeviceDiagnostics: function(opcoes) { return window.pywebview.api.homologar_dispositivos(opcoes); },"
        "openCashDrawer: function(payload) { return window.pywebview.api.openCashDrawer(payload); },"
        "listPrinters: function() { return window.pywebview.api.listar_impressoras(); },"
        "status: function() { return window.pywebview.api.status(); },"
        "reconnect: function() { return window.pywebview.api.reconnect(); },"
        "closeApplication: function() { return window.pywebview.api.closeApplication(); }"
        "};"
        "document.documentElement.classList.add('desktop-pdv');"
        "document.dispatchEvent(new CustomEvent('supermercado:desktop-ready'));"
    )
    thread_sincronizacao.start()
    try:
        webview.start(private_mode=False)
    finally:
        parar_sincronizacao.set()
        thread_sincronizacao.join(timeout=2)
    if janela is None:
        raise RuntimeError("Nao foi possivel iniciar a janela do PDV.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deigo PDV Desktop")
    parser.add_argument("--configurar", action="store_true", help="Abre novamente a ativacao deste terminal.")
    argumentos = parser.parse_args()
    try:
        executar(reconfigurar=argumentos.configurar)
    except RuntimeError as erro:
        print(f"Erro ao iniciar PDV Desktop: {erro}", file=sys.stderr)
        raise SystemExit(1) from erro
