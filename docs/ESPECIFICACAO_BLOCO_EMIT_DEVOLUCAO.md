# Especificação do bloco `emit` da devolução

14/09/2026 · ciclo 100 · contrato `supplier_return_emit_field_specification_v1`.

Esta etapa descreve os 11 campos do emitente já confirmados na matriz e no pacote XSD 010f auditado. O contrato não lê valores reais, não altera o cadastro da filial e não cria elementos XML.

| Posição estrutural | Caminho futuro | Cardinalidade | Formato XSD |
|---:|---|---:|---|
| 1 | `emit/CNPJ` | 1–1 dentro da escolha CNPJ/CPF | `TCnpj`, máximo 14, `[0-9A-Z]{12}[0-9]{2}` |
| 2 | `emit/xNome` | 1–1 | `TString`, 2 a 60 caracteres |
| 4.1 | `emit/enderEmit/xLgr` | 1–1 | `TString`, 2 a 60 caracteres |
| 4.2 | `emit/enderEmit/nro` | 1–1 | `TString`, 1 a 60 caracteres |
| 4.4 | `emit/enderEmit/xBairro` | 1–1 | `TString`, 2 a 60 caracteres |
| 4.5 | `emit/enderEmit/cMun` | 1–1 | `TCodMunIBGE`, `[0-9]{7}` |
| 4.6 | `emit/enderEmit/xMun` | 1–1 | `TString`, 2 a 60 caracteres |
| 4.7 | `emit/enderEmit/UF` | 1–1 | `TUfEmi`, uma das 27 UFs brasileiras |
| 4.8 | `emit/enderEmit/CEP` | 1–1 | `[0-9]{8}` |
| 5 | `emit/IE` | 0–1 | `TIe`, máximo 14, `[0-9]{2,14}|ISENTO` |
| 8 | `emit/CRT` | 1–1 | `1`, `2`, `3` ou `4` |

As posições `4.n` representam a posição de `enderEmit` dentro de `emit` e a posição do campo dentro do tipo `TEnderEmi`. A posição 8 do CRT considera o grupo municipal opcional como um único slot estrutural do compositor XSD.

## Lacunas confirmadas

- O XSD 010f aceita letras nas 12 primeiras posições do CNPJ; o contrato atual aceita somente 14 dígitos e já mantinha `CNPJ_ALFANUMERICO_NAO_SUPORTADO` como bloqueio.
- A validação atual de razão social, logradouro, bairro e município não exige o mínimo de dois caracteres do XSD.
- A IE atual permite até 30 caracteres genéricos; o XSD admite somente 2 a 14 dígitos ou `ISENTO`, e o próprio elemento é opcional no schema.
- A UF atual verifica duas letras maiúsculas, mas ainda não limita explicitamente o valor ao domínio `TUfEmi`.

Essas diferenças foram registradas; não foram corrigidas silenciosamente porque isso mudaria o contrato de dados e exige uma etapa própria de compatibilidade e migração. Código do município, CEP, número e domínio do CRT já possuem validações estruturais compatíveis com os formatos observados, sem que isso confirme o conteúdo fiscal do caso real.

## Segurança

Cada campo mantém o bloqueio da origem, `SERIALIZACAO_NAO_IMPLEMENTADA` e, quando aplicável, a lacuna de compatibilidade correspondente. `valor_incluido`, `elemento_xml_criado`, alteração de cadastro, XML, assinatura, Focus, SEFAZ direta e transmissão permanecem falsos.

A implementação passou em 24 testes focados da cadeia até `emit` e em 452 testes da suíte fiscal completa.

## Próximo passo

Planejar a compatibilidade do cadastro do emitente com os formatos XSD confirmados, separando mudanças retrocompatíveis das que exigem migração e validação de dados reais. Nenhuma correção de cadastro será aplicada antes desse plano.
