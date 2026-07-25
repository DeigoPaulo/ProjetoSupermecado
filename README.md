# Sistema de Supermercado

Projeto Django para gestão interna de supermercado, iniciado a partir dos documentos de pré-desenvolvimento do MVP e já evoluído para módulos de compras, financeiro, fiscal, marketplace, produção, sincronização e PDV desktop.

## Estado atual

O núcleo operacional do MVP está implementado: autenticação e perfis, empresa e filiais, produtos, clientes, fornecedores, estoque, PDV, vendas, pagamentos combinados, caixa, auditoria e relatórios. O roadmap atualizado fica na tela **Sistema > Checklist** e em `apps/configuracoes/views.py`.

As próximas frentes concentram-se em homologação de equipamentos, integrações externas, empacotamento do servidor/PDV desktop e itens do escopo original que ainda precisam de decisão.

## Requisitos locais

- Windows PowerShell.
- Python 3.12 ou superior.
- PostgreSQL apenas para ambientes que não usarão o SQLite local.

## Preparar o ambiente

O script de setup cria ou reaproveita a `.venv`, instala as dependências, cria o `.env` quando necessário e valida Django e migrations:

```powershell
.\scripts\setup_local.ps1
```

Se a política do Windows bloquear scripts, use a liberação somente para esse processo, sem alterar a política global:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1
```

Se o Python não estiver disponível como `python`, informe o caminho:

```powershell
.\scripts\setup_local.ps1 -Python "C:\caminho\python.exe"
```

Uma `.venv` inválida não é apagada: o script a preserva como `.venv.broken-AAAAmmdd-HHmmss` antes de criar o ambiente novo.

Depois do setup:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## Validação antes de alterar o projeto

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

## Regras técnicas

- Quantidades usam `DecimalField` com 3 casas decimais.
- Valores monetários usam `DecimalField` com 2 casas decimais.
- Estoque possui `quantidade_atual`, `quantidade_reservada` e `quantidade_disponivel`.
- Movimentações críticas de estoque usam `transaction.atomic()` e `select_for_update()`.
- Cadastros históricos usam inativação lógica com `is_active` e `deleted_at`.
- Desenvolvimento local pode usar SQLite; PostgreSQL é configurado por variáveis de ambiente.

## Ambiente

O projeto lê variáveis do arquivo `.env`. Use `.env.example` como base.

- `DJANGO_ENV=development` mantém o modo local simples.
- `DEBUG=false` exige `SECRET_KEY` própria.
- `ALLOWED_HOSTS` deve conter os dominios/IPs liberados.
- Para PostgreSQL, configure `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` e `POSTGRES_PORT`.
- `MEDIA_ROOT`, `STATIC_ROOT` e `LOG_DIR` podem apontar para pastas especificas do servidor.
- Recuperação de senha usa console no desenvolvimento. Em produção, configure `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`/`EMAIL_USE_SSL` e `DEFAULT_FROM_EMAIL`.

## Próximos passos

1. Homologar o PDV desktop com balança, TEF, impressora e gaveta reais.
2. Gerar instaladores assinados para o PDV e o servidor local.
3. Escolher e homologar provedores externos antes de ativar SEFAZ, CNPJ/CEP e mapas em produção.
