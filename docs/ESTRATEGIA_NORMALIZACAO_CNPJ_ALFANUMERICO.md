# Estratégia de normalização do CNPJ alfanumérico

14/09/2026 · ciclo 103 · contrato `alphanumeric_cnpj_canonicalization_strategy_v1`.

## Decisão

A representação canônica será formada por 14 caracteres `A-Z0-9`, sem pontuação e em maiúsculas. As duas últimas posições continuam exclusivamente numéricas. A máscara `AA.AAA.AAA/AAAA-DD` pertence somente à apresentação.

O normalizador puro aceita apenas duas formas de entrada:

1. os 14 caracteres sem máscara;
2. a máscara oficial completa.

Espaços externos são removidos. Ponto, barra e hífen só são retirados quando aparecem na posição da máscara oficial. Outros símbolos, máscara parcial, caracteres Unicode e DV com letras são rejeitados; o sistema não tentará “consertar” silenciosamente um identificador inválido.

## Compatibilidade

- Um CNPJ numérico sem máscara mantém exatamente o mesmo valor canônico.
- Versões mascarada e não mascarada do mesmo CNPJ são equivalentes.
- Letras minúsculas são convertidas para maiúsculas.
- Zeros à esquerda são preservados.
- DV e normalização são operações separadas: canonicalizar não transforma um DV incorreto em válido.
- Não haverá fallback para o normalizador antigo, pois ele descarta letras e pode associar uma identidade incorreta.
- Nenhuma gravação deve começar enquanto a auditoria encontrar colisões ou valores inválidos.

O algoritmo reproduz o exemplo oficial `12.ABC.345/01DE-35`. A mesma função de módulo 11 com ASCII menos 48 também foi aplicada a uma chave alfanumérica de 44 posições em teste isolado.

## Inventário de impacto

Foram registrados 23 consumidores em nove áreas:

- cadastro de empresa/filial, consulta cadastral, matriz e cliente/fornecedor;
- máscara e consulta na interface;
- credenciais, eventos e objetos de sincronização;
- validações assinadas e identificação do pagador no licenciamento;
- documento do consumidor no PDV;
- importação XML, distribuição e armazenamento de DF-e;
- adaptadores Focus e SEFAZ direta;
- geradores, validação de XML/retorno e QR Code;
- devolução, transporte e futuro código de barras do DANFE.

O campo único atual de `Empresa.cnpj` opera sobre o texto armazenado, não sobre o valor canônico. Assim, versões formatada e pura podem representar a mesma identidade sem serem necessariamente tratadas como duplicadas em todas as fronteiras. O mesmo risco existe em comparações exatas de payloads, credenciais e chaves. Isso exige auditoria antes de qualquer escrita canônica.

## Transição em seis fases

1. Normalizador puro isolado — concluído neste ciclo, sem acoplamento.
2. Auditoria somente leitura — concluída sem aceite de produção no ciclo 104.
3. Leitura dupla controlada — portão puro concluído, ainda sem consumidores, no ciclo 105.
4. Escrita canônica por fronteira — pendente.
5. Chave, XML, QR Code e DANFE — pendente.
6. Homologação separada de Focus e SEFAZ direta — pendente.

Todas as fases continuam com execução operacional bloqueada. Modelos, dados, migrações, consumidores atuais, credenciais, ambientes, canais e emissão não foram alterados.

## Próximo passo

Auditoria, portão puro, adaptador sombra, política e inventário estático foram concluídos nos ciclos 104 a 108. O próximo passo é definir um catálogo central para novos testes, sem substituição em massa, conforme [INVENTARIO_ESTATICO_IDENTIDADES_FISCAIS.md](INVENTARIO_ESTATICO_IDENTIDADES_FISCAIS.md).

Foram aprovados 15 testes focados e 467 testes da suíte fiscal completa.
