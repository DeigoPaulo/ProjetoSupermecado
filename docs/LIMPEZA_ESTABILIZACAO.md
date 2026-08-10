# Limpeza e estabilização do repositório

Data: 10/08/2026  
Base auditada: commit `bfe40f6` da branch `main`

## Objetivo

Reduzir resíduos de build e inconsistências técnicas sem remover funcionalidades, reverter trabalho existente ou alterar contratos operacionais do ERP, PDV e aplicativos desktop.

## Alterações realizadas

- Removidos do versionamento 5.184 arquivos de ambientes virtuais de build em `desktop_admin/.build-venv` e `desktop_pdv/.venv-build`.
- Removidas saídas reproduzíveis de `desktop_admin/build`, `desktop_admin/dist`, arquivos `.spec` antigos e o temporário `tmp-client-test.out`.
- Preservados os pacotes publicados em `artifacts/`, usados pelas centrais de distribuição.
- Ampliado o `.gitignore` para impedir novo versionamento de ambientes, builds, executáveis temporários e especificações geradas.
- Estabilizados os scripts de build do DeTec Admin e as referências do DeTec PDV, com validação de versão do Python, falha explícita por etapa e testes de portabilidade.
- Incluído no versionamento o `desktop_pdv/DeTecPDV.spec`, necessário ao build atual.
- Removidas referências públicas obsoletas de marca, mantendo apenas identificadores legados necessários à migração e compatibilidade.
- Corrigidas referências quebradas aos documentos físicos do projeto.
- Corrigidos textos visíveis e expectativas de testes com acentuação inconsistente.
- Verificados arquivos próprios em UTF-8 estrito e ausência de caminhos absolutos de usuário no código atual.
- Removida uma importação duplicada sem efeito funcional.

## Itens deliberadamente preservados

- Artefatos oficiais existentes em `artifacts/`.
- Migração da configuração `%LOCALAPPDATA%\SupermercadoPDV`.
- Mutexes, entropia DPAPI e identificadores internos de serviço já usados por instalações existentes.
- Documentos, protótipos e integrações ainda referenciados pelo checklist.
- Funcionalidades, migrations e dados de desenvolvimento.

## Validação

Execute na raiz:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe -m unittest discover -s desktop_pdv -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s desktop_admin -p "test_*.py"
git diff --check
```

Para a configuração de produção, execute também `manage.py check --deploy` com `DEBUG=false`, chave secreta forte, hosts, origens CSRF, HTTPS, cookies seguros e HSTS configurados.

## Pendências externas

Continuam dependentes de ambiente e fornecedores: homologação com TEF real, SEFAZ, impressoras, gaveta, balança e leitores físicos; credenciais de produção; assinatura digital dos instaladores; e ensaio final em máquina Windows limpa e servidor definitivo.