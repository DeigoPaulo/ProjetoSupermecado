from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from version import APP_VERSION
from devices.printers import ErroDescobertaImpressoras, listar_impressoras_windows
from devices.labels import montar_etiquetas_nativas
from devices.printing import ErroImpressao, imprimir_raw_windows, montar_cupom_escpos
from devices.scales import ler_peso_balanca, normalizar_configuracao_balanca

APP_DIR = Path(__file__).resolve().parent


def caminho_configuracao() -> Path:
    caminho_informado = os.environ.get("SUPERMERCADO_PDV_CONFIG", "").strip()
    if caminho_informado:
        return Path(caminho_informado).expanduser().resolve()
    config_desenvolvimento = APP_DIR / "config.json"
    if config_desenvolvimento.exists():
        return config_desenvolvimento
    pasta_local = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SupermercadoPDV"
    return pasta_local / "config.json"


def carregar_configuracao() -> dict:
    config_path = caminho_configuracao()
    if not config_path.exists():
        raise RuntimeError("Terminal ainda nao ativado.")
    with config_path.open(encoding="utf-8") as arquivo:
        config = json.load(arquivo)
    obrigatorios = ("servidor_base_url", "terminal_id", "terminal_chave")
    ausentes = [campo for campo in obrigatorios if not str(config.get(campo, "")).strip()]
    if ausentes:
        raise RuntimeError(f"Configuracao incompleta: {', '.join(ausentes)}.")
    config["servidor_base_url"] = config["servidor_base_url"].rstrip("/")
    return config


def salvar_configuracao(config: dict) -> None:
    config_path = caminho_configuracao()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporario = config_path.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(config, arquivo, ensure_ascii=True, indent=2)
    temporario.replace(config_path)


def caminho_log_dispositivos() -> Path:
    return caminho_configuracao().parent / "devices.log.jsonl"


def registrar_evento_dispositivo(tipo: str, payload: dict) -> None:
    caminho = caminho_log_dispositivos()
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        evento = {
            "em": datetime.now(timezone.utc).isoformat(),
            "tipo": tipo,
            "payload": payload,
        }
        with caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(evento, ensure_ascii=True, sort_keys=True) + "\n")
    except OSError:
        return


def listar_eventos_dispositivo(limite: int = 50) -> dict:
    caminho = caminho_log_dispositivos()
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {"status": "ok", "eventos": [], "total": 0}
    except OSError as erro:
        return {"status": "erro", "mensagem": str(erro), "eventos": [], "total": 0}

    eventos = []
    for linha in linhas[-max(1, min(int(limite or 50), 200)):]:
        try:
            eventos.append(json.loads(linha))
        except json.JSONDecodeError:
            eventos.append({"tipo": "log_corrompido", "payload": {"linha": linha[:200]}})
    return {"status": "ok", "eventos": eventos, "total": len(linhas)}


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
        raise RuntimeError(f"Terminal recusado pelo servidor: {mensagem}") from erro
    except URLError as erro:
        raise RuntimeError(f"Servidor PDV indisponivel: {erro.reason}") from erro


def verificar_versao(bootstrap: dict) -> dict:
    aplicativo = bootstrap.get("aplicativo", {})
    return {
        "instalada": APP_VERSION,
        "vigente": aplicativo.get("versao_vigente", APP_VERSION),
        "atualizacao_disponivel": bool(aplicativo.get("atualizacao_disponivel", False)),
        "atualizacao_obrigatoria": bool(aplicativo.get("atualizacao_obrigatoria", False)),
    }


def avisar_atualizacao(situacao: dict) -> None:
    if not situacao["atualizacao_disponivel"]:
        return
    from tkinter import messagebox

    mensagem = (
        f"Versao instalada: {situacao['instalada']}\n"
        f"Versao vigente: {situacao['vigente']}\n\n"
        "Solicite ao admin master a instalacao da versao publicada no ERP."
    )
    if situacao["atualizacao_obrigatoria"]:
        messagebox.showerror("Atualizacao obrigatoria", mensagem)
        raise RuntimeError("Atualizacao obrigatoria do PDV Desktop.")
    messagebox.showwarning("Atualizacao disponivel", mensagem)


def ativar_terminal(config_atual: dict | None = None) -> dict:
    import tkinter as tk
    from tkinter import messagebox, ttk

    resultado: dict = {}
    raiz = tk.Tk()
    raiz.title("Ativar PDV Supermercado")
    raiz.geometry("520x330")
    raiz.resizable(False, False)

    corpo = ttk.Frame(raiz, padding=24)
    corpo.pack(fill="both", expand=True)
    ttk.Label(corpo, text="Ativacao do terminal", font=("Segoe UI", 16, "bold")).pack(anchor="w")
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

    def __init__(self, bootstrap: dict):
        self.bootstrap = bootstrap

    def status(self) -> dict:
        return {
            "status": "ok",
            "ambiente": "desktop",
            "terminal": self.bootstrap.get("terminal", {}),
            "recursos": self.bootstrap.get("recursos", {}),
            "dispositivos": self.bootstrap.get("dispositivos", {}),
            "aplicativo": self.bootstrap.get("aplicativo", {}),
        }

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

    def imprimir_etiquetas(self, payload: dict) -> dict:
        impressora = str(payload.get("impressora_padrao", "")).strip() if isinstance(payload, dict) else ""
        try:
            dados = montar_etiquetas_nativas(payload)
            if len(dados) > 2 * 1024 * 1024:
                raise ErroImpressao("Lote de etiquetas excede o limite local de 2 MB.")
            total_bytes = imprimir_raw_windows(impressora, dados, "Etiquetas de gondola")
        except (ErroImpressao, AttributeError, TypeError) as erro:
            return {"status": "erro", "mensagem": str(erro), "impresso": False}
        return {
            "status": "ok",
            "impresso": True,
            "impressora": impressora,
            "linguagem": str(payload.get("linguagem", "")).upper(),
            "bytes": total_bytes,
        }

    def printLabels(self, payload: dict) -> dict:
        return self.imprimir_etiquetas(payload)

    def readScale(self) -> dict:
        return self.ler_peso_balanca()

    def scaleConfig(self) -> dict:
        return self.configuracao_balanca()


def executar(reconfigurar: bool = False) -> None:
    try:
        config_atual = carregar_configuracao()
    except (RuntimeError, json.JSONDecodeError):
        config_atual = None
    config = ativar_terminal(config_atual) if reconfigurar or config_atual is None else config_atual
    bootstrap = validar_terminal(config)
    avisar_atualizacao(verificar_versao(bootstrap))
    url_pdv = f"{config['servidor_base_url']}/pdv/"
    import webview

    janela = webview.create_window(
        "PDV Supermercado",
        url=url_pdv,
        js_api=PonteLocal(bootstrap),
        fullscreen=bool(config.get("tela_cheia", True)),
        resizable=bool(config.get("permitir_redimensionar", False)),
        min_size=(1024, 700),
    )
    janela.events.loaded += lambda: janela.evaluate_js(
        "window.SupermercadoDesktop = {"
        "printSale: function(payload) { return window.pywebview.api.imprimir_venda(payload); },"
        "printLabels: function(payload) { return window.pywebview.api.imprimir_etiquetas(payload); },"
        "listPrinters: function() { return window.pywebview.api.listar_impressoras(); },"
        "status: function() { return window.pywebview.api.status(); }"
        "};"
    )
    webview.start(private_mode=False)
    if janela is None:
        raise RuntimeError("Nao foi possivel iniciar a janela do PDV.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDV Desktop Supermercado")
    parser.add_argument("--configurar", action="store_true", help="Abre novamente a ativacao deste terminal.")
    argumentos = parser.parse_args()
    try:
        executar(reconfigurar=argumentos.configurar)
    except RuntimeError as erro:
        print(f"Erro ao iniciar PDV Desktop: {erro}", file=sys.stderr)
        raise SystemExit(1) from erro
