# Portão de leitura dupla do CNPJ

14/09/2026 · ciclo 105 · contrato `alphanumeric_cnpj_dual_read_gate_v1`.

## Objetivo

O portão compara simultaneamente o texto recebido e sua representação canônica, sem consultar nem alterar o banco. A implementação ainda é uma função pura: recebe candidatos preparados pelo chamador e devolve somente o identificador interno quando existe exatamente uma correspondência segura.

As fronteiras previstas são Empresa, Filial, Licença e Credencial. Elas não foram conectadas aos consumidores reais neste ciclo.

## Regras de segurança

- A consulta precisa ter formato e dígito verificador válidos.
- A fronteira precisa ser informada explicitamente.
- Quando os candidatos pertencem a empresas, o escopo da empresa é obrigatório e é aplicado antes da comparação.
- Cadastros com formato ou DV inválido são contabilizados, mas nunca selecionados ou corrigidos.
- Candidatos malformados ou sem origem/identificador são recusados como cadastro inválido.
- Uma correspondência textual exata não tem preferência sobre outra correspondência canônica.
- Duas ou mais correspondências dentro da mesma fronteira produzem `AMBIGUO`, sem devolver ID.
- O diagnóstico informa apenas contagens, divergências e impressão digital reduzida; não devolve o CNPJ completo.

## Resultados possíveis

- `ENCONTRADO_UNICO`: exatamente um candidato válido; o ID interno pode ser devolvido.
- `NAO_ENCONTRADO`: nenhum candidato canônico válido.
- `AMBIGUO`: mais de um candidato; identidade recusada.
- `CONSULTA_INVALIDA`: formato, vazio ou DV da consulta inválido.
- `ESCOPO_EMPRESA_OBRIGATORIO`: a fronteira contém candidatos escopados, mas a empresa não foi informada.
- `FRONTEIRA_INVALIDA` ou `CONJUNTO_INVALIDO`: contrato de chamada recusado.

## Estado operacional

Nenhum model, consulta, tela, sincronização, licença, credencial, integração Focus, conexão direta com a SEFAZ ou emissão passou a usar o portão. Não houve alteração de ambiente, feature flag, certificado ou dado persistido.

## Próximo passo

O adaptador sombra e a política de identidades de desenvolvimento foram concluídos nos ciclos 106 e 107. O próximo passo é classificar estaticamente os candidatos por finalidade, sem reescrever valores.

Foram aprovados 21 testes focados e 482 testes da suíte fiscal completa.
