# PDV Desktop

Shell Windows do PDV operacional. Ele abre a mesma interface Django usada em
`/pdv/` dentro de uma WebView e reserva uma ponte local para impressora, gaveta,
balança e TEF.

A ponte `window.SupermercadoDesktop.printSale(payload)` imprime venda,
`window.SupermercadoDesktop.printLabels(payload)` gera etiquetas ZPL, EPL, PPLA
ou PPLB e envia o lote diretamente ao spooler Windows em modo RAW. A homologacao
fisica por modelo de impressora continua obrigatoria antes de ativar em producao.

A ponte `window.SupermercadoDesktop.processPayment(payload)` representa o TEF. Se
o terminal não tiver provedor configurado, ela retorna erro para o operador. Se
houver provedor configurado, o app usa um simulador rastreável durante o
desenvolvimento, devolvendo transação, NSU e autorização antes de liberar a
finalização da venda. Cada tentativa de TEF grava um evento local `tef` em
`devices.log.jsonl`, permitindo que a central do ERP enxergue aprovações, falhas
e terminais sem maquininha configurada quando o app sincronizar os diagnósticos.

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
`/pdv/api/terminal/device-events/`; se o servidor estiver indisponível, o PDV abre
normalmente e tenta novamente depois.

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
`%LOCALAPPDATA%\SupermercadoPDV\config.json`; para reconfigurar, execute o app
com `--configurar`. A chave fica apenas na máquina do caixa e não e versionada.

## Build Windows

Execute `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. O
executavel sera criado em `dist\SupermercadoPDV.exe`. Assinatura digital e
geração do instalador MSI ainda fazem parte da etapa de distribuição.

Depois do build e da assinatura, execute
`powershell -ExecutionPolicy Bypass -File .\publish_windows.ps1 -Version 0.1.0`.
O script confere o SHA-256 e publica o arquivo de forma atômica em `artifacts`,
de onde a central do ERP passa a disponibiliza-lo ao admin master.

O empacotamento Windows sera feito a partir deste projeto separado. O ERP web
continua sendo a fonte unica da interface, dos atalhos e das regras de venda.
