# Reposição para cotação de compra

## Objetivo

O fluxo `replenishment_quote_draft_v1` transforma itens selecionados da sugestão de reposição em uma cotação de compra em rascunho. Ele elimina redigitação sem automatizar decisões comerciais.

## Como funciona

1. Acesse **Relatórios > Reposição**.
2. Escolha período, dias de cobertura e uma única filial.
3. O servidor recalcula estoque disponível, estoque mínimo, venda líquida e necessidade de cobertura.
4. Marque até 500 produtos sugeridos.
5. Escolha **Criar cotação em rascunho**.
6. Revise quantidades e fornecedores na área de Compras antes de abrir a cotação.

## Travas

- somente perfis com acesso a Compras executam a ação;
- o perfil Financeiro pode consultar a sugestão, mas não cria cotação;
- uma cotação nunca mistura filiais;
- produtos e quantidades são recalculados no servidor; valores enviados pelo navegador não são aceitos;
- produto de outra filial/empresa, seleção duplicada, vazia ou acima do limite é recusado;
- uma chave SHA-256 única torna a mesma solicitação idempotente inclusive sob concorrência;
- a ação cria somente `CotacaoCompra` em estado `RASCUNHO` e seus itens;
- nenhum fornecedor é acionado, nenhum pedido é enviado e estoque, preço, financeiro e fiscal não são alterados;
- a criação fica registrada na auditoria.

## Checklist de uso

- [ ] Conferir período e dias de cobertura.
- [ ] Selecionar uma única filial.
- [ ] Revisar itens sugeridos e produtos sazonais.
- [ ] Criar o rascunho e conferir quantidades.
- [ ] Definir fornecedores e abrir a cotação apenas após revisão humana.
- [ ] Registrar propostas e selecionar a melhor condição pelo fluxo normal de Compras.

A cotação em rascunho é uma sugestão operacional. Ela não representa compromisso, compra, recebimento ou obrigação financeira.
