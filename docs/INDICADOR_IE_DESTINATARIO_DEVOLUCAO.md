# Indicador de IE candidato do destinatário

10/09/2026 · ciclo 88 · contrato não emissivo.

## Origem e representação

O campo `indicador_ie_candidato` recebe somente o indicador existente no cadastro atual do fornecedor. Sua fonte é fixada em `CADASTRO_FORNECEDOR_ATUAL` e `indicador_ie_confirmado` deve permanecer falso.

Os códigos cadastrais 1, 2 e 9 são reconhecidos como candidatos, respectivamente contribuinte, isento e não contribuinte. Reconhecer o formato não confirma o enquadramento para a devolução.

## Comportamento do validador

- Candidato vazio gera `IND_IE_DESTINATARIO_CANDIDATO_PENDENTE`.
- Candidato 1, 2 ou 9 gera `IND_IE_DESTINATARIO_NAO_CONFIRMADO`.
- Fonte diferente do cadastro atual é erro.
- Alterar a confirmação para verdadeiro é erro.
- `permite_aplicar_indicador_ie`, geração de XML e emissão permanecem falsas.

## Limites

O indicador não escolhe os demais dados do destinatário, não resolve divergências cadastrais, não grava decisão fiscal e não é enviado ao Focus ou à SEFAZ direta. A prévia restrita apenas mostra o candidato e seu bloqueio.

## Verificação e próximo passo

A regressão conjunta do ciclo aprovou 107 testes. O passo seguinte foi concluído no ciclo 89: `indTot` agora é decisão vazia e não confirmada, sem efeito na totalização. O próximo bloqueio é `modBC` por hipótese do contador.
