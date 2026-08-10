import ctypes
import ipaddress
import socket
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


def suggested_ip() -> str:
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        return next(address for address in addresses if not address.startswith("127."))
    except (OSError, StopIteration):
        return "127.0.0.1"


def is_administrator() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


class InstallerWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Instalar DeTec Server")
        self.root.resizable(False, False)
        frame = ttk.Frame(root, padding=24)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="Instalar DeTec Server", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            frame,
            text=("Instala o servidor administrativo, PostgreSQL, Python, servico do Windows "
                  "e libera a porta da rede local."),
            wraplength=470,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 20))
        ttk.Label(frame, text="IP deste servidor").grid(row=2, column=0, sticky="w")
        self.ip_value = tk.StringVar(value=suggested_ip())
        ip_entry = ttk.Entry(frame, textvariable=self.ip_value, width=32)
        ip_entry.grid(row=3, column=0, sticky="ew", padx=(0, 12), pady=(4, 14))
        ttk.Label(frame, text="Porta").grid(row=2, column=1, sticky="w")
        self.port_value = tk.StringVar(value="8000")
        ttk.Entry(frame, textvariable=self.port_value, width=10).grid(
            row=3, column=1, sticky="ew", pady=(4, 14)
        )
        ttk.Label(
            frame,
            text=("Na primeira execucao, o instalador oficial do PostgreSQL podera solicitar "
                  "a senha mestre. Depois de conclui-lo, abra este instalador novamente."),
            foreground="#4b5f7d",
            wraplength=470,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 20))
        ttk.Button(frame, text="Instalar", command=self.install).grid(
            row=5, column=0, columnspan=2, sticky="ew", ipady=6
        )
        root.bind("<Return>", lambda _event: self.install())
        root.bind("<Escape>", lambda _event: root.destroy())
        ip_entry.focus_set()

    def install(self) -> None:
        try:
            server_ip = str(ipaddress.IPv4Address(self.ip_value.get().strip()))
            port = int(self.port_value.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Dados invalidos", "Informe um IPv4 e uma porta valida.")
            return
        bundle_root = Path(sys.executable).resolve().parent
        installer = bundle_root / "Install-DeTecServer.ps1"
        if not installer.is_file():
            messagebox.showerror(
                "Pacote incompleto",
                "Install-DeTecServer.ps1 nao foi encontrado ao lado deste executavel.",
            )
            return
        command = [
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit",
            "-File", str(installer), "-ServerIp", server_ip, "-Port", str(port),
            "-OpenPostgreSqlInstaller",
            "-Force",
        ]
        try:
            if is_administrator():
                subprocess.Popen(["powershell.exe", *command], cwd=bundle_root)
            else:
                result = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "powershell.exe",
                    subprocess.list2cmdline(command), str(bundle_root), 1,
                )
                if result <= 32:
                    raise OSError(f"Falha ao solicitar permissao administrativa ({result}).")
        except OSError as exc:
            messagebox.showerror("Falha ao iniciar", str(exc))
            return
        messagebox.showinfo(
            "Instalacao iniciada",
            "Acompanhe a instalacao na janela do PowerShell. Este iniciador pode ser fechado.",
        )
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    InstallerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
