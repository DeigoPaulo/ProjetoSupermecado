# DeTec Admin

Casca Windows para o painel administrativo do ERP, sem navegador, PDV ou dispositivos de caixa.

## Uso

1. Instale as dependencias: `pip install -r requirements.txt`.
2. Execute: `python app.py`.
3. Informe a URL do servidor, por exemplo `http://192.168.1.10:8000`.
4. Entre com uma conta administrativa do ERP.

Use `python app.py --configurar` para alterar o servidor. A configuracao fica em `%LOCALAPPDATA%\DeTecAdmin\config.json`.

## Build Windows

Execute `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`.
O executavel sera criado em `dist\DeTecAdmin.exe`.