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

## 5. Preparacao do Windows

1. Aplicar atualizacoes do Windows e reiniciar.
2. Definir IP fixo e nome da maquina.
3. Ativar BitLocker e guardar a chave de recuperacao em local controlado.
4. Criar a pasta de instalacao aprovada.
5. Reservar `%ProgramData%\DeigoVarejo` para dados, servicos, logs e backups.
6. Liberar no firewall somente a porta HTTP/HTTPS interna usada pelo ERP.
7. Confirmar que os caixas resolvem o IP ou DNS do servidor.
8. Registrar data, tecnico, maquina, numero de serie e hash do pacote instalado.

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
ALLOWED_HOSTS=127.0.0.1,localhost,IP_DO_SERVIDOR,NOME_DNS
CSRF_TRUSTED_ORIGINS=http://IP_DO_SERVIDOR:8000

POSTGRES_DB=deigo_varejo
POSTGRES_USER=deigo_varejo_app
POSTGRES_PASSWORD=SENHA_EXCLUSIVA
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=60

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
- revisar NCM, CEST, CFOP, CSOSN/CST e aliquotas dos produtos;
- configurar CSC e identificador quando NFC-e exigir;
- homologar autorizacao, rejeicao, contingencia, cancelamento e reimpressao;
- configurar as URLs oficiais do QR Code e da consulta NFC-e por UF/ambiente;
- configurar e homologar `FISCAL_SEFAZ_ADAPTER`, schema e certificado A1;
- manter `FISCAL_AUTO_TRANSMIT_ENABLED=False` ate a homologacao ser aprovada;
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
producao, habilitar AES-256 e manter copia externa protegida.

Validar restauracao sem alterar dados:

```powershell
.\scripts\restore_local_backup.ps1 `
  -BackupPath "D:\DeigoVarejo\Backups\backup.zip.aes" `
  -ValidarSomente
```

Antes da entrega, restaurar uma copia em ambiente separado, executar healthcheck e
conferir dados operacionais. Nunca testar restauracao pela primeira vez no servidor
de producao.

## 15. Sincronizacao e licenciamento

No modo hibrido:

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
- logs, auditoria, data/hora e espaco em disco.

Falha critica impede o aceite e a entrada em producao.

## 17. Entrega ao cliente

Entregar:

- URL interna do ERP;
- usuarios iniciais, sem revelar credenciais da Deigo Tecnologia;
- lista de terminais e dispositivos homologados;
- horario de backup e local da copia externa;
- contato de suporte e janela de manutencao;
- versao, hash e data da instalacao;
- termo de aceite assinado;
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
