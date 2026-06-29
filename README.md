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
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## Dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Proximos passos

1. Criar telas internas com Bootstrap para dashboard, produtos, estoque, caixa e PDV.
2. Implementar fluxo de venda com baixa transacional de estoque.
3. Criar importacao de produtos/precos via CSV ou Excel.
4. Adicionar relatorios basicos de vendas, estoque baixo e fechamento de caixa.
5. Evoluir integracoes fiscais, marketplace e impressao conforme fases posteriores.
