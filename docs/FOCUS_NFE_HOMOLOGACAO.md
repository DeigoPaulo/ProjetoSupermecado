# Homologação Focus NFe

## Objetivo

Preparar a integração do DeTecServer com a Focus NFe para emissão e recebimento fiscal, sem liberar produção antes da homologação integral por filial.

A Focus recebe dados estruturados, assina documentos emitidos e conversa com a SEFAZ. O ERP continua sendo a origem operacional da venda, tributação, estoque, financeiro e auditoria. O provedor não substitui as validações internas de empresa, filial, série, CST, classificação tributária, certificado e permissão de emissão.

## Ambientes

| Ambiente | Base da Focus | Regra |
| --- | --- | --- |
| Homologação | `https://homologacao.focusnfe.com.br` | Padrão do projeto; sem efeito fiscal ou tributário. |
| Produção | `https://api.focusnfe.com.br` | Bloqueada até aceite fiscal e habilitação explícita. |

O token usa HTTP Basic: token como usuário e senha vazia. Ele fica somente no `.env`, nunca no Git, em logs, backups operacionais ou capturas de tela.

## NF-e recebidas contra o CNPJ

O adaptador implementado é `apps.fiscal.focus_dfe_adapter.FocusNFeDFeAdapter`. A Focus usa uma `versao` numérica por CNPJ e informa `X-Max-Version`; o ERP guarda esse cursor separadamente para cada filial.

Configuração mínima de homologação:

```env
FISCAL_DFE_ADAPTER=apps.fiscal.focus_dfe_adapter.FocusNFeDFeAdapter
FOCUS_NFE_DFE_BASE_URL=https://homologacao.focusnfe.com.br
FOCUS_NFE_DFE_TOKEN=TOKEN_DO_AMBIENTE
FOCUS_NFE_DFE_FETCH_XML=True
FOCUS_NFE_DFE_ALLOW_PRODUCTION=False
```

Para uma conta que exija tokens diferentes por CNPJ, prefira o mapa abaixo e deixe o token global vazio:

```env
FOCUS_NFE_DFE_TOKEN=
FOCUS_NFE_DFE_TOKENS_JSON={"12345678000199":"TOKEN_FILIAL_1","12345678000270":"TOKEN_FILIAL_2"}
```

Regras de segurança:

1. A consulta é somente `GET`; o adaptador não manifesta a nota automaticamente.
2. Resumo recebido não cria compra, estoque, contas a pagar ou escrituração.
3. Quando o XML completo estiver disponível, ele é armazenado e ainda depende de revisão humana.
4. A entrada de compra nasce em rascunho somente por ação autorizada no ERP.
5. O cursor só avança até o último documento efetivamente processado, mesmo que o provedor informe mais registros.
6. Token ausente, HTTP sem TLS e produção não liberada bloqueiam a consulta.

Comando para execução manual ou agendada:

```powershell
python manage.py consultar_dfe_recebidos --usuario admin --estrito
```

É possível limitar por empresa ou filial:

```powershell
python manage.py consultar_dfe_recebidos --usuario admin --empresa-id 1 --limite 100 --estrito
python manage.py consultar_dfe_recebidos --usuario admin --filial-id 1 --limite 100 --estrito
```

## Emissão NFC-e/NF-e

A emissão usa outro contrato, configurado por `FISCAL_SEFAZ_ADAPTER`. O adaptador de documentos recebidos não libera emissão e não deve ser confundido com o emissor.

O adaptador implementado é `apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter`. Ele transforma o XML local validado em JSON da Focus, envia NFC-e/NF-e com referência idempotente, consulta processamento, cancela, inutiliza e persiste no ERP a chave, o protocolo e o XML processado efetivamente autorizados pelo provedor.

Configuração mínima de homologação:

```env
FISCAL_SEFAZ_ADAPTER=apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter
FOCUS_NFE_FISCAL_BASE_URL=https://homologacao.focusnfe.com.br
FOCUS_NFE_FISCAL_TOKEN=TOKEN_DO_AMBIENTE
FOCUS_NFE_FISCAL_TOKENS_JSON={}
FOCUS_NFE_FISCAL_TIMEOUT_SECONDS=30
FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False
FISCAL_AUTO_TRANSMIT_ENABLED=False
```

Quando cada CNPJ possuir um token próprio, deixe `FOCUS_NFE_FISCAL_TOKEN` vazio e use `FOCUS_NFE_FISCAL_TOKENS_JSON`. A fila automática deve permanecer desligada até a emissão manual de homologação ser aprovada. Não use token de produção no ambiente de desenvolvimento.

Antes da primeira emissão devem estar homologados:

1. Emitente: CNPJ, IE, CRT/regime, endereço, certificado A1 e CSC quando aplicável.
2. Documento: NFC-e ou NF-e, série, numeração, ambiente, natureza e forma de emissão.
3. Itens: GTIN/código, descrição, NCM, CEST quando aplicável, CFOP, unidade, quantidade, valores e tributos.
4. Pagamentos: forma fiscal, valor, troco, NSU/autorização e venda dividida.
5. Destinatário e entrega conforme o modelo fiscal.
6. Cancelamento, inutilização, consulta, contingência, XML, DANFE e QR Code.
7. IBS/CBS somente conforme schema e cálculo oficialmente homologados.

## Sequência de homologação

1. Ativar a conta e cadastrar os CNPJs na Focus em homologação.
2. O contador confirma regras fiscais e cenários de teste.
3. O administrador configura cada filial e o certificado A1 pelo fluxo protegido.
4. Configurar o adaptador e executar diagnósticos sem produção.
5. Validar recebimento de resumo, XML completo, repetição, alteração de versão e indisponibilidade.
6. Validar emissão manual de NFC-e e NF-e, consulta, rejeição, indisponibilidade, cancelamento e inutilização nos cenários acordados.
7. Conferir no ERP se chave, protocolo e XML autorizado são exatamente os devolvidos pela Focus.
8. Registrar o aceite em Fiscal > Homologação.
9. Somente depois avaliar a fila automática e propor a ativação de produção.

## Responsabilidades

| Responsável | Entrega |
| --- | --- |
| Deigo Tecnologia | Adaptadores, fila, idempotência, telas, auditoria e evidências. |
| Empresa | Conta do provedor, certificado A1, CSC, credenciamento e autorização de produção. |
| Contador | Tributação, classificação, cenários e aceite fiscal. |
| Focus NFe | API, credenciais, comunicação com SEFAZ, distribuição e suporte. |

> Qualquer token compartilhado em conversa ou captura deve ser rotacionado antes da produção.