# Roadmap de evolucao pos-piloto

## Controle de escopo e retomada — 14/09/2026

A frente atual pertence à transição do CNPJ alfanumérico planejada no ciclo 103, dentro da prioridade fiscal. Os registros de ciclos abaixo são histórico de execução, não uma lista de funcionalidades operacionais concluídas.

- [x] Normalizador, auditoria local, leitura comparativa e preparação pura de escrita implementados e testados.
- [x] Desdobramentos técnicos acrescentados nos ciclos 109–113: catálogo de teste, adoção, controle de importações, regressão e exclusão do pacote. Estes trabalhos apoiam a frente original, mas não concluem a integração cadastral.
- [x] Fase 4 original: escrita canônica por fronteira concluída nos ciclos 117 e 119 para Empresa, Filial, Cliente PJ e Fornecedor PJ; a interface e o lookup foram fechados no ciclo 120. Os 18 bloqueios legados permanecem separados para correção manual antes de constraints ou migração de conteúdo.
- [x] Próxima entrega delimitada da fase 4 concluída no ciclo 115: comparação isolada com os formulários de Empresa/Filial, divergências e colisões comprovadas e pontos de integração identificados, sem persistência.
- [x] Após essa comparação, atualizar a pendência de integração da própria fase 4, identificando o que depende de correção de dados e o que pode ser validado localmente. A classificação foi concluída no ciclo 116, sem declarar a fase completa.
- [x] Fase 5 interna: chave/XML/QR Code/DANFE HTML e consumidores internos compatibilizados
  nos ciclos 121–126, mantendo o Code 128 RAW/ESC-POS como risco de homologação de hardware.
- [ ] Fase 6 original: Focus, SEFAZ direta e DF-e continuam separados e pendentes de
  compatibilização/homologação própria.

Novas tarefas devem indicar o item original que atendem, a lacuna concreta e o critério de conclusão antes da implementação. Melhorias opcionais vão para pendências futuras e não substituem automaticamente a próxima entrega. Contagem de testes e quantidade de ciclos não medem conclusão funcional.

## Frente prioritária — pré-homologação SEFAZ-GO

Registro documental de preparação/prontidão em 17/09/2026, baseado no HEAD
b7cf2b060d9b7f0aa6e6783cc635613d8245a5bb (ciclo 126). A auditoria externa usou o
HEAD anterior 2aba217; os achados já corrigidos foram atualizados sem reabrir o ciclo.

A estrutura segue NF-e/NFC-e 4.00, perfil GO/cUF 52 e ambientes separados.
Compatibilidade offline, pendência tributária, dependência externa e homologação real
são estados distintos. Esta frente não constitui certificação ou aceite da SEFAZ.

Matriz, evidências locais e critérios:
[AUDITORIA_PRE_HOMOLOGACAO_SEFAZ_GO.md](AUDITORIA_PRE_HOMOLOGACAO_SEFAZ_GO.md).

- [x] Incorporar o histórico offline do ciclo 126: DV do emitente, destinatário CNPJ alfa,
  snapshot Cliente/Pedido, contingência alfa e texto/QR do Desktop.
- [x] P1: revisar normativamente consumidor PJ/modelo documental, cobertura de obrigatoriedade
  cBenef GO e readiness/CSC diante do QR Code v3; sem presumir regra legal a partir do código.
- [ ] Homologar hardware e definir Code 128 RAW/ESC-POS; HTML já possui Code 128 C/A.
- [ ] Fase 6: compatibilizar SEFAZ direta, inutilização, eventos e DF-e; homologar Focus separadamente.
- [ ] Preparar XSD oficial aplicável: origem, versão, SHA-256, compilação offline, instalação
  controlada, XMLs do ERP e versão congelada para o piloto.
- [ ] Confirmar CRT e cronograma IBS/CBS aplicável; fechar grupos, cálculos, testes e homologação.
- [ ] Confirmar CNPJ, IE, CNAE, A1, credenciamento, configuração e produtos reais do piloto.
- [ ] Classificar cada SKU/operação como SUPORTADO ou BLOQUEADO; impedir cenário desconhecido.
- [ ] Executar bateria real por canal/filial, incluindo autorização, consulta, rejeição/correção,
  cancelamento, inutilização, contingência/SVC, cadastro, eventos/DF-e, QR/DANFE,
  reimpressão e armazenamento XML/protocolo.

Próximo ciclo técnico preservado: identidade CNPJ alfa fora do fiscal — sincronização,
eventos, resolução Empresa/Filial, licenciamento, challenge/release offline e provedor externo.
Depois: frente tributária GO → Fase 6 → preparação de homologação → homologação real.
Este registro documental não consome a numeração do próximo ciclo técnico.

Critério de pronto: XML gerado, schema compilado, testes aprovados, adaptador carregado ou
endpoint cadastrado não bastam para declarar homologação GO. Exigir evidência real do
ambiente de homologação para o escopo aceito. As regras vigentes serão verificadas em fontes
oficiais no ciclo correspondente; nenhuma consulta externa foi realizada neste registro.

Validação deste registro: conferência local de código/histórico e revisão do diff; apenas
documentação alterada, sem testes funcionais novos, migration, transmissão ou push.

## Frente prioritária — integridade crítica pré-piloto

Uma auditoria independente realizada após o ciclo 115 confirmou riscos de integridade
transacional e de invariantes de domínio que devem ser resolvidos antes do piloto. Nenhum
item desta frente pode ser marcado concluído apenas por inspeção: são obrigatórios código e
teste compatíveis com o mecanismo de banco que fornece a proteção.

P1:

- [x] concorrência na finalização da EntradaCompra;
- [x] unicidade lógica do DocumentoFiscal por venda/pedido;
- [x] segregação de série fiscal por ambiente;
- [x] semântica segura da baixa financeira;
- [x] reserva/idempotência da transmissão fiscal;
- [x] concorrência entre fechamento e operações do caixa;
- [x] testes concorrentes reais em PostgreSQL.

P2:

- [x] parcelas/duplicatas da NF-e recebida, preservadas na entrada e vinculadas às contas a pagar;
- [x] criptografia do CSC;
- [x] constraints de contas originadas por compra/venda;
- [x] contrato temporal do snapshot contábil;
- [x] CI inicial com PostgreSQL.
- [x] defesa em profundidade da origem do DocumentoFiscal: garantir no banco exatamente
  uma origem comercial permitida por fluxo, impedindo simultaneamente venda + pedido e a
  ausência de ambas, após revisar os fluxos que possam criar documentos sem origem.

O ciclo 115 permanece sendo o ponto exato de retomada da frente CNPJ. O ciclo 116 não será
iniciado até esta frente P1 atingir estado seguro. Depois da frente de integridade, o trabalho
retornará exatamente à fase 4 do CNPJ, sem antecipar as fases seguintes.

### P1.1 concluído — 15/09/2026

A causa foi confirmada: `finalizar_entrada_compra` validava o estado e carregava os itens antes
da transação que aplicava os efeitos. A implementação agora abre a transação antes da leitura
decisória, bloqueia a `EntradaCompra` com `select_for_update`, revalida o estado após o lock e
carrega os itens somente então. As validações de fornecedor, conferência, itens, estoque, lote,
custo, financeiro, pedido de origem e auditoria foram preservadas.

- Estado: concluído com prova concorrente PostgreSQL.
- Arquivos: `apps/compras/services.py`, `apps/compras/test_concorrencia_finalizacao.py`,
  `config/settings.py`, `scripts/test_concorrencia_postgresql.ps1` e
  `docs/TESTES_CONCORRENCIA_POSTGRESQL.md`.
- Migrações: nenhuma.
- SQLite: 70 testes de compras, fechamento/fluxo de estoque e efeitos financeiros da compra;
  resultado `OK`, com um teste ignorado por exigir PostgreSQL.
- PostgreSQL: um teste em PostgreSQL 18 real, com conta e banco descartáveis, duas conexões
  simultâneas e resultado `OK`; exatamente uma finalização foi aceita e a outra rejeitada, sem
  duplicação de estoque, movimentação ou conta financeira. Conta, banco e logs temporários
  foram removidos após a validação.
- Riscos residuais: a defesa adicional por constraint de conta/movimento permanece no backlog
  P2; ela não foi necessária para corrigir a exclusão mútua da finalização.
- Próximo passo exato: P1.2, unicidade lógica do `DocumentoFiscal` por venda/pedido.

### P1.2 concluído — 15/09/2026

A causa foi confirmada: os serviços protegiam a numeração da série, mas verificavam a
existência de documento antes de bloquear a venda ou o pedido. Agora cada preparação
recarrega e bloqueia sua origem com `select_for_update` antes da verificação, mantendo o
lock até a criação do documento, a gravação do XML, o avanço da série e a auditoria.

A migration fiscal 0051 adiciona uma segunda camada no banco: existe no máximo um
`DocumentoFiscal` não cancelado por venda e no máximo um por pedido online. Documentos
cancelados continuam no histórico e permitem uma nova preparação, como já previa o fluxo.
Antes de criar as constraints, a migration procura duplicidades legadas e interrompe com os
identificadores encontrados, sem escolher ou apagar registros automaticamente.

- Estado: concluído com trava transacional, constraints e prova concorrente PostgreSQL.
- Arquivos: `apps/fiscal/services.py`, `apps/fiscal/models.py`,
  `apps/fiscal/migrations/0051_documentofiscal_unicidade_origem.py`,
  `apps/fiscal/test_concorrencia_preparacao.py`,
  `scripts/test_concorrencia_postgresql.ps1` e
  `docs/TESTES_CONCORRENCIA_POSTGRESQL.md`.
- Migrações: `fiscal.0051`, com pré-verificação não destrutiva de dados existentes.
- SQLite: regressão de 145 testes dos fluxos fiscais, pedidos online e novas constraints;
  resultado `OK`. Os dois testes concorrentes permanecem explicitamente ignorados nesse
  banco, pois SQLite não fornece a semântica de lock exigida.
- PostgreSQL: dois testes em PostgreSQL 18 real, cada um com duas conexões simultâneas;
  resultado `OK`. Uma única NFC-e foi preparada para a venda e uma única NF-e para o pedido,
  com a segunda requisição bloqueada e cada série avançando apenas uma vez.
- Higiene: contas, bancos e logs temporários usados na prova foram removidos; nenhuma
  credencial foi gravada no projeto.
- Riscos residuais: caminhos que escrevam `DocumentoFiscal` diretamente continuam
  protegidos pela constraint, mas a idempotência completa da fila, retransmissão e consulta
  permanece no item P1 específico de reserva/idempotência da transmissão fiscal.
- Próximo passo exato: P1.3, segregação de série fiscal por ambiente.

### P1.3 concluído — 15/09/2026

A série fiscal agora pertence explicitamente a um ambiente. A chave lógica passou a ser
filial, tipo de documento, ambiente e série; a unicidade da numeração do
`DocumentoFiscal` também inclui o ambiente, permitindo que homologação e produção tenham
sequências juridicamente separadas. Preparação de NFC-e, preparação de NF-e, prontidão,
listas operacionais e inutilização consultam somente a série do ambiente ativo na
configuração da filial. A ausência dessa série bloqueia o fluxo antes de reservar número.

A migration fiscal 0052 classifica cada série legada pelo ambiente atual da configuração
fiscal da filial. Quando não existe configuração, adota homologação como destino seguro.
Ela não copia, reinicia nem move números automaticamente quando o ambiente for alterado
depois da migração; a série correspondente deve ser cadastrada conscientemente.

- Estado: concluído com segregação no modelo, serviços, tela, prontidão e inutilização.
- Arquivos principais: `apps/fiscal/models.py`, `apps/fiscal/services.py`,
  `apps/fiscal/forms.py`, `apps/fiscal/views.py`, `apps/fiscal/readiness.py`,
  `apps/fiscal/admin.py`, `templates/fiscal/documentos.html`,
  `apps/fiscal/migrations/0052_seriefiscal_ambiente.py` e
  `apps/fiscal/test_serie_ambiente.py`.
- Migrações: `fiscal.0052`, com classificação de dados legados e alteração das chaves
  únicas de série e numeração fiscal.
- Regressão: 120 testes do núcleo fiscal após os ajustes, incluindo emissão, fila,
  cancelamento, contingência, inutilização e os seis novos cenários; resultado `OK`. Os
  demais testes de pedidos, vendas e PDV do lote ampliado não apresentaram falhas ligadas
  à mudança.
- PostgreSQL: os seis cenários P1.3 passaram em PostgreSQL 18 real com uma base descartável
  pertencente a uma conta sem `CREATEDB`; mesma série e número coexistiram entre ambientes,
  duplicidade dentro do mesmo ambiente foi recusada e cada emissão consumiu somente sua
  sequência. Conta, base e logs temporários foram removidos.
- Segurança operacional: mudar a configuração da filial de homologação para produção não
  reaproveita a série anterior; sem série de produção ativa, a emissão e a inutilização
  falham fechadas.
- Próximo passo exato: P1.4, semântica segura da baixa financeira.

### P1.4 concluído — 15/09/2026

O modelo atual de `ContaFinanceira` preserva somente uma data e um valor de pagamento, sem
histórico de várias baixas. Para não declarar uma conta quitada após pagamento parcial nem
perder a composição financeira, a semântica segura adotada nesta etapa é baixa exclusivamente
integral. Pagamentos parciais ou acima do total são recusados até existir um modelo próprio de
parcelas/baixas, acréscimos, descontos e estornos.

A tela informa o valor integral exigido e valida a entrada antes do envio. O serviço permanece
como autoridade mesmo quando chamado fora da tela: bloqueia a conta com `select_for_update`,
revalida o estado, exige igualdade exata entre valor pago e valor da conta e valida a filial da
conta de movimento antes de qualquer mutação. A constraint de banco admite somente dois
estados coerentes: conta paga com data e valor integral, ou conta aberta/cancelada sem dados de
pagamento. A migration interrompe a aplicação se encontrar legado incompatível e não corrige
valores financeiros automaticamente.

- Estado: concluído com validação de interface, serviço transacional e constraint de banco.
- Arquivos principais: `apps/financeiro/models.py`, `apps/financeiro/forms.py`,
  `apps/financeiro/services.py`, `apps/financeiro/views.py`,
  `templates/financeiro/baixa_form.html`,
  `apps/financeiro/migrations/0023_conta_baixa_integral_coerente.py` e
  `apps/financeiro/test_baixa_integral.py`.
- Migração: `financeiro.0023`, aplicada na base local após pré-verificação; a base existente não
  continha conta incompatível e nenhum valor foi alterado automaticamente.
- Testes focados: seis cenários passaram em SQLite e em PostgreSQL 18 real, incluindo quitação
  integral, recusa de valor parcial e excedente, ausência de efeitos colaterais, mensagem do
  formulário e bloqueio de gravações inválidas diretamente no banco.
- PostgreSQL: a prova usou conta sem `CREATEDB` e base descartável; ambas foram removidas após
  o resultado `OK`, sem credencial gravada no projeto.
- Regressão financeira: 66 de 67 testes passaram. O teste histórico do pacote contábil falha
  isoladamente fora do último dia do mês porque compara um fechamento capturado no dia atual
  com o último dia da competência. A falha não percorre a baixa financeira e corresponde à
  pendência P2 já registrada como contrato temporal do snapshot contábil; ela não foi mascarada
  nem corrigida dentro deste item.
- Próximo passo exato: P1.5, reserva/idempotência da transmissão fiscal.

### P1.5 concluído — 16/09/2026

A fila já possuía um lease baseado apenas em horário, mas o serviço de transmissão não
identificava nem validava o proprietário da reserva. Assim, uma chamada manual podia concorrer
com a fila e um processo antigo podia liberar ou sobrescrever o estado de outro após a expiração
do lease. Também foi confirmado que a chave genérica de idempotência do contrato não é usada
pelos adaptadores atuais: a Focus deduplica pela referência determinística do documento e a
SEFAZ direta trabalha pela chave fiscal. A proteção local, portanto, precisava ser autoritativa.

Cada reserva agora recebe um UUID persistido junto com o horário. A fila entrega esse token aos
serviços de transmissão, simulação e consulta; somente o proprietário pode aplicar o retorno,
reagendar ou liberar a reserva. Chamadas manuais adquirem a mesma reserva sob lock, e são
bloqueadas quando outro processo já controla o documento. Uma constraint exige que horário e
token existam ou sejam nulos sempre em conjunto.

Antes da chamada externa, o documento passa de forma durável para reconciliação obrigatória.
Se houver timeout, queda do processo ou retorno desconhecido depois do início do envio, a fila
consulta a SEFAZ/Focus em vez de retransmitir. Uma resposta isolada de "não localizado" não
libera novo envio: são exigidas pelo menos duas confirmações consecutivas, reduzindo o risco de
duplicidade durante propagação do autorizador. Falhas comprovadamente anteriores ao envio
continuam elegíveis a nova tentativa controlada.

- Estado: concluído com reserva identificada, propriedade condicional e reconciliação de envio
  incerto.
- Arquivos principais: `apps/fiscal/models.py`, `apps/fiscal/services.py`,
  `apps/fiscal/fila.py`, `apps/fiscal/migrations/0053_documentofiscal_reserva_token.py`,
  `apps/fiscal/test_reserva_transmissao.py` e `apps/fiscal/tests.py`.
- Migração: `fiscal.0053`, com pré-verificação não destrutiva e constraint de coerência entre
  horário e token. A base local possuía zero reservas legadas e a migração foi aplicada sem
  corrigir ou apagar documentos.
- Regressão: 170 testes do núcleo fiscal, Focus, SEFAZ direta, compatibilidade e reserva passaram
  em SQLite; o único cenário ignorado exige concorrência real PostgreSQL.
- PostgreSQL: os cinco cenários P1.5 passaram em PostgreSQL 18, inclusive duas transmissões
  simultâneas contra um adaptador bloqueado. Houve exatamente uma chamada externa, uma
  autorização e uma tentativa; a concorrente foi recusada e a reserva terminou limpa.
- Segurança operacional: nenhuma chamada externa foi realizada, nenhuma flag de rede ou
  produção foi ativada e nenhuma credencial foi gravada no projeto.
- Próximo passo exato: P1.6, concorrência entre fechamento e operações do caixa.

### P1.6 concluído — 16/09/2026

O fechamento, a venda, a sangria e o suprimento consultavam o estado do caixa sem compartilhar
uma exclusão mútua. Uma requisição podia validar o caixa como aberto, perder a corrida para o
fechamento e ainda gravar estoque ou movimento financeiro depois dele. A correção estabelece a
linha de `Caixa` como autoridade transacional: todas essas operações bloqueiam a mesma linha com
`select_for_update` e revalidam o estado somente depois de obter o lock.

Sangria, suprimento e fechamento foram concentrados em serviços atômicos. As telas continuam
responsáveis por permissão, formulário, PIN do supervisor, mensagens e gaveta, mas não gravam
mais movimento de caixa diretamente. A finalização da venda adquire o lock antes de criar a
venda, movimentar estoque, registrar pagamentos, financeiro ou documento fiscal. Assim, se a
operação obtém o lock primeiro ela termina e o fechamento a inclui; se o fechamento obtém o lock
primeiro, a operação é recusada sem efeito parcial.

- Estado: concluído com autoridade transacional única e prova concorrente PostgreSQL.
- Arquivos principais: `apps/pdv/services_caixa.py`, `apps/pdv/views.py`,
  `apps/vendas/services.py` e `apps/pdv/test_concorrencia_caixa.py`.
- Migrações: nenhuma.
- Regressão: 94 testes de PDV, caixa e vendas passaram em SQLite; os três cenários ignorados
  nesse banco exigem a semântica real de `select_for_update` e foram executados separadamente.
- PostgreSQL: cinco testes passaram em PostgreSQL 18 real, com três provas simultâneas. Quando
  o fechamento venceu, venda, sangria e suprimento foram recusados sem venda, estoque ou
  lançamento parcial. Quando o suprimento venceu, ele e seu lançamento terminaram antes de o
  fechamento prosseguir. A conta usada não possuía privilégios administrativos.
- Cobertura P1: as provas concorrentes reais agora cobrem finalização de compra, preparação
  fiscal por venda/pedido, reserva de transmissão e fechamento/operações do caixa. O item
  agregador de testes concorrentes PostgreSQL está concluído, encerrando a frente P1.
- Próximo passo exato: retomar a fase 4 do CNPJ no ponto registrado após o ciclo 115, separando
  as divergências que exigem correção de dados das que podem avançar para validação local antes
  de integrar a escrita canônica aos formulários reais.

## Ponto de retomada — ciclo 115, 14/09/2026

Concluída a comparação delimitada da fase 4 entre os formulários atuais de Empresa/Filial e o portão canônico. O observador usa os próprios `EmpresaForm` e `FilialForm`, trabalha sobre cópia da instância em atualização, consulta colisões apenas com `SELECT` e nunca chama `save()`.

- [x] Reutilizar o caminho real de validação dos formulários, sem criar formulário alternativo.
- [x] Confirmar que o cadastro atual aceita CNPJ com DV inválido.
- [x] Confirmar que a unicidade textual de Empresa não detecta representações canonicamente equivalentes.
- [x] Confirmar que Filial não possui unicidade de CNPJ e exige verificação dentro do escopo da empresa.
- [x] Detectar colisão canônica de Empresa e Filial sem alterar a decisão ou salvar dados.
- [x] Excluir a própria identidade na comparação de uma atualização equivalente.
- [x] Proteger CNPJ e identificadores internos no diagnóstico.
- [x] Identificar os pontos futuros de integração em `EmpresaForm.clean_cnpj` e `FilialForm.clean_cnpj`, antes das validações do modelo.
- [x] Confirmar 642 arquivos Python, seis importações autorizadas em testes e zero em runtime.
- [x] Reexecutar inventário geral: 714 arquivos, 332 candidatos em 56 arquivos e zero `_REVISAR`.
- [x] Validar sete testes próprios, 39 testes focados do ciclo, 77 testes focados acumulados e 538 testes da suíte fiscal completa.
- [x] Manter modelos, formulários operacionais, migrações, dados, credenciais, certificados, ambientes e emissão inalterados.
- [ ] Fase 4 continua parcial: revisar os dados existentes e definir a integração cadastral; a comparação isolada não autoriza escrita operacional.

## Ponto de retomada — ciclo 116, 16/09/2026

Criado `alphanumeric_cnpj_company_branch_integration_plan_v1`. A auditoria protegida foi
repetida sobre a base local e confirmou o mesmo resultado agregado: 17 DVs inválidos, uma
colisão bloqueante, seis equivalências esperadas Empresa–Filial, uma identidade válida, um CPF
ignorado corretamente e um campo opcional vazio. Nenhum identificador completo foi exibido.

- [x] Separar bloqueios de dados legados das validações que podem avançar localmente.
- [x] Classificar os 17 DVs inválidos e a colisão como correção manual, nunca automática.
- [x] Preservar as seis equivalências Empresa–Filial como situação esperada.
- [x] Liberar somente testes locais de criação válida, DV inválido, atualização equivalente,
  colisão canônica, legado inválido e troca de identidade.
- [x] Manter persistência canônica, constraints e migração de conteúdo bloqueadas.
- [x] Manter credenciais, certificados, Focus, SEFAZ direta, homologação, produção e emissão
  fora desta decisão.
- [x] Integração Empresa/Filial concluída e provada no ciclo 117, sem correção silenciosa do
  legado nem troca de identidade sem controle.

Arquivos: `apps/fiscal/plano_integracao_escrita_cnpj.py` e
`apps/fiscal/test_plano_integracao_escrita_cnpj.py`. Documentação:
[PLANO_INTEGRACAO_ESCRITA_CNPJ_EMPRESA_FILIAL.md](PLANO_INTEGRACAO_ESCRITA_CNPJ_EMPRESA_FILIAL.md).
Migrações: nenhuma.

## Ponto de retomada — ciclo 117, 16/09/2026

O portão canônico passou a ser consumido por `EmpresaForm.clean_cnpj` e
`FilialForm.clean_cnpj`. Novos cadastros válidos são gravados com 14 caracteres em maiúsculas e
sem pontuação. DV inválido e colisão entre representações mascarada/canônica são recusados antes
do `save`; a colisão de Filial respeita o escopo da Empresa. Filial sem CNPJ continua permitida.

Em atualização, uma representação equivalente mantém a identidade e pode ser canonicalizada.
Um valor legado inválido não é corrigido silenciosamente e uma troca para outra identidade
válida permanece bloqueada para controles externos. A proteção está na fronteira dos
formulários; nenhuma constraint ou migração de conteúdo foi criada enquanto os 18 bloqueios
locais ainda aguardam decisão manual.

- [x] Integrar o portão aos formulários reais de Empresa e Filial.
- [x] Gravar criação válida na representação canônica oficial.
- [x] Rejeitar DV inválido e colisão canônica antes da persistência.
- [x] Preservar Filial sem CNPJ como campo opcional.
- [x] Permitir atualização equivalente sem trocar a identidade.
- [x] Bloquear legado inválido e troca de identidade sem correção silenciosa.
- [x] Atualizar o observador sombra para comprovar convergência do formulário com o portão.
- [x] Corrigir somente fixtures de formulário que usavam DVs inválidos, sem relaxar a regra.
- [x] Validar 79 testes de Empresas e oito cenários específicos da integração.
- [x] Validar 29 testes dos portões fiscais relacionados; o controle AST leu 656 arquivos,
  permitiu sete importações em testes e encontrou zero importações do catálogo em runtime.
- [x] Confirmar ausência de migration e manter dados locais, credenciais, certificados, Focus,
  SEFAZ direta, homologação, produção e emissão inalterados.
- [x] Avaliação de Cliente pessoa jurídica e Fornecedor pessoa jurídica concluída no ciclo 118,
  respeitando campos mistos CPF/CNPJ e o escopo da Empresa.

## Ponto de retomada — ciclo 118, 16/09/2026

Criado `alphanumeric_cnpj_customer_supplier_shadow_write_adapter_v1`. A comparação usa os
formulários reais sem `save`, preserva CPF do Cliente fora do portão de CNPJ, mantém os campos
vazios opcionais e verifica colisões canônicas somente dentro da Empresa.

- [x] Separar CPF de Cliente do caminho de CNPJ alfanumérico.
- [x] Preservar documento vazio opcional em Cliente e Fornecedor.
- [x] Confirmar concordância estrutural para CNPJ válido mascarado.
- [x] Confirmar que ambos os formulários ainda aceitam DV de CNPJ inválido.
- [x] Detectar colisões canônicas de Cliente PJ e Fornecedor PJ no escopo da Empresa.
- [x] Executar somente `SELECT`, sem salvar ou alterar instâncias existentes.
- [x] Proteger CPF, CNPJ e identificadores internos no diagnóstico.
- [x] Integração dos formulários reais concluída no ciclo 119, mantendo CPF fora da
  canonicalização de CNPJ e aplicando as travas de legado inválido e troca de identidade.

Arquivos: `apps/fiscal/adaptador_sombra_escrita_cnpj_partes.py` e
`apps/fiscal/test_adaptador_sombra_escrita_cnpj_partes.py`. Documentação:
[ADAPTADOR_SOMBRA_ESCRITA_CNPJ_CLIENTE_FORNECEDOR.md](ADAPTADOR_SOMBRA_ESCRITA_CNPJ_CLIENTE_FORNECEDOR.md).
Migrações: nenhuma.

## Ponto de retomada — ciclo 119, 16/09/2026

`ClienteForm.clean_cpf_cnpj` e `FornecedorForm.clean_cnpj` agora consomem o portão canônico.
Cliente separa primeiro CPF, que permanece fora do algoritmo de CNPJ; documento vazio também
continua permitido. No caminho PJ, as duas fronteiras validam formato e DV, gravam os 14
caracteres canônicos e recusam colisões dentro da Empresa.

Atualizações com CNPJ equivalente preservam a identidade. Legado inválido, troca entre CPF e
CNPJ e troca para outro CNPJ permanecem bloqueados para revisão externa. Nenhuma validação nova
de DV de CPF foi introduzida nesta etapa, evitando ampliar silenciosamente o escopo.

- [x] Canonicalizar CNPJ novo de Cliente PJ e Fornecedor PJ.
- [x] Rejeitar DV inválido e colisão canônica no escopo da Empresa.
- [x] Preservar CPF de Cliente e campos vazios opcionais.
- [x] Bloquear troca CPF/CNPJ, troca entre identidades e correção silenciosa de legado.
- [x] Atualizar o observador sombra para comprovar convergência com os formulários integrados.
- [x] Validar 32 testes de Cliente, Fornecedor, comparação e integração.
- [x] Confirmar 660 arquivos Python, nove importações autorizadas em testes e zero importações
  do catálogo de identidades em runtime.
- [x] Confirmar ausência de migration e manter os dados legados inalterados.
- [x] Concluir a fase 4 nas quatro fronteiras previstas, sem criar constraints enquanto a base
  local ainda contém 18 bloqueios que exigem decisão manual.
- [ ] Próximo passo: iniciar a fase 5 com auditoria delimitada da formação de chave de acesso,
  XML, QR Code e DANFE diante do CNPJ alfanumérico, sem ativar Focus, SEFAZ direta ou produção.

Arquivos principais: `apps/fiscal/validacao_escrita_cnpj.py`, `apps/clientes/forms.py`,
`apps/fornecedores/forms.py`, `apps/fiscal/test_integracao_escrita_cnpj_partes.py` e
`apps/fiscal/test_adaptador_sombra_escrita_cnpj_partes.py`. Migrações: nenhuma.

Arquivos principais: `apps/empresas/forms.py`, `apps/empresas/test_cnpj_canonico_forms.py`,
`apps/empresas/tests.py`, `apps/fiscal/adaptador_sombra_escrita_cnpj.py` e
`apps/fiscal/test_adaptador_sombra_escrita_cnpj.py`. Migrações: nenhuma.

Arquivos: `apps/fiscal/adaptador_sombra_escrita_cnpj.py` e `apps/fiscal/test_adaptador_sombra_escrita_cnpj.py`. Documentação: [ADAPTADOR_SOMBRA_ESCRITA_CNPJ.md](ADAPTADOR_SOMBRA_ESCRITA_CNPJ.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 120, 16/09/2026

Fechado o restante da Fase 4 nas fronteiras de interface e consulta cadastral. A causa era a
normalização exclusivamente numérica no JavaScript e no endpoint: a máscara compartilhada e o
botão de consulta usavam remoção de todo caractere não numérico, enquanto a busca local repetia
essa comparação. Isso podia apagar letras válidas antes de o backend canônico recebê-las.

- [x] Separar visualmente campos exclusivos de CNPJ dos campos mistos CPF/CNPJ.
- [x] Preservar letras durante a digitação, convertê-las para maiúsculas e aplicar a
  apresentação AA.AAA.AAA/AAAA-DD, mantendo os dois últimos caracteres numéricos.
- [x] Manter CPF numérico com a apresentação 000.000.000-00 e CNPJ numérico legado com a
  apresentação já conhecida.
- [x] Enviar ao lookup o CNPJ canônico sem descartar letras e manter o backend como autoridade
  de formato e DV.
- [x] Comparar Empresa e Filial localmente pela identidade canônica válida.
- [x] Não chamar provider externo com CNPJ alfanumérico enquanto o contrato configurado não
  declarar suporte; exibir mensagem clara e preservar o cadastro manual.
- [x] Preservar o contrato histórico alphanumeric_cnpj_canonicalization_strategy_v1 e criar
  alphanumeric_cnpj_integration_state_v2 para representar o estado corrente.
- [x] Manter dados legados inalterados e nenhuma migration. A unicidade canônica transacional
  no banco continua pendente até o saneamento consciente dos 18 bloqueios conhecidos.
- [x] Auditar DocumentoFiscal: o modelo possui unicidade por venda e por pedido, mas não
  possui constraint que exija exatamente uma origem. A defesa em profundidade foi registrada
  como P2 e não foi aplicada sem revisar todos os fluxos.
- [x] Inventariar sem alterar os consumidores posteriores que ainda assumem CNPJ/chave
  exclusivamente numéricos em geração fiscal, validação/transporte, DF-e, devolução, QR Code,
  Focus e SEFAZ direta.
- [x] Validar 157 testes da regressão cadastral/CNPJ e 572 testes da suíte fiscal ampla
  (três ignorados por requisitos específicos de ambiente), além do check geral sem erros e
  da confirmação de nenhuma migration pendente.
- [ ] Próximo passo: Fase 5 — auditoria delimitada da formação da chave de acesso, XML, QR Code
  e DANFE diante do CNPJ alfanumérico, sem ativar Focus, SEFAZ direta ou produção.

Arquivos principais: static/js/cnpj-documento.js, static/js/app.js,
apps/empresas/views.py, formulários de Empresa/Filial/Fornecedor,
apps/fiscal/estrategia_normalizacao_cnpj.py,
apps/empresas/test_cnpj_interface_lookup.py, templates/base.html e
docs/CONSULTA_CNPJ_CEP.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 121, 16/09/2026

Concluída a auditoria estática delimitada da Fase 5 pelo contrato
alphanumeric_cnpj_phase5_static_audit_v1. Esse registro representa o snapshot do ciclo 121; o
estado vivo evoluiu para v2 no ciclo 122.

- [x] Confirmar que a formação operacional da chave remove letras do CNPJ.
- [x] Confirmar que o cálculo operacional do DV pressupõe 43 posições numéricas.
- [x] Confirmar a mesma perda de letras nos XMLs de NFC-e e NF-e.
- [x] Classificar o Id de infNFe e a apresentação textual do DANFE como compatíveis somente
  quando receberem uma chave formada corretamente.
- [x] Localizar exigências exclusivamente numéricas na validação do XML, nos retornos dos
  adaptadores e nos serviços de simulação, cancelamento e consulta.
- [x] Confirmar que o QR Code da NFC-e descarta letras.
- [x] Confirmar a ausência do código de barras Code 128 híbrido no DANFE atual.
- [x] Separar três pontos posteriores dos canais: retorno Focus potencialmente compatível,
  SEFAZ direta incompatível e ingestão DF-e incompatível.
- [x] Registrar 11 pontos da Fase 5: oito incompatíveis, dois condicionais e um ausente.
- [x] Validar 21 testes da auditoria, evidência normativa, estratégia canônica e dados
  auditados; check geral sem erros e nenhuma migration pendente.
- [x] Manter geradores, XML operacional, modelos, banco, migrations, credenciais, certificados,
  ambientes, Focus, SEFAZ direta, rede e produção inalterados.
- [ ] Próximo passo: integrar em testes offline somente a formação e validação central da chave
  de acesso, reutilizando o algoritmo canônico existente e preservando o CNPJ numérico.

Arquivos: apps/fiscal/auditoria_fase5_cnpj.py,
apps/fiscal/test_auditoria_fase5_cnpj.py e
docs/AUDITORIA_FASE5_CNPJ_ALFANUMERICO.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 122, 16/09/2026

Criado o núcleo central fiscal_access_key_alphanumeric_v1 para formar e validar chaves de
acesso NF-e/NFC-e. Ele reutiliza a canonicalização oficial do CNPJ e o cálculo de DV por ASCII
menos 48, validando separadamente todas as posições numéricas da chave.

- [x] Preservar exatamente o resultado anterior para CNPJ e chave exclusivamente numéricos.
- [x] Formar a mesma chave alfanumérica a partir de CNPJ puro, mascarado ou em minúsculas.
- [x] Exigir 44 posições, letras somente na faixa reservada ao CNPJ e DV válido.
- [x] Integrar o gerador numérico real ao núcleo central.
- [x] Integrar a validação pré-transmissão ao normalizador central, com prova XML offline.
- [x] Bloquear explicitamente a geração operacional com emitente alfanumérico enquanto a tag
  CNPJ dos XMLs ainda não estiver integrada, evitando chave e XML divergentes.
- [x] Evoluir a auditoria viva para alphanumeric_cnpj_phase5_static_audit_v2: formação, DV e
  validação central estão compatíveis offline; permanecem cinco incompatibilidades, dois
  pontos condicionais e o código de barras híbrido ausente.
- [x] Validar 10 testes finais do núcleo/auditoria e 582 testes da suíte fiscal completa, com
  três ignorados por requisitos específicos de ambiente; check geral sem erros e nenhuma
  migration pendente.
- [x] Manter QR Code, DANFE, retornos dos adaptadores, Focus, SEFAZ direta, DF-e, credenciais,
  certificados, flags, rede e produção inalterados.
- [x] Próximo passo concluído no ciclo 123: CNPJ canônico integrado de forma atômica à chave,
  aos XMLs offline de NFC-e/NF-e e ao QR Code acoplado da NFC-e.

Arquivos principais: apps/fiscal/chave_acesso.py, apps/fiscal/services.py,
apps/fiscal/validacoes.py, apps/fiscal/test_chave_acesso.py,
apps/fiscal/auditoria_fase5_cnpj.py e
docs/AUDITORIA_FASE5_CNPJ_ALFANUMERICO.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 123, 16/09/2026

Concluída a integração offline do CNPJ canônico aos geradores reais de NFC-e e NF-e. A
mesma representação agora alimenta a faixa do emitente na chave e a tag emit/CNPJ, com
validação pré-transmissão que recusa qualquer divergência entre os dois valores.

- [x] Centralizar a normalização do CNPJ do emitente sem alterar o resultado numérico legado.
- [x] Remover o bloqueio preventivo somente após integrar os dois geradores fiscais reais.
- [x] Preservar letras na chave, no Id de infNFe e em emit/CNPJ da NFC-e do PDV.
- [x] Preservar letras na chave, no Id de infNFe e em emit/CNPJ da NF-e de pedido online.
- [x] Tratar o acoplamento obrigatório do QR Code dentro do gerador NFC-e, reutilizando a
  chave central válida sem filtragem somente numérica.
- [x] Recusar antes da transmissão XML cujo emit/CNPJ não corresponda às posições 7 a 20
  da chave.
- [x] Evoluir a auditoria viva para alphanumeric_cnpj_phase5_static_audit_v3: sete pontos
  compatíveis offline, dois incompatíveis, um condicional e o Code 128 híbrido ausente.
- [x] Validar 14 testes focados e 628 testes das suítes fiscal e marketplace, com três
  ignorados por requisitos específicos de ambiente.
- [x] Manter banco, modelos, migrations, credenciais, certificados, Focus, SEFAZ direta,
  chamadas de rede e produção inalterados.
- [x] Próximo passo concluído no ciclo 124: retornos dos adaptadores e fluxos internos
  pós-geração passaram a usar o normalizador central de chave.

Arquivos principais: apps/fiscal/chave_acesso.py, apps/fiscal/services.py,
apps/fiscal/qrcode_nfce.py, apps/fiscal/validacoes.py,
apps/fiscal/auditoria_fase5_cnpj.py, testes fiscais/marketplace e
docs/AUDITORIA_FASE5_CNPJ_ALFANUMERICO.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 124, 16/09/2026

Concluída a remoção das exigências exclusivamente numéricas nos retornos de autorização e
consulta e nos fluxos internos de simulação, cancelamento e consulta fiscal. Todos esses
pontos agora reutilizam a validação central de estrutura, posições e DV.

- [x] Aceitar e canonicalizar para maiúsculas chaves alfanuméricas válidas retornadas por
  autorização ou consulta.
- [x] Continuar recusando chaves de tamanho, posição ou DV inválidos.
- [x] Permitir simulação, cancelamento e consulta com chave alfanumérica válida.
- [x] Corrigir fixtures antigos que possuíam 44 dígitos, mas não um DV fiscal válido.
- [x] Evoluir a auditoria viva para alphanumeric_cnpj_phase5_static_audit_v4: nove pontos
  compatíveis offline, nenhum incompatível interno, um condicional e o Code 128 ausente.
- [x] Validar 20 testes focados, os dois cenários de provedor corrigidos e 630 testes das
  suítes fiscal e marketplace, com três ignorados por requisitos de ambiente.
- [x] Manter modelos, banco, migrations, credenciais, certificados, Focus, SEFAZ direta,
  chamadas de rede e produção inalterados.
- [x] Próximo passo concluído no ciclo 125: Code 128 híbrido C/A implementado e integrado ao
  DANFE, preservando a chave textual e sem liberar produção.

Arquivos principais: apps/fiscal/adapters.py, apps/fiscal/services.py,
apps/fiscal/test_chave_acesso.py, apps/fiscal/tests.py,
apps/fiscal/auditoria_fase5_cnpj.py e testes da auditoria. Migrações: nenhuma.

## Ponto de retomada — ciclo 125, 16/09/2026

Concluída a compatibilidade offline interna da Fase 5 com o código de barras da chave no
DANFE NFC-e. O gerador fiscal valida a chave central, inicia no conjunto C, alterna somente
para A ao encontrar letras e retorna a C em sequências numéricas, sem usar o conjunto B.

- [x] Reutilizar a biblioteca Code 128 já instalada, sem nova dependência.
- [x] Criar o contrato fiscal_access_key_code128_ca_v1 separado do código de barras de produto.
- [x] Preservar chaves exclusivamente numéricas compactas no conjunto C.
- [x] Alternar chaves alfanuméricas somente entre os conjuntos C e A, inclusive no fechamento
  de uma sequência numérica ímpar.
- [x] Gerar SVG local incorporado como data URI, sem rede ou serviço externo.
- [x] Integrar o código de barras aos dois caminhos de DANFE: Central Fiscal e fallback do PDV.
- [x] Isolar falhas de QR Code e código de barras para que uma representação não elimine a outra.
- [x] Preservar a apresentação textual integral da chave abaixo do código de barras.
- [x] Evoluir a auditoria viva para alphanumeric_cnpj_phase5_static_audit_v5, com os 11 pontos
  internos compatíveis offline.
- [x] Validar 5 testes focados e 708 testes das suítes fiscal, PDV e marketplace, com seis
  ignorados por requisitos específicos de ambiente.
- [x] Manter banco, migrations, credenciais, certificados, Focus, SEFAZ direta, rede e produção
  inalterados.
- [ ] Próximo passo: revisar o ciclo curto proposto para consumidores externos ao núcleo e,
  após concordância de escopo, tratar a Fase 6 sem antecipar homologação real.

Arquivos principais: apps/fiscal/barcode_chave.py, apps/fiscal/views.py,
apps/pdv/views.py, templates/fiscal/danfe_nfce.html, testes fiscais e da auditoria.
Migrações: nenhuma.

## Ponto de retomada — ciclo 136, 18/09/2026

Estruturado o registro auditável das futuras evidências reais por filial, canal e operação,
sem armazenamento de arquivos brutos ou segredos e sem aprovação automática.

- [x] Criar `EvidenciaHomologacaoCanal` vinculada à configuração fiscal, com snapshot do
  canal, operação e ambiente.
- [x] Armazenar somente referência protegida, SHA-256, versão, status/protocolo e confronto
  entre resultado esperado e obtido.
- [x] Restringir registro e revisão ao Master; todo registro nasce `PENDENTE`.
- [x] Bloquear produção, operação sem roteiro e lacuna interna como Eventos Focus.
- [x] Exigir justificativa na aprovação/rejeição e tornar a decisão revisada imutável pelo
  serviço, com auditoria nas duas etapas.
- [x] Proibir exclusão pelo modelo e criar restrições de banco para ambiente de homologação e
  coerência entre status, revisor e data de revisão.
- [x] Gerar e validar a migration `fiscal.0054_evidenciahomologacaocanal`.
- [x] Validar 6 testes próprios e 17 testes conjuntos de permissão, segurança, bloqueio,
  auditoria, revisão, roteiros e roteamento.
- [ ] Próximo passo exato: criar na tela Master o formulário de metadados, a lista e as ações
  separadas de aprovação/rejeição; depois conectar a conclusão da homologação às evidências
  aprovadas exigidas pelo canal.

Arquivos principais: apps/fiscal/models.py,
apps/fiscal/services_evidencias_homologacao.py,
apps/fiscal/test_evidencias_homologacao_canais.py,
apps/fiscal/migrations/0054_evidenciahomologacaocanal.py e
docs/REGISTRO_EVIDENCIAS_HOMOLOGACAO_CANAIS.md.

## Ponto de retomada — ciclo 144, 18/09/2026

Definido formalmente o primeiro piloto fiscal de supermercado em Goiás pelo canal
`SEFAZ_DIRETA_GO`, mantendo Focus NFe como opção secundária sem fallback ou
dependência no caminho direto.

- [x] Registrar a decisão de produto sem remover ou quebrar a integração Focus.
- [x] Unificar a matriz em sete operações: Autorização, Consulta, Rejeição,
  Cancelamento, Inutilização, Eventos (CC-e + manifestação) e DF-e.
- [x] Confirmar SEFAZ direta GO em 7/7 offline e manter Eventos Focus como lacuna
  6/7, sem bloquear o canal direto.
- [x] Centralizar a política canal × UF e aplicá-la em formulário, seleção do
  adaptador, roteamento, capacidade, prontidão e portão de homologação.
- [x] Separar a qualificação de build da validação runtime, eliminando dependência
  instalada em `test_*.py`.
- [x] Criar `fiscal_channel_qualification_manifest_v1` e identidade instalada
  independentes, com versão, commit, operações, lacunas, provas e hashes.
- [x] Tornar manifesto e identidade obrigatórios no ZIP comercial, mantendo
  testes e documentação interna fora do pacote.
- [x] Evoluir o portão para
  `fiscal_channel_homologation_completion_gate_v2`: qualificação instalada
  válida e sete evidências reais aprovadas são requisitos simultâneos.
- [x] Falhar fechado para manifesto ausente, inválido, adulterado ou divergente
  em contrato, integridade, versão, commit, canal ou operação.
- [x] Preservar isolamento por filial/canal e os históricos dos ciclos 141/142.
- [x] Manter rede, produção, credenciais e homologação real desligadas; nenhum
  CNPJ, IE, A1 ou CSC real foi usado.
- [x] Validar 51 testes focados e a regressão conjunta Fiscal + Configurações
  com 785 testes aprovados (3 pulados), incluindo o pacote offline; validar
  também `check`, ausência de migrations e integridade do diff.
- [x] Não iniciar criptografia/rotação de CSC; a pendência continua P2, com
  prioridade posterior ao fechamento do piloto direto.
- [ ] Próximo passo exato: quando existirem CNPJ/IE, A1 e credenciamento válidos
  (e CSC somente se houver compatibilidade explícita com QR Code v2), preparar a
  homologação real da filial piloto em SEFAZ direta GO,
  executar as sete operações e arquivar o aceite fiscal/contábil. Até lá, não
  habilitar rede nem produção.

Arquivos principais: apps/fiscal/politica_canais_fiscais.py,
apps/fiscal/manifesto_qualificacao_fiscal.py,
apps/fiscal/services_evidencias_homologacao.py,
scripts/fiscal_channel_qualification.py, scripts/package_local_server.ps1 e
docs/MANIFESTO_QUALIFICACAO_FISCAL.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 145, 21/09/2026

Concluída a pendência P2 de proteção do CSC. O segredo deixou de ser persistido em
texto aberto e passou a usar a mesma chave criptográfica de ambiente do certificado
A1, sem ser reexibido nas interfaces comuns.

- [x] Substituir a coluna de token em texto aberto por conteúdo criptografado e data
  da última atualização.
- [x] Criar migration preservadora que criptografa os CSCs existentes antes de remover
  a coluna legada; a reversão restaura o dado somente durante rollback técnico.
- [x] Manter leitura do segredo explícita e controlada, com falha fechada quando a chave
  fiscal do ambiente não corresponde à usada na gravação.
- [x] Restringir ID, inclusão, rotação e revogação do CSC ao Master; administradores
  comuns não visualizam nem conseguem alterar esses campos por POST forjado.
- [x] Nunca preencher o token no formulário; envio em branco preserva a cifra atual.
- [x] Excluir material criptografado do formulário do admin e usar apenas estado booleano
  nos diagnósticos de prontidão.
- [x] Auditar inclusão, rotação e revogação com descrição sanitizada, sem token.
- [x] Adicionar regressão específica para criptografia em repouso, não reexibição,
  preservação, rotação, revogação, autorização Master, admin e chave divergente.
- [x] Validar a regressão conjunta Fiscal + Vendas + PDV com 743 testes aprovados
  e 6 ignorados; após remover o atalho implícito de escrita, revalidar os 144
  testes diretamente afetados. `check`, `makemigrations --check --dry-run` e
  `git diff --check` permaneceram sem pendências.
- [ ] Próximo passo exato: revisar as constraints de contas financeiras originadas por
  compra/venda e impedir no banco origens ausentes, simultâneas ou incompatíveis sem
  quebrar os fluxos legados válidos.

Arquivos principais: apps/fiscal/models.py, apps/fiscal/certificados.py,
apps/fiscal/forms.py, apps/fiscal/views.py, apps/fiscal/admin.py,
apps/fiscal/readiness.py, apps/fiscal/test_protecao_csc.py,
templates/fiscal/form.html e docs/PROTECAO_CSC.md. Migration:
apps/fiscal/migrations/0055_protege_csc_criptografado.py.

## Ponto de retomada — ciclo 146, 21/09/2026

Concluída a pendência P2 de integridade das contas financeiras originadas por
compra e venda, preservando contas manuais e compras parceladas legítimas.

- [x] Mapear três classes válidas: conta manual sem origem comercial, crediário
  com uma venda e conta de compra única ou parcelada por duplicatas da mesma NF-e.
- [x] Impedir no banco venda e compra simultâneas na mesma conta.
- [x] Exigir entrada de compra quando a conta referencia uma duplicata de NF-e.
- [x] Exigir `RECEBER` para conta de venda e `PAGAR` para conta de compra.
- [x] Garantir uma conta por venda e uma conta não parcelada por entrada, sem
  bloquear múltiplas duplicatas válidas da mesma compra.
- [x] Acrescentar validação de domínio para filial divergente e duplicata
  pertencente a outra entrada de compra.
- [x] Criar preflight de migration não destrutivo: legado incompatível interrompe
  a aplicação e informa IDs/grupos; nenhum dado é apagado ou corrigido por heurística.
- [x] Validar 75 testes da matriz nova, crediário e Compras, além de `check`,
  `makemigrations --check --dry-run` e `git diff --check` sem pendências.
- [x] Executar a regressão Financeiro + Vendas: 92 de 93 testes passaram. A única
  falha, reproduzida isoladamente, é preexistente e pertence ao próximo item P2:
  o pacote da competência atual procura snapshot no último dia do mês, enquanto
  a captura imutável só admite a data corrente.
- [ ] Próximo passo exato: formalizar o contrato temporal do snapshot contábil,
  distinguindo competência em andamento de mês encerrado, sem fabricar fechamento
  retroativo e sem declarar snapshot completo para uma data que não foi capturada.

Arquivos principais: apps/financeiro/models.py,
apps/financeiro/migrations/0025_protege_origens_conta_financeira.py,
apps/financeiro/test_constraints_origem_conta.py e
docs/CONSTRAINTS_ORIGEM_CONTA_FINANCEIRA.md.

## Ponto de retomada — ciclo 147, 21/09/2026

Concluído o contrato temporal do inventário no pacote contábil, eliminando a
classificação incorreta de uma captura feita durante o mês como fechamento mensal.

- [x] Distinguir explicitamente competência em andamento e competência encerrada.
- [x] Usar, no mês corrente, a captura imutável do dia quando todas as filiais do
  pacote estiverem cobertas, sem declarar o mês fechado ou o snapshot completo.
- [x] Exigir, para mês encerrado, cobertura de todas as filiais exatamente no último
  dia da competência antes de declarar `SNAPSHOT_IMUTAVEL_FECHAMENTO`.
- [x] Não fabricar inventário retroativo: sem fechamento histórico completo, a
  posição atual é identificada como não retroativa e exige conferência.
- [x] Rejeitar competência futura antes da geração do pacote.
- [x] Expor no manifesto o estado da competência, a data de referência, a qualidade
  temporal, o indicador estrito de fechamento e os hashes das capturas usadas.
- [x] Cobrir os estados corrente, encerrado completo/incompleto e futuro, além do
  pacote mensal real; 8 testes focados aprovados.
- [x] Revalidar conjuntamente Financeiro + Estoque: 211 testes aprovados, sem
  regressões; `check`, `makemigrations --check --dry-run` e `git diff --check`
  permaneceram sem pendências.
- [ ] Próximo passo exato: criar a CI inicial com PostgreSQL para executar as
  proteções concorrentes e constraints no mesmo mecanismo de banco do piloto.

Arquivos principais: apps/financeiro/views.py,
apps/financeiro/test_contrato_temporal_inventario.py, apps/financeiro/tests.py e
docs/CONTRATO_TEMPORAL_SNAPSHOT_CONTABIL.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 148, 21/09/2026

Criada a CI inicial com PostgreSQL para que as proteções que dependem de lock,
concorrência e constraints deixem de depender apenas de execuções locais manuais.

- [x] Criar workflow acionado por pull request, push na `main` e disparo manual.
- [x] Usar PostgreSQL 16 descartável com healthcheck, base de teste separada e
  conexões persistentes desativadas.
- [x] Não usar segredo, certificado ou credencial fiscal real; todas as credenciais
  do banco pertencem exclusivamente ao job efêmero.
- [x] Executar `check` e detectar migrations não geradas antes dos testes.
- [x] Executar, numa única base PostgreSQL, as provas concorrentes de compra,
  origem fiscal, transmissão e caixa.
- [x] Reexecutar também as constraints de origem das contas financeiras.
- [x] Limitar o primeiro workflow à suíte crítica PostgreSQL; a suíte completa e a
  homologação externa continuam separadas.
- [x] Ensaiar localmente o mesmo conjunto em PostgreSQL 18 real: todas as migrations
  foram aplicadas, 14 testes passaram e a base descartável foi removida ao final.
- [x] Confirmar a primeira execução hospedada no PostgreSQL 16: workflow
  `PostgreSQL integrity` aprovado para o HEAD `f6518a8`, execução 35598784389.
- [ ] Próximo passo exato: revisar a defesa em profundidade da origem do
  `DocumentoFiscal`, mapeando antes todos os fluxos que criam documento sem origem
  comercial para não impor constraint incompatível.

Arquivos principais: .github/workflows/postgresql-integrity.yml,
docs/TESTES_CONCORRENCIA_POSTGRESQL.md e
docs/ROADMAP_EVOLUCAO_POS_PILOTO.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 149, 21/09/2026

Iniciada a defesa em profundidade da origem do `DocumentoFiscal`. A auditoria
confirmou que os dois criadores operacionais atuais são venda/NFC-e e pedido
online/NF-e; sincronização recebida e DF-e usam modelos separados.

- [x] Inventariar criações operacionais, Admin, fixtures, migrations e base local.
- [x] Confirmar que rascunhos de devolução ao fornecedor ainda não criam
  `DocumentoFiscal` e precisarão de origem própria antes da futura emissão.
- [x] Bloquear no banco venda e pedido online simultâneos, com preflight que não
  corrige nem exclui dados legados.
- [x] Exigir na validação de domínio exatamente uma origem e filial coerente.
- [x] Tornar o Admin de documentos fiscais somente leitura, sem inclusão ou exclusão.
- [x] Aplicar `fiscal.0056` na base local: 1 documento sem origem foi preservado e
  nenhuma dupla origem foi encontrada.
- [x] Validar a seleção atualizada da CI em PostgreSQL 18 real: 21 testes aprovados,
  incluindo as provas concorrentes e as constraints de origem.
- [x] Revalidar o módulo Fiscal completo: 653 testes aprovados e 3 ignorados por
  dependerem de ambiente específico.
- [x] Confirmar a CI PostgreSQL 16 hospedada para o HEAD `169df11`, execução
  35600481353, com a seleção ampliada aprovada.
- [ ] A constraint final de presença permanece pendente: existe 1 NFC-e emitida
  legada sem origem, sem venda candidata de mesma filial/valor e sem chave que
  permita vínculo inequívoco. Seu XML contém apenas `NFeDemo9001`, sem modelo,
  número, série, emissão ou total estruturados; nenhuma associação ou exclusão foi
  realizada por suposição.
- [ ] Próximo passo exato: o responsável fiscal deve classificar esse documento
  legado com evidência; depois, definir a origem da futura devolução ao fornecedor
  e criar a constraint que exija exatamente uma origem entre os fluxos suportados.

Arquivos principais: apps/fiscal/models.py, apps/fiscal/admin.py,
apps/fiscal/test_concorrencia_preparacao.py,
apps/fiscal/migrations/0056_bloqueia_origens_simultaneas_documento.py e
docs/DEFESA_ORIGEM_DOCUMENTO_FISCAL.md.

## Ponto de retomada — ciclo 150, 21/09/2026

Concluída a defesa em profundidade da origem do `DocumentoFiscal`. Com autorização
expressa para tratar a base local como exclusivamente demonstrativa, o único registro
sem origem (`id=1`, conteúdo `NFeDemo9001`) foi removido depois de confirmar que não
possuía dependências. Nenhuma migration contém exclusão ou inferência de vínculo.

- [x] Remover exclusivamente o registro demonstrativo local que impedia a invariância;
  nenhum outro documento fiscal ou dado de domínio foi apagado ou recriado.
- [x] Criar a migration `fiscal.0057_exige_origem_documento_fiscal` com preflight
  fail-closed: instalações com origem ausente ou dupla param e exibem os IDs afetados,
  sem excluir dados, aproximar vínculos ou inventar origem.
- [x] Substituir a proteção parcial por `fisc_doc_exatamente_uma_origem`, exigindo no
  banco exatamente uma origem entre `venda` e `pedido_online`, mantendo as
  unicidades já existentes e a validação de mesma filial.
- [x] Adequar as fixtures fiscais e financeiras para criarem documentos por uma origem
  comercial explícita, sem enfraquecer a regra para acomodar testes antigos.
- [x] Aplicar a migration 0057 na base local e confirmar zero documentos sem origem,
  com dupla origem ou fora da nova invariância.
- [x] Validar a regressão Fiscal completa: 654 testes aprovados e três ignorados por
  dependências explícitas de ambiente.
- [x] Validar no PostgreSQL 18 local a seleção integral da CI: 22 testes aprovados,
  inclusive ausência de origem, dupla origem, mesma filial, unicidade e concorrência.
- [x] Definir a evolução da devolução ao fornecedor: antes de esse fluxo emitir NF-e,
  `DocumentoFiscal` receberá uma relação protegida e dedicada ao registro aprovado de
  `RascunhoDevolucaoFornecedor`; na mesma migration, o XOR será ampliado atomicamente
  para exatamente uma entre venda, pedido online ou devolução. Até lá, esse fluxo não
  pode criar `DocumentoFiscal`; não haverá origem genérica ou manual.
- [ ] Próximo passo exato: confirmar a execução hospedada da CI deste commit. Depois,
  selecionar a primeira pendência interna ainda segura da ordem do roadmap. Se o item
  seguinte exigir CNPJ/IE/A1/CSC reais, acesso à SEFAZ ou liberação de produção, parar
  e preservar essas travas.

Arquivos principais: apps/fiscal/models.py,
apps/fiscal/migrations/0057_exige_origem_documento_fiscal.py,
apps/fiscal/test_concorrencia_preparacao.py, apps/fiscal/test_support_documentos.py,
fixtures fiscais/financeiras e docs/DEFESA_ORIGEM_DOCUMENTO_FISCAL.md.

## Ponto de retomada — ciclo 151, 21/09/2026

Concluída a revisão normativa P1 de consumidor PJ, cBenef GO e readiness/CSC. As
fontes oficiais foram confrontadas com o comportamento atual antes da alteração;
nenhuma credencial real, chamada à SEFAZ ou configuração de produção foi utilizada.

- [x] Confirmar no Ajuste SINIEF 19/16 consolidado que a identificação do destinatário
  da NFC-e admite CNPJ e que o § 4º, que obrigaria modelo 55 para todo destinatário
  identificado por CNPJ, foi revogado pelo Ajuste 12/26 com efeitos em 09/04/2026.
- [x] Permitir no PDV a escolha explícita Não/CPF/CNPJ, sem preencher documento a partir
  do cadastro do cliente por suposição.
- [x] Validar e canonicalizar CNPJ numérico ou alfanumérico antes de finalizar a venda;
  serializar `dest/CNPJ` e `indIEDest=9` na NFC-e do consumidor final não contribuinte.
- [x] Preservar NF-e modelo 55 e os bloqueios tributários para contribuinte/B2B,
  interestadual e cenários que o PDV não representa.
- [x] Preservar o CNPJ alfanumérico do destinatário nos parâmetros assinados do QR Code
  v3 em contingência.
- [x] Confirmar na NT 2025.001 v1.03 que QR Code v3 não exige CSC e usa assinatura A1
  apenas na contingência; remover CSC como requisito de prontidão do leiaute v3.
- [x] Manter inclusão, rotação, revogação e criptografia do CSC para compatibilidade
  legada explícita com QR Code v2, sem expor ou apagar o segredo já cadastrado.
- [x] Confirmar que a cobertura cBenef continua parcial: catálogo oficial, vigência,
  formato, CST e redução de base estão protegidos; outras hipóteses dependem de um
  indicador explícito de benefício por produto/operação e não podem ser inferidas.
- [x] Validar 8 testes focados e a regressão conjunta Fiscal + Vendas + PDV:
  752 testes aprovados e 6 ignorados por dependências explícitas de ambiente.
- [x] Validar `check`, ausência de migrations novas e integridade do diff.
- [x] Próximo passo interno seguro: modelar o indicador explícito de benefício fiscal
  por produto/operação, em estado indefinido/sem benefício/com benefício, sem classificar
  automaticamente produtos existentes e sem liberar emissão quando a decisão necessária
  estiver ausente. A parametrização tributária real continuará dependendo do contador.

Fontes oficiais: Ajuste SINIEF 19/16 consolidado e NT 2025.001 v1.03 do Portal Nacional
da NF-e; catálogo cBenef e INs já preservados em docs/CBENEF_GO.md.
Migrações: nenhuma.

## Ponto de retomada — ciclo 152, 21/09/2026

Concluída a decisão explícita de benefício fiscal de ICMS por produto e natureza de
operação. O ciclo permaneceu inteiramente local, sem CNPJ/IE/certificado reais, sem
chamada à SEFAZ e sem ativação de produção.

- [x] Criar `ParametrizacaoBeneficioFiscalProduto` com os estados indefinido, sem
  benefício e com benefício, responsável, fundamento contábil e data de atualização.
- [x] Exigir unicidade de produto + natureza e coerência entre situação e `cBenef`
  também no banco; a migration não cria, classifica nem altera decisões existentes.
- [x] Bloquear a preparação de NF-e/NFC-e em Goiás, no regime normal, quando a decisão
  estiver ausente ou indefinida para a natureza efetivamente usada.
- [x] Fazer o XML consumir somente o `cBenef` da parametrização explícita da operação;
  o campo legado do produto não é usado como inferência nesse fluxo.
- [x] Validar códigos informados contra o catálogo cBenef GO já instalado e impedir
  combinações contraditórias, inclusive “sem benefício” com código de benefício.
- [x] Disponibilizar cadastro e consulta na área fiscal, com alteração restrita a
  Administrador/Contabilidade e trilha em `LogAuditoria`.
- [x] Manter todos os registros locais existentes sem classificação automática: após a
  migration, a nova tabela permaneceu com zero registros até decisão humana.
- [x] Atualizar fixtures sintéticas para declarar explicitamente “sem benefício”, sem
  converter essa decisão de teste em regra ou dado de produção.
- [x] Validar 13 testes focados e a regressão fiscal completa: 660 testes aprovados e
  3 ignorados por dependências explícitas de ambiente; `check`, migrations e diff íntegros.
- [x] Aplicar localmente a migration fiscal 0058; a base local usa SQLite. Na mesma
  execução, migrations já existentes e ainda pendentes de Compras 0012, Fornecedores
  0004 e Financeiro 0024/0025 também foram aplicadas, sem limpeza de dados.
- [x] Próximo passo interno seguro: integrar a decisão por operação ao diagnóstico e à
  listagem/exportação de produtos fiscais, exibindo quais naturezas padrão ainda estão
  indefinidas; depois retirar o campo legado de `Produto` sem migrar ou inferir valores.

Migration: `apps/fiscal/migrations/0058_parametrizacaobeneficiofiscalproduto.py`.

## Ponto de retomada — ciclo 153, 21/09/2026

Concluída a integração da decisão de benefício fiscal por operação aos instrumentos de
prontidão cadastral. O campo legado continua armazenado apenas para compatibilidade e
deixou de ser apresentado no CSV como fonte emissiva.

- [x] Fazer o diagnóstico de prontidão considerar as naturezas NFC-e padrão das empresas
  atendidas e marcar produto sem decisão explícita como pendente.
- [x] Fazer a listagem fiscal distinguir pendente/pronto por natureza padrão de operação
  em empresas de Goiás no regime normal.
- [x] Exibir a natureza no texto da pendência, evitando uma mensagem genérica que não
  indique qual parametrização contábil falta.
- [x] Exportar no CSV as decisões por operação e renomear o cabeçalho antigo para
  `codigo_beneficio_fiscal_legado_nao_emissivo`, sem reclassificar qualquer produto.
- [x] Preservar o comportamento anterior para UFs/CRTs sem exigência desta decisão e
  manter a preparação emissiva fail-closed em Goiás.
- [x] Validar 3 testes focados e a regressão fiscal completa: 661 testes aprovados e
  3 ignorados por dependências explícitas de ambiente.
- [x] Passo retomado nos ciclos 154/155: os escritores cadastrais e de integração foram
  retirados sem inferência. A remoção física foi bloqueada porque ainda existe fallback
  emissivo de compatibilidade fora de GO + CRT 2/3.

Migrações: nenhuma nova neste ciclo.

## Ponto de retomada — ciclo 154, 21/09/2026

Concluído o fechamento das bordas de NFC-e e cBenef antes de qualquer remoção do
campo legado. Nenhuma classificação fiscal foi inferida, nenhuma rede fiscal foi
acessada e as travas de produção permaneceram inalteradas.

- [x] Unificar a resolução emissiva do cBenef com a validação: GO + CRT 2/3 exige
  decisão explícita por produto/natureza e não aceita o legado como atalho; fora
  desse recorte, o comportamento legado permanece enquanto a migração cadastral
  não estiver concluída.
- [x] Provar em NFC-e e NF-e que o cBenef legado não é descartado silenciosamente
  nos escopos ainda não migrados e que GO/regime normal continua fail-closed.
- [x] Corrigir o QR Code NFC-e v3 em contingência para destinatário estrangeiro:
  tipo 3 com o parâmetro seguinte vazio, sem alterar o dest/idEstrangeiro do
  XML. Referência: Manual de Padrões Técnicos DANFE NFC-e/QR Code v6.0 do Portal
  Nacional da NF-e.
- [x] Tornar obrigatória no backend a decisão NAO/CPF/CNPJ; rejeitar ausência,
  valor desconhecido e documento inválido, e limpar documento residual quando a
  decisão for NAO.
- [x] Alinhar cenários e documentação operacional: CSC não é requisito do QR Code
  v3 e permanece protegido apenas para compatibilidade legada explicitamente
  configurada com QR Code v2.
- [x] Auditar a cardinalidade 1:N do catálogo fiscal. Os joins reversos podiam
  multiplicar linhas quando o produto tinha várias naturezas; a consulta passou a
  usar subconsultas por produto, sem distinct() indiscriminado. Tela, métricas e
  CSV foram provados com duas parametrizações e uma única ocorrência.
- [x] Revisar a coerência já protegida de ParametrizacaoBeneficioFiscalProduto:
  unicidade produto+natureza, estados/códigos coerentes, escopo de empresa, papel
  de revisão fiscal e auditoria permanecem cobertos.
- [x] Validar 24 testes focados, 669 testes fiscais (3 ignorados), 79 testes de PDV
  (3 ignorados) e 20 testes de Vendas. A suíte crítica de concorrência PostgreSQL
  foi chamada explicitamente, mas seus 2 testes foram ignorados porque a base local
  deste ciclo é SQLite. check, migrations e diff ficaram íntegros.
- [ ] Próximo passo interno seguro: auditar e retirar os consumidores cadastrais e
  de integração ainda existentes do legado — formulário/importação de Produto,
  snapshots e eventos de entrada, CSV e fallback de prontidão/emissão — com testes
  de caracterização. Só autorizar a remoção da coluna quando houver zero consumidor
  emissivo e zero diferença de comportamento coberta; até lá, não criar migration
  de remoção.

Migrações: nenhuma nova neste ciclo. Produto.codigo_beneficio_fiscal foi
deliberadamente preservado.

## Ponto de retomada — ciclo 155, 21/09/2026

Concluída a aposentadoria dos escritores e exposições cadastrais do cBenef legado. A
auditoria completa está em `docs/INVENTARIO_CBENEF_LEGADO.md`; nenhuma classificação foi
inferida, nenhuma migration foi criada e nenhuma rede fiscal foi acessada.

- [x] Inventariar modelos, formulários, serviços, importação/exportação, snapshots,
  eventos recebidos, telas, serialização XML, fallback emissivo, testes e migrations.
- [x] Retirar o campo legado do formulário de Produto e orientar a decisão explícita na
  área Fiscal por produto e natureza de operação.
- [x] Retirar o escritor da importação CSV e rejeitar o cabeçalho antigo com mensagem
  clara, sem aceitar silenciosamente um valor que não será aplicado.
- [x] Publicar `produto_snapshot_v2` sem cBenef legado; manter eventos v1 legíveis, mas
  ignorar o campo antigo na entrada, preservando o valor local existente.
- [x] Retirar a coluna legada da exportação fiscal e manter somente as decisões por
  operação como informação cadastral atual.
- [x] Criar diagnóstico e comando somente leitura para contar produtos remanescentes e
  listar referências técnicas; a base local retornou zero produtos preenchidos.
- [x] Caracterizar a borda emissiva: GO + CRT 2/3 usa exclusivamente a decisão explícita;
  fora desse recorte, o fallback legado permanece para evitar mudança fiscal silenciosa.
- [x] Classificar o estado como `AINDA_EXISTE_CONSUMIDOR_EMISSIVO` e a decisão como
  `NAO_PODE_REMOVER_COLUNA`; a ausência de dados locais não muda essa conclusão.
- [x] Validar 11 testes focados, 54 testes de Produtos, 90 de Empresas/sincronização,
  669 fiscais (3 ignorados) e 142 de Configurações. A classe crítica teve 10 testes
  aprovados e 2 exclusivos de PostgreSQL ignorados na base SQLite local; `check`,
  migrations e diff ficaram íntegros.
- [ ] Próximo passo interno seguro: desenhar e testar a substituição explícita do fallback
  nos demais escopos de UF/CRT. Só então repetir o inventário e avaliar uma migration de
  remoção, exigindo zero consumidor emissivo e zero diferença de comportamento.

Migrações: nenhuma nova neste ciclo. `Produto.codigo_beneficio_fiscal` permanece apenas
para a compatibilidade emissiva documentada.

## Ponto de retomada — ciclo 156, 21/09/2026

Concluído o primeiro bloco interno seguro da vinculação fiscal dos pagamentos eletrônicos
na NFC-e GO. A auditoria detalhada está em
`docs/AUDITORIA_VINCULACAO_PAGAMENTOS_NFCE_GO.md`. Nenhuma credencial real foi usada,
nenhuma rede Focus/SEFAZ foi acionada e nenhuma liberação de produção foi realizada.

- [x] Confirmar que o PDV já suporta pagamentos divididos e exige confirmação, ID externo,
  NSU e autorização para cada parcela eletrônica antes de concluir a venda.
- [x] Confirmar que o núcleo fiscal já mapeia crédito, débito e PIX para `tPag` 03, 04 e
  17, preservando o `vPag` individual, mas ainda não serializa o grupo condicional `card`.
- [x] Criar no `PagamentoVenda` os campos estruturados de tipo de integração, CNPJ da
  instituição, bandeira, CNPJ do beneficiário e identificador do terminal; ampliar a
  autorização para o limite do leiaute e preservar todos os campos vazios quando o
  adaptador não os fornecer.
- [x] Evoluir o contrato do app desktop para `pdv_tef_v2`, transportar os metadados por
  parcela até a venda e rejeitar formatos inválidos no adaptador e no serviço.
- [x] Manter o simulador restrito ao desenvolvimento sem fabricar tipo de integração,
  CNPJ, bandeira, beneficiário ou terminal; esses dados deverão vir do provedor real.
- [x] Criar a migration `vendas.0013_pagamentovenda_dados_fiscais_eletronicos` e validar
  persistência, contrato do PDV, adaptadores, pagamentos divididos e regressões fiscal e
  de configuração.
- [x] Próximo passo interno seguro executado no ciclo 157: serialização condicional do
  grupo `card`, bloqueios de dados incompletos e paridade estrutural offline nos dois
  canais. Prova de origem confiável do adaptador e homologação permanecem pendentes.

Pendências externas preservadas: escolher/conectar o driver real de TEF/PIX, obter os
metadados oficiais da adquirente/instituição, validar em equipamento físico e homologar
o XML com a SEFAZ-GO. Esses itens não podem ser aprovados por simulador.

Migração: `apps/vendas/migrations/0013_pagamentovenda_dados_fiscais_eletronicos.py`.

## Ponto de retomada — ciclo 157, 22/09/2026

Concluída a serialização interna do vínculo fiscal por parcela na NFC-e GO. O gerador
preserva `tPag` e `vPag` de cada pagamento e adiciona o grupo `card` na ordem do XSD
010f auditado. O conversor Focus usa os nomes publicados em sua documentação e o
adaptador SEFAZ direto preserva o mesmo XML no envelope SOAP. Nenhuma rede fiscal,
credencial real ou liberação de produção foi usada.

- [x] Emitir `tpIntegra`, CNPJ da instituição, bandeira de cartão quando aplicável,
  `cAut`, CNPJ do beneficiário e identificador do terminal sem valores inventados.
- [x] Em Goiás, bloquear preparação da NFC-e eletrônica sem tipo de integração; para
  `tpIntegra=1`, exigir CNPJ, autorização, estado confirmado, ID externo e NSU.
- [x] Rejeitar bandeira em PIX, formatos fiscais inválidos e metadados eletrônicos em
  forma de pagamento incompatível. O simulador segue sem fornecer integração fiscal.
- [x] Preservar CNPJ alfanumérico canônico no driver desktop, serviço de vendas e XML;
  vendas legadas fora de GO sem os novos metadados mantêm o XML anterior.
- [x] Cobrir cartão, PIX, pagamento dividido, rejeições, Focus e SEFAZ direta com
  testes offline. O pacote XSD 010f foi confrontado estruturalmente; ele continua
  arquivado, sem promoção operacional.
- [x] Bloco interno de origem confiável executado no ciclo 158: registro confirmado no
  servidor, consumo único por parcela e bloqueio de campos ocultos como prova de
  integração. Verificador real e ligação autenticada ao provedor seguem pendentes.

Pendências externas: driver/adquirente real, equipamento físico, dados oficiais do
provedor, aprovação do schema para o piloto, aceite de CNPJ alfanumérico pela Focus
e homologação em SEFAZ-GO/Focus. A paridade acima é apenas offline; `tpIntegra=1` ainda não comprova integração real de ponta a
ponta. Nenhuma migration nova foi criada neste ciclo.

## Ponto de retomada — ciclo 158, 23/09/2026

Concluído o bloco interno de proveniência dos pagamentos integrados. A `main` iniciou
limpa em `d73931ad9506e7335b7528eaa47af6e66d303616`. O ciclo não retomou checkboxes
históricos nem ativou Focus, SEFAZ, credenciais reais ou produção.

- [x] Exigir confirmação persistida no servidor para declarar `tipo_integracao=1`;
  autorização, NSU e metadados do navegador não são prova de integração.
- [x] Vincular a confirmação ao caixa, forma, valor e transação do provedor; proteger
  consumo único com bloqueio transacional e unicidade no banco, inclusive parcelas
  divididas. Falhas revertem efeitos parciais.
- [x] Usar exclusivamente os metadados confirmados do servidor na parcela integrada.
  A allowlist de verificadores permanece vazia e não há endpoint público de registro.
- [x] Revalidar origem na geração fiscal e conferir pagamentos/`card` do XML já salvo
  antes da transmissão comum a Focus e SEFAZ direta. Legado sem confirmação não é
  promovido automaticamente a integração confiável.
- [x] Criar migration aditiva `vendas.0014_confirmacao_integracao_pagamento`, sem
  exclusões ou backfill de evidências; incluir os testes de integridade e concorrência
  de confirmação no workflow PostgreSQL.
- [x] Bloco interno executado no ciclo 159: confronto offline do XML completo com
  cartão/PIX divididos contra o XSD 010f arquivado, com assinatura sintética e
  evidências independentes de Focus e SEFAZ direta. Ver diagnóstico específico.

Pendências externas: implementar o verificador real com autenticação e escopo do
estabelecimento/terminal, ligar o bridge ao registro do servidor, obter respostas oficiais
do provedor, testar equipamento físico, aprovar o schema para o piloto e homologar
SEFAZ-GO/Focus. A integração real continua bloqueada até essa comprovação; os testes
sintéticos não a liberam.

Verificações do fechamento: 110 testes focados aprovados; regressão de vendas, PDV,
fiscal e configurações com 934 testes, 7 ignorados por exigirem PostgreSQL; 17 testes
finais do vínculo/XML, 16 aprovados e 1 concorrente reservado ao PostgreSQL; 8 testes
TEF desktop aprovados. A regressão ampliada e o fechamento usaram hash de senha rápido
somente no processo de testes. Django check, migrations check, auditoria de importação
das fixtures e diff check aprovados. Migration 0014 aplicada ao SQLite local, seguida
de `migrate --check` sem pendências; nenhum dado demonstrativo foi removido.
O workflow PostgreSQL executará também as novas constraints e a corrida de consumo
único no push deste ciclo; o resultado hospedado será informado no encerramento.

## Ponto de retomada — ciclo 159, 23/09/2026

Confronto offline documentado em
`docs/DIAGNOSTICO_NFCE_PAGAMENTOS_XSD_010F.md`. O cenário sintético com crédito e
PIX em parcelas separadas passou no XSD completo **após assinatura de teste**;
Focus e SEFAZ direta preservaram os campos fiscais de cada parcela em seus artefatos
locais. Adulteração da autorização invalidou a assinatura, e bandeira inválida
falhou no XSD. Cada canal apresentou falha independente nos ensaios negativos.

- [x] Auditar hash/estrutura do pacote arquivado antes de compilar o XSD somente em
  diretório temporário; não instalar nem promover o schema candidato.
- [x] Corrigir `PIS/PISAliq|PISNT|PISOutr` e `COFINS/COFINSAliq|COFINSNT|COFINSOutr`
  no XML. O erro impedia a conformidade XSD e a leitura desses grupos pela Focus.
- [x] Gerar `enderEmit` na NFC-e a partir do endereço **estruturado e completo** da
  filial; nenhum endereço é fabricado quando os dados estão ausentes.
- [x] Registrar diagnóstico sanitizado com estado e hash do XML/XSD e projeções
  separadas de Focus e SEFAZ direta; nenhuma rede fiscal foi usada.
- [ ] Próximo passo interno seguro: impedir preparação/transmissão da NFC-e GO com
  cadastro do emitente incompleto e conferir a exigência em ambos os canais;
  depois ampliar o confronto XSD a variantes tributárias e pagamentos suportados.

Pendências externas preservadas: endereço real da filial, driver/retorno autenticado
da adquirente, equipamento físico, aprovação do schema, validação da Focus e
homologação SEFAZ-GO. O ensaio sintético não libera produção. Migrações: nenhuma.
Verificações: 4 testes focados aprovados; regressão fiscal, vendas e PDV com 793 testes
(7 ignorados por dependerem de PostgreSQL); teste final do envelope integral aprovado.
Django check, migrations check, auditoria de fixtures e diff check aprovados.

## Ponto de retomada — ciclo 160, 23/09/2026

Fechado o preflight interno da NFC-e GO e a origem do código de autorização,
sem migration, rede fiscal, credenciais reais ou liberação de produção.

- [x] Preparação e geração do XML recusam endereço estruturado incompleto do
  emitente GO (logradouro, número, bairro, município, UF e código IBGE de 7 dígitos
  iniciado por 52); CEP e telefone opcionais também têm formato conferido
  quando informados. Não há preenchimento presumido.
- [x] Pré-envio compartilhado por Focus e SEFAZ direta recusa XML GO legado sem
  `enderEmit`, cadastro alterado/divergente e UF incompatível na chave/XML. O
  emissor simulado local aplica o mesmo preflight. A falha ocorre antes da
  chamada ao adaptador; corrigir dados exige regenerar e assinar novamente.
- [x] `cAut` exige confirmação vinculada ao pagamento e autenticada no servidor,
  inclusive para `tpIntegra=2`. Valor do simulador, POST, legado, NSU, ID externo
  ou E2E sem essa origem não é aceito como autorização fiscal. O verificador
  operacional continua desligado; o verificador sintético existe só em testes.
- [x] A paridade XML ↔ banco confere todas as parcelas sempre que houver `card`
  ou metadados fiscais eletrônicos, não apenas `tpIntegra=1`. Testes cobrem
  adulteração posterior de `cAut`, `tpIntegra`, endereço e dados persistidos.
- [x] Mantido o diagnóstico XSD 010f offline para crédito + PIX dividido e a
  projeção independente nos dois canais, sem promover o schema arquivado.
- [ ] Próximo passo interno seguro: ampliar o confronto XSD offline às variantes
  tributárias e demais formas de pagamento já suportadas, mantendo testes de
  assinatura, paridade e falha independente por canal.

Verificações locais: 798 testes fiscal/vendas/PDV, 7 ignorados por exigirem
PostgreSQL; Django check, `makemigrations --check --dry-run`, `migrate --check`
e `git diff --check` aprovados. A suíte local adicional revelou uma fixture
antiga de NF-e GO sem classificação de benefício fiscal; ela foi completada
somente no teste, e os 45 testes marketplace passaram. A CI PostgreSQL do
commit `0704da4` concluiu com sucesso.
Pendências externas preservadas: endereço cadastral real, driver TEF/PIX e
retorno autenticado de provedor/adquirente, equipamento físico, promoção
controlada de schema, validação Focus, homologação SEFAZ-GO e aceite de produção.

## Ponto de retomada — ciclo 161 (bloco curto), 23/09/2026

- [x] Ampliar o confronto XSD 010f arquivado ao pagamento dividido de débito
  (`tPag=04`) + PIX (`tPag=17`), com XML sintético assinado e preservação offline
  no conversor Focus e no envelope SEFAZ direta.
- [x] Confrontar também PIS/COFINS não tributados (`PISNT`/`COFINSNT`) na NFC-e
  sintética assinada com pagamentos divididos.
- [x] Confrontar PIS/COFINS de outras operações (CST 49,
  `PISOutr`/`COFINSOutr`) no mesmo fluxo. Quatro testes XSD focados passaram,
  incluindo a regressão de crédito + PIX; nenhuma rede fiscal foi usada.
- [x] Acrescentar IPI não tributado (CST 53, `IPINT`) ao confronto XSD offline
  com crédito + PIX divididos; teste focado aprovado. A CI PostgreSQL do
  commit `d29c0c2` passou.
- [x] Confrontar também IPI tributado (CST 50, `IPITrib`) com política explícita
  de imposto incluso no preço, sem alterar o total pago. Os dois testes IPI
  focados passaram com assinatura e paridade offline dos canais.
- [x] Confrontar pagamento misto em três parcelas (cartão de crédito, PIX e
  dinheiro) no XSD arquivado e nos dois canais offline. Alterar depois o valor
  do dinheiro no XML assinado é recusado pela paridade XML ↔ banco e invalida a
  assinatura. Regressão `FiscalTests`: 130 testes aprovados.
- [ ] Prosseguir em blocos pequenos com outras variantes tributárias e formas
  já suportadas; próximo candidato: vale-alimentação/refeição, se o contrato
  fiscal e as fixtures permitirem, sem promover schema nem declarar homologação.

## Ponto de retomada — ciclo 143, 18/09/2026

Concluída a pendência P2 de parcelas/duplicatas da NF-e recebida, eliminando a perda da
estrutura financeira na importação de compras parceladas.

- [x] Confirmar no MOC 7.0 oficial o grupo `cobr/fat/dup`, limite de 120 parcelas, numeração
  sequencial, vencimentos crescentes e valor obrigatório de cada parcela.
- [x] Preservar número e valores da fatura e, por duplicata, sequência, número, vencimento e
  valor, sempre vinculados à entrada de compra importada.
- [x] Validar número `001...`, ordem dos vencimentos, valor positivo e igualdade entre a
  soma das duplicatas e `vLiq` quando a fatura líquida estiver informada.
- [x] Criar uma conta a pagar por duplicata íntegra, com vínculo unívoco entre conta,
  duplicata e entrada de compra.
- [x] Manter compatibilidade segura para XML sem fatura líquida íntegra: preservar o dado
  recebido, mas gerar somente a conta tradicional pelo total fiscal, sem inventar parcelas.
- [x] Exibir as parcelas íntegras na revisão e no detalhe da entrada antes e depois da
  finalização.
- [x] Corrigir dois testes legados que simulavam conta paga sem data de pagamento, estado já
  proibido pela constraint de baixa integral vigente.
- [x] Validar 51 testes focados de compras, importação XML e baixa integral; `check` limpo,
  `makemigrations --check --dry-run` sem mudanças e `git diff --check` aprovado.
- [x] Gerar as migrations `compras.0012` e `financeiro.0024`, sem aplicar no banco operacional.
- [ ] Pendência P2 preservada: revisar e implementar a criptografia do CSC em repouso,
  incluindo fluxo auditado de inclusão/rotação/revogação e testes de não exposição. O
  ciclo 144 alterou apenas sua prioridade; ela não foi iniciada.

Arquivos principais: apps/compras/models.py, apps/compras/services.py,
apps/compras/services_xml.py, apps/compras/tests.py, apps/financeiro/models.py,
templates/compras/entrada_form.html e templates/compras/entrada_detalhe.html.
Migrações: apps/compras/migrations/0012_faturanfeentrada_duplicatanfeentrada.py e
apps/financeiro/migrations/0024_contafinanceira_duplicata_nfe_entrada.py.

## Ponto de retomada — ciclo 142, 18/09/2026

Criada a consulta Master do histórico de canais e transições da homologação por filial,
sem depender da leitura direta de logs e sem revelar conteúdo protegido.

- [x] Resumir por canal somente quantidade total, aprovada, pendente e rejeitada.
- [x] Listar data, Master responsável e descrição sanitizada das trocas de canal.
- [x] Não incluir referência protegida, hash, protocolo, XML, certificado, CSC, token, senha
  ou endereço técnico.
- [x] Restringir o serviço e a interface ao Master.
- [x] Manter a consulta somente leitura, sem alterar homologação ou produção.
- [x] Validar em uma única bateria 30 testes dos ciclos 136–142, permissões, isolamento,
  formulário, histórico e interface; `check` limpo e nenhuma migration pendente.
- [ ] Próximo passo exato: encerrar esta frente interna no limite possível sem CNPJ,
  credenciais e homologação reais e selecionar, pela ordem do roadmap, a primeira pendência
  interna já registrada que não dependa desses insumos externos.

Arquivos principais: apps/fiscal/services_evidencias_homologacao.py,
apps/fiscal/views.py, templates/fiscal/homologacao_goias.html e
apps/fiscal/test_evidencias_homologacao_canais.py. Migrações: nenhuma.

## Ponto de retomada — ciclo 141, 18/09/2026

Endurecida a troca do canal fiscal para impedir reaproveitamento indevido de evidências e
homologação entre Focus e SEFAZ direta.

- [x] Filtrar a cobertura exclusivamente pelo snapshot do canal selecionado na filial.
- [x] Preservar evidências antigas vinculadas ao canal em que foram produzidas.
- [x] Exigir confirmação explícita do Master quando a filial possui evidências ou
  homologação concluída no canal atual.
- [x] Informar na confirmação que a homologação será reiniciada e as evidências antigas não
  serão reaproveitadas.
- [x] Reinicializar o registro técnico como pendente após a troca confirmada, sem ativar
  produção.
- [x] Registrar na auditoria os canais anterior e novo, a quantidade preservada e o estado
  anterior da homologação, sem expor segredos.
- [x] Validar em uma única bateria 29 testes do formulário, isolamento de evidências,
  reinicialização, permissões, roteiros e regressões dos ciclos 136–140; `check` limpo e
  nenhuma migration pendente.
- [ ] Próximo passo exato: criar uma consulta Master do histórico de canais e transições por
  filial, composta apenas de metadados sanitizados, para que a troca confirmada possa ser
  revisada sem depender da leitura direta dos logs técnicos.

Arquivos principais: apps/fiscal/forms.py, apps/fiscal/views.py,
apps/fiscal/services_evidencias_homologacao.py, templates/fiscal/form.html e
apps/fiscal/test_evidencias_homologacao_canais.py. Migrações: nenhuma.

## Ponto de retomada — ciclo 140, 18/09/2026

Tornado explícito ao Master o estado do portão de conclusão e comprovado, em cenário
isolado sem rede, o caminho positivo completo da SEFAZ direta sem ativação de produção.

- [x] Exibir “Portão de conclusão bloqueado” com os motivos consolidados da cobertura.
- [x] Exibir “Portão de conclusão liberado” somente quando as sete operações estiverem
  aprovadas.
- [x] Deixar claro que a liberação permite apenas concluir o registro técnico e não ativa
  produção.
- [x] Simular no teste as sete operações da SEFAZ direta com evidências revisadas e
  aprovadas, sem chamada externa.
- [x] Provar que o registro técnico pode ser concluído com checklist e cobertura completos.
- [x] Confirmar após a conclusão que a configuração permanece em homologação.
- [ ] Próximo passo exato: endurecer a troca de canal depois que existirem evidências ou
  homologação concluída, exigindo ação explícita do Master e preservando o histórico do
  canal anterior sem reaproveitamento indevido.

Arquivos principais: templates/fiscal/homologacao_goias.html,
apps/fiscal/test_evidencias_homologacao_canais.py e
docs/REGISTRO_EVIDENCIAS_HOMOLOGACAO_CANAIS.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 139, 18/09/2026

Conectado à homologação o portão formal de cobertura completa por canal, mantendo a
liberação de produção como decisão independente e posterior.

- [x] Criar o contrato `fiscal_channel_homologation_completion_gate_v1`.
- [x] Bloquear a conclusão diante de operação sem evidência, pendente, rejeitada ou com
  lacuna interna.
- [x] Exigir simultaneamente checklist técnico automático pronto e cobertura integral de
  evidências aprovadas.
- [x] Exibir motivos objetivos do bloqueio sem revelar referência, XML, certificado ou
  credencial.
- [x] Confirmar que o portão não altera configuração do canal e não libera produção.
- [x] Validar 12 testes próprios, incluindo tentativa de conclusão com checklist automático
  totalmente pronto e cobertura incompleta.
- [ ] Próximo passo exato: tornar explícita na tela Master a situação do portão de conclusão
  e criar o cenário positivo completo para o canal SEFAZ direta em teste isolado, sem rede,
  provando que a conclusão técnica pode ser liberada sem ativar produção.

Arquivos principais: apps/fiscal/services_evidencias_homologacao.py,
apps/fiscal/views.py, templates/fiscal/homologacao_goias.html e
apps/fiscal/test_evidencias_homologacao_canais.py. Migrações: nenhuma.

## Ponto de retomada — ciclo 138, 18/09/2026

Criado o diagnóstico somente leitura da cobertura de evidências reais por operação e canal,
sem alterar o registro técnico da homologação e sem liberar produção.

- [x] Consolidar por operação os estados aprovada, pendente, rejeitada e ausente.
- [x] Dar precedência à evidência aprovada quando houver histórico de mais de uma tentativa.
- [x] Preservar como bloqueada a lacuna interna do canal mesmo que existam evidências das
  demais operações.
- [x] Exibir ao Master a cobertura das sete operações e a quantidade efetivamente aprovada.
- [x] Declarar no contrato que o diagnóstico não altera homologação nem libera produção.
- [x] Validar 10 testes próprios e 22 testes conjuntos do registro, interface, roteiros,
  roteamento e capacidade Focus.
- [ ] Próximo passo exato: criar o portão formal de conclusão que exija cobertura completa e
  falhe fechado diante de evidência pendente, rejeitada, ausente ou lacuna interna; manter a
  ativação de produção como decisão posterior e independente.

Arquivos principais: apps/fiscal/services_evidencias_homologacao.py,
apps/fiscal/views.py, templates/fiscal/homologacao_goias.html,
apps/fiscal/test_evidencias_homologacao_canais.py e apps/fiscal/tests.py.
Migrações: nenhuma.

## Ponto de retomada — ciclo 137, 18/09/2026

Disponibilizado ao Master o fluxo visual de registro e revisão manual das evidências de
homologação fiscal, mantendo somente metadados protegidos e sem upload de arquivos ou
segredos.

- [x] Adicionar formulário de registro filtrado pelo canal efetivo e pelos roteiros sem
  lacuna interna.
- [x] Listar por filial as evidências com operação, canal, estado, referência protegida e
  resultado esperado/obtido.
- [x] Separar registro da decisão, garantindo que toda evidência nova continue pendente.
- [x] Oferecer ações explícitas de aprovação e rejeição, ambas com justificativa obrigatória.
- [x] Restringir visualização e endpoints ao Master; usuário comum recebe acesso negado.
- [x] Manter certificado, CSC, token, senha, XML e arquivo bruto fora da interface e do
  armazenamento.
- [x] Validar 8 testes próprios e 20 testes conjuntos de interface, serviço, roteiros e
  roteamento; `check` sem alertas e nenhuma migration adicional pendente.
- [ ] Próximo passo exato: criar um diagnóstico somente leitura da cobertura de evidências
  aprovadas exigidas pelo canal, distinguindo pendentes, rejeitadas, ausentes e a lacuna
  interna de Eventos Focus; somente depois ligar esse diagnóstico ao bloqueio de conclusão
  da homologação.

Arquivos principais: apps/fiscal/forms.py, apps/fiscal/views.py, apps/fiscal/urls.py,
templates/fiscal/homologacao_goias.html,
apps/fiscal/test_evidencias_homologacao_canais.py e
docs/REGISTRO_EVIDENCIAS_HOMOLOGACAO_CANAIS.md. Migrações: nenhuma neste ciclo.

## Ponto de retomada — ciclo 135, 18/09/2026

Disponibilizada ao Master a consulta dos roteiros do canal selecionado diretamente na tela
de homologação da filial, em modo estritamente somente leitura.

- [x] Filtrar os 14 roteiros para as sete operações do canal efetivo da filial.
- [x] Mostrar estado pré-homologação, critério de aprovação, cenários obrigatórios e bloqueios
  atuais sem expor caminho técnico ou segredo.
- [x] Exibir seis operações Focus como “Aguarda dados reais” e Eventos como “Bloqueado”.
- [x] Manter a visão restrita ao Master, sem botão, endpoint ou ação de execução.
- [x] Preservar como falsos todos os indicadores de rede, homologação, aprovação e produção.
- [x] Validar 12 testes da tela, roteiros e roteamento; nenhuma migration ou configuração
  operacional foi alterada.
- [ ] Próximo passo exato: estruturar o registro auditável de evidências reais por
  filial/canal/operação, com estados pendente, aprovado e rejeitado, sem permitir aprovação
  automática a partir de teste offline.

Arquivos principais: apps/fiscal/views.py, templates/fiscal/homologacao_goias.html,
apps/fiscal/tests.py e docs/ROTEIROS_HOMOLOGACAO_CANAIS_FISCAIS.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 134, 18/09/2026

Criados os roteiros versionados de futura homologação para cada combinação de canal e
operação. Os contratos organizam cenários, evidências, critérios e bloqueios, mas são
deliberadamente não executáveis enquanto faltarem dados e credenciais reais.

- [x] Versionar `fiscal_channel_homologation_runbook_v1` a partir da matriz de qualificação
  offline já comprovada.
- [x] Criar 14 roteiros separados: sete operações para Focus e sete para SEFAZ direta GO.
- [x] Exigir em cada roteiro identificação da filial/canal/ambiente, responsável, versão,
  hash sem segredos, retorno protegido, status, protocolo e confronto esperado–obtido.
- [x] Definir cenários de idempotência, timeout/recuperação, rejeição controlada, consulta,
  cancelamento, inutilização, eventos e cursor DF-e conforme a operação.
- [x] Manter 13 roteiros em `AGUARDA_DEPENDENCIAS_EXTERNAS` e Eventos Focus em
  `BLOQUEADO_LACUNA_INTERNA`.
- [x] Fixar `executavel_agora`, `rede_permitida`, `producao_permitida` e `aprovado` como
  falsos em todos os roteiros.
- [x] Validar 8 testes conjuntos dos roteiros e da matriz de qualificação; nenhuma migration,
  credencial, certificado, endpoint ou flag operacional foi alterado.
- [ ] Próximo passo exato: disponibilizar ao Master a consulta desses roteiros por filial e
  canal, sem botão de execução; depois estruturar o registro auditável das evidências reais.

Arquivos principais: apps/fiscal/roteiros_homologacao_canais.py,
apps/fiscal/test_roteiros_homologacao_canais.py e
docs/ROTEIROS_HOMOLOGACAO_CANAIS_FISCAIS.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 133, 18/09/2026

Levado o roteamento efetivo para o diagnóstico administrativo por filial, sem confundir
estrutura local com homologação real. A matriz detalhada do canal permanece visível somente
ao Master.

- [x] Criar o contrato local `fiscal_branch_channel_capabilities_v1`, sem instanciar
  adaptadores, ler credenciais ou acessar rede.
- [x] Exibir autorização/rejeições, consulta, cancelamento, inutilização, DF-e, CC-e e
  manifestação conforme o canal escolhido na filial.
- [x] Mostrar Focus com cinco de sete capacidades estruturais e bloquear visualmente CC-e e
  manifestação enquanto não houver implementação específica.
- [x] Mostrar SEFAZ direta GO com sete de sete capacidades estruturais, mantendo todas como
  pendentes de homologação real e sem produção liberada.
- [x] Restringir a matriz detalhada ao Master; gerente e demais perfis não recebem a visão de
  escolha/configuração do canal.
- [x] Corrigir caixa DF-e, detalhe fiscal e manifestação para consultarem o diagnóstico da
  filial concreta, eliminando o indicador global potencialmente divergente.
- [x] Validar 38 testes de canais, eventos, DF-e e tela Master, mais 11 testes completos da
  caixa DF-e; confirmar ausência de migrations.
- [ ] Próximo passo exato: criar os roteiros versionados de homologação e coleta de evidências
  por operação/canal, com critérios de aprovação e bloqueios explícitos, sem executar rede.

Arquivos principais: apps/fiscal/roteamento_operacoes_fiscais.py, apps/fiscal/views.py,
templates/fiscal/homologacao_goias.html e templates/fiscal/dfe_recebidos.html.
Migrações: nenhuma.

## Ponto de retomada — ciclo 132, 17/09/2026

Alinhado o roteamento das operações fiscais auxiliares ao canal técnico escolhido pelo
Master em cada filial. A seleção deixou de valer somente para emissão e passou a orientar
também DF-e, CC-e e manifestação, sem ativar rede ou produção.

- [x] Criar um resolvedor único e explícito de operação/canal por filial.
- [x] Direcionar a distribuição DF-e para Focus ou SEFAZ direta conforme a seleção da
  filial, preservando a compatibilidade global apenas no modo `PADRAO_SERVIDOR`.
- [x] Direcionar CC-e e manifestação para os módulos diretos quando a filial usa
  `SEFAZ_DIRETA_GO`.
- [x] Bloquear com mensagem controlada CC-e e manifestação quando o canal Focus estiver
  selecionado, pois essas operações não possuem adaptador Focus implementado.
- [x] Garantir que `DESATIVADO` não carregue adaptador auxiliar e que a conexão direta seja
  recusada fora de Goiás.
- [x] Validar 34 testes de roteamento, DF-e, CC-e e manifestação; manter banco, migrations,
  credenciais, certificados, rede e produção inalterados.
- [ ] Próximo passo exato: exibir no diagnóstico administrativo a capacidade efetiva por
  filial e canal, incluindo os bloqueios de Eventos Focus; depois preparar os roteiros de
  homologação e coleta de evidências por operação.

Arquivos principais: apps/fiscal/roteamento_operacoes_fiscais.py,
apps/fiscal/dfe_adapters.py, apps/fiscal/cce_adapters.py,
apps/fiscal/manifestacao_adapters.py e serviços associados. Migrações: nenhuma.

## Ponto de retomada — ciclo 131, 17/09/2026

Fechado um filtro exclusivamente numérico residual posterior aos adaptadores: o serviço de
DF-e e o parser de NF-e recebida agora preservam CNPJ e chave alfanuméricos até a consulta,
comparação cadastral e persistência.

- [x] Substituir a remoção de letras por canonicalização de CNPJ na identificação da filial,
  do destinatário, do emitente e do fornecedor do XML recebido.
- [x] Preservar a chave estrutural de 44 caracteres em resumos, eventos, XML processado e
  comparação com o protocolo de autorização.
- [x] Entregar ao adaptador DF-e o CNPJ canônico da filial, sem reduzir a identidade a
  dígitos antes da consulta.
- [x] Evoluir a auditoria viva para `alphanumeric_cnpj_phase5_static_audit_v8`, incluindo os
  consumidores de persistência DF-e e do parser de Compras na Fase 6.
- [x] Validar 8 testes da Fase 6, 12 testes conjuntos com a auditoria e 16 testes do fluxo de
  importação XML; nenhuma migration foi criada.
- [x] Registrar que a suíte ampla de Compras executou 64 testes e encontrou duas falhas em
  fixtures financeiras antigas que tentam violar a restrição
  `financeiro_conta_baixa_integral_coerente`, fora dos arquivos e do fluxo alterados.
- [ ] Próximo passo exato: alinhar o roteamento por filial de emissão, DF-e, CC-e e
  manifestação, registrando o canal realmente executado e bloqueando operações que o canal
  escolhido não implemente, sem ativar rede ou produção.

Arquivos principais: apps/fiscal/services_dfe.py, apps/compras/services_xml.py,
apps/fiscal/test_cnpj_phase6_channels.py e apps/fiscal/auditoria_fase5_cnpj.py.
Migrações: nenhuma.

## Ponto de retomada — ciclo 130, 17/09/2026

Criada a matriz formal de qualificação offline dos canais fiscais. O diagnóstico cobre as
mesmas sete operações nos dois canais e impede que evidência local seja confundida com
homologação real ou liberação de produção.

- [x] Versionar o contrato `fiscal_channel_offline_qualification_matrix_v1` sem acesso à
  rede, leitura de credenciais ou alteração de configuração operacional.
- [x] Cobrir autorização, consulta, rejeição, cancelamento, inutilização, eventos e DF-e
  separadamente para Focus e SEFAZ direta GO.
- [x] Vincular cada classificação a marcadores reais de implementação e testes existentes,
  falhando fechado quando a evidência local desaparece.
- [x] Confirmar seis operações Focus como compatíveis offline e registrar Eventos como
  lacuna interna, pois o adaptador Focus atual não expõe CC-e nem manifestação.
- [x] Confirmar as sete operações da SEFAZ direta como compatíveis offline, inclusive CC-e,
  manifestação e distribuição DF-e.
- [x] Manter todos os indicadores de homologação real, encerramento e produção como falsos,
  com dependências externas explícitas por canal.
- [x] Validar 4 testes próprios da matriz e 58 testes conjuntos dos adaptadores Focus,
  SEFAZ direta, eventos e DF-e; confirmar também ausência de migrations.
- [ ] Próximo passo exato: decidir e registrar se Eventos fará parte do escopo Focus ou será
  capacidade exclusiva da SEFAZ direta; em seguida, criar os roteiros de execução e coleta
  de evidências por operação, sem chamadas externas antes das credenciais reais.

Arquivos principais: apps/fiscal/qualificacao_canais_fiscais.py,
apps/fiscal/test_qualificacao_canais_fiscais.py e
docs/MATRIZ_QUALIFICACAO_CANAIS_FISCAIS.md. Migrações: nenhuma.

## Ponto de retomada — ciclo 129, 17/09/2026

Concluído o segundo subciclo offline da Fase 6: as chaves de acesso alfanuméricas deixaram
de passar por filtros exclusivamente numéricos nos retornos Focus e SEFAZ direta. A
canonicalização estrutural do canal foi separada da validação integral de DV já existente na
fronteira central do ERP.

- [x] Criar canonicalização estrutural explícita para a chave de 44 caracteres, preservando
  letras somente nas 12 posições pertencentes ao CNPJ.
- [x] Preservar a chave retornada pela Focus em autorização, consulta e XML processado,
  comparando resposta e `infNFe/@Id` sem descartar letras.
- [x] Preservar a chave e o número do documento na distribuição DF-e Focus.
- [x] Preservar a chave no núcleo SEFAZ direto usado por autorização, consulta,
  cancelamento, CC-e, manifestação e detecção de SVC.
- [x] Preservar chaves de NF-e, resumos e eventos na distribuição DF-e direta.
- [x] Corrigir a inutilização direta para usar o CNPJ canônico completo na identificação e
  no XML, sem alterar série, faixa ou justificativa.
- [x] Validar uma chave real de teste formada com CNPJ alfanumérico nos dois canais e manter
  as regressões numéricas existentes.
- [x] Fechar o consumidor genérico de lotes DF-e para documentos e eventos, preservando a
  chave canônica antes da persistência.
- [x] Evoluir a auditoria viva para `alphanumeric_cnpj_phase5_static_audit_v7`, com os três
  pontos inventariados da Fase 6 compatíveis offline.
- [x] Validar 59 testes focados e a suíte fiscal completa com 603 testes, três ignorados por
  requisitos específicos de ambiente.
- [x] Manter rede, certificados, credenciais, endpoints, ambientes, banco, migrations,
  transmissão automática e produção inalterados.
- [ ] Próximo passo exato: criar a matriz de qualificação offline separada por canal e
  operação (autorização, consulta, rejeição, cancelamento, inutilização, eventos e DF-e),
  explicitando evidências aprovadas e dependências externas antes da homologação real.

Arquivos principais: apps/fiscal/chave_acesso.py,
apps/fiscal/focus_sefaz_adapter.py, apps/fiscal/focus_dfe_adapter.py,
apps/fiscal/sefaz_direta/adapter.py, apps/fiscal/sefaz_direta/dfe.py e testes associados.
Migrações: nenhuma.

## Ponto de retomada — ciclo 128, 17/09/2026

Iniciada a Fase 6 original com a compatibilização offline e separada da identidade CNPJ
alfanumérica nos canais Focus e SEFAZ direta. Nenhum endpoint foi acessado e todas as
travas de rede, produção e transmissão automática permaneceram inalteradas.

- [x] Separar normalização de CNPJ da normalização exclusivamente numérica de chave de
  acesso, cursor, telefone, CPF e inscrição estadual.
- [x] Preservar CNPJ alfanumérico na escolha de token por filial e na inutilização Focus,
  aceitando chave de configuração canônica, mascarada ou em letras minúsculas.
- [x] Preservar destinatário e emitente na distribuição DF-e Focus sem descartar letras.
- [x] Preservar CNPJ alfanumérico no núcleo da SEFAZ direta usado por emissão,
  cancelamento, inutilização, manifestação e Carta de Correção.
- [x] Preservar CNPJ alfanumérico na distribuição DF-e direta e na resolução da
  Configuração Fiscal da filial.
- [x] Compatibilizar a fronteira CNPJ da consulta cadastral direta sem alterar CPF ou IE.
- [x] Documentar que compatibilidade interna não equivale a aceite externo da Focus ou da
  SEFAZ-GO.
- [x] Validar 4 testes novos, 77 testes focados dos adaptadores/DF-e/eventos/cadastro e a
  suíte fiscal completa com 602 testes, três ignorados por requisitos específicos de ambiente.
- [x] Manter credenciais, certificado A1, CSC, endpoints, banco, migrations, rede,
  transmissão automática, homologação real e produção inalterados.
- [ ] Próximo passo exato: compatibilizar e provar as chaves alfanuméricas retornadas pelos
  dois canais em autorização, consulta, XML processado, cancelamento, CC-e e DF-e, mantendo
  Focus e SEFAZ direta em baterias independentes e sem rede.

Arquivos principais: apps/fiscal/focus_sefaz_adapter.py,
apps/fiscal/focus_dfe_adapter.py, apps/fiscal/sefaz_direta/adapter.py,
apps/fiscal/sefaz_direta/dfe.py, apps/fiscal/sefaz_direta/cadastro.py e testes associados.
Migrações: nenhuma.

## Ponto de retomada — ciclo 127, 17/09/2026

Concluída a compatibilidade da identidade CNPJ alfanumérica nos consumidores externos ao
núcleo fiscal. Sincronização e licenciamento agora usam a mesma representação canônica de
14 caracteres, preservam letras e aceitam a máscara oficial sem criar identidades paralelas.

- [x] Preservar letras na seleção da credencial individual de sincronização, inclusive com
  chave de configuração mascarada ou em letras minúsculas.
- [x] Canonicalizar o CNPJ da Empresa na recepção de eventos sem alterar a precedência da
  autenticação, evitando revelar validações cadastrais antes de validar o token.
- [x] Resolver Empresa e Filial pela identidade canônica, aceitando representação pura ou
  máscara oficial e recusando formato desconhecido sem correção silenciosa.
- [x] Serializar Empresa e Filial em eventos de saída com os 14 caracteres completos, sem
  descarte de letras.
- [x] Canonicalizar o vínculo assinado do licenciamento em concessão, renovação, desafio e
  liberação emergencial offline.
- [x] Impedir que comparações do licenciamento considerem somente os dígitos e aceitem por
  engano duas identidades alfanuméricas diferentes.
- [x] Adicionar `ASAAS_SUPORTA_CNPJ_ALFANUMERICO`, desligada por padrão, e bloquear a
  publicação externa quando o provedor não declarar capacidade, preservando a fatura interna.
- [x] Quando a capacidade for explicitamente habilitada, enviar ao Asaas o CNPJ canônico
  completo, sem remover letras.
- [x] Documentar a configuração segura do Asaas e a exigência de homologação no sandbox
  antes da ativação.
- [x] Validar 5 testes novos focados e 96 testes das suítes completas de Empresas e
  Licenciamento, sem falhas.
- [x] Manter banco, modelos, migrations, credenciais reais, rede, Focus, SEFAZ direta e
  ambientes operacionais inalterados.
- [ ] Próximo passo exato: preparar a Fase 6 de homologação separada dos canais Focus e
  SEFAZ direta, começando por contratos e testes offline, sem emissão real e sem ativar
  credenciais ou certificados.

Arquivos principais: apps/empresas/credenciais_sincronizacao.py,
apps/empresas/services_sincronizacao.py, apps/empresas/services_eventos_entrada.py,
apps/empresas/views.py, apps/licenciamento/services.py, apps/licenciamento/views.py,
config/settings.py e testes associados. Migrações: nenhuma.

## Ponto de retomada — ciclo 126, 17/09/2026

Os 11 pontos originais permanecem compatíveis e o inventário foi ampliado após auditoria
independente, que identificou consumidores internos adicionais. A auditoria viva evoluiu para
alphanumeric_cnpj_phase5_static_audit_v6, com 17 pontos internos: 16 compatíveis offline e
um risco residual explícito de hardware.

- [x] Exigir DV válido do CNPJ do emitente antes de formar chave, XML, QR Code ou DANFE,
  sem corrigir silenciosamente cadastro legado inválido.
- [x] Preservar e canonicalizar CNPJ alfanumérico do destinatário da NF-e de pedido online,
  incluindo máscara e letras minúsculas, com recusa de estrutura ou DV inválido.
- [x] Respeitar o tipo documental explícito no snapshot do pedido e só inferir CPF/CNPJ
  quando a identidade correspondente for efetivamente válida.
- [x] Comprovar em XML real de teste que dest/CNPJ recebe a identidade alfanumérica
  completa, sem descarte de letras.
- [x] Detectar tpEmis=9 na posição correta de chave numérica ou alfanumérica validada,
  preservando o reconhecimento pelo status antes da existência da chave.
- [x] Validar a chave no servidor antes de montar o payload do Desktop e preservar os 44
  caracteres, em maiúsculas e blocos de quatro, no texto RAW/ESC-POS.
- [x] Preservar o QR Code nativo do Desktop e comprovar em bytes que ele continua no cupom.
- [ ] Code 128 RAW/ESC-POS: não implementado sem uma base genérica comprovada para as
  impressoras suportadas. O DANFE HTML continua com Code 128 híbrido C/A; o caminho RAW
  permanece com chave textual completa e QR Code até homologação de hardware.
- [x] Sanear somente fixtures de teste alcançadas pela nova invariância de DV, usando o
  catálogo protegido; nenhuma identidade, cadastro ou dado operacional foi alterado.
- [x] Validar 60 testes focados Django, 3 testes focados do Desktop e 718 testes das suítes
  Fiscal, PDV e Marketplace, com 6 ignorados por requisitos específicos de ambiente.
- [x] Manter Focus, SEFAZ direta, DF-e, sincronização, licenciamento, credenciais,
  certificados, rede, banco de produção e ambientes operacionais inalterados.
- [ ] Próximo passo exato: compatibilizar a identidade CNPJ alfanumérica fora do fiscal —
  credenciais e eventos de sincronização, resolução de Empresa/Filial, licenciamento,
  challenge/release offline e provedor externo — antes de iniciar a Fase 6.

Arquivos principais: apps/fiscal/chave_acesso.py, apps/fiscal/services.py,
apps/marketplace/documentos_destinatario.py, apps/marketplace/models.py,
apps/pdv/views.py, desktop_pdv/devices/printing.py,
apps/fiscal/auditoria_fase5_cnpj.py e testes associados. Migrações: nenhuma.

## Ponto de retomada — ciclo 114, 14/09/2026

Criado `alphanumeric_cnpj_canonical_write_gate_v1`, portão puro que prepara a escrita canônica de CNPJ nas fronteiras Empresa, Filial, Cliente pessoa jurídica e Fornecedor pessoa jurídica. O contrato não consulta banco, não altera objetos e mantém a persistência bloqueada em todos os resultados.

- [x] Separar criação e atualização sem acoplar formulários, modelos ou serviços.
- [x] Exigir escopo da empresa para Filial, Cliente pessoa jurídica e Fornecedor pessoa jurídica.
- [x] Exigir formato oficial e dígito verificador válido para a proposta.
- [x] Preparar representação canônica em criação, sem autorizar persistência.
- [x] Reconhecer atualização equivalente sem propor troca de identidade.
- [x] Exigir valor atual válido em atualização e impedir correção automática do legado.
- [x] Manter troca de identidade bloqueada até controles externos de colisão, titularidade, autorização e auditoria.
- [x] Proteger o valor atual completo no diagnóstico por impressão digital reduzida.
- [x] Marcar somente a fase estrutural 4 como concluída, preservando todos os consumidores operacionais desligados.
- [x] Confirmar 640 arquivos Python, cinco importações do catálogo autorizadas em testes e zero em runtime.
- [x] Reexecutar inventário geral: 711 arquivos, 332 candidatos em 56 arquivos e zero `_REVISAR`.
- [x] Validar 14 testes do ciclo, 70 testes focados acumulados e 531 testes da suíte fiscal completa.
- [x] Manter banco, modelos, migrações, credenciais, certificados, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 115: comparação sombra executada sobre os formulários reais, sem persistência ou consumidor operacional.

Arquivos: `apps/fiscal/portao_escrita_canonica_cnpj.py`, `apps/fiscal/test_portao_escrita_canonica_cnpj.py`, `apps/fiscal/estrategia_normalizacao_cnpj.py` e contratos auxiliares de retomada. Documentação: [PORTAO_ESCRITA_CANONICA_CNPJ.md](PORTAO_ESCRITA_CANONICA_CNPJ.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 113, 14/09/2026

Confirmada automaticamente a exclusão do catálogo fiscal de teste na fronteira real de empacotamento. O teste usa `git archive`, como `package_local_server.ps1`, e a defesa adicional injeta o catálogo em um pacote adulterado para confirmar a recusa por `local_server_package_content_v1`.

- [x] Mapear o empacotamento real do servidor local e confirmar uso de commit rastreável com `git archive`.
- [x] Gerar e inspecionar ZIP temporário pelo mesmo mecanismo, sem publicar artefato.
- [x] Exigir presença do portão operacional e ausência do catálogo e dos testes associados.
- [x] Confirmar no ensaio real 588 entradas, zero arquivos Python de teste e zero catálogo.
- [x] Remover o ZIP temporário após a inspeção.
- [x] Confirmar segunda barreira no validador comercial de conteúdo.
- [x] Reinserir o caminho exato do catálogo em pacote de teste adulterado e exigir recusa.
- [x] Validar nove testes do portão, o cenário comercial específico e 523 testes da suíte fiscal completa.
- [x] Reexecutar inventário geral: 708 arquivos, 332 candidatos em 56 arquivos e zero `_REVISAR`.
- [x] Manter empacotador, publicador, Central, artefatos publicados e ambientes inalterados.
- [x] Manter banco, modelos, migrações, credenciais, certificados, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 114: portão puro de escrita canônica definido, sem consumidor operacional.

Arquivos: `apps/fiscal/test_auditoria_importacoes_catalogo_teste.py` e `apps/configuracoes/tests.py`. Documentação: [VERIFICACAO_EMPACOTAMENTO_CATALOGO_TESTE.md](VERIFICACAO_EMPACOTAMENTO_CATALOGO_TESTE.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 112, 14/09/2026

O portão `fiscal_test_catalog_import_gate_v1` foi integrado a `scripts/test_regression.ps1` antes da criação dos argumentos e da execução das suítes. A proteção vale para os perfis rápido e completo e interrompe a regressão imediatamente diante de não conformidade.

- [x] Reutilizar a rotina padrão existente, sem criar fluxo paralelo.
- [x] Executar `auditar_importacoes_catalogo_teste` antes de qualquer grupo de testes.
- [x] Aplicar a mesma barreira aos perfis rápido e completo.
- [x] Interromper a rotina quando o comando retornar código diferente de zero.
- [x] Testar automaticamente presença, ordem anterior aos testes e tratamento de falha.
- [x] Validar a sintaxe PowerShell da rotina sem erros.
- [x] Executar o portão integrado: 638 arquivos Python, quatro referências autorizadas e zero em runtime.
- [x] Atualizar README e roteiro de estabilização para usar a regressão padrão.
- [x] Validar oito testes próprios acumulados, 61 testes focados acumulados e 522 testes da suíte fiscal completa.
- [x] Manter código operacional, banco, modelos, migrações, credenciais, certificados, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 113: exclusão comprovada no ZIP real e recusa confirmada após reinserção manual.

Arquivos: `scripts/test_regression.ps1`, `apps/fiscal/test_auditoria_importacoes_catalogo_teste.py`, `apps/fiscal/auditoria_importacoes_catalogo_teste.py`, `README.md` e `docs/LIMPEZA_ESTABILIZACAO.md`. Documentação relacionada: [PORTAO_IMPORTACOES_CATALOGO_IDENTIDADES_TESTE.md](PORTAO_IMPORTACOES_CATALOGO_IDENTIDADES_TESTE.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 111, 14/09/2026

Criado `fiscal_test_catalog_import_gate_v1` e o comando `auditar_importacoes_catalogo_teste`. O portão analisa a árvore sintática dos arquivos Python sem importar módulos e recusa referências diretas ou dinâmicas ao catálogo fora das fronteiras reconhecidas de teste.

- [x] Analisar todos os arquivos Python sob `apps` sem executar código analisado.
- [x] Reconhecer `import`, `from ... import`, `__import__` e `import_module` com módulo literal.
- [x] Permitir uso somente em `test_*.py`, `tests.py` ou pasta `tests`.
- [x] Não tratar simples menção textual ao módulo como importação.
- [x] Fechar o portão diante de erro de leitura ou sintaxe.
- [x] Fazer o comando terminar com erro diante de não conformidade.
- [x] Analisar 638 arquivos Python, com quatro referências autorizadas em testes e zero em runtime.
- [x] Confirmar zero erros de leitura/sintaxe e zero consultas ao banco.
- [x] Reexecutar inventário geral: 707 arquivos, 332 candidatos em 56 arquivos e zero `_REVISAR`.
- [x] Validar sete testes próprios, 60 testes focados acumulados e 521 testes da suíte fiscal completa.
- [x] Manter código operacional, dados, modelos, migrações, credenciais, certificados, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 112: comando integrado antes das suítes nos perfis rápido e completo.

Arquivos: `apps/fiscal/auditoria_importacoes_catalogo_teste.py`, `apps/fiscal/management/commands/auditar_importacoes_catalogo_teste.py` e `apps/fiscal/test_auditoria_importacoes_catalogo_teste.py`. Documentação: [PORTAO_IMPORTACOES_CATALOGO_IDENTIDADES_TESTE.md](PORTAO_IMPORTACOES_CATALOGO_IDENTIDADES_TESTE.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 110, 14/09/2026

Concluída a primeira adoção gradual de `fiscal_test_identity_catalog_v1` em um novo caso do portão puro de leitura dupla. O cenário usa o papel `FILIAL` para comparar forma canônica e mascarada, preserva a entrada e confirma que o diagnóstico não expõe o documento.

- [x] Adotar o catálogo em um caso novo, sem substituir teste ou fixture existente.
- [x] Ler o ambiente `test` da configuração efetiva por `override_settings`.
- [x] Exercitar a fronteira isolada `FILIAL`, sem consumidor operacional.
- [x] Confirmar equivalência entre representação pura e mascarada.
- [x] Confirmar ausência das duas representações no diagnóstico retornado.
- [x] Confirmar que a lista de entrada permanece inalterada.
- [x] Manter inventário estático em 703 arquivos, 332 candidatos, 56 arquivos com candidatos e zero `_REVISAR`.
- [x] Não substituir nenhum dos 332 candidatos existentes.
- [x] Validar 17 testes puros do catálogo/portão, 53 testes focados acumulados e 514 testes da suíte fiscal completa.
- [x] Manter banco, modelos, migrações, credenciais, certificados, licenças, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 111: verificação estática criada e executada sem encontrar importação em runtime.

Arquivos: `apps/fiscal/test_portao_leitura_dupla_cnpj.py` e `apps/fiscal/portao_leitura_dupla_cnpj.py`. Documentação: [CATALOGO_IDENTIDADES_FISCAIS_TESTE.md](CATALOGO_IDENTIDADES_FISCAIS_TESTE.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 109, 14/09/2026

Criado `fiscal_test_identity_catalog_v1`, catálogo central destinado somente a testes novos ou naturalmente modificados. Os quatro papéis usam bases alfanuméricas determinísticas identificadas por `TST`, calculam o DV pelo normalizador isolado e continuam sem qualquer alegação de titularidade.

- [x] Definir papéis distintos para empresa matriz, filial, fornecedor e cliente pessoa jurídica.
- [x] Gerar identificadores determinísticos com DV estruturalmente válido, sem cadastrar dados.
- [x] Ler o ambiente efetivamente configurado, sem aceitar ambiente informado pelo chamador.
- [x] Permitir somente `development`/`test` e finalidades de teste unitário ou integração local.
- [x] Recusar homologação, produção, finalidade operacional e código desconhecido.
- [x] Não expor documentos completos na descrição do catálogo.
- [x] Manter explícito que validade estrutural não prova titularidade.
- [x] Excluir o suporte de artefatos gerados por `git archive` usando a regra existente para `test_*.py`.
- [x] Preservar os 331 candidatos anteriores, sem substituição em massa.
- [x] Reexecutar inventário: 703 arquivos, 332 candidatos em 56 arquivos e zero categorias `_REVISAR`.
- [x] Confirmar que o único candidato adicional pertence ao teste da nova classificação.
- [x] Validar seis testes próprios, 52 testes focados acumulados e 513 testes da suíte fiscal completa.
- [x] Manter base, modelos, migrações, credenciais, certificados, licenças, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 110: primeiro caso novo adotado no portão isolado de leitura dupla, sem reescrever fixtures.

Arquivos: `apps/fiscal/test_support_identidades_fiscais.py`, `apps/fiscal/test_catalogo_identidades_fiscais.py`, `apps/fiscal/inventario_estatico_identidades_fiscais.py`, `apps/fiscal/test_inventario_estatico_identidades_fiscais.py` e `apps/fiscal/politica_identidades_fiscais.py`. Documentação: [CATALOGO_IDENTIDADES_FISCAIS_TESTE.md](CATALOGO_IDENTIDADES_FISCAIS_TESTE.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 108, 14/09/2026

Criado `static_fiscal_identity_candidate_inventory_v1` e o comando `inventariar_identidades_fiscais_estaticas`. O inventário estático usa delimitadores literais, duas posições finais numéricas e contexto fiscal na própria linha para evitar códigos/palavras. O relatório protege os valores e classifica todos os candidatos por finalidade.

- [x] Ler somente fontes sob `apps` e `docs`, sem consultar banco.
- [x] Reconhecer máscara completa, bloco CNPJ de 14 posições e chave de 44 posições.
- [x] Exigir duas posições finais numéricas nos candidatos a CNPJ alfanumérico.
- [x] Exigir aspas, crases ou tags XML para não capturar nomes de código.
- [x] Exigir contexto de identidade na mesma linha para blocos de 14 posições.
- [x] Classificar máscara, demonstração, modelo, validação, XML, chave, documentação e regras do inventário.
- [x] Reduzir falsos positivos do primeiro ensaio de 3.602 para 331 candidatos.
- [x] Inventariar 700 arquivos, com 331 candidatos distribuídos em 56 arquivos.
- [x] Zerar categorias `_REVISAR` após revisão por caminho e linha sem expor valores.
- [x] Confirmar ausência de identidade operacional fixa escondida no runtime.
- [x] Disponibilizar resumo padrão e detalhes protegidos por hash opcional.
- [x] Validar 46 testes focados e 507 testes da suíte fiscal completa.
- [x] Manter fontes, fixtures, base, modelos, migrações, credenciais, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 109: catálogo central protegido criado para adoção gradual, sem substituição em massa.

Arquivos: `apps/fiscal/inventario_estatico_identidades_fiscais.py`, `apps/fiscal/management/commands/inventariar_identidades_fiscais_estaticas.py` e `apps/fiscal/test_inventario_estatico_identidades_fiscais.py`. Documentação: [INVENTARIO_ESTATICO_IDENTIDADES_FISCAIS.md](INVENTARIO_ESTATICO_IDENTIDADES_FISCAIS.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 107, 14/09/2026

Criado `fiscal_identity_development_policy_v1`. A política separa exemplo normativo, dado fictício de desenvolvimento, identidade real pendente e identidade real verificada; deixa explícito que formato/DV válido não provam titularidade e não libera qualquer canal fiscal. Os comandos que gravam bases fictícias agora são bloqueados antes do banco em homologação e produção.

- [x] Separar validade estrutural de verificação de titularidade.
- [x] Classificar exemplo normativo, fictício de desenvolvimento, real pendente e real verificada.
- [x] Restringir exemplos e dados fictícios a `development` e `test` com finalidade não operacional.
- [x] Proibir exemplo/fictício em credencial, licença, certificado, homologação, produção e emissão.
- [x] Manter portões fiscais próprios mesmo para futura identidade real verificada.
- [x] Proteger `criar_dados_iniciais` contra execução em homologação e produção.
- [x] Proteger `popular_demo` contra execução em homologação e produção.
- [x] Confirmar nos testes que a recusa acontece com zero consultas SQL.
- [x] Inventariar inicialmente 48 arquivos de teste, três executáveis e cinco documentos com padrões candidatos.
- [x] Registrar que a busca é conservadora e ainda exige classificação semântica dos valores.
- [x] Validar 37 testes focados e 498 testes da suíte fiscal completa.
- [x] Manter base local, fixtures, modelos, migrações, credenciais, licenças, ambientes fiscais, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 108: candidatos classificados estaticamente sem reescrever valores.

Arquivos: `apps/fiscal/politica_identidades_fiscais.py`, `apps/fiscal/test_politica_identidades_fiscais.py`, `apps/configuracoes/management/commands/criar_dados_iniciais.py` e `apps/configuracoes/management/commands/popular_demo.py`. Documentação: [POLITICA_IDENTIDADES_FISCAIS_DESENVOLVIMENTO.md](POLITICA_IDENTIDADES_FISCAIS_DESENVOLVIMENTO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 106, 14/09/2026

Criado `alphanumeric_cnpj_company_branch_shadow_adapter_v1`. O adaptador reproduz em observação a busca atual de Empresa ativa e a busca de Filial escopada pela empresa, compara seus resultados com o portão canônico e não interfere na identidade utilizada pelo sistema. O relatório agregado não expõe CNPJ nem IDs.

- [x] Preservar no ensaio o filtro atual de Empresa ativa.
- [x] Preservar no ensaio o escopo obrigatório da Filial pela empresa.
- [x] Executar busca textual atual e portão canônico sem trocar o resultado operacional.
- [x] Classificar concordância, ganho canônico, recusa segura, ambiguidade e divergência.
- [x] Não permitir que igualdade textual prevaleça sobre ambiguidade canônica.
- [x] Omitir CNPJ, ID de Empresa e ID de Filial do relatório.
- [x] Capturar SQL nos testes e exigir exclusivamente `SELECT`.
- [x] Executar ensaio local agregado: 16 observações, 34 consultas somente `SELECT`.
- [x] Confirmar 16 casos em que a busca legada seleciona e o portão recusa DV inválido.
- [x] Validar 29 testes focados e 490 testes da suíte fiscal completa.
- [x] Manter buscas atuais, dados, modelos, migrações, credenciais, licenças, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 107: política de identidades fiscais definida e comandos fictícios protegidos sem modificar a base atual.

Arquivos: `apps/fiscal/adaptador_sombra_cnpj.py` e `apps/fiscal/test_adaptador_sombra_cnpj.py`. Documentação: [ADAPTADOR_SOMBRA_CNPJ_EMPRESA_FILIAL.md](ADAPTADOR_SOMBRA_CNPJ_EMPRESA_FILIAL.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 105, 14/09/2026

Criado `alphanumeric_cnpj_dual_read_gate_v1`, um portão puro e ainda sem consumidores para comparar CNPJ textual e canônico nas fronteiras Empresa, Filial, Licença e Credencial. A seleção só ocorre com um candidato válido; fronteira e escopo são aplicados antes da comparação, cadastro inválido não é corrigido e igualdade textual nunca desambigua duas identidades canônicas.

- [x] Exigir consulta com formato e DV oficiais válidos.
- [x] Exigir fronteira explícita entre Empresa, Filial, Licença e Credencial.
- [x] Exigir escopo da empresa quando os candidatos forem escopados.
- [x] Comparar igualdade textual e canônica sem regravar valores.
- [x] Registrar divergência entre valor armazenado e forma canônica.
- [x] Recusar mais de uma correspondência mesmo quando uma delas for textual exata.
- [x] Não selecionar nem corrigir silenciosamente cadastro com formato ou DV inválido.
- [x] Recusar candidato malformado ou sem origem/identificador.
- [x] Não devolver CNPJ completo no diagnóstico; usar impressão digital reduzida.
- [x] Validar CNPJ alfanumérico oficial em fronteira isolada.
- [x] Validar 21 testes focados e 482 testes da suíte fiscal completa.
- [x] Manter banco, modelos, migrações, buscas reais, licença, credenciais, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 106: adaptador somente leitura ensaiado em paralelo, sem alterar o resultado operacional.

Arquivos: `apps/fiscal/portao_leitura_dupla_cnpj.py` e `apps/fiscal/test_portao_leitura_dupla_cnpj.py`. Documentação: [PORTAO_LEITURA_DUPLA_CNPJ.md](PORTAO_LEITURA_DUPLA_CNPJ.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 104, 14/09/2026

Criado `alphanumeric_cnpj_readonly_audit_v1` e o comando `auditar_cnpj_alfanumerico`. A auditoria usa somente `SELECT`, protege CNPJs e chaves com ocultação/impressão digital, ignora CPF reconhecido no campo misto e classifica repetições como esperadas, revisáveis ou bloqueantes. O ensaio local não é aceite de produção e não consultou credenciais.

- [x] Consultar Empresa, Filial, Fornecedor, Cliente e CNPJ de referência em DF-e.
- [x] Consultar chaves em Documento Fiscal, sincronização, Entrada de Compra, Evidência e DF-e/eventos.
- [x] Separar formato, DV, ausência obrigatória e vazio permitido.
- [x] Reconhecer CPF no campo misto de Cliente sem tratá-lo como CNPJ inválido.
- [x] Ocultar identificadores completos e usar impressão digital SHA-256 reduzida.
- [x] Não consultar tokens, certificados, senhas ou outras credenciais.
- [x] Capturar SQL nos testes e exigir exclusivamente consultas `SELECT`.
- [x] Distinguir equivalência empresa–filial, papéis distintos e colisão bloqueante.
- [x] Executar ensaio local: 20 documentos, três chaves, 17 DVs inválidos, seis equivalências esperadas e uma colisão bloqueante.
- [x] Marcar resultado local como ensaio sem aceite de produção.
- [x] Validar 11 testes focados da auditoria/estratégia e 472 testes da suíte fiscal completa.
- [x] Manter dados, modelos, migrações, normalizadores atuais, credenciais, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 105: portão puro definido sem escrita e com recusa obrigatória de identidade ambígua.

Arquivos: `apps/fiscal/auditoria_cnpj_alfanumerico.py`, `apps/fiscal/management/commands/auditar_cnpj_alfanumerico.py` e `apps/fiscal/test_auditoria_cnpj_alfanumerico.py`. Documentação: [AUDITORIA_CNPJ_ALFANUMERICO.md](AUDITORIA_CNPJ_ALFANUMERICO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 103, 14/09/2026

Criado `alphanumeric_cnpj_canonicalization_strategy_v1`, com normalização pura e isolada, cálculo oficial dos DVs do CNPJ e da chave e prévia de colisões sem acesso ao banco. O inventário registra 23 consumidores em cadastro, interface, identidade, licenciamento, vendas, compras/DF-e, fiscal, devolução, DANFE e canais. Nenhum consumidor operacional passou a usar a rotina neste ciclo.

- [x] Definir representação canônica com 14 caracteres, sem pontuação e em maiúsculas.
- [x] Aceitar somente forma pura ou máscara oficial completa.
- [x] Preservar zeros à esquerda e compatibilidade integral do CNPJ numérico.
- [x] Rejeitar símbolos extras, máscara parcial, Unicode e DV alfanumérico.
- [x] Separar canonicalização de validação do DV.
- [x] Reproduzir o DV `35` do exemplo oficial `12.ABC.345/01DE-35`.
- [x] Calcular e validar chave de 44 posições com CNPJ alfanumérico em teste isolado.
- [x] Detectar colisões entre versões mascarada/pura e maiúscula/minúscula sem alterar a entrada.
- [x] Inventariar 23 consumidores e seus riscos.
- [x] Organizar transição em seis fases, todas operacionalmente bloqueadas.
- [x] Proibir fallback para o normalizador antigo que descarta letras.
- [x] Validar 15 testes focados e 467 testes da suíte fiscal completa.
- [x] Manter banco, modelos, migrações, consumidores, credenciais, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 104: auditoria somente leitura criada e ensaiada sem transformar a base local em aceite de produção.

Arquivos: `apps/fiscal/estrategia_normalizacao_cnpj.py` e `apps/fiscal/test_estrategia_normalizacao_cnpj.py`. Documentação: [ESTRATEGIA_NORMALIZACAO_CNPJ_ALFANUMERICO.md](ESTRATEGIA_NORMALIZACAO_CNPJ_ALFANUMERICO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 102, 14/09/2026

Criado `alphanumeric_cnpj_official_evidence_v1`, que preserva e verifica por SHA-256 quatro PDFs oficiais e o pacote XSD 010f. A regra normativa deixou de ser pendência: CNPJ com 12 posições alfanuméricas e dois DVs numéricos, coexistência com o formato antigo, chave de acesso de 44 posições com letras no trecho do CNPJ, cálculo por ASCII menos 48 e módulo 11, e produção NF-e/NFC-e desde 01/07/2026. A constatação não liberou alterações operacionais.

- [x] Preservar Manual de cálculo do DV e Perguntas e respostas da Receita Federal.
- [x] Preservar NT Conjunta DF-e 2025.001 v1.00 e NT NF-e/NFC-e 2026.004 v1.01.
- [x] Registrar SHA-256 das quatro fontes e reutilizar o hash do XSD 010f.
- [x] Confirmar CNPJ `[A-Z0-9]{12}[0-9]{2}` e coexistência com CNPJs numéricos.
- [x] Confirmar DV do CNPJ por ASCII menos 48, módulo 11 e pesos de 2 a 9.
- [x] Confirmar chave de acesso de 44 posições com padrão `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`.
- [x] Confirmar DV da chave por ASCII menos 48 e módulo 11 sobre as 43 posições anteriores.
- [x] Confirmar implantação NF-e/NFC-e até 15/06/2026 em homologação e em 01/07/2026 em produção.
- [x] Registrar impacto adicional no código de barras, com Code 128 C/A quando houver letras.
- [x] Não inventar restrição de letras que a NT Conjunta deixou pendente e que a Receita/XSD posterior não adotaram.
- [x] Validar 13 testes focados e 461 testes da suíte fiscal completa.
- [x] Manter modelos, dados, migrações, geradores, credenciais, ambientes, Focus, SEFAZ direta e emissão inalterados.
- [x] Próximo passo concluído no ciclo 103: normalização canônica, inventário de consumidores e prévia de colisões definidos sem migrar dados reais.

Arquivos: `apps/fiscal/evidencia_cnpj_alfanumerico.py` e `apps/fiscal/test_evidencia_cnpj_alfanumerico.py`. Documentação: [EVIDENCIA_CNPJ_ALFANUMERICO_DFE.md](EVIDENCIA_CNPJ_ALFANUMERICO_DFE.md). Evidências: [evidencias/cnpj_alfanumerico_2026_09_14/README.md](evidencias/cnpj_alfanumerico_2026_09_14/README.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 101, 14/09/2026

Criado `issuer_xsd_compatibility_plan_v1`, que organiza cinco frentes, seis pontos de acoplamento e seis etapas bloqueadas para compatibilizar o emitente com o XSD. O levantamento confirmou que a largura atual dos campos não exige migração imediata, mas a semântica numérica do CNPJ atravessa interface, sincronização, licenciamento, buscas, compras, DF-e, chave de acesso e geradores. Também foi registrada a ausência de `enderEmit` nos geradores existentes de NFC-e e NF-e de pedido online, sem confundir código existente com canal ativo.

- [x] Mapear armazenamento de Empresa, Filial e Configuração Fiscal.
- [x] Mapear máscara, consulta, sincronização, licenciamento, compras, DF-e e geração fiscal.
- [x] Confirmar que largura do CNPJ comporta 14 caracteres, sem concluir compatibilidade semântica.
- [x] Manter possível migração do CNPJ como `NAO_DEFINIDA` até confirmar normalização e chave de acesso.
- [x] Planejar mínimos textuais na fronteira fiscal, sem truncar nem estreitar colunas.
- [x] Planejar validação da IE sem reduzir a capacidade do banco antecipadamente.
- [x] Confirmar que as escolhas de UF dos modelos correspondem a `TUfEmi`.
- [x] Registrar ausência de `enderEmit` nos dois geradores existentes.
- [x] Ordenar seis etapas, da confirmação normativa à homologação separada dos canais.
- [x] Manter todos os portões e permissões de mudança falsos.
- [x] Validar 28 testes focados da cadeia até o plano de compatibilidade.
- [x] Validar 456 testes da suíte fiscal completa.
- [x] Manter dados reais, modelos, migrações, XML, credenciais, ambientes, Focus e SEFAZ direta inalterados.
- [x] Próximo passo concluído no ciclo 102: regra oficial, chave de acesso e vigência confirmadas com fontes preservadas.

Arquivos: `apps/fiscal/plano_compatibilidade_emitente_xsd.py` e `apps/fiscal/test_plano_compatibilidade_emitente_xsd.py`. Documentação: [PLANO_COMPATIBILIDADE_EMITENTE_XSD.md](PLANO_COMPATIBILIDADE_EMITENTE_XSD.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 100, 14/09/2026

Criado `supplier_return_emit_field_specification_v1`, que descreve os 11 campos mapeados do emitente sem ler valores ou alterar o cadastro. O contrato registra a escolha CNPJ/CPF, `enderEmit` e suas posições internas, cardinalidades e formatos do XSD 010f. Também torna explícitas quatro lacunas entre o XSD e a validação atual: CNPJ alfanumérico, comprimentos mínimos de texto, formato da IE e domínio da UF.

- [x] Confrontar os 11 caminhos de `emit` com matriz e plano íntegros.
- [x] Registrar a escolha estrutural CNPJ/CPF sem presumir a identidade do caso real.
- [x] Registrar posições de `emit` e posições internas de `TEnderEmi`.
- [x] Confirmar cardinalidade 0–1 da IE e 1–1 dos demais campos no respectivo contexto.
- [x] Registrar tipos, comprimentos, padrões e enumerações do XSD auditado.
- [x] Registrar que o CNPJ alfanumérico do XSD ainda não é suportado pelo contrato atual.
- [x] Registrar diferenças de mínimo textual, formato da IE e domínio da UF.
- [x] Exigir bloqueios da origem, de compatibilidade e de serialização por campo.
- [x] Rejeitar matriz/plano adulterado e definição, bloqueio, lacuna, contagem ou política alterada.
- [x] Validar 24 testes focados da cadeia até o bloco `emit`.
- [x] Validar 452 testes da suíte fiscal completa.
- [x] Manter cadastro, valores, XML, assinatura, transmissão, Focus e SEFAZ direta inalterados.
- [x] Próximo passo concluído no ciclo 101: compatibilidade organizada em etapas e portões, sem alteração de dados.

Arquivos: `apps/fiscal/especificacao_emit_devolucao.py` e `apps/fiscal/test_especificacao_emit_devolucao.py`. Documentação: [ESPECIFICACAO_BLOCO_EMIT_DEVOLUCAO.md](ESPECIFICACAO_BLOCO_EMIT_DEVOLUCAO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 99, 14/09/2026

Criado `supplier_return_ide_field_specification_v1`, que confronta a matriz atômica e o plano por blocos para descrever os cinco campos já mapeados em `ide`. Foram registradas as posições na sequência completa, cardinalidade 1–1, fontes primárias e definições exatas do XSD auditado: comprimento de `natOp`, domínio de `idDest`, padrão IBGE de `cMunFG` e domínios de `indFinal` e `indPres`. Estrutura XSD não foi tratada como decisão fiscal.

- [x] Confirmar a ordem completa: `natOp` 3, `idDest` 11, `cMunFG` 12, `indFinal` 21 e `indPres` 22.
- [x] Registrar cardinalidade 1–1 para os cinco campos.
- [x] Registrar tipos, comprimentos, padrão e enumerações do pacote 010f auditado.
- [x] Reaproveitar fontes, tratamento da ausência, regra e estado da matriz sem transportar valores.
- [x] Distinguir candidato calculável de decisão fiscal confirmada para `idDest`.
- [x] Manter `indFinal` e `indPres` dependentes de decisão fiscal explícita.
- [x] Exigir bloqueio contextual e `SERIALIZACAO_NAO_IMPLEMENTADA` em cada campo.
- [x] Rejeitar matriz/plano adulterado e divergências de definição, cardinalidade, bloqueio, contagem ou política.
- [x] Validar 20 testes focados da cadeia e 448 testes da suíte fiscal completa.
- [x] Manter valores, elementos XML, assinatura, transmissão, Focus e SEFAZ direta desativados.
- [x] Próximo passo concluído no ciclo 100: bloco `emit` especificado e lacunas de compatibilidade registradas, sem valores ou XML.

Arquivos: `apps/fiscal/especificacao_ide_devolucao.py` e `apps/fiscal/test_especificacao_ide_devolucao.py`. Documentação: [ESPECIFICACAO_BLOCO_IDE_DEVOLUCAO.md](ESPECIFICACAO_BLOCO_IDE_DEVOLUCAO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 98, 11/09/2026

Criado `supplier_return_xsd_block_build_plan_v1`, que distribui os 105 caminhos confirmados em oito blocos na ordem e cardinalidade do XSD: `ide` 5, `emit` 11, `dest` 11, `det` 50, `total` 15, `transp` 10, `pag` 2 e `infAdic` 1. Cada campo preserva regra, estado do inventário, alternativas e bloqueios. O plano não contém valores, não cria árvore XML e mantém todos os blocos não prontos.

- [x] Agrupar os 105 caminhos confirmados pelos blocos diretos de `infNFe`.
- [x] Preservar posição e cardinalidade apuradas no XSD auditado.
- [x] Registrar regra, estado do inventário, alternativas e bloqueios por campo.
- [x] Manter os treze blocos fora do escopo sem presumir dispensa fiscal.
- [x] Exigir bloqueio de serialização em todos os campos.
- [x] Fixar bloqueios globais de aplicabilidade, instalação, aprovação e serializador.
- [x] Rejeitar ordem, contagem, cardinalidade, campo/bloco liberado e política alterada.
- [x] Corrigir validação para acumular adulteração de contagem e de campo interno.
- [x] Validar 19 testes focados da cadeia matriz–auditoria–compatibilidade–plano.
- [x] Validar 444 testes da suíte fiscal completa.
- [x] Manter valores, árvore XML, promoção, assinatura e transmissão desativados.
- [x] Próximo passo concluído no ciclo 99: bloco `ide` especificado campo a campo, sem valores ou XML.

Arquivos: `apps/fiscal/plano_blocos_xsd_devolucao.py` e `apps/fiscal/test_plano_blocos_xsd_devolucao.py`. Documentação: [PLANO_BLOCOS_XSD_DEVOLUCAO.md](PLANO_BLOCOS_XSD_DEVOLUCAO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 97, 11/09/2026

Criado o contrato `supplier_return_atomic_xsd_compatibility_v1` e o comando `confrontar_matriz_xsd_devolucao`. O verificador percorre a estrutura dos XSDs auditados e exige todas as alternativas documentadas nos destinos da matriz. O pacote 010f confirmou 105 caminhos, manteve oito marcadores de leiaute RTC pendente, reconheceu duas ausências deliberadas de tag total de base PIS/COFINS e não encontrou divergência estrutural. Compatibilidade não significa aplicabilidade, vigência ou autorização para serializar.

- [x] Religar a matriz somente depois de validar sua integridade e auditar novamente o ZIP.
- [x] Percorrer elementos globais, tipos complexos, sequências, escolhas, grupos e extensões.
- [x] Interpretar caminhos literais, curingas e alternativas documentadas.
- [x] Exigir que todas as alternativas listadas existam em algum caminho estrutural válido.
- [x] Separar marcadores de leiaute pendente e ausência deliberada de tag total.
- [x] Confirmar 105 caminhos, oito pendências de leiaute e duas ausências documentadas, com zero divergência.
- [x] Criar comando JSON reproduzível e sem escrita persistente.
- [x] Validar 21 testes focados e 440 testes da suíte fiscal completa.
- [x] Rejeitar adulteração de matriz, destino, classificação, resumo e política.
- [x] Manter schema sem promoção e XML, assinatura, Focus, SEFAZ direta e emissão bloqueados.
- [x] Próximo passo concluído no ciclo 98: 105 caminhos organizados em oito blocos, sem valores ou XML.

Arquivos: `apps/fiscal/compatibilidade_matriz_xsd.py`, `apps/fiscal/management/commands/confrontar_matriz_xsd_devolucao.py` e seus testes. Documentação: [COMPATIBILIDADE_MATRIZ_XSD_DEVOLUCAO.md](COMPATIBILIDADE_MATRIZ_XSD_DEVOLUCAO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 96, 11/09/2026

Criado o contrato `fiscal_schema_package_audit_v1` e o comando `auditar_pacote_xsd`, separando verificação técnica de instalação/promoção. A auditoria confere offline o hash do ZIP, CRC, limites, caminhos, duplicidades, conteúdo exclusivamente XSD, dependências relativas e compilação do schema raiz. O pacote 010f arquivado passou com cinco XSDs e quatro dependências. O resultado declara apenas integridade técnica: aplicabilidade, aprovação, instalação, configuração, XML e transmissão permanecem falsos.

- [x] Validar arquivo local regular, tamanho e SHA-256 esperado antes de abrir o ZIP.
- [x] Conferir CRC, limites de quantidade/tamanho e métodos de compressão.
- [x] Recusar travessia, links, letra de unidade e duplicidades sensíveis ao Windows.
- [x] Exigir somente XSD e exatamente um schema raiz.
- [x] Resolver `include`, `import` e `redefine` exclusivamente dentro do pacote.
- [x] Compilar a raiz em área temporária, sem rede nem extração persistente.
- [x] Auditar o pacote real 010f e reproduzir o inventário de cinco XSDs.
- [x] Validar 17 testes focados e 435 testes da suíte fiscal completa.
- [x] Definir a promoção candidata para `pacotes/<versão>` sem executá-la.
- [x] Manter aprovação normativa, instalação, ativação, XML, assinatura e transmissão bloqueados.
- [x] Próximo passo concluído no ciclo 97: 105 destinos confirmados, oito pendentes e duas ausências totais documentadas, sem XML ou promoção.

Arquivos: `apps/fiscal/auditoria_pacote_xsd.py`, `apps/fiscal/management/commands/auditar_pacote_xsd.py` e seus testes. Documentação: [AUDITORIA_PACOTE_XSD.md](AUDITORIA_PACOTE_XSD.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 95, 11/09/2026

O limite de entrada do futuro gerador foi formalizado no contrato `supplier_return_offline_generator_input_plan_v1`, ainda sem serialização. A leitura direta da evidência arquivada confirmou os 21 filhos de `NFe/infNFe`, suas posições e cardinalidades. Os oito blocos usados pela devolução foram distinguidos dos treze blocos atualmente fora de escopo, sem tratar estes últimos como dispensados. Os hashes do ZIP 010f e do XSD principal foram reproduzidos. A evidência existe no repositório, mas o pacote continua não instalado em `fiscal_schemas`, não aprovado e não promovido para operação.

- [x] Reproduzir os hashes do ZIP arquivado e do `leiauteNFe_v4.00.xsd` interno.
- [x] Corrigir a distinção entre evidência arquivada e schema instalado/aprovado.
- [x] Registrar a ordem e cardinalidade dos 21 blocos diretos de `infNFe`.
- [x] Marcar separadamente blocos mapeados e blocos fora do escopo atual.
- [x] Definir requisitos explícitos para os subcontratos e portões externos.
- [x] Recusar qualquer campo indisponível, destino pendente ou decisão/origem incompleta.
- [x] Tornar obrigatórios os bloqueios de instalação, aprovação, ordem operacional e serializador.
- [x] Integrar o portão à extração e à prévia fiscal somente leitura.
- [x] Validar 158 testes da devolução e 428 testes da suíte fiscal completa.
- [x] Manter XML, assinatura, certificado, Focus, SEFAZ direta e emissão desativados.
- [x] Próximo passo concluído no ciclo 96: auditoria offline e promoção versionada especificadas, sem instalação, aprovação, ativação ou XML.

Arquivos: `apps/fiscal/plano_gerador_devolucao.py`, `apps/fiscal/extracao_contrato_devolucao.py`, `apps/fiscal/rastreabilidade_leiaute_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Documentação: [PLANO_GERADOR_OFFLINE_DEVOLUCAO.md](PLANO_GERADOR_OFFLINE_DEVOLUCAO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 94, 11/09/2026

Os 115 campos do inventário da devolução foram consolidados no contrato `supplier_return_atomic_xml_matrix_v1`. Cada registro contém campo, fonte primária, tratamento da ausência, regra de aplicação, destino futuro no XML e estado do inventário. As 115 referências de destino são verificáveis e não duplicadas; pontos cujo leiaute vigente ainda não foi aprovado ficam marcados explicitamente como pendentes. O mapeamento distingue dados exigidos antes do gerador, campos condicionados e decisões que só podem existir após aprovação. Destino documentado não significa aplicabilidade fiscal nem autorização de serialização.

- [x] Reunir os 115 campos do inventário em uma matriz única e validável.
- [x] Associar a cada campo sua fonte primária e regra de ausência/aplicação.
- [x] Documentar 115 destinos futuros no leiaute da NF-e.
- [x] Preservar a evidência e o hash do pacote XSD já inventariado.
- [x] Registrar explicitamente que bases totais informativas de PIS/COFINS não possuem tag total própria em `ICMSTot`.
- [x] Rejeitar campo duplicado, fonte/regra/destino divergente e evidência XSD adulterada.
- [x] Manter `serializacao_implementada=False` para todos os campos.
- [x] Integrar a matriz à extração e à prévia fiscal somente leitura.
- [x] Manter Focus, SEFAZ direta, XML e emissão bloqueados.
- [x] Validar a regressão conjunta de 164 testes da devolução.
- [x] Próximo passo concluído no ciclo 95: limite de entrada e ordem estrutural apurados, com recusa fechada e sem assinatura ou transmissão.

Arquivos de implementação: `apps/fiscal/matriz_atomica_devolucao.py`, `apps/fiscal/extracao_contrato_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Testes: `apps/fiscal/test_matriz_atomica_devolucao.py` e `apps/fiscal/test_devolucao_fornecedor.py`. Documentação: [MATRIZ_ATOMICA_XML_DEVOLUCAO.md](MATRIZ_ATOMICA_XML_DEVOLUCAO.md), `INVENTARIO_DADOS_DEVOLUCAO.md`, `MATRIZ_RASTREABILIDADE_DEVOLUCAO.md` e este roadmap. Migrações: nenhuma.

Decisões tributárias continuam pendentes do contador e da análise normativa. O pacote XSD continua não promovido, a paridade Focus não foi fechada e a SEFAZ direta apenas transportará um futuro XML integral. Nenhuma credencial, certificado, ambiente ou feature flag foi acessado ou alterado.

## Ponto de retomada — ciclo 93, 11/09/2026

Os grupos PIS e COFINS do contrato `supplier_return_item_tax_values_v1` passaram a representar separadamente a variante estrutural candidata e sua modalidade de cálculo candidata. O XSD preservado confirma quatro escolhas exclusivas por contribuição (`Aliq`, `Qtde`, `NT` e `Outr`); em `Outr`, percentual e quantidade continuam alternativas internas. Os candidatos nascem vazios, com fonte `DECISAO_CONTADOR_PENDENTE`, estado `NAO_DEFINIDA` e confirmação falsa. O sistema não deduz a escolha pelo CST nem pelos números da memória. Quando uma escolha é fornecida para validação, apenas a compatibilidade estrutural com o CST e a modalidade é conferida, sem aplicar cálculo ou gerar grupo XML. O inventário passou a 115 campos e duas lacunas; rastreabilidade e obrigatoriedade passaram a 42 famílias.

- [x] Confirmar no XSD preservado os grupos opcionais e as quatro escolhas de PIS/COFINS.
- [x] Representar variante e modalidade de cálculo separadamente para PIS e COFINS.
- [x] Iniciar todos os candidatos vazios e não confirmados, dependentes do contador.
- [x] Registrar cardinalidade, fonte e destino XML futuro sem criar serializador.
- [x] Validar compatibilidade entre variante explicitamente candidata, CST informado e modalidade escolhida.
- [x] Exigir modalidade explícita para `PISOutr` e `COFINSOutr`.
- [x] Recusar variante inválida, CST incompatível, fonte trocada e confirmação antecipada.
- [x] Provar que base, alíquota, valor, totalização e canais não sofrem alteração.
- [x] Manter `permite_aplicar_variantes_pis_cofins=False`, XML e emissão bloqueados.
- [x] Exibir variantes e modalidades pendentes na prévia somente leitura.
- [x] Remover `VARIANTES_PIS_COFINS_NAO_MODELADAS`; restam duas lacunas.
- [x] Validar a regressão conjunta de 156 testes.
- [x] Próximo passo concluído no ciclo 94: matriz atômica consolidada com 115 destinos, sem serialização.

Arquivos de implementação alterados: `apps/fiscal/tributos_itens_devolucao.py`, `apps/fiscal/extracao_contrato_devolucao.py`, `apps/fiscal/inventario_dados_devolucao.py`, `apps/fiscal/rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/obrigatoriedade_campos_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Testes alterados: `apps/fiscal/test_tributos_itens_devolucao.py`, `apps/fiscal/test_inventario_dados_devolucao.py`, `apps/fiscal/test_rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/test_obrigatoriedade_campos_devolucao.py` e `apps/fiscal/test_devolucao_fornecedor.py`. Migrações: nenhuma. Decisões ainda pendentes: aplicabilidade dos grupos, variantes reais, modalidades, CSTs e valores do caso concreto. Dependências externas: decisão do contador, análise normativa integral e posterior homologação de cada canal. Detalhes em [VARIANTES_PIS_COFINS_DEVOLUCAO.md](VARIANTES_PIS_COFINS_DEVOLUCAO.md).

Sem cálculo novo, decisão tributária, XML, credencial, certificado, mudança de ambiente ou transmissão.

## Ponto de retomada — ciclo 92, 10/09/2026

O contrato `supplier_return_returned_ipi_policy_v1` passou a representar o enquadramento legal do IPI por item como decisão própria, separada tanto do IPI informativo da memória quanto de `impostoDevol`. O XSD preservado confirma `cEnq` com cardinalidade 1-1 dentro de `IPI` e tipo `TString` de 1 a 3 caracteres; ele não prova, isoladamente, que o grupo IPI se aplique ao caso nem qual código deva ser usado. Por isso o candidato nasce vazio, com fonte `DECISAO_CONTADOR_PENDENTE`, disponibilidade `NAO_DEFINIDO`, confirmação falsa e destino futuro `NFe/infNFe/det/imposto/IPI/cEnq`. O inventário passou a 111 campos e três lacunas; a rastreabilidade e a matriz de obrigatoriedade passaram a 38 famílias.

- [x] Confirmar no XSD preservado cardinalidade, posição e formato lexical de `cEnq`.
- [x] Separar `cEnq`, IPI da memória e `impostoDevol` em estruturas independentes.
- [x] Iniciar o candidato vazio, sem copiar cadastro atual, XML histórico ou memória.
- [x] Registrar fonte, disponibilidade, obrigação estrutural, obrigação contextual, dependência do contador e destino XML futuro.
- [x] Aceitar candidato de 1 a 3 caracteres apenas como hipótese não confirmada, sem presumir restrição numérica ausente do XSD.
- [x] Rejeitar formato inválido, fonte trocada, metadados divergentes e confirmação antecipada.
- [x] Separar integridade da origem de completude fiscal e manter `permite_aplicar_enquadramento_ipi=False`.
- [x] Provar que o candidato não altera IPI da memória, `impostoDevol`, totalização ou emissão.
- [x] Exibir `cEnq` pendente na prévia somente leitura.
- [x] Remover `ENQUADRAMENTO_IPI_NAO_MODELADO_NA_DEVOLUCAO`; restam três lacunas.
- [x] Validar a regressão conjunta de 153 testes.
- [x] Próximo passo concluído no ciclo 93: variantes e modalidades de PIS/COFINS modeladas como decisões vazias e não confirmadas.

Arquivos de implementação alterados: `apps/fiscal/ipi_devolvido_contrato.py`, `apps/fiscal/inventario_dados_devolucao.py`, `apps/fiscal/rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/obrigatoriedade_campos_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Testes alterados: `apps/fiscal/test_ipi_devolvido_contrato.py`, `apps/fiscal/test_inventario_dados_devolucao.py`, `apps/fiscal/test_rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/test_obrigatoriedade_campos_devolucao.py` e `apps/fiscal/test_devolucao_fornecedor.py`. Documentos alterados ou criados: este roadmap, [ENQUADRAMENTO_IPI_DEVOLUCAO.md](ENQUADRAMENTO_IPI_DEVOLUCAO.md), `INVENTARIO_DADOS_DEVOLUCAO.md`, `MATRIZ_RASTREABILIDADE_DEVOLUCAO.md`, `CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md`, `DEVOLUCAO_FORNECEDOR.md`, `CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md`, `MATRIZ_CONFORMIDADE_FISCAL_CONTABIL_GO_2026.md` e `REDUCAO_BASE_ICMS_DEVOLUCAO.md`.

Migrações: nenhuma. Riscos remanescentes: tabela/código aplicável não aprovados, hipótese de IPI devolvido ainda aberta, pacote XSD não promovido e paridade Focus/SEFAZ não homologada. Decisões não tomadas: código `cEnq`, presença do grupo IPI, CST, valores, justificativa, geração de XML, provedor e ambiente. Dependências externas: validação do contador para casos reais, confirmação normativa integral e futura homologação separada dos canais.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. O trabalho para antes de PIS/COFINS conforme o plano aprovado.

## Ponto de retomada — ciclo 91, 10/09/2026

O grupo ICMS do contrato tributário passou a representar `pRedBC` como candidata vazia, fonte `DECISAO_CONTADOR_PENDENTE` e confirmação falsa. O formato foi confrontado com `TDec_0302a04` do XSD preservado e o contrato limita o percentual candidato à faixa segura de 0 a 100, com duas a quatro casas quando houver parte decimal. Nem o campo existente no cadastro atual do produto, nem o XML histórico, nem diferenças entre bases preenchem a decisão. A base aprovada continua somente reproduzida. O inventário passou a 110 campos e quatro lacunas.

- [x] Confirmar no XSD preservado o formato lexical usado por `pRedBC`.
- [x] Manter a redução exclusivamente no grupo ICMS.
- [x] Iniciar candidata vazia, sem copiar cadastro atual, XML histórico ou memória.
- [x] Fixar fonte em decisão pendente do contador e confirmação falsa.
- [x] Validar percentuais candidatos de 0 a 100, sem aplicá-los.
- [x] Rejeitar formato/percentual inválido, fonte alterada e confirmação direta.
- [x] Manter `permite_aplicar_reducao_base_icms=False`, XML e emissão bloqueados.
- [x] Provar que a candidata não modifica `vBC`, alíquota, valor ou totalização.
- [x] Exibir `pRedBC` pendente na prévia somente leitura.
- [x] Remover `REDUCAO_BASE_ICMS_NAO_MODELADA`; restam quatro lacunas.
- [x] Validar a regressão conjunta de 149 testes.
- [x] Próximo passo concluído no ciclo 92: `cEnq` modelado como decisão contábil vazia e não confirmada, sem copiar cadastro, XML ou memória.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [REDUCAO_BASE_ICMS_DEVOLUCAO.md](REDUCAO_BASE_ICMS_DEVOLUCAO.md).

## Ponto de retomada — ciclo 90, 10/09/2026

O grupo ICMS do contrato `supplier_return_item_tax_values_v1` passou a transportar a modalidade de base como candidata vazia, fonte `DECISAO_CONTADOR_PENDENTE` e confirmação falsa. O XSD oficial preservado confirma os códigos 0, 1, 2 e 3, mas nenhum deles é escolhido pelo sistema; em especial, o valor 3 fixado no emissor antigo não é herdado. A integridade da memória tributária permanece separada da completude da decisão fiscal, portanto bases e totais continuam somente conferíveis e não são recalculados. O inventário passou a 109 campos e cinco lacunas.

- [x] Confirmar no XSD preservado os códigos 0, 1, 2 e 3 de `modBC`.
- [x] Manter a modalidade exclusivamente no grupo ICMS.
- [x] Iniciar candidata vazia, sem copiar XML, cadastro ou emissor antigo.
- [x] Fixar a fonte em decisão pendente do contador e confirmação falsa.
- [x] Rejeitar código fora da enumeração, fonte alterada e confirmação direta.
- [x] Manter `permite_aplicar_modalidade_base_icms=False`, XML e emissão bloqueados.
- [x] Separar origem tributária íntegra de decisão fiscal completa.
- [x] Provar que a candidata não modifica base, alíquota, valor ou totalização.
- [x] Exibir `modBC` pendente na prévia somente leitura.
- [x] Remover a lacuna `MODALIDADE_BASE_ICMS_NAO_MODELADA`; restam cinco.
- [x] Validar a regressão conjunta de 147 testes.
- [x] Próximo passo concluído no ciclo 91: `pRedBC` modelado como hipótese contábil vazia e não confirmada, sem copiar cadastro nem recalcular a base.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [MODALIDADE_BASE_ICMS_DEVOLUCAO.md](MODALIDADE_BASE_ICMS_DEVOLUCAO.md).

## Ponto de retomada — ciclo 89, 10/09/2026

O contrato `supplier_return_products_v1` passou a representar `indTot` por item como candidato explicitamente vazio, com fonte fiscal pendente e confirmação falsa. O validador reconhece 0 e 1 somente como candidatos não confirmados, recusa fonte trocada ou confirmação direta e nunca permite aplicação, XML ou emissão. A completude da origem dos valores foi separada da decisão fiscal para que a totalização diagnóstica continue conferindo a memória aprovada sem usar o novo campo. O inventário passou a 108 campos atômicos e seis lacunas.

- [x] Incluir candidato, fonte e estado de confirmação de `indTot` por item.
- [x] Iniciar o candidato vazio, sem copiar o XML original nem assumir 0 ou 1.
- [x] Rejeitar fonte alterada e promoção direta para confirmado.
- [x] Manter `permite_aplicar_indtot=False`, geração de XML e emissão bloqueadas.
- [x] Separar origem comercial completa de decisão fiscal completa.
- [x] Provar que o campo não altera `valor_produtos`, soma diagnóstica ou `vNF`.
- [x] Exibir o estado pendente na prévia fiscal somente leitura.
- [x] Remover `INDTOT_NAO_MODELADO` do inventário; restam seis lacunas.
- [x] Validar a regressão conjunta de 145 testes.
- [x] Próximo passo concluído no ciclo 90: `modBC` modelado como candidato do contador, sem default, cálculo ou serialização.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [INDTOT_DEVOLUCAO.md](INDTOT_DEVOLUCAO.md).

## Ponto de retomada — ciclo 88, 10/09/2026

O contrato `supplier_return_identity_parties_v1` passou a transportar `indicador_ie_candidato`, sua fonte cadastral e a confirmação obrigatoriamente falsa. Valores 1, 2 e 9 são aceitos somente como candidatos; valor ausente continua pendente e qualquer tentativa de confirmação direta é erro estrutural. A prévia protegida mostra o candidato como não confirmado. O inventário passou a 107 campos atômicos e sete lacunas de modelagem.

- [x] Incluir o indicador de IE candidato no destinatário sem usar o XML como origem.
- [x] Fixar a fonte em `CADASTRO_FORNECEDOR_ATUAL`.
- [x] Manter `indicador_ie_confirmado=False` e rejeitar promoção direta para confirmado.
- [x] Tratar candidato ausente e candidato válido como pendências distintas.
- [x] Proibir aplicação do candidato, XML e emissão no resultado da validação.
- [x] Exibir o candidato e o bloqueio na prévia fiscal somente leitura.
- [x] Adicionar o campo ao inventário e encerrar a lacuna `IND_IE_DESTINATARIO_NAO_MODELADO`.
- [x] Validar o fluxo afetado em regressão conjunta de 107 testes.
- [x] Próximo passo concluído no ciclo 89: `indTot` modelado como candidato explícito e não confirmado, sem valor padrão nem efeito na totalização.

Sem migração, confirmação fiscal, geração de XML, acesso a credencial/certificado, mudança de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [INDICADOR_IE_DESTINATARIO_DEVOLUCAO.md](INDICADOR_IE_DESTINATARIO_DEVOLUCAO.md).

## Ponto de retomada — ciclo 87, 10/09/2026

Criado `supplier_return_supplier_registration_xml_comparison_v1`, que confronta 13 campos do cadastro atual do fornecedor com o emitente da NF-e original. A comparação normaliza somente apresentação equivalente — pontuação de CNPJ/IE/CEP, caixa e acentos — e mantém diferenças reais como divergência. Cadastro, XML e resultado não são gravados ou sobrescritos. A prévia protegida de Administração/Contabilidade mostra as duas fontes e o diagnóstico; Compras e Financeiro continuam sem acesso.

- [x] Comparar identidade, IE e endereço fiscal campo a campo.
- [x] Distinguir coincidência, divergência e ausência em cada fonte.
- [x] Tratar indicador de IE como dado atual sem equivalente direto no emitente histórico.
- [x] Rejeitar adulteração de estado, resumo ou política do contrato.
- [x] Proibir fonte preferencial automática, sobrescrita, XML, Focus, SEFAZ direta e emissão.
- [x] Integrar a comparação à extração e à prévia fiscal somente leitura.
- [x] Remover do inventário a lacuna de confronto concluída; restam oito lacunas estruturais.
- [x] Validar o fluxo afetado em regressão conjunta de 107 testes.
- [x] Modelar `indIEDest` no contrato de identidade usando o indicador atual apenas como dado candidato, sem resolver divergências nem liberar emissão.
- [ ] Modelar `indTot` por item como decisão explícita, vazia e não confirmada.

Sem migração, atualização cadastral, geração de XML, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão. Detalhes em [CONFRONTO_CADASTRO_XML_FORNECEDOR.md](CONFRONTO_CADASTRO_XML_FORNECEDOR.md).

## Ponto de retomada — ciclo 86, 10/09/2026

O fornecedor passou a possuir cadastro fiscal estruturado opcional: indicador de IE, inscrição estadual, logradouro, número, complemento, bairro, CEP, município, UF e código IBGE. Campos vazios continuam aceitos sem valor fiscal presumido; quando IE ou endereço são iniciados, as validações exigem coerência e completude. O endereço comercial livre foi preservado e nenhum importador XML escreve nos novos campos.

- [x] Criar dez campos fiscais opcionais sem preencher registros existentes.
- [x] Exigir IE somente para indicador contribuinte e exigir IE quando ele for selecionado.
- [x] Validar endereço fiscal como conjunto completo, com IBGE de sete dígitos, UF de duas letras e CEP de oito dígitos.
- [x] Exibir uma seção fiscal separada no cadastro, explicando que o XML não a atualiza.
- [x] Preservar endereço comercial, isolamento por empresa e administração do cadastro.
- [x] Substituir no inventário a lacuna cadastral pela lacuna de confronto cadastro–XML.
- [x] Validar cadastro e integração fiscal em regressão conjunta de 101 testes.
- [x] Criar confronto não emissivo entre o cadastro atual do fornecedor e o emitente histórico do XML, exibindo divergências sem sobrescrever nenhuma fonte.
- [ ] Modelar o indicador de IE do destinatário como candidato não emissivo no contrato de identidade.

Migração `fornecedores.0004` somente aditiva e 101 testes aprovados. Sem consulta externa, importação automática, geração de XML, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão. Detalhes em [CADASTRO_FISCAL_FORNECEDOR.md](CADASTRO_FISCAL_FORNECEDOR.md).

## Ponto de retomada — ciclo 85, 10/09/2026

Criado `supplier_return_atomic_data_inventory_v1`, que decompõe os blocos fiscais em 106 campos acompanhados e informa somente fonte, ocorrências e disponibilidade, sem expor valores. O inventário confirmou nove lacunas de modelagem: cadastro fiscal estruturado do fornecedor, `indIEDest`, `indTot`, modalidade/redução de base ICMS, `cEnq` do IPI, variantes PIS/COFINS, gerador específico e paridade Focus. O XML original permanece evidência histórica e não pode atualizar cadastro automaticamente.

- [x] Decompor famílias mistas e grupos críticos em 106 campos atômicos.
- [x] Identificar fonte primária e estado de disponibilidade sem expor valores.
- [x] Separar ausência bloqueante, campo condicionado e vazio imposto por política.
- [x] Registrar nove lacunas de cadastro, contrato, hipótese, código e adaptador.
- [x] Impedir uso do XML histórico como cadastro atual ou preenchimento por default.
- [x] Integrar o diagnóstico à prévia protegida e validar 138 testes conjuntos.
- [x] Estruturar IE, indicador de IE, endereço fiscal e município IBGE no fornecedor, opcionais e sem importação automática do XML.
- [ ] Confrontar cadastro atual e XML histórico sem emitir ou sobrescrever dados.

Sem migração, exposição de valores, geração de XML, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão neste ciclo. Detalhes em [INVENTARIO_DADOS_DEVOLUCAO.md](INVENTARIO_DADOS_DEVOLUCAO.md).

## Ponto de retomada — ciclo 84, 10/09/2026

Criado `supplier_return_field_requirement_matrix_v1` para classificar as 37 famílias rastreadas por cardinalidade XSD, regra contextual, hipótese tributária, vigência e necessidade de decisão do contador. A matriz registra que XSD isolado não define aplicação: `DFeReferenciado` é opcional na estrutura e obrigatório no contexto documentado; pagamento usa `tPag=90`/`vPag=0`; IPI devolvido, ST/FCP e RTC permanecem condicionados. Famílias com regra contextual ou hipótese ainda não fechada aparecem como pendentes na prévia.

- [x] Separar obrigatoriedade estrutural de obrigatoriedade contextual MOC/NT.
- [x] Classificar campos dependentes de valor, transporte, hipótese e enquadramento.
- [x] Marcar expressamente quais famílias exigem decisão do contador.
- [x] Manter vigência GO, análise integral e caso real como não confirmados.
- [x] Recusar alteração da classificação, aplicação antecipada ou liberação de canal.
- [x] Integrar o diagnóstico à prévia protegida e validar 135 testes conjuntos.
- [ ] Próximo passo: decompor famílias mistas em campos atômicos e inventariar quais dados existem no sistema, quais faltam no cadastro e quais dependem do XML/contador, sem gerar XML.

Sem migração, geração de XML, instalação de schema, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão neste ciclo. Detalhes em [CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md](CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md).

## Ponto de retomada — ciclo 83, 10/09/2026

Criado o contrato `supplier_return_layout_traceability_v1`, com 37 famílias de campos distribuídas pelos 13 subcontratos. A matriz liga cada origem neutra ao destino no leiaute, à cobertura observada no conversor Focus e ao comportamento do adaptador SEFAZ direto. Foram confirmadas lacunas Focus em referências por item, ajustes, transporte completo, totais, `infAdProd`, IPI devolvido e RTC. O canal direto preserva a `NFe` recebida, mas continua dependente de um gerador específico que não existe.

- [x] Vincular os 13 contratos aos destinos principais do `leiauteNFe_v4.00.xsd` preservado.
- [x] Separar cobertura do conversor Focus de capacidades não comprovadas da API externa.
- [x] Registrar que a SEFAZ direta não reconstrói conteúdo, sem confundir transporte integral com prontidão.
- [x] Proibir serialização, Focus, SEFAZ direta e emissão em todas as linhas da matriz.
- [x] Exibir o resumo na prévia protegida e validar 132 testes conjuntos.
- [ ] Próximo passo: classificar as 37 famílias como obrigatórias, opcionais ou condicionadas por fonte normativa, mantendo decisões tributárias dependentes do contador e sem criar XML.

Sem migração, geração de XML, instalação de schema, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão neste ciclo. Detalhes em [MATRIZ_RASTREABILIDADE_DEVOLUCAO.md](MATRIZ_RASTREABILIDADE_DEVOLUCAO.md).

## Ponto de retomada — ciclo 82, 10/09/2026

Criado o portão diagnóstico `supplier_return_readiness_gate_v1`. Ele confere em ordem os 13 subcontratos da devolução, separa estrutura consolidada de origens conferidas, agrega os bloqueios e impede que qualquer bloco libere XML ou emissão. Os sete portões externos — análise normativa integral, matriz tributária, dados reais, casos aprovados pelo contador, schema aplicável, paridade Focus e paridade SEFAZ direta — permanecem explicitamente desligados.

- [x] Consolidar envelope, referências, partes, produtos, tributos, ajustes, transporte, totais, pagamento fiscal, observações, IPI devolvido, ICMS-ST/FCP e RTC.
- [x] Recusar divergência de contrato, ausência estrutural e tentativa de liberação de XML/emissão por qualquer subcontrato.
- [x] Exibir o diagnóstico na prévia protegida, distinguindo estrutura reunida de NF-e pronta.
- [x] Manter Focus, SEFAZ direta, certificados, ambientes e configurações inalterados.
- [x] Validar 129 testes conjuntos dos contratos e do fluxo de devolução.
- [ ] Próximo passo: construir a matriz campo a campo entre o contrato neutro, o leiaute/XSD aplicável e os adaptadores Focus/SEFAZ direta, sem serializar XML, e usar as lacunas para concluir a leitura normativa.

Sem migração, geração de XML, instalação de schema, acesso a credencial/certificado, mudança de feature flag ou transmissão neste ciclo.

## Ponto de retomada — ciclo 81, 10/09/2026

Criado o contrato `supplier_return_rtc_vigency_policy_v1` para manter IBS/CBS/RTC condicionado à confirmação normativa e operacional. A NT 2026.007 v1.00, seu SHA-256 e as datas documentais são registrados como evidência, mas não ativam nada. Os valores da memória são apenas referência; enquadramento, classificação, grupos e totais ficam vazios enquanto leitura integral, implantação em Goiás, leiaute aplicável e homologação não estiverem confirmados.

- [x] Preservar IBS/CBS da memória somente como referência vinculada.
- [x] Registrar versão, hash, páginas e datas documentais da NT analisada.
- [x] Impedir ativação automática por data ou mera presença de schema.
- [x] Manter enquadramento, classificação, grupos e totais RTC não definidos.
- [x] Integrar o diagnóstico à prévia protegida sem produzir grupo XML.
- [x] Validar 126 testes conjuntos dos contratos e do fluxo de devolução.
- [ ] Próximo passo: consolidar um portão de prontidão que confira todos os subcontratos e liste, sem ambiguidade, o que ainda impede a futura geração de XML.

Sem migração, ativação de RTC, instalação de schema, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 80, 10/09/2026

Criado o contrato `supplier_return_icms_st_fcp_hypothesis_v1` para separar valores de referência da futura decisão sobre ICMS-ST/FCP. Cada item preserva base, alíquota e valor informados na memória, mas hipótese, grupos fiscais, informação complementar e totais ficam vazios. O validador proíbe copiar valores ou inferir tratamento por código ICMS, regime ou generalização das orientações GO 21305/21349.

- [x] Estruturar ICMS-ST e FCP por item com origem e hashes comuns.
- [x] Preservar os valores da memória somente como referência.
- [x] Manter hipótese, destino fiscal, texto complementar e totais não definidos.
- [x] Bloquear inferência por CST/CSOSN, regime ou orientação genérica de Goiás.
- [x] Integrar o diagnóstico à prévia protegida sem produzir grupo XML.
- [x] Validar 123 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar IBS/CBS/RTC com política explícita de vigência e leiaute, mantendo grupos e totais bloqueados até confirmação normativa e homologação (ciclo 81).

Sem migração, definição de hipótese ST/FCP, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 79, 10/09/2026

Criado o contrato `supplier_return_returned_ipi_policy_v1` para manter `impostoDevol` separado do IPI informado na memória. Cada item preserva a referência aprovada de IPI, mas permanece no estado `HIPOTESE_NAO_APROVADA`; `pDevol`, `vIPIDevol`, justificativa fiscal e total ficam vazios. O validador rejeita cópia, cálculo automático ou preenchimento desses campos.

- [x] Estruturar `impostoDevol` por item sem confundi-lo com `det/imposto/IPI`.
- [x] Preservar IDs e hashes da memória/revisão que contém o IPI de referência.
- [x] Manter hipótese, percentual, valor, justificativa e total não definidos.
- [x] Rejeitar cópia do IPI da memória e cálculo automático de percentual.
- [x] Integrar o diagnóstico à prévia protegida sem produzir grupo XML.
- [x] Validar 120 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar ICMS-ST/FCP por hipótese explícita, mantendo destaque/restituição e valores bloqueados até orientação aprovada para o caso real (ciclo 80).

Sem migração, cálculo de IPI devolvido, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 78, 10/09/2026

Criado o contrato `supplier_return_fiscal_notes_policy_v1` para separar anotações internas de futuros textos fiscais. A extração confere parecer, parametrização, memória e revisão, mas expõe somente IDs, hashes e um inventário de presença/contagem. Motivo operacional, fundamentações e observações não são copiados para a prévia nem para os campos fiscais. `infAdic` e `infAdProd` permanecem vazios, e qualquer preenchimento ou exportação automática é rejeitado.

- [x] Inventariar fontes internas sem reproduzir seus textos no contrato ou na prévia.
- [x] Exigir cadeia final aprovada e hashes de parecer, parâmetros, memória e revisão.
- [x] Manter `infAdic` e `infAdProd` vazios até aprovação fiscal específica.
- [x] Rejeitar cópia automática ou injeção antecipada de texto fiscal.
- [x] Integrar o diagnóstico à prévia protegida sem expor conteúdo interno.
- [x] Validar 117 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar o grupo específico de IPI devolvido por item, separado do IPI da memória e sem presumir hipótese, percentual ou valor (ciclo 79).

Sem migração, cópia de texto para XML, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 77, 10/09/2026

Criado o contrato `supplier_return_fiscal_payment_policy_v1`, isolado do fluxo comum de vendas. Para devolução de compra modelo 55/finalidade 4, a única política aceita nesta etapa é `tPag=90` e `vPag=0.00`. O contrato proíbe usar o total comercial e exige que geração de título, movimento de caixa, acionamento de meio de pagamento e cálculo de troco permaneçam falsos.

- [x] Estruturar `tPag=90` e `vPag=0.00` como política fiscal explícita.
- [x] Restringir o contrato à devolução de compra, modelo 55 e finalidade 4.
- [x] Rejeitar uso do total comercial ou valor diferente de zero.
- [x] Rejeitar qualquer efeito operacional e manter o fluxo de vendas desacoplado.
- [x] Integrar a política à prévia protegida, sem gerar `pag/detPag`.
- [x] Validar 114 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar observações fiscais separando conteúdo interno de `infAdic` e `infAdProd`, sem copiar texto livre automaticamente para o XML (ciclo 78).

Sem migração, lançamento operacional, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 76, 10/09/2026

Criado o contrato `supplier_return_diagnostic_totals_v1` para consolidar somente valores já informados nas origens aprovadas. Produtos, base comercial, frete, seguro, despesas, desconto, bases e valores tributários são somados para conferência e precisam apontar para a mesma memória. O diagnóstico não forma `vNF`: valor da nota, IPI devolvido e totais RTC permanecem deliberadamente vazios e bloqueados.

- [x] Consolidar totais comerciais sem reaplicar componentes às bases.
- [x] Somar bases e valores informados de cada grupo tributário sem recalcular imposto.
- [x] Exigir produtos, tributos e ajustes completos, íntegros e ligados à mesma memória.
- [x] Recusar preenchimento antecipado de `vNF`, IPI devolvido e totais RTC.
- [x] Integrar o diagnóstico à prévia protegida.
- [x] Validar 111 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar a política fiscal de pagamento `tPag=90` e `vPag=0.00` como contrato não emissivo, sem produzir efeitos operacionais (ciclo 77).

Sem migração, cálculo de `vNF`, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 75, 10/09/2026

Criado o contrato `supplier_return_transport_input_v1` para expor a ficha logística sem transformá-la em XML. A extração só aceita a ficha ligada à última memória final aprovada e confere novamente os hashes da ficha, da memória e da revisão. Modalidade, transportador, documento, volumes e pesos são validados com suas regras condicionais; a ausência da ficha ou uma origem superada aparecem como pendência explícita.

- [x] Estruturar transporte com IDs e hashes da ficha, memória e revisão.
- [x] Exigir a última memória final aprovada e íntegra como origem.
- [x] Validar modalidade sem transporte, dados do transportador, CPF/CNPJ, volumes e pesos.
- [x] Integrar estado e bloqueios à prévia protegida, sem gerar o grupo `transp`.
- [x] Validar 108 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar a totalização diagnóstica, separando total comercial, bases, tributos e grupos ainda não suportados, sem calcular ou declarar `vNF` (ciclo 76).

Sem migração, geração de XML, acesso a certificado, alteração de ambiente ou transmissão neste ciclo.

## Ponto de retomada — ciclo 74, 10/09/2026

Criado o contrato `supplier_return_commercial_adjustments_v1` para os ajustes informados no rateio. A extração exige a cadeia composição/rateio/reflexos aprovados/memória revisada aprovada e preserva a memória histórica que originou cada linha. Frete, seguro, despesas, desconto, base e total são apenas reproduzidos e conferidos por item e no total; o contrato proíbe reaplicar esses componentes às bases tributárias.

- [x] Estruturar ajustes por item e totais com IDs e hashes de toda a origem.
- [x] Exigir reflexos e memória final aprovados, além da integridade do rateio.
- [x] Preservar a distinção entre memória histórica do rateio e memória revisada final.
- [x] Conferir somas informadas sem preencher valores nem alterar bases.
- [x] Integrar o diagnóstico à prévia protegida.
- [x] Validar 105 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar o grupo de transporte a partir da ficha ligada à memória final, validando campos condicionais sem gerar XML (ciclo 75).

Sem migração, reaplicação de valores, cálculo tributário, XML ou transmissão neste ciclo.

## Ponto de retomada — ciclo 73, 10/09/2026

Criado o contrato `supplier_return_item_tax_values_v1` para transportar, sem recalcular, as bases, alíquotas e valores da memória revisada aprovada. Cada linha exige vínculo exato entre rascunho, parametrização, memória, revisão e nItem. ICMS, PIS e COFINS permanecem pendentes da matriz; ICMS-ST/FCP ficam em hipótese não confirmada; IPI da memória não é tratado como `impostoDevol`; IBS/CBS permanecem bloqueados por vigência e leiaute. A prévia apresenta esses estados sem declarar suporte fiscal.

- [x] Estruturar bases, alíquotas, valores, códigos e hashes por item.
- [x] Exigir memória revisada aprovada, íntegra e ligada ao mesmo item/parametrização/nItem.
- [x] Manter ICMS-ST/FCP, IPI devolvido e IBS/CBS em estados separados e bloqueantes.
- [x] Validar formatos decimais sem criar fórmulas ou recalcular tributos.
- [x] Integrar a extração e a prévia protegida.
- [x] Validar 102 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar ajustes comerciais por item a partir do rateio aprovado, conferindo os totais informados sem aplicá-los novamente às bases (ciclo 74).

Sem migração, cálculo tributário, XML, certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 72, 10/09/2026

Criado o contrato puro `supplier_return_products_v1` e integrado à extração protegida. Cada item preserva o vínculo com rascunho, produto, nItem original, XML, parametrização e memória. Quantidade vem da seleção congelada; código, descrição, NCM, CEST, unidades e valores unitários vêm do snapshot do XML; CFOP, valor da operação e classificações só são expostos quando a memória está aprovada e toda a cadeia de hashes confere. O serviço apenas compara quantidade × unitário com o valor informado, sem preencher ou recalcular esse valor.

- [x] Preservar no snapshot documental unidade, quantidade e valor unitário tributáveis.
- [x] Estruturar produtos com origem explícita para identidade, quantidade, valor e classificação.
- [x] Bloquear valores/classificações enquanto a memória não estiver aprovada e íntegra.
- [x] Validar nItem, identificadores, hashes, NCM/CEST/CFOP, unidades, decimais, duplicidades e total informado.
- [x] Expor produtos e pendências na prévia protegida.
- [x] Validar 99 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar bases e valores tributários por item a partir da memória aprovada, mantendo ICMS-ST/FCP, IPI devolvido e IBS/CBS separados por hipótese e vigência (ciclo 73).

Sem migração, alteração de cadastro, cálculo tributário automático, XML ou transmissão neste ciclo.

## Ponto de retomada — ciclo 71, 10/09/2026

Criado o contrato puro `supplier_return_identity_parties_v1` para identificação, emitente e destinatário da NF-e de devolução. A extração protegida usa natureza do parecer, cadastro atual da filial, IE/CRT da configuração fiscal e identidade/endereço do fornecedor preservados no XML original. Estrutura e completude são resultados separados: campos ausentes aparecem na prévia, sem preenchimento presumido. O contrato mantém bloqueios de vigência, CNPJ alfanumérico, XML e homologação.

- [x] Estruturar identificação como modelo 55, finalidade de devolução e operação de saída.
- [x] Estruturar emitente a partir da filial e configuração fiscal, sem expor credenciais.
- [x] Estruturar destinatário a partir do XML original e vínculo cadastral do fornecedor.
- [x] Validar campos, fontes, formatos e tentativa de habilitar emissão em serviço puro.
- [x] Integrar o diagnóstico à extração e à prévia exclusiva de Administrador/Contabilidade.
- [x] Validar 95 testes conjuntos do contrato e do fluxo de devolução.
- [x] Estruturar o grupo de produtos da devolução com quantidades, unidades, valores e classificações vindos dos snapshots aprovados, sem cálculo automático (ciclo 72).

Sem migração, gravação cadastral, certificado, XML ou transmissão neste ciclo.

## Ponto de retomada — ciclo 70, 10/09/2026

A extração protegida da devolução agora produz as referências fiscais chave+nItem a partir do rascunho e as confronta com o XML integral preservado. A conferência exige DF-e da mesma empresa e filial, hash congelado, protocolo com cStat 100, chave idêntica no XML/protocolo/DF-e/compra/rascunho, modelo 55, fornecedor como emitente, filial como destinatária e igualdade do nItem e de seu snapshot. A prévia somente leitura de Administrador/Contabilidade mostra o resultado e os bloqueios, sem permitir edição.

- [x] Integrar o validador de referências à extração autenticada e ao escopo da empresa.
- [x] Conferir protocolo, chave, modelo, partes, nItem e snapshot do XML original.
- [x] Falhar fechado diante de hash, protocolo ou retrato do item divergente.
- [x] Expor a conferência na prévia protegida, mantendo XML e emissão bloqueados.
- [x] Validar 92 testes dos contratos e do fluxo completo de devolução; check do Django sem problemas.
- [x] Estruturar os grupos de identificação, emitente e destinatário do contrato neutro, com snapshots e validação somente leitura (ciclo 71).

Sem migração, acesso a certificado, geração de XML ou chamada a Focus/SEFAZ neste ciclo.

## Ponto de retomada — ciclo 69, 10/09/2026

O pagamento do PDV agora começa com a decisão clara “CPF na nota? Não/Sim”. Nenhuma opção vem escolhida na tela; o operador precisa responder antes de finalizar. “Sim” abre e focaliza o CPF, admite digitação ou pinpad e exige 11 dígitos com verificadores válidos. “Não” limpa o documento e grava consumidor não identificado. O CPF de cliente cadastrado não é mais incluído automaticamente sem essa escolha. CNPJ permanece fora desse atalho e deve seguir NF-e modelo 55.

- [x] Tornar a decisão de CPF explícita antes do recebimento e adequada ao teclado do caixa.
- [x] Validar CPF no navegador e novamente no servidor, inclusive dígitos verificadores e sequências repetidas.
- [x] Impedir inclusão automática do documento do cadastro sem escolha expressa do consumidor.
- [x] Manter captura opcional pelo pinpad e digitação manual, sem expor documento em diagnóstico.
- [x] Validar sintaxe JavaScript, check do Django, 88 testes completos de PDV/vendas e testes fiscais focados.
- [x] Retomar no ciclo seguinte a extração autenticada de chave+nItem da devolução a partir do XML original (ciclo 70).

Sem migração, mudança de banco, transmissão fiscal ou alteração financeira neste ciclo.

## Ponto de retomada — ciclo 68, 10/09/2026

Implementado o contrato puro e não emissivo de referências da devolução por item. Valida chave de 44 dígitos e DV, nItem original, unicidade, política/operação/modelo explícitos e ausência de NFref no cabeçalho. Múltiplas origens recebem bloqueio de escopo, sem serem tratadas como proibição fiscal. A validação ampliada aprovou 91 testes do novo contrato, envelope e fluxo de devolução; check do Django sem problemas. Não houve banco, XML, schema, certificado, cobrança ou transmissão.

- [x] Implementar e testar o validador estrutural de DFeReferenciado por item.
- [x] Extração autenticada de chave+nItem a partir do dossiê/XML original, conferindo integridade, modelo e partes no escopo da empresa (ciclo 70).
- [ ] Depois: completar matriz tributária, totais e vigências antes de criar o gerador separado e homologar cada canal.

## Retomada atual — ciclo 67, 10/09/2026

Confronto dos trechos oficiais de devolução registrado em [REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md](REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md). Corrigida a proposta de referência do cabeçalho para chave+nItem original em DFeReferenciado por item. A NT v1.51 indica 05/10/2026 na regra específica, mas tem divergência no histórico: confirmação operacional continua pendente. Documentados pagamento sem pagamento/valor zero e IPI devolvido separado; isso não decide enquadramento tributário nem acerto financeiro do fornecedor.

- [x] Confrontar referência, pagamento e estrutura de IPI devolvido com os trechos oficiais, registrando limites e divergências.
- [ ] Próximo passo: implementar e testar validador puro de referências fiscais por item; depois integrar extração autenticada, sem XML ou emissão.
- [ ] Completar análise tributária/RTC, tabelas e vigências; confirmar pacote e hipóteses com o contador antes do gerador/homologação.

Apenas documentação alterada neste ciclo; sem mudança de código executável, banco, configuração, cobrança ou transmissão. Registros abaixo são históricos, não o ponto atual de retomada.

Ciclo 66 — 10/09/2026: bloqueio de obtenção das fontes superado com sessão HTTP/cookies. ZIP oficial 010f e PDFs MOC Anexo I, NT 2025.002 v1.51 e NT 2026.007 v1.00 preservados em docs/evidencias/nfe_2026_09_10, com inventário e hashes no README da pasta. ZIP passou CRC e XSD raiz compilou em memória sem rede; identificação dos PDFs conferida. Não houve instalação, alteração fiscal, banco ou emissão. Leitura normativa integral e validação de vigências permanecem pendentes: próximo passo é confrontar regras de devolução com o contrato e os dados do sistema. Os bloqueios históricos de acesso descritos abaixo não representam mais falta dos arquivos; a aprovação do pacote continua pendente.

## Ponto de retomada — ciclo 65, 09/09/2026

Bloqueio documental confirmado: `fiscal_schemas` contém somente README.md, sem pacote XSD. Nova tentativa de abrir a página oficial de schemas indicada pelo projeto retornou redirecionamento circular; a leitura integral do MOC/NT permanece pendente. Não houve alteração de regras, configuração, certificado, banco ou emissão. Não contar esta verificação como módulo fiscal concluído.

Para retomar a matriz normativa: obter o ZIP oficial dos schemas, o MOC Anexo I e as notas técnicas aplicáveis em arquivos locais, com URL de origem e identificação da versão. Conferir o conteúdo e gerar inventário/hash antes de qualquer instalação. O comando existente `instalar_schemas_fiscais` exige hash esperado e versão: não executá-lo para promover um pacote ainda não validado. Nenhuma decisão de tributação ou versão de produção deve ser inferida por disponibilidade de um ZIP.

Próxima ação necessária: disponibilizar os arquivos oficiais ou restabelecer acesso ao portal; depois analisar campos/regras de devolução e vigências, completar a matriz e implementar testes antes do gerador. A prévia e a extração já existentes continuam somente leitura e não autorizam transmissão.

Validação do ciclo 64: suíte de 94 testes executada, com 93 aprovados inicialmente e uma asserção de ausência de formulário ajustada para ignorar formulários globais da página. Os dois testes da prévia foram reexecutados e aprovados após o ajuste. Verificação da aplicação e git diff --check sem erros. Sem nova migração ou transmissão.

Ciclo 64 (09/09/2026): prévia protegida das referências fiscais disponível pela tela de revisão da devolução. Rota somente GET, restrita a Administrador/Contabilidade e à empresa do usuário, com cache desabilitado. Mostra grupos, referências, hashes, pendências e bloqueios, sem edição ou emissão. A etapa de extração do ciclo 63 foi salva no commit 7efa868 após restabelecimento da execução. Próximo passo: obter e analisar integralmente as fontes oficiais e schemas pendentes para fechar a matriz de capacidade fiscal; a prévia não substitui essa validação.

- Ciclo 63 (09/09/2026): extração somente leitura do envelope a partir do banco em apps/fiscal/extracao_contrato_devolucao.py. Exige Administrador/Contabilidade e filtra preparação pela empresa antes de ler suas referências; consulta atual sem reutilizar relações em cache, confere hashes e reutiliza pendências do dossiê. Preserva referências da memória atual, origem e predecessoras de correção, além de decisões disponíveis. Não inclui XML, credenciais ou conteúdo pessoal no envelope. Referência encontrada não significa aprovada: pendências do dossiê seguem separadas e campos fiscais não mapeados continuam NAO_SUPORTADO. Sem endpoint/tela próprios ou validação normativa. Próximo passo: apresentar a prévia protegida do contrato e bloqueios na tela, sem permitir edição manual ou emissão.

- Ciclo 62 (09/09/2026): envelope preliminar supplier_return_nfe_input_v1 e validador puro implementados em apps/fiscal/contrato_devolucao.py, com sete testes aprovados. Exige identificação da preparação/empresa, grupos conhecidos, estados explícitos e referências tipo/id/SHA-256. Distingue ausência, divergência, superação e não suporte; rejeita extras e referências duplicadas. Estrutura válida não significa autenticidade ou conformidade: XML e emissão sempre bloqueados. Ainda sem extração do banco, autorização por empresa, tela ou endpoint próprios. Próximo passo: construir o envelope a partir do dossiê em serviço somente leitura com escopo e integridade verificados. Confirmado aviso oficial de publicação da NT 2025.002 v1.51; leitura integral e XSD ainda pendentes.

- Ciclo 61 (09/09/2026): especificação preliminar do contrato supplier_return_nfe_input_v1 em docs/CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md. Mapeados grupos, fontes locais e bloqueios, incluindo ausência de referência documental no payload Focus observado e despacho de modelo 55 para venda online. Consulta às orientações oficiais GO 21305/21349 confirma necessidade de enquadramento específico para ST. Leitura integral do MOC/NT não concluída por erro no portal; versões e schemas ainda não fixados. Próximo passo: obter fontes integrais e implementar contrato/validador neutro somente leitura. Sem geração de XML, migração ou mudança de emissor.

Validação do ciclo 60: 82 testes aprovados após corrigir reutilização de relações em cache na consulta do XML. Sem alterações de modelos ou novas migrations; sem divergências de migrations e sem erros em git diff --check. Nenhuma transmissão, cobrança ou aplicação de migrations ao banco operacional.

- Ciclo 60 (09/09/2026): conferência consolidada da devolução na tela fiscal, contrato supplier_return_dossier_status_v1. Consulta restrita a Administrador/Contabilidade no escopo da empresa; não grava documentos ou auditorias. Apresenta pendências de preparação, parecer/parâmetros atuais, memória e sua revisão, composição, rateio, reflexos, vínculo à memória revisada e transporte. Distingue referências históricas legítimas da memória revisada de versões superadas. Confere hash dos registros e usa o validador existente de integridade da memória/XML. Não é validador normativo completo nem gate de emissão: XML e homologação continuam explicitamente bloqueados. Próximo passo: especificar o contrato de dados do XML modelo 55 da devolução a partir do dossiê, com matriz de campos suportados e bloqueios antes de gerar XML.

Validação do ciclo 59: 79 testes aprovados; sem divergências de migrations e sem erros em git diff --check. Migration 0050 gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Nenhuma cobrança ou transmissão liberada.

- Ciclo 59 (09/09/2026): correção rastreável da memória revisada implementada (migration 0050). Reflexos passam a admitir versões de memória, mas cada memória devolvida só pode originar uma sucessora. A seleção explícita da memória a corrigir exige versão atual, decisão de devolução íntegra, origem preservada e bases finais idênticas às aprovadas. Nova versão conserva hashes da memória devolvida e da decisão, sem reaplicar impactos; exige nova revisão. Reenvio da correção já utilizada é bloqueado. Próximo passo: consolidar a situação do dossiê da devolução e suas pendências em uma conferência única antes do trabalho de XML. Emissão e homologação permanecem pendentes.

Validação do ciclo 58: 76 testes aprovados. Migration 0049 gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Nenhuma transmissão ou cobrança liberada.

- Ciclo 58 (09/09/2026): memória tributária revisada vinculada explicitamente aos reflexos aprovados, migration 0049. O vínculo único preserva IDs e hashes da memória anterior, dos reflexos e da aprovação. As bases informadas devem corresponder exatamente às bases finais aprovadas; valor da operação e parametrização permanecem os da origem. Não soma impactos, não presume alíquotas ou impostos e exige a revisão independente já existente da nova memória. A opção é apresentada para reflexos atuais aprovados ainda não utilizados. Reenvio do mesmo vínculo é bloqueado, não cria outra memória. Próximo passo: tratar a devolução para correção da memória revisada com nova versão rastreável, sem reutilizar impactos como novo ajuste. Aceite real e homologação continuam pendentes.

Validação do ciclo 57: 73 testes de devolução, transporte, rateio e reflexos aprovados. Migration 0048 gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Sem transmissão externa ou alteração de cobrança.

- Ciclo 57 (09/09/2026): revisão independente dos reflexos nas bases implementada, contrato supplier_return_tax_base_impacts_review_v1, migration 0048. Outro Administrador/Contabilidade da empresa aprova ou devolve com justificativa; uma decisão imutável por versão. O serviço bloqueia o rascunho, exige reflexos/rateio/composição/memória atuais, confere hashes, vínculos, bases e totais e XML de origem. Correção cria nova versão sem apagar a decisão. A tela mostra autoria, justificativa e decisão e não oferece revisão ao autor ou para versões superadas. Próximo passo: vincular os reflexos aprovados à preparação de uma memória tributária revisada, sem reaplicar impactos ou substituir a memória original. Cálculo dos impostos, aceite real e homologação continuam pendentes.

Validação do ciclo 56: 67 testes aprovados; sem divergências de migrations e sem erros em git diff --check. Migration 0047 gerada e exercitada no banco de testes, não aplicada ao banco operacional. Sem transmissão externa.

- Ciclo 56 (09/09/2026): reflexos das bases integrados ao histórico imutável e à tela de revisão, contrato supplier_return_tax_base_impacts_v1, migration 0047. Serviço transacional bloqueia a preparação, exige Administrador/Contabilidade no escopo, composição/memória aprovadas atuais e rateio mais recente, verifica hashes, itens, totais e XML de origem. Conteúdo repetido é idempotente; alterações criam versão. A conferência continua apenas aritmética: não recalcula impostos nem libera emissão. Próximo passo: conferência independente dos reflexos e definição do vínculo com uma memória tributária revisada; aprovação contábil real e homologação permanecem pendentes.

Validação do ciclo 55: 63 testes de devolução, transporte, rateio e reflexos aprovados. Sem alterações de modelo ou novas migrations; sem comunicação externa e sem aplicação de migrations ao banco operacional.

- Ciclo 55 (09/09/2026): núcleo de conferência dos reflexos nas bases implementado em `ReflexosBasesDevolucaoForm`, contrato provisório `supplier_return_tax_base_impacts_draft_v1`. Exige impactos assinados explícitos de frete, seguro, despesas e desconto para cada item e cada um dos oito tributos, base final declarada e totais por tributo. Confere base anterior + impactos = base final sem inferir incidência, alíquota ou valor do imposto. Etapa parcial: ainda sem persistência, rota ou tela; não está disponível para uso operacional. Próximo passo: serviço transacional e histórico vinculados ao rateio atual, com escopo, integridade e auditoria, seguidos da tela. Aceite contábil real e homologação continuam pendentes.

- Ciclo 54 concluído estruturalmente em 09/09/2026: rateio comercial por item `supplier_return_commercial_allocation_v1` implementado, migration 0046. Exige composição e memória atuais aprovadas, valores explícitos inclusive zeros e somas exatas por componente e total. Histórico imutável, idempotência, escopo e hashes preservados. 56 testes de devolução, transporte e rateio aprovados; nenhuma divergência de migrations. Migration gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Não gera cobrança, imposto, XML ou transmissão. Próximo passo: estruturar os reflexos sobre bases tributárias com orientação contábil; aceite real e homologação permanecem pendentes.

Atualizado em 01/09/2026 a partir das notas técnicas de evolução contábil, integração SEFAZ, comparativo iSOLIDUS e auditoria do estado executável do repositório.

## Principio de produto

O DeTecServer nao deve copiar telas, nomes ou componentes proprietarios de outros ERPs. A evolucao busca resultados operacionais mensuraveis: menos digitacao, menor divergencia, estoque confiavel, margem protegida, fechamento mais rapido e operacao resiliente.

## Estado atual

O ERP ja possui uma base operacional, financeira gerencial, fiscal preparada por adaptador, auditoria, empresas/filiais, PDV e sincronizacao. O livro financeiro e o pacote contabil sao gerenciais e de integracao; eles nao substituem razao contabil por partidas dobradas, ECD, ECF, EFD ou a responsabilidade do contador.

## Prioridade fiscal e contábil definida em 28/08/2026

- Focus e SEFAZ direta estão estruturalmente avançados, mas o motor tributário e o pacote do contador ainda são parciais.
- Antes da homologação real, deve ser implementada a MATRIZ_CONFORMIDADE_FISCAL_CONTABIL_GO_2026.md.
- Produção permanece bloqueada; selecionar um canal não significa homologá-lo ou liberar sua rede.
- A ordem passa a ser: definição fiscal, cobertura tributária/XML, pacote do contador v2 e homologação separada dos canais.
- IBS/CBS é portão obrigatório conforme regime e vigência aplicáveis.
- Primeiro ciclo concluído em 28/08/2026: perfil provisório sem identidade fiscal, catálogo fiscal_tax_scenarios_go_v1, emissão direta reclassificada como parcial e 25 testes offline aprovados. Próxima ação: validador central de cenário e testes de XML da venda interna.
- Segundo ciclo concluído em 28/08/2026: validador central conectado à NFC-e GO, venda interna documentada no XML, CFOP interestadual bloqueado antes da reserva de número e regressão fiscal completa com 229 testes aprovados. Próxima ação: dados fiscais estruturados do destinatário da NF-e 55.
- Terceiro ciclo concluído em 28/08/2026: cliente e pedido ganharam dados fiscais estruturados, o pedido preserva snapshot imutável, a NF-e gera enderDest completo e a preparação incompleta é bloqueada antes da numeração. Migrations clientes 0004 e marketplace 0011 criadas; 61 testes conjuntos e 229 fiscais aprovados. Próxima ação: catálogo cBenef GO versionado.

- Quarto ciclo concluído em 28/08/2026: catálogo cBenef GO versionado pela migration fiscal 0032, importador local com fonte, hash, vigência e contagem obrigatórios, validação de código x CST no cadastro e no pré-fluxo e falha segura sem catálogo. O anexo oficial consolidado foi conferido pelo SHA-256 `a4fbbeff5ff431a17cf38011d1d8c095558e2bee44121afaee7cbe07bf9e292e`, resultou em 282 códigos e foi ativado somente no banco local de desenvolvimento. Seis testes focados e a regressão fiscal completa com 233 testes passaram. Focus, SEFAZ direta, rede e produção permanecem desligados. Próxima ação: versionar NCM/CEST/CFOP e iniciar o pacote do contador v2 com dados já confiáveis.
- Quinto ciclo, subciclo NCM concluído em 28/08/2026: catálogo oficial Siscomex versionado por snapshot, SHA-256, ato e vigência individual; 10.515 códigos finais importados e ativados localmente pela migration fiscal 0033, com validação na emissão, gate de prontidão, 10 testes focados e 239 testes fiscais aprovados. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: CEST e sua relação com NCM.
- Sexto ciclo, subciclo CEST concluído em 31/08/2026: página consolidada oficial do Convênio ICMS 142/18 preservada por snapshot e SHA-256; 1.561 linhas normativas analisadas, 1.035 CEST vigentes em 25 segmentos e 8 códigos revogados excluídos. A migration fiscal 0034, o importador offline, o cadastro, a pré-emissão e o gate de prontidão validam existência e compatibilidade objetiva CEST x NCM sem presumir enquadramento por descrição. Sessenta e seis testes focados e 244 testes fiscais passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: CFOP.
- Sétimo ciclo, subciclo CFOP concluído em 31/08/2026: página consolidada oficial do Ajuste SINIEF 07/01 preservada por snapshot e SHA-256; 528 linhas codificadas analisadas, 68 agrupadores excluídos e 460 CFOP utilizáveis importados, sendo 213 de entrada e 247 de saída. A migration fiscal 0035, o importador offline, as naturezas, a pré-emissão e o gate de prontidão validam existência, direção, alcance interno/interestadual/exterior e modelo documental. A escolha do código específico continua dependente do cenário e da aprovação fiscal/contábil. Onze testes focados e 249 testes fiscais passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: ampliar os cenários tributários/XML e iniciar o pacote do contador v2.
- Oitavo ciclo, pacote do contador v2 iniciado em 31/08/2026: o ZIP mensal passou ao contrato `accounting_monthly_package_v2`, mantendo caminhos legados do v1 durante a transição. A competência fiscal prioriza `dhEmi`/`dEmi`, registra `dhRecbto` quando disponível e explicita o fallback; saídas, entradas, itens, cancelamentos, CC-e, manifestações e eventos recebidos são exportados por filial a partir dos XMLs armazenados. O manifesto contém contagens, tamanho e SHA-256 de cada arquivo, e o filtro de filial deixou de incluir outras lojas da mesma empresa. Quatro testes focados cobriram extração tributária, XML inválido, competência, integridade, entradas/eventos e isolamento; as regressões completas passaram com 252 testes fiscais e 49 financeiros (301 no total). Focus, SEFAZ direta, rede e produção não foram alterados e permaneceram desligados. A posição atual de estoque também passou a ser exportada pelo custo médio ponderado móvel, com quantidade física/reservada/disponível, valor total e qualidade temporal explícita; competências passadas são marcadas como não retroativas. Próxima ação: snapshots auditáveis de quantidade e custo para fechamento histórico.
- Nono ciclo, fechamento contábil do estoque concluído estruturalmente em 31/08/2026: as migrations estoque 0023/0024 criaram cabeçalhos e itens imutáveis por filial/data, responsável autorizado e auditoria, com dados cadastrais congelados, quantidades, custo médio ponderado móvel, valor e SHA-256. O comando `capturar_fechamento_estoque_contabil` exige confirmação, aceita somente o dia atual, é idempotente e recusa divergência posterior. O pacote usa o snapshot apenas com cobertura completa das filiais e mantém fallback temporal explícito. Quatro testes do fechamento e o teste integrado do pacote passaram; a regressão completa de estoque e financeiro aprovou 121 testes. Próxima ação: reconciliação ampliada do pacote v2.
- Décimo ciclo, reconciliação operacional do pacote v2 concluída estruturalmente em 31/08/2026: o contrato `accounting_operational_reconciliation_v1` cruza, por filial e competência, vendas finalizadas, pagamentos confirmados, livro financeiro, documentos emitidos, itens e movimentos de estoque; nas compras, cruza totais dos itens, DF-e vinculado, contas a pagar e entrada de estoque. O ZIP inclui resumo JSON e CSVs separados, o manifesto contabiliza registros e divergências, e nenhuma diferença altera dados ou cria obrigação automaticamente. Consultas de estoque são processadas em lotes para suportar volumes mensais. Três testes focados cobrem coerência, divergências e isolamento; o teste integrado do pacote e a regressão financeira completa com 52 testes também passaram. Focus, SEFAZ direta, rede e produção não foram alterados. Próxima ação: definir o contrato do software contábil e o responsável pela EFD ICMS/IPI, então validar uma amostra mensal e registrar o aceite.
- Décimo primeiro ciclo, contrato de integração contábil estruturado em 31/08/2026: a migration financeiro 0021 criou versões imutáveis por empresa sob o contrato `accounting_integration_agreement_v1`. Somente o Master registra rascunhos ou valida versões; administrador e Contabilidade consultam o resumo. A validação exige software/escritório destinatário, formato técnico, responsável externo pela EFD ICMS/IPI e referência do aceite. ZIP e API declaram o estado sem expor segredos, preços ou condições comerciais; nenhum cadastro envia arquivo ou gera obrigação. O envio preexistente por adaptador passou a exigir versão validada especificamente no formato de adaptador: configuração de servidor, rascunho, ZIP ou API não liberam a chamada. Os testes focados e integrados e a regressão financeira completa com 57 testes passaram. A definição real permanece pendente enquanto não houver contador/software e dados da empresa. Próxima ação: estruturar o validador da amostra mensal e o registro de aceite, mantendo tudo inativo até dados reais.
- Décimo segundo ciclo, validação da amostra contábil concluída estruturalmente em 31/08/2026: a migration financeiro 0022 criou o aceite imutável por empresa, competência, versão de contrato e SHA-256 do pacote. O contrato `accounting_monthly_sample_validation_v1` valida ZIP v2, empresa, versão contratual, manifesto, hashes, arquivos obrigatórios, XMLs de entrada/saída, reconciliação sem divergências e fechamento imutável completo de estoque; caminhos inseguros, duplicidades e limites excessivos são recusados. Somente o Master acessa a tela e registra aceite mediante referência e confirmação explícita; o processo é idempotente e auditado. Quatro testes focados e a regressão financeira completa com 61 testes passaram. Nenhum arquivo é transmitido, nenhuma EFD é gerada e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação externa: com dados reais, registrar o contrato validado, gerar a amostra, obter conferência do contador e arquivar a referência do aceite.
- Décimo terceiro ciclo, reposição integrada a Compras concluída estruturalmente em 31/08/2026: o relatório de sugestão passou a permitir que perfis de Compras selecionem até 500 itens de uma única filial e criem uma cotação em rascunho pelo contrato `replenishment_quote_draft_v1`. Período, filial, produtos e quantidades são recalculados no servidor; adulterações, duplicidades, itens externos e perfis sem permissão são recusados. Uma chave SHA-256 única garante idempotência sob repetição e concorrência. A ação é auditada e não abre a cotação, não escolhe fornecedor, não envia pedido e não altera estoque, preço, financeiro ou fiscal. A migration compras 0010 materializou a chave técnica. Três testes focados e, após o endurecimento concorrente, a regressão conjunta de Relatórios/Compras com 76 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: avaliar o fechamento operacional de validade/perdas sem automatizar descarte ou baixa.
- Décimo quarto ciclo, planejamento de validade concluído estruturalmente em 31/08/2026: lotes vencidos ou a vencer em até 30 dias ganharam o contrato `inventory_expiry_treatment_plan_v1`, com estados de separação, devolução, promoção ou descarte planejados, observação, responsável, horário e auditoria. Promoção de lote vencido é recusada; itens fora da janela ou de outra empresa também são bloqueados. Repetir o mesmo plano é idempotente. Nenhuma dessas decisões reduz saldo, cria perda, altera preço, financeiro ou fiscal; a baixa continua separada e exige o fluxo de perda com supervisor. A migration estoque 0025 materializou o plano. Três testes focados e a regressão completa de Estoque com 75 testes passaram. Próxima ação: vincular uma baixa de perda autorizada ao lote exato, evitando que o FEFO consuma outra camada.
- Décimo quinto ciclo, perda por vencimento no lote exato concluída estruturalmente em 31/08/2026: `PerdaEstoque` passou a guardar o lote e o núcleo de movimentação recebeu direcionamento obrigatório por `lote_id`. A baixa só ocorre em lote efetivamente vencido com descarte previamente planejado, quantidade positiva dentro do saldo e autorização de supervisor; custo histórico do lote, movimento agregado e alocação da camada são gravados na mesma transação. O FEFO não consome outra camada e saldo zerado muda o plano para Baixa concluída. A migration estoque 0026 materializou o vínculo e o novo estado. Três testes focados e a regressão completa de Estoque com 78 testes passaram. Nenhuma operação fiscal, financeira ou externa foi ativada. Próxima ação: consolidar um relatório operacional de perdas por lote, causa e valor para conferência gerencial.
- Décimo sexto ciclo, relatório gerencial de perdas concluído estruturalmente em 31/08/2026: o relatório existente passou ao contrato `inventory_loss_management_report_v1`, preservando registros legados sem lote e acrescentando filtros por causa e vínculo de lote, quantidade total, consolidação por lote/produto/filial e valores estimados de custo e venda. A tela, o CSV e a impressão aplicam o mesmo escopo e exibem lote, validade, causa e motivo; usuários de uma empresa não acessam dados de outra. O fluxo é somente leitura e não movimenta estoque, não cria lançamento financeiro e não aciona emissão fiscal ou serviço externo. Três testes focados e a regressão completa de Relatórios com 15 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: consolidar uma fila diária de lotes com tratamento de validade pendente, priorizada por vencimento e status, sem automatizar descarte ou baixa.
- Décimo sétimo ciclo, fila diária de validade concluída estruturalmente em 31/08/2026: a própria tela de lotes recebeu o contrato `inventory_expiry_daily_queue_v1`, sem duplicar cadastros. A fila inclui somente camadas com saldo e validade vencida ou em até 30 dias, exclui baixa concluída e prioriza, nesta ordem, vencidos sem tratamento, vencidos em tratamento, próximos sem tratamento e próximos em tratamento; dentro de cada grupo, a validade mais antiga aparece primeiro. Contadores destacam fila total e itens ainda não iniciados, o filtro por estado é validado no servidor e a tela informa dias de atraso ou prazo restante. A consulta respeita o escopo da empresa e não movimenta estoque, não registra perda, não altera preço e não aciona financeiro, fiscal ou serviço externo. Três testes focados e a regressão completa de Estoque com 81 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: registrar uma conferência física auditável do lote, com quantidade observada e dados congelados, antes de decisões irreversíveis, sem ajustar saldo automaticamente.
- Décimo oitavo ciclo, conferência física auditável da validade concluída estruturalmente em 31/08/2026: a migration estoque 0027 criou o registro imutável sob o contrato `inventory_expiry_physical_check_v1`. Cada conferência congela empresa, filial, produto, código e validade do lote, custo, saldo do sistema, quantidade observada, diferença, estado do tratamento, responsável, horário, observação e SHA-256. Divergência exige justificativa e nunca ajusta estoque automaticamente. A perda no lote vencido agora exige uma conferência do mesmo dia, ainda compatível com código, validade, custo e saldo atuais, e não pode superar a quantidade observada; uma baixa parcial invalida a evidência anterior e exige nova contagem para a próxima baixa. A tela preserva o histórico, informa se a evidência está válida e mantém autorização de supervisor para a perda. Dez testes focados e a regressão completa de Estoque com 85 testes passaram. O banco local contém zero conferências fictícias. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: integrar o estado da conferência à fila diária, distinguindo pendente, divergente e pronto para decisão, sem ajustar saldo automaticamente.
- Décimo nono ciclo, estados de conferência integrados à fila diária concluídos em 31/08/2026: o contrato `inventory_expiry_daily_queue_v2` classifica em tempo real cada lote da janela como Pendente ou desatualizado, Divergente ou Pronto para decisão. A classificação usa somente a conferência mais recente do dia e exige correspondência de código, validade, custo e saldo; qualquer alteração retorna o item para Pendente. A fila ganhou contadores, filtro validado no servidor e coluna com saldo observado, mantendo a prioridade de vencimento e tratamento e ordenando pendências antes de divergências e itens prontos dentro de cada grupo. Os três contadores são calculados em uma única agregação e nenhuma classificação grava dados, ajusta estoque ou cria perda. Cinco testes focados e a regressão completa de Estoque com 87 testes passaram. Não houve nova migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: permitir que divergências selecionadas originem um inventário em rascunho para a filial e o produto, com recálculo no servidor e sem aplicar ajuste automaticamente.
- Vigésimo ciclo, divergências encaminhadas ao inventário em rascunho concluído estruturalmente em 31/08/2026: o contrato `inventory_expiry_divergence_inventory_draft_v1` reutiliza o inventário auditado existente. A fila permite selecionar somente lotes classificados como divergentes; o servidor revalida escopo, limite de 200, filial única, saldo e conferência vigente antes de criar. Produtos repetidos em vários lotes viram um único item, sempre com quantidade contada pendente e orientação para contagem total do produto. A migration estoque 0028 registra a origem Manual, Fila de risco ou Divergência de validade e uma chave SHA-256 idempotente baseada nas evidências selecionadas; repetição retorna o mesmo inventário. Aplicação continua bloqueada até todas as contagens e ainda exige supervisor. Nove testes focados e a regressão completa de Estoque com 91 testes passaram. A migration foi aplicada localmente; o inventário anterior foi preservado e nenhum rascunho fictício de divergência foi criado. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: persistir o vínculo relacional entre os itens do inventário e cada conferência/lote de origem, exibindo essa trilha no detalhe sem permitir alteração das evidências.
- Vigésimo primeiro ciclo, trilha relacional e bloqueio de aplicação por lote concluídos estruturalmente em 31/08/2026: a migration estoque 0029 criou `OrigemItemInventarioValidade`, vínculo imutável e único entre item do inventário, conferência e lote. Vários lotes do mesmo produto preservam vínculos separados no item deduplicado; repetição idempotente não duplica a trilha. O detalhe do inventário abre a evidência exata, a evidência retorna aos inventários originados, o histórico do lote ganhou acesso ao registro somente leitura e o Admin não permite inclusão, alteração ou exclusão. A revisão do aplicador revelou que reduções agregadas reconciliam camadas por FEFO e poderiam consumir lote diferente do divergente; por segurança, inventários originados por validade agora permanecem bloqueados mesmo após a contagem agregada, até existir contagem específica por lote. Dez testes focados e duas regressões completas de Estoque, ambas com 92 testes, passaram. A migration foi aplicada localmente e não criou vínculos fictícios. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: criar contagem por lote para cada vínculo, validar a soma contra a contagem total do produto e aplicar a reconciliação diretamente nas camadas corretas, de forma atômica e com supervisor.
- Vigésimo segundo ciclo, contagem completa e reconciliação atômica por lote concluídos estruturalmente em 31/08/2026: a migration estoque 0030 criou o escopo imutável de lotes do inventário e o histórico imutável de contagens sob o contrato inventory_expiry_lot_count_v1. Ao abrir o rascunho, todos os lotes positivos dos produtos selecionados entram no escopo congelado; somente os lotes divergentes mantêm vínculo com a evidência original, enquanto os demais são identificados como complementares para fechar a contagem total. Cada recontagem preserva saldo do sistema, quantidade física, responsável, horário, observação e SHA-256. A aplicação exige contagem total do produto, contagem de cada lote, igualdade exata entre as somas, saldo agregado integralmente rastreado, ausência de lote novo, ausência de alteração após a contagem e supervisor. A transação cria ajustes diretamente nos lotes exatos, atualiza o agregado e registra auditoria; qualquer falha reverte tudo, sem FEFO. O escopo fechado também remove a inclusão manual de produtos. Doze testes focados e a regressão completa de Estoque com 99 testes passaram. A migration foi aplicada localmente e registrou zero escopos e zero contagens fictícias. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: modelar uma retificação auditável para sobra física que ultrapasse a quantidade inicial registrada do lote, sem reescrever o histórico original, e cobrir cancelamento/expiração segura de rascunhos de contagem.

- Vigésimo terceiro ciclo, retificação auditável de sobra física concluída estruturalmente em 31/08/2026: a migration estoque 0031 preserva quantidade_inicial e acrescenta ao lote somente a capacidade adicional acumulada por eventos autorizados. RetificacaoCapacidadeLoteEstoque registra de forma imutável inventário, contagem, quantidade inicial, capacidade anterior, acréscimo, nova capacidade, quantidade contada, justificativa, solicitante, supervisor, horário e SHA-256 sob o contrato inventory_lot_capacity_rectification_v1. Uma contagem acima da capacidade exige justificativa e não altera saldo sozinha; a ampliação é criada apenas durante a aplicação atômica já autorizada, junto com movimento, camada, saldo agregado, status e auditoria. Falha posterior em qualquer lote reverte também a retificação. A tela exibe quantidade inicial e capacidade auditada, e o Admin é somente leitura. Quinze testes focados e a regressão completa de Estoque com 102 testes passaram. A migration foi aplicada localmente e registrou zero retificações fictícias. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: implementar cancelamento explícito e expiração segura dos rascunhos de inventário não concluídos, preservando escopos, contagens e evidências para auditoria.
- Vigésimo quarto ciclo, cancelamento, expiração e nova tentativa segura concluídos estruturalmente em 31/08/2026: a migration estoque 0032 acrescenta prazo, encerramento, responsável, motivo, status Expirado e chave-base de origem. Rascunhos de divergência recebem prazo operacional de 24 horas; contagem e aplicação são bloqueadas assim que o prazo vence, mesmo antes da materialização. O cancelamento exige justificativa mínima e supervisor, não movimenta saldo e preserva itens, escopos, contagens e evidências. A rotina explícita expirar_inventarios_validade encerra somente rascunhos de validade vencidos, exige confirmação, gera auditoria sistêmica e não ajusta estoque. A migração atribui chave-base e prazo aos rascunhos antigos sem expirá-los. Após cancelamento ou expiração, as mesmas evidências podem abrir uma nova tentativa com chave única, enquanto repetições de uma tentativa ativa continuam idempotentes. Lista e detalhe exibem prazo e encerramento; o Admin de inventários e itens tornou-se estritamente somente leitura. Vinte e um testes focados e a regressão completa de Estoque com 108 testes passaram. A migration foi aplicada localmente; não havia inventário de validade antigo para converter. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: integrar a rotina de expiração ao ciclo de manutenção do servidor local com execução idempotente e visibilidade operacional, e então consolidar um cenário piloto ponta a ponta de compra, lote, venda, perda, inventário e fechamento.
- Vigésimo quinto ciclo, manutenção automática dos inventários de validade concluída estruturalmente em 01/09/2026: a migration estoque 0033 criou o histórico imutável `ExecucaoManutencaoInventarioValidade` sob os contratos `inventory_expiry_maintenance_run_v1` e `inventory_expiry_maintenance_status_v1`. Cada execução diária registra identificador, início, fim, sucesso ou falha, quantidade encerrada, código de erro sanitizado e SHA-256, sem guardar caminho, credencial ou conteúdo sensível. O comando agora registra sucesso mesmo quando não há rascunhos, mantém repetição idempotente e grava falha fora da transação revertida. O script `register_inventory_expiry_maintenance_task.ps1` agenda a rotina diariamente, pode usar `SYSTEM`, inicia quando possível, impede sobreposição e limita a execução a dez minutos. A lista de inventários e a Central do servidor mostram última execução, atraso, falha e rascunhos vencidos; o Admin preserva o histórico somente leitura. A migration foi aplicada localmente e confirmou zero históricos artificiais e zero rascunhos vencidos. Seis testes focados, o teste integrado da Central e a regressão completa de Estoque com 113 testes passaram. Nenhum saldo foi alterado, nenhuma chamada externa foi realizada e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: preparar e executar um ensaio ponta a ponta isolado de compra, lote, venda, perda, inventário e fechamento, com dados sintéticos e relatório de evidências, sem emissão ou transmissão fiscal.
- Vigésimo sexto ciclo, ensaio ponta a ponta de estoque e validade concluído estruturalmente em 01/09/2026: o verificador somente leitura `inventory_pilot_end_to_end_evidence_v1` cruza entrada finalizada, camadas de lote, venda, alocação FEFO, perda no lote vencido exato, origem e ajuste do inventário e fechamento imutável. O relatório exige uma única filial e um produto comum, confirma saldo agregado contra as camadas, saldo final contra o fechamento, ausência de documento fiscal na venda do ensaio e gera SHA-256 próprio. O comando `verificar_fluxo_estoque_piloto` aceita modo estrito e distingue explicitamente dados sintéticos de um futuro piloto real. O teste integrado criou dez unidades em dois lotes, vendeu duas somente do lote válido, baixou uma vencida, reconciliou uma divergência por lote e fechou seis unidades; também confirmou que registros de filiais diferentes são recusados. A Central do servidor expõe o comando ao Master. O ensaio integrado, o teste da Central e a regressão completa de Estoque com 114 testes passaram. O banco temporário foi destruído e nenhum dado sintético foi gravado localmente. Nenhum documento fiscal foi criado, nenhuma chamada externa ocorreu e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação externa: repetir o roteiro com registros reais da filial piloto, arquivar o JSON/SHA-256 e obter a conferência operacional; enquanto isso, seguir para melhorias internas que não dependam de CNPJ ou enquadramento real.

- Vigésimo sétimo ciclo, saldo vendável e quarentena por lote concluídos estruturalmente em 01/09/2026: o núcleo de estoque passou a separar saldo físico de saldo efetivamente liberado ao caixa. Vendas consomem somente lotes não vencidos nos estados Não iniciado ou Promoção planejada; lotes Separado, Devolução planejada, Descarte planejado e Baixa concluída permanecem bloqueados. A validação ocorre dentro da transação da venda, antes da baixa, inclusive para produtos que não exigem lote, e a recusa reverte venda, itens, pagamentos e movimentos. Perdas direcionadas continuam alcançando o lote segregado autorizado. A tela de estoque distingue físico, reservado, disponível físico, vendável e bloqueado por lote, calculando a página em lote para evitar consultas repetidas. Não houve migration. Cinco testes focados, incluindo o fluxo completo do caixa, e a regressão conjunta de Estoque e Vendas com 137 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: ampliar a evidência do piloto para preservar e validar a situação de tratamento dos lotes no momento do consumo, sem depender do estado atual mutável do lote.
- Vigésimo oitavo ciclo, evidência histórica da liberação do lote concluída estruturalmente em 01/09/2026: a migration estoque 0034 acrescentou à alocação por lote os snapshots de código, validade e estado de tratamento, além de SHA-256 calculado sobre movimento, lote, quantidade, custo e fotografia. Novas alocações são preenchidas automaticamente e protegidas contra alteração ou exclusão pelo modelo e pelo Admin; registros anteriores permanecem vazios, identificados honestamente como legado sem prova retroativa. O contrato do piloto evoluiu para `inventory_pilot_end_to_end_evidence_v2`, passou a comparar validade com a data da venda, validar integridade e tratamento liberado e publicar as fotografias no JSON. O teste integrado altera validade e tratamento do lote depois da venda e comprova que a evidência original permanece íntegra. A migration foi aplicada localmente: havia zero alocações, portanto zero registros legados ou alterados. Sete testes focados e a regressão conjunta de Estoque, Vendas e Configurações com 277 testes passaram; a prova negativa confirmou que snapshot ausente torna a evidência v2 inválida. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: criar um diagnóstico somente leitura de cobertura dos snapshots por filial, com contagem de registros íntegros, legados e inconsistentes, visível apenas ao Master.
- Vigésimo nono ciclo, diagnóstico de cobertura dos snapshots de venda por lote concluído em 01/09/2026: o contrato `inventory_lot_snapshot_coverage_v1` percorre as alocações de venda em lotes de até 1.000 registros e classifica por filial snapshots íntegros, legados sem fotografia e inconsistentes. Integridade exige SHA-256 válido, tratamento liberado e validade compatível com a data do movimento; a consulta usa duas queries, não altera nem corrige dados e inclui filiais sem vendas. A Central e seu manifesto mostram totais, percentual e estado somente ao Master; administradores de empresa não veem o painel e continuam sem acesso ao manifesto. No banco local, nove filiais foram consultadas e não havia vendas por lote, resultando em estado Sem vendas por lote, com zero registros alterados. Três testes focados e a regressão completa de Estoque e Configurações com 260 testes passaram. Não houve migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: incorporar o diagnóstico ao gate de prontidão do piloto real, bloqueando aceite diante de inconsistência e mantendo legado como pendência explícita.
- Trigésimo ciclo, trava de prontidão do piloto real concluída em 01/09/2026: o contrato `inventory_real_pilot_readiness_v1` transforma a cobertura histórica da filial em estados objetivos. Ausência de vendas por lote fica como Sem base; qualquer registro legado ou inconsistente bloqueia o aceite; somente uma base existente e integralmente íntegra fica Pronta estruturalmente. O relatório ponta a ponta evoluiu para `inventory_pilot_end_to_end_evidence_v3` e aplica essa trava como verificação obrigatória quando os IDs informados são reais. Ensaios marcados com `--dados-sinteticos` continuam verificáveis, mas declaram que a trava não foi aplicada ao aceite. A Central do servidor explica a regra somente ao Master. Quatro testes focados e a regressão completa de Estoque e Configurações com 261 testes passaram. Não houve migration nem correção retroativa, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: criar uma prévia somente leitura do ensaio por filial que liste candidatos aos cinco registros e impedimentos antes da execução do comando, sem selecionar ou aprovar dados automaticamente.
- Trigésimo primeiro ciclo, prévia dos candidatos do piloto concluída em 01/09/2026: o contrato `inventory_pilot_candidate_preview_v1` lista, por filial e em janela limitada, entradas finalizadas, vendas finalizadas sem documento fiscal, perdas por vencimento vinculadas a lote, inventários aplicados e fechamentos de estoque. O relatório mostra os produtos presentes nas cinco categorias, incorpora a prontidão histórica e explicita ausência de base, categorias vazias ou falta de produto comum. Ele não combina nem escolhe IDs automaticamente, não altera dados e não acessa a rede. O comando `previsualizar_fluxo_estoque_piloto` aceita limite de 1 a 100 e modo estrito; a Central exibe seu uso somente dentro do painel do Master, sem mostrá-lo ao administrador da empresa. Seis testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: produzir uma ficha de execução do piloto a partir de IDs escolhidos pelo Master, validando compatibilidade antes da operação e sem criar aprovação automática.
- Trigésimo segundo ciclo, ficha de execução do piloto concluída estruturalmente em 08/09/2026: o contrato `inventory_pilot_execution_sheet_v1` recebe os cinco IDs escolhidos manualmente e, antes do verificador final, confirma filial única, produto comum único, estados finalizados, venda sem documento fiscal, perda por vencimento vinculada ao lote, inventário aplicado, hash do fechamento e prontidão histórica. A ficha lista cada impedimento, monta o comando final somente com IDs inteiros e gera SHA-256 próprio, mas declara `aprovacao_automatica=false`. O comando `gerar_ficha_execucao_piloto` possui modo estrito e fica visível somente no painel Master; seleção entre filiais diferentes é recusada sem acessar rede ou alterar dados. Três testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: permitir ao Master gerar a prévia e a ficha pela interface visual, com seleção explícita de filial e IDs, mantendo confirmação humana e sem executar o ensaio automaticamente.
- Trigésimo terceiro ciclo, interface Master do piloto concluída estruturalmente em 08/09/2026: o painel exclusivo de snapshots na Central ganhou dois cartões responsivos. O primeiro exige seleção explícita de filial e baixa a prévia JSON com limite validado; o segundo exige os cinco IDs positivos e uma confirmação humana antes de baixar a ficha JSON assinada. As rotas recusam administradores de empresa, devolvem erros sanitizados para entradas inválidas e não oferecem ação para executar automaticamente o verificador final. Os nomes dos arquivos identificam filial ou hash sem expor conteúdo fiscal. Três testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, gravação operacional ou chamada externa; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: adicionar à ficha orientações operacionais e campos de responsáveis pela execução e conferência, ainda sem persistir aceite ou dados pessoais automaticamente.
- Trigésimo quarto ciclo, responsabilidade operacional da ficha do piloto concluída estruturalmente em 08/09/2026: o contrato evoluiu para `inventory_pilot_execution_sheet_v2` e passou a exigir identificação manual de quem executa e de quem confere, recomendar separação de funções, aceitar observação operacional limitada e incluir um roteiro fixo de conferência, execução isolada e arquivamento. CPF, CNPJ e e-mail são recusados; os dados informados existem somente no JSON baixado, entram no SHA-256 da ficha e não são persistidos no banco nem registrados como aceite. Linha de comando e interface Master seguem as mesmas regras, enquanto administradores de empresa continuam sem acesso. Três testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, emissão, transmissão ou chamada externa; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: criar um verificador offline de integridade que confira o SHA-256 da ficha baixada e seu vínculo com o relatório final v3, sem persistir aceite ou executar integrações.
- Trigésimo quinto ciclo, verificação offline dos artefatos do piloto concluída estruturalmente em 08/09/2026: o contrato `inventory_pilot_artifact_integrity_v1` recalcula os SHA-256 da ficha v2 e do relatório final v3, valida contratos, horários, filial, produto, os cinco IDs e os estados apta/válida. O leitor aceita JSON UTF-8 com ou sem BOM, limita cada arquivo local a 5 MB e recusa links simbólicos e caminhos de rede. O relatório resultante não repete responsáveis, possui SHA-256 próprio e declara que não consulta banco, não persiste resultado nem registra aceite. O comando `verificar_artefatos_piloto` possui modo estrito e aparece somente no painel Master; quatro testes focados, incluindo o cenário ponta a ponta real do sistema, e a regressão completa de Estoque e Configurações com 265 testes passaram. Não houve migration, emissão, transmissão ou chamada externa; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: permitir ao Master baixar o relatório final v3 pela interface após confirmação explícita, sem executar emissão fiscal e mantendo a conferência offline como etapa separada.
- Trigésimo sexto ciclo, download visual do relatório final v3 concluído estruturalmente em 08/09/2026: o painel exclusivo do Master ganhou uma terceira etapa que recebe os cinco IDs, exige confirmação própria e obriga a escolha consciente entre ensaio sintético e piloto real. O primeiro declara que a trava histórica não foi aplicada ao aceite; o segundo aplica e publica a prontidão real da filial. O servidor reutiliza o gerador `inventory_pilot_end_to_end_evidence_v3`, revalida todos os vínculos e entrega inclusive relatórios reprovados como evidência, sem transformá-los em aprovação. Arquivos identificam tipo, filial e prefixo do SHA-256; erros são sanitizados e administradores da empresa não veem o cartão nem acessam a rota. Três testes focados, incluindo as duas modalidades e as recusas por falta de confirmação ou tipo, e a regressão completa de Estoque e Configurações com 265 testes passaram. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: oferecer ao Master a conferência dos dois arquivos pela interface local, processando uploads apenas em memória, com limite de 5 MB e sem persistir conteúdo ou resultado.
- Trigésimo sétimo ciclo, conferência visual dos artefatos em memória concluída estruturalmente em 08/09/2026: o quarto cartão do painel Master recebe a ficha v2 e o relatório final v3, exige confirmação e entrega para download o resultado `inventory_pilot_artifact_integrity_v1`. Um handler dedicado, instalado antes da validação CSRF, mantém os arquivos somente em memória; cada JSON é limitado a 5 MB, a requisição total também é limitada e extensão, codificação, raiz e conteúdo são validados. A proteção CSRF permanece ativa e foi testada com e sem token. Resultado íntegro ou reprovado não persiste arquivo, nome, responsável ou aceite, não consulta banco e não acessa rede; administradores da empresa não veem o cartão nem acessam a rota. Oito testes focados cobriram o fluxo real da interface, adulteração, tamanho, confirmação, CSRF e permissão; a regressão completa de Estoque e Configurações passou com 267 testes. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: consolidar um dossiê ZIP local do piloto com ficha, relatório e verificação já fornecidos pelo Master, validando tudo em memória e sem registrar aceite automático.
- Trigésimo oitavo ciclo, dossiê ZIP local do piloto concluído estruturalmente em 08/09/2026: o quinto cartão exclusivo do Master recebe ficha v2, relatório v3 e o resultado `inventory_pilot_artifact_integrity_v1`, exige confirmação e somente gera o pacote `inventory_pilot_dossier_v1` quando todo o conjunto continua íntegro e coerente. Os três uploads permanecem em memória, são limitados individualmente a 5 MB e têm limite total; a proteção CSRF continua ativa. O servidor recalcula contratos, hashes, filial, produto, cinco IDs, estados e proteções contra persistência ou aceite, recusando conferência adulterada ou pertencente a outro ensaio. O ZIP usa quatro nomes internos fixos e inclui manifesto com tamanhos e SHA-256 dos bytes empacotados, além de hash próprio e declaração explícita de que não é assinatura digital. Administradores da empresa não veem o cartão nem acessam a rota. Seis testes focados e a regressão completa de Estoque e Configurações com 270 testes passaram. Não houve migration, gravação operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: criar um verificador offline do dossiê ZIP que valide entradas, manifesto e hashes sem extrair arquivos ou consultar o banco.
- Trigésimo nono ciclo, verificação offline do dossiê ZIP concluída estruturalmente em 08/09/2026: o comando `verificar_dossie_piloto` publica o contrato `inventory_pilot_dossier_integrity_v1` e, em modo estrito, reprova qualquer pacote inconsistente. O leitor aceita somente arquivo local limitado, recusa links simbólicos e exige exatamente os quatro nomes fixos, sem entradas extras, duplicadas, criptografadas ou métodos de compressão inesperados. Antes de ler o conteúdo, limita cada entrada e a soma descompactada; depois confere CRC, JSON UTF-8, contrato, SHA-256 próprio do manifesto e reconstrói o manifesto esperado a partir da ficha, relatório e conferência. Alteração interna continua sendo detectada mesmo com o ZIP recomposto e CRC válido. O relatório possui hash próprio, não inclui caminho nem responsáveis, não extrai arquivos, não persiste resultado, não consulta banco e não acessa rede. O comando aparece somente no painel Master. Quatro testes novos e a regressão completa de Estoque e Configurações com 274 testes passaram. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: oferecer a mesma conferência do ZIP na interface Master, mantendo upload em memória, confirmação explícita e ausência de armazenamento.
- Quadragésimo ciclo, conferência visual do dossiê ZIP concluída estruturalmente em 08/09/2026: o sexto cartão exclusivo do Master recebe o dossiê, exige confirmação e baixa o relatório `inventory_pilot_dossier_integrity_v1`. Um handler dedicado limita a requisição e mantém o ZIP integralmente em memória; nenhuma entrada é extraída. Pacotes estruturalmente válidos ou reprovados produzem relatório sanitizado, enquanto extensão, ausência, tamanho ou confirmação inválidos retornam erro controlado. A proteção CSRF foi testada com e sem token, e administradores da empresa não veem o cartão nem acessam a rota. O nome do ZIP gerado passou a conter o prefixo do SHA-256 do arquivo inteiro, que é publicado integralmente pelo relatório visual para comparação. Onze testes focados cobriram fluxo real completo, pacote inválido, confirmação, CSRF, permissão, ausência de extração e hash; a regressão completa de Estoque e Configurações passou com 275 testes, seguida da revalidação integrada do vínculo entre nome e hash. Não houve migration, persistência, aceite, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: organizar as seis ferramentas do piloto como roteiro visual numerado, com arquivos esperados e critérios claros de parada, sem automatizar aprovação ou execução.
- Quadragésimo primeiro ciclo, roteiro visual numerado do piloto concluído estruturalmente em 08/09/2026: o painel exclusivo do Master agora apresenta as seis etapas na ordem 1 a 6 e repete o número em cada cartão. O guia informa os arquivos esperados da prévia, ficha, relatório, conferência dos JSON, dossiê e conferência do ZIP, além dos critérios objetivos que obrigam o operador a parar. A etapa final esclarece que integridade confirmada não constitui aceite real. O layout usa três colunas em telas amplas e uma coluna em telas menores, sem criar estado oculto, encadear requisições, reaproveitar uploads ou executar aprovação automática. Um teste novo verifica a ordem real no HTML, os seis nomes de saída e os avisos de parada; a regressão completa de Estoque e Configurações passou com 276 testes. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: retomar a matriz fiscal GO pelos cenários ainda bloqueados, começando pela preparação segura da devolução ao fornecedor, sem emissão e sem presumir tributação antes dos dados reais e da revisão do contador.
- Quadragésimo segundo ciclo, pré-diagnóstico da devolução ao fornecedor concluído estruturalmente em 09/09/2026: o contrato `supplier_return_fiscal_preparation_v1` passou a conferir, na entrada finalizada, chave de 44 dígitos, XML integral preservado pelo DF-e, modelo 55, vínculo entre chaves, CNPJ do emitente/fornecedor, CNPJ do destinatário/filial e presença dos itens fiscais originais. A leitura reaproveita o retrato tributário do XML e não reconstrói impostos pelo cadastro ou custo. A tela de compras exibe somente a situação documental e as decisões pendentes; “base disponível” não libera emissão. CFOP e tributação permanecem vazios, e o contrato afirma `permite_emissao=False` e `permite_transmissao=False`. Os 17 testes focados e a regressão conjunta de Compras e Fiscal com 320 testes passaram. Não houve migration, documento fiscal, numeração, estoque, rede ou transmissão; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar um rascunho persistente de devolução, ligado à entrada e com seleção limitada de itens e quantidades, sem ainda gerar XML ou assumir tratamento tributário.
- Quadragésimo terceiro ciclo, rascunho operacional da devolução ao fornecedor concluído estruturalmente em 09/09/2026: o contrato `supplier_return_draft_v1` e a migration fiscal 0036 passaram a preservar entrada, chave referenciada, motivo, autor, última atualização e itens com quantidade recebida em snapshot. A seleção aceita até três casas decimais, rejeita números inválidos ou acima do recebido e permite somente uma preparação ativa por entrada. Atualizações substituem os itens dentro de uma transação; cancelamentos liberam a seleção sem apagar o histórico. A entrada não pode ser cancelada enquanto houver preparação ativa, e as rotas respeitam o isolamento por empresa. A interface permite salvar e cancelar o rascunho, sempre declarando que nenhuma nota, estoque ou transmissão foi gerada. Os 16 testes focados e de isolamento e a regressão conjunta de Compras e Fiscal com 326 testes passaram. Nenhum `DocumentoFiscal`, série, número, XML, tributo, movimento de estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar a submissão do rascunho para revisão fiscal e mapear cada seleção ao `nItem` do XML original, sem ainda calcular tributos ou gerar NF-e.
- Quadragésimo quarto ciclo, mapeamento ao XML e submissão para revisão concluídos estruturalmente em 09/09/2026: a migration compras 0011 preserva o `nItem` em cada camada/lote criada por novas importações. Para entradas legadas, o vínculo automático só ocorre quando os identificadores do produto correspondem a um único item do XML; ausência, divergência ou ambiguidade bloqueiam o rascunho. Cada seleção guarda o `nItem` e o snapshot completo do item fiscal original, e a soma de lotes não pode ultrapassar a quantidade daquele item. A migration fiscal 0037 adiciona responsável, horário e SHA-256 do XML à submissão e uma restrição de banco impede o estado “aguardando revisão” sem essas três evidências. Depois de submetido, o rascunho não pode ser alterado, embora possa ser cancelado sem efeitos externos. A tela mostra o `nItem`, a situação e o hash, mas não oferece emissão. Os 35 testes focados de devolução, importação e isolamento e a regressão conjunta de Compras e Fiscal com 329 testes passaram. Nenhum cálculo novo, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: implementar a decisão segregada do revisor fiscal, permitindo devolver para correção ou aprovar apenas a preparação, sem liberar emissão automaticamente.
- Quadragésimo quinto ciclo, revisão fiscal segregada da devolução ao fornecedor concluída estruturalmente em 09/09/2026: o contrato `supplier_return_fiscal_review_v1` e a migration fiscal 0038 criam decisões sequenciais e imutáveis, com aprovação da preparação ou devolução para correção, justificativa obrigatória, responsável, horário, snapshot integral e SHA-256 do conteúdo decidido. A fila visual é isolada por empresa e exclusiva de Administrador e Contabilidade; Compras e Financeiro não acessam nem decidem. O XML original é novamente conferido pelo hash no instante da decisão. A devolução para correção reabre o mesmo rascunho e preserva o histórico; a aprovação bloqueia edição e cancelamento pelo comprador, mas não autoriza emissão. Os 19 testes focados e a regressão conjunta de Compras e Fiscal com 335 testes passaram. Nenhum cálculo tributário, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: modelar um parecer tributário versionado para receber natureza, CFOP e tratamento por tributo somente quando validados pelo contador, sem valores presumidos nem emissão.
- Quadragésimo sexto ciclo, parecer tributário versionado da devolução ao fornecedor concluído estruturalmente em 09/09/2026: o contrato `supplier_return_tax_opinion_v1` e a migration fiscal 0039 preservam versões append-only e idempotentes somente sobre preparação aprovada. Cada parecer exige data, regime e natureza informados pelo responsável, CFOP de saída do modelo 55 presente no catálogo oficial vigente e manifestação textual explícita sobre ICMS, ICMS-ST/FCP, IPI, PIS, COFINS, cBenef e IBS/CBS, inclusive quando não aplicáveis. Snapshot e SHA-256 vinculam o conteúdo ao catálogo CFOP, à revisão aprovada e ao XML original; perda de integridade bloqueia o registro. A mesma fila exclusiva de Administrador/Contabilidade exibe o histórico e o formulário sem defaults. Os 24 testes focados e a regressão conjunta de Compras, Fiscal e checklist visual com 342 testes passaram. Nenhum cálculo tributário, cadastro operacional, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: estruturar parâmetros fiscais por `nItem` vinculados a uma versão explícita do parecer, ainda sem defaults, cálculo ou emissão.
- Quadragésimo sétimo ciclo, parâmetros fiscais por item da devolução ao fornecedor concluídos estruturalmente em 09/09/2026: o contrato `supplier_return_item_tax_parameters_v1` e a migration fiscal 0040 criam versões append-only e idempotentes de uma ficha atômica que deve cobrir todos os `nItem` da preparação aprovada. O responsável escolhe conscientemente a versão do parecer e informa, sem defaults, origem e CST/CSOSN do ICMS, CST ou `NA` de IPI/PIS/COFINS, código cBenef GO ou `NA` e orientações para ICMS-ST/FCP, cBenef e IBS/CBS. Formatos e completude são validados antes de qualquer escrita; snapshot e SHA-256 vinculam a ficha ao parecer íntegro e ao XML original. A tela exclusiva de Administrador/Contabilidade mostra evidência da entrada sem copiá-la automaticamente. Os 29 testes focados e a regressão conjunta de Compras, Fiscal e checklist visual com 347 testes passaram. Nenhuma base, alíquota, valor calculado, alteração cadastral, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar memória de cálculo não emissiva por item, recebendo somente valores explicitamente informados e validando totais sem gerar XML.
- Quadragésimo oitavo ciclo, memória de cálculo não emissiva da devolução ao fornecedor concluída estruturalmente em 09/09/2026: o contrato `supplier_return_item_tax_calculation_memory_v1` e a migration fiscal 0041 criam versões append-only e idempotentes ligadas à versão exata da ficha por item. Administrador ou Contabilidade informa, sem defaults, o valor da operação e base, alíquota e valor de ICMS, ICMS-ST, FCP, IPI, PIS, COFINS, IBS e CBS para todos os `nItem`, inclusive zeros explícitos; tributos classificados como não aplicáveis recusam qualquer valor diferente de zero. O serviço valida formato, precisão, não negatividade, cobertura integral dos itens e integridade de ficha, parecer e XML antes de comparar o total da operação e cada total de base/valor com a soma dos itens. Divergência impede toda a gravação. A interface exibe histórico, critério informado, totais e hash somente na fila de Administrador/Contabilidade. Os 34 testes focados e a regressão conjunta de Compras, Fiscal e checklist visual com 352 testes passaram. O sistema não define fórmula tributária, não copia a entrada, não altera cadastro e não cria `DocumentoFiscal`, série, número, XML, estoque, rede ou transmissão; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar revisão segregada da memória completa, permitindo aprovação ou devolução para correção sem liberar XML ou emissão.
- Quadragésimo nono ciclo concluído estruturalmente em 09/09/2026: revisão da memória pelo contrato `supplier_return_item_tax_calculation_review_v1`, migration fiscal 0042. Outro Administrador/Contabilidade pode aprovar ou devolver a versão mais recente, com justificativa e decisão única imutável vinculada aos hashes da memória, parâmetros, parecer e XML. Autorrevisão e versões superadas são bloqueadas. Correções geram nova memória, preservando decisões anteriores. Os 38 testes focados passaram. Aprovação não libera XML, numeração, estoque ou transmissão. Próxima ação: estruturar transporte e composição do valor da devolução para posterior conferência contábil.

## Continuidade registrada em 24/08/2026

- Ciclo 53 concluído estruturalmente em 09/09/2026: revisão da composição comercial `supplier_return_commercial_review_v1`, migration fiscal 0045. Outro responsável fiscal aprova ou devolve somente a composição atual ligada à memória atual; decisão única imutável e hashes preservam a trilha. Aprovação exige orientação textual para ICMS/ST/FCP, IPI, PIS/COFINS, IBS/CBS e fundamentação. Devolução exige justificativa e permite nova composição sem apagar a decisão anterior. 51 testes de devolução/transporte aprovados. Não há incidência ou cálculo automático, XML, cobrança ou transmissão. Próxima etapa interna: rateio informado dos componentes por item, conferindo bases e totalizações. Aceite e orientação do contador com dados reais permanecem pendentes.

- Ciclo 52 concluído estruturalmente em 09/09/2026: composição comercial `supplier_return_commercial_composition_v1`, migration fiscal 0044. A ficha exige base igual ao valor da operação da memória aprovada mais recente, frete, seguro, despesas, desconto e total declarado, todos explícitos. Confere base + frete + seguro + despesas − desconto e exige confirmação de que os ajustes não estão embutidos no valor base. Versões imutáveis e idempotentes preservam responsável, memória e revisão por SHA-256; integridade do XML é revalidada. 47 testes de devolução/transporte aprovados. Não representa vNF, não define incidência tributária, não cria cobrança ou movimentação e não libera emissão. Próxima etapa: revisão contábil da composição e definição dos reflexos tributários antes de qualquer XML.

- Ciclo 51 concluído em 09/09/2026: ficha logística valida dígitos verificadores de CPF/CNPJ numéricos e identidade no transporte próprio (modalidades 3/4). Referências vêm do XML preservado, com remetente/destinatário invertidos na devolução; CNPJ compara raiz e CPF compara o documento completo. Ausência de documento respeita a exceção oficial. 44 testes aprovados. Sem migration, emissão ou transmissão. CNPJ alfanumérico e demais regras de transporte continuam pendentes. Próxima etapa: composição dos valores da devolução para revisão contábil.

- Ciclo 50 concluído estruturalmente em 09/09/2026: ficha logística `supplier_return_transport_v1`, migration fiscal 0043, ligada à memória aprovada mais recente. Modalidade explícita, dados opcionais do transportador, volumes e pesos validados, versões imutáveis e deduplicação por SHA-256. A gravação reconfere a integridade da revisão, memória e XML. 41 testes de devolução aprovados. Nenhuma emissão ou movimentação é realizada. Próxima ação: compor frete, seguro, desconto e despesas, com revisão contábil. Validação completa dos documentos do transportador e regras fiscais de transporte próprio permanecem pendentes antes de alimentar XML.

- A auditoria do checkout confirmou o núcleo fiscal, o adaptador de emissão e recebimento Focus NFe e o pacote SEFAZ direta GO implementados, com produção bloqueada por padrão.
- A trilha técnica inicial ativa passa a ser a homologação Focus NFe em sandbox, começando por uma única filial piloto e emissão manual. Esta escolha técnica não libera produção nem substitui a contratação e o aceite comercial do provedor.
- O banco local de desenvolvimento continua sem configuração fiscal por filial, credenciais Focus ou evidência de homologação real. A migration fiscal `0028_consultacadastrocontribuinte` foi aplicada localmente em 24/08/2026.
- A fila automática, a produção Focus e as redes da SEFAZ direta, DF-e direto, manifestação e CC-e devem permanecer desligadas até cada aceite documentado.
- O diagnóstico pré-homologação foi endurecido em 24/08/2026: pode exigir configuração operacional, informa apenas presença de credencial e travas, distingue sandbox de produção e bloqueia prontidão real quando token, endpoint e liberação de produção não coincidem. Oito testes direcionados passaram sem comunicação externa.
- O preflight por filial foi concluído em 24/08/2026 e consolida no terminal o mesmo checklist seguro da tela de homologação GO. A seleção de token Focus é validada pelo CNPJ da filial, impedindo que a credencial de outra loja produza falsa prontidão; uma filial marcada como produção também é recusada no roteiro de sandbox. Oito testes direcionados e a suíte fiscal completa com 195 testes passaram sem comunicação externa.
- O roteamento fiscal por filial foi concluído em 24/08/2026: somente o Master visualiza e altera o canal técnico entre Focus NFe, SEFAZ direta GO, compatibilidade do servidor ou emissão externa desativada. Emissão, consulta, cancelamento, inutilização, preflight e prontidão agregada respeitam a escolha; alterações geram auditoria. A opção direta é recusada fora de Goiás, e selecionar um canal não habilita rede nem produção. A suíte fiscal completa passou com 199 testes, sem comunicação externa.
- A resiliência do transporte SOAP direto foi concluída em 24/08/2026: consultas idempotentes possuem retentativa exponencial limitada, emissão e eventos mantêm uma única tentativa diante de resposta incerta, falhas consecutivas abrem circuito por host e a recuperação usa sonda controlada. A telemetria fica somente em memória e registra tipo de resultado, serviço, host e duração, sem XML, chave, CNPJ, certificado, credencial ou mensagem bruta. Dezesseis testes offline do adaptador direto e a suíte fiscal completa com 204 testes passaram sem comunicação externa.
- A contingência NF-e SVC-RS para Goiás foi concluída estruturalmente em 24/08/2026. O Master pode preparar uma NF-e modelo 55 do canal direto com justificativa; o ERP regenera chave e XML com `tpEmis=7`, `dhCont` e `xJust`, invalida assinatura anterior e roteia autorização, consulta, status e evento para o catálogo SVC-RS. A chave `SEFAZ_DIRETA_SVC_ENABLED` é independente e permanece desligada, produção continua bloqueada e operadores comuns não visualizam nem transmitem o fluxo. Testes offline confirmam o endpoint separado, o bloqueio seguro e o fluxo visual; a validação ampla de fiscal, marketplace e checklist passou com 314 testes. A homologação real continua dependente de CNPJ/IE/A1 válidos.
- A reconciliação da contingência NFC-e offline foi concluída estruturalmente em 24/08/2026. A fila mantém consulta antes de qualquer reenvio, exige duas confirmações consecutivas de documento não localizado, reinicia a sequência após timeout, preserva `tpEmis=9` e a chave ao corrigir rejeições, bloqueia cancelamento apenas local e sinaliza prazo excedido sem descartar a nota. A migration fiscal `0030` persiste o contador de confirmações. A validação ampla de fiscal e configurações passou com 276 testes. A homologação real da emissão offline e da regularização continua externa.
- O arquivo interno de evidências fiscais foi concluído estruturalmente em 24/08/2026 pela migration `0031`. Cada documento preserva, sem substituir versões anteriores, o XML entregue ao adaptador, o retorno normalizado, o XML autorizado, as consultas e os eventos de cancelamento/CC-e. Os registros são append-only, idempotentes por referência e encadeados por SHA-256; alterações/exclusões pela aplicação são bloqueadas e o Master visualiza somente o diagnóstico de integridade, sem conteúdo fiscal. A validação anterior passou com 280 testes. Após a implementação da âncora externa, a validação ampla de fiscal e configurações passou com 283 testes. A etapa seguinte acrescentou o comando estrito `verificar_integridade_evidencias_fiscais`, manifesto sanitizado `fiscal_evidence_anchor_v1`, promoção atômica, comparação com a âncora externa anterior, bloqueio de regressão/remoção da cauda, inclusão no backup com SHA-256 e conferência após restauração antes do serviço iniciar. Dois backups temporários consecutivos confirmaram a continuidade externa. O ciclo seguinte concluiu o alerta operacional sanitizado: backup, restauração e verificação manual podem registrar o resultado na auditoria sem XML, chave, CNPJ, certificado ou credencial; estados repetidos não duplicam o histórico e somente o Master visualiza a situação, a origem e o horário no Super Admin e na tela de Backup. Após esse alerta, a validação ampla de fiscal e configurações passou com 285 testes. Em 25/08/2026, a cópia secundária criptografada foi concluída estruturalmente: permanece desligada por padrão, exige confirmação explícita de NAS/rede/disco externo, recusa destino igual ou interno ao principal, copia somente `.zip.aes`, recalcula SHA-256, promove atomicamente e possui retenção independente. Uma execução completa com banco e destinos temporários confirmou hashes idênticos, ausência de ZIP aberto e limpeza dos arquivos parciais; a repetição após o endurecimento concorrente confirmou o mesmo resultado. A validação ampla de fiscal e configurações permaneceu aprovada com 285 testes. O ciclo seguinte concluiu o histórico operacional sanitizado: cada execução real gera identificação idempotente, registra sucesso ou falha, etapa, criptografia, destino secundário e confirmação do hash sem armazenar caminhos, nomes de rede, arquivos, senha ou conteúdo. Somente o Master vê as últimas execuções no Super Admin e em Backup; a última falha vira pendência alta, enquanto `-ValidarSomente` não polui o histórico. Uma simulação com banco temporário confirmou um sucesso e uma falha controlada na cópia secundária sem vazamento de caminho ou senha. A validação ampla de fiscal e configurações passou com 286 testes. O ciclo seguinte acrescentou o monitor sanitizado `backup_freshness_v1`: desligado por padrão com `LOCAL_BACKUP_MAX_AGE_HOURS=0`, ele usa a idade do último backup bem-sucedido, diferencia “Sem sucesso”, “Em dia” e “Atrasado” e gera pendência alta somente ao Master quando a política ativa é descumprida. Os testes focados cobriram os estados e a separação entre última execução e último sucesso; a validação ampla de fiscal e configurações passou com 287 testes. O ciclo seguinte unificou o painel, `verificar_pos_implantacao` e `gerar_evidencia_aceite` pela política `backup_age_policy_v1`: o ambiente é a fonte padrão, `0` bloqueia o aceite, o argumento opcional é identificado como substituição explícita e a checagem física do pacote continua sem expor caminhos. Sete testes focados confirmaram política ausente, ambiente ativo, substituição por argumento, aceite e manifesto; a suíte ampliada de fiscal, configurações, pós-instalação e aceite passou com 292 testes. O ciclo atual endureceu a checagem física pelo contrato `local_backup_package_validation_v1`: o pacote mais recente só libera o aceite depois de validar o arquivo SHA-256 correspondente, nome vinculado, ZIP integral e seguro, contrato `erp_local_backup_v2`, dump lógico, banco declarado e âncora fiscal. Pacotes AES-256 também são descriptografados e inspecionados localmente quando `BACKUP_ENCRYPTION_PASSPHRASE` está disponível; sem a senha, o checksum pode ser confirmado, mas o aceite permanece bloqueado sem expor segredo ou caminho. Sete testes focados cobrem pacote válido, adulteração, contrato incompatível, caminho inseguro e AES-256; a suíte ampliada de fiscal, configurações, pós-instalação e aceite passou com 296 testes. Em 28/08/2026, o restaurador ganhou o ensaio `local_restore_rehearsal_v1`: depois da validação completa, `-EnsaiarIsolado` copia o snapshot SQLite para uma área temporária, verifica `PRAGMA integrity_check` antes e depois, aplica migrations, executa o Django check e compara a cadeia fiscal com a âncora do pacote, sempre declarando que serviço e dados ativos não foram alterados e limpando a área ao final. Um ciclo real com banco temporário gerou somente `.zip.aes`, removeu o ZIP aberto e aprovou a restauração isolada sem expor caminho ou senha. O ciclo seguinte estendeu o mesmo contrato ao PostgreSQL: o operador precisa fornecer um banco já criado, vazio e nomeado com o prefixo `deigo_rehearsal_`, confirmar explicitamente o alvo e manter a senha somente no ambiente. O restaurador recusa o banco ativo/origem, confirma zero objetos antes de executar `pg_restore --single-transaction`, não usa `--clean`, aplica migrations, Django check e integridade fiscal e preserva o banco temporário para inspeção. Como `pg_restore` e um servidor PostgreSQL não estão disponíveis neste ambiente, as travas e a sintaxe foram validadas localmente, mas o restore real continua pendente para a máquina de homologação. Um pacote PostgreSQL sintético confirmou, sem conexão, os bloqueios por ausência de confirmação, nome fora do prefixo e host ausente. A regressão completa do caminho SQLite revelou que `Compress-Archive` omitia mídia declarada quando a pasta estava vazia; o backup agora cria entradas de diretório vazias no ZIP, e um novo ciclo AES-256 com mídia vazia aprovou restauração, migrations, âncora fiscal, ausência de alteração ativa e limpeza temporária. O ciclo seguinte endureceu a mídia de instalação limpa pelo contrato `detech_server_offline_package_validation_v2`: a Central só libera o pacote offline depois de exigir servidor, runtime Python, wheelhouse, PostgreSQL, WinSW, iniciador e apps desktop declarados uma única vez; conferir hashes e tamanhos; bloquear caminhos, links, duplicidades e arquivos extras; abrir o ZIP interno do servidor; validar que o wheelhouse contém pacotes `.whl`; e comparar os manifestos dos apps com os executáveis. Dez testes focados cobrem o pacote válido e adulterações, inclusive a falha antes silenciosa de wheelhouse ausente. O ciclo seguinte integrou o mesmo contrato ao empacotador: a mídia nasce em ZIP temporário, só é promovida após aprovação e preserva o artefato anterior em falha. Dois ensaios completos com componentes sintéticos confirmaram a promoção válida e o bloqueio sem resíduos quando o wheelhouse continha arquivo indevido. O ensaio também revelou e corrigiu duas dependências ocultas do build antigo: o hash agora usa SHA-256 nativo do .NET sem depender do perfil PowerShell, e a cópia intermediária não declarada do wheelhouse é removida antes da compactação final. ZIP e checksum são preparados antes da promoção, e qualquer exceção limpa os temporários. O ciclo seguinte criou `publish_detech_server_offline.ps1`: ele exige o checksum vinculado da origem, revalida origem e cópia temporária, promove ZIP e sidecar com cópias de rollback e remove todos os resíduos. Três ensaios reais confirmaram publicação válida, recusa de origem adulterada e preservação byte a byte do pacote anterior durante substituição forçada inválida. O ciclo seguinte adicionou `detech_server_offline_publication_validation_v1` à Central: o download offline agora exige `.zip.sha256` presente, hash correspondente e nome final vinculado, sem expor caminhos. Três testes novos cobrem publicação íntegra, sidecar ausente e hash/nome divergentes. A interface Master separa o estado do instalador offline do pacote técnico, evitando que a indisponibilidade de um esconda o outro. A suíte completa de fiscal e configurações permaneceu aprovada com 351 testes. O ciclo seguinte integrou a publicação offline à prontidão e ao aceite pelo contrato `local_installation_media_policy_v1`: cada implantação de servidor local é registrada como **com rede** ou **offline**. Com rede, a mídia pendente permanece recomendação; offline, ZIP e SHA-256 íntegros tornam-se obrigatórios e bloqueiam prontidão, dossiê e aceite. O Master ganhou ações separadas para gerar os dois tipos de evidência, e a política escolhida fica registrada na auditoria sem expor caminhos ou segredos. Sete testes novos cobrem mídia opcional, bloqueio offline, liberação íntegra, validação do dossiê e escolha na interface. A suíte completa de fiscal e configurações permaneceu aprovada com 358 testes. A homologação sob a conta `SYSTEM` em NAS ou disco externo real e a política legal de retenção continuam dependentes da infraestrutura definitiva.
- Próximo marco externo: quando existirem dados reais, registrar software/responsável EFD, validar uma amostra real com o contador e arquivar a referência do aceite. Até lá, continuar somente frentes internas que não dependam de inventar enquadramento tributário; Focus, SEFAZ direta e produção permanecem desligados.

## Frente prioritária — fechamento financeiro e gerencial pós-piloto

Esta frente registra as lacunas financeiras, contábeis e fiscais identificadas na auditoria sem recriar os módulos operacionais já existentes. PDV, caixa, contas a pagar e receber, contas de movimento, transferências, livro financeiro, plano de contas, centros de custo, conciliação, recebíveis eletrônicos, compras, estoque, pacote do contador e núcleo fiscal permanecem como base. Os itens abaixo tratam somente de evolução, reconciliação, proteção e homologação ainda não comprovadas.

### DRE 2.0 e CMV

- [ ] Evoluir a DRE gerencial para separar explicitamente receita bruta, cancelamentos, devoluções, descontos, receita líquida, CMV, lucro bruto, despesas operacionais, perdas, taxas financeiras, resultado operacional, resultado antes dos tributos e resultado líquido.
- [ ] Formalizar o cálculo de CMV por período com base no custo congelado no momento da venda e reconciliação com o fechamento contábil de estoque.
- [ ] Validar devoluções, cancelamentos, perdas e ajustes para que não distorçam CMV, receita líquida ou margem.
- [ ] Garantir que taxas de cartão, PIX, antecipações, chargebacks e divergências de adquirentes tenham classificação financeira/contábil coerente e impacto correto na DRE.
- [ ] Criar testes de reconciliação entre vendas, CMV, estoque final, perdas e resultado gerencial.

Critério de aceite:

A DRE de um período deve ser reproduzível, conciliável com vendas, estoque e financeiro, e explicável por conta contábil e centro de custo.

### Fechamento mensal financeiro-contábil

- [ ] Definir um fechamento mensal formal por empresa/filial, com data de corte e responsável.
- [ ] Exigir conciliação bancária, recebíveis eletrônicos, contas a pagar/receber e inventário contábil em estado aceitável antes do fechamento.
- [ ] Criar snapshot ou referência imutável dos saldos, DRE, CMV, inventário valorizado e documentos fiscais do período.
- [ ] Bloquear alterações retroativas que afetem período fechado ou exigir fluxo formal de reabertura/ajuste auditado.
- [ ] Registrar divergências pendentes no fechamento em vez de ocultá-las.
- [ ] Integrar o fechamento mensal ao pacote do contador v2.

Critério de aceite:

Um mês fechado deve poder ser reprocessado para conferência sem alterar seus totais históricos, salvo mediante reabertura ou ajuste auditado.

### Concorrência e integridade da numeração fiscal

- [ ] Auditar a reserva de numeração de NF-e/NFC-e sob concorrência real com vários PDVs simultâneos.
- [ ] Garantir lock transacional ou estratégia equivalente na combinação filial + modelo + série + ambiente.
- [ ] Criar testes concorrentes para impedir número duplicado, salto indevido por retry e dupla emissão da mesma venda.
- [ ] Validar idempotência ponta a ponta entre venda, DocumentoFiscal, fila, retransmissão e consulta SEFAZ.

Critério de aceite:

Nenhum cenário de concorrência, retry ou falha de rede pode gerar dois documentos para a mesma operação nem reutilizar a mesma numeração fiscal.

### Proteção de CSC e segredos fiscais

- [x] Revisar o armazenamento de CSC e confirmar proteção criptografada em repouso no mesmo nível de criticidade do certificado A1 e sua senha.
- [x] Impedir exposição de CSC em logs, admin, formulários, serializações, traces, exportações e pacotes de diagnóstico.
- [x] Definir fluxo auditado de inclusão, rotação e revogação do CSC.
- [x] Criar testes específicos de não exposição de segredo.

Critério de aceite:

CSC, senha e material privado do certificado não podem ser recuperados em texto claro por interfaces comuns, logs ou exportações.

### Vinculação fiscal dos pagamentos eletrônicos na NFC-e GO

Esta é uma frente complementar obrigatória antes da homologação real da NFC-e e não altera a sequência da trilha fiscal interna atual. A implementação deverá seguir o XSD e as regras vigentes confirmadas para Goiás, sem copiar literalmente exemplos externos nem presumir que cartão e PIX usam exatamente os mesmos campos condicionais.

- [x] Capturar no PDV o estado confirmado, identificador externo, NSU e código de autorização do TEF/PIX e impedir a finalização de transação eletrônica incompleta.
- [x] Mapear as formas operacionais para `tPag` 03 (crédito), 04 (débito) e 17 (PIX), preservando o valor de cada parcela em `vPag`.
- [x] Estruturar no cadastro/retorno do adaptador os dados fiscais ainda ausentes, incluindo tipo de integração, CNPJ da credenciadora ou instituição, bandeira quando aplicável, CNPJ do beneficiário e identificador do terminal, sem valores padrão.
- [x] Serializar no XML da NFC-e GO o grupo condicional `card`, incluindo `tpIntegra`, `CNPJ`, `tBand`, `cAut`, `CNPJReceb` e `idTermPag` quando aplicáveis à parcela; a validação XSD operacional permanece pendente da promoção controlada do pacote oficial.
- [x] Internamente, alimentar `cAut` só com autorização da confirmação autenticada no servidor; NSU, identificador externo, E2E, simulador e texto digitado não a substituem. Driver real ainda pendente.
- [x] Internamente, serializar PIX sem bandeira inventada e confrontar com o XSD 010f arquivado. Revisão de regra/schema vigente e homologação reais continuam externas.
- [x] Impedir `tpIntegra=1` sem confirmação confiável no servidor e bloquear preparo/envio com dados obrigatórios ausentes ou contraditórios. `tpIntegra=2` não é proibido por presunção e também tem paridade verificada.
- [x] Fechar a paridade estrutural offline separadamente no conversor Focus e no XML transportado pela SEFAZ direta, sem perder ou reconstruir campos.
- [x] Testar offline cartão, PIX, pagamento dividido, XSD arquivado e rejeições controladas.
- [ ] Homologar com driver/provedor TEF/PIX, equipamento e retorno reais; validar Focus se mantido como canal e SEFAZ-GO, antes de qualquer produção.

Critério de aceite:

Cada parcela eletrônica da NFC-e deve manter vínculo auditável entre a confirmação do TEF/PIX, os dados persistidos e o grupo fiscal efetivamente transmitido. A aprovação exige validação XSD, paridade dos dois canais e evidência de homologação real; simulador não libera produção.

### Homologação real SEFAZ GO

- [ ] Revalidar endpoints, schemas e Notas Técnicas vigentes antes do primeiro teste externo.
- [ ] Configurar filial piloto com CNPJ/IE, certificado A1, séries e credenciamento válidos por canal seguro; CSC somente se houver compatibilidade explícita com QR Code v2.
- [ ] Executar em homologação: autorização, consulta, rejeições controladas, cancelamento, inutilização, status do serviço e contingência NFC-e.
- [ ] Testar recuperação após timeout ou queda de rede sem duplicidade.
- [ ] Validar DF-e, manifestação e eventos com credenciais reais de homologação quando aplicável.
- [ ] Arquivar evidências técnicas e obter aceite fiscal/contábil antes de qualquer liberação de produção.
- [ ] Manter `SEFAZ_DIRETA_NETWORK_ENABLED` e `SEFAZ_DIRETA_ALLOW_PRODUCTION` sob liberação explícita e independente.

Critério de aceite:

Nenhuma capacidade deve ser classificada como pronta para produção somente por testes offline; deve existir evidência de homologação real da filial piloto.

### IBS/CBS e evolução tributária

- [ ] Manter IBS/CBS como parcial enquanto cálculo, grupos XML, schemas vigentes e aceite fiscal não estiverem confirmados.
- [ ] Implementar regras por vigência e versão de leiaute sem hard-code no PDV.
- [ ] Exigir validação do contador para classificações tributárias e cenários que dependam de enquadramento.
- [ ] Criar regressão fiscal com cenários legado e transição antes de ativar emissão homologada.

Critério de aceite:

A ativação de IBS/CBS deve depender de configuração explícita, schema homologado e evidência de testes; nenhuma data isolada deve habilitar o recurso automaticamente.

### Dependências externas desta frente

- Credenciais reais/sandbox, A1, IE e credenciamento da filial piloto; CSC somente para compatibilidade explícita com QR Code v2.
- Arquivos reais anonimizados de adquirentes/bancos para homologação de conciliação.
- Aceite do contador sobre plano de contas, CMV, DRE, classificações, IBS/CBS e pacote contábil.
- Ambiente de homologação com banco e infraestrutura equivalentes ao piloto.

## Frente futura — UX 2.0 e usabilidade

A avaliação de interface registrada como referência identifica oportunidades de melhoria em navegação, hierarquia de informação, responsividade, acessibilidade e redução de carga cognitiva, sem necessidade de redesign completo. O plano detalhado está em [ROADMAP_UX_USABILIDADE.md](ROADMAP_UX_USABILIDADE.md).

A frente deve ser iniciada após a conclusão da trilha fiscal interna atual e da primeira etapa da DRE 2.0/CMV, salvo correção crítica de usabilidade que afete operação ou segurança. O PDV atual deve ser preservado como referência de operação orientada a teclado; mudanças futuras devem priorizar redução de erro, tempo operacional e clareza.

- [ ] Iniciar UX 2.0 conforme o roadmap próprio após os marcos técnicos anteriores.

## Disciplina de atualização

- Toda frente iniciada deve ser marcada no checklist com data, estado atual, travas de segurança e próximo marco verificável.
- Uma entrega só muda para concluída quando código, migration, testes e documentação aplicáveis estiverem alinhados; dependências externas continuam como parciais até a evidência real.
- Ao encerrar cada ciclo, registrar aqui o que mudou, o que foi validado e qual dependência passa a ser a próxima ação.

## Sequencia aprovada

1. Piloto operacional: validar instalacao, PDV, impressao, caixa, estoque, backup e recuperacao em uma filial real.
2. Fiscal: concluir a matriz GO 2026, ampliar o motor tributario/XML e só depois escolher o canal piloto e configurar a homologacao.
3. Entrada fiscal: o XML só se vincula automaticamente a pedido único com produtos, quantidades e totais idênticos; divergências não vinculam pedido nem movimentam estoque ou financeiro. O vínculo manual autorizado, a conferência física guiada e a política por empresa já estão disponíveis: por padrão, uma divergência impede a finalização até que a conferência física seja registrada. A caixa de entrada de DF-e já permite importar e armazenar XMLs recebidos, isolados por empresa. O responsável pode encaminhar manualmente um XML para uma entrada de compra em rascunho, com vínculo e auditoria; também pode desconsiderar documento não aplicável mediante motivo auditado. Essas ações não movimentam estoque nem financeiro e a finalização continua exigindo revisão. O núcleo da consulta por CNPJ/NSU está preparado com cursor independente por filial, lote atômico, deduplicação, auditoria, botão protegido e comando agendável. O adaptador real de recebimento pela Focus NFe já está implementado em homologação, com autenticação segura, versão por CNPJ, consulta opcional do XML completo e bloqueio de produção. Falta configurar credenciais válidas, executar os cenários com a conta sandbox e registrar o aceite antes de produção.
4. Conciliação: o núcleo usa o contrato versionado `financial_statement_adapter_v1`, oferece CSV genérico e OFX nativos e aceita adapters privados registrados no servidor. Cada importação preserva layout, contrato, SHA-256, deduplicação, auditoria e fila paginada. A agenda calcula prazo, taxa, bruto, líquido previsto e atrasos; o matching prioriza NSU, transação ou autorização e classifica liquidação, antecipação, divergência e chargeback. Depósitos agrupados podem ser rateados manualmente com saldo parcial e proteção contra dupla conciliação. A próxima evolução depende de arquivos reais anonimizados para homologar adapters proprietários e automatizar sugestões de lotes.
5. Estoque e preco: inventario orientado a risco, validade, perdas classificadas, simulacao de margem e regras de preco/publicacao. Lotes recebidos por XML ja preservam fabricacao e validade; as vendas consomem FEFO sem selecionar lotes vencidos e produtos configurados para exigir lote bloqueiam a baixa quando nao houver saldo rastreado valido. Perdas e ajustes seguem sendo os fluxos auditados para tratar mercadoria vencida. O reajuste em massa agora simula custo e margem nova, rejeita preco zerado ou negativo e bloqueia produtos abaixo da margem desejada; a excecao exige autorizacao explicita de supervisor ou administrador e gera auditoria. O preco normal possui agenda versionada, vigencia automatica, cancelamento sem apagar historico e auditoria; promocoes validas continuam tendo prioridade no PDV. O inventario orientado a risco agora prioriza produtos por saldo minimo, lotes vencidos ou proximos, perdas recentes, ausencia de contagem e divergencias anteriores. A fila e filtrada por filial, gera um plano com itens pendentes e nao permite aplicar ajustes antes de todas as contagens fisicas, mantendo autorizacao e auditoria. A sugestão de reposição também pode gerar uma cotação em rascunho pelo contrato `replenishment_quote_draft_v1`, sempre para uma única filial, com seleção humana, recálculo no servidor, idempotência e sem envio ou impacto operacional.
6. Contabilidade: entregar primeiro o pacote do contador v2; depois do aceite, decidir com o escritorio se partidas dobradas, EFD, ECD e ECF pertencem ao ERP ou ao sistema integrado.
7. BI e IA: construir sobre metricas conciliadas e permissoes, inicialmente apenas leitura.

## Melhorias operacionais concluídas em 18/08/2026

- Select2 remoto abre com os primeiros registros e pagina em lotes de 20, sem exigir que o usuário memorize três letras; a pesquisa continua disponível para localizar rapidamente bases grandes.
- A gestão de caixas separa o escopo do operador e da supervisão: operador vê e movimenta somente o próprio caixa; supervisor e administrador filtram por filial, operador e situação, abrem o caixa escolhido e imprimem a conferência individual.
- O detalhe do caixa pagina vendas e movimentos manuais separadamente em lotes de 25, preservando os totais da conferência sobre todo o movimento.
- A revisão de codificação removeu textos quebrados das telas financeiras e manteve UTF-8 nas exportações e interfaces.
## Decisoes pendentes do cliente

- Decisão registrada no ciclo 144: o primeiro piloto GO terá SEFAZ direta como alvo técnico; Focus NFe permanece opção comercial secundária.
- Validar certificado A1, IE, series e regras tributarias com o contador; CSC somente para compatibilidade explícita com QR Code v2.
- Definir adquirentes/TEF, bancos e layouts de conciliacao utilizados pela loja.
- Escolher a filial piloto e responsaveis por operacao, fiscal e contabilidade.

## Limites de responsabilidade

Classificacao tributaria, CFOP, CST/CSOSN, IBS/CBS, plano de contas, regras de contabilizacao e obrigacoes oficiais precisam de aprovacao do contador responsavel. O sistema deve oferecer configuracao, validacao, evidencias e bloqueios, sem inventar tributacao.
## Evolução DF-e concluída em 18/08/2026

- Criado o contrato versionado fiscal_dfe_distribution_v1 para desacoplar o ERP do provedor fiscal.
- O cursor de distribuição passou a ser controlado por filial/CNPJ, evitando mistura de NSU entre matriz e filiais.
- A caixa de entrada mostra prontidão do adaptador, último NSU, maior NSU, retorno e consulta manual por filial.
- Lotes são validados integralmente antes de gravar documentos ou avançar o cursor.
- Documentos permanecem isolados por empresa, deduplicados por chave e sem movimentar estoque ou financeiro.
- O comando consultar_dfe_recebidos permite agendamento com usuário técnico e modo estrito.
- Contrato e implantação estão documentados em docs/CONTRATO_DISTRIBUICAO_DFE.md.
- O adaptador Focus NFe foi implementado com HTTP Basic, seleção de token por CNPJ, homologação padrão, TLS obrigatório e bloqueio explícito de produção.
- A paginação por `versao` usa `X-Max-Version`, mas o cursor só avança até o último item efetivamente processado, evitando perda quando o lote é limitado.
- A busca do XML completo não manifesta a NF-e; quando indisponível, o resumo permanece pendente e nenhuma operação é criada.
- Dependência externa restante: configurar/rotacionar as credenciais sandbox, executar a homologação real e registrar o aceite fiscal por filial.

## Evolução da emissão Focus NFe concluída em 20/08/2026

- O adaptador `FocusNFeSefazAdapter` cobre emissão de NFC-e/NF-e, consulta, cancelamento e inutilização pelo contrato fiscal do ERP.
- O payload preserva ICMS, PIS, COFINS, IPI, pagamentos, destinatário e os dados operacionais já validados pelo XML local.
- A referência por documento é estável para evitar duplicidade em repetição ou recuperação de falha.
- Autorizações gravam a chave, o protocolo e o XML processado devolvidos pela Focus; o ERP não mantém como definitivo um XML local diferente do autorizado.
- Respostas pendentes seguem para consulta antes de qualquer retransmissão, e documento não localizado volta ao fluxo controlado da fila.
- O endpoint de produção continua bloqueado por configuração explícita; nenhum teste desta etapa enviou documento real.
- Testes automatizados cobrem autenticação, seleção de token por CNPJ, IPI, retorno autorizado, processamento, consulta 404, host oficial, bloqueio de produção e fila real de homologação.
- Em 24/08/2026, a prontidão Focus passou a validar localmente presença de token, ambiente e liberação de produção sem expor segredo ou testar a credencial na rede; sandbox pronto não é mais confundido com produção liberada.
- Pendência externa: configurar token sandbox, emitir os cenários reais por filial, validar NF-e com endereço estruturado, reunir evidências e obter aceite fiscal/contábil antes de habilitar produção.
## Estrutura da SEFAZ direta GO concluída em 20/08/2026

- Criado o adaptador SOAP direto para autorização, consulta, cancelamento e inutilização de NF-e/NFC-e 4.00 em Goiás.
- O A1 local atende assinatura XML e autenticação mútua TLS; segredos continuam fora do repositório.
- Rede e produção possuem travas independentes e permanecem desligadas por padrão.
- Hosts externos ao catálogo oficial de Goiás são recusados.
- Testes offline cobrem SOAP, autorização, consulta, eventos, inutilização, assinatura real com A1 temporário e bloqueios de segurança.
- Nenhum documento foi transmitido nesta etapa.
- Pendência externa: revalidar endpoints e schemas vigentes, credenciar a filial, executar a homologação real e obter aceite fiscal/contábil. Até lá, Focus NFe e SEFAZ direta continuam opções técnicas sem produção liberada.
## Monitor fiscal oficial concluído em 20/08/2026

- O contrato `fiscal_update_monitor_v1` acompanha notas técnicas, schemas e publicações fiscais oficiais sem executar alterações automáticas.
- A primeira consulta registra uma linha de base; novidades posteriores são deduplicadas e encaminhadas para revisão administrativa auditada.
- HTTPS, hosts oficiais, timeout, limite de resposta e cache condicional reduzem risco operacional.
- O comando de gerenciamento e o agendamento diário no Windows estão preparados, mas o recurso permanece desabilitado por padrão.
- Schemas, cálculos e endpoints continuam exigindo implementação separada, testes em homologação e aceite fiscal/contábil.
- A arquitetura permite extrair o monitor como serviço/API futuramente sem acoplar certificados ou dados operacionais dos clientes.
## Pacote isolável do Deigo Fiscal iniciado em 20/08/2026

- O núcleo SEFAZ direto foi movido para `apps/fiscal/sefaz_direta/`, preservando uma fachada no caminho antigo.
- O contrato `deigo_fiscal_capabilities_v1` registra capacidades implementadas, parciais, planejadas e dependências externas.
- A consulta de status do autorizador foi acrescentada ao adaptador e coberta por teste SOAP offline.
- A matriz Focus x Deigo Fiscal está documentada sem declarar paridade antes da homologação.
- A distribuição DF-e direta por NSU foi implementada com notas, resumos, eventos, cursor por filial e cooldown. A manifestação do destinatário, a CC-e e a consulta cadastral do contribuinte em Goiás também foram concluídas estruturalmente. Próxima sequência de produto após a homologação ativa: contingência NF-e e catálogo multi-UF.
## Distribuição DF-e direta concluída estruturalmente em 20/08/2026

- O pacote isolado consulta o serviço oficial `NFeDistribuicaoDFe` por `distNSU`, usando o A1 da filial.
- NF-e, resumos e eventos fiscais são validados e persistidos antes do avanço do cursor.
- Eventos possuem armazenamento e download próprios; não são tratados como entrada de mercadoria.
- O intervalo solicitado pela SEFAZ fica salvo por filial e bloqueia repetição antecipada da consulta.
- Rede e produção permanecem desligadas por padrão e nenhum web service real foi chamado nesta etapa.
- Pendência externa: validar A1/CNPJ no Ambiente Nacional, executar homologação real e obter aceite técnico e fiscal.
## Manifestação do Destinatário concluída estruturalmente em 20/08/2026

- Implementados os eventos 210200 (confirmação), 210210 (ciência), 210220 (desconhecimento) e 210240 (operação não realizada).
- Operação não realizada exige justificativa de 15 a 255 caracteres; os demais eventos recusam justificativa indevida.
- Ciência pode anteceder uma manifestação conclusiva, mas manifestações conclusivas conflitantes ou simultâneas ficam bloqueadas por transação.
- A regra preventiva considera 90 dias para manifestação conclusiva, conforme atualização oficial vigente desde 01/06/2026; a data efetiva de autorização deve ser confirmada na homologação.
- Histórico, cStat, protocolo, XML de envio/retorno, usuário e auditoria ficam preservados e isolados por empresa.
- O adaptador SOAP usa o Ambiente Nacional, certificado A1 e configurações independentes para rede e produção; ambas permanecem desligadas por padrão.
- Nenhum evento real foi enviado. Pendência externa: testar com certificado/CNPJ válidos em homologação e obter aceite fiscal antes de produção.
## Carta de Correção Eletrônica concluída estruturalmente em 20/08/2026

- Implementado o contrato `fiscal_cce_v1` e o evento oficial `110110` para NF-e modelo 55 autorizada.
- O serviço controla concorrência, sequências de 1 a 20, texto de 15 a 1.000 caracteres, prazo preventivo de 720 horas, histórico, XML, protocolo, auditoria e isolamento por empresa.
- A tela exige confirmação explícita dos limites legais e informa que a CC-e mais recente substitui as anteriores; alterações de imposto, preço, quantidade, remetente, destinatário e datas fiscais permanecem proibidas.
- Rede e produção ficam bloqueadas por configuração independente. Nenhum evento real foi enviado.
- Pendência externa: testar assinatura A1 e retorno do `NFeRecepcaoEvento4` em homologação de Goiás e obter aceite fiscal antes de produção.

## Consulta cadastral do contribuinte concluída estruturalmente em 20/08/2026

- Implementado o serviço `ConsCad` 2.00 para Goiás com CNPJ, CPF ou IE, histórico, XML de envio/retorno, auditoria e isolamento por empresa.
- Rede e produção possuem bloqueios independentes e permanecem desligadas por padrão.
- A migration `fiscal.0028_consultacadastrocontribuinte` materializa o histórico no banco e deve estar aplicada em cada ambiente antes do uso.
- Em 24/08/2026 foram acrescentados sete testes offline para montagem e interpretação do SOAP, validação de contrato, bloqueios independentes de rede e produção, persistência, falha auditada e ausência de adaptador; todos passaram sem comunicação externa.
- Nenhuma consulta real foi enviada. Pendência externa: revalidar endpoint e retorno vigente, testar com A1/IE válidos em homologação e obter aceite fiscal.
