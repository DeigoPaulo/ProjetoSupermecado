# PDV Desktop

Shell Windows do PDV operacional. Ele abre a mesma interface Django usada em
`/pdv/` dentro de uma WebView e reserva uma ponte local para impressora, gaveta,
balança e TEF.

A ponte `window.SupermercadoDesktop.printSale(payload)` imprime venda,
`window.SupermercadoDesktop.printLabels(payload)` gera etiquetas ZPL, EPL, PPLA
ou PPLB e envia o lote diretamente ao spooler Windows em modo RAW. A homologacao
fisica por modelo de impressora continua obrigatoria antes de ativar em producao. O agente exige o contrato `label_print_v1`, impressora configurada, código de barras ou SKU em todos os itens e limita cada lote a 500 produtos, 100 cópias por produto e 2.000 etiquetas. Sucesso e falha geram evento local `etiquetas` com impressora, linguagem, itens, cópias e bytes para diagnóstico central, sem copiar o conteúdo comercial completo para o log.

A ponte `window.SupermercadoDesktop.processPayment(payload)` usa um contrato unico para TEF. O adaptador local configurado em `config.json` recebe pagamento, consulta e estorno, independentemente de o provedor ser SiTef, Cielo, Stone, Getnet, PagBank, Rede ou outro. O driver deve devolver estado, transacao, NSU e autorizacao completos; resposta incompleta ou driver ausente falha de forma fechada e nunca libera a venda.

O adaptador `SIMULADOR` existe somente para desenvolvimento. Ele funciona apenas quando o servidor publica `simulador_permitido=true`, controlado por `PDV_TEF_SIMULATOR_ENABLED`; em producao essa variavel deve permanecer falsa. PIX retorna QR Code pendente e exige consultas ate a confirmacao. Cada tentativa grava eventos locais `tef` ou `tef_estorno` em `devices.log.jsonl`. Drivers reais sao pacotes locais homologados e selecionados no formato `pacote.modulo:fabrica`; credenciais e parametros do fornecedor ficam somente na configuracao protegida da maquina.

A gaveta usa o contrato `pdv_cash_drawer_v1` recebido no bootstrap. A ponte
`window.SupermercadoDesktop.openCashDrawer(payload)` envia o pulso ESC/POS pela
impressora configurada e grava diagnóstico local quando a gaveta abre, falha ou
esta desabilitada. Gaveta desabilitada ou sem impressora retorna aviso e não deve
bloquear a venda.

A balança usa o contrato `pdv_scale_v1` recebido no bootstrap do terminal. A ponte
local expõe `scaleConfig()` e `readScale()` com fallback manual. O driver genérico
suporta Serial RS-232/USB via `pyserial`, TCP/IP no formato `endereço:porta` e
arquivo texto local. A leitura tem timeout e tamanho limitados, normaliza decimal
e rejeita peso instável, zerado, negativo ou em sobrecarga. Protocolos que exigem
comandos proprietários ainda precisam de um adaptador validado com o fabricante.
Para homologar a tela sem equipamento, use
`SUPERMERCADO_PDV_PESO_SIMULADO=1,250`. Falhas e retornos manuais da balança são
gravados em `devices.log.jsonl` na pasta local do terminal e podem ser
consultados pela ponte `window.SupermercadoDesktop.deviceLogs()`. Na inicialização,
o app tenta enviar os eventos ainda não sincronizados para
`/pdv/api/terminal/device-events/`; se o servidor estiver indisponível, os eventos
permanecem locais e são reenviados depois da reconexão.

A fila usa o contrato `pdv_device_event_queue_v1`. Cada evento possui ID, os
lotes seguem do mais antigo ao mais novo e o cursor só avança após confirmação
integral do servidor. Reenvios são deduplicados por terminal. Quando o histórico
cresce, a compactação mantém uma janela dos confirmados e todos os pendentes.
A sincronização continua durante todo o turno em uma thread exclusiva. O intervalo
padrão é 60 segundos e pode ser ajustado em `diagnostico_sync_interval_seconds`
entre 15 e 3.600 segundos. A thread para junto com a janela do PDV.

A Central do App expõe `window.SupermercadoDesktop.runDeviceDiagnostics(opcoes)`
com o contrato `pdv_device_homologation_v1`. O roteiro consolida impressoras,
balança, gaveta e TEF e grava a evidência em `devices.log.jsonl`. Por padrão ele
é não invasivo: não imprime, não abre gaveta e não cria cobrança. A leitura da
balança e o pulso da gaveta exigem seleção explícita na tela; o pulso ainda pede
confirmação do operador.

## Desenvolvimento

1. Instale as dependencias com `pip install -r requirements.txt`.
2. Execute `python app.py`.
3. Na primeira abertura, informe servidor, identificador e chave do terminal.

O app valida a licença em `/pdv/api/terminal/bootstrap/` antes de abrir o PDV.
A ativação é validada antes de ser salva. No Windows, a configuração fica em
`%LOCALAPPDATA%\DeTecPDV\config.json` (a configuracao legada em `%LOCALAPPDATA%\SupermercadoPDV` e migrada automaticamente); para reconfigurar, execute o app
com `--configurar`. A chave fica apenas na máquina do caixa, protegida pelo DPAPI
do usuário do Windows, e não é versionada. Configurações antigas com chave em texto
são migradas automaticamente na primeira abertura; copiar somente o arquivo para outro
usuário não permite recuperar a credencial. Os parâmetros locais do adaptador TEF em`r`n`tef.configuracao` recebem a mesma proteção e existem em texto apenas na memória do app.

O app mantém uma única instância por identidade de terminal na sessão do Windows.
Uma segunda abertura do mesmo caixa é bloqueada por mutex nomeado; terminais diferentes
podem operar na mesma máquina para suporte/homologação e o bloqueio é liberado ao fechar. O modo `--configurar` também respeita o bloqueio da identidade atual.
### Contingência de conexão

Depois de uma validação online, o app mantém em `bootstrap_cache.json` somente a
configuração operacional recebida do servidor. Se a rede interna cair, ele não
abre uma página quebrada e não inicia venda com dados antigos: mostra uma tela
local de contingência com o terminal identificado e mantém vendas, pagamentos e
estoque bloqueados. `F5` ou `Enter` tenta validar novamente terminal, licença e
servidor; somente a resposta aprovada redireciona para `/pdv/`.

O cache autorizado vale 24 horas por padrão. O limite pode ser reduzido ou
ampliado entre 1 e 168 horas com `offline_cache_max_hours` em `config.json`.
Cache vencido, ausente ou sem permissão de modo offline bloqueia a inicialização.
Uma recusa explícita do servidor nunca usa o cache como alternativa.

## Build Windows

O build usa Python 3.12 para manter compatibilidade com o PyInstaller fixado. Para gerar MSI, a máquina de build precisa também do .NET SDK 8 e do WiX Toolset 4 (dotnet tool install --global wix --version 4.0.6). Esses componentes são necessários somente na máquina que compila, não nos caixas que instalam o aplicativo.

Execute `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. O
executavel sera criado em `dist\DeTecPDV.exe`.

O instalador MSI usa WiX Toolset v4. Para gerar um pacote de desenvolvimento:

```powershell
.\build_msi.ps1 -Version 0.1.5
```

Para producao, assine primeiro o executavel e exija a assinatura durante o
empacotamento. O MSI tambem pode ser assinado no mesmo comando:

```powershell
.\build_msi.ps1 -Version 0.1.5 `
  -RequireSignedExecutable `
  -CertificateThumbprint "CERTIFICADO_SHA1"
```

O MSI instala por maquina em `Program Files`, cria atalhos no menu Iniciar e na
area de trabalho, permite upgrade de versao e remove os atalhos na
desinstalacao. O build grava um arquivo `.version.json` com versao, tamanho,
SHA-256 e situacao das assinaturas. A homologacao final ainda exige certificado
real e teste em uma maquina Windows limpa.

Depois do build e da assinatura, publique o MSI:

```powershell
.\publish_windows.ps1 -Version 0.1.5 -RequireSignature
```

O script prioriza o MSI da versao informada, confere o SHA-256 e publica o
arquivo de forma atomica em `artifacts\DeTecPDV.msi`, caminho padrao
usado pelo ERP. O parametro `-Source` permite publicar um artefato especifico e
`PDV_DESKTOP_INSTALLER_PATH` permite alterar o caminho no ambiente quando
necessario.

## Credencial NFC de supervisor

O botao Ler cartao das operacoes protegidas usa a ponte readSupervisorCredential no aplicativo desktop. No Windows, o agente consulta leitores NFC compativeis com PC/SC por winscard.dll e solicita o UID pelo comando APDU padrao. O identificador segue diretamente para o formulario e nao e gravado em devices.log.jsonl.

Se o leitor, cartao ou servico de Cartao Inteligente estiver indisponivel, o operador pode usar um leitor configurado como teclado ou informar login e senha. A liberacao continua sendo validada e auditada pelo servidor; o UID bruto nunca deve ser usado como senha ou registrado em suporte.

## Deploy do instalador no servidor

O servidor web nao executa nem recompila o MSI. Gere o pacote em uma maquina Windows e transfira estes dois arquivos para o diretorio de artefatos da aplicacao:

- `artifacts/DeTecPDV.msi`
- `artifacts/DeTecPDV.msi.version.json`

No ambiente do servidor, mantenha `PDV_DESKTOP_VERSION` igual a versao publicada e aponte `PDV_DESKTOP_INSTALLER_PATH` para o caminho absoluto do MSI. Exemplo Linux:

```env
PDV_DESKTOP_VERSION=0.1.5
PDV_DESKTOP_INSTALLER_PATH=/srv/deigo-varejo/artifacts/DeTecPDV.msi
PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER=false
```

A ultima opcao deve permanecer `true` em producao depois da contratacao do certificado de assinatura. O usuario do Gunicorn, Uvicorn ou servico Windows precisa de permissao de leitura no MSI e no manifesto. Em Docker, monte o diretorio `artifacts` como volume persistente somente leitura. Reinicie os processos Django depois de alterar a versao ou o caminho.

Nunca compile o PDV no servidor Linux. O build deve rodar no Windows com `build_windows.ps1`, `build_msi.ps1` e `publish_windows.ps1`; o resultado publicado e entao enviado ao servidor ou ao armazenamento de releases.
O empacotamento Windows sera feito a partir deste projeto separado. O ERP web
continua sendo a fonte unica da interface, dos atalhos e das regras de venda.

## Encerramento pelo teclado

No aplicativo instalado, `Ctrl+F5 (Ctrl+Q tambem aceito)` solicita o encerramento em qualquer tela carregada pelo shell desktop. O sistema pede confirmação antes de fechar porque formulários e operações ainda não salvas serão descartados. O atalho também funciona na ativação inicial e na contingência sem conexão; no navegador comum, o ERP não intercepta esse comando.