# Matriz de capacidade fiscal do piloto GO

Data de congelamento: 24/09/2026. Contrato:
`fiscal_go_pre_homologation_matrix_v1`.

Esta matriz consolida somente evidência existente no código e nos testes. `SUPORTADO`
significa suporte interno dentro do recorte descrito, não homologação nem autorização de
produção. Todo item continua com `autoriza_producao=false`. A consulta desta matriz é
somente diagnóstica: ela não participa do preflight, da geração nem da transmissão.

Estados:

- `SUPORTADO`: ramo interno explícito, com validação e teste dentro do recorte.
- `BLOQUEADO`: o sistema deve recusar o cenário nas condições atuais.
- `DEPENDE_DE_HOMOLOGACAO`: estrutura offline existe, mas falta prova externa real.
- `DEPENDE_DE_PARAMETRIZACAO`: depende de cadastro ou decisão fiscal explícita.
- `NAO_IMPLEMENTADO`: não existe cobertura emissiva completa.

O campo `controle` localiza a evidência independente: `DIAGNOSTICO`, `PREFLIGHT`,
`GERADOR`, `PRE_TRANSMISSAO` ou `EXTERNO`. `bloqueio_operacional=COMPROVADO` só é
usado quando o caminho emissivo correspondente foi localizado. A presença de um controle
na lista não significa que a função `consultar_capacidade_piloto_go` o acione.

## Congelamento do XSD

`PACOTE_ATUAL` para testes e auditoria: `PL_010f_v1.04`, preservado em
`docs/evidencias/nfe_2026_09_10/schemas_010f.zip`.

`PACOTE_OFICIAL_IDENTIFICADO`: o Portal Nacional NF-e ainda lista o pacote 010f entre as
versões oficiais em uso, publicado em 31/08/2026 e relacionado à NT 2025.002 v1.50 e à
NT 2026.007 v1.00. A cópia foi baixada novamente da fonte oficial em 24/09/2026 apenas
para comparação local e descartada em seguida.

| Evidência | Resultado |
| --- | --- |
| Origem oficial | `https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=8ITFuBLltXs%3D` |
| SHA-256 oficial revalidado | `b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998` |
| SHA-256 arquivado | `b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998` |
| Comparação | `IGUAIS_POR_SHA256` |
| Raiz | `PL_010f_v1.04/nfe_v4.00.xsd` |
| SHA-256 da raiz | `adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df` |
| Conteúdo | cinco XSDs e quatro dependências relativas |
| Modelos estruturais | NF-e 55 e NFC-e 65, leiaute 4.00 |
| Compilação | offline, sem rede, já coberta por auditoria automatizada |
| Pacote operacional | não instalado; `fiscal_schemas` contém somente instruções |
| Impacto | nenhum arquivo substituído; promoção e aprovação continuam pendentes |

O pacote arquivado é usado pelos testes de auditoria, pagamentos NFC-e, CNPJ
alfanumérico e contratos estruturais da devolução. O validador operacional carrega somente
o arquivo configurado por `FISCAL_SCHEMA_DIR`, `FISCAL_NFE_SCHEMA_FILE` e
`FISCAL_SCHEMA_SHA256`; por padrão não há XSD operacional no repositório.

## Matriz consolidada

| Cenário | Estado | Limite comprovado |
| --- | --- | --- |
| NFC-e modelo 65 | `DEPENDE_DE_HOMOLOGACAO` | Venda interna a consumidor final possui gerador e preflight |
| NF-e modelo 55 | `DEPENDE_DE_HOMOLOGACAO` | Pedido online interno possui gerador no recorte atual |
| CRT 1 Simples | `DEPENDE_DE_PARAMETRIZACAO` | Exige CSOSN e cadastro completo |
| CRT 2 excesso | `DEPENDE_DE_PARAMETRIZACAO` | Exige CST e decisão de cBenef GO |
| CRT 3 normal | `BLOQUEADO` | Desde 03/08/2026, UB12-10 exige `IBSCBS` no recorte comum; o XML atual o omite |
| CRT 4 MEI | `DEPENDE_DE_PARAMETRIZACAO` | Usa ramo CSOSN; enquadramento depende de revisão |
| CST 00/20/40/41/50 | `SUPORTADO` | Grupos ICMS explícitos no gerador |
| CST fora da matriz | `BLOQUEADO` | Preflight e gerador recusam |
| CSOSN 102/103/300/400 | `SUPORTADO` | Grupo ICMSSN102 explícito |
| CSOSN fora da matriz | `BLOQUEADO` | Preflight e gerador recusam |
| PIS | `DEPENDE_DE_PARAMETRIZACAO` | CST 01/02, 04-09, 49 e 99 possuem ramos explícitos |
| COFINS | `DEPENDE_DE_PARAMETRIZACAO` | CST 01/02, 04-09, 49 e 99 possuem ramos explícitos |
| IPI | `DEPENDE_DE_PARAMETRIZACAO` | Exige CST, cEnq e política da natureza |
| cBenef GO | `DEPENDE_DE_PARAMETRIZACAO` | Decisão por produto/natureza; validade exige revisão fiscal |
| IBS/CBS | `NAO_IMPLEMENTADO` | Cadastro existe, cálculo e XML continuam bloqueados |
| Dinheiro | `SUPORTADO` | `tPag=01`, inclusive em pagamento dividido offline |
| Crédito | `DEPENDE_DE_HOMOLOGACAO` | `tPag=03`; sem driver/adquirente real |
| Débito | `DEPENDE_DE_HOMOLOGACAO` | `tPag=04`; sem driver/adquirente real |
| PIX | `DEPENDE_DE_HOMOLOGACAO` | `tPag=17`; sem verificador real |
| Vale-alimentação | `DEPENDE_DE_HOMOLOGACAO` | `tPag=10`; sem operadora real |
| Vale-refeição | `DEPENDE_DE_HOMOLOGACAO` | `tPag=11`; sem operadora real |
| Pagamento dividido | `DEPENDE_DE_HOMOLOGACAO` | Parcelas e paridade provadas somente offline |
| Destinatário não identificado | `SUPORTADO` | NFC-e omite `dest` explicitamente |
| CPF informado | `SUPORTADO` | Canonicalização e `dest/CPF` implementadas |
| CNPJ quando aplicável | `DEPENDE_DE_HOMOLOGACAO` | Serialização existe; B2B contribuinte não está coberto |
| Endereço do emitente | `DEPENDE_DE_PARAMETRIZACAO` | GO exige estrutura e CEP completos, sem defaults |
| QR Code NFC-e | `DEPENDE_DE_HOMOLOGACAO` | Geração existe; versão, URL e CSC aplicável exigem validação |
| Contingência NFC-e | `DEPENDE_DE_HOMOLOGACAO` | `tpEmis=9` e reconciliação existem offline |
| SEFAZ direta GO | `DEPENDE_DE_HOMOLOGACAO` | Sete capacidades estruturais, rede e produção desligadas |
| Focus NFe | `DEPENDE_DE_HOMOLOGACAO` | Cinco capacidades; CC-e/manifestação falham fechado |
| XSD operacional | `BLOQUEADO` | 010f não foi promovido, aprovado ou instalado |
| Venda interestadual | `NAO_IMPLEMENTADO` | `idDest` atual é interno e o avaliador recusa |
| Destinatário contribuinte | `NAO_IMPLEMENTADO` | B2B exige regras próprias |
| Frete | `NAO_IMPLEMENTADO` | XML atual declara sem frete |
| Finalidade diferente de venda normal | `NAO_IMPLEMENTADO` | Avaliador recusa e geradores fixam `finNFe=1` |
| Produção | `BLOQUEADO` | Nenhuma evidência offline libera produção |

## Diagnóstico versus bloqueio operacional

O emissor já recusa CST/CSOSN fora das listas, cenário GO com modelo desconhecido,
operação interestadual, finalidade não normal, destinatário contribuinte e frete. O novo
diagnóstico não altera esses portões. Essas recusas estão em
`pendencias_preparacao_fiscal`, `pendencias_preparacao_nfe_pedido`, `_icms_produto` e
`avaliar_cenario_fiscal_go`; produção também é recusada pelos adaptadores quando sua
liberação explícita está desligada.

`consultar_capacidade_piloto_go` classifica código ausente como
`BLOQUEADO/CENARIO_NAO_CATALOGADO`, mas retorna `controle=[DIAGNOSTICO]`,
`efeito_da_consulta=SOMENTE_DIAGNOSTICO` e
`bloqueio_operacional=NAO_COMPROVADO`. Portanto, esse retorno impede uma conclusão
positiva da auditoria, porém não prova que um XML seria recusado pelo emissor. Ligar toda a
matriz ao caminho emissivo exigiria um contrato próprio e não faz parte deste ciclo.

O comando abaixo apenas recompõe hashes, compila o ZIP em diretório temporário e publica
JSON determinístico. Ele não consulta rede, banco ou credenciais e não instala schema:

```powershell
python manage.py diagnosticar_pre_homologacao_go
```

## Pendências

Internas: manter a matriz sincronizada quando um ramo emissivo mudar; não implementar
IBS/CBS, B2B, frete ou interestadual sem contrato normativo e testes próprios.

Externas: dados representativos por SKU/operação, decisão do contador, filial e identidade
fiscal reais, A1, credenciamento, adquirentes/verificadores, equipamento, aprovação formal
do pacote e homologação separada de SEFAZ-GO e Focus. Somente depois cabe decidir pela
promoção controlada do XSD; esta auditoria não a autoriza.
