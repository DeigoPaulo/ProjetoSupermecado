# Evidência do CNPJ alfanumérico nos DF-e

14/09/2026 · ciclo 102 · contrato `alphanumeric_cnpj_official_evidence_v1`.

## Resultado

A etapa normativa está concluída. Para NF-e e NFC-e, o suporte ao CNPJ alfanumérico já é uma exigência vigente: a NT 2026.004 v1.01 registra produção em 01/07/2026. Isso não torna o ProjetoSupermecado compatível automaticamente; apenas elimina a dúvida normativa que bloqueava a estratégia.

O contrato confere cinco fontes preservadas por SHA-256 e falha se algum arquivo estiver ausente ou alterado. Nenhuma fonte é tratada como autorização para emitir.

## Regra confirmada

- Representação canônica recomendada: 14 caracteres, sem pontuação, em maiúsculas.
- Formato: `[A-Z0-9]{12}[0-9]{2}`.
- DV do CNPJ: ASCII menos 48, módulo 11 e pesos de 2 a 9 da direita para a esquerda.
- CNPJs numéricos e alfanuméricos coexistem; identificadores existentes não mudam.
- Zeros à esquerda devem ser preservados.
- O sufixo `0001` não pode ser usado como indicador permanente de matriz.

## Chave de acesso

A chave mantém 44 posições. Nas posições 7 a 20 permanece o CNPJ do emitente, agora potencialmente alfanumérico. A expressão passa a ser `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`. Para o DV, todos os 43 caracteres anteriores são convertidos por ASCII menos 48 e submetidos ao módulo 11.

O impacto não termina no XML: consultas, eventos, inutilização, referências, QR Code/DANFE e código de barras também precisam aceitar a chave alfanumérica. Para código de barras, a NT Conjunta define alternância Code 128 C/A quando houver letras.

## Situação do sistema

A largura atual dos campos de CNPJ comporta a representação, então não há justificativa para uma migração de largura. A incompatibilidade é semântica:

1. máscaras aceitam apenas números;
2. normalizadores descartam letras;
3. sincronização, licenciamento e buscas dependem dessa normalização;
4. compras e distribuição DF-e comparam documentos e chaves numéricas;
5. os geradores e validadores calculam chaves como sequências somente numéricas;
6. o DANFE ainda não possui contrato para Code 128 híbrido;
7. Focus e SEFAZ direta exigirão homologações independentes.

Portanto, nenhuma mudança operacional foi liberada. Modelos, dados, geradores, credenciais, ambientes, Focus, SEFAZ direta e emissão continuam inalterados e desligados.

## Próximo passo

Definir e testar a estratégia de normalização canônica e retrocompatibilidade, ainda sem alterar cadastros reais: preservar `A-Z0-9`, remover apenas pontuação admitida, converter letras para maiúsculas, manter zeros à esquerda e impedir colisões com identidades numéricas já existentes. A estratégia deverá listar cada consumidor antes de qualquer troca compartilhada.

Foram aprovados 13 testes focados e 461 testes da suíte fiscal completa.
