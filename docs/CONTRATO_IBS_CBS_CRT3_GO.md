# Contrato IBS/CBS GO CRT 3

Data de corte: 25/09/2026. Contrato:
`fiscal_ibs_cbs_go_crt3_standard_v1`.

## Escopo emissivo

O recorte cobre somente NF-e 55 e NFC-e 65 emitidas em Goiás por filial `CRT=3`,
em operação interna normal já aceita pelos avaliadores existentes, com
`CST=000` e `cClassTrib=000001`. A obrigação entra em homologação em 01/07/2026
e em produção em 03/08/2026. O modo administrativo `LEGADO` não pode suprimir
o grupo depois dessas datas.

O catálogo é mínimo e falha fechado. Classificação desconhecida, incompatível
com o modelo, regime automotivo especial, monofasia, redução, diferimento,
crédito presumido, doação, transferência, devolução e qualquer hipótese não
catalogada são recusados. CRT 1, 2 e 4 não são antecipados por este contrato.

## Cálculo e XML

A base deste recorte é formada por valor dos produtos menos desconto, PIS,
COFINS, ICMS e FCP destacados. Os cálculos usam `Decimal` e
`ROUND_HALF_UP`, com alíquotas de transição de 2026:

- IBS estadual: `0,1000%`;
- IBS municipal: `0,0000%`;
- CBS: `0,9000%`.

Cada item recebe `imposto/IBSCBS/gIBSCBS`; a nota recebe
`total/IBSCBSTot`. A pré-transmissão exige o grupo em todos os itens do recorte,
valida CST/classificação/modelo e reconcilia as somas dos itens com o total.
`vNFTot` não foi antecipado porque sua validação permanece futura na NT vigente.

O adaptador Focus projeta os campos IBS/CBS já validados a partir do XML; ele
não recalcula tributos. O canal direto preserva o XML assinado.

## Evidências e limites

O XML NFC-e assinado foi validado offline contra o pacote oficial
`PL_010f_v1.04`, SHA-256
`b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`.
O schema não foi instalado nem promovido. O teste opcional reproduz o confronto
quando `FISCAL_IBS_CBS_XSD_ZIP` aponta para o ZIP oficial auditado.

Testes cobrem datas e CRTs, catálogo fechado, compatibilidade 55/65, arredondamento,
desconto, dois itens, totais adulterados, preflight, pré-transmissão, projeção
Focus e ausência de vazamento para o Simples. Homologação real por filial e canal,
aprovação do schema operacional e aceite do responsável fiscal continuam externos.

Fontes oficiais: NT 2025.002-RTC v1.51, IT 2025.002 v1.60, Ato Conjunto
RFB/CGIBS 4/2026 e pacote de schemas `PL_010f_v1.04`, todos listados no Portal
Nacional da NF-e na data de corte.
