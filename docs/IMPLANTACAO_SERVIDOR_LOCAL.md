# Implantação do servidor local administrativo

Este roteiro cobre supermercados que precisam operar sem depender da internet. O PDV dos caixas continua sendo um aplicativo separado e limitado ao operador. O administrativo local roda o mesmo ERP Django em um computador servidor ou máquina principal da loja.

## Arquitetura

- Servidor local: Django/Waitress, banco de dados, arquivos `media/`, logs, backup e filas de sincronização.
- Acesso administrativo: navegador em `http://127.0.0.1:8000/` na própria máquina ou pelo IP da rede interna.
- PDV desktop: instalado nos caixas e conectado ao servidor local.
- Nuvem: opcional, por sincronização segura quando a loja contratar esse modo.

## Preparação inicial

1. Instale Python, Git e as dependências do sistema.
2. Crie a `.venv` e instale `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Ajuste `ALLOWED_HOSTS` com `127.0.0.1`, `localhost` e o IP interno do servidor.
5. Em loja real, troque `SECRET_KEY`, desative `DEBUG` e use PostgreSQL quando possível.

## Operação manual

O script usa Waitress por padrão:

```powershell
.\scripts\run_local_server.ps1 -Bind 0.0.0.0 -Port 8000
```

O `runserver` fica restrito a desenvolvimento explícito:

```powershell
.\scripts\run_local_server.ps1 -Development
```

## Serviço Windows

O serviço `DeigoVarejoServidorLocal` usa WinSW para executar Waitress, iniciar automaticamente com o Windows, reiniciar após falha e manter logs rotativos em `%ProgramData%\DeigoVarejo\ServidorLocal\logs`.

1. Baixe o WinSW somente da publicação oficial e confira o SHA-256 divulgado pela fonte ou pelo processo de distribuição interno.
2. Abra o PowerShell como administrador.
3. Execute:

```powershell
.\scripts\install_local_server_service.ps1 `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -ExpectedSha256 "COLOQUE_AQUI_64_CARACTERES_HEXADECIMAIS" `
  -Bind 0.0.0.0 `
  -Port 8000 `
  -DatabaseEngine PostgreSQL
```

O instalador usa PostgreSQL por padrão e recusa concluir quando o `.env` aponta para outro motor ou quando `pg_dump`/`pg_restore` não estão disponíveis. Ele valida o hash antes de copiar o wrapper, executa `check`, migrations e `collectstatic`, instala/inicia o serviço e só conclui após o healthcheck em `/login/`. A conta virtual `NT SERVICE\DeigoVarejoServidorLocal` não possui senha armazenada; código fica somente leitura, enquanto `media`, estáticos e logs em `%ProgramData%\DeigoVarejo\Dados` recebem modificação.

O pacote offline inclui um runtime Python 3.12 oficial e exclusivo, extraído em `%ProgramData%\DeTecServer\Python312`; ele não instala nem altera o Python do Windows. Um ambiente virtual ligado ao perfil particular de um usuário é preservado como backup e recriado antes de instalar o serviço, evitando que a conta virtual dependa de caminhos em `C:\Users\...`.

O instalador é idempotente: em uma atualização ele valida e reutiliza o runtime Python, as dependências e a configuração PostgreSQL existentes. Somente componentes ausentes, incompatíveis ou com versão diferente são substituídos; banco, `.env`, mídia, certificados e backups permanecem preservados.

Para uma instalação deliberadamente SQLite de desenvolvimento, use `-DatabaseEngine SQLite -ImportExistingSqlite`. SQLite não é a escolha para o servidor de produção com vários caixas.

Diagnóstico operacional:

```powershell
.\scripts\test_local_server_service.ps1
```

Remoção do serviço, preservando os logs:

```powershell
.\scripts\uninstall_local_server_service.ps1
```

Para remover também os arquivos do wrapper e logs, use `-RemoveServiceFiles`. O banco, `media/`, projeto e backups não ficam nessa pasta e não são apagados.

Em produção, configure o serviço para uma conta local dedicada, sem login interativo e com acesso mínimo à pasta do ERP e ao banco. A homologação deve confirmar início após reinicialização, recuperação após falha e acesso pela rede interna.

## Tarefa agendada de contingência

Se o serviço ainda não estiver homologado, a tarefa agendada pode ser usada temporariamente:

```powershell
.\scripts\register_local_server_task.ps1 -Bind 0.0.0.0 -Port 8000 -AtStartup -Force
```

## Backup local

Antes do primeiro backup, valide as fontes sem criar arquivos:

```powershell
.\scripts\backup_local.ps1 -ValidarSomente
```

Quando o serviço WinSW estiver instalado, o script lê `DeigoVarejoServidorLocal.xml` e usa os mesmos `SQLITE_PATH`, `MEDIA_ROOT` e `LOG_DIR` da aplicação. Sem o serviço, usa a configuração efetiva do Django. O destino padrão é `%ProgramData%\DeigoVarejo\Backups` e pode ser alterado por `LOCAL_BACKUP_DIR` ou `-Destino`.

```powershell
.\scripts\backup_local.ps1
.\scripts\backup_local.ps1 -IncluirLogs
```

O contrato `erp_local_backup_v2` contém dump lógico, mídia, manifesto e SHA-256. Em SQLite, inclui snapshot consistente pela API nativa. Em PostgreSQL, inclui `database.dump` no formato custom de `pg_dump`, sem senha na linha de comando. Em produção, defina `BACKUP_ENCRYPTION_PASSPHRASE` fora do repositório para gerar também `.zip.aes`.

Agendamento diário:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -RetencaoDias 15
```

A tarefa valida as fontes antes de ser registrada e roda como `SYSTEM`, sem depender de usuário conectado. A conta precisa ter leitura do código e acesso ao diretório de dados e ao destino dos backups.

## Pacote de distribuição

O pacote do servidor é gerado somente a partir de um commit Git limpo e rastreável:

```powershell
.\scripts\package_local_server.ps1 -Version 1.0.0
```

O resultado contém o ZIP sem banco, mídia ou `.env`, um manifesto `local_server_package_v1` e um arquivo SHA-256. Em produção, use `-RequireSignedCommit` para aceitar somente commit Git com assinatura válida. A assinatura de código do artefato definitivo continua sendo uma etapa separada do pipeline comercial. Antes de concluir o pacote, o pipeline abre o ZIP pelo contrato `local_server_package_content_v1`, limita quantidade e tamanho descompactado, exige `manage.py`, `requirements.txt`, `config/settings.py` e aplicações Django e bloqueia caminhos inseguros, `.git`, ambientes virtuais, bancos, `.env`, certificados/chaves, mídia, logs, backups e artefatos. O publicador repete a mesma inspeção e a Central a executa novamente antes de liberar o download. As regras `export-ignore` também retiram testes Python, documentos iniciais, protótipos e referências internas; o contrato rejeita esses arquivos mesmo se forem reinseridos manualmente. Manuais operacionais de implantação permanecem permitidos.
### Módulos sensíveis compilados

O pacote comercial pode substituir módulos Python selecionados por extensões compiladas com Nuitka. Isso dificulta a leitura casual do código, mas não torna uma instalação sob controle do cliente absolutamente indevassável. A proteção comercial também depende de licenciamento, assinatura, ACLs e contrato.

Na estação Windows de build, usando a mesma versão e arquitetura do Python da instalação de destino:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_protected_modules.ps1 -Commit HEAD -Force
.\scripts\package_local_server.ps1 `
  -Version 1.0.0 `
  -ProtectedModulesDirectory dist\protected_modules `
  -RequireProtectedModules `
  -RequireSignedCommit
```

O contrato `local_server_protected_modules_v1` registra commit, implementação, versão e ABI do Python, plataforma, arquitetura e SHA-256 do fonte e do binário. O empacotador recusa overlays de outro commit ou runtime, confirma os hashes, remove o `.py` correspondente e incorpora o manifesto ao ZIP. Nunca copie um overlay entre versões do Python ou entre arquiteturas. Sem `-RequireProtectedModules`, o pacote continua sendo apenas de desenvolvimento/homologação.

Depois da revisão, promova a versão para a Central do servidor local:

```powershell
.\scripts\publish_local_server.ps1 -Version 1.0.0 -RequireSignedCommit
```

O publicador confere contrato, versão, nome, tamanho, SHA-256, ausência de dados do cliente e exigência de commit assinado. O ZIP é copiado para `LOCAL_SERVER_PACKAGE_PATH` e o manifesto é promovido por último; assim, um upload parcial permanece bloqueado. A Central libera o download somente ao admin master, registra a entrega em auditoria e volta a bloquear o pacote se qualquer byte for alterado. Configure `LOCAL_SERVER_VERSION`, `LOCAL_SERVER_PACKAGE_PATH` e `LOCAL_SERVER_REQUIRE_SIGNED_COMMIT` por ambiente.
## Atualização controlada e rollback

Baixe o ZIP e o manifesto publicado para a mesma pasta. Antes da janela de manutenção, valide o pacote sem tocar no serviço:

```powershell
.\scripts\update_local_server.ps1 `
  -PackagePath "C:\Instaladores\DeigoVarejoServidorLocal.zip" `
  -RequireSignedCommit `
  -ValidarSomente
```

Na janela aprovada, abra o PowerShell como administrador e execute o mesmo comando sem `-ValidarSomente`. O atualizador:

1. confere contrato, versão, commit, tamanho, SHA-256 e ausência de dados do cliente;
2. rejeita caminhos inseguros, pacote excessivo ou estrutura incompleta;
3. preserva `.env`, banco, mídia, ambiente virtual e configuração do serviço;
4. cria cópia do código e snapshot SQLite consistente em `%ProgramData%\DeigoVarejo\Atualizacoes`;
5. para o serviço, aplica código, dependências, migrations e arquivos estáticos;
6. inicia o serviço e exige healthcheck em `/login/`;
7. restaura automaticamente código e SQLite se qualquer etapa falhar.

O histórico usa o contrato `local_server_update_history_v1`, e o ponto de retorno usa `local_server_rollback_v1`. Não apague a pasta de rollback antes da conferência operacional. A automação de rollback desta versão é exclusiva para SQLite. Instalações PostgreSQL exigem backup nativo, plano de reversão de migrations e execução assistida por DBA.
## Restauração validada

Sempre teste a integridade antes da janela, sem alterar o serviço ou os dados:

```powershell
.\scripts\restore_local_backup.ps1 `
  -BackupPath "C:\Backups\supermercado-local-20260728-020000.zip" `
  -ValidarSomente
```

Para arquivo criptografado, informe `BACKUP_ENCRYPTION_PASSPHRASE` no ambiente ou use `-SenhaCriptografia`. O arquivo `.sha256` correspondente é obrigatório. A validação confere SHA-256, descriptografia, segurança do ZIP, contrato `erp_local_backup_v2`, dump lógico, snapshot SQLite e mídia declarada.

Na janela aprovada, abra o PowerShell como administrador:

```powershell
.\scripts\restore_local_backup.ps1 `
  -BackupPath "C:\Backups\supermercado-local-20260728-020000.zip" `
  -ConfirmarRestauracao
```

Antes de substituir qualquer dado, o script cria outro backup em `%ProgramData%\DeigoVarejo\Restauracoes`. Depois para o serviço, confirma que o motor do backup coincide com o servidor, restaura SQLite por snapshot ou PostgreSQL por `pg_restore --single-transaction`, restaura a mídia, executa migrations e `manage.py check`, inicia o serviço e exige healthcheck em `/login/`. Se alguma etapa falhar, banco e mídia anteriores são recolocados automaticamente. O resultado usa `local_restore_history_v1` e a validação usa `local_restore_validation_v1`.

Para PostgreSQL, instale as ferramentas cliente oficiais e mantenha `pg_dump` e `pg_restore` da mesma versão principal do servidor. Quando não estiverem no `PATH`, configure `POSTGRES_PG_DUMP_PATH` e `POSTGRES_PG_RESTORE_PATH`. A senha é obtida da configuração Django e permanece somente no ambiente do subprocesso, nunca nos argumentos. A primeira restauração de produção ainda deve ser homologada em uma base separada e acompanhada por DBA.

## Política operacional por modo

- **Local:** vendas, estoque e cadastros não são enviados à nuvem. Novos eventos remotos são rejeitados e eventos pendentes ficam pausados, sem descarte.
- **Híbrido ou nuvem com agente:** exige sincronização automática habilitada e URL HTTPS. Ao reativar essa política, os eventos pausados voltam às filas.
- **Licenciamento:** a consulta comercial à central é independente dessa política operacional e continua seguindo tolerância, cache e liberação emergencial definidos no módulo de licenciamento.

A troca de modo deve ser feita pelo administrador da empresa. O diagnóstico em `Sistema > Sincronização` mostra separadamente eventos pendentes, com erro e pausados.
## Credencial individual da sincronização

Cada matriz deve usar uma credencial própria na comunicação loja-nuvem. Configure no servidor local e na Central o mesmo mapa JSON, usando o CNPJ como chave:

```env
SINCRONIZACAO_TOKENS_EMPRESA_JSON={"00.000.000/0001-00":"segredo-longo-e-exclusivo-da-empresa"}

Para trocar a credencial sem interromper a loja, publique primeiro a configuração de rotação nos dois lados. O primeiro valor é sempre usado para novos envios, e os anteriores são aceitos apenas temporariamente:

    SINCRONIZACAO_TOKENS_EMPRESA_JSON={"00.000.000/0001-00":{"atual":"novo-segredo-exclusivo","anteriores":["segredo-anterior"]}}

Depois que todos os servidores locais estiverem enviando com o token atual, remova `anteriores`. O diagnóstico marca empresas que ainda estão nessa janela de rotação e nunca exibe os segredos.

SINCRONIZACAO_MAX_EVENTO_BYTES=1048576
```

Não reutilize a credencial entre clientes. SINCRONIZACAO_API_TOKEN só pode ser aceito durante uma migração controlada, com SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=true; o padrão seguro é false. O diagnóstico em Sistema > Sincronização lista empresas com credencial individual, fallback transitório ou configuração ausente.

## Sincronização loja-nuvem

No modo híbrido ou nuvem com agente:

```powershell
.\scripts\register_sync_task.ps1 -IntervaloMinutos 1
```

Antes da produção, confirme URL e token da API no `.env` e homologue conflitos e retomada após indisponibilidade.

## Pendências de homologação

- Instalar o serviço com um binário WinSW verificado em uma máquina Windows limpa.
- Homologar a conta virtual dedicada e as ACLs em uma máquina Windows limpa.
- Validar atualização com rollback e janela fora do expediente.
- Homologar backup restaurável, sincronização e transmissão fiscal no ambiente real.
