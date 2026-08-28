# Roadmap de evolucao pos-piloto

Atualizado em 28/08/2026 a partir das notas técnicas de evolução contábil, integração SEFAZ, comparativo iSOLIDUS e auditoria do estado executável do repositório.

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
## Continuidade registrada em 24/08/2026

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
- Próximo marco: versionar NCM, CEST e CFOP e iniciar o pacote do contador v2, preservando bloqueios para cenários tributários ainda não homologados.

## Disciplina de atualização

- Toda frente iniciada deve ser marcada no checklist com data, estado atual, travas de segurança e próximo marco verificável.
- Uma entrega só muda para concluída quando código, migration, testes e documentação aplicáveis estiverem alinhados; dependências externas continuam como parciais até a evidência real.
- Ao encerrar cada ciclo, registrar aqui o que mudou, o que foi validado e qual dependência passa a ser a próxima ação.

## Sequencia aprovada

1. Piloto operacional: validar instalacao, PDV, impressao, caixa, estoque, backup e recuperacao em uma filial real.
2. Fiscal: concluir a matriz GO 2026, ampliar o motor tributario/XML e só depois escolher o canal piloto e configurar a homologacao.
3. Entrada fiscal: o XML só se vincula automaticamente a pedido único com produtos, quantidades e totais idênticos; divergências não vinculam pedido nem movimentam estoque ou financeiro. O vínculo manual autorizado, a conferência física guiada e a política por empresa já estão disponíveis: por padrão, uma divergência impede a finalização até que a conferência física seja registrada. A caixa de entrada de DF-e já permite importar e armazenar XMLs recebidos, isolados por empresa. O responsável pode encaminhar manualmente um XML para uma entrada de compra em rascunho, com vínculo e auditoria; também pode desconsiderar documento não aplicável mediante motivo auditado. Essas ações não movimentam estoque nem financeiro e a finalização continua exigindo revisão. O núcleo da consulta por CNPJ/NSU está preparado com cursor independente por filial, lote atômico, deduplicação, auditoria, botão protegido e comando agendável. O adaptador real de recebimento pela Focus NFe já está implementado em homologação, com autenticação segura, versão por CNPJ, consulta opcional do XML completo e bloqueio de produção. Falta configurar credenciais válidas, executar os cenários com a conta sandbox e registrar o aceite antes de produção.
4. Conciliação: o núcleo usa o contrato versionado `financial_statement_adapter_v1`, oferece CSV genérico e OFX nativos e aceita adapters privados registrados no servidor. Cada importação preserva layout, contrato, SHA-256, deduplicação, auditoria e fila paginada. A agenda calcula prazo, taxa, bruto, líquido previsto e atrasos; o matching prioriza NSU, transação ou autorização e classifica liquidação, antecipação, divergência e chargeback. Depósitos agrupados podem ser rateados manualmente com saldo parcial e proteção contra dupla conciliação. A próxima evolução depende de arquivos reais anonimizados para homologar adapters proprietários e automatizar sugestões de lotes.
5. Estoque e preco: inventario orientado a risco, validade, perdas classificadas, simulacao de margem e regras de preco/publicacao. Lotes recebidos por XML ja preservam fabricacao e validade; as vendas consomem FEFO sem selecionar lotes vencidos e produtos configurados para exigir lote bloqueiam a baixa quando nao houver saldo rastreado valido. Perdas e ajustes seguem sendo os fluxos auditados para tratar mercadoria vencida. O reajuste em massa agora simula custo e margem nova, rejeita preco zerado ou negativo e bloqueia produtos abaixo da margem desejada; a excecao exige autorizacao explicita de supervisor ou administrador e gera auditoria. O preco normal possui agenda versionada, vigencia automatica, cancelamento sem apagar historico e auditoria; promocoes validas continuam tendo prioridade no PDV. O inventario orientado a risco agora prioriza produtos por saldo minimo, lotes vencidos ou proximos, perdas recentes, ausencia de contagem e divergencias anteriores. A fila e filtrada por filial, gera um plano com itens pendentes e nao permite aplicar ajustes antes de todas as contagens fisicas, mantendo autorizacao e auditoria.
6. Contabilidade: entregar primeiro o pacote do contador v2; depois do aceite, decidir com o escritorio se partidas dobradas, EFD, ECD e ECF pertencem ao ERP ou ao sistema integrado.
7. BI e IA: construir sobre metricas conciliadas e permissoes, inicialmente apenas leitura.

## Melhorias operacionais concluídas em 18/08/2026

- Select2 remoto abre com os primeiros registros e pagina em lotes de 20, sem exigir que o usuário memorize três letras; a pesquisa continua disponível para localizar rapidamente bases grandes.
- A gestão de caixas separa o escopo do operador e da supervisão: operador vê e movimenta somente o próprio caixa; supervisor e administrador filtram por filial, operador e situação, abrem o caixa escolhido e imprimem a conferência individual.
- O detalhe do caixa pagina vendas e movimentos manuais separadamente em lotes de 25, preservando os totais da conferência sobre todo o movimento.
- A revisão de codificação removeu textos quebrados das telas financeiras e manteve UTF-8 nas exportações e interfaces.
## Decisoes pendentes do cliente

- Confirmar a Focus NFe como provedor comercial inicial ou registrar outra decisão; para a trilha técnica atual, disponibilizar credenciais sandbox por canal seguro.
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
