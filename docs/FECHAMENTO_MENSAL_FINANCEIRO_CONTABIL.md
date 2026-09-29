# Fechamento mensal financeiro-contábil

## Escopo

O contrato `financial_monthly_close_v1` registra o fechamento gerencial interno de uma empresa e competência mensal. A competência usa sempre o primeiro dia do mês, enquanto `data_inicio`, `data_fim` e `fechado_em` permanecem campos distintos. O fechamento abrange todas as filiais ativas da empresa; não existe fechamento parcial por filial.

O processo não substitui fechamento contábil ou fiscal oficial, SPED, ECD, ECF, homologação externa nem aceite do contador. `AceiteAmostraContabil` continua sendo um conceito independente.

## Estado e versões

`CompetenciaFinanceiroContabil` mantém o estado atual `ABERTA` ou `FECHADA` e a referência do snapshot vigente. A combinação empresa e competência é única e a competência não pode ser excluída.

Cada fechamento cria um novo `FechamentoMensalSnapshot`. A versão começa em 1 e nunca é reutilizada. Após reabertura, o snapshot anterior permanece imutável e o próximo fechamento cria a versão seguinte. `EventoCompetenciaFinanceiroContabil` registra fechamentos e reaberturas com usuário, horário, motivo e IP quando disponível.

Snapshots e eventos rejeitam `update`, `delete` e novo `save` após a criação. A concorrência é serializada com transação, bloqueio da empresa e da competência, além da restrição única competência + versão.

## Readiness

`diagnosticar_fechamento_mensal(empresa, competencia)` separa `bloqueios` de `alertas` e retorna os dados estruturados que formarão o snapshot.

Bloqueiam o fechamento:

- competência futura, ainda em andamento ou já fechada;
- empresa sem filial ativa;
- ausência de `FechamentoEstoqueContabil` exatamente no último dia para qualquer filial ativa;
- SHA-256 inválido em fechamento de estoque obrigatório;
- CMV incompleto;
- reconciliação de CMV `DIVERGENTE` ou `INCOMPLETO`;
- item de extrato `AMBIGUO` ou `PARCIAL` dentro da competência.

Geram alerta e `com_ressalvas=true`, sem bloquear isoladamente:

- entrada ou saída sem classificação DRE;
- tributos sobre resultado não apurados;
- lançamentos bancários pendentes de conciliação;
- recebíveis divergentes cuja diferença realizada permanece exposta;
- homologação fiscal externa pendente.

Recebíveis pendentes com liquidação prevista em mês posterior e contas abertas no fim do mês são posições normais, não erros.

## Conteúdo congelado

O snapshot guarda separadamente:

- DRE `financial_dre_v2` e reconciliação `financial_cmv_reconciliation_v1`;
- resultado financeiro, transferências, estornos, conciliação e saldos históricos das contas de movimento;
- contas a pagar e receber abertas, vencidas e realizadas no período;
- recebíveis pendentes, liquidados, antecipados, divergentes, chargebacks, bruto, previsto, realizado, custos e divergências;
- referências e hashes dos fechamentos imutáveis de estoque;
- resumo fiscal somente leitura, referências mínimas e hash agregado, sem copiar XML;
- bloqueios, alertas e limitações conhecidas.

Saldos de caixa, banco, PIX e outras contas são calculados por `saldo_inicial + entradas até o fim - saídas até o fim`. Movimentos posteriores não alteram a posição congelada.

Para contas financeiras, a posição usa criação, vencimento e data de pagamento. Conta paga depois do encerramento continua aberta no snapshot anterior. Como o cancelamento de conta ainda não possui timestamp estruturado, contas atualmente canceladas não são reconstruídas retroativamente e essa limitação fica registrada.

## Hash

O SHA-256 protege o conteúdo econômico serializado em JSON canônico com `sort_keys=True`, separadores compactos, datas ISO e `Decimal` como string. O usuário, horário e observação operacional não alteram o hash econômico. Qualquer alteração de DRE, CMV, saldo, conta, recebível, fiscal, diagnóstico ou referência de estoque produz outro hash.

## DRE congelada

Quando a consulta em `/financeiro/dre/`, `/financeiro/dre.json` ou `/financeiro/dre/exportar.csv` corresponde exatamente a uma competência fechada e ao escopo consolidado de todas as filiais ativas, a fonte é `SNAPSHOT_FECHADO`. Tela e exportações informam versão, SHA-256 e fechamento. Períodos arbitrários ou escopos parciais continuam com fonte `DINAMICA`.

O snapshot vigente é a verdade histórica oficial interna. Alterações posteriores de categoria, custo ou configuração não recalculam silenciosamente uma DRE fechada.

## Reabertura e trava retroativa

A reabertura exige perfil Master, Administração ou Contabilidade da empresa, confirmação explícita e motivo de pelo menos 15 caracteres. Ela muda a competência para `ABERTA`, remove somente a indicação de vigência e preserva todas as versões anteriores.

`validar_competencia_aberta` protege lançamentos, transferências, estornos e baixas financeiras com data explícita. A data econômica do novo evento decide a competência: uma devolução, baixa ou estorno realmente ocorrido em outubro não é bloqueado porque o objeto original nasceu em setembro.

## Pacote contábil V2

Para competência fechada e escopo consolidado, `accounting_monthly_package_v2` inclui:

- `financeiro/fechamento-mensal.json`;
- `financeiro/dre-gerencial-v2.json`, copiado exatamente de `dre_snapshot`;
- metadados `fechamento_mensal` no manifesto, com versão, SHA-256 e ressalvas.

Competência aberta mantém o comportamento anterior e declara `fechamento_mensal=false`. O validador `accounting_monthly_sample_validation_v1` preserva a compatibilidade com pacotes históricos, mas, quando o manifesto declara fechamento, exige os dois arquivos e confere contrato, versão, SHA e correspondência da DRE.

## Limitações

- Não são fabricados fechamentos para competências anteriores ao Ciclo 188.
- Não há combinação automática de vários snapshots para períodos arbitrários.
- A posição fiscal é gerencial e somente leitura; não declara homologação externa.
- O timestamp de cancelamento de conta financeira ainda não existe e a limitação fica explícita.
- Fechamentos de estoque devem existir na data exata; a posição atual não pode substituir o snapshot mensal formal.
