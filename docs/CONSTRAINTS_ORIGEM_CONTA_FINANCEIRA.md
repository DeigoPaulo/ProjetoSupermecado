# Integridade da origem das contas financeiras

As contas manuais continuam válidas sem venda ou entrada de compra. Quando existe
uma origem comercial, o banco passa a proteger as invariantes mínimas que os
serviços já esperam.

## Regras de banco

- uma conta não pode apontar simultaneamente para venda e entrada de compra;
- conta de venda é sempre `RECEBER` e existe no máximo uma por venda;
- conta de compra é sempre `PAGAR`;
- conta com duplicata precisa apontar também para a entrada de compra;
- sem duplicata, existe no máximo uma conta por entrada;
- com duplicatas, várias parcelas da mesma entrada permanecem permitidas, e a
  relação um-para-um da duplicata impede reaproveitar a mesma parcela.

O modelo acrescenta validações que não podem ser expressas por `CHECK` sem consultar
outra tabela: filial da conta coerente com a origem e duplicata pertencente à mesma
entrada informada. Os serviços continuam responsáveis por chamar os fluxos de domínio;
as constraints são a última defesa contra gravações concorrentes ou fora desses fluxos.

## Aplicação da migration

A migration `financeiro.0025` executa primeiro uma auditoria não destrutiva. Se
encontrar registros incompatíveis, interrompe a aplicação e lista até 50 IDs ou
grupos por tipo de problema. A correção deve ser analisada manualmente; a migration
não escolhe origem, tipo nem parcela e não exclui histórico.

O banco local de desenvolvimento examinado estava anterior à migration
`financeiro.0024`, por isso não foi alterado nem usado como prova de ausência de
legado. A validação estrutural foi feita em bancos descartáveis criados pela suíte.

## Limite e próximo passo

Esta entrega não redefine competência ou fechamento contábil. A regressão revelou
um contrato temporal já pendente no roadmap: o pacote do mês corrente consulta o
último dia da competência, enquanto o snapshot imutável só pode ser capturado no dia
atual. Esse comportamento deve ser resolvido na frente seguinte sem fabricar snapshot
retroativo.
