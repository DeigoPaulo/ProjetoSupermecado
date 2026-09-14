# Especificação do bloco `ide` da devolução

14/09/2026 · ciclo 99 · contrato `supplier_return_ide_field_specification_v1`.

Esta etapa especifica somente os cinco campos de `ide` já confirmados na matriz da devolução. Ela confronta a matriz atômica com o plano por blocos, registra a definição observada no pacote XSD 010f auditado e não transporta valores nem cria elementos XML.

| Ordem em `ide` | Tag futura | Fonte primária | Cardinalidade | Formato XSD | Bloqueio contextual |
|---:|---|---|---:|---|---|
| 3 | `natOp` | parecer do contador | 1–1 | `TString`, 1 a 60 caracteres | parecer não aprovado |
| 11 | `idDest` | filial e XML original | 1–1 | `xs:string`: `1`, `2` ou `3` | destino não confirmado |
| 12 | `cMunFG` | cadastro da filial | 1–1 | `TCodMunIBGE`: `[0-9]{7}` | cadastro não confirmado |
| 21 | `indFinal` | decisão fiscal | 1–1 | `xs:string`: `0` ou `1` | decisão pendente |
| 22 | `indPres` | decisão fiscal | 1–1 | `xs:string`: `0`, `1`, `2`, `3`, `4`, `5` ou `9` | decisão pendente |

## Limite desta etapa

As posições são relativas à sequência completa de `ide`, não apenas aos cinco campos mapeados. O XSD confirma estrutura e domínio, mas não escolhe o valor correto do caso concreto. Em especial:

- a natureza depende do parecer aprovado;
- a comparação das UFs pode fornecer um candidato a destino, mas não o confirma;
- o código do município deve vir do cadastro da filial e obedecer ao padrão IBGE;
- consumidor final e presença do comprador continuam decisões fiscais explícitas.

Todo campo conserva `SERIALIZACAO_NAO_IMPLEMENTADA` e seu bloqueio de origem. O contrato fixa `valor_incluido`, `elemento_xml_criado` e `pronto_para_serializar` como falsos. Aplicabilidade normativa, instalação e aprovação do XSD e implementação do serializador também continuam pendentes.

## Validação

O validador rejeita divergência de fonte, destino, ordem, cardinalidade, tipo, domínio, bloqueio, contagem ou política. Focus e SEFAZ direta permanecem desligados; não houve acesso a credenciais, certificados ou ambientes.

A implementação passou em 20 testes focados da cadeia matriz–auditoria–compatibilidade–plano–`ide` e em 448 testes da suíte fiscal completa.

## Próximo passo

Especificar o bloco `emit` campo a campo, preservando a separação entre cadastro da filial, configuração fiscal e decisões ainda não aprovadas, sem valores ou XML.
