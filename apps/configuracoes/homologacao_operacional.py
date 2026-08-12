ROTEIRO_HOMOLOGACAO_OPERACIONAL = (
    ("cadastro", "Cadastros e permissões", "Validar empresa, filial, usuário administrador, supervisor, operador e contador com escopo correto."),
    ("compra", "Compra e entrada", "Registrar entrada, conferir fornecedor, custo, lote quando aplicável e saldo de estoque."),
    ("pdv", "Venda no PDV", "Abrir caixa, vender por código de barras, testar cliente avulso e conferir baixa de estoque."),
    ("pagamento", "Pagamentos e caixa", "Testar dinheiro, PIX, cartão/TEF simulado, pagamento dividido, sangria e fechamento."),
    ("impressao", "Impressões", "Validar cupom não fiscal, pedido de entrega, etiqueta e configuração da impressora correta."),
    ("financeiro", "Financeiro e contabilidade", "Conferir lançamentos, resultado, relatório de caixa por operador e pacote contábil mensal."),
    ("fiscal", "Fiscal em homologação", "Confirmar séries, alíquotas, XML e emissão simulada. Não habilitar produção sem credenciais e aceite fiscal."),
    ("backup", "Segurança e contingência", "Gerar backup, testar restauração em ambiente separado e confirmar acesso restrito por empresa."),
)