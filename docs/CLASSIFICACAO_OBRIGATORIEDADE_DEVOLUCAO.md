# Classificação de obrigatoriedade da devolução

10/09/2026 · ciclo 84 · análise parcial, não emissiva.

Atualização do ciclo 85: as famílias foram decompostas em 106 campos no [inventário atômico](INVENTARIO_DADOS_DEVOLUCAO.md), que também registra nove lacunas de cadastro/modelagem. A classificação normativa abaixo permanece bloqueada para aplicação operacional.

Atualização do ciclo 92: a matriz passou a 38 famílias. `cEnq` é 1-1 somente dentro do grupo `IPI`; a presença desse grupo continua condicionada à hipótese fiscal e o código depende do contador.

Atualização do ciclo 93: a matriz passou a 42 famílias. PIS e COFINS são grupos 0-1 no item e possuem uma escolha interna exclusiva quando presentes; variantes com cálculo exigem a modalidade estrutural correspondente. Aplicabilidade e conteúdo continuam dependentes do contador.

O contrato `supplier_return_field_requirement_matrix_v1` classifica as 42 famílias rastreadas sem transformar cardinalidade de XSD em decisão fiscal. O escopo permanece restrito a NF-e modelo 55, finalidade 4, saída, com uma NF-e de origem. Leitura normativa integral, vigência operacional em Goiás e caso real aprovado pelo contador continuam falsos.

## Critério empregado

| Categoria | Significado |
|---|---|
| `OBRIGATORIO_ESTRUTURAL` | Grupo/campo exigido pela estrutura aplicável do leiaute; conteúdo ainda precisa ser válido para o cenário. |
| `OBRIGATORIO_REGRA_CONTEXTO` | O XSD pode admitir ausência, mas MOC/NT exige presença ou valor no cenário de devolução. |
| `MISTO_SUBCAMPOS` | A família reúne campos obrigatórios e condicionais; deverá ser decomposta antes do serializador. |
| `CONDICIONADO_VALOR` | Informado quando o componente existe e deve reconciliar item e total. |
| `CONDICIONADO_MODALIDADE` / `CONDICIONADO_PRESENCA` | Depende do transporte escolhido ou dos dados físicos efetivamente informados. |
| `CONDICIONADO_ENQUADRAMENTO` / `CONDICIONADO_HIPOTESE` | Depende do tratamento tributário aprovado para o caso concreto. |
| `CONDICIONADO_GRUPO_IPI` | O campo é estruturalmente obrigatório dentro de `IPI`, mas a presença do grupo depende da hipótese fiscal aprovada. |
| `CONDICIONADO_GRUPO_CONTRIBUICAO` | PIS/COFINS é opcional no item; quando presente, exige uma variante estrutural exclusiva. |
| `CONDICIONADO_VARIANTE_CONTRIBUICAO` | A modalidade percentual, quantidade ou sem cálculo deve ser compatível com a variante explicitamente escolhida. |
| `OPCIONAL_CONTROLADO` | O leiaute admite ausência; qualquer conteúdo exige origem fiscal aprovada e nunca recebe anotação interna automaticamente. |
| `PENDENTE_HIPOTESES` / `PENDENTE_VIGENCIA_E_ENQUADRAMENTO` | A evidência atual ainda não permite fechar conteúdo ou aplicação operacional. |

## Conclusões documentais já sustentadas

- `ide`, `emit`, `det/prod`, `det/imposto`, `total`, `transp` e `pag/detPag` fazem parte da estrutura obrigatória ou contêm subcampos obrigatórios no leiaute aplicável.
- `DFeReferenciado` possui ocorrência opcional no XSD, mas as regras VC02/VC03 da NT 2025.002 v1.51 exigem chave e `nItem` no contexto tratado. O cronograma e a implantação por UF ainda precisam ser confirmados antes do uso operacional.
- Para finalidade 4, a regra YA02-04 exige `tPag=90`. `vPag` é estruturalmente obrigatório no detalhamento e o contrato adota `0.00`, coerente com YA03-30.
- `impostoDevol` é opcional como grupo. Se a hipótese for aplicável, `pDevol` e `vIPIDevol` internos tornam-se obrigatórios e o motivo deve ser tratado em `infAdProd`; a decisão de enquadramento continua com o contador.
- `cEnq` é obrigatório dentro de `IPI`, mas isso não torna o próprio grupo `IPI` obrigatório em toda devolução. Seu valor permanece pendente de decisão do contador.
- Frete, seguro, despesas e desconto são condicionados à existência dos valores, com reconciliação entre itens e totais. Não se presume incidência tributária.
- Transportador e volumes dependem da modalidade e da operação física; `modFrete` permanece estruturalmente necessário.
- ICMS, PIS, COFINS, ST/FCP e seus totais dependem de regime, hipótese e orientação do caso concreto. As orientações GO 21305/21349 não foram generalizadas.
- IBS/CBS/RTC continua dependente de vigência, classificação, tabelas, enquadramento e implantação. Presença no pacote XSD não ativa o grupo.
- `infAdic` é opcional e controlado. `infAdProd` torna-se necessário em hipóteses documentadas, como IPI devolvido, mas não recebe cópia automática de textos internos.

## Fontes e limites

- XSD preservado `PL_010f_v1.04/leiauteNFe_v4.00.xsd`, SHA-256 `2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542`.
- MOC 7.0 Anexo I, páginas 57–58, 62 e 125–126.
- NT 2025.002 v1.51, regras de referência e totais nas páginas 71–72 e grupos RTC associados.
- NT 2026.007 v1.00, páginas 3 e 7, usada somente para registrar cronograma e condicionantes de contribuinte exclusivo IBS/CBS.
- Orientações tributárias de Goiás 21305/21349, mantidas como hipóteses específicas.
- Parecer do contador para o caso real, ainda indisponível.

As fontes foram lidas nos trechos diretamente relevantes; isso não equivale à leitura integral de todas as notas, tabelas e regras. Nenhuma classificação possui `aplicacao_operacional=True`.

## Próximo marco

Decompor as famílias `MISTA` em campos atômicos e criar um inventário de lacunas de dados do sistema: disponível, ausente no cadastro, dependente do XML original ou dependente do contador. O resultado continuará sem XML e servirá para decidir quais cadastros precisam ser completados antes do serializador.
