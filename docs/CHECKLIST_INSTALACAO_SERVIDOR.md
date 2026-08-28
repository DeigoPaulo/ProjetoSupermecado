# Checklist de instalacao do Deigo Varejo

Este roteiro e a versao curta para uma instalacao nova. O manual completo fica
em `docs/MANUAL_INSTALACAO_SUPERMERCADO.md`.

## 1. Escolha o cenario

| Cenario | Onde instalar | O que recebe |
| --- | --- | --- |
| Servidor local da loja | Windows Server ou Windows Pro dedicado | Pacote ZIP do servidor local, banco PostgreSQL e servico Windows |
| Servidor central/nuvem | Linux ou Windows Server da Deigo Tecnologia | Pacote de deploy aprovado, PostgreSQL, proxy HTTPS e servico da aplicacao |
| Caixa | Computador do operador | Somente o MSI `DeTecPDV`, liberado para aquele terminal |

Nao instale o MSI do PDV no servidor administrativo e nao instale o projeto
aberto nos caixas.

## 2. Antes de iniciar

- [ ] Definir se a empresa usara modo local, hibrido ou nuvem.
- [ ] Reservar IP fixo ou nome DNS para o servidor da loja.
- [ ] Criar banco PostgreSQL e usuario exclusivo do ERP.
- [ ] Separar uma pasta para codigo, outra para dados, midia, logs e backups.
- [ ] Obter o pacote da versao aprovada, seu manifesto e SHA-256.
- [ ] Guardar fora do servidor as senhas de banco, `SECRET_KEY`, certificado fiscal e credenciais de integracoes.
- [ ] Confirmar que o firewall permite somente a rede interna acessar a porta do ERP.

Em producao, use o pacote de distribuicao aprovado. O GitHub e apropriado para
desenvolvimento e para a maquina de build; nao e a forma recomendada de entregar
o sistema ao cliente.

## 3. Servidor local Windows

### Instalacao guiada recomendada

Depois de instalar Python, PostgreSQL e obter o WinSW oficial, utilize o
bootstrap `scripts\\install_detech_server.ps1`. Ele configura o ambiente, banco,
servico Windows e regra de firewall da rede privada em uma unica execucao. O
roteiro completo esta em `docs\\INSTALADOR_AUTOMATICO_DETEC_SERVER.md`.

### Baixar e preparar

- [ ] Instalar Python 3.12 x64.
- [ ] Instalar PostgreSQL 16 ou versao homologada, incluindo `pg_dump` e `pg_restore`.
- [ ] Baixar o ZIP `DeigoVarejoServidorLocal`, o arquivo `.manifest.json` e o SHA-256 publicados.
- [ ] Baixar o WinSW x64 de fonte oficial e registrar o SHA-256 conferido.
- [ ] Extrair o ZIP em uma pasta somente do servidor, por exemplo `C:\DeigoVarejo\app`.

No PowerShell, dentro da pasta extraida:

```powershell
Copy-Item .env.example .env
notepad .env
```

No arquivo `.env`, ao menos ajuste:

```text
DJANGO_ENV=production
DEBUG=false
SECRET_KEY=uma-chave-longa-e-exclusiva
# Gere uma vez no servidor: python -c "import secrets; print(secrets.token_urlsafe(48))"
FISCAL_CERTIFICATE_KEY=uma-chave-fiscal-longa-e-exclusiva
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.2.65,NOME_INTERNO  # troque 192.168.2.65 pelo IPv4 privado exibido no servidor
CSRF_TRUSTED_ORIGINS=http://192.168.2.65:8001  # troque pelo IPv4 e porta reais
POSTGRES_DB=supermercado
POSTGRES_USER=deigo_erp
POSTGRES_PASSWORD=senha-exclusiva-do-banco
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
PDV_DESKTOP_VERSION=0.1.5
PDV_DESKTOP_MIN_VERSION=0.1.5
PDV_DESKTOP_INSTALLER_PATH=artifacts/DeTecPDV.exe
```

### Instalar dependencias e banco

```powershell
.\scripts\setup_local.ps1 -Python "C:\Caminho\Para\Python312\python.exe"
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py check
```

### Primeiro teste manual

Use somente para conferir antes de registrar o servico:

```powershell
.\scripts\run_local_server.ps1 -Bind 127.0.0.1 -Port 8000
```

Abra `http://127.0.0.1:8000/login/`, faça login e encerre com `Ctrl+C`.
Nao use `runserver` ou uma janela PowerShell aberta como servico permanente.

### Registrar o servico Windows

Abra PowerShell como administrador e execute:

```powershell
.\scripts\install_local_server_service.ps1 `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -ExpectedSha256 "COLE_O_SHA256_DO_WINSW" `
  -Bind 0.0.0.0 `
  -Port 8000 `
  -DatabaseEngine PostgreSQL

.\scripts\test_local_server_service.ps1
```

- [ ] Copiar o IPv4 privado exibido no servidor e confirmar que `http://192.168.2.65:8001/login/` abre em outro computador, substituindo o IP do exemplo pelo IP real.
- [ ] Configurar e testar backup: `./scripts/backup_local.ps1 -ValidarSomente`; confirmar `evidencias_fiscais_integras=true`, verificar no painel exclusivo do Master o estado e horário da integridade fiscal, proteger `fiscal-evidence-anchor-latest.json` e testar também mídia vazia para confirmar que a entrada `media/` permanece restaurável.
- [ ] Registrar o agendamento de backup: `./scripts/register_backup_task.ps1 -Horario 02:30 -RetencaoDias 15`.
- [ ] Se houver NAS, rede ou disco externo, configurar `LOCAL_BACKUP_SECONDARY_DIR`, confirmar o destino externo, executar uma cópia AES-256 e conferir que os SHA-256 primário e secundário são iguais sob a conta `SYSTEM`.
- [ ] Entrar como Master em Sistema > Backup, confirmar o histórico sanitizado de sucesso e simular uma falha controlada para verificar a pendência alta sem exposição de caminho, senha ou nome de rede.
- [ ] Após homologar o agendamento, definir `LOCAL_BACKUP_MAX_AGE_HOURS=36`, confirmar o estado “Em dia” e testar em base controlada que ausência ou atraso do último sucesso gera pendência alta somente ao Master.
- [ ] Executar `python manage.py verificar_pos_implantacao --json` sem substituir o prazo e confirmar `politica_contrato=backup_age_policy_v1`, origem `ambiente`, o mesmo limite exibido ao Master e `validacao.contrato=local_backup_package_validation_v1` com SHA-256, estrutura, contrato do backup, banco e âncora fiscal válidos; com política `0`, pacote adulterado/incompatível ou AES-256 sem a senha operacional, o aceite deve permanecer bloqueado.
- [ ] Executar `.\scripts\restore_local_backup.ps1 -BackupPath backup.zip.aes -EnsaiarIsolado` com a senha no ambiente protegido e arquivar o JSON `local_restore_rehearsal_v1`; confirmar integridade SQLite antes/depois, migrations, Django check e âncora fiscal, com `servico_alterado=false` e `dados_ativos_alterados=false`. Para PostgreSQL, preparar banco vazio `deigo_rehearsal_*`, configurar as variáveis `RESTORE_REHEARSAL_POSTGRES_*` no processo protegido e executar com `-ConfirmarBancoPostgresTemporario`; confirmar transação única, banco diferente da origem, ausência de `--clean` e preservar o alvo para inspeção antes do descarte manual autorizado.
- [ ] Na máquina de build, confirmar que `package_detech_server_offline.ps1` executou `detech_server_offline_package_validation_v2`, promoveu o ZIP temporário somente após aprovação e gerou o SHA-256; uma falha não pode substituir o artefato anterior.
- [ ] Publicar com `publish_detech_server_offline.ps1`, confirmar validação da origem e da cópia, checksum vinculado ao nome final e ausência de `.uploading-*`/`.rollback-*`; simular falha controlada e confirmar preservação da mídia anterior.
- [ ] Na Central, confirmar `detech_server_offline_publication_validation_v1`: sidecar encontrado, hash válido, nome vinculado e publicação liberada; remover ou adulterar o sidecar deve bloquear somente o download offline, sem depender do pacote técnico separado.
- [ ] Antes de gerar as evidências, o Master deve escolher **com rede** ou **offline**. Confirmar `local_installation_media_policy_v1`: com rede, a mídia pendente é apenas recomendação; offline, `midia_offline_exigida=true` e prontidão/dossiê/aceite devem permanecer bloqueados sem ZIP + SHA-256 íntegros.
- [ ] Antes de copiar a mídia para a máquina limpa, confirmar no Master que o instalador offline passou pelo contrato `detech_server_offline_package_validation_v2`: componentes obrigatórios, ZIP interno do servidor, wheelhouse `.whl`, aplicativos, manifestos, hashes, tamanhos e ausência de duplicidades ou arquivos não declarados.
- [ ] Homologar a maquina limpa e registrar a evidencia na Central do Servidor Local.

## 4. Servidor Linux central/nuvem

O servidor Linux normalmente hospeda a central/nuvem. O app PDV continua sendo
instalado somente nos caixas Windows. Use uma distribuicao Linux suportada pela
empresa, PostgreSQL e HTTPS com proxy reverso.

Exemplo para Ubuntu/Debian (ajuste a versao do Python conforme sua distribuicao):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql nginx unzip
sudo adduser --system --group --home /opt/deigo-varejo deigoerp
sudo mkdir -p /opt/deigo-varejo/app /var/lib/deigo-varejo/{media,static,logs}
sudo chown -R deigoerp:deigoerp /opt/deigo-varejo /var/lib/deigo-varejo
```

- [ ] Copiar o pacote aprovado para `/opt/deigo-varejo/app`; nao fazer `git clone` na maquina do cliente.
- [ ] Extrair o pacote, criar `.env` a partir de `.env.example` e preencher PostgreSQL, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e HTTPS.
- [ ] Criar o ambiente e instalar dependencias:

```bash
sudo -u deigoerp python3 -m venv /opt/deigo-varejo/app/.venv
sudo -u deigoerp /opt/deigo-varejo/app/.venv/bin/pip install -r /opt/deigo-varejo/app/requirements.txt
cd /opt/deigo-varejo/app
sudo -u deigoerp .venv/bin/python manage.py migrate --noinput
sudo -u deigoerp .venv/bin/python manage.py collectstatic --noinput
sudo -u deigoerp .venv/bin/python manage.py createsuperuser
sudo -u deigoerp .venv/bin/python manage.py check
```

- [ ] Criar um servico `systemd` para executar Waitress ou Gunicorn como `deigoerp`.
- [ ] Configurar Nginx como proxy reverso e emitir certificado HTTPS.
- [ ] Liberar somente portas 80/443 publicamente; PostgreSQL deve permanecer interno.
- [ ] Validar o login pelo dominio HTTPS e executar backup/restore em ambiente de teste.

Nao exponha `python manage.py runserver 0.0.0.0:8000` em Linux de producao. Ele
serve apenas para desenvolvimento.

## 5. Instalar um caixa PDV

- [ ] No servidor, confirmar que o MSI da mesma versao esta publicado em `artifacts/DeTecPDV.msi` com `.version.json` valido.
- [ ] Criar o terminal e liberar a licenca no ERP como admin master.
- [ ] Baixar o MSI pelo painel **Configuracoes > PDV desktop**.
- [ ] Instalar no Windows do caixa e informar servidor, identificador do terminal e chave de ativacao.
- [ ] Testar login, leitura de codigo de barras, impressora, fechamento de caixa e contingencia de conexao.
- [ ] Configurar balanca, gaveta e TEF apenas depois de homologar o equipamento real.

## 6. Validacao de entrega

- [ ] `manage.py check` sem erros.
- [ ] Migrations aplicadas.
- [ ] Backup criado e validado.
- [ ] Acesso de administrador e operador testado com as permissões corretas.
- [ ] PDV instalado somente em terminal licenciado.
- [ ] Documento fiscal, TEF, impressoras e balanca mantidos em modo de homologacao ate a configuracao real ser aprovada.
- [ ] Registrar a homologacao tecnica da versao:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_homologacao_servidor_local --estrito
```

O comando acima deve ser executado depois que a evidencia da maquina limpa for
registrada. Antes disso ele deve bloquear a liberacao, que e o comportamento
correto.
