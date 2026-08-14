from __future__ import annotations

import argparse
import json
import os
import sys
from html import escape
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import webview

APP_NAME = "DeTec Admin"
APP_DIR = Path(__file__).resolve().parent


def config_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DeTecAdmin" / "config.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def valid_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Informe a URL completa do servidor, por exemplo http://192.168.1.10:8000")
    return url


def save_config(server_url: str) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"server_url": valid_url(server_url)}, indent=2), encoding="utf-8")


def verificar_servidor(server_url: str) -> str | None:
    """Retorna uma mensagem somente quando o endereco salvo nao responde."""
    try:
        request = Request(f"{valid_url(server_url)}/login/", method="GET")
        with urlopen(request, timeout=5):
            return None
    except (URLError, OSError, ValueError) as erro:
        return str(erro)


class ActivationApi:
    def activate(self, server_url: str):
        try:
            save_config(server_url)
            return {"ok": True, "url": valid_url(server_url) + "/login/"}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def close(self):
        window = webview.windows[0] if webview.windows else None
        if window:
            window.destroy()


def activation_html(server_url: str = "", motivo: str = "") -> str:
    url_inicial = escape(server_url, quote=True)
    erro_inicial = escape(motivo)
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Ativar DeTec Admin</title><style>body{{font-family:Segoe UI,Arial;margin:42px;color:#092b66;background:#f4f7fb}}main{{max-width:560px}}input,button{{font:inherit;padding:12px;width:100%;box-sizing:border-box}}input{{margin:18px 0;border:1px solid #b9c9df;border-radius:5px}}button{{background:#0757e6;color:#fff;border:0;border-radius:5px;font-weight:700;cursor:pointer}}small{{color:#5f7090}}#error{{color:#bd1a1a;margin-top:12px}}</style></head><body><main><h1>DeTec Admin</h1><p>Informe o endereco do servidor do supermercado.</p><input id="server" autofocus value="{url_inicial}" placeholder="http://192.168.1.10:8001"><button onclick="activate()">Salvar e entrar</button><p id="error">{erro_inicial}</p><small>O acesso e feito com o usuario administrativo cadastrado no ERP.</small></main><script>async function activate(){{const result=await window.pywebview.api.activate(document.getElementById('server').value);if(result.ok){{location.href=result.url}}else{{document.getElementById('error').textContent=result.error}}}}</script></body></html>'''


def run(reconfigure: bool = False) -> None:
    config = {} if reconfigure else load_config()
    url = str(config.get("server_url") or "").strip()
    motivo = verificar_servidor(url) if url else ""
    content = {"url": valid_url(url) + "/login/"} if url and not motivo else {"html": activation_html(url, motivo)}
    window = webview.create_window(APP_NAME, js_api=ActivationApi(), min_size=(1024, 700), **content)
    window.events.loaded += lambda: window.evaluate_js("document.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key==='F5'){e.preventDefault();if(confirm('Fechar o aplicativo administrativo?')) window.pywebview.api.close();}},true);")
    webview.start(private_mode=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeTec Admin")
    parser.add_argument("--configurar", action="store_true", help="Altera o endereco do servidor.")
    args = parser.parse_args()
    try:
        run(args.configurar)
    except Exception as exc:
        print(f"Erro ao iniciar {APP_NAME}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc