# Inventário estático de identidades fiscais

14/09/2026 · ciclo 108 · contrato `static_fiscal_identity_candidate_inventory_v1`.

## Método

O inventário lê arquivos `.py`, `.md`, `.json`, `.yaml` e `.yml` sob `apps` e `docs`. Ele reconhece:

- máscara completa de CNPJ com duas posições finais numéricas;
- bloco literal de 14 posições com as 12 primeiras alfanuméricas e as duas últimas numéricas;
- chave fiscal literal de 44 posições no padrão alfanumérico vigente.

Para evitar capturar variáveis e palavras, valores precisam estar delimitados por aspas, crases ou tags XML. Blocos de 14 posições também exigem contexto fiscal explícito na mesma linha. Categorias desconhecidas terminariam em `_REVISAR`; o ensaio final não deixou nenhuma ocorrência nessa situação.

## Resultado consolidado

Após o ciclo 109, foram lidos 703 arquivos. Cinquenta e seis contêm 332 candidatos protegidos:

- 208 identidades de modelo em testes;
- 61 casos de validação de documento;
- 19 chaves fiscais de teste;
- 10 trechos XML fiscais de teste;
- 20 valores usados para testar o próprio classificador;
- seis exemplos de configuração em documentação;
- dois exemplos normativos documentados;
- quatro marcadores dos comandos de demonstração;
- uma máscara visual e uma regra interna do classificador.

Por representação, são 178 máscaras, 132 blocos de 14 posições e 22 chaves de 44 posições. O único candidato acrescentado é a entrada que testa a classificação do catálogo central; o catálogo gera seus documentos a partir de bases de 12 posições e não adiciona identidade operacional fixa. Algumas chaves pertencem aos testes do classificador e, por isso, a soma por finalidade permanece coerente sem classificar todas como chave fiscal funcional.

## Diagnóstico

Não foi encontrada identidade operacional fixa escondida no código executável. Os quatro marcadores de demonstração pertencem aos comandos protegidos no ciclo 107; a máscara visual não representa pessoa jurídica; e a ocorrência restante é a regra do próprio inventariador.

O relatório padrão apresenta apenas contagens. `--detalhes` acrescenta caminho, linha, categoria e impressão digital reduzida, nunca o valor completo. A execução não consulta banco, não grava arquivos e não reescreve fixtures.

## Uso

```text
python manage.py inventariar_identidades_fiscais_estaticas
python manage.py inventariar_identidades_fiscais_estaticas --detalhes
```

## Próximo passo

O catálogo central foi definido no ciclo 109 em [CATALOGO_IDENTIDADES_FISCAIS_TESTE.md](CATALOGO_IDENTIDADES_FISCAIS_TESTE.md), sem substituir em massa os candidatos existentes, e recebeu seu primeiro uso gradual no ciclo 110. O inventário permaneceu em 332 candidatos. O próximo passo é criar uma verificação estática que recuse sua importação por código de runtime antes de ampliar a adoção.

Com a primeira adoção do ciclo 110, foram aprovados 53 testes focados e 514 testes da suíte fiscal completa. Nenhuma migração foi gerada.
