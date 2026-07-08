from __future__ import annotations

import json
import platform
import subprocess


class ErroDescobertaImpressoras(RuntimeError):
    pass


def listar_impressoras_windows() -> list[dict]:
    if platform.system() != "Windows":
        return []
    comando = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-CimInstance Win32_Printer | "
            "Select-Object Name,PortName,DriverName,Default,WorkOffline,PrinterStatus | "
            "ConvertTo-Json -Compress"
        ),
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        processo = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        raise ErroDescobertaImpressoras(f"Nao foi possivel consultar as impressoras: {erro}") from erro
    if processo.returncode != 0:
        detalhe = processo.stderr.strip() or "consulta do Windows falhou"
        raise ErroDescobertaImpressoras(detalhe)
    if not processo.stdout.strip():
        return []
    try:
        payload = json.loads(processo.stdout)
    except json.JSONDecodeError as erro:
        raise ErroDescobertaImpressoras("O Windows retornou uma lista de impressoras invalida.") from erro
    itens = payload if isinstance(payload, list) else [payload]
    return [
        {
            "nome": str(item.get("Name") or ""),
            "porta": str(item.get("PortName") or ""),
            "driver": str(item.get("DriverName") or ""),
            "padrao": bool(item.get("Default")),
            "offline": bool(item.get("WorkOffline")),
            "status_windows": item.get("PrinterStatus"),
        }
        for item in itens
        if item.get("Name")
    ]
