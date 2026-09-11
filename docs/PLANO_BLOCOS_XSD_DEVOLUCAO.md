# Plano de construção por bloco da devolução

11/09/2026 · ciclo 98 · contrato `supplier_return_xsd_block_build_plan_v1`.

Os 105 caminhos confirmados no XSD auditado foram organizados conforme a ordem direta de `NFe/infNFe`. Este plano não contém valores e não cria árvore XML; ele apenas informa onde cada campo deverá ser tratado e por que ainda não pode ser serializado.

| Posição XSD | Bloco | Cardinalidade | Campos confirmados |
|---:|---|---:|---:|
| 1 | `ide` | 1 | 5 |
| 2 | `emit` | 1 | 11 |
| 4 | `dest` | 0–1 | 11 |
| 8 | `det` | 1–990 | 50 |
| 9 | `total` | 1 | 15 |
| 10 | `transp` | 1 | 10 |
| 12 | `pag` | 1 | 2 |
| 14 | `infAdic` | 0–1 | 1 |

Total: 8 blocos e 105 campos. Os demais blocos da sequência oficial continuam fora do escopo atual, sem serem classificados automaticamente como dispensados.

## Bloqueios por campo

Todo campo recebe `SERIALIZACAO_NAO_IMPLEMENTADA`. Conforme a matriz, também pode receber `ORIGEM_NAO_PRONTA`, `CONDICAO_FISCAL_NAO_APROVADA` ou `DECISAO_FISCAL_NAO_APROVADA`. Nenhum campo ou bloco pode ser marcado como pronto.

## Bloqueios globais

- aplicabilidade normativa pendente;
- XSD não instalado;
- XSD não aprovado;
- serializador não implementado.

O contrato fixa como falsas a presença de valores, construção de árvore XML, promoção de schema, geração, assinatura e transmissão. Focus e SEFAZ direta permanecem bloqueados.

## Segurança

O validador confere a ordem e cardinalidade dos blocos, total de 105 campos, contagens internas, presença de bloqueios e políticas. Uma contagem adulterada não interrompe a inspeção dos campos internos: todos os erros são acumulados.

A validação passou em 19 testes focados e na suíte fiscal completa com 444 testes. Não houve migração nem instalação de schema.

## Próximo passo

Especificar o contrato do primeiro bloco (`ide`) campo a campo, incluindo fontes, formato, cardinalidade e bloqueios contextuais, ainda sem atribuir valores ou criar elementos XML.