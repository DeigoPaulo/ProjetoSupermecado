# Tratamento operacional de validade

O contrato `inventory_expiry_treatment_plan_v1` registra a decisão operacional para lotes vencidos ou com vencimento em até 30 dias, sem baixar estoque automaticamente.

## Opções

- separado para análise;
- devolução planejada;
- promoção planejada, somente antes do vencimento;
- descarte planejado.

Cada alteração preserva responsável, horário, observação e auditoria. Repetir o mesmo estado e observação é idempotente.

## Checklist

- [ ] Conferir fisicamente produto, lote, validade e saldo.
- [ ] Separar mercadoria quando necessário.
- [ ] Registrar orientação objetiva no plano.
- [ ] Nunca promover lote já vencido.
- [ ] Se houver devolução, executar o fluxo documental combinado com o fornecedor.
- [ ] Se houver perda, usar separadamente **Registrar perda**, com autorização do supervisor e quantidade conferida.
- [ ] Confirmar depois que o saldo do lote e o estoque agregado permanecem reconciliados.

Marcar **Descarte planejado** não descarta mercadoria e não constitui baixa. O plano também não altera preço, financeiro, fiscal ou contabilidade.

## Baixa no lote exato

Após registrar **Descarte planejado**, um lote efetivamente vencido pode receber perda por vencimento. A operação exige supervisor, limita a quantidade ao saldo da camada, vincula a perda e a movimentação ao lote escolhido e reduz o estoque agregado na mesma transação. O FEFO não pode consumir outro lote nesse fluxo. Saldo zerado muda o plano para **Baixa concluída**.

## Relatório gerencial de perdas

O contrato `inventory_loss_management_report_v1` amplia o relatório existente, sem criar uma segunda fonte de informação. Ele respeita período e escopo de filial, permite filtrar causa e presença de lote e consolida quantidade e valores estimados por lote, produto e filial. Registros antigos sem lote continuam visíveis como **Sem lote**.

- [x] Mesmos filtros na tela, no CSV e na impressão.
- [x] Lote, validade, causa e motivo preservados nas saídas.
- [x] Totais de quantidade, custo estimado e venda estimada.
- [x] Isolamento entre empresas validado automaticamente.
- [x] Operação somente leitura, sem baixa, financeiro ou emissão fiscal.

A conferência gerencial não substitui a contagem física nem autoriza descarte. Divergências devem retornar ao fluxo auditado de estoque.
## Fila diária de validade

O contrato `inventory_expiry_daily_queue_v1` usa a tela existente de lotes como lista diária de trabalho. Entram apenas lotes com saldo, vencidos ou com vencimento em até 30 dias, que ainda não estejam com baixa concluída.

A prioridade operacional é:

1. vencidos sem tratamento;
2. vencidos com tratamento iniciado;
3. próximos do vencimento sem tratamento;
4. próximos do vencimento com tratamento iniciado.

Dentro de cada grupo, vence primeiro quem possui a validade mais antiga. O filtro de tratamento aceita somente estados conhecidos e todo o conteúdo continua limitado à empresa do usuário.

- [x] Contagem total da fila e dos itens sem tratamento.
- [x] Prazo restante ou dias de atraso visíveis.
- [x] Atalho para planejar o tratamento no lote correto.
- [x] Baixas concluídas, saldos zerados e lotes fora da janela excluídos.
- [x] Nenhuma baixa, perda, promoção, devolução ou obrigação criada pela consulta.

A próxima proteção é registrar a conferência física do lote antes de decisões irreversíveis. Essa conferência deverá preservar o observado e a autoria sem ajustar automaticamente o saldo.
## Conferência física auditável

O contrato `inventory_expiry_physical_check_v1` preserva uma fotografia imutável da conferência do lote. O registro contém os dados identificadores, saldo do sistema, quantidade observada, diferença, custo, tratamento, autoria, horário, observação e SHA-256.

- [x] Confirmação explícita do operador.
- [x] Justificativa obrigatória quando houver divergência.
- [x] Histórico imutável e visível no lote.
- [x] Nenhum ajuste automático de estoque.
- [x] Nenhuma perda, obrigação financeira ou emissão fiscal criada pela conferência.
- [x] Perda por vencimento bloqueada sem conferência válida do mesmo dia.
- [x] Quantidade da perda limitada ao saldo atual e ao total fisicamente observado.
- [x] Nova conferência obrigatória depois de uma baixa parcial.

Uma evidência deixa de ser válida quando muda o dia, o código, a validade, o custo ou o saldo do lote. Divergências devem ser apuradas pelo inventário auditado; a conferência de validade não corrige o estoque por conta própria.
## Estados de conferência na fila

O contrato `inventory_expiry_daily_queue_v2` calcula o estado operacional sem alterar o registro do lote:

- **Pendente ou desatualizada:** não existe conferência de hoje ou a fotografia não corresponde mais ao código, validade, custo ou saldo atual.
- **Divergente:** a fotografia continua atual, mas a quantidade observada difere do sistema.
- **Pronto para decisão:** a fotografia está atual e a quantidade observada coincide com o saldo.

- [x] Contadores e filtros para os três estados.
- [x] Filtro recusando códigos inventados.
- [x] Pendências priorizadas dentro do grupo de vencimento e tratamento.
- [x] Quantidade observada visível para conferências atuais.
- [x] Classificação somente leitura, sem ajustes ou perdas.
- [x] Contadores consolidados em uma única agregação.

Uma conferência pronta não autoriza baixa por si só: descarte planejado, quantidade permitida e autorização do supervisor continuam obrigatórios. Divergências devem seguir para inventário auditado.
## Inventário a partir de divergências

O contrato `inventory_expiry_divergence_inventory_draft_v1` encaminha lotes divergentes selecionados para o inventário já existente. A criação não reaproveita a quantidade observada como contagem final: cada produto permanece pendente até uma contagem física total.

- [x] Seleção limitada a 200 lotes e a uma única filial.
- [x] Escopo e estado divergente recalculados no servidor.
- [x] Produtos repetidos deduplicados em um item de inventário.
- [x] Saldo agregado fotografado no momento da criação.
- [x] Origem técnica visível na lista, no detalhe e no Admin.
- [x] Chave SHA-256 impede rascunhos duplicados para as mesmas evidências.
- [x] Nenhum movimento ou ajuste criado pelo rascunho.
- [x] Aplicação continua exigindo todas as contagens e autorização do supervisor.

Uma nova conferência gera uma nova identidade de origem. O próximo endurecimento deve preservar vínculos navegáveis entre o item do inventário e todas as conferências/lotes que motivaram sua criação.
## Trilha do inventário até a evidência

A migration 0029 materializa o vínculo imutável entre item do inventário, conferência e lote. A navegação funciona nos dois sentidos: o inventário abre cada evidência e a evidência lista os inventários que originou.

- [x] Um vínculo por conferência, sem perder lotes deduplicados no mesmo produto.
- [x] Vínculo imutável e protegido contra exclusão.
- [x] Evidência individual somente leitura e isolada por empresa.
- [x] SHA-256 completo visível para conferência de integridade.
- [x] Admin dos vínculos estritamente somente leitura.
- [x] Repetição idempotente sem duplicar a trilha.
- [x] Aplicação agregada bloqueada para inventários originados por validade.

### Bloqueio de segurança identificado

A aplicação comum reduz excesso rastreado pelas camadas FEFO. Isso é adequado ao inventário agregado comum, mas não prova qual lote apresentou a divergência. Por isso, o rascunho de validade usa agora a reconciliação direta descrita abaixo e não passa pelo aplicador agregado.
## Contagem e reconciliação direta por lote

A migration 0030 cria EscopoLoteInventarioValidade e ContagemLoteInventarioValidade. O primeiro congela todos os lotes positivos dos produtos no momento da abertura; o segundo preserva cada contagem ou recontagem como evento imutável com SHA-256.

- [x] Todos os lotes positivos do produto entram no escopo, inclusive os complementares sem divergência.
- [x] A evidência original continua ligada somente ao lote que realmente motivou o inventário.
- [x] Inclusão manual de produto bloqueada no rascunho originado por validade.
- [x] Cada lote exige confirmação física independente e pode ser recontado sem apagar histórico.
- [x] Nenhuma contagem isolada movimenta estoque.
- [x] Soma das contagens por lote deve coincidir exatamente com a contagem total do produto.
- [x] Saldo agregado deve estar integralmente representado pelas camadas rastreadas.
- [x] Lote novo ou saldo alterado após a contagem bloqueia a aplicação.
- [x] Aplicação exige supervisor e ajusta diretamente cada lote, sem seleção FEFO.
- [x] Movimentos, camadas, agregado, status e auditoria são gravados na mesma transação.
- [x] Qualquer erro reverte toda a operação.
- [x] Admin de escopos e contagens é somente leitura.
- [x] Migração aplicada sem criar escopos ou contagens fictícias.

## Retificação auditável de sobra física

A migration 0031 mantém a quantidade inicial como fato histórico e soma capacidade somente por eventos RetificacaoCapacidadeLoteEstoque autorizados.

- [x] Quantidade inicial nunca reescrita pela reconciliação.
- [x] Capacidade auditada calculada como quantidade inicial mais acréscimos autorizados.
- [x] Contagem acima da capacidade exige justificativa.
- [x] Contagem isolada não amplia capacidade nem movimenta estoque.
- [x] Retificação criada somente dentro da aplicação com supervisor.
- [x] Evento preserva contagem, solicitante, autorizador, valores anterior e novo e SHA-256.
- [x] Ajuste positivo registrado no lote exato e no saldo agregado.
- [x] Falha em outro lote reverte retificação, movimento e saldos.
- [x] Retificação protegida contra alteração e exclusão.
- [x] Admin estritamente somente leitura.
- [x] Migração aplicada sem criar retificações fictícias.

## Cancelamento e expiração segura

A migration 0032 adiciona encerramento auditável e prazo de 24 horas somente aos rascunhos originados por divergência de validade.

- [x] Prazo gravado no momento da abertura.
- [x] Rascunhos antigos recebem chave-base e prazo sem serem expirados pela migração.
- [x] Tela identifica prazo vencido antes da materialização do status.
- [x] Contagem total, contagem por lote e aplicação bloqueadas após o prazo.
- [x] Cancelamento exige justificativa com ao menos 10 caracteres e supervisor.
- [x] Cancelamento não cria movimento, perda, retificação ou ajuste.
- [x] Escopos, contagens, evidências e hashes permanecem consultáveis.
- [x] Rotina de expiração exige confirmação explícita.
- [x] Rotina alcança somente inventários de divergência abertos e vencidos.
- [x] Expiração gera auditoria sistêmica e não altera saldo.
- [x] Inventários manuais e por risco não expiram por essa rotina.
- [x] Nova tentativa permitida depois de cancelamento ou expiração.
- [x] Repetição da tentativa ativa permanece idempotente.
- [x] Admin de inventários e itens estritamente somente leitura.

## Manutenção automática e visibilidade operacional

A migration 0033 e o contrato `inventory_expiry_maintenance_run_v1` incorporam a expiração ao ciclo local diário.

- [x] Execução registra sucesso mesmo quando nenhum rascunho venceu.
- [x] Repetição não duplica encerramento, movimento ou auditoria de inventário.
- [x] Falha reverte a expiração e gera histórico sanitizado separado.
- [x] Histórico preserva identificador, horários, resultado, total encerrado e SHA-256.
- [x] Histórico não armazena caminhos, credenciais ou mensagem bruta da exceção.
- [x] Histórico e Admin são estritamente somente leitura.
- [x] Diagnóstico distingue não executada, em dia, atrasada e falha.
- [x] Lista de inventários mostra o estado e somente os vencidos dentro do escopo do usuário.
- [x] Central do servidor mostra estado global e arquivo do agendador.
- [x] Agendador diário aceita conta SYSTEM, impede sobreposição e limita tempo de execução.
- [x] Script executa somente `expirar_inventarios_validade --confirmar-expiracao`.
- [x] Migration aplicada sem criar histórico artificial nem encerrar rascunho.
- [x] Regressão completa de Estoque aprovada com 113 testes.

## Ensaio ponta a ponta

O contrato `inventory_pilot_end_to_end_evidence_v3` e o roteiro detalhado em `ENSAIO_PILOTO_ESTOQUE.md` fecham o cenário sintético integrado e aplicam a prontidão histórica quando os dados são reais.

- [x] Entrada criou dois lotes e preservou quantidades por camada.
- [x] Venda consumiu somente o lote válido e não criou documento fiscal.
- [x] Lote vencido permaneceu fora do FEFO da venda.
- [x] Perda autorizada atingiu somente o lote vencido conferido.
- [x] Divergência restante originou inventário com escopo completo de lotes.
- [x] Contagem total correspondeu à soma das contagens por lote.
- [x] Aplicação ajustou o lote divergente exato e reconciliou o agregado.
- [x] Fechamento imutável refletiu o saldo final.
- [x] Relatório somente leitura gerou SHA-256 e passou em modo estrito.
- [x] Mistura de registros de filiais diferentes foi recusada.
- [x] Opção identifica honestamente dados sintéticos; o padrão fica reservado ao piloto real.
- [x] Banco temporário destruído sem inserir dados artificiais no banco local.
- [x] Regressão completa de Estoque aprovada com 114 testes.

### Próximo marco externo

Repetir o roteiro com registros reais de uma filial piloto, arquivar o JSON e seu SHA-256 e registrar a conferência operacional. Até isso ser possível, nenhuma integração fiscal ou rede externa deve ser ativada por este fluxo.
## Saldo vendável e quarentena no caixa

O saldo físico continua representando o que existe na loja, mas o caixa utiliza o saldo vendável. Para venda, são elegíveis somente lotes não vencidos nos estados **Não iniciado** ou **Promoção planejada**. Os estados **Separado**, **Devolução planejada**, **Descarte planejado** e **Baixa concluída** funcionam como quarentena operacional.

- [x] Venda FEFO ignora lote vencido ou segregado.
- [x] Produto sem exigência de lote também respeita o saldo rastreado bloqueado.
- [x] Validação e consumo ocorrem na mesma transação.
- [x] Tentativa recusada não deixa venda, item, pagamento ou movimento parcial.
- [x] Perda/descarte direcionado continua podendo alcançar o lote autorizado.
- [x] Tela separa físico, reservado, disponível físico, vendável e bloqueado por lote.
- [x] Consulta da página consolida os lotes sem uma leitura adicional por produto.

Planejar promoção mantém o lote válido liberado para venda; após o vencimento, ele é bloqueado mesmo que o plano ainda esteja como promoção. O bloqueio não baixa saldo, não muda preço e não cria efeito financeiro, fiscal ou contábil.
## Evidência histórica da liberação do lote

A migration 0034 acrescenta snapshots à alocação de cada novo movimento por lote. A venda preserva o código, a validade e o estado de tratamento observados no consumo, além de um SHA-256 calculado com os dados centrais da alocação.

- [x] Cadastro posterior do lote não reescreve o snapshot da venda.
- [x] Snapshot informa se o lote estava não iniciado ou em promoção planejada.
- [x] Validade é comparada com a data do movimento, não com a data do relatório.
- [x] SHA-256 detecta alteração inconsistente dos campos preservados.
- [x] Alocação não pode ser alterada ou excluída pelo modelo e pelo Admin.
- [x] Evidência v2 lista os snapshots e falha em modo estrito quando estiverem ausentes ou inválidos.
- [x] Registros anteriores à migration permanecem identificáveis como legado, sem preenchimento retroativo presumido.

Esse snapshot prova a decisão do sistema no momento do consumo. Ele não substitui documento fiscal, inventário físico ou avaliação tributária.
## Diagnóstico de cobertura dos snapshots

O contrato `inventory_lot_snapshot_coverage_v1` consolida somente as alocações de venda e fica visível na Central do servidor apenas para o Master.

- [x] Todas as filiais aparecem, inclusive as que ainda não possuem vendas por lote.
- [x] Snapshot íntegro exige hash válido, tratamento liberado e validade compatível com a data da venda.
- [x] Ausência de snapshot é classificada como legado, sem preenchimento presumido.
- [x] Hash divergente ou condição comercial inválida é classificada como inconsistência.
- [x] Totais e percentual de cobertura são consolidados por filial e globalmente.
- [x] Processamento usa leitura em lotes e número fixo de consultas.
- [x] Diagnóstico não altera nem corrige qualquer alocação.
- [x] Administradores das empresas não visualizam o painel nem acessam o manifesto técnico.

O estado **Sem vendas por lote** não representa homologação; indica apenas que ainda não existem movimentos no escopo para avaliar.

## Trava de prontidão do piloto real

O contrato `inventory_real_pilot_readiness_v1` usa o diagnóstico da filial como portão do relatório real, sem corrigir ou selecionar registros automaticamente.

- [x] Sem vendas por lote permanece Sem base e não libera aceite.
- [x] Qualquer snapshot legado bloqueia o aceite real como pendência explícita.
- [x] Qualquer snapshot inconsistente bloqueia o aceite real para investigação.
- [x] Somente base existente e integralmente íntegra fica Pronta estruturalmente.
- [x] Evidência v3 inclui estado, critérios e contagens no JSON assinado.
- [x] Modo estrito considera o gate em dados reais.
- [x] Dados sintéticos declaram que o gate não foi aplicado ao aceite.
- [x] Central do servidor explica a trava exclusivamente ao Master.
- [x] Regressão completa de Estoque e Configurações aprovada com 261 testes.

Pronta estruturalmente ainda não significa homologação operacional, fiscal ou contábil. O aceite continua dependendo da execução responsável na filial real e do arquivamento da evidência.

## Prévia dos candidatos do piloto

O contrato `inventory_pilot_candidate_preview_v1` reduz erro na escolha manual dos cinco IDs sem transformar sugestão em aprovação.

- [x] Filtra todos os registros pela mesma filial.
- [x] Lista somente entradas e vendas finalizadas, perdas por vencimento com lote, inventários aplicados e fechamentos.
- [x] Exclui vendas que já possuem documento fiscal.
- [x] Mostra os produtos presentes nas cinco categorias dentro da janela consultada.
- [x] Explicita prontidão histórica, categorias ausentes e falta de produto comum.
- [x] Limite por categoria é validado entre 1 e 100.
- [x] Não combina nem seleciona IDs automaticamente.
- [x] Não altera registros nem acessa serviços externos.
- [x] Modo estrito falha enquanto houver impedimentos.
- [x] Comando de prévia fica visível na Central apenas ao Master.

A prévia é preparatória. O contrato v3 continua revalidando os cinco registros escolhidos e é a fonte do resultado final do ensaio.

## Ficha de execução do piloto

O contrato `inventory_pilot_execution_sheet_v1` formaliza a revisão dos IDs escolhidos pelo Master antes do verificador final.

- [x] Exige os IDs de entrada, venda, perda, inventário e fechamento.
- [x] Confere filial única e exatamente um produto comum.
- [x] Confere os estados operacionais mínimos dos cinco registros.
- [x] Bloqueia venda que já possua documento fiscal.
- [x] Exige perda por vencimento vinculada ao lote.
- [x] Incorpora a trava de prontidão histórica da filial.
- [x] Lista impedimentos sem corrigir dados automaticamente.
- [x] Gera comando final somente com IDs inteiros e SHA-256 da ficha.
- [x] Declara explicitamente que não produz aprovação automática.
- [x] Modo estrito recusa seleção incompatível.
- [x] Central exibe o comando somente no painel Master.

A ficha não substitui o relatório v3, o arquivamento da evidência nem a conferência operacional responsável.
