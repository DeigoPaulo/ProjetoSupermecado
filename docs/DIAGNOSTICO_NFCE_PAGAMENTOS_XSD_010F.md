# NFC-e GO — confronto offline dos pagamentos com XSD 010f

Data: 23/09/2026. Escopo: cenário sintético com cartão de crédito e PIX em duas
parcelas, sem rede fiscal, credencial real, equipamento físico ou homologação.

## Evidência e método

O diagnóstico `nfce_pagamentos_xsd_offline_v1` usa apenas o ZIP já preservado em
`docs/evidencias/nfe_2026_09_10/schemas_010f.zip`, SHA-256
`b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`.
Antes de ler o XML, a auditoria existente confere ZIP, CRC, caminhos, dependências e
compilação do XSD raiz `PL_010f_v1.04/nfe_v4.00.xsd`, SHA-256
`adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df`.
Os cinco XSDs são copiados apenas para diretório temporário, com DTD, entidades
externas e rede desabilitados. Nenhum schema é instalado ou promovido.

O teste prepara NFC-e com endereço estruturado **sintético** da filial, duas
confirmações sintéticas registradas no servidor e parcelas de crédito e PIX. Usa o
certificado de teste já existente no projeto para assinar localmente o documento.
Depois valida o **XML completo** no XSD e verifica a assinatura separadamente.
O conversor Focus recebe esse mesmo XML e produz o JSON sem chamar a API. O canal
direto monta o envelope SOAP localmente, sem transporte. As projeções por parcela
são comparadas ao XML original, e o diagnóstico devolve apenas hashes e estados.

| Verificação offline | Resultado no cenário sintético |
| --- | --- |
| XML completo assinado × XSD 010f arquivado | Conforme |
| Assinatura sintética × conteúdo assinado | Conforme |
| Focus: `tPag`, `vPag`, `tpIntegra`, CNPJ, bandeira, autorização, beneficiário e terminal | Duas parcelas preservadas |
| SEFAZ direta: mesmos campos no XML do envelope SOAP | Duas parcelas e XML integral preservados |
| Cartão e PIX no mesmo documento | Sem bandeira inventada para PIX; projeções idênticas |

O XML ainda não assinado foi rejeitado pelo XSD, que exige `Signature` em `NFe`.
Uma autorização alterada após a assinatura permaneceu estruturalmente aceitável no
XSD, mas foi recusada na checagem criptográfica. Uma bandeira inválida foi recusada
no XSD. Falhas simuladas de conversão Focus e de envelope direto ficaram separadas
por canal e impediram o estado `conforme_offline`.

## Incompatibilidades encontradas e corrigidas

- O gerador escrevia `PISAliq`/`COFINSAliq` diretamente sob `imposto`. O XSD exige
  `imposto/PIS/PISAliq` e `imposto/COFINS/COFINSAliq`, com variantes `NT` e `Outr`
  também dentro dos seus grupos. O aninhamento foi corrigido no gerador comum;
  o conversor Focus agora lê esses tributos no cenário gerado.
- O XML da NFC-e não tinha `enderEmit`. Quando a filial possui logradouro, número,
  bairro, município, código IBGE e UF estruturados, o gerador usa **esses dados**
  para montar o grupo, na posição exigida pelo XSD. Não preenche campos ausentes
  com endereço inventado. Cadastros incompletos ainda produzem diagnóstico XSD
  divergente e requerem bloqueio operacional antes da homologação.

## Limite do resultado

O teste confirma apenas este cenário e este pacote arquivado. Não comprova
aplicabilidade normativa final, aceite da Focus ao CNPJ alfanumérico, aprovação do
schema para o piloto, integração real do TEF/PIX, autorização da SEFAZ-GO ou
prontidão de produção. O registro de confirmação real segue indisponível, pois a
allowlist de verificadores do servidor permanece vazia. Um cadastro incompleto de
emitente continua sendo bloqueio de conformidade e precisa de tratamento explícito
antes de qualquer transmissão real.

Verificações: 4 testes focados dos cenários de pagamento/tributos e, após a
conferência adicional do envelope integral, 1 teste focado aprovado. Regressão de
fiscal, vendas e PDV: 793 testes, 7 ignorados no SQLite por exigirem PostgreSQL.
`manage.py check`, `makemigrations --check --dry-run`, auditoria das importações de
fixtures e `git diff --check` aprovados. Nenhuma migration foi criada neste ciclo.
