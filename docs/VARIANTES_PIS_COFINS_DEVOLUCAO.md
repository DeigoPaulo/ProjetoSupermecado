# Variantes de PIS e COFINS na devolução

11/09/2026 · ciclo 93 · contrato não emissivo.

## Evidência estrutural

O XSD preservado `PL_010f_v1.04/leiauteNFe_v4.00.xsd` define PIS e COFINS com ocorrência 0-1 por item. Quando um grupo está presente, há uma escolha exclusiva entre quatro variantes:

| Contribuição | Por percentual | Por quantidade | Sem cálculo | Outras operações |
|---|---|---|---|---|
| PIS | `PISAliq` | `PISQtde` | `PISNT` | `PISOutr` |
| COFINS | `COFINSAliq` | `COFINSQtde` | `COFINSNT` | `COFINSOutr` |

As variantes `Outr` possuem outra escolha exclusiva: base/alíquota percentual ou quantidade/alíquota por unidade. O schema demonstra estrutura e compatibilidade de CST; não decide qual grupo ou variante se aplica à devolução concreta.

## Representação por item

Cada grupo mantém os valores já informados na memória e acrescenta:

- `variante_candidata`, vazia por padrão;
- `modalidade_calculo_candidata`, vazia por padrão;
- `variante_fonte=DECISAO_CONTADOR_PENDENTE`;
- `estado_variante=NAO_DEFINIDA`;
- `grupo_opcional_xsd=True`;
- `depende_decisao_contador=True`;
- destino XML futuro próprio de PIS ou COFINS;
- `variante_confirmada=False`.

Uma variante explicitamente candidata é validada contra o conjunto de CSTs aceitos pelo XSD. A modalidade precisa ser `PERCENTUAL`, `QUANTIDADE` ou `SEM_CALCULO` conforme a estrutura escolhida. Esse confronto não faz o caminho inverso: o sistema não escolhe variante pelo CST, pela base, pela alíquota, pelo valor, pelo cadastro atual ou pelo XML histórico.

## Bloqueios

Candidato vazio produz pendência própria para PIS e COFINS. Candidato informado permanece `CANDIDATA_NAO_CONFIRMADA`. O validador recusa variante desconhecida, modalidade ausente ou incompatível, CST incompatível, fonte alterada, cardinalidade promovida, dependência do contador removida, destino divergente e confirmação antecipada.

`origem_completa` continua descrevendo somente a integridade da memória aprovada. `dados_completos` permanece falso enquanto houver decisões fiscais pendentes. `permite_aplicar_variantes_pis_cofins`, geração de XML e emissão permanecem falsos.

## Próximo passo

Consolidar em uma matriz atômica cada campo do contrato, sua fonte, regra de presença/compatibilidade e destino futuro no XML. Somente depois dessa conferência deverá começar o gerador específico da devolução.
