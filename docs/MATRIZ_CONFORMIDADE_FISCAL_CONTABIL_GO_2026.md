# Matriz de conformidade fiscal e contábil — Goiás 2026

Atualizada em 31/08/2026. Documento interno de engenharia e homologação.

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
- [x] Manter Focus, SEFAZ direta e produção desligados durante toda a preparação realizada até 31/08/2026.
- [ ] Revisar a Fase 1 com o contador quando os dados reais chegarem.

## Próxima ação verificável

O validador e o registro imutável de aceite estão prontos sem envio externo. Quando os dados reais estiverem disponíveis, registrar o software contábil e o responsável pela EFD ICMS/IPI, gerar uma amostra da competência, obter a conferência do contador e arquivar a referência do aceite. Enquanto isso, o próximo trabalho interno pode avançar apenas em cenários operacionais que não exijam inventar enquadramento tributário.
