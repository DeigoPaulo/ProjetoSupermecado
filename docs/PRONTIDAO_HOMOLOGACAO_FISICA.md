# Prontidão para homologação física

Este documento separa a prontidão comprovada em código da validação que depende do
ambiente operacional. Os estados usados são:

- **PRONTO INTERNAMENTE**: contrato, proteção e testes automatizados aprovados.
- **AGUARDANDO HOMOLOGAÇÃO**: depende de execução física, credencial ou serviço externo.
- **HOMOLOGADO**: reservado para evidência real aprovada; nenhum item externo recebe este
  estado neste checklist.

## Pronto internamente

### PDV

- Jornada keyboard-first e mesma rota operacional para Web e Desktop.
- Venda, desconto, quantidade fracionada, cliente e pagamentos.
- Devolução de venda e fechamento protegido de caixa.
- Proteção contra duplo envio e concorrência entre vários PDVs.
- Preparação fiscal idempotente e série fiscal compartilhada por filial.

### Fiscal

- Preparação concorrente de NF-e e NFC-e, numeração, fila e reserva de transmissão.
- Idempotência, consulta após resultado incerto, lease e contingências existentes.
- Contratos atuais dos canais Focus NFe e SEFAZ direta, sem habilitação automática de rede.
- Evidências fiscais append-only e proteção contra transmissão duplicada.

### Financeiro

- Livro financeiro, contas a pagar e receber, conciliação e recebíveis eletrônicos.
- DRE Gerencial 2.0, CMV, fechamento mensal, reabertura, snapshots e SHA econômico.
- Pacote contábil V2 e trilha de auditoria interna.

### Estoque e compras

- Pedido, recebimento, importação de XML, entrada em estoque e custos.
- Conversão explícita da unidade comercial da NF-e para a unidade-base, inclusive códigos
  de embalagem, custo-base, lotes e casamento com pedido.
- Resolução de produto e fator em modo fail-closed, com evidência documental persistida no
  contrato `purchase_xml_unit_conversion_v1`.
- Lotes, validade, perdas, inventário e fechamento contábil do estoque.
- Concorrência protegida na finalização de compras.

### Distribuição e recuperação

- Pacote do servidor proveniente de commit rastreável e inspecionado pelo contrato
  `local_server_package_content_v1`.
- Testes, `.git`, `.env`, bancos, certificados, chaves, logs, backups e mídia são bloqueados
  no artefato; pacote adulterado é recusado.
- Rotinas de backup, validação de pacote e ensaio isolado já existem em código.

## Pendente de teste físico

Todos os itens abaixo permanecem **AGUARDANDO HOMOLOGAÇÃO**.

### PDV e Windows

- Instalação e operação contínua em Windows real, fora da máquina de desenvolvimento.
- Teclado operacional real e ergonomia keyboard-first durante um turno completo.
- Desempenho com uso contínuo, dois ou mais PDVs e troca de operador.
- Reinício do PDV, reinício do servidor, queda e retorno de rede.

### Impressora

- Impressão de cupom, largura, acentuação, corte e múltiplas impressões.
- Impressora desconectada, reconexão e comportamento do spooler Windows.
- Segunda via sem duplicar venda, pagamento ou documento fiscal.

### Gaveta

- Abertura comandada e comportamento por terminal.
- Falha conjunta ou isolada de impressora/gaveta.
- Garantia de que ações indevidas não acionam a gaveta.

### Balança

- Contrato `pdv_scale_v1`, leitura em KG e três casas no peso explícito.
- Peso estável, zero, desconexão, reconexão e peso inválido.
- Produto pesável e bloqueio para produto não pesável.
- O protocolo não deve ser alterado sem o equipamento real.

### TEF e PIN pad

- Débito, crédito e PIX quando suportado pelo provedor.
- Cancelamento, timeout e cancelamento pelo operador.
- Aprovação na processadora com perda de resposta no PDV e posterior reconciliação.
- Proteção contra dupla confirmação e conferência de NSU, autorização e terminal.

### Backup e restauração

- Gerar backup real e restaurar em ambiente limpo.
- Conferir vendas, estoque, financeiro, usuários e configurações após a restauração.
- A mera criação do arquivo não caracteriza homologação de recuperação.

### Instalação limpa

- Windows limpo, servidor local, banco, Desktop PDV e periféricos.
- Instalação sem dependência da máquina ou das ferramentas de desenvolvimento.

### Importação de NF-e e embalagens

- Importar NF-e com embalagem ainda não cadastrada, configurar o fator confirmado pelo operador e concluir a entrada como rascunho; importar a próxima NF-e da mesma embalagem e confirmar o reconhecimento automático.
- Alterar um fator de embalagem de 12 para 15 com confirmação explícita e conferir que entradas e snapshots anteriores preservam 12, enquanto uma nova NF-e usa 15.
- Validar CX, FD e PCT com códigos e fatores distintos, garantindo que uma apresentação adicional não substitui silenciosamente a embalagem padrão.
- Confirmar que análise, vínculo, cadastro de produto e alteração de fator não movimentam estoque nem criam financeiro antes da finalização da entrada.

### NFC-e do recorte real do piloto

- Emitir NFC-e sintética com CFOP 5102 e 5405 no mesmo documento, incluindo fallback da natureza e parametrização explícita por produto/operação.
- Conferir CST 60 como `ICMS60` retido anteriormente, sem cálculo de ICMS-ST próprio, MVA, `vBCST` ou `vST`.
- Conferir IBS/CBS 200/200003 e 200/200014 com redução de 100%, e 200/200034 com redução de 60%, incluindo `gRed`, alíquotas efetivas e totalização.
- Testar GTIN válido e código comercial arbitrário convertido fiscalmente para `SEM GTIN`, sem alterar o cadastro do produto.
- Testar dinheiro+débito, dinheiro+crédito, crédito+débito, três ou mais formas, PIX+dinheiro, vale e convênio.
- Testar dois cartões da mesma modalidade com transações, NSUs e autorizações independentes.
- Confirmar pagamento eletrônico e PIX parciais, atualização de pago/restante e bloqueio de parcela acima do saldo.
- Testar troco simples e misto, conferindo valor aplicado no financeiro, valor informado no XML, `vTroco` e recibo.
- Configurar por filial `tPag=99` com `xPag` para convênio e confirmar que o fallback PIX permanece `17`.
- Repetir os cenários parciais em TEF real, mantendo cada parcela associada à própria transação.

## Pendente de credencial real

Os itens fiscais abaixo permanecem **AGUARDANDO HOMOLOGAÇÃO**:

- CNPJ e inscrição estadual reais da empresa piloto.
- Certificado A1 e senha sob custódia operacional definida.
- CSC e `idCSC` reais para NFC-e.
- Credenciais e liberação comercial do provedor, quando o canal for Focus NFe.
- Endpoints e autorização de uso do ambiente correspondente.

Nenhuma identidade sintética de teste pode receber certificado, CSC, licença ou credencial
operacional.

## Pendente de homologação externa

- Autorização, consulta e cancelamento reais de NF-e/NFC-e na SEFAZ GO.
- Emissão e reconciliação reais pelos canais Focus e SEFAZ direta escolhidos.
- Contingência NFC-e e SVC-RS em cenário autorizado e acompanhado.
- Validação do pacote contábil e dos fechamentos pelo contador e pelo usuário piloto.
- Aceite operacional da instalação, restauração e periféricos pelo responsável do cliente.

A preparação de devolução ao fornecedor continua sem emissão e sem transmissão. A
**NT 2026.009 já foi identificada; há impacto futuro na emissão de devolução NF-e. Sem
alteração operacional necessária enquanto a emissão de devolução permanece bloqueada.**

## Opcional ou pós-piloto

- Automatização periódica da Distribuição DF-e/NSU, que já possui fluxo manual implementado.
- Evoluções de conveniência que não removam um bloqueador de segurança ou operação do piloto.
- Ampliação fiscal além dos contratos já implementados e homologados para o recorte inicial.

## Plano de longa duração

Executar um ensaio mínimo de oito horas no ambiente piloto:

1. Operar vendas repetidas em dois ou mais PDVs.
2. Alternar operadores, descontos, quantidades fracionadas e meios de pagamento.
3. Reiniciar um PDV e depois o servidor, verificando retomada e idempotência.
4. Interromper e restaurar a rede, reconciliando pagamentos e documentos incertos.
5. Validar impressora, gaveta, balança e PIN pad durante todo o período.
6. Encerrar e conferir cada caixa ao fim do turno.
7. Gerar backup, restaurar em ambiente limpo e conferir os módulos críticos.

## Critério de liberação do piloto

### Bloqueadores de piloto

- Migration quebrada ou instalação limpa não reproduzível.
- Perda ou duplicação de venda, estoque inconsistente ou fechamento de caixa incorreto.
- Dupla emissão, numeração fiscal duplicada ou resultado incerto retransmitido sem consulta.
- Falha em pagamento real, reconciliação ou periférico necessário à operação escolhida.
- Backup sem restauração real aprovada.
- Credencial fiscal ausente quando emissão fiscal for requisito do piloto.

### Importante, mas não bloqueador

- Automação de tarefa que possua procedimento manual seguro e compatível com o piloto.
- Periférico opcional não contratado para a loja piloto.
- Ajustes de ergonomia sem perda de função, integridade ou segurança.

### Pós-piloto

- Scheduler da Distribuição DF-e/NSU, salvo exigência comercial explícita.
- Expansões tributárias e operacionais fora do recorte contratado.
- Otimizações e integrações não necessárias ao primeiro ambiente físico.

## Evidência exigida

Cada homologação física ou externa deve registrar data, ambiente, filial, terminal,
responsável, cenário, resultado e referência da evidência, sem expor senha, token, XML
fiscal completo ou material privado. Até essa execução, o estado correto é
**AGUARDANDO HOMOLOGAÇÃO**.
