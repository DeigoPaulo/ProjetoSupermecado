# Modalidade da base do ICMS na devolução

10/09/2026 · ciclo 90 · contrato não emissivo.

## Evidência de leiaute

O arquivo oficial preservado `PL_010f_v1.04/leiauteNFe_v4.00.xsd`, SHA-256 `2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542`, enumera `modBC` com 0 — margem de valor agregado, 1 — pauta, 2 — preço tabelado máximo e 3 — valor da operação. A presença e a aplicabilidade do campo dependem do grupo ICMS concreto; a enumeração não decide a hipótese tributária.

## Representação segura

Somente o grupo ICMS do contrato tributário contém `modalidade_base_candidata`, `modalidade_base_fonte` e `modalidade_base_confirmada`. A extração inicia candidata vazia, fixa a fonte em `DECISAO_CONTADOR_PENDENTE` e mantém a confirmação falsa.

Um código de 0 a 3 preenchido continua gerando `MODBC_NAO_CONFIRMADA`. Código fora da enumeração, fonte diferente ou confirmação direta são recusados. O valor 3 fixado no gerador antigo de outras operações não é copiado para a devolução.

## Isolamento dos valores e canais

A pendência de `modBC` não modifica nem invalida a origem aprovada de base, alíquota e valor. Ela mantém `dados_completos` falso, `permite_aplicar_modalidade_base_icms` falso e não produz grupo XML. Focus e SEFAZ direta permanecem bloqueados.

## Próximo passo

O passo seguinte foi concluído no ciclo 91: `pRedBC` agora é hipótese vazia e não confirmada do contador, sem preenchimento automático. A próxima lacuna é `cEnq` do IPI.
