# Pacote offline do DeTec Server

O pacote offline é criado na máquina de build e levado ao cliente por pendrive
ou armazenamento interno. Ele não contém banco, `.env`, mídia, certificados ou
qualquer dado do supermercado.

## Geração na máquina de build

Primeiro, gere o ZIP validado do servidor usando `package_local_server.ps1`. Em
seguida, prepare o runtime portátil oficial do Python 3.12, obtenha o instalador do PostgreSQL 16 e
calcule os respectivos hashes com `Get-FileHash -Algorithm SHA256`.

```powershell
.\scripts\package_detech_server_offline.ps1 `
  -Version "1.0.0" `
  -ServerPackagePath ".\dist\server_local\DeigoVarejoServidorLocal-1.0.0.zip" `
  -PythonRuntimePath ".\dist\offline_sources\python-3.12.10-runtime.zip" `
  -PythonRuntimeSha256 "SHA256_DO_RUNTIME_PYTHON" `
  -PostgreSqlInstallerPath "C:\Instaladores\postgresql-16.exe" `
  -PostgreSqlInstallerSha256 "SHA256_DO_POSTGRESQL" `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -WinSWSha256 "SHA256_DO_WINSW" `
  -PythonPath ".\.venv\Scripts\python.exe"
```

Antes de criar o SHA-256 definitivo, o empacotador gera um ZIP temporário e executa `detech_server_offline_package_validation_v2` com o Python informado. Somente um resultado publicável é promovido ao nome final; em falha, o temporário é removido e um artefato anterior válido permanece intacto. O cálculo de hash usa a biblioteca criptográfica do Windows e não depende de perfil ou módulo PowerShell. A cópia intermediária do wheelhouse é removida antes da compactação para que somente `payload/wheelhouse.zip`, declarado no manifesto, seja entregue.

O resultado fica em `dist\detech_server_offline` acompanhado do SHA-256.

Para publicar na Central configurada por `LOCAL_SERVER_OFFLINE_PACKAGE_PATH`, execute:

```powershell
.\scripts\publish_detech_server_offline.ps1 -Version "1.0.0" -Force
```

O publicador confere o sidecar da origem, executa novamente o contrato no arquivo original e na cópia temporária, recalcula SHA-256 e vincula o checksum ao nome final. A Central aplica ainda `detech_server_offline_publication_validation_v1`: sem o `.zip.sha256`, com hash divergente ou nome vinculado diferente, o botão de download permanece bloqueado mesmo quando o conteúdo do ZIP é válido. Durante uma substituição, mantém cópias de rollback do ZIP e checksum; falha restaura a publicação anterior e remove resíduos `.uploading-*` e `.rollback-*`. O pacote tambem inclui os artefatos
`artifacts\DeTecPDV.exe` e `artifacts\DeTecAdmin.exe`, com seus manifestos de versao e integridade. Ao instalar
ou atualizar o servidor, os dois aplicativos sao publicados automaticamente nas respectivas Centrais de download.

## Instalação no cliente

1. Extraia o ZIP em uma pasta local.
2. Abra o PowerShell como administrador na pasta extraída.
3. Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Install-DeTecServer.ps1 -ServerIp "192.168.0.10"
```

O runtime Python é extraído em `%ProgramData%\DeTecServer\Python312` e não instala nem altera o Python do Windows. A primeira
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
