# pdv_desktop_keyboard_contract_v1

Contrato operacional do PDV Web carregado pelo `desktop_pdv/app.py`. `COBERTO_TECLADO`
significa que existe uma sequência de teclas implementada no JavaScript e não apenas um botão.
O shell desktop reserva somente `Ctrl+Q` e `Ctrl+F5` para encerramento.

| Função | Estado | Sequência ou dependência |
| --- | --- | --- |
| Produto/scanner | COBERTO_TECLADO | foco inicial, código, `Enter`; foco retorna ao produto |
| Consulta de preço | COBERTO_TECLADO | `F3`, busca, setas, `Esc` |
| Quantidade inicial | COBERTO_TECLADO | campo quantidade; padrão 1 |
| Editar quantidade | COBERTO_TECLADO | setas no carrinho, `Enter`, quantidade, `Enter` |
| Remover item | COBERTO_TECLADO | `Delete`; `Ctrl+Delete` limpa com confirmação |
| Consumidor não identificado | COBERTO_TECLADO | `F9`, `1` |
| CPF | COBERTO_TECLADO | `F9`, `2`, CPF, `Enter` |
| CNPJ | COBERTO_TECLADO | `F9`, `3`, CNPJ, `Enter` |
| Cliente | COBERTO_TECLADO | `F4`, busca, setas, `Enter` |
| Produtos favoritos/lista | COBERTO_TECLADO | `F5`, busca, setas, `Enter` |
| Promoções | COBERTO_TECLADO | `F11`, busca, setas, `Enter` |
| Desconto total | COBERTO_TECLADO | dentro do pagamento: `F6`, valor, `Enter` |
| Autorização de desconto | COBERTO_TECLADO | credencial/PIN ou usuário/senha, `Enter` entre campos |
| Dinheiro | COBERTO_TECLADO | dentro do pagamento: `F1`, valor, `Enter` |
| Convênio | COBERTO_TECLADO | dentro do pagamento: `F2` |
| Eletrônico | COBERTO_TECLADO | dentro do pagamento: `F3` |
| Crédito/débito | DEPENDE_HARDWARE | escolha eletrônica `F1`/`F2`; confirmação depende do TEF |
| PIX | DEPENDE_HARDWARE | escolha eletrônica `F3`; aprovação depende do provedor/TEF |
| Pagamento dividido | COBERTO_TECLADO | `Shift++` ou `Add`; `Delete` remove a linha ativa |
| TEF | DEPENDE_HARDWARE | bridge local; repetição bloqueada enquanto processa |
| Troco | COBERTO_TECLADO | cálculo e leitura no resumo do pagamento |
| Finalização | COBERTO_TECLADO | `Enter` somente quando o contexto está pronto |
| Entrega | COBERTO_TECLADO | `Ctrl+E`; pendências em `Shift+E` |
| Estorno | COBERTO_TECLADO | `F6` fora do pagamento, setas, `Enter`, `Ctrl+Enter` protegido |
| DAV | COBERTO_TECLADO | `F7` |
| Caixa | COBERTO_TECLADO | `F8`; seleção por setas e `Enter` |
| Suprimento | COBERTO_TECLADO | no caixa: `F2`, valor, `Ctrl+Enter` |
| Sangria | COBERTO_TECLADO | no caixa: `F3`, valor, `Ctrl+Enter` |
| Fechamento | COBERTO_TECLADO | no caixa: `F5`, valor, `Ctrl+Enter` |
| Balança | DEPENDE_HARDWARE | `F12`; falha retorna foco à quantidade manual |
| Captura no pinpad | DEPENDE_HARDWARE | `Shift+F4`; falha retorna foco ao documento manual |
| Impressão | DEPENDE_HARDWARE | pós-venda `F10`; spooler/impressora são externos |
| Próxima venda | COBERTO_TECLADO | pós-venda `Enter` ou `Esc`; foco retorna ao produto |

## Contextos de tecla

- `GLOBAL`: F2 busca, F3 preço, F4 cliente, F5 produtos, F6 estorno, F7 DAV,
  F8 caixa, F9 pagamento, F11 promoções e F12 balança.
- `CART`: setas selecionam, `Enter` edita, `Delete` reduz/remove e `Ctrl+Delete` limpa.
- `QUANTITY`: `Enter` confirma e `Esc` cancela.
- `CPF_DECISION`: `1/2/3`, setas e `Enter` atuam somente na pergunta de documento.
- `PAYMENT`: F1 dinheiro, F2 convênio, F3 eletrônico, F4 outros, F6 desconto,
  `Shift++`/`Add` divide e `Delete` remove a parcela ativa.
- `ELECTRONIC_PAYMENT`: F1 crédito, F2 débito, F3 PIX, F4 vale-alimentação e
  F5 vale-refeição.
- `REFUND`, `CASH`, `DELIVERY` e `POST_SALE`: seguem as sequências da tabela.

## Cenários mínimos

1. Venda simples: produto, `Enter`, `F9`, `1`, `F1`, valor, `Enter`, confirmar entrega,
   `Enter` para a próxima venda.
2. CPF/CNPJ: produto, `F9`, `2` ou `3`, documento, `Enter`, pagamento.
3. Quantidade: setas, `Enter`, nova quantidade, `Enter`.
4. Pesável: produto, `F12`, peso, `Enter`.
5. Desconto: `F9`, decisão CPF, `F6`, desconto, supervisor, pagamento.
6. Dividido: `F9`, primeira forma, `Shift++`, segunda forma, `Enter`.
7. Estorno: `F6`, setas, venda, ação protegida.

Hardware real permanece fora deste contrato; os testes automatizados usam bridges simuladas.
