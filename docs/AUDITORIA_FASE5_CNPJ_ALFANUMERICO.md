# Auditoria da Fase 5 — CNPJ alfanumérico

Data de corte: 16/09/2026.

## Objetivo

Esta auditoria viva compara o caminho fiscal operacional com a regra oficial já preservada
no repositório. No ciclo 123, geradores e validações offline foram integrados; credenciais,
certificados, ambientes, adaptadores de canal e flags de rede continuam inalterados.

As evidências normativas versionadas incluem o manual da Receita Federal, perguntas e
respostas da Receita, a NT Conjunta DF-e 2025.001, a NT NF-e 2026.004 e o pacote XSD
PL_010f_v1.04. A integridade desses arquivos continua protegida por SHA-256 e pelos testes do
contrato alphanumeric_cnpj_official_evidence_v1.

## Resultado

O núcleo isolado já conhece a estrutura oficial da chave:

- 44 caracteres;
- posições 7 a 20 destinadas ao CNPJ alfanumérico;
- expressão [0-9]{6}[A-Z0-9]{12}[0-9]{26};
- DV calculado por módulo 11 usando o valor ASCII menos 48;
- código de barras Code 128 híbrido, alternando conjuntos C e A quando houver letras.

Desde o ciclo 124, esse núcleo é usado pela formação da chave, pelos XMLs reais de NFC-e e
NF-e, pelo QR Code, pela validação pré-transmissão, pelos retornos internos de autorização e
consulta e pelos fluxos de simulação, cancelamento e consulta. Foram confirmados 11 pontos
da Fase 5: nove compatíveis offline, nenhum incompatível interno, um compatível apenas de
forma condicional e uma capacidade ausente. Três pontos dos canais da Fase 6 permanecem
inventariados sem alteração.

| Ordem | Componente | Estado | Diagnóstico |
|---|---|---|---|
| 1 | Formação da chave | Compatível offline | Preserva o CNPJ canônico; o fluxo numérico usa o núcleo. |
| 1 | DV da chave | Compatível offline | Usa módulo 11 com valor ASCII menos 48. |
| 2 | XML NFC-e | Compatível offline | Usa o mesmo CNPJ canônico na chave e em emit/CNPJ. |
| 2 | XML NF-e | Compatível offline | Usa o mesmo CNPJ canônico na chave e em emit/CNPJ. |
| 2 | Id de infNFe | Compatível offline | Preserva integralmente a chave central validada. |
| 3 | Validação do XML | Compatível offline | Valida estrutura, posições, DV e igualdade entre emitente e chave. |
| 3 | Retorno dos adaptadores | Compatível offline | Canonicaliza chave válida e recusa estrutura ou DV inválidos. |
| 3 | Simulação/cancelamento/consulta | Compatível offline | Reutiliza a validação central sem exigir somente dígitos. |
| 4 | QR Code NFC-e | Compatível offline | Reutiliza a chave central válida sem descartar letras. |
| 5 | Chave textual no DANFE | Condicional | O template imprime o valor integral recebido. |
| 5 | Código de barras do DANFE | Ausente | Não existe implementação Code 128 híbrida. |

## Canais posteriores

O retorno da Focus verifica tamanho, mas não impõe chave numérica nesse ponto; isso é apenas
compatibilidade potencial e não substitui homologação. O adaptador SEFAZ direto e a ingestão
genérica de DF-e removem caracteres não numéricos, portanto continuam incompatíveis. Esses
pontos pertencem à Fase 6 e não devem ser misturados à integração offline da Fase 5.

## Sequência segura

1. Implementar e testar o Code 128 híbrido no DANFE.
2. Somente depois homologar Focus e SEFAZ direta separadamente.

O próximo ciclo deve implementar o código de barras Code 128 híbrido no DANFE, preservando
a apresentação textual da chave e mantendo rede e produção desligadas.
