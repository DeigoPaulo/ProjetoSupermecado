# Plano de Backup e Restauracao

Este plano foi adaptado para o Sistema de Supermercado. A regra principal e nunca restaurar direto em producao sem testar antes em ambiente separado.

## 1. Backup por empresa

Quando o sistema estiver em modelo multiempresa/SaaS, o painel administrativo deve permitir exportar os dados de uma empresa especifica para conferencia, auditoria ou recuperacao assistida.

Por seguranca, esse backup nao deve incluir:

- senhas de usuarios;
- chaves de integracoes fiscais, pagamento ou marketplace;
- certificado digital A1;
- senha do certificado;
- arquivos enviados na pasta `media/`, como logos e imagens de produtos.

## 2. Backup local do sistema

Em desenvolvimento, um backup JSON pode ser gerado com:

```powershell
.\.venv\Scripts\python.exe manage.py dumpdata --exclude auth.permission --exclude contenttypes --indent 2 > backups\backup_supermercado.json
```

Antes de usar esse comando, crie a pasta `backups/`.

Para servidor local da loja, use o script operacional:

```powershell
.\scripts\backup_local.ps1
```

Primeiro execute `.\scripts\backup_local.ps1 -ValidarSomente`. O diagnóstico informa as fontes efetivas sem gerar arquivos. Quando o WinSW estiver instalado, o script lê seu XML para usar o banco, a mídia e os logs de `%ProgramData%`; sem o serviço, usa a configuração do Django. O contrato `erp_local_backup_v2` gera `.zip` com `dados.json`, pasta `media/`, manifesto e checksum SHA-256. Para SQLite inclui snapshot consistente; para PostgreSQL inclui `database.dump` custom criado por `pg_dump`. Diretórios declarados de mídia ou logs também recebem entrada explícita no ZIP quando vazios, evitando manifesto incompatível com a restauração. A execução também verifica as cadeias fiscais em modo estrito, compara a âncora externa anterior, preserva `fiscal-evidence-anchor-latest.json` no destino e inclui uma cópia validada no ZIP; divergência impede a conclusão do backup. Cada execução operacional registra na auditoria apenas o estado sanitizado, a origem e os totais, sem conteúdo fiscal ou credenciais; o alerta fica visível somente ao Master e estados idênticos consecutivos não geram duplicação. Para incluir logs:

```powershell
.\scripts\backup_local.ps1 -IncluirLogs
```

O destino padrão é `%ProgramData%\DeigoVarejo\Backups`; configure `LOCAL_BACKUP_DIR` para outro volume protegido. Para automatizar no Windows como `SYSTEM`, sem depender de usuário conectado, registre a tarefa diária:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -RetencaoDias 15
```

Para gerar tambem um pacote criptografado em producao, configure a senha fora do repositorio e execute:

```powershell
$env:BACKUP_ENCRYPTION_PASSPHRASE = "senha-forte-fora-do-git"
.\scripts\backup_local.ps1 -IncluirLogs
```

O script cria um `.zip.aes` com AES-256 e checksum proprio. Quando a politica da empresa exigir somente o arquivo criptografado, use `-RemoverOriginalCriptografado` para apagar o `.zip` aberto ao final da geracao.

A cópia secundária fica desligada por padrão. Para NAS, compartilhamento de rede ou disco externo, configure um destino diferente da pasta principal e confirme explicitamente a natureza externa:

```powershell
$env:BACKUP_ENCRYPTION_PASSPHRASE = "senha-forte-fora-do-git"
.\scripts\backup_local.ps1 `
  -DestinoSecundario "\\nas-loja\backup\DeigoVarejo" `
  -ConfirmarDestinoSecundario `
  -RetencaoSecundariaDias 90 `
  -RemoverOriginalCriptografado
```

Somente o `.zip.aes` e seu `.sha256` são copiados. O arquivo usa nome temporário no segundo destino, tem o hash recalculado e só é promovido após igualdade com a origem. Cada execução real registra no banco um resultado idempotente e sanitizado com data, sucesso ou falha, etapa, uso de criptografia, presença de cópia secundária e confirmação do SHA-256; caminhos, nomes de rede, arquivos, senhas e conteúdo não são armazenados. O histórico e o alerta da última falha aparecem somente ao Master. Destino igual, interno à pasta principal, sem confirmação ou sem criptografia é recusado. Para a tarefa diária, passe as mesmas opções a `register_backup_task.ps1` ou configure `LOCAL_BACKUP_SECONDARY_DIR` e `LOCAL_BACKUP_SECONDARY_CONFIRMED=True` no ambiente protegido da conta de serviço. O monitor de periodicidade também é exclusivo do Master e usa somente o último resultado bem-sucedido. Ele fica desligado com `LOCAL_BACKUP_MAX_AGE_HOURS=0`; após homologar a tarefa diária, recomenda-se definir `36` horas. Ausência de sucesso ou idade superior ao limite gera pendência alta sem revelar destino ou conteúdo. O pós-instalação e a evidência de aceite usam a mesma política `backup_age_policy_v1`; com valor `0`, o aceite permanece bloqueado até o agendamento e o prazo serem homologados. O aceite não considera mais suficiente apenas o nome e a data do arquivo: `local_backup_package_validation_v1` recalcula o SHA-256, abre e testa todo o ZIP, recusa caminhos inseguros ou duplicados e valida contrato, dump lógico, banco e âncora fiscal. Se somente o `.zip.aes` for mantido, a conta que executa o aceite precisa receber `BACKUP_ENCRYPTION_PASSPHRASE`; a descriptografia ocorre em diretório temporário e o diagnóstico permanece sanitizado.

## 3. Banco e arquivos

O backup completo de producao deve contemplar:

- dump do PostgreSQL;
- copia da pasta `media/`;
- checksum SHA-256;
- criptografia AES-256 para pacotes armazenados fora do servidor;
- retencao automatica de backups antigos;
- copia externa em local protegido.

## 4. Restauracao segura

O fluxo recomendado e:

1. Subir uma copia do sistema em ambiente separado.
2. Aplicar migrations.
3. Restaurar o banco nesse ambiente de teste.
4. Conferir login, empresas, produtos, estoque, vendas, caixa e relatorios.
5. Fazer uma copia atual de producao.
6. Planejar uma janela de restauracao.

Para o backup operacional completo, valide primeiro. Em SQLite, depois da validação execute também `-EnsaiarIsolado`: ele abre uma cópia temporária do snapshot, aplica migrations, roda o Django check e confere a âncora fiscal sem alterar serviço ou dados ativos. O resultado sanitizado usa `local_restore_rehearsal_v1`. PostgreSQL exige um banco já criado, vazio e com prefixo `deigo_rehearsal_`. Configure `RESTORE_REHEARSAL_POSTGRES_DB`, `RESTORE_REHEARSAL_POSTGRES_HOST`, `RESTORE_REHEARSAL_POSTGRES_USER` e `RESTORE_REHEARSAL_POSTGRES_PASSWORD`, então execute `-EnsaiarIsolado -ConfirmarBancoPostgresTemporario`. O script recusa banco ativo/origem e banco com objetos, não usa `--clean`, restaura em transação única e preserva o alvo para inspeção e descarte manual autorizado.

Para o backup operacional completo, valide primeiro:

```powershell
.\scripts\restore_local_backup.ps1 -BackupPath "C:\Backups\backup.zip" -ValidarSomente
```

Na janela aprovada, execute como administrador com `-ConfirmarRestauracao`. O script recusa motores diferentes, usa snapshot no SQLite ou `pg_restore --single-transaction` no PostgreSQL, preserva um backup anterior e faz rollback se migrations ou healthcheck falharem.

Para carregar um backup JSON em ambiente limpo:

```powershell
.\.venv\Scripts\python.exe manage.py loaddata caminho\do\backup.json
```

## 5. Itens sensiveis

Backups com dados fiscais, financeiros ou certificados digitais devem ser criptografados e armazenados fora do computador comum de trabalho.

## 6. Servidor local administrativo

O roteiro de instalacao local fica em `docs/IMPLANTACAO_SERVIDOR_LOCAL.md`. A regra do projeto e manter o ERP administrativo como servidor web local acessado por navegador, enquanto o PDV desktop segue separado e restrito ao operador.
