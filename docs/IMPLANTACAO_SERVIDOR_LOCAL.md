# Implantação do servidor local administrativo

Este roteiro cobre supermercados que precisam operar sem depender da internet. O PDV dos caixas continua sendo um aplicativo separado e limitado ao operador. O administrativo local roda o mesmo ERP Django em um computador servidor ou máquina principal da loja.

## Arquitetura

- Servidor local: Django/Waitress, banco de dados, arquivos `media/`, logs, backup e filas de sincronização.
- Acesso administrativo: navegador em `http://127.0.0.1:8000/` na própria máquina ou pelo IP da rede interna.
- PDV desktop: instalado nos caixas e conectado ao servidor local.
- Nuvem: opcional, por sincronização segura quando a loja contratar esse modo.

## Preparação inicial

1. Instale Python, Git e as dependências do sistema.
2. Crie a `.venv` e instale `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Ajuste `ALLOWED_HOSTS` com `127.0.0.1`, `localhost` e o IP interno do servidor.
5. Em loja real, troque `SECRET_KEY`, desative `DEBUG` e use PostgreSQL quando possível.

## Operação manual

O script usa Waitress por padrão:

```powershell
.\scripts\run_local_server.ps1 -Bind 0.0.0.0 -Port 8000
```

O `runserver` fica restrito a desenvolvimento explícito:

```powershell
.\scripts\run_local_server.ps1 -Development
```

## Serviço Windows

O serviço `MercaFlowServidorLocal` usa WinSW para executar Waitress, iniciar automaticamente com o Windows, reiniciar após falha e manter logs rotativos em `%ProgramData%\MercaFlow\ServidorLocal\logs`.

1. Baixe o WinSW somente da publicação oficial e confira o SHA-256 divulgado pela fonte ou pelo processo de distribuição interno.
2. Abra o PowerShell como administrador.
3. Execute:

```powershell
.\scripts\install_local_server_service.ps1 `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -ExpectedSha256 "COLOQUE_AQUI_64_CARACTERES_HEXADECIMAIS" `
  -Bind 0.0.0.0 `
  -Port 8000
```

O instalador valida o hash antes de copiar o wrapper, executa `check`, migrations e `collectstatic`, instala/inicia o serviço e só conclui após o healthcheck em `/login/`.

Diagnóstico operacional:

```powershell
.\scripts\test_local_server_service.ps1
```

Remoção do serviço, preservando os logs:

```powershell
.\scripts\uninstall_local_server_service.ps1
```

Para remover também os arquivos do wrapper e logs, use `-RemoveServiceFiles`. O banco, `media/`, projeto e backups não ficam nessa pasta e não são apagados.

Em produção, configure o serviço para uma conta local dedicada, sem login interativo e com acesso mínimo à pasta do ERP e ao banco. A homologação deve confirmar início após reinicialização, recuperação após falha e acesso pela rede interna.

## Tarefa agendada de contingência

Se o serviço ainda não estiver homologado, a tarefa agendada pode ser usada temporariamente:

```powershell
.\scripts\register_local_server_task.ps1 -Bind 0.0.0.0 -Port 8000 -AtStartup -Force
```

## Backup local

```powershell
.\scripts\backup_local.ps1
.\scripts\backup_local.ps1 -IncluirLogs
```

O script gera `.zip` e `.sha256`. Em produção, defina `BACKUP_ENCRYPTION_PASSPHRASE` fora do repositório para gerar também `.zip.aes`.

Agendamento diário:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -RetencaoDias 15
```

## Sincronização loja-nuvem

No modo híbrido ou nuvem com agente:

```powershell
.\scripts\register_sync_task.ps1 -IntervaloMinutos 1
```

Antes da produção, confirme URL e token da API no `.env` e homologue conflitos e retomada após indisponibilidade.

## Pendências de homologação

- Instalar o serviço com um binário WinSW verificado em uma máquina Windows limpa.
- Definir ACLs e conta de serviço dedicada.
- Validar atualização com rollback e janela fora do expediente.
- Homologar backup restaurável, sincronização e transmissão fiscal no ambiente real.