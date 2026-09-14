# Verificação de empacotamento do catálogo de teste

14/09/2026 · ciclo 113.

## Fronteira real

O pacote do servidor local é produzido por `scripts/package_local_server.ps1` a partir de um commit rastreável, usando `git archive`. Esse método aplica as regras `export-ignore` de `.gitattributes`, que retiram `tests.py` e `test_*.py` sob `apps`, além dos testes dos demais componentes declarados.

O catálogo `apps/fiscal/test_support_identidades_fiscais.py` começa com `test_` e, portanto, pertence explicitamente a essa exclusão. O teste automatizado gera um ZIP temporário de `apps` pelo mesmo comando, abre o arquivo e exige simultaneamente:

- presença do portão de runtime `apps/fiscal/auditoria_importacoes_catalogo_teste.py`;
- ausência do catálogo de identidades de teste;
- ausência do teste próprio do catálogo;
- ausência de qualquer arquivo Python reconhecido como teste.

O ensaio real do commit resultou em 588 entradas, zero arquivos Python de teste e zero ocorrências do catálogo. O ZIP temporário foi removido depois da inspeção; nenhum pacote ou artefato foi publicado.

## Defesa em profundidade

Depois de criar o ZIP, o empacotador já chama `local_server_package_content_v1`. Esse contrato abre o conteúdo e recusa arquivos `tests.py`, prefixo `test_`, sufixo `_test.py` ou pasta `tests`, independentemente do `git archive`.

O cenário existente de adulteração foi ampliado com o caminho exato do catálogo. O pacote manipulado foi recusado e o diagnóstico identificou `test_support_identidades_fiscais.py`. Assim, uma alteração acidental em `export-ignore` ainda encontra uma segunda barreira antes da promoção do arquivo definitivo; o publicador e a Central também repetem a validação de conteúdo já existente.

Foram aprovados nove testes do portão, o cenário comercial específico de adulteração e 523 testes da suíte fiscal completa.

## Limites

A verificação não gerou instalador, não substituiu artefato, não publicou arquivo e não acessou banco, credencial ou certificado. Ela não libera homologação, produção, Focus, SEFAZ direta ou emissão fiscal.

## Próximo passo

Com a cadeia catálogo → importação → regressão → empacotamento protegida, retomar a estratégia principal do CNPJ alfanumérico pela definição de um portão puro de escrita canônica, ainda sem conectá-lo a formulários, modelos ou banco.
