# Plano de integração da escrita de CNPJ em Empresa e Filial

16/09/2026 · ciclo 116 · contrato
`alphanumeric_cnpj_company_branch_integration_plan_v1`.

## Decisão

A auditoria protegida da base local foi repetida sem escrita e confirmou 18 bloqueios: 17 CNPJs
com DV inválido e uma colisão. Também existem seis equivalências esperadas entre Empresa e sua
Filial matriz. Os bloqueios têm aparência de dados fictícios de desenvolvimento, mas não serão
corrigidos, excluídos ou substituídos automaticamente.

O plano separa duas frentes:

- dados legados inválidos e colisões bloqueantes exigem decisão e correção manual identificada;
- criação válida, rejeição de DV inválido, atualização equivalente, colisão canônica, legado
  inválido e troca de identidade podem avançar para validação local nos formulários reais.

## Limite operacional

O plano não consulta credenciais, não expõe identificadores e não altera formulário, modelo ou
banco. Persistência canônica, constraints e migração de conteúdo continuam bloqueadas. Focus,
SEFAZ direta, homologação, produção e emissão permanecem desligados por esta etapa.

## Próximo passo

A integração foi concluída e comprovada no ciclo 117 em `EmpresaForm.clean_cnpj` e
`FilialForm.clean_cnpj`, sem migration ou correção automática dos 18 bloqueios locais. O próximo
passo da fase 4 é avaliar separadamente Cliente pessoa jurídica e Fornecedor pessoa jurídica,
pois seus campos, escopos e compatibilidade com CPF não podem herdar a regra de Empresa/Filial
sem uma comparação própria.
