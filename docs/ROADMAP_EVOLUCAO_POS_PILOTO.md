# Roadmap de evolucao pos-piloto

Atualizado em 20/08/2026 a partir das notas técnicas de evolução contábil, integração SEFAZ e comparativo iSOLIDUS.

## Principio de produto

O DeTecServer nao deve copiar telas, nomes ou componentes proprietarios de outros ERPs. A evolucao busca resultados operacionais mensuraveis: menos digitacao, menor divergencia, estoque confiavel, margem protegida, fechamento mais rapido e operacao resiliente.

## Estado atual

O ERP ja possui uma base operacional, financeira gerencial, fiscal preparada por adaptador, auditoria, empresas/filiais, PDV e sincronizacao. O livro financeiro e o pacote contabil sao gerenciais e de integracao; eles nao substituem razao contabil por partidas dobradas, ECD, ECF, EFD ou a responsabilidade do contador.

## Sequencia aprovada

1. Piloto operacional: validar instalacao, PDV, impressao, caixa, estoque, backup e recuperacao em uma filial real.
2. Fiscal: escolher provedor ou adaptador direto, configurar credenciais fora do repositorio e emitir somente em homologacao ate o aceite tecnico e contabil.
3. Entrada fiscal: o XML só se vincula automaticamente a pedido único com produtos, quantidades e totais idênticos; divergências não vinculam pedido nem movimentam estoque ou financeiro. O vínculo manual autorizado, a conferência física guiada e a política por empresa já estão disponíveis: por padrão, uma divergência impede a finalização até que a conferência física seja registrada. A caixa de entrada de DF-e já permite importar e armazenar XMLs recebidos, isolados por empresa. O responsável pode encaminhar manualmente um XML para uma entrada de compra em rascunho, com vínculo e auditoria; também pode desconsiderar documento não aplicável mediante motivo auditado. Essas ações não movimentam estoque nem financeiro e a finalização continua exigindo revisão. O núcleo da consulta por CNPJ/NSU está preparado com cursor independente por filial, lote atômico, deduplicação, auditoria, botão protegido e comando agendável. O adaptador real de recebimento pela Focus NFe já está implementado em homologação, com autenticação segura, versão por CNPJ, consulta opcional do XML completo e bloqueio de produção. Falta configurar credenciais válidas, executar os cenários com a conta sandbox e registrar o aceite antes de produção.
4. Conciliação: o núcleo usa o contrato versionado `financial_statement_adapter_v1`, oferece CSV genérico e OFX nativos e aceita adapters privados registrados no servidor. Cada importação preserva layout, contrato, SHA-256, deduplicação, auditoria e fila paginada. A agenda calcula prazo, taxa, bruto, líquido previsto e atrasos; o matching prioriza NSU, transação ou autorização e classifica liquidação, antecipação, divergência e chargeback. Depósitos agrupados podem ser rateados manualmente com saldo parcial e proteção contra dupla conciliação. A próxima evolução depende de arquivos reais anonimizados para homologar adapters proprietários e automatizar sugestões de lotes.
5. Estoque e preco: inventario orientado a risco, validade, perdas classificadas, simulacao de margem e regras de preco/publicacao. Lotes recebidos por XML ja preservam fabricacao e validade; as vendas consomem FEFO sem selecionar lotes vencidos e produtos configurados para exigir lote bloqueiam a baixa quando nao houver saldo rastreado valido. Perdas e ajustes seguem sendo os fluxos auditados para tratar mercadoria vencida. O reajuste em massa agora simula custo e margem nova, rejeita preco zerado ou negativo e bloqueia produtos abaixo da margem desejada; a excecao exige autorizacao explicita de supervisor ou administrador e gera auditoria. O preco normal possui agenda versionada, vigencia automatica, cancelamento sem apagar historico e auditoria; promocoes validas continuam tendo prioridade no PDV. O inventario orientado a risco agora prioriza produtos por saldo minimo, lotes vencidos ou proximos, perdas recentes, ausencia de contagem e divergencias anteriores. A fila e filtrada por filial, gera um plano com itens pendentes e nao permite aplicar ajustes antes de todas as contagens fisicas, mantendo autorizacao e auditoria.
6. Contabilidade formal: somente depois da validacao com escritorio/contador, implementar eventos contabilizaveis, regras versionadas, partidas dobradas e fechamento por competencia.
7. BI e IA: construir sobre metricas conciliadas e permissoes, inicialmente apenas leitura.

## Melhorias operacionais concluídas em 18/08/2026

- Select2 remoto abre com os primeiros registros e pagina em lotes de 20, sem exigir que o usuário memorize três letras; a pesquisa continua disponível para localizar rapidamente bases grandes.
- A gestão de caixas separa o escopo do operador e da supervisão: operador vê e movimenta somente o próprio caixa; supervisor e administrador filtram por filial, operador e situação, abrem o caixa escolhido e imprimem a conferência individual.
- O detalhe do caixa pagina vendas e movimentos manuais separadamente em lotes de 25, preservando os totais da conferência sobre todo o movimento.
- A revisão de codificação removeu textos quebrados das telas financeiras e manteve UTF-8 nas exportações e interfaces.
## Decisoes pendentes do cliente

- Confirmar provedor fiscal inicial e disponibilizar credenciais de sandbox.
- Validar certificado A1, CSC, IE, series e regras tributarias com o contador.
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
- A distribuição DF-e direta por NSU foi implementada com notas, resumos, eventos, cursor por filial e cooldown. A manifestação do destinatário e a CC-e também foram concluídas estruturalmente. Próxima sequência: consulta cadastral do contribuinte, contingência NF-e e catálogo multi-UF.
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