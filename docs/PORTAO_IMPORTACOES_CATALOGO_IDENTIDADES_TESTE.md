# Portão de importações do catálogo de identidades de teste

14/09/2026 · ciclo 111 · contrato `fiscal_test_catalog_import_gate_v1`.

## Objetivo

O portão impede que `test_support_identidades_fiscais` seja importado por código operacional. Arquivos `test_*.py`, `tests.py` ou dentro de uma pasta `tests` podem usar o catálogo; qualquer importação equivalente fora dessas fronteiras torna a verificação não conforme.

## Cobertura

A análise usa a árvore sintática dos arquivos Python sob `apps` e reconhece:

- `import` direto;
- `from ... import ...`, inclusive relativo;
- `__import__` com módulo literal;
- `importlib.import_module` com módulo literal.

Textos que apenas mencionam o módulo não são tratados como importação. Erro de leitura ou sintaxe fecha o portão para que um arquivo não seja ignorado silenciosamente.

O relatório padrão contém contagens. Detalhes de arquivo, linha, mecanismo e módulo só aparecem com `--detalhes` ou quando há não conformidade. A execução não importa os módulos analisados, não consulta banco, não grava arquivos e não altera configurações.

## Uso

```text
python manage.py auditar_importacoes_catalogo_teste
python manage.py auditar_importacoes_catalogo_teste --detalhes
```

O comando termina com erro quando encontra importação operacional ou arquivo que não pôde ser analisado. Desde o ciclo 112, `scripts/test_regression.ps1` o executa antes de qualquer suíte nos perfis rápido e completo.

## Estado

O projeto atual possui somente importações autorizadas em testes e nenhuma importação do catálogo em runtime. Focus, SEFAZ direta, ambientes, credenciais, certificados e emissão permanecem inalterados e desligados conforme seus próprios portões.

Foram analisados 638 arquivos Python, com quatro referências autorizadas em testes, nenhuma em runtime e nenhum erro de leitura ou sintaxe. Após a verificação do empacotamento, nove testes próprios e 523 testes da suíte fiscal completa foram aprovados.

## Próximo passo

A exclusão do empacotamento foi comprovada no ciclo 113 em [VERIFICACAO_EMPACOTAMENTO_CATALOGO_TESTE.md](VERIFICACAO_EMPACOTAMENTO_CATALOGO_TESTE.md). O próximo passo é retomar o CNPJ alfanumérico com um portão puro de escrita canônica, sem consumidor operacional.
