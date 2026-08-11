import ctypes
import ipaddress
import socket
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


def suggested_ip() -> str:
    # Ask Windows routing which address would be used to leave the machine.
    # This avoids fiscal/TEF loopback adapters that expose public-looking /32
    # addresses but have no gateway and cannot serve other computers.
    route_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        route_socket.connect(("1.1.1.1", 443))
        routed_ip = route_socket.getsockname()[0]
        if ipaddress.IPv4Address(routed_ip).is_private:
            return routed_ip
    except OSError:
        pass
    finally:
        route_socket.close()

    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        valid = [ipaddress.IPv4Address(address) for address in addresses]
        return str(next(address for address in valid if address.is_private and not address.is_loopback))
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
            text=("Instala ou atualiza o servidor administrativo. Componentes, banco e "
                  "configuracoes validos sao preservados automaticamente."),
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
            text=("Use o IPv4 da Ethernet/Wi-Fi que possui gateway. "
                  "Ignore adaptadores Loopback, VPN, TEF ou fiscais."),
            foreground="#4b5f7d",
            wraplength=470,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(
            frame,
            text=("Na primeira execucao, o instalador oficial do PostgreSQL podera solicitar "
                  "a senha mestre. Depois de conclui-lo, abra este instalador novamente."),
            foreground="#4b5f7d",
            wraplength=470,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 20))
        ttk.Button(frame, text="Instalar ou atualizar", command=self.install).grid(
            row=6, column=0, columnspan=2, sticky="ew", ipady=6
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
            "-AllowUnsignedDesktopApps",
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
