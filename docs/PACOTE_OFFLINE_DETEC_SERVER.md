# Pacote offline do DeTec Server

O pacote offline e criado na maquina de build e levado ao cliente por pendrive
ou armazenamento interno. Ele nao contem banco, `.env`, midia, certificados ou
qualquer dado do supermercado.

## Geracao na maquina de build

Primeiro gere o ZIP validado do servidor usando `package_local_server.ps1`. Em
seguida, obtenha os instaladores oficiais do Python 3.12 e PostgreSQL 16 e
calcule seus hashes com `Get-FileHash -Algorithm SHA256`.

```powershell
.\\scripts\\package_detech_server_offline.ps1 `
  -Version "1.0.0" `
  -ServerPackagePath ".\\dist\\server_local\\DeigoVarejoServidorLocal-1.0.0.zip" `
  -PythonInstallerPath "C:\\Instaladores\\python-3.12.exe" `
  -PythonInstallerSha256 "SHA256_DO_PYTHON" `
  -PostgreSqlInstallerPath "C:\\Instaladores\\postgresql-16.exe" `
  -PostgreSqlInstallerSha256 "SHA256_DO_POSTGRESQL" `
  -WinSWPath "C:\\Instaladores\\WinSW-x64.exe" `
  -WinSWSha256 "SHA256_DO_WINSW"
```

O resultado fica em `dist\\detech_server_offline` acompanhado do SHA-256.

## Instalacao no cliente

1. Extraia o ZIP em uma pasta local.
2. Abra PowerShell como administrador na pasta extraida.
3. Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\Install-DeTecServer.ps1 -ServerIp "192.168.0.10"
```

O Python e instalado silenciosamente quando ainda nao existir. A primeira
instalacao do PostgreSQL abre o instalador oficial, pois a senha mestre do banco
precisa ser definida pelo tecnico. Ao terminar essa tela, execute o mesmo
comando novamente; o restante e automatico.
