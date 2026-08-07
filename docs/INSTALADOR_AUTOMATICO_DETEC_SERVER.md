# Instalador automatico do DeTec Server (Windows)

O script `scripts\\install_detech_server.ps1` prepara uma maquina Windows que sera
o servidor local do supermercado. Ele instala o ambiente Python do ERP, cria o
banco e usuario da aplicacao no PostgreSQL, grava a configuracao de rede,
executa migrations, registra o servico Windows e libera somente a porta do ERP
na rede privada.

## Antes de executar

1. Reserve um IP fixo para a maquina do servidor, por exemplo `192.168.0.10`.
2. Instale o PostgreSQL 16 x64 com as ferramentas de linha de comando (`psql`,
   `pg_dump` e `pg_restore`).
3. Instale Python 3.12 x64.
4. Baixe o WinSW x64 da fonte oficial e confira seu SHA-256.
5. Extraia o pacote do DeTec Server em uma pasta local, por exemplo
   `C:\\DeTecServer\\app`.
6. Abra o PowerShell como administrador nessa pasta.

## Pre-homologacao

Antes de alterar a maquina do cliente, valide os pre-requisitos sem criar banco,
servico ou regra de firewall:

```powershell
.\scripts\install_detech_server.ps1 `
  -ServerIp "192.168.0.10" `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -WinSWSha256 "COLE_O_SHA256_OFICIAL_DO_WINSW" `
  -Preflight
```
## Execucao

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\scripts\\install_detech_server.ps1 `
  -ServerIp "192.168.0.10" `
  -WinSWPath "C:\\Instaladores\\WinSW-x64.exe" `
  -WinSWSha256 "COLE_O_SHA256_OFICIAL_DO_WINSW" `
  -PostgresDatabase "detech_erp" `
  -PostgresUser "detech_erp"
```

O instalador pedira as senhas do administrador PostgreSQL e do usuario exclusivo
do ERP sem exibi-las na tela. Ao concluir, o acesso e feito por:

```text
http://192.168.0.10:8000/login/
```

Os caixas com DeTec PDV e os administradores com DeTec Admin devem apontar para
esse mesmo endereco. Nenhum computador cliente deve se conectar diretamente ao
PostgreSQL.

## O que o script nao faz

Ele nao baixa silenciosamente programas de terceiros, nao instala drivers de
TEF, impressoras ou balancas e nao abre o servidor para a internet. Esses itens
precisam de homologacao por fabricante e configuracao controlada. Para acesso
externo, use VPN; nao exponha a porta `8000` no roteador.
