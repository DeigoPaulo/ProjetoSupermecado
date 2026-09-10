# Indicador de composição do total por item

10/09/2026 · ciclo 89 · contrato não emissivo.

## Representação segura

O `indTot` foi representado no contrato de produtos por `inclui_total_candidato`, `inclui_total_fonte` e `inclui_total_confirmado`. A extração sempre inicia o candidato vazio, fixa a fonte em `DECISAO_FISCAL_PENDENTE` e mantém a confirmação falsa.

Os valores `0` e `1` são reconhecidos apenas como formato de candidato. Eles não se tornam uma decisão aplicada: candidato vazio gera `INDTOT_CANDIDATO_PENDENTE`, candidato preenchido gera `INDTOT_NAO_CONFIRMADO`, fonte diferente é recusada e confirmação direta é erro estrutural.

## Isolamento da totalização

O novo campo não filtra itens, não altera `valor_produtos`, não recalcula totais e não preenche `vNF`. A totalização diagnóstica continua somando exclusivamente os valores informados pelas origens já aprovadas, enquanto `permite_aplicar_indtot`, geração de XML e emissão permanecem falsas.

## Próximo passo

O passo seguinte foi concluído no ciclo 90: `modBC` agora é candidato do contador, vazio e não confirmado, sem cálculo ou serialização. A próxima lacuna é `pRedBC`.
