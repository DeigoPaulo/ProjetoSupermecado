# Sistema de Supermercado

Projeto Django para gestao interna de supermercado, iniciado a partir dos documentos de pre-desenvolvimento do MVP.

## Foco do MVP 1

- Login, usuarios e perfis basicos.
- Empresa e filiais.
- Produtos, categorias, marcas, precos e produtos pesaveis.
- Clientes e fornecedores.
- Estoque por filial, com quantidade fisica, quantidade reservada e movimentacoes.
- PDV, vendas, pagamentos combinados e caixa.
- Auditoria de acoes sensiveis.
- Configuracoes iniciais de impressao por empresa/filial.

## Regras tecnicas ja previstas

- Quantidades usam `DecimalField` com 3 casas decimais.
- Valores monetarios usam `DecimalField` com 2 casas decimais.
- Estoque possui `quantidade_atual`, `quantidade_reservada` e `quantidade_disponivel`.
- Movimentacoes criticas de estoque usam `transaction.atomic()` e `select_for_update()`.
- Cadastros historicos usam inativacao logica com `is_active` e `deleted_at`.
- O projeto inicia em SQLite para desenvolvimento local e esta preparado para PostgreSQL via variaveis de ambiente.

## Como rodar

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## Ambiente

O projeto le variaveis do arquivo `.env`. Use `.env.example` como base.

- `DJANGO_ENV=development` mantem o modo local simples.
- `DEBUG=false` exige `SECRET_KEY` propria.
- `ALLOWED_HOSTS` deve conter os dominios/IPs liberados.
- Para PostgreSQL, configure `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` e `POSTGRES_PORT`.
- `MEDIA_ROOT`, `STATIC_ROOT` e `LOG_DIR` podem apontar para pastas especificas do servidor.

## Dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Proximos passos

1. Evoluir auditoria com tela de consulta filtrada.
2. Planejar modulo financeiro completo.
3. Evoluir integracoes fiscais, marketplace e aplicativo desktop conforme fases posteriores.
