# Matriz de conformidade fiscal e contábil — Goiás 2026

Ciclo 71 — 10/09/2026: identificação e partes da devolução foram estruturadas em contrato puro e integradas à extração/tela protegidas. O serviço identifica a origem de cada campo e lista ausências sem aplicar defaults. O cadastro do fornecedor ainda não possui IE/endereço fiscal estruturado; o snapshot original é preservado, mas não substitui validação atual. CNPJ alfanumérico, decisões de identificação, vigências, XML e homologação seguem bloqueados. A regressão conjunta passou com 95 testes.

Ciclo 70 — 10/09/2026: extração autenticada de chave+nItem implementada no serviço protegido e na prévia somente leitura. São conferidos escopo da empresa/filial, hash congelado, protocolo cStat 100, modelo 55, chave em cinco fontes, partes e snapshot do item. Divergências permanecem bloqueantes e 92 testes passaram. Isto não valida assinatura digital, tributação, vigência, XSD ou homologação.

Ciclo 68 — 10/09/2026: validador estrutural não emissivo do grupo DFeReferenciado por item implementado e testado. Cobertura inclui DV da chave, nItem, duplicidades, NFref simultâneo, modelo/operação/política e múltiplas origens fora do escopo inicial. Permanecem pendentes confronto autenticado do XML e das partes, NFA/CNPJ alfanumérico, vigência em Goiás, conteúdo tributário, totalização, contador e homologação.

## Retomada atual — ciclo 67, 10/09/2026

Confronto dos trechos oficiais de devolução registrado em [REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md](REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md). Corrigida a proposta de referência do cabeçalho para chave+nItem original em DFeReferenciado por item. A NT v1.51 indica 05/10/2026 na regra específica, mas tem divergência no histórico: confirmação operacional continua pendente. Documentados pagamento sem pagamento/valor zero e IPI devolvido separado; isso não decide enquadramento tributário nem acerto financeiro do fornecedor.

- [x] Confrontar referência, pagamento e estrutura de IPI devolvido com os trechos oficiais, registrando limites e divergências.
- [x] Implementar e testar validador puro de referências fiscais por item e integrar extração autenticada, sem XML ou emissão (ciclos 68 e 70).
- [ ] Completar análise tributária/RTC, tabelas e vigências; confirmar pacote e hipóteses com o contador antes do gerador/homologação.

Apenas documentação alterada neste ciclo; sem mudança de código executável, banco, configuração, cobrança ou transmissão. Registros abaixo são históricos, não o ponto atual de retomada.

Ciclo 66 — 10/09/2026: bloqueio de obtenção das fontes superado com sessão HTTP/cookies. ZIP oficial 010f e PDFs MOC Anexo I, NT 2025.002 v1.51 e NT 2026.007 v1.00 preservados em docs/evidencias/nfe_2026_09_10, com inventário e hashes no README da pasta. ZIP passou CRC e XSD raiz compilou em memória sem rede; identificação dos PDFs conferida. Não houve instalação, alteração fiscal, banco ou emissão. Leitura normativa integral e validação de vigências permanecem pendentes: próximo passo é confrontar regras de devolução com o contrato e os dados do sistema. Os bloqueios históricos de acesso descritos abaixo não representam mais falta dos arquivos; a aprovação do pacote continua pendente.

Ciclo 64 (09/09/2026): prévia protegida das referências fiscais disponível pela tela de revisão da devolução. Rota somente GET, restrita a Administrador/Contabilidade e à empresa do usuário, com cache desabilitado. Mostra grupos, referências, hashes, pendências e bloqueios, sem edição ou emissão. A etapa de extração do ciclo 63 foi salva no commit 7efa868 após restabelecimento da execução. Próximo passo: obter e analisar integralmente as fontes oficiais e schemas pendentes para fechar a matriz de capacidade fiscal; a prévia não substitui essa validação.

Ciclo 63: referências do envelope passam a ser extraídas por serviço autenticado com escopo de empresa, hashes e pendências do dossiê. Não há payload tributário completo, validação XSD ou liberação de emissão. A autenticidade aqui significa origem em registros autorizados do sistema e conferência de hashes, não assinatura fiscal ou aceite da SEFAZ. Próximo passo: prévia protegida na tela; fontes integrais e homologação seguem pendentes.

Ciclo 62: validador estrutural do envelope de referências implementado, ainda sem leitura autenticada do banco ou validação normativa. Mesmo referências sintaticamente válidas produzem bloqueio de conteúdo fiscal não implementado; modelo 65, campos desconhecidos e emissão habilitada são rejeitados. Não há XML, transmissão, persistência ou nova migração. Próximo passo: extração com autorização e integridade, mantendo os bloqueios fiscais.

Ciclo 61: contrato preliminar e matriz de campos documentados em [CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md](CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md). O gerador de venda e o payload Focus observado não demonstram suporte completo a devolução. Orientações oficiais GO sobre ST exigem hipóteses específicas; nenhuma política tributária foi aplicada. Leitura integral de MOC/NT e pacote XSD permanece pendente por erro de acesso, portanto não há certificação de conformidade. Emissão continua bloqueada.

Ciclo 60: painel somente leitura consolida pendências estruturais do dossiê e distingue origem histórica da memória revisada de dados superados. A consulta confere hashes e integridade da memória/XML, mas não substitui validações fiscais completas ou aprovação de dados reais. O bloqueio de XML e homologação é permanente nesta etapa; nenhum resultado do painel autoriza emissão. Próximo passo: especificar o contrato de dados do XML e os bloqueios por campo com base na documentação oficial vigente.

Ciclo 59: correções da memória revisada devolvida agora criam sucessoras rastreáveis com a mesma origem e bases aprovadas. A decisão anterior é preservada e cada sucessora exige revisão independente. Não há aplicação automática de impactos, cálculo legal dos impostos ou liberação de XML. Próxima etapa interna: consolidar o dossiê e suas pendências atuais; aceite contábil real e homologação continuam necessários.

Ciclo 58: reflexos aprovados podem fundamentar uma memória revisada, com vínculo único, hashes e conferência exata das bases finais. A memória anterior permanece intacta. Não há recálculo automático dos impostos ou certificação normativa. A nova memória segue a revisão independente existente. Correção após devolução dessa memória vinculada ainda requer implementação específica; não reutilizar o vínculo nem tratar impactos anteriores como novos ajustes. Emissão continua bloqueada.

Ciclo 57: a conferência independente dos reflexos foi implementada com decisão imutável de outro responsável, justificativa e validação de integridade/atualidade. Esta aprovação interna não representa validação normativa, cálculo dos impostos ou homologação. Ainda falta vincular os reflexos aprovados à memória tributária revisada e obter aceite com dados reais. A emissão continua bloqueada.

Ciclo 56: a limitação operacional do ciclo 55 foi superada: os reflexos declarados agora têm serviço protegido, histórico imutável e tela de revisão (migration 0047). A gravação valida escopo, rateio atual, aprovações, integridade da cadeia e somas, mantendo a memória original intacta. Ainda não há aprovação independente dos reflexos, recálculo de impostos, aceite contábil real ou homologação deste fluxo. Emissão permanece bloqueada.

Ciclo 55: existe um núcleo isolado para conferir aritmeticamente impactos declarados sobre bases por item/tributo. Ainda não há gravação, endpoint ou tela dessa etapa. A correspondência dos itens é conferida, mas a autenticação, atualidade e integridade da origem devem ser verificadas pelo futuro serviço. Não constitui validação normativa, cálculo de impostos ou evidência de homologação. Próxima entrega: serviço protegido e persistência dos reflexos vinculados ao rateio atual.

Atualizada em 09/09/2026. Documento interno de engenharia e homologação.

## Regra de conclusão

Comunicação com Focus ou SEFAZ não será tratada como conformidade enquanto cenários tributários, XMLs, evidências e pacote do contador não estiverem validados. Esta matriz não substitui o contador responsável nem a homologação por empresa, filial, regime, modelo e UF.

## Estado consolidado

| Frente | Estado | Condição para concluir |
|---|---|---|
| Operação de supermercado | Avançada | Homologação na filial piloto |
| Focus NFe | Estruturalmente integrada | Sandbox, cenários reais e aceite |
| SEFAZ direta GO | Estruturalmente avançada e desligada | A1/IE/CSC, homologação e aceite |
| Motor NF-e/NFC-e | Parcial | Cobrir operações e tributos |
| IBS/CBS 2026 | Bloqueado com segurança | Schema, cálculo, XML e vigência |
| Pacote do contador | v2 e validador prontos, pendente aceite real | Contrato externo, amostra real e aceite |
| Produção fiscal | Bloqueada | Todos os portões críticos aprovados |

## Fase 1 — definição fiscal da filial piloto

- [ ] Registrar regime tributário, CNAE, CRT e vigência.
- [ ] Confirmar CNPJ, IE, endereço fiscal e credenciamento.
- [ ] Confirmar NF-e 55 e/ou NFC-e 65.
- [ ] Confirmar certificado A1, CSC/ID CSC, séries e numeração.
- [ ] Inventariar venda, devolução, transferência, bonificação, remessa, entrega e entrada.
- [ ] Inventariar consumidor final, contribuinte, não contribuinte e operação interestadual.
- [ ] Validar ST, monofásico, benefício fiscal, desoneração e demais exceções.
- [ ] Definir a vigência de IBS/CBS aplicável ao regime.

## Fase 2 — motor tributário e XML

- [ ] Criar testes versionados para cada cenário da Fase 1.
- [ ] Ampliar ICMS/CSOSN, incluindo ST e retenções aplicáveis.
- [ ] Implementar operações interestaduais, DIFAL, devolução, frete e entrega aplicáveis.
- [ ] Validar PIS, COFINS, IPI, FCP e monofásicos.
- [x] Versionar cBenef GO com fonte, SHA-256, vigência, CST e importação/ativação controladas.
- [x] Versionar NCM com snapshot oficial Siscomex, SHA-256, ato, referência, vigência individual e importação/ativação controladas.
- [x] Versionar CEST pelo Convênio ICMS 142/18 consolidado, com snapshot, SHA-256, segmentos, revogações e relação objetiva com NCM.
- [x] Versionar CFOP pelo Ajuste SINIEF 07/01 consolidado e validar existência, direção, alcance e modelo documental.
- [ ] Implementar IBS/CBS conforme schema e nota técnica vigentes.
- [ ] Validar XML no schema oficial e registrar a versão.
- [ ] Comparar cálculos e XMLs com o contador.

## Fase 3 — pacote do contador v2

- [x] Usar emissão do XML como competência, exportar autorização quando disponível e explicitar fallback para documentos legados.
- [x] Incluir XMLs de saída, entrada e eventos, separados por origem e filial.
- [x] Exportar itens, CFOP, NCM, CEST, CST/CSOSN, cBenef, bases, alíquotas e tributos diretamente do XML armazenado.
- [x] Incluir cancelamento, CC-e, manifestação e situação/protocolo registrados, preservando os XMLs de evento.
- [x] Incluir inventário valorizado por custo médio ponderado móvel, com snapshot imutável por filial/data, SHA-256 e fallback temporal explícito para períodos sem fechamento.
- [x] Reconciliar vendas, recebimentos, livro financeiro, documentos fiscais, entradas, contas a pagar e estoque, em modo somente leitura e com divergências rastreáveis.
- [x] Estruturar contrato contábil versionado, imutável e auditado, com rascunho seguro, formatos suportados e responsável externo pela EFD ICMS/IPI.
- [x] Estruturar o validador local da amostra mensal e o registro imutável/auditado do aceite, sem transmissão externa.
- [ ] Registrar a definição real do software contábil e do responsável pela EFD ICMS/IPI, com referência do aceite.
- [ ] Validar uma amostra mensal real com o contador e registrar o aceite.

## Fase 4 — homologação dos canais

- [ ] Homologar Focus sandbox, se for o canal piloto.
- [ ] Homologar separadamente a SEFAZ direta GO, com produção bloqueada.
- [ ] Testar autorização, rejeição, duplicidade, consulta, cancelamento e inutilização.
- [ ] Testar NFC-e offline, regularização, SVC-RS e falhas de comunicação.
- [ ] Testar DF-e, manifestação, CC-e e consulta cadastral.
- [ ] Conferir XML, assinatura, protocolo, QR Code e evidências.
- [ ] Obter aceite por empresa, filial e canal.

## Portões para produção

- [ ] Cadastro fiscal aprovado pelo contador.
- [ ] Matriz de operações e produtos coberta por testes.
- [ ] IBS/CBS adequado à vigência e ao regime.
- [ ] Schemas, tabelas, certificado, CSC, séries e numeração validados.
- [ ] Contingência e recuperação homologadas.
- [ ] XMLs e eventos íntegros e restauráveis.
- [ ] Pacote do contador v2 aceito.
- [ ] Canal homologado sem liberar automaticamente o outro.
- [ ] Termo de aceite por filial arquivado.

## Ordem sem credenciais reais

- [x] Formalizar o perfil provisório go_dev_sem_credenciais_v1, sem regime inventado, rede ou produção.
- [x] Criar o catálogo fiscal_tax_scenarios_go_v1 com cenários parciais, bloqueados e dependências externas.
- [x] Proteger o contrato inicial com 7 testes e validar a regressão focada com 25 testes offline.
- [x] Conectar o validador à pré-emissão e ao gerador NFC-e de Goiás, sem afetar outras UFs.
- [x] Importar e ativar localmente o catálogo oficial consolidado cBenef GO com 282 códigos e validar código x CST; migration fiscal 0032, 6 testes focados e 233 testes fiscais aprovados.
- [x] Importar e ativar localmente o snapshot oficial NCM vigente em 28/08/2026, com 10.515 códigos finais, integridade SHA-256, migration fiscal 0033 e gate de prontidão.
- [x] Importar e ativar localmente o snapshot CEST CONFAZ de 31/08/2026, com 1.035 itens vigentes, 25 segmentos, migration fiscal 0034, validação CEST x NCM e gate de prontidão.
- [x] Importar e ativar localmente o snapshot CFOP CONFAZ de 31/08/2026, com 460 códigos utilizáveis, 68 agrupadores excluídos, migration fiscal 0035 e validação antes da numeração.
- [x] Manter a importação sem rede, exigir hash esperado e falhar com segurança quando não existir catálogo vigente.
- [x] Cobrir a venda interna com CFOP 5xxx e bloquear CFOP interestadual antes de consumir numeração; 229 testes fiscais aprovados.
- [x] Estruturar o destinatário da NF-e 55 no cliente e preservar snapshot próprio no pedido pelas migrations clientes 0004 e marketplace 0011.
- [x] Exigir endereço, município/IBGE, UF, CEP e indicador de IE; gerar enderDest e bloquear antes da numeração quando incompleto. Regressões com 61 e 229 testes aprovadas.
- [ ] Transformar os demais cenários catalogados em fixture e teste do XML correspondente.
- [ ] Ampliar o motor tributário e concluir o aceite do pacote do contador v2 com contrato externo e amostra mensal validada.
- [x] Manter Focus, SEFAZ direta e produção desligados durante toda a preparação realizada até 09/09/2026.
- [x] Criar o pré-diagnóstico `supplier_return_fiscal_preparation_v1` para devolução ao fornecedor, ligado à entrada e ao XML integral, sem emissão, numeração, estoque ou transmissão.
- [x] Bloquear preparação incompleta quando faltarem XML integral, chave, modelo 55, identidades coincidentes ou itens fiscais originais.
- [x] Criar a seleção persistente e reversível dos itens e quantidades da devolução, limitada ao recebido e ainda sem gerar documento fiscal; migration fiscal 0036.
- [x] Preservar o `nItem` na importação e mapear cada seleção ao item original, bloqueando ambiguidades e excesso agregado por lotes; migration compras 0011.
- [x] Submeter o rascunho à revisão fiscal com snapshot por item, responsável, horário e SHA-256 do XML; migration fiscal 0037.
- [x] Implementar a decisão segregada e imutável do revisor fiscal, exclusiva de Administrador/Contabilidade, com aprovação da preparação ou devolução para correção e sem autorização automática de emissão; migration fiscal 0038.
- [x] Modelar parecer tributário versionado e imutável para natureza, CFOP oficial de saída e tratamento textual por tributo definido por Administrador/Contabilidade, sem defaults presumidos; migration fiscal 0039.
- [x] Estruturar parâmetros fiscais por `nItem` vinculados ao parecer escolhido, com lote completo, versões imutáveis e códigos explícitos, ainda sem bases, alíquotas, cálculo ou XML; migration fiscal 0040.
- [x] Criar memória de cálculo não emissiva por item, usando somente valores expressamente informados, zeros explícitos quando não aplicáveis e conferência atômica dos totais; migration fiscal 0041.
- [x] Criar aprovação segregada da memória completa antes de qualquer futuro rascunho de XML; migration fiscal 0042, decisão única por outro responsável e somente sobre a versão mais recente.
- [ ] Revisar a Fase 1 com o contador quando os dados reais chegarem.

## Próxima ação verificável

O fluxo já preserva origem, itens, `nItem`, snapshot e hash do XML. A revisão aprova somente a preparação, o parecer registra a orientação global e a ficha por item preserva as classificações explícitas sem copiar a entrada. A memória vinculada à versão exata da ficha agora exige bases, alíquotas e valores para ICMS, ICMS-ST, FCP, IPI, PIS, COFINS, IBS e CBS, inclusive zeros, e só grava quando os totais declarados conferem com a soma integral dos itens. Ela não calcula uma fórmula por conta própria nem alimenta XML. A revisão segregada já permite a outro responsável aprovar ou devolver somente a memória mais recente, preservando uma decisão imutável por versão. A ficha logística versionada já registra modalidade, transportador, volumes e pesos sobre a memória aprovada mais recente (migration 0043). A composição comercial versionada agora confere base + frete + seguro + despesas − desconto (migration 0044), sem representar o vNF. A revisão segregada foi implementada pela migration 0045 e exige orientação explícita sobre os reflexos tributários; o aceite com dados reais continua pendente. O rateio comercial por item foi implementado (migration 0046), com componentes explícitos, somas exatas, vínculo à composição aprovada atual e histórico imutável. Não define incidência tributária. A próxima ação interna é estruturar os reflexos sobre bases tributárias, mediante orientação contábil. XML, numeração e transmissão continuam bloqueados. Quando os dados reais estiverem disponíveis, ainda será necessário o aceite contábil e a homologação por canal.
