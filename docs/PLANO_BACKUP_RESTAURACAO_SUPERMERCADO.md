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

Ele gera um pacote `.zip` com `dados.json`, banco SQLite quando existir, pasta `media/`, manifesto e checksum SHA-256. Para incluir logs:

```powershell
.\scripts\backup_local.ps1 -IncluirLogs
```

Para automatizar no Windows, registre a tarefa diaria:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -RetencaoDias 15
```

Para gerar tambem um pacote criptografado em producao, configure a senha fora do repositorio e execute:

```powershell
$env:BACKUP_ENCRYPTION_PASSPHRASE = "senha-forte-fora-do-git"
.\scripts\backup_local.ps1 -IncluirLogs
```

O script cria um `.zip.aes` com AES-256 e checksum proprio. Quando a politica da empresa exigir somente o arquivo criptografado, use `-RemoverOriginalCriptografado` para apagar o `.zip` aberto ao final da geracao.

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

Para carregar um backup JSON em ambiente limpo:

```powershell
.\.venv\Scripts\python.exe manage.py loaddata caminho\do\backup.json
```

## 5. Itens sensiveis

Backups com dados fiscais, financeiros ou certificados digitais devem ser criptografados e armazenados fora do computador comum de trabalho.

## 6. Servidor local administrativo

O roteiro de instalacao local fica em `docs/IMPLANTACAO_SERVIDOR_LOCAL.md`. A regra do projeto e manter o ERP administrativo como servidor web local acessado por navegador, enquanto o PDV desktop segue separado e restrito ao operador.
