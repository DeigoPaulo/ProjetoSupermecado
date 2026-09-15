# Testes concorrentes com PostgreSQL

Os testes de concorrência não usam SQLite como evidência, pois esse banco não exerce
`select_for_update`. O projeto aceita uma base PostgreSQL local ou descartável somente por
variáveis de ambiente; nenhuma credencial real ou configuração de produção é necessária.

## Preparação

Use um usuário PostgreSQL de desenvolvimento que possa criar e remover bancos de teste.
`POSTGRES_DB` é a base de conexão do ambiente de desenvolvimento. `POSTGRES_TEST_DB` é a
base descartável criada e removida pelo executor de testes do Django e, por segurança, deve
começar com `test_` e ser diferente da base de conexão.

No PowerShell, configure o processo atual sem gravar a senha no repositório:

```powershell
$env:POSTGRES_DB = "postgres"
$env:POSTGRES_TEST_DB = "test_supermercado_concorrencia"
$env:POSTGRES_HOST = "127.0.0.1"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_USER = "usuario_de_teste"
$env:POSTGRES_PASSWORD = "senha_do_ambiente_de_teste"
.\scripts\test_concorrencia_postgresql.ps1
```

O teste de unicidade fiscal por venda e pedido usa o mesmo ambiente:

```powershell
.\scripts\test_concorrencia_postgresql.ps1 `
    -TestLabel "apps.fiscal.test_concorrencia_preparacao.DocumentoFiscalOriginConcurrencyTests"
```

O script recusa nome de teste sem o prefixo `test_`, recusa usar a mesma base nos dois
campos, desativa conexões persistentes e executa somente o caminho informado em
`TestLabel`. Sem esse parâmetro, executa
`apps.compras.test_concorrencia_finalizacao` com duas conexões simultâneas.

Em uma execução comum no SQLite, o teste fica explicitamente ignorado. Um resultado
ignorado não valida concorrência. A correção só pode ser marcada como validada quando o
teste concluir em PostgreSQL real.
