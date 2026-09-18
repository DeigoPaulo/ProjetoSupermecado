# Matriz de qualificação offline dos canais fiscais

Contrato: `fiscal_channel_offline_qualification_matrix_v1`.

Esta matriz separa o que os testes locais comprovam do que ainda depende de Focus NFe,
SEFAZ, certificado, credenciamento e dados reais. Ela não acessa rede, não lê segredos, não
altera a configuração da filial e não autoriza homologação nem produção.

| Operação | Focus NFe | SEFAZ direta GO |
| --- | --- | --- |
| Autorização | Compatível offline | Compatível offline |
| Consulta | Compatível offline | Compatível offline |
| Rejeição controlada | Compatível offline | Compatível offline |
| Cancelamento | Compatível offline | Compatível offline |
| Inutilização | Compatível offline | Compatível offline |
| Eventos | Lacuna interna: o adaptador Focus atual não expõe CC-e ou manifestação | Compatível offline para CC-e e manifestação |
| Distribuição DF-e | Compatível offline | Compatível offline |

“Compatível offline” significa somente que o caminho existe, possui evidência estática e é
coberto por teste local. Não significa que o provedor aceitou CNPJ alfanumérico, que a
operação foi autorizada em homologação ou que pode ser usada em produção.

## Dependências externas ainda fechadas

Para a Focus são necessários CNPJ/IE e credenciamento reais, conta/token de homologação,
cenários aprovados pelo responsável fiscal e evidências dos retornos efetivos. Para a SEFAZ
direta também são necessários A1, CSC/ID CSC quando aplicável e revalidação dos endpoints,
schemas e Notas Técnicas oficiais vigentes.

Cada operação deverá ser homologada separadamente. Os protocolos, XMLs enviados e
processados, códigos de rejeição e evidência de recuperação deverão ser arquivados por
filial e canal. A conclusão manual da homologação permanece sujeita às travas existentes.

No ciclo 131, a preservação alfanumérica também foi fechada depois dos adaptadores: o
serviço de consulta/persistência de resumos e eventos DF-e e o parser de XML de entrada
passaram a usar CNPJ e chave canônicos. Assim, letras não são mais removidas antes da busca
da filial/fornecedor nem antes da gravação do documento recebido.

## Próximo passo interno

O roteamento por filial foi formalizado no ciclo 132. Focus usa seu adaptador próprio de
DF-e, mas CC-e e manifestação falham fechado enquanto não houver implementação oficial
específica. SEFAZ direta GO resolve DF-e, CC-e e manifestação para seus adaptadores próprios.
O canal desativado não carrega operações auxiliares e o modo de compatibilidade do servidor
continua aceitando as configurações globais já existentes.

O próximo passo é levar essa mesma visão por filial ao diagnóstico administrativo e preparar
os roteiros de execução/coleta de evidências por operação, sem chamadas externas até que as
credenciais e a filial piloto existam.

No ciclo 133, essa visão passou a existir na tela de homologação e ficou restrita ao Master.
Focus apresenta cinco de sete capacidades estruturais, com CC-e e manifestação bloqueadas;
SEFAZ direta GO apresenta sete de sete. Em ambos os casos, a coluna de homologação real
permanece pendente. A caixa DF-e e os detalhes de CC-e/manifestação também passaram a
diagnosticar o adaptador da filial concreta, em vez de uma configuração global genérica.

No ciclo 134, a matriz passou a alimentar os roteiros não executáveis documentados em
[ROTEIROS_HOMOLOGACAO_CANAIS_FISCAIS.md](ROTEIROS_HOMOLOGACAO_CANAIS_FISCAIS.md).
Cada combinação canal/operação agora possui cenários, evidências e critério de aprovação
explícitos sem qualquer liberação de rede.
