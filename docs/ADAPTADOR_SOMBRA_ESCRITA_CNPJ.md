# Comparação sombra da escrita de CNPJ

14/09/2026 · ciclo 115 · contrato `alphanumeric_cnpj_company_branch_shadow_write_adapter_v1`.

## Objetivo

O comparador executa os formulários reais de Empresa e Filial ao lado do portão canônico. Ele não substitui a validação atual, não chama `save()` e usa uma cópia da instância durante atualizações para preservar inclusive o objeto em memória.

## Resultado

A comparação isolada confirmou três lacunas:

- os formulários atuais aceitam CNPJ com DV inválido;
- a unicidade textual de Empresa permite cadastrar a mesma identidade em outra representação;
- Filial não possui unicidade de CNPJ, portanto a colisão precisa ser verificada dentro do escopo da empresa.

O observador classifica concordância, recusa divergente e colisão canônica. O diagnóstico apresenta somente estados, campos com erro e contagens; não expõe CNPJ ou identificadores internos.

Os pontos exatos para uma integração futura são `EmpresaForm.clean_cnpj`, antes da unicidade do modelo, e `FilialForm.clean_cnpj`, antes da validação do modelo. A integração ainda depende da revisão dos dados existentes para não transformar valores legados inválidos ou colisões em alterações silenciosas.

## Validação e limites

Sete testes próprios cobrem criação, DV inválido, colisões de Empresa e Filial, atualização equivalente, preservação da instância e proteção do diagnóstico. Foram aprovados 39 testes focados do ciclo, 77 testes focados acumulados e 538 testes da suíte fiscal completa. As consultas observadas foram exclusivamente `SELECT` e nenhuma migração foi criada.

O portão de importações analisou 642 arquivos Python, encontrou seis usos autorizados do catálogo em testes e nenhum em runtime. O inventário analisou 714 arquivos e manteve os mesmos 332 candidatos classificados, sem item para revisão.

Focus, SEFAZ direta, homologação, produção e emissão continuam fora desta etapa.

## Atualização — 16/09/2026

As três lacunas observadas neste ciclo foram corrigidas na fronteira Empresa/Filial pelo ciclo
117. O comparador permanece como regressão e agora confirma que formulário e portão recusam DV
inválido, que ambos detectam colisões canônicas e que a atualização equivalente preserva a
identidade. O texto acima registra o diagnóstico histórico anterior à integração.

## Próximo passo

A próxima fronteira da fase 4 é Cliente pessoa jurídica e Fornecedor pessoa jurídica. Os dados
legados Empresa/Filial permanecem sem correção automática.
