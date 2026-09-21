# Auditoria — vinculação fiscal dos pagamentos eletrônicos na NFC-e GO

Data: 21/09/2026
Escopo: primeiro bloco interno seguro, sem rede fiscal, credenciais reais ou produção.

## Referências normativas verificadas

- Nota Técnica NF-e 2023.004 v1.10, publicada no Portal Nacional da NF-e.
- Leiaute NF-e/NFC-e 4.00 do pacote oficial `PL_010f_v1.04`, preservado em
  `docs/evidencias/nfe_2026_09_10/schemas_010f.zip`.
- Orientação da Secretaria da Economia de Goiás sobre a integração dos meios de
  pagamento vinculada à IN 1.608/2025-GSE, atualizada em 28/08/2026.

No XSD oficial auditado, o grupo `card` contempla cartões, PIX, boletos e outros
pagamentos eletrônicos. Ele contém `tpIntegra` obrigatório quando o grupo existe e os
campos condicionais `CNPJ`, `tBand`, `cAut`, `CNPJReceb` e `idTermPag`. A presença e a
combinação efetivamente exigidas precisam ser decididas por forma de pagamento e regra
vigente; não é seguro preencher campos ausentes por suposição.

## Estado encontrado antes deste ciclo

| Área | Já existia | Lacuna confirmada |
| --- | --- | --- |
| PDV | Pagamentos divididos; confirmação; ID externo; NSU; autorização; bloqueio de parcela eletrônica incompleta | Sem metadados fiscais estruturados do provedor |
| Cartão/PIX | Adaptador único, PIX pendente com consulta e simulador explicitamente restrito | Contrato não transportava integração, CNPJ, bandeira, beneficiário ou terminal |
| Persistência | Uma linha `PagamentoVenda` por parcela | Campos fiscais ausentes |
| XML NFC-e | `detPag` por parcela, com `tPag` 03/04/17 e `vPag` individual | Grupo `card` ainda ausente |
| Canais fiscais | XML comum para o núcleo e conversão Focus dos dados básicos de pagamento | Paridade do novo grupo ainda não implementada |

## Entrega deste ciclo

- `PagamentoVenda` passou a armazenar, sem valores padrão: `tipo_integracao`,
  `cnpj_instituicao_pagamento`, `bandeira_cartao`,
  `cnpj_beneficiario_pagamento` e `identificador_terminal_pagamento`.
- `codigo_autorizacao` passou a aceitar até 128 caracteres, conforme o leiaute.
- O contrato `pdv_tef_v2` anuncia os novos campos, e a interface os preserva por parcela.
- O adaptador desktop e o serviço de vendas normalizam CNPJs e rejeitam tipo de
  integração, bandeira e comprimentos inválidos.
- O simulador continua gerando apenas a evidência técnica antiga de desenvolvimento; ele
  não inventa os novos metadados fiscais.

## Limite deliberado e ponto de retomada

Os novos campos ainda não são serializados no XML. Isso evita declarar integração real
sem driver homologado e separa a captura de dados da regra condicional fiscal.

O próximo bloco deve montar o grupo `card` por `detPag`, validar de forma fail-closed as
combinações aplicáveis a cartão e PIX, usar em `cAut` exclusivamente a autorização
confirmada e demonstrar paridade entre o payload Focus e o XML da SEFAZ direta. A etapa
externa posterior continua dependente do provedor físico e da homologação SEFAZ-GO.