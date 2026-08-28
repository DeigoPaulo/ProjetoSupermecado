# Manual de Instalacao no Supermercado

## 1. Objetivo e responsabilidade

Este manual orienta o tecnico autorizado da Deigo Tecnologia na implantacao do
Deigo Varejo em uma matriz ou filial. Ele cobre servidor local, PostgreSQL, servico
Windows, licenciamento, PDVs, dispositivos, backup, validacao e entrega.

O cliente recebe acesso administrativo ao ERP conforme o contrato. O codigo-fonte,
o repositorio Git, as chaves privadas de assinatura e os segredos da central nao
fazem parte da instalacao.

## 2. Regra de distribuicao

Nunca instalar em cliente usando `git clone`, uma copia da pasta de desenvolvimento
ou um ZIP criado manualmente.

A instalacao comercial deve usar:

- pacote de producao gerado por commit Git limpo e rastreavel;
- manifesto de versao e checksum SHA-256;
- assinatura do commit e do artefato quando o pipeline definitivo estiver ativo;
- identificacao da empresa, filial e instalacao licenciada;
- pacote sem `.git`, testes, documentos internos, caches ou segredos;
- atualizacao publicada pela Central da Deigo Tecnologia.

Enquanto o pipeline endurecido e a assinatura definitiva nao forem homologados, a
instalacao deve ser tratada como ambiente de teste assistido, nao como producao.

## 3. Topologia que deve ser definida

Antes da visita, registrar:

- modo da empresa: local, hibrido ou nuvem com agente;
- matriz, filiais e quantidade de terminais contratados;
- computador que sera o servidor local;
- IP fixo, nome DNS interno e faixa da rede;
- quantidade de caixas e sistema operacional de cada um;
- impressoras, gavetas, balancas e provedores TEF;
- modelo fiscal, certificado A1 e CSC quando aplicavel;
- horario aprovado para parada e migracao;
- responsaveis do cliente e da Deigo Tecnologia;
- politica de backup, retencao e copia externa.

O PDV desktop acessa a API do servidor local. Nenhum caixa acessa diretamente o
PostgreSQL.

## 4. Requisitos do servidor

Recomendacao inicial para uma loja:

- Windows Server 2019 ou superior, ou Windows 11 Pro dedicado;
- processador de 4 nucleos ou mais;
- 16 GB de RAM ou mais;
- SSD com espaco para banco, midia, logs, backups e crescimento;
- IP fixo e horario do Windows sincronizado;
- PostgreSQL suportado pelo projeto e ferramentas cliente instaladas;
- acesso de administrador apenas para o tecnico autorizado;
- BitLocker com TPM quando disponivel;
- antivirus com exclusoes revisadas para banco e servico, sem desativar a protecao;
- nobreak e rotina de desligamento seguro;
- volume de backup diferente do volume principal sempre que possivel.

Nao expor PostgreSQL, WinSW ou a administracao do ERP diretamente na internet.
Em producao, publicar o ERP por proxy reverso HTTPS, inclusive na rede interna da loja.
O proxy deve encaminhar X-Forwarded-Proto=https; HTTP direto fica restrito ao
desenvolvimento e ao healthcheck local controlado.

## 5. Preparacao do Windows

1. Aplicar atualizacoes do Windows e reiniciar.
2. Definir IP fixo e nome da maquina.
3. Ativar BitLocker e guardar a chave de recuperacao em local controlado.
4. Criar a pasta de instalacao aprovada.
5. Reservar `%ProgramData%\DeigoVarejo` para dados, servicos, logs e backups.
6. Liberar no firewall somente a porta HTTP/HTTPS interna usada pelo ERP.
7. Confirmar que os caixas resolvem o IP ou DNS do servidor.
8. Registrar data, tecnico, maquina, numero de serie e hash do pacote instalado.

### 5.1 Acesso pela rede interna

O endereco usado pelos outros computadores deve ser o IPv4 privado do adaptador
Ethernet ou Wi-Fi que possui gateway. Nao use enderecos de adaptadores Loopback,
VPN, TEF ou fiscais. O instalador sugere o endereco roteado, mas o tecnico deve
conferi-lo com `ipconfig` antes do aceite.

No PowerShell aberto como administrador, use o comando abaixo. Ele escolhe o
adaptador ativo que possui gateway e exibe o IPv4 privado encontrado:

```powershell
$porta = 8001
$configRede = Get-NetIPConfiguration |
  Where-Object { $_.NetAdapter.Status -eq "Up" -and $_.IPv4DefaultGateway -and $_.IPv4Address } |
  Select-Object -First 1

$interface = $configRede.InterfaceAlias
$ipServidor = $configRede.IPv4Address.IPAddress

Write-Host "Interface: $interface"
Write-Host "IP do servidor: $ipServidor"

Set-NetConnectionProfile -InterfaceAlias $interface -NetworkCategory Private

$regra = "DeTec Server - rede privada - porta $porta"
Get-NetFirewallRule -DisplayName $regra -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule `
  -DisplayName $regra `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort $porta `
  -Profile Private `
  -RemoteAddress LocalSubnet

Restart-Service DeigoVarejoServidorLocal
Get-Service DeigoVarejoServidorLocal
Invoke-WebRequest "http://${ipServidor}:$porta/login/" -UseBasicParsing
```

No outro computador da mesma rede, copie o numero exibido em `IP do servidor`.
O exemplo abaixo usa `192.168.2.65`; substitua-o quando a loja utilizar outro IP:

```powershell
$ipServidor = "192.168.2.65"
Test-NetConnection $ipServidor -Port 8001
```

Se `TcpTestSucceeded` for `True`, abra no navegador:
`http://192.168.2.65:8001/login/`, substituindo pelo IP real da instalacao.
Nunca execute literalmente `Test-NetConnection IP_DO_SERVIDOR`, pois esse texto
era apenas um marcador e nao e um nome de computador valido.

Os clientes devem estar na mesma rede interna e fora de uma rede de convidados
com isolamento entre dispositivos. Reserve o IP no roteador ou configure IP fixo.
Ao alterar `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` ou qualquer outra chave do `.env`
instalado, reinicie `DeigoVarejoServidorLocal` para aplicar a configuracao.

### 5.2 HTTPS e acesso remoto

Nao exponha a porta `8001` diretamente na internet. Em producao, use um dominio
proprio com proxy reverso HTTPS, como Caddy, ou uma VPN/tunel corporativo. O proxy
recebe HTTPS na porta 443 e encaminha internamente para `127.0.0.1:8001`.

Exemplo de `Caddyfile`:

```caddyfile
erp.exemplo.com.br {
    reverse_proxy 127.0.0.1:8001
    encode zstd gzip
}
```

Depois de validar dominio, DNS e certificado, configure o `.env`:

```dotenv
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.2.65,erp.exemplo.com.br  # substitua pelo IPv4 privado real
CSRF_TRUSTED_ORIGINS=https://erp.exemplo.com.br
USE_X_FORWARDED_PROTO=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=False
```

Nesse modelo o proxy redireciona HTTP para HTTPS. O PostgreSQL continua restrito
ao servidor; nunca abra a porta `5432` na rede ou na internet. Para acesso remoto,
registre dominio, certificado, regras do proxy, responsavel e teste externo no
dossie da implantacao.

## 6. PostgreSQL

PostgreSQL e o banco padrao do servidor de producao. SQLite fica restrito a
desenvolvimento, testes ou instalacao simplificada explicitamente aprovada.

Instalar o servidor PostgreSQL e os componentes de linha de comando. Confirmar:

```powershell
pg_dump --version
pg_restore --version
psql --version
```

Criar usuario e banco com nomes definidos na ficha da implantacao. Exemplo que deve
ser adaptado pelo tecnico:

```sql
CREATE ROLE deigo_varejo_app LOGIN PASSWORD 'SUBSTITUIR_POR_SENHA_FORTE';
CREATE DATABASE deigo_varejo OWNER deigo_varejo_app ENCODING 'UTF8';
```

Regras:

- nao usar o usuario `postgres` na aplicacao;
- aceitar conexoes somente do servidor da aplicacao;
- usar senha exclusiva por cliente;
- nao registrar a senha em chamados, capturas ou documentacao entregue;
- manter `pg_dump` e `pg_restore` compativeis com a versao principal do servidor.

## 7. Configuracao do ambiente

Criar o `.env` de producao a partir do modelo do pacote. Exemplo minimo:

```dotenv
DJANGO_ENV=production
DEBUG=false
SECRET_KEY=GERAR_UMA_CHAVE_EXCLUSIVA
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.2.65,NOME_DNS  # substitua pelo IPv4 privado real
CSRF_TRUSTED_ORIGINS=https://NOME_DNS

POSTGRES_DB=deigo_varejo
POSTGRES_USER=deigo_varejo_app
POSTGRES_PASSWORD=SENHA_EXCLUSIVA
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=60

SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
SECURE_SSL_REDIRECT=true
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=false
SECURE_HSTS_PRELOAD=false
USE_X_FORWARDED_PROTO=true

MEDIA_ROOT=C:\ProgramData\DeigoVarejo\Dados\media
STATIC_ROOT=C:\ProgramData\DeigoVarejo\Dados\staticfiles
LOG_DIR=C:\ProgramData\DeigoVarejo\Dados\logs
LOCAL_BACKUP_DIR=D:\DeigoVarejo\Backups
```

Quando as ferramentas nao estiverem no `PATH`, configurar:

```dotenv
POSTGRES_PG_DUMP_PATH=C:\Program Files\PostgreSQL\16\bin\pg_dump.exe
POSTGRES_PG_RESTORE_PATH=C:\Program Files\PostgreSQL\16\bin\pg_restore.exe
```

Aplicar ACL para que o `.env` seja legivel somente por administradores autorizados
e pela identidade do servico. Segredos nunca entram no Git.

## 8. Pre-validacao da aplicacao

No PowerShell administrativo, dentro do pacote instalado:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Qualquer erro interrompe a instalacao. Nao iniciar caixas enquanto migrations ou
healthcheck estiverem pendentes.

## 9. Instalacao do servico Windows

Usar um WinSW obtido de fonte oficial e conferir seu SHA-256:

```powershell
.\scripts\install_local_server_service.ps1 `
  -WinSWPath "C:\Instaladores\WinSW-x64.exe" `
  -ExpectedSha256 "HASH_SHA256_VALIDADO" `
  -Bind 0.0.0.0 `
  -Port 8000 `
  -DatabaseEngine PostgreSQL
```

O instalador deve:

- confirmar que o `.env` seleciona PostgreSQL;
- localizar `pg_dump` e `pg_restore`;
- executar check, migrations e arquivos estaticos;
- instalar `DeigoVarejoServidorLocal`;
- usar a conta virtual dedicada sem senha interativa;
- aplicar ACL minima;
- iniciar o servico e aprovar `/login/`.

Diagnostico:

```powershell
.\scripts\test_local_server_service.ps1
```

Reiniciar o Windows e repetir o diagnostico para comprovar inicio automatico.

## 10. Cadastro inicial

O super admin da Deigo Tecnologia deve:

1. cadastrar contrato, matriz e filiais contratadas;
2. definir o modo local, hibrido ou nuvem com agente;
3. cadastrar o administrador da empresa;
4. configurar quantidade de terminais licenciados;
5. gerar as credenciais de instalacao;
6. confirmar politica fiscal, sincronizacao e tolerancia de licenca;
7. registrar a versao instalada e o tecnico responsavel.

O administrador da empresa recebe apenas as telas e filiais permitidas pelo
contrato. Telas do super admin permanecem exclusivas da Deigo Tecnologia.

## 11. Instalacao dos PDVs

Para cada caixa:

1. cadastrar o terminal na filial correta;
2. definir nome, identificador, caixa e canal de atualizacao;
3. configurar TEF, impressora, gaveta e balanca;
4. liberar a licenca do terminal pelo super admin;
5. baixar o MSI publicado pela Central;
6. conferir versao, SHA-256 e assinatura quando exigida;
7. instalar como administrador;
8. informar servidor, identificador e chave de ativacao;
9. validar o bootstrap antes de iniciar o operador;
10. testar fechamento e reabertura do aplicativo.

Cada maquina recebe uma credencial propria. Nunca reutilizar a chave de outro caixa.
### Recuperação quando o PDV não abre

A partir da versão 0.1.13, quando o servidor recusar a credencial salva, o DeTec PDV não encerra silenciosamente: ele mostra o motivo e abre a tela de reativação com o servidor e o identificador atuais preenchidos.

Para forçar a reconfiguração manual no Windows:

```powershell
& "$env:USERPROFILE\Desktop\DeTecPDV.exe" --configurar
```

Use o endereço do ambiente que realmente operará o caixa:

- servidor instalado: `http://127.0.0.1:8001`;
- desenvolvimento: `http://127.0.0.1:8000`.

O terminal e a chave devem ser gerados nesse mesmo servidor. Bancos separados possuem credenciais separadas; uma chave emitida no `:8000` não autentica no `:8001`. Se a mensagem indicar bloqueio ou licença cancelada, não gere outra chave sem antes conferir a situação do terminal no painel do admin master.

## 12. Homologacao dos dispositivos

Executar a pre-homologacao da Central do App antes do primeiro turno.

### Impressora

- listar impressoras instaladas;
- selecionar a impressora correta por tipo de documento;
- imprimir pagina de teste;
- testar cupom, comprovante e reimpressao;
- confirmar largura, corte e acentuacao.

### Gaveta

- manter desabilitada quando a loja nao possui o equipamento;
- acionar somente com confirmacao explicita;
- testar abertura em dinheiro, suprimento e sangria;
- confirmar que falha da gaveta nao perde a venda.

### Balanca

- registrar fabricante, modelo, protocolo e porta;
- validar zero, estabilidade, peso conhecido e sobrecarga;
- conferir tres casas para quilogramas;
- manter digitacao manual como contingencia autorizada.

### TEF

- desativar o simulador em producao;
- homologar credito, debito, PIX, recusa, timeout e estorno;
- confirmar NSU, autorizacao e idempotencia;
- validar dois pagamentos sequenciais na mesma venda;
- confirmar que venda nao finaliza com transacao pendente.

## 13. Fiscal

Antes de emitir documento real:

- conferir CNPJ, IE, regime e endereco da filial;
- validar serie, numero inicial, ambiente e natureza de operacao;
- instalar certificado A1 e proteger sua senha;
- gerar uma unica `FISCAL_CERTIFICATE_KEY` forte no servidor com `python -c "import secrets; print(secrets.token_urlsafe(48))"`;
- guardar essa chave fora do Git e do banco; ela criptografa o arquivo e a senha do A1 cadastrados no ERP;
- nao trocar `FISCAL_CERTIFICATE_KEY` depois de cadastrar certificados, pois os dados protegidos anteriormente nao poderao mais ser abertos;
- obter o certificado digital A1 (`.pfx` ou `.p12`) da empresa junto a uma Autoridade Certificadora ICP-Brasil; essa chave interna nao substitui o certificado;
- revisar NCM, CEST, CFOP, CSOSN/CST e aliquotas dos produtos;
- configurar CSC e identificador quando NFC-e exigir;
- homologar autorizacao, rejeicao, contingencia, cancelamento e reimpressao;
- configurar as URLs oficiais do QR Code e da consulta NFC-e por UF/ambiente;
- configurar e homologar `FISCAL_SEFAZ_ADAPTER`, schema e certificado A1;
- manter `FISCAL_AUTO_TRANSMIT_ENABLED=False` ate a homologacao ser aprovada;
- ajustar `FISCAL_AUTO_QUERY_MAX_ATTEMPTS` somente com o provedor fiscal; o padrão limita a 12 consultas automáticas antes de exigir análise manual, sem retransmitir a nota;
- manter `FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS=2` ou valor superior; a NFC-e offline nunca deve ser retransmitida após uma única resposta de ausência;
- depois da aprovacao, habilitar a fila e registrar `scripts/register_fiscal_transmission_task.ps1` com conta de servico dedicada;
- conferir na Central Fiscal documentos elegiveis, leases ativos, retentativas e tentativas esgotadas;
- quando uma rejeicao ou falha esgotar as tentativas, corrigir primeiro o cadastro de origem e usar `Recolocar na fila` no detalhe do documento;
- informar um motivo operacional: a acao regenera o XML, invalida a assinatura anterior, reinicia as tentativas e grava usuario, IP e estado anterior na auditoria;
- nunca recolocar na fila documento autorizado, cancelado ou inutilizado; nesses casos, seguir o fluxo fiscal de evento ou cancelamento aplicavel;
- usar `--simular-homologacao` somente em ambiente de teste, nunca na tarefa de producao;
- manter emissao real bloqueada ate a aprovacao fiscal do cliente.

## 14. Backup e restauracao

Validar as fontes:

```powershell
.\scripts\backup_local.ps1 -ValidarSomente
```

Gerar e conferir um backup:

```powershell
.\scripts\backup_local.ps1 -IncluirLogs
```

Registrar a tarefa diaria:

```powershell
.\scripts\register_backup_task.ps1 -Horario 02:30 -RetencaoDias 30
```

O backup PostgreSQL deve conter `database.dump`, manifesto, midia e SHA-256. Em
producao, habilitar AES-256 e configurar `LOCAL_BACKUP_SECONDARY_DIR` para NAS, rede ou disco externo. Confirmar o destino com `LOCAL_BACKUP_SECONDARY_CONFIRMED=True`, testar a igualdade SHA-256 e garantir que a conta `SYSTEM` possua acesso sem armazenar senha no comando. Depois da primeira execução real, o Master deve conferir em Sistema > Backup o registro de sucesso, criptografia, destino secundário e SHA-256 validado; nenhum caminho ou segredo deve aparecer. Somente depois desse aceite, configurar `LOCAL_BACKUP_MAX_AGE_HOURS=36` e confirmar que o painel muda de “Em dia” para “Atrasado” quando o último sucesso ultrapassa o prazo; `0` mantém o monitor desligado. Nesse estado, o aceite pós-instalação permanece bloqueado; painel, comando e evidência só ficam alinhados e liberáveis depois que a política for ativada. O comando também aplica `local_backup_package_validation_v1` ao pacote mais recente: exige o `.sha256` correspondente, recalcula a integridade, testa integralmente o ZIP e confere contrato, banco e âncora fiscal. Para instalação que remove o ZIP aberto e conserva apenas `.zip.aes`, disponibilize `BACKUP_ENCRYPTION_PASSPHRASE` à conta do serviço; sem ela, o pacote criptografado não libera o aceite.

Validar restauracao sem alterar dados:

```powershell
.\scripts\restore_local_backup.ps1 `
  -BackupPath "D:\DeigoVarejo\Backups\backup.zip.aes" `
  -ValidarSomente
```

Em SQLite, antes da janela real, repetir o comando com `-EnsaiarIsolado`. O JSON `local_restore_rehearsal_v1` deve confirmar integridade antes/depois, migrations, Django check, cadeia fiscal e ausência de alteração do serviço ou dos dados ativos. Em PostgreSQL, preparar um banco vazio `deigo_rehearsal_*`, fornecer host, usuário e senha pelas variáveis `RESTORE_REHEARSAL_POSTGRES_*` e executar também `-ConfirmarBancoPostgresTemporario`. O script não cria nem remove o banco, recusa qualquer objeto pré-existente ou coincidência com a origem e usa `pg_restore --single-transaction`; preserve o alvo para inspeção e descarte-o somente em procedimento manual autorizado.

Antes da entrega, restaurar uma copia em ambiente separado, executar healthcheck e
conferir dados operacionais. Nunca testar restauracao pela primeira vez no servidor
de producao.

## 15. Sincronizacao e licenciamento

No modo hibrido:

No arquivo de ambiente do servidor local e da Central, configure uma credencial exclusiva por CNPJ:

```env
SINCRONIZACAO_TOKENS_EMPRESA_JSON={"00.000.000/0001-00":"segredo-longo-e-exclusivo-da-empresa"}

Para trocar a credencial sem interromper a loja, publique primeiro a configuração de rotação nos dois lados. O primeiro valor é sempre usado para novos envios, e os anteriores são aceitos apenas temporariamente:

    SINCRONIZACAO_TOKENS_EMPRESA_JSON={"00.000.000/0001-00":{"atual":"novo-segredo-exclusivo","anteriores":["segredo-anterior"]}}

Depois que todos os servidores locais estiverem enviando com o token atual, remova `anteriores`. O diagnóstico marca empresas que ainda estão nessa janela de rotação e nunca exibe os segredos.

SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=false
SINCRONIZACAO_MAX_EVENTO_BYTES=1048576
```

O token global compartilhado é apenas uma contingência de migração e não deve permanecer habilitado na produção.

```powershell
.\scripts\register_sync_task.ps1 -IntervaloMinutos 1
```

Confirmar:

- conexao de saida HTTPS para a Central;
- concessao de licenca valida;
- operacao local durante queda de internet;
- retomada sem duplicar eventos;
- reconciliacao de liberacao offline;
- alertas de vencimento e regularizacao;
- bloqueio comercial sem corromper ou apagar dados do cliente.

## 16. Testes de aceite

Executar e registrar:

- login do super admin, admin da empresa, gerente e operador;
- isolamento entre empresas e filiais;
- cadastro e consulta de produto;
- entrada de compra e atualizacao do estoque;
- abertura, suprimento, sangria, fechamento e conferencia de caixa;
- venda avulsa e identificada;
- pagamento em dinheiro, cartao e PIX;
- cancelamento, estorno autorizado e reimpressao;
- emissao fiscal homologada;
- reinicio do servidor e dos PDVs;
- queda de internet e retorno;
- backup automatico e restauracao em ambiente separado;
- logs, auditoria, data/hora e espaco em disco;
- dossie de implantacao com SHA-256 validado em modo estrito.

~~~powershell
.\.venv\Scripts\python.exe manage.py gerar_dossie_implantacao --perfil servidor-local --producao --saida artifacts\dossie_implantacao.json
.\.venv\Scripts\python.exe manage.py verificar_dossie_implantacao artifacts\dossie_implantacao.json --estrito
.\.venv\Scripts\python.exe manage.py verificar_pos_implantacao --estrito
.\.venv\Scripts\python.exe manage.py gerar_evidencia_aceite --dossie artifacts\dossie_implantacao.json --saida artifacts\evidencia_aceite.json --estrito
~~~

Falha critica ou dossie nao liberavel impede o aceite e a entrada em producao.

Como alternativa aos comandos, o super admin pode acessar **Sistema > Servidor local** e escolher **Evidências com rede** ou **Evidências offline**. O ZIP gerado contém o dossiê, a evidência de aceite e seus arquivos SHA-256; o evento e a política escolhida ficam registrados na auditoria. No modo com rede, a ausência da mídia offline é recomendação. No modo offline, o contrato `local_installation_media_policy_v1` exige ZIP e SHA-256 publicados e íntegros, bloqueando prontidão e aceite enquanto houver pendência. O pacote de evidências continua sendo gerado quando houver bloqueios, para documentar as correções necessárias antes da liberação.

Na máquina de build, o empacotador deve concluir `detech_server_offline_package_validation_v2` antes de promover o ZIP e criar seu SHA-256; falha não pode substituir a última mídia válida. Publique com `publish_detech_server_offline.ps1`: ele revalida origem e cópia, vincula o checksum ao nome final e restaura automaticamente a publicação anterior em falha. Antes de transportar a mídia, confirme no Master que `detech_server_offline_publication_validation_v1` aprovou presença, hash e nome do `.zip.sha256`. Use somente o instalador offline liberado pelo Master após `detech_server_offline_package_validation_v2`. O aceite confere servidor, runtime, wheelhouse, PostgreSQL, WinSW, iniciador, apps e manifestos, além dos ZIPs internos e de arquivos duplicados ou não declarados; falha mantém o download bloqueado antes de qualquer mudança na máquina.

Após executar os testes em uma máquina limpa, registre o resultado em **Sistema > Servidor local > Homologação em máquina limpa**. Informe a máquina, o sistema operacional e a versão do artefato; envie **evidencia_aceite.json** e o arquivo **.sha256** produzido junto com ela. O sistema compara o checksum, valida contrato, perfil, alvo de produção, diagnóstico pós-instalação e flags de segurança, e calcula o hash sem entrada manual. Uma aprovação exige evidência liberável e só vale para a versão vigente do servidor; após publicar uma nova versão, a tela sinaliza a homologação anterior como desatualizada. Registros criados antes do roteiro de testes críticos aparecem como incompletos e devem ser refeitos uma vez. Reprovações exigem a descrição da falha e da correção necessária; o sistema impede reutilizar a mesma evidência e registra o responsável na auditoria.


### Verificacao automatica da versao homologada

Confirme a homologacao da mesma versao que sera instalada:

~~~powershell
python manage.py verificar_homologacao_servidor_local --versao 1.2.0 --estrito
~~~

Nao prossiga se o comando informar que a versao esta bloqueada. O diagnostico
usa o mesmo registro e o mesmo checklist critico exibidos na tela **Servidor
local** do ERP.

## 17. Entrega ao cliente

Entregar:

- URL interna do ERP;
- usuarios iniciais, sem revelar credenciais da Deigo Tecnologia;
- lista de terminais e dispositivos homologados;
- horario de backup e local da copia externa;
- contato de suporte e janela de manutencao;
- versao, hash e data da instalacao;
- termo de aceite assinado;
- evidencia_aceite.json e seu SHA-256 anexados ao termo;
- orientacao para nao alterar servicos, banco ou arquivos da instalacao.

Nao entregar repositorio, codigo-fonte, chaves privadas, token central, certificado
de assinatura ou senha tecnica interna.

## 18. Atualizacao e rollback

Validar o pacote antes da janela:

```powershell
.\scripts\update_local_server.ps1 `
  -PackagePath "C:\Instaladores\DeigoVarejoServidorLocal.zip" `
  -RequireSignedCommit `
  -ValidarSomente
```

Atualizacoes devem usar backup anterior, janela aprovada, migrations revisadas e
healthcheck. Em PostgreSQL, migrations destrutivas exigem plano assistido de
reversao e aprovacao tecnica.

## 19. Registro da implantacao

O chamado ou ordem de servico deve registrar:

- cliente, matriz, filial e CNPJ;
- versao do servidor e dos PDVs;
- hashes dos pacotes;
- tecnico e data/hora;
- topologia e enderecos internos;
- versao PostgreSQL;
- terminais e dispositivos;
- resultado de cada teste;
- pendencias aceitas;
- backup inicial e teste de restauracao;
- assinatura do responsavel da loja e da Deigo Tecnologia.

Este documento deve ser revisado a cada mudanca no instalador, licenciamento,
PostgreSQL, fiscal, TEF ou politica de distribuicao.
