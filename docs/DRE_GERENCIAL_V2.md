# DRE Gerencial 2.0

## Escopo

A DRE Gerencial 2.0 é um demonstrativo econômico interno, reproduzível por período e segregado por empresa e filial. Ela não substitui DRE contábil oficial, ECD, ECF, SPED ou a classificação realizada pelo contador.

A tela `/financeiro/resultado/` continua sendo exclusivamente a visão financeira do caixa e do livro realizado. A única DRE visual do sistema é a DRE Gerencial 2.0, com tela, JSON e CSV próprios em `/financeiro/dre/`, `/financeiro/dre.json` e `/financeiro/dre/exportar.csv`. As três saídas usam o mesmo serviço.

O contrato legado `financial_accounting_package_v1` preserva o campo `dre_gerencial` para consumidores existentes. Esse campo é um resumo financeiro histórico de entradas e saídas, não representa a DRE Gerencial 2.0 e não é mais exibido como DRE na tela ou no CSV de resultado.

Contratos:

- `financial_dre_v2`
- `financial_cmv_reconciliation_v1`

## Base temporal

- Venda e desconto: data da venda.
- Cancelamento estruturado: `Venda.cancelada_em`.
- Cancelamento legado sem data: data original da venda, com qualidade temporal parcial explícita.
- Devolução: `DevolucaoVenda.data`.
- Perda: `PerdaEstoque.data`.
- Despesa ou receita realizada: `LancamentoFinanceiro.data`.
- Liquidação e antecipação: `RecebivelEletronico.data_liquidacao`.
- Chargeback: `MovimentoRecebivelEletronico.data`.

Essa política é gerencial e orientada aos eventos disponíveis. Ela não declara regime de competência contábil formal.

## Receita

Fórmula:

`receita líquida = receita bruta - descontos - cancelamentos - devoluções`

A receita bruta e o desconto vêm dos valores persistidos na venda. O cancelamento integral reverte o valor líquido da venda, pois o desconto já está destacado. Assim, uma venda de R$ 100,00 com R$ 10,00 de desconto e R$ 90,00 de cancelamento produz receita líquida zero.

Devoluções usam `DevolucaoVenda.valor_total` no período em que ocorreram. Valores não são reconstruídos com preços atuais.

## CMV

A fonte exclusiva do custo histórico é `ItemVenda.custo_unitario_no_momento`:

`CMV bruto = soma(quantidade vendida × custo unitário congelado)`

`CMV líquido = CMV bruto - reversões de cancelamento - reversões de devolução`

O cálculo mantém a precisão decimal durante multiplicações e somas. `quantizar_moeda` é aplicado ao total apresentado, não a cada item intermediário.

Cancelamentos revertem todo o custo congelado da venda. Devoluções revertem `ItemDevolucaoVenda.quantidade × ItemVenda.custo_unitario_no_momento` no período da devolução.

Quando o snapshot está ausente, o serviço não usa `Produto.preco_custo` nem `Estoque.custo_medio`. O custo conhecido é apresentado como incompleto, com quantidade de itens, valor comercial sem cobertura e percentual de cobertura.

## Reconciliação de CMV

A reconciliação principal compara cada operação com `MovimentacaoEstoque`:

- venda: referência `venda:<id>` e movimento `VENDA`;
- cancelamento: referência `cancelamento_venda:<id>` e movimento `DEVOLUCAO`;
- devolução: referência `devolucao_venda:<id>` e movimento `DEVOLUCAO`.

Os estados são `OK`, `DIVERGENTE`, `INCOMPLETO` e `SEM_BASE`. Diferenças são expostas por operação e não são compensadas silenciosamente.

`FechamentoEstoqueContabil` aparece como evidência complementar do valor de estoque anterior/final disponível, data, critério e exatidão temporal. A versão atual não afirma a equação completa de inventário, pois compras, perdas, ajustes, produção, desmembramentos e inventários também alteram o estoque.

## Perdas

Perdas usam `PerdaEstoque.valor_custo_estimado` e aparecem separadas do CMV, detalhadas pelo tipo persistido. A DRE não converte perda em custo de venda.

## Livro financeiro e categorias

`CategoriaFinanceira.grupo_dre` exige classificação humana explícita:

- despesa operacional;
- despesa financeira;
- tributo sobre resultado;
- outra receita;
- outra despesa;
- não classificado.

Não existe classificação automática pelo nome. Saídas e entradas sem grupo aparecem nos diagnósticos e tornam o resultado líquido incompleto.

Pagamentos ligados a `ContaFinanceira.entrada_compra` são excluídos da despesa da DRE: a mercadoria será reconhecida pelo CMV quando vendida. Recebimentos ligados a `PagamentoVenda` ou a `ContaFinanceira.venda` também são excluídos da classificação econômica, pois a receita já é reconhecida pela venda. Esses recebimentos continuam íntegros no livro e no resultado financeiro. Transferências, sangrias, suprimentos e estornos técnicos também não geram resultado econômico por si sós.

As despesas detalhadas preservam categoria, conta contábil, centro de custo e filial quando disponíveis.

## Recebíveis eletrônicos

`taxa_prevista` é apenas diagnóstico e não altera o resultado realizado. Cada recebível entra uma única vez na data de liquidação, mesmo quando possui múltiplos movimentos históricos. O custo de liquidação conhecido é a diferença não negativa entre valor bruto e valor liquidado. A divergência de liquidação é `valor liquidado - valor líquido previsto` e permanece destacada para não ser confundida com taxa.

A antecipação é identificada como evento, mas seu valor é o total efetivamente liquidado. Sem um campo estruturado próprio, a DRE não inventa nem segrega uma taxa específica de antecipação.

Chargebacks usam o movimento estruturado e sua data, uma única vez, dentro das despesas financeiras. Não são confundidos com devoluções comerciais.

## Tributos e resultado

Tributos sobre resultado só aparecem quando existem saídas explicitamente classificadas nesse grupo. Sem classificação, a linha informa “Não apurado”.

O resultado conhecido continua disponível para conferência, mas o resultado líquido gerencial só é declarado completo quando há cobertura de CMV, ausência de movimentos relevantes não classificados e classificação explícita de tributos.

Todos os valores monetários do JSON são strings decimais. Nenhum cálculo usa `float`.

## Limitações desta versão

- Não há fechamento mensal, bloqueio de período, reabertura ou snapshot imutável da DRE.
- O fechamento de estoque é evidência, não uma reconciliação contábil integral do inventário.
- A DRE depende da configuração humana das categorias e da qualidade dos snapshots históricos.
- Cancelamentos antigos sem timestamp mantêm uma política de compatibilidade declarada, sem regravar ou inventar dados históricos.
