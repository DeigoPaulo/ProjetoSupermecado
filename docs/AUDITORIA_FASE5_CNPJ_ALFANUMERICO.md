# Auditoria da Fase 5 — CNPJ alfanumérico

Data de corte: 16/09/2026.

## Objetivo

Esta auditoria compara o caminho fiscal operacional com a regra oficial já preservada no
repositório. Ela não altera geradores, adaptadores, XML, credenciais, certificados, ambientes
ou flags de rede.

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

Esse núcleo ainda não é usado pelo fluxo operacional. Foram confirmados 11 pontos da Fase 5:
oito incompatíveis, dois compatíveis apenas de forma condicional e uma capacidade ausente.
Três pontos dos canais da Fase 6 também foram inventariados sem alteração.

| Ordem | Componente | Estado | Diagnóstico |
|---|---|---|---|
| 1 | Formação da chave | Incompatível | Remove letras do CNPJ antes de montar a chave. |
| 1 | DV da chave | Incompatível | Converte cada posição com int, aceitando somente números. |
| 2 | XML NFC-e | Incompatível | Serializa o emitente após normalização somente numérica. |
| 2 | XML NF-e | Incompatível | Repete a mesma normalização no pedido online. |
| 2 | Id de infNFe | Condicional | Preserva a chave recebida, mas depende da formação correta. |
| 3 | Validação do XML | Incompatível | Exige chave de 44 dígitos. |
| 3 | Retorno dos adaptadores | Incompatível | Rejeita autorização ou consulta com letras. |
| 3 | Simulação/cancelamento/consulta | Incompatível | Os serviços ainda exigem somente dígitos. |
| 4 | QR Code NFC-e | Incompatível | Filtra a chave e descarta todas as letras. |
| 5 | Chave textual no DANFE | Condicional | O template imprime o valor integral recebido. |
| 5 | Código de barras do DANFE | Ausente | Não existe implementação Code 128 híbrida. |

## Canais posteriores

O retorno da Focus verifica tamanho, mas não impõe chave numérica nesse ponto; isso é apenas
compatibilidade potencial e não substitui homologação. O adaptador SEFAZ direto e a ingestão
genérica de DF-e removem caracteres não numéricos, portanto continuam incompatíveis. Esses
pontos pertencem à Fase 6 e não devem ser misturados à integração offline da Fase 5.

## Sequência segura

1. Centralizar formação e validação da chave no algoritmo canônico já testado.
2. Integrar o CNPJ canônico aos XMLs offline de NFC-e e NF-e.
3. Trocar as validações numéricas internas sem relaxar tamanho, posição ou DV.
4. Adequar o QR Code da NFC-e e validar os dois modos previstos pelo projeto.
5. Implementar e testar o Code 128 híbrido no DANFE.
6. Somente depois homologar Focus e SEFAZ direta separadamente.

O próximo ciclo deve executar apenas o item 1 em testes offline, mantendo rede e produção
desligadas.
