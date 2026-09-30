# Politica numerica v1

## Contratos

- Quantidades operacionais usam `Decimal` com 3 casas. A resolucao minima padrao e `0.001`.
- Pesos em kg usam 3 casas nos modelos e na apresentacao explicita de peso. A bridge da balanca preserva a precisao configurada de 0 a 6 casas.
- Precos comerciais de venda e promocionais usam 2 casas.
- Custos unitarios internos usam 6 casas.
- Custo medio usa 6 casas.
- Totais comerciais, documentais e financeiros usam 2 casas, com `ROUND_HALF_UP` no limite monetario.
- Totais analiticos de estoque, producao e desmembramento podem usar 6 casas quando alimentam custeio posterior.
- Snapshots cuja integridade depende do custo preservam as 6 casas no payload versionado; contratos historicos continuam verificaveis sem regravacao.

## Compra e conversao

`Produto.fator_conversao_compra` informa quantas unidades base existem em uma unidade de compra. O fluxo manual de cotacao, pedido e entrada recebe `quantidade` e `custo_unitario` na unidade base e nao aplica uma segunda conversao.

Para uma caixa com 12 unidades e custo total de R$ 10,00, o contrato exige registrar `12.000` unidades base e custo unitario interno `0.833333`. O total documental do item permanece R$ 10,00. Na importacao XML, a conversao e explicita para o operador e aplicada uma unica vez.

Na importacao de NF-e, `qCom`, `uCom`, `vUnCom` e `vProd` sao preservados como contrato documental. Antes de criar `ItemEntradaCompra`, a quantidade documental e convertida para a unidade-base por fator explicito do codigo adicional da embalagem ou pelo cadastro de `unidade_compra`. O custo por unidade-base e `vProd / quantidade_base`, quantizado em 6 casas, enquanto o total documental permanece em centavos.

O codigo comercial `cEAN` tem prioridade para identificar a embalagem. `cEANTrib`, o codigo principal do produto e o codigo do produto no fornecedor podem confirmar a identificacao, mas evidencias que apontem para produtos ou fatores diferentes bloqueiam toda a importacao. Equivalencia com zeros a esquerda so existe para GTIN numerico com comprimento e digito verificador validos, usando representacao canonica GTIN-14; codigo interno e SKU de fornecedor exigem correspondencia exata.

O sistema nao infere fator pela descricao do item. Unidade desconhecida, fator invalido ou quantidade convertida que nao caiba exatamente em 3 casas tambem bloqueiam a importacao. Lotes usam o mesmo fator e pedidos continuam expressos na unidade-base. A evidencia documental e a conversao aplicada ficam no snapshot `purchase_xml_unit_conversion_v1` do item.

A conversao nao altera `vProd`, `vNF`, fatura, duplicatas ou conta a pagar. A composicao tributaria do custo, incluindo ICMS-ST, IPI, PIS/COFINS e IBS/CBS, permanece fora deste contrato ate validacao contabil especifica.

### Cadastro assistido de embalagens

Quando a identificacao do produto ou a conversao ainda nao estiver cadastrada, a pre-importacao apresenta a pendencia sem persistir o XML e sem movimentar estoque ou financeiro. O operador autorizado deve confirmar a unidade-base, a apresentacao e o fator; textos como `CX12` na descricao nunca geram fator automaticamente. A confirmacao reenvia o mesmo arquivo, confere seu SHA-256 e reaplica todas as decisoes e a importacao em uma unica transacao.

O aprendizado usa os cadastros existentes: embalagem padrao em `Produto`, apresentacoes adicionais em `CodigoBarrasProduto` e codigo comercial do fornecedor em `ProdutoFornecedor`. CX, FD e PCT podem coexistir com fatores diferentes. Uma nova apresentacao nao substitui silenciosamente a embalagem padrao, e um novo codigo de barras preserva os codigos anteriores. NCM e CEST exibidos no assistente sao apenas referencias informadas pelo fornecedor na NF-e; nenhuma tributacao de entrada e copiada como regra de saida.

Fatores podem ser corrigidos por usuario de Cadastros, com confirmacao explicita e `LogAuditoria`. A mudanca e estritamente prospectiva: novas NF-e usam o fator vigente, enquanto `ItemEntradaCompra`, estoque, custos e snapshots `purchase_xml_unit_conversion_v1` historicos nunca sao recalculados ou reescritos.

## Venda e CMV

Cada item de venda e quantizado uma unica vez para centavos antes de compor o total da venda. Pagamentos, descontos e estornos permanecem em 2 casas. O snapshot de custo da venda preserva 6 casas para permitir o futuro calculo de CMV sem arredondar o custo unitario antes da multiplicacao.
