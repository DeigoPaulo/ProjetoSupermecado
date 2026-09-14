# Adaptador sombra de CNPJ para Empresa e Filial

14/09/2026 · ciclo 106 · contrato `alphanumeric_cnpj_company_branch_shadow_adapter_v1`.

## Escopo

O adaptador observa, sem interferir, duas buscas existentes:

- Empresa ativa por CNPJ textual exato, usada no recebimento de eventos de sincronização;
- Filial vinculada a uma empresa por CNPJ textual exato, usada no processamento desses eventos.

Para cada observação, a busca atual e o portão canônico são executados em paralelo. O resultado operacional existente não é substituído nem alterado. O relatório não devolve CNPJ, ID da empresa ou ID da filial.

## Classificações

- `CONCORDAM`: busca exata e portão selecionariam a mesma identidade.
- `CANONICO_ENCONTRA_LEGADO_NAO`: máscara, caixa ou representação impedem a busca exata, mas há uma identidade canônica única.
- `LEGADO_SELECIONA_PORTAO_RECUSA`: a busca atual aceita o texto, mas o portão recusa formato, DV, escopo ou outra regra de segurança.
- `AMBIGUIDADE_CANONICA`: mais de um cadastro representa a identidade consultada; o portão não devolve ID.
- `IDENTIDADES_DIVERGENTES`: os dois mecanismos chegariam a identidades diferentes.
- `AMBOS_NAO_SELECIONAM`: nenhum mecanismo seleciona cadastro.

Toda divergência é bloqueante para uma futura troca. Uma igualdade textual não prevalece sobre ambiguidade canônica.

## Proteções verificadas

- Somente consultas `SELECT` são executadas.
- Empresa preserva o filtro atual de cadastro ativo.
- Filial preserva o escopo obrigatório da empresa e a abrangência atual, que inclui filial inativa.
- O adaptador não lê tokens, certificados, senhas nem configuração de licença.
- O relatório contém apenas contagens, estados e impressão digital reduzida.
- Não há chamada externa, gravação, migração, emissão ou alteração de feature flag.

## Ensaio local

O ensaio protegido realizou 16 observações por meio de 34 consultas, todas `SELECT`. Nas 16, a busca textual atual encontrou o próprio registro de desenvolvimento e o portão recusou o CNPJ por DV inválido. Portanto, o resultado foi:

- 16 `LEGADO_SELECIONA_PORTAO_RECUSA`;
- 16 `CONSULTA_INVALIDA` no portão;
- 16 bloqueios para qualquer ativação.

O resultado confirma a situação apontada na auditoria do ciclo 104. Esses registros têm aparência de dados fictícios e não serão corrigidos automaticamente nem tratados como aceite do futuro CNPJ real.

## Próximo passo

Definir uma política explícita para identidades fiscais de desenvolvimento e teste. Ela deverá separar exemplos oficiais válidos, dados fictícios deliberadamente inválidos e o futuro cadastro real, sem modificar a base atual nem permitir que fixtures sejam confundidas com homologação ou produção.

Foram aprovados 29 testes focados e 490 testes da suíte fiscal completa. Nenhuma migração foi gerada.
