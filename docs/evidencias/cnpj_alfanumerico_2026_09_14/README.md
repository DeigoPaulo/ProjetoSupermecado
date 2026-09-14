# Evidências oficiais do CNPJ alfanumérico

Data de corte: 14/09/2026.

Este diretório preserva as fontes usadas no ciclo 102. Os arquivos são somente evidência; não representam ativação de emissão, troca de ambiente ou homologação de qualquer canal.

| Arquivo | Origem oficial | SHA-256 |
|---|---|---|
| `manual_dv_cnpj_alfanumerico.pdf` | Receita Federal — Manual de cálculo do DV | `7bb839f6c9beb968bd5bb67d31dd5db090d2333be55815759cfb293e639b4754` |
| `perguntas_respostas_cnpj_alfanumerico.pdf` | Receita Federal — Perguntas e respostas | `c59ab587536ca22f634373cd6a0603afc834f286d3f557e60ad488f4e6264835` |
| `nt_conjunta_dfe_2025_001_v1_00.pdf` | Portal Nacional DF-e — NT Conjunta 2025.001 v1.00 | `671d546b24ad4682e267fc76a9eeca8f14ad15ead2be20721ee2aec5438cf964` |
| `nt_nfe_2026_004_v1_01.pdf` | Portal Nacional NF-e — NT 2026.004 v1.01 | `5f24a25351e790692754b07bbefac42ac67e70167a62a7806395d880f56675be` |

O pacote XSD `docs/evidencias/nfe_2026_09_10/schemas_010f.zip`, já preservado com SHA-256 `b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`, também integra a cadeia de evidência.

## Conclusões reproduzíveis

- O CNPJ mantém 14 posições: as 12 primeiras aceitam números e letras maiúsculas e as duas últimas são dígitos verificadores numéricos.
- CNPJs numéricos existentes continuam válidos e coexistem com novos CNPJs alfanuméricos.
- O DV usa módulo 11; cada caractere é convertido pelo valor ASCII menos 48 antes da ponderação.
- A chave de acesso continua com 44 posições e passa a seguir `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`.
- O DV da chave também usa ASCII menos 48 e módulo 11 sobre as 43 posições anteriores.
- A NT 2026.004 v1.01 fixou implantação NF-e/NFC-e até 15/06/2026 em homologação e em 01/07/2026 em produção.
- A indicação preliminar da NT Conjunta sobre possível exclusão de algumas letras dizia expressamente que dependia de confirmação. A orientação posterior da Receita e o XSD oficial aceitam `A-Z`; portanto, o sistema não deve inventar uma lista de letras proibidas.
- Quando houver letra na chave, o código de barras do documento auxiliar precisa alternar entre Code 128 C e A. Essa adequação faz parte do escopo futuro do DANFE e não foi implementada neste ciclo.

## URLs

- [Receita Federal — Manual de cálculo do DV](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf/view)
- [Receita Federal — Perguntas e respostas](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/cnpj/cnpj-alfanumerico.pdf)
- [Portal Nacional — NT Conjunta DF-e 2025.001](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=5ZkvIZt10mQ%3D)
- [Portal Nacional — NT NF-e/NFC-e 2026.004 v1.01](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=BTZQzgsO9Ws%3D)
- [Portal Nacional — esquemas XML vigentes](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D)
