# Politica numerica v1

## Contratos

- Quantidades operacionais usam `Decimal` com 3 casas. A resolucao minima padrao e `0.001`.
- Pesos em kg usam 3 casas nos modelos e na apresentacao explicita de peso. A bridge da balanca preserva a precisao configurada de 0 a 6 casas.
- Precos comerciais de venda e promocionais usam 2 casas.
- Custos unitarios internos usam 6 casas.
- Custo medio usa 6 casas.
- Totais comerciais, documentais e financeiros usam 2 casas, com `ROUND_HALF_UP` no limite monetario.
- Totais analiticos de estoque, producao e desmembramento podem usar 6 casas quando alimentam custeio posterior.

## Compra e conversao

`Produto.fator_conversao_compra` informa quantas unidades base existem em uma unidade de compra, mas o fluxo atual de cotacao, pedido e entrada ainda recebe `quantidade` e `custo_unitario` na unidade base. O sistema nao aplica conversao silenciosa nesse fluxo.

Para uma caixa com 12 unidades e custo total de R$ 10,00, o contrato atual exige registrar `12.000` unidades base e custo unitario interno `0.833333`. O total documental do item permanece R$ 10,00. Uma futura UX de conversao deve ser explicita e aplicada uma unica vez.

Na importacao de NF-e, `qCom` e `vProd` sao preservados como contrato documental. O custo unitario gerencial e derivado separadamente com 6 casas; o total do fornecedor permanece em centavos.

## Venda e CMV

Cada item de venda e quantizado uma unica vez para centavos antes de compor o total da venda. Pagamentos, descontos e estornos permanecem em 2 casas. O snapshot de custo da venda preserva 6 casas para permitir o futuro calculo de CMV sem arredondar o custo unitario antes da multiplicacao.
