# Pacote offline do DeTec Server

O pacote offline é criado na máquina de build e levado ao cliente por pendrive
ou armazenamento interno. Ele não contém banco, `.env`, mídia, certificados ou
qualquer dado do supermercado.

## Geração na máquina de build

Primeiro, gere o ZIP validado do servidor usando `package_local_server.ps1`. Em
seguida, obtenha os instaladores oficiais do Python 3.12 e PostgreSQL 16 e
calcule os respectivos hashes com `Get-FileHash -Algorithm SHA256`.

```powershell
.\scripts\package_detech_server_offline.ps1 `
  -Version "1.0.0" `
  -ServerPackagePath ".\dist\server_local\DeigoVarejoServidorLocal-1.0.0.zip" `
  -PythonInstallerPath "C:\Instaladores\python-3.12.exe" `
  -PythonInstallerSha256 "SHA256_DO_PYTHON" `
  -PostgreSqlInstallerPath "C:\Instaladores\postgresql-16.exe" `
  -PostgreSqlInstallerSha256 "SHA256_DO_POSTGRESQL" `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -WinSWSha256 "SHA256_DO_WINSW"
```

O resultado fica em `dist\detech_server_offline` acompanhado do SHA-256.

## Instalação no cliente

1. Extraia o ZIP em uma pasta local.
2. Abra o PowerShell como administrador na pasta extraída.
3. Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Install-DeTecServer.ps1 -ServerIp "192.168.0.10"
```

O Python é instalado silenciosamente quando ainda não existir. A primeira
instalação do PostgreSQL abre o instalador oficial, pois a senha mestre do banco
precisa ser definida pelo técnico. Ao terminar essa etapa, execute o mesmo
comando novamente; o restante é automático.
