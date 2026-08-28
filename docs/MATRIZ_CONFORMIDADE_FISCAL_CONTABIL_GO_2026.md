# Matriz de conformidade fiscal e contábil — Goiás 2026

Atualizada em 28/08/2026. Documento interno de engenharia e homologação.

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
| Pacote do contador | Gerencial | Pacote fiscal estruturado e aceite |
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
- [ ] Versionar NCM, CEST e CFOP.
- [ ] Implementar IBS/CBS conforme schema e nota técnica vigentes.
- [ ] Validar XML no schema oficial e registrar a versão.
- [ ] Comparar cálculos e XMLs com o contador.

## Fase 3 — pacote do contador v2

- [ ] Usar emissão/autorização para definir competência.
- [ ] Incluir XMLs de saída, entrada e eventos.
- [ ] Exportar itens, CFOP, NCM, CEST, CST/CSOSN, cBenef, bases, alíquotas e tributos.
- [ ] Incluir cancelamento, CC-e, manifestação e situação oficial.
- [ ] Incluir inventário valorizado e critério de custo.
- [ ] Reconciliar vendas, recebimentos, documentos, entradas e estoque.
- [ ] Definir contrato com o software contábil e onde será gerada a EFD ICMS/IPI.
- [ ] Validar uma amostra mensal e registrar o aceite.

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
- [x] Manter a importação sem rede, exigir hash esperado e falhar com segurança quando não existir catálogo vigente.
- [x] Cobrir a venda interna com CFOP 5xxx e bloquear CFOP interestadual antes de consumir numeração; 229 testes fiscais aprovados.
- [x] Estruturar o destinatário da NF-e 55 no cliente e preservar snapshot próprio no pedido pelas migrations clientes 0004 e marketplace 0011.
- [x] Exigir endereço, município/IBGE, UF, CEP e indicador de IE; gerar enderDest e bloquear antes da numeração quando incompleto. Regressões com 61 e 229 testes aprovadas.
- [ ] Transformar os demais cenários catalogados em fixture e teste do XML correspondente.
- [ ] Corrigir o motor tributário e construir o pacote do contador v2.
- [ ] Manter Focus, SEFAZ direta e produção desligados durante toda a preparação.
- [ ] Revisar a Fase 1 com o contador quando os dados reais chegarem.

## Próxima ação verificável

Versionar NCM, CEST e CFOP e ampliar os cenários tributários do motor sem presumir o enquadramento dos produtos; em paralelo, iniciar o pacote do contador v2 com os dados fiscais já estruturados.
