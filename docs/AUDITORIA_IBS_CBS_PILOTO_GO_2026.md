# Auditoria IBS/CBS do piloto GO em 2026

Data de corte: 24/09/2026. Escopo: NF-e modelo 55 e NFC-e modelo 65 de
supermercado varejista, operação interna em Goiás, consumidor final, com CRT 1, 2,
3 e 4 analisados separadamente. Esta auditoria não implementa tributo, não promove
schema e não autoriza produção.

## Fontes oficiais e versão vigente

- Portal Nacional NF-e, [Notas Técnicas](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY%3D):
  NT 2025.002-RTC v1.51, publicada em 04/08/2026. Não foi localizada versão
  posterior da NT 2025.002 na data de corte.
- [NT 2025.002-RTC v1.51](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=AKD%2FmuSmiIY%3D),
  especialmente páginas 4 a 8, 18 a 31 e 40 a 73.
- Portal Nacional NF-e, [Atos RFB/CGIBS](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=ECxaPvwFHQE%3D):
  [Ato Conjunto 1/2025](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=5FAxxHGS5Ic%3D)
  e [Ato Conjunto 4/2026](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=esD6zF5PwcE%3D).
- [Ato Técnico Conjunto 1/2026](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J6f5HbhitlI%3D),
  que aprovou a NT 2025.002 v1.51 para modelos 55 e 65.
- Portal Nacional NF-e, [schemas oficiais](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D):
  `PL_010f_v1.04`, publicado em 31/08/2026, ainda listado em “VERSÕES OFICIAIS
  (em uso)” na data de corte.
- [NT 2026.009 v1.00](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=ADlgg2xjMZI%3D),
  publicada em setembro de 2026: altera apenas a RV I08-140 de CFOP da NF-e 55 e
  declara não modificar leiaute nem schemas XML.

## Conclusão executiva

O XML atual do Deigo não contém `det/imposto/IBSCBS`, `total/IBSCBSTot` nem
`total/vNFTot`. Para emissão em produção desde 03/08/2026, uma venda comum de
`CRT=3` nos modelos 55 ou 65 pode ser rejeitada pela RV UB12-10, cStat 1115,
porque o grupo `IBSCBS` não é informado. As exceções expressas da UB12-10 devem
ser avaliadas por operação; a venda varejista interna comum não deve ser presumida
como exceção.

Para `CRT=1`, `CRT=2` e `CRT=4`, a própria NT v1.51 registra implementação em
produção a partir de 04/01/2027 e informa que orientações específicas serão
publicadas em NT futura. O Ato Conjunto 4/2026 também posterga para 01/01/2027 os
optantes pelo Simples Nacional. Em setembro de 2026, não há base oficial nesta
auditoria para aplicar a rejeição UB12-10 desses CRTs antes das datas declaradas.

Consequência para o piloto: `CRT=3` é bloqueio interno prioritário enquanto o Deigo
não calcular, serializar e totalizar IBS/CBS. Para CRT 1, 2 ou 4, IBS/CBS não é o
bloqueio de setembro de 2026 identificado por esta auditoria, mas classificação,
catálogo, NT futura, virada de 2027 e homologação permanecem pendentes.

## Respostas A a J

### A. Grupos e campos existentes

O grupo de item `IBSCBS` contém `CST`, `cClassTrib`, `indDoacao` e uma escolha
entre tributação regular (`gIBSCBS`) e monofásica (`gIBSCBSMono`). No ramo regular
existem `vBC`, `gIBSUF`, `gIBSMun`, `vIBS` e `gCBS`, com grupos condicionais de
diferimento, devolução, redução, tributação regular, compra governamental, crédito
presumido, transferência e estorno. O total da nota é `IBSCBSTot`, com bases e
totais de IBS UF, IBS municipal, IBS total, CBS, créditos, monofasia e estornos. O
campo `vNFTot` representa o total da NF-e considerando IBS/CBS/IS por fora.

### B. Opcionalidade estrutural no XSD

No `PL_010f_v1.04`, `IBSCBS`, `IBSCBSTot` e `vNFTot` têm `minOccurs=0`. Quando
`IBSCBS` existe, `CST` e `cClassTrib` são estruturalmente obrigatórios. O ramo
regular/monofásico é uma escolha estrutural opcional; dentro do ramo regular,
`vBC`, `gIBSUF`, `gIBSMun`, `vIBS` e `gCBS` são obrigatórios. A opcionalidade do
XSD não elimina regras de validação do autorizador.

### C. Obrigatoriedade por regra ou operação

- UB12-10 exige `IBSCBS` por item no cronograma aplicável e rejeita sua ausência
  com cStat 1115. A regra traz exceções para devolução/complementar referenciada e
  produtos monofásicos identificados por `cProdANP`; elas não autorizam uma exceção
  genérica para varejo.
- UB13 e UB14 validam existência e compatibilidade de `CST`, `cClassTrib` e dos
  ramos condicionados às tabelas oficiais.
- W34-20 exige `IBSCBSTot` quando ao menos um item informa `IBSCBS`; W35 a W59g
  conferem os totais contra a soma dos itens.
- W60-05 e W60-10, relativos a `vNFTot`, permanecem marcados como implementação
  futura na v1.51.

### D. Regras com vigência iniciada em 2026

Para `CRT=3`, UB12-10 foi prevista em homologação para emissões desde 01/07/2026
e em produção para emissões desde 03/08/2026, nos modelos 55 e 65. O Ato Conjunto
4/2026 fixa 03/08/2026 para NF-e e NFC-e, ressalvando Simples, monofasia e os
demais casos expressamente adiados. O Ato Conjunto 1/2025 prevê tolerância de
penalidades até o marco nele definido; esse ato não contém disposição que altere
ou desative a regra técnica UB12-10 do autorizador.

### E. Implementações futuras

A NT marca como futuras, entre outras, as validações de `vItem` e `vNFTot`, partes
do Imposto Seletivo e diversas validações do leiaute monofásico reformulado. Também
remete a NT futura as orientações de CRT 1, 2 e 4 e tributação monofásica. Uma regra
marcada futura não deve ser implementada como obrigatória por suposição.

### F. Diferenças entre NF-e e NFC-e

UB12-10 e os totais principais se aplicam a `55/65`. Há restrições específicas:
crédito presumido da operação e ZFM possui regras exclusivas ou mais amplas na
NF-e 55; a NFC-e 65 rejeita determinados grupos, como crédito presumido da
operação, conforme UB120-10. Eventos tributários descritos na NT são, em sua maior
parte, de NF-e 55. O catálogo `cClassTrib` precisa indicar compatibilidade com o
modelo; não se deve transportar automaticamente uma hipótese da NF-e para NFC-e.

### G. Aplicação ao supermercado varejista em GO

Goiás e a natureza “operação interna/consumidor final” não criam exceção própria na
UB12-10. Para venda comum não monofásica em `CRT=3`, NF-e 55 e NFC-e 65 entram no
cronograma de 03/08/2026. Produtos monofásicos, devoluções, reduções, benefícios e
demais tratamentos precisam de classificação individual por SKU/operação e parecer
fiscal; “supermercado” não é uma classificação tributária suficiente.

### H. Dependência do CRT

| CRT | Situação em 24/09/2026 | Conclusão para o XML Deigo sem IBS/CBS |
| --- | --- | --- |
| 1 - Simples Nacional | NT v1.51: produção a partir de 04/01/2027; Ato 4: optantes a partir de 01/01/2027 | UB12-10 não confirmada como ativa em setembro/2026 |
| 2 - Simples, excesso de sublimite | NT v1.51 inclui expressamente CRT 2 no cronograma de 04/01/2027 e em orientação futura | UB12-10 não confirmada como ativa em setembro/2026 |
| 3 - Regime Normal | UB12-10 em produção desde 03/08/2026 para 55/65 | Pode rejeitar com cStat 1115 |
| 4 - MEI | NT v1.51: produção a partir de 04/01/2027; Ato 4 alcança optantes | UB12-10 não confirmada como ativa em setembro/2026 |

### I. Decisões do contador/responsável fiscal

Permanecem externas ao software: CRT real por filial; enquadramento de cada SKU e
operação; `CST` e `cClassTrib`; base, alíquotas e reduções; monofasia; benefícios;
devoluções; doações; crédito presumido; tratamentos de ZFM/ALC; e aplicabilidade das
exceções. O sistema não pode inferir esses valores de NCM, CFOP ou descrição.

### J. O XML atual pode ser rejeitado?

Sim, para NF-e 55 ou NFC-e 65 de `CRT=3`, emissão em produção com data igual ou
posterior a 03/08/2026 e item fora das exceções da UB12-10: a ausência de
`det/imposto/IBSCBS` pode gerar cStat 1115. Para CRT 1, 2 e 4 em setembro de 2026,
a v1.51 agenda a implementação para janeiro de 2027; esta auditoria não confirma
rejeição antecipada. Em qualquer CRT, se `IBSCBS` for informado, as regras
condicionais e de totalização aplicáveis passam a ser relevantes.

## Matriz normativa e estado do Deigo

| REGRA/CAMPO | MODELO | CRT/ESCOPO | VIGÊNCIA | FONTE OFICIAL | ESTADO NO DEIGO | BLOQUEIA PILOTO? | AÇÃO NECESSÁRIA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IBSCBS` / UB12-10 | 55/65 | CRT 3, salvo exceções | Produção 03/08/2026 | NT 2025.002 v1.51, p. 7 e RV UB12-10; Ato 4/2026 | `ESTRUTURA_AUSENTE` | SIM | Implementar somente em ciclo próprio, após parecer e testes |
| `IBSCBS` / UB12-10 | 55/65 | CRT 1 | 04/01/2027 na NT; 01/01/2027 no Ato | NT v1.51; Ato 4/2026 §1º | `ESTRUTURA_AUSENTE`, `DEPENDENCIA_CONTABIL` | NAO | Monitorar NT futura e preparar catálogo |
| `IBSCBS` / UB12-10 | 55/65 | CRT 2 | 04/01/2027 na NT | NT v1.51, UB12-10 e p. 7 | `ESTRUTURA_AUSENTE`, `DEPENDENCIA_CONTABIL` | NAO | Não equiparar a CRT 3; aguardar orientação específica |
| `IBSCBS` / UB12-10 | 55/65 | CRT 4 | 04/01/2027 na NT; 01/01/2027 no Ato | NT v1.51; Ato 4/2026 §1º | `ESTRUTURA_AUSENTE`, `DEPENDENCIA_CONTABIL` | NAO | Monitorar NT futura e preparar catálogo |
| `CST`, `cClassTrib` | 55/65 | Por item/operação | Com o grupo `IBSCBS` | NT v1.51, UB13/UB14; XSD 010f | Campos de texto existem; `CATALOGO_AUSENTE`, `REGRA_NEGOCIO_AUSENTE` | DEPENDE_DE_ENQUADRAMENTO | Importar tabelas oficiais versionadas e obter decisão fiscal |
| `gIBSCBS` e subgrupos | 55/65 | Conforme CST/classificação | Condicional | NT v1.51, UB13-UB82a; XSD 010f | `ESTRUTURA_AUSENTE`, `CALCULO_AUSENTE` | DEPENDE_DE_ENQUADRAMENTO | Projetar contrato por hipótese fiscal |
| `gIBSCBSMono` | 55/65 | Produtos monofásicos | Majoritariamente 2027/futura | NT v1.51 e Ato 4/2026 §2º | `ESTRUTURA_AUSENTE`, `CALCULO_AUSENTE`, `CATALOGO_AUSENTE` | DEPENDE_DE_ENQUADRAMENTO | Não implementar antes das tabelas e orientação vigentes |
| `IBSCBSTot` / W34-20 | 55/65 | Quando item contém IBS/CBS | Com o grupo de item | NT v1.51, W34-W59g; XSD 010f | `TOTALIZADOR_AUSENTE` | SIM | Implementar soma e reconciliação em ciclo próprio |
| `vNFTot` / W60 | 55/65 | Quando aplicável | Implementação futura | NT v1.51, W60-05/W60-10 | `TOTALIZADOR_AUSENTE` | NAO | Aguardar ativação oficial da regra |
| Compatibilidade por modelo | 55/65 | Conforme `cClassTrib` | Com informação do grupo | NT v1.51, UB14-25 e regras específicas | `REGRA_NEGOCIO_AUSENTE`, `CATALOGO_AUSENTE` | DEPENDE_DE_ENQUADRAMENTO | Validar tabela por modelo e versão |
| XSD `PL_010f_v1.04` | 55/65 | Estrutural | Em uso, publicado 31/08/2026 | Lista oficial de schemas | Arquivado e íntegro; não promovido | SIM | Aprovação e instalação controlada após implementação |
| Homologação GO | 55/65 | Filial/canal reais | Antes de produção | Processo operacional externo | `TESTE_AUSENTE`, `DEPENDENCIA_HOMOLOGACAO` | SIM | Homologar separadamente SEFAZ direta e Focus |

## Confronto com o código

| Componente atual | Constatação | Lacunas |
| --- | --- | --- |
| `ModoTransicaoIbsCbs` | `LEGADO`, `PREPARACAO` e `EMISSAO_HOMOLOGADA`; o último é bloqueado, mas `LEGADO` ainda gera XML sem IBS/CBS | `REGRA_NEGOCIO_AUSENTE`, `DEPENDENCIA_HOMOLOGACAO` |
| `ibs_cbs_vigencia_inicio` | Data depende de cadastro aprovado e não aplica o cronograma oficial por CRT/modelo | `REGRA_NEGOCIO_AUSENTE`, `DEPENDENCIA_CONTABIL` |
| Produto: `cst_ibs_cbs`, `classificacao_tributaria_ibs_cbs` | Valida somente formato 3/6 dígitos quando exigido | `CATALOGO_AUSENTE`, `REGRA_NEGOCIO_AUSENTE` |
| `capacidade_tributaria_fiscal()` | Declara corretamente cadastro disponível e XML desabilitado | `ESTRUTURA_AUSENTE`, `CALCULO_AUSENTE` |
| `_pendencias_ibs_cbs_produto()` | Verifica presença/formato, sem existência ou compatibilidade oficial | `CATALOGO_AUSENTE`, `REGRA_NEGOCIO_AUSENTE`, `TESTE_AUSENTE` |
| `_pendencias_emissao_ibs_cbs()` | Bloqueia `EMISSAO_HOMOLOGADA`; não bloqueia CRT 3 em modo legado após 03/08/2026 | `REGRA_NEGOCIO_AUSENTE` |
| Geradores NF-e/NFC-e | Não serializam `IBSCBS` | `ESTRUTURA_AUSENTE`, `CALCULO_AUSENTE` |
| `_adicionar_totais_icms()` | Totaliza tributos legados; não cria `IBSCBSTot` ou `vNFTot` | `TOTALIZADOR_AUSENTE` |
| Testes fiscais | Cobrem bloqueio preparatório e omissão deliberada, não cenários normativos UB12/W34 | `TESTE_AUSENTE`, `DEPENDENCIA_HOMOLOGACAO` |

## XSD e decisão deste ciclo

O pacote oficial vigente não mudou em relação ao congelamento 010f. A cópia arquivada
continua com SHA-256
`b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`;
o `nfe_v4.00.xsd` interno continua com SHA-256
`adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df`.
Nenhum arquivo foi substituído ou promovido.

Próximo bloqueio interno prioritário: suportar IBS/CBS para `CRT=3` em um ciclo
separado, depois de decisão do responsável fiscal sobre o catálogo e as operações
reais. Bloqueios externos permanecem aprovação do XSD operacional e homologação por
canal/filial. Esta auditoria, isoladamente, não libera nenhuma emissão.
