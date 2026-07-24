# Implantacao do servidor local administrativo

Este roteiro cobre supermercados que precisam operar sem depender da internet. O PDV dos caixas continua sendo um aplicativo separado e limitado ao operador. O administrativo local roda o mesmo ERP Django em um computador servidor ou maquina principal da loja.

## Arquitetura

- Servidor local: Django, banco de dados, arquivos `media/`, logs, backup e filas de sincronizacao.
- Acesso administrativo: navegador em `http://127.0.0.1:8000/` na propria maquina ou pelo IP da rede interna.
- PDV desktop: instalado nos caixas e conectado ao servidor local.
- Nuvem: opcional, por sincronizacao segura quando a loja contratar esse modo.

## Preparacao inicial

1. Instale Python, Git e dependencias do sistema.
2. Crie a `.venv` e instale `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Ajuste `ALLOWED_HOSTS` com `127.0.0.1`, `localhost` e o IP interno do servidor.
5. Em loja real, troque `SECRET_KEY`, desative `DEBUG` e use PostgreSQL quando possivel.

## Rodar localmente

Para uso na propria maquina:

```powershell
.\scripts\run_local_server.ps1
```

Para liberar na rede interna:

```powershell
.\scripts\run_local_server.ps1 -Bind 0.0.0.0 -Port 8000
```

Depois acesse pelo navegador:

```text
http://IP-DO-SERVIDOR:8000/
```

## Serviço Windows planejado

A tarefa agendada continua como fallback operacional. Para o instalador/serviço real, o contrato atual do sistema usa:

```text
Nome: MercaFlowServidorLocal
Comando: .\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 config.wsgi:application
Healthcheck: /login/
Restart: iniciar com o Windows e reiniciar automaticamente em falha
Logs: logs/django.log e logs/servidor-local.log
```

Use uma conta local dedicada, sem permissao de administrador diario. O `runserver` deve ficar apenas para desenvolvimento ou contingencia assistida.

## Agendar inicializacao no Windows

Para iniciar o servidor quando o usuario do servidor entrar no Windows:

```powershell
.\scripts\register_local_server_task.ps1 -Bind 0.0.0.0 -Port 8000
```

Para registrar uma tarefa de inicializacao da maquina, execute o PowerShell como administrador:

```powershell
.\scripts\register_local_server_task.ps1 -Bind 0.0.0.0 -Port 8000 -AtStartup -Force
```

## Backup local

Backup padrao:

```powershell
.\scripts\backup_local.ps1
```

Backup incluindo logs:

```powershell
.\scripts\backup_local.ps1 -IncluirLogs
```

O script gera um arquivo `.zip` em `backups/` e um `.sha256` para conferencia de integridade.
Em producao, defina `BACKUP_ENCRYPTION_PASSPHRASE` fora do repositorio para gerar tambem um pacote `.zip.aes` criptografado.

## Agendar backup no Windows

Para registrar backup diario as 02:30:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -RetencaoDias 15
```

Para enviar backups para outra pasta ou disco:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -Destino "D:\Backups\MercaFlow" -RetencaoDias 30 -Force
```

## Agendar sincronizacao loja-nuvem

Quando a empresa usar o modo hibrido ou nuvem com agente, registre a sincronizacao recorrente no servidor local:

```powershell
.\scripts\register_sync_task.ps1 -IntervaloMinutos 1
```

Para substituir uma tarefa existente ou aumentar o lote processado por ciclo:

```powershell
.\scripts\register_sync_task.ps1 -IntervaloMinutos 5 -LimiteSaida 100 -LimiteEntrada 100 -Force
```

O script agenda o comando `processar_sincronizacao_completa`, que processa a fila de saida da loja e a fila de entrada recebida da nuvem. Antes de ativar em producao, confirme as variaveis de URL e token da API de sincronizacao no `.env`.

## Proximas evolucoes

- Gerar instalador/servico Windows assinado a partir do contrato MercaFlowServidorLocal.
- Criptografar backup automatico em producao.
- Criar instalador assinado para o servidor local.
- Criar rotina de atualizacao com rollback.
- Homologar politicas finais de conflito, monitoramento remoto e transmissao fiscal real por ambiente.
