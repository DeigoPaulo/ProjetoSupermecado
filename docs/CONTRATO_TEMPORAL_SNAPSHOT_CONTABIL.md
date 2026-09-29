# Contrato temporal do snapshot contábil

## Objetivo

O pacote contábil deve informar com precisão qual posição de inventário está sendo
entregue. Uma captura diária feita durante o mês não pode ser apresentada como o
fechamento mensal, e a posição atual não pode ser usada para reconstruir um mês
passado como se fosse histórica.

Desde o Ciclo 188 existem dois níveis distintos de evidência:

- `FechamentoEstoqueContabil`: snapshot diário imutável por filial, usado como fonte da posição de estoque;
- `financial_monthly_close_v1`: fechamento mensal formal por empresa, que referencia os snapshots diários exatos do último dia e congela também DRE, financeiro, contas, recebíveis, fiscal e diagnósticos.

O snapshot diário, isoladamente, não fecha a competência. O fechamento mensal só existe após ação administrativa explícita e versionada, a partir do dia seguinte ao encerramento do mês.

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

No pacote de uma competência formalmente fechada, o escopo de filiais vem do
`filiais_snapshot`, não do cadastro ativo atual. O arquivo de fechamento também
carrega o conteúdo econômico canônico completo; seu SHA-256 é recalculado pelo
validador e a DRE protegida deve ser idêntica ao arquivo de DRE congelada.

## Limites

Este contrato continua definindo a qualidade temporal do inventário no pacote do contador. O fechamento mensal formal, sua reabertura, DRE congelada e versionamento são definidos em `docs/FECHAMENTO_MENSAL_FINANCEIRO_CONTABIL.md`. A homologação contábil e fiscal externa permanece fora de ambos os contratos.
