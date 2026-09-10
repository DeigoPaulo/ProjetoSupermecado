# Redução da base do ICMS na devolução

10/09/2026 · ciclo 91 · contrato não emissivo.

## Evidência de leiaute

O `pRedBC` usa `TDec_0302a04` no arquivo oficial preservado `PL_010f_v1.04/leiauteNFe_v4.00.xsd`, cujo SHA-256 é `2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542`. O tipo aceita até três dígitos inteiros e, quando houver parte decimal, de duas a quatro casas. O contrato limita candidatos à faixa de percentual de 0 a 100.

## Representação segura

O grupo ICMS contém `reducao_base_candidata`, `reducao_base_fonte` e `reducao_base_confirmada`. A extração sempre inicia o percentual vazio, fixa a fonte em `DECISAO_CONTADOR_PENDENTE` e mantém a confirmação falsa.

Um percentual válido preenchido gera `PREDBC_NAO_CONFIRMADA`; vazio gera `PREDBC_CANDIDATA_PENDENTE`. Percentual ou formato inválido, fonte diferente e confirmação direta são recusados.

## Separação das fontes

O campo `reducao_base_icms` do cadastro atual do produto não é lido por esta extração. O XML original e diferenças observadas na memória também não preenchem a candidata. Essas fontes podem apoiar futura conferência humana, mas não substituem uma decisão formal para o caso concreto.

## Isolamento fiscal

A candidata não recalcula nem altera base, alíquota ou valor já informados. `permite_aplicar_reducao_base_icms`, geração de XML, Focus, SEFAZ direta e emissão permanecem falsos.

## Próximo passo

Concluído no ciclo 92: o enquadramento legal do IPI (`cEnq`) foi modelado dentro da política de IPI devolvido, separado do valor informativo da memória e sem copiar automaticamente o cadastro atual. O próximo passo é discriminar variantes de PIS/COFINS.
