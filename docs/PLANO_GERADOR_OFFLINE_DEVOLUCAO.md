# Portão de entrada do gerador offline da devolução

11/09/2026 · ciclo 95 · especificação não emissiva.

O contrato `supplier_return_offline_generator_input_plan_v1` define o limite entre os contratos neutros já construídos e um futuro serializador exclusivo da NF-e de devolução. Ele não produz XML: apenas confere a matriz atômica, os subcontratos, os portões externos e registra todos os motivos que impedem a entrada.

## Evidência estrutural

O pacote `docs/evidencias/nfe_2026_09_10/schemas_010f.zip` está arquivado no repositório e teve o SHA-256 `b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998` reproduzido. Dentro dele, `PL_010f_v1.04/leiauteNFe_v4.00.xsd` teve o SHA-256 `2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542` reproduzido.

Isso comprova a integridade da evidência arquivada. Não comprova vigência/aplicabilidade integral, não instala o pacote em `fiscal_schemas` e não o aprova para uso operacional.

## Ordem direta de `NFe/infNFe`

| Ordem | Elemento | Ocorrências XSD | Situação no contrato atual |
|---:|---|---:|---|
| 1 | `ide` | 1 | Mapeado |
| 2 | `emit` | 1 | Mapeado |
| 3 | `avulsa` | 0–1 | Fora do escopo atual |
| 4 | `dest` | 0–1 | Mapeado |
| 5 | `retirada` | 0–1 | Fora do escopo atual |
| 6 | `entrega` | 0–1 | Fora do escopo atual |
| 7 | `autXML` | 0–10 | Fora do escopo atual |
| 8 | `det` | 1–990 | Mapeado |
| 9 | `total` | 1 | Mapeado |
| 10 | `transp` | 1 | Mapeado |
| 11 | `cobr` | 0–1 | Fora do escopo atual |
| 12 | `pag` | 1 | Mapeado |
| 13 | `infIntermed` | 0–1 | Fora do escopo atual |
| 14 | `infAdic` | 0–1 | Mapeado |
| 15 | `exporta` | 0–1 | Fora do escopo atual |
| 16 | `compra` | 0–1 | Fora do escopo atual |
| 17 | `cana` | 0–1 | Fora do escopo atual |
| 18 | `infRespTec` | 0–1 | Fora do escopo atual |
| 19 | `infSolicNFF` | 0–1 | Fora do escopo atual |
| 20 | `agropecuario` | 0–1 | Fora do escopo atual |
| 21 | `infPAA` | 0–1 | Fora do escopo atual |

“Fora do escopo atual” não significa proibido ou dispensado. Significa somente que o contrato de devolução ainda não fornece esse grupo e que sua aplicabilidade não foi decidida.

## Recusa fechada

A entrada permanece recusada se houver campo indisponível, destino dependente de leiaute, subcontrato incompleto, decisão fiscal pendente ou portão externo fechado. Além disso, quatro bloqueios estruturais são obrigatórios nesta etapa:

- `XSD_APLICAVEL_NAO_INSTALADO`;
- `XSD_APLICAVEL_NAO_APROVADO`;
- `ORDEM_NAO_APROVADA_PARA_GERADOR`;
- `SERIALIZADOR_OFFLINE_NAO_IMPLEMENTADO`.

O validador rejeita a remoção desses bloqueios, mudança da ordem/cardinalidade, alteração da evidência ou tentativa de liberar a entrada.

## Limites preservados

A confirmação da ordem na evidência arquivada é separada da aprovação operacional. XML, assinatura, certificado, Focus, SEFAZ direta, ambiente e emissão permanecem desativados. O código não acessa nem altera credenciais, certificados, feature flags ou configurações de provedor.

## Próximo passo

Automatizar a auditoria offline do pacote XSD arquivado — ZIP/CRC, hashes, conjunto de dependências e schema raiz — e especificar sua promoção versionada para `fiscal_schemas`. A auditoria não deve instalar, aprovar ou ativar o pacote automaticamente e não deve gerar XML.