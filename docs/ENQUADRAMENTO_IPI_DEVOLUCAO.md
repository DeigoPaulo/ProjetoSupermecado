# Enquadramento legal do IPI na devolução

10/09/2026 · ciclo 92 · contrato não emissivo.

## Evidência e limite

No XSD preservado `PL_010f_v1.04/leiauteNFe_v4.00.xsd`, o tipo `TIpi` contém `cEnq` sem `minOccurs=0`; portanto sua cardinalidade é 1-1 quando o grupo `IPI` existe. O campo restringe `TString` ao comprimento de 1 a 3 caracteres. Essa evidência estrutural não decide se o grupo IPI se aplica à devolução concreta, não seleciona um código e não comprova, por si só, regra numérica. O pacote continua preservado para análise, sem promoção operacional.

## Contrato por item

`enquadramento_ipi` registra:

- `valor_candidato`: vazio por padrão; candidato lexicalmente compatível permanece não confirmado;
- `fonte`: `DECISAO_CONTADOR_PENDENTE`;
- `estado_disponibilidade`: `NAO_DEFINIDO` ou `CANDIDATO_NAO_CONFIRMADO`;
- `obrigatoriedade_estrutural`: obrigatório dentro do grupo IPI;
- `obrigatoriedade_contextual`: a presença do grupo depende da hipótese fiscal do item;
- `depende_decisao_contador`: verdadeiro;
- `destino_xml_futuro`: `NFe/infNFe/det/imposto/IPI/cEnq`;
- `confirmado`: falso.

O campo não é copiado de `Produto.codigo_enquadramento_ipi`, XML original, memória tributária nem emissor existente. Também não forma `IPI`, não alimenta `impostoDevol`, não altera base, alíquota, valor ou totalização e não permite XML ou emissão.

## Validações e bloqueios

O validador recusa comprimento fora de 1 a 3, espaços nas extremidades, caracteres fora do intervalo lexical preservado, fonte ou metadados divergentes e confirmação antecipada. Candidato vazio gera `CENQ_CANDIDATO_PENDENTE`; candidato informado gera `CENQ_NAO_CONFIRMADO`. Em ambos os casos `dados_fiscais_completos`, `enquadramento_ipi_definido` e `permite_aplicar_enquadramento_ipi` permanecem falsos.

A integridade da memória é avaliada separadamente da decisão fiscal: uma origem íntegra pode continuar `origem_completa=True`, mas os bloqueios de hipótese, `cEnq`, valores, justificativa, mapeamento XML e homologação impedem qualquer promoção operacional.

## Dependências externas e próximo passo

Ainda dependem do contador e da análise normativa integral: aplicabilidade do grupo IPI, CST, código de enquadramento, eventual `impostoDevol`, justificativa e valores. Focus e SEFAZ direta deverão ser homologados separadamente depois que existir um gerador neutro; nenhuma configuração de canal foi alterada.

Próximo passo técnico: discriminar as variantes de PIS/COFINS sem inferir CST, fórmula, base ou valor e parar novamente antes de qualquer serialização.
