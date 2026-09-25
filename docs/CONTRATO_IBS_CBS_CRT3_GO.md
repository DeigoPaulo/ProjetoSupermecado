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
Como defesa independente, ela recompõe a base a partir de `vProd - vDesc -
vPIS - vCOFINS - vICMS - vFCP` e recalcula `vIBSUF`, `vIBSMun`, `vIBS` e
`vCBS`. Para documentos de 2026, as alíquotas informadas precisam ser exatamente
`0.1000`, `0.0000` e `0.9000`; o contrato não projeta esses valores para anos
futuros. Frete, seguro, outras despesas, II, ICMSUFDest, ICMS monofásico, ISSQN
e IS no item falham fechado. O mesmo ocorre para `vFCPUFDest`, `vICMSUFDest`,
`PISST`, `COFINSST` e qualquer marcador monofásico encontrado no grupo de
impostos. Esses bloqueios refletem componentes da fórmula oficial que o recorte
atual não modela; não representam suporte novo.
`vNFTot` não foi antecipado porque sua validação permanece futura na NT vigente.

O adaptador Focus projeta os campos IBS/CBS já validados a partir do XML; ele
não recalcula tributos. O canal direto preserva o XML assinado.

## Evidências e limites

Os XMLs assinados de NFC-e 65 e NF-e 55 são validados obrigatoriamente na suíte
contra o pacote oficial arquivado no repositório,
`PL_010f_v1.04`, SHA-256
`b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`.
O helper de auditoria valida caminhos, links, compressão, CRC, dependências e
hash antes de materializar os XSDs em diretório temporário; DTD, entidades
externas e rede permanecem desabilitados. O schema não foi instalado nem
promovido e os testes não dependem de variável de ambiente.

Testes cobrem datas e CRTs, catálogo fechado, compatibilidade 55/65, arredondamento,
desconto, dois itens e adulteração individual de `vBC`, alíquotas, valores, CST,
classificação e totalizadores, inclusive quando item e total são adulterados de
forma coerente. Focus e SEFAZ direta passam pela mesma validação matemática antes
do envio. Homologação real por filial e canal, aprovação do schema operacional e
aceite do responsável fiscal continuam externos.

No endurecimento do ciclo 173, a presença de `IBSCBS` passou a ser verificada
explicitamente, sem depender da avaliação booleana de elementos XML. Assim,
`IBSCBS` vazio, campos estruturais ausentes, preenchimento parcial e presença em
somente parte dos itens são recusados localmente também quando o adaptador Focus
declara validação de schema própria. O caminho SEFAZ direta usa a mesma barreira.
O ciclo não adicionou CST, cClassTrib, redução, monofasia, regime ou autorização
de produção.

## Catálogo e capacidade

O catálogo permanece mínimo: `CST=000` com `cClassTrib=000001`. Sua evidência
registra IT 2025.002 v1.60, data oficial 23/06/2026, URL oficial e consulta em
24/09/2026. As classificações vieram do endpoint oficial de dados abertos, que
não oferecia snapshot versionado estável; por isso nenhum hash de catálogo foi
inventado. A capacidade distingue emissão genérica desabilitada do recorte
`fiscal_ibs_cbs_go_crt3_standard_v1` habilitado.

Fontes oficiais: NT 2025.002-RTC v1.51, IT 2025.002 v1.60, Ato Conjunto
RFB/CGIBS 4/2026 e pacote de schemas `PL_010f_v1.04`, todos listados no Portal
Nacional da NF-e na data de corte.
