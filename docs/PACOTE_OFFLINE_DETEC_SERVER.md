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


## Instalador executavel e GitHub

Antes de montar o pacote, execute:

```powershell
.\server_installer\build_windows.ps1
```

O pacote passa a incluir **Instalar DeTec Server.exe**. O modo PowerShell permanece disponivel para suporte tecnico. O PostgreSQL pode solicitar a senha mestre na primeira execucao; depois, execute o instalador novamente para concluir.

O ZIP offline pronto nao deve ser adicionado como arquivo comum do Git: ele ultrapassa o limite de 100 MB do GitHub. Publique-o como ativo de uma **GitHub Release** privada ou transfira-o por armazenamento controlado. O codigo e os scripts de build permanecem no repositorio e permitem reconstruir o pacote em outra maquina.


### Dependencias Python offline

Antes de montar o ZIP, prepare o wheelhouse Windows/Python 3.12 executando `pip download --only-binary=:all:` para `dist/offline_sources/wheelhouse` com o arquivo `requirements.txt`.

O empacotador inclui e valida `payload/wheelhouse.zip`. Durante a instalacao, o pip usa `PIP_NO_INDEX=1`; portanto, nenhuma dependencia e baixada no cliente.
