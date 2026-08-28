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

No serviço Windows com Waitress, o WhiteNoise entrega os arquivos produzidos por `collectstatic` diretamente em `/static/`. Isso mantém CSS, JavaScript, ícones e fontes disponíveis sem depender de `runserver` ou de um servidor web externo.

Antes do download pelo Master, o contrato `detech_server_offline_package_validation_v2` abre a mídia e exige servidor, runtime Python, wheelhouse, PostgreSQL, WinSW, iniciador e aplicativos desktop. Ele confere declaração única, hashes, tamanhos, caminhos seguros, ausência de arquivos extras, estrutura do ZIP interno do servidor, pacotes `.whl` no wheelhouse e correspondência dos manifestos dos aplicativos. Pacote incompleto ou adulterado não recebe URL de download. O próprio `package_detech_server_offline.ps1` executa esse contrato sobre um ZIP temporário e só promove o nome definitivo após aprovação; falhas removem o temporário e preservam o último artefato válido.

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

O contrato `erp_local_backup_v2` contém dump lógico, mídia, manifesto e SHA-256; mídia ou logs declarados permanecem representados no ZIP mesmo quando o diretório está vazio. Em SQLite, inclui snapshot consistente pela API nativa. Em PostgreSQL, inclui `database.dump` no formato custom de `pg_dump`, sem senha na linha de comando. Antes de gerar o pacote, o backup executa `verificar_integridade_evidencias_fiscais --estrito`, compara a cadeia com `fiscal-evidence-anchor-latest.json`, recusa regressão ou remoção histórica e inclui `fiscal-evidence-anchor.json` com SHA-256 no ZIP. A restauração valida essa âncora e compara o banco restaurado antes de iniciar o serviço. Em produção, defina `BACKUP_ENCRYPTION_PASSPHRASE` fora do repositório para gerar também `.zip.aes`.

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

O publicador offline `scripts/publish_detech_server_offline.ps1` valida o sidecar e repete `detech_server_offline_package_validation_v2` na origem e na cópia temporária. ZIP e checksum final são promovidos com rollback: adulteração ou falha preserva a mídia anterior e remove temporários. Configure `LOCAL_SERVER_OFFLINE_PACKAGE_PATH` com o mesmo destino usado pelo script. A Central exige também o arquivo de mesmo nome acrescido de `.sha256` pelo contrato `detech_server_offline_publication_validation_v1`; ausência, hash divergente ou nome diferente bloqueia o download. O pacote técnico e o instalador offline possuem estados independentes na tela Master.

O publicador técnico confere contrato, versão, nome, tamanho, SHA-256, ausência de dados do cliente e exigência de commit assinado. O ZIP é copiado para `LOCAL_SERVER_PACKAGE_PATH` e o manifesto é promovido por último; assim, um upload parcial permanece bloqueado. A Central libera o download somente ao admin master, registra a entrega em auditoria e volta a bloquear o pacote se qualquer byte for alterado. Configure `LOCAL_SERVER_VERSION`, `LOCAL_SERVER_PACKAGE_PATH` e `LOCAL_SERVER_REQUIRE_SIGNED_COMMIT` por ambiente.
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

Antes da janela real, execute `.\scripts\restore_local_backup.ps1 -BackupPath backup.zip.aes -EnsaiarIsolado`. O contrato `local_restore_rehearsal_v1` restaura SQLite somente em área temporária, verifica a integridade antes e depois, aplica migrations, executa o Django check e compara a cadeia fiscal com a âncora do pacote. Não exige serviço Windows, não altera dados ativos e descarta os arquivos temporários ao terminar. Para PostgreSQL, prepare manualmente um banco vazio com nome iniciado por `deigo_rehearsal_`; o restaurador não cria nem remove bancos. Configure `RESTORE_REHEARSAL_POSTGRES_DB`, `RESTORE_REHEARSAL_POSTGRES_HOST`, `RESTORE_REHEARSAL_POSTGRES_USER` e `RESTORE_REHEARSAL_POSTGRES_PASSWORD` no processo protegido e execute `-EnsaiarIsolado -ConfirmarBancoPostgresTemporario`. O comando recusa banco ativo/origem, nome fora do prefixo ou qualquer objeto existente; somente então executa `pg_restore --single-transaction`, migrations, Django check e integridade fiscal. O banco temporário é preservado para inspeção e descarte manual autorizado.

A cópia externa opcional usa `LOCAL_BACKUP_SECONDARY_DIR` e exige `LOCAL_BACKUP_SECONDARY_CONFIRMED=True` ou `-ConfirmarDestinoSecundario`. Ela aceita somente o pacote AES-256, recalcula o SHA-256 após copiar, promove o arquivo temporário apenas quando o hash coincide e aplica retenção independente. A conta `SYSTEM` da tarefa precisa ter permissão no NAS, compartilhamento ou disco externo; isso deve ser homologado na máquina definitiva. O comando `registrar_resultado_backup_operacional` recebe somente opções fechadas, grava o contrato `backup_operacional_v1` na auditoria e torna o histórico visível apenas no Super Admin e em Backup. Falha recente é pendência alta; validações com `-ValidarSomente` não criam histórico. `LOCAL_BACKUP_MAX_AGE_HOURS` controla o alerta do último sucesso: `0` desativa e `36` é o prazo inicial recomendado após homologar o agendamento. Sem sucesso ou fora do prazo, somente o Master recebe pendência alta. O comando `verificar_pos_implantacao` e a evidência de aceite consultam a mesma política; `0` não libera o aceite. `--backup-max-horas` é uma substituição pontual identificada como argumento no JSON. O aceite usa ainda `local_backup_package_validation_v1`: recalcula o SHA-256, vincula o sidecar ao nome do pacote, rejeita ZIP inseguro ou corrompido e exige `erp_local_backup_v2`, dados lógicos, banco declarado e âncora fiscal íntegra. Quando o pacote mais recente é `.zip.aes`, a inspeção completa depende de `BACKUP_ENCRYPTION_PASSPHRASE` no ambiente protegido da conta executora; o conteúdo temporário é descartado e o resultado não expõe caminho, hash ou segredo.

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
