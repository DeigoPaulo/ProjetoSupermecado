# Conciliação de extratos e adquirentes

## Objetivo

Comparar o livro financeiro do ERP com movimentações externas sem criar, editar ou excluir lançamentos. Todos os arquivos passam pelo contrato `financial_statement_adapter_v1`, que normaliza layouts diferentes antes da deduplicação e da conciliação.

## Layouts nativos

### CSV genérico

O arquivo deve ter até 5 MB, usar ponto e vírgula, vírgula ou tabulação e conter:

```text
data;tipo;valor;descricao;referencia
17/08/2026;credito;150,00;Recebimento cartão;NSU-1001
17/08/2026;debito;12,50;Tarifa bancária;TARIFA-2001
```

- `data`: `DD/MM/AAAA` ou `AAAA-MM-DD`.
- `tipo`: entrada/crédito ou saída/débito.
- `valor`: valor positivo, com vírgula ou ponto decimal.
- `descricao`: histórico apresentado na conferência.
- `referencia`: identificador externo obrigatório.

### OFX bancário

O adaptador OFX aceita arquivos `.ofx` e lê os grupos `STMTTRN`:

- `DTPOSTED`: data;
- `TRNAMT`: valor e natureza pelo sinal;
- `FITID`: referência externa obrigatória;
- `MEMO` ou `NAME`: descrição.

Arquivos OFX sem `FITID`, com valor zero ou movimentações duplicadas são recusados.

## Adaptadores privados

Layouts proprietários são registrados no servidor, nunca enviados pelo navegador:

```env
FINANCEIRO_EXTRATO_ADAPTERS_JSON={"REDE_DEMO":"integracoes.rede.ExtratoRedeAdapter"}
```

A classe deve declarar `nome`, `extensoes` e implementar:

```python
def ler(self, *, conteudo: bytes, arquivo_nome: str) -> list[dict]:
    ...
```

Cada item deve conter `data`, `tipo`, `valor`, `descricao` e `referencia_externa`. Consulte `docs/CONTRATO_ADAPTADOR_EXTRATO.md`.

## Regras de segurança

- O mesmo arquivo, identificado por SHA-256 e conta, não é processado duas vezes.
- O mesmo movimento, considerando conta, referência, natureza e data, não é importado novamente.
- O histórico preserva código, nome e versão do contrato do adaptador utilizado.
- O navegador escolhe somente códigos previamente registrados pelo servidor.
- O matching exige mesma conta, natureza e valor, com janela máxima de três dias.
- NSU, identificador da transação ou autorização têm prioridade.
- Apenas um candidato permite conciliação automática; ambiguidades exigem revisão.
- Importar não cria lançamento financeiro.
- Importações e conciliações geram auditoria e respeitam empresa e filial.

## Agenda e liquidação real

Uma regra ativa por filial e forma eletrônica define prazo, taxa percentual e taxa fixa. Ao confirmar o pagamento, o ERP preserva esses parâmetros e calcula bruto, taxa, líquido previsto e data esperada.

O extrato pode registrar liquidação, antecipação, divergência e chargeback. Cada evento gera movimento imutável. Um depósito agrupado pode ser dividido entre vários recebíveis; ele permanece parcialmente alocado até zerar e não aceita conciliação comum em paralelo.

## Pendências do piloto

1. Obter arquivos reais anonimizados e layouts dos bancos, adquirentes e TEF utilizados.
2. Validar prazos, MDR, taxas e datas com o financeiro da loja.
3. Implementar e homologar um adaptador privado para cada layout proprietário.
4. Automatizar sugestões de lotes agrupados após homologar referências e regras reais.
5. Avaliar API/webhook somente para fornecedores que ofereçam contrato, autenticação e sandbox.
