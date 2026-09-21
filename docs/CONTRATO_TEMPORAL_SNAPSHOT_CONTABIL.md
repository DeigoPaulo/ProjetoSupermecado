# Contrato temporal do snapshot contábil

## Objetivo

O pacote contábil deve informar com precisão qual posição de inventário está sendo
entregue. Uma captura diária feita durante o mês não pode ser apresentada como o
fechamento mensal, e a posição atual não pode ser usada para reconstruir um mês
passado como se fosse histórica.

## Estados da competência

### Competência em andamento

- A data de referência do inventário é o dia corrente.
- Havendo snapshot imutável do dia para todas as filiais do pacote, o CSV usa essa
  posição e a classifica como `SNAPSHOT_IMUTAVEL_PARCIAL_COMPETENCIA`.
- `snapshot_completo` permanece `false`, porque o mês ainda não terminou.
- Sem cobertura completa do dia, o pacote usa a posição operacional atual e informa
  `POSICAO_ATUAL_COMPETENCIA_EM_ANDAMENTO`.

### Competência encerrada

- A data de referência exigida é o último dia da competência.
- O fechamento só é completo quando existe snapshot imutável dessa data para todas
  as filiais incluídas.
- Com cobertura completa, a qualidade é `SNAPSHOT_IMUTAVEL_FECHAMENTO` e
  `snapshot_completo` é `true`.
- Sem cobertura completa, o pacote não fabrica posição retroativa: usa a posição
  atual, marca `POSICAO_ATUAL_NAO_RETROATIVA` e mantém `snapshot_completo=false`.

### Competência futura

Pacotes de uma competência que ainda não começou são rejeitados. Não existe posição
contábil válida para antecipar esse período.

## Manifesto e integridade

O `manifesto.json` do pacote informa:

- `estado_competencia`: `EM_ANDAMENTO` ou `ENCERRADA`;
- `data_referencia`: dia efetivamente procurado para a captura;
- `qualidade_temporal`: natureza da posição entregue;
- `snapshot_completo`: confirmação estrita de fechamento mensal;
- `fechamentos`: hashes das capturas imutáveis efetivamente usadas;
- `alerta`: explicação legível da limitação temporal.

Os hashes continuam permitindo conferir as capturas usadas, inclusive quando a
competência corrente possui uma posição diária imutável ainda parcial.

## Limites

Este contrato corrige a classificação temporal do inventário no pacote do contador.
Ele não implementa o fechamento mensal formal, reabertura de período, CMV ou
homologação contábil. Essas evoluções permanecem em suas frentes próprias.
