# Integração com adaptador SEFAZ

O ERP possui o contrato `sefaz_adapter_contract_v1` para integrar um provedor fiscal ou uma implementação direta dos web services. O adaptador roda somente no servidor, nunca no PDV desktop, e as credenciais ficam no ambiente (`.env` ou cofre de segredos), fora do banco, dos logs e do repositório.

## Seleção por filial e visibilidade

Na tela de configuração fiscal, somente o usuário Master visualiza o campo **Canal técnico de emissão**. A escolha é feita por filial e pode usar Focus NFe, conexão direta SEFAZ GO, compatibilidade com a configuração global do servidor ou manter a emissão externa desativada. Administradores e gerentes continuam operando a configuração fiscal sem visualizar nomes de canais nem alterar essa decisão.

A seleção apenas define o roteamento técnico. Ela não grava credenciais no banco e não liga rede, fila automática ou produção. As credenciais, o certificado A1 e as travas de ambiente continuam independentes e protegidos no servidor. Instalações antigas permanecem compatíveis pelo valor PADRAO_SERVIDOR, que consulta FISCAL_SEFAZ_ADAPTER.

## Antes de apontar para produção

1. Escolha o provedor fiscal ou o integrador responsável e obtenha credenciais de homologação.
2. Cadastre na filial o certificado A1, inscrição estadual, CSC, série NFC-e e natureza de operação.
3. Instale o schema XSD aprovado pelo contador e pelo provedor.
4. Configure a classe do adaptador no servidor:

Para a Focus NFe, o projeto já fornece o adaptador oficial:

```env
FISCAL_SEFAZ_ADAPTER=apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter
FOCUS_NFE_FISCAL_BASE_URL=https://homologacao.focusnfe.com.br
FOCUS_NFE_FISCAL_TOKEN=TOKEN_SANDBOX
FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False
FISCAL_AUTO_TRANSMIT_ENABLED=False
```

A trilha técnica iniciada em 24/08/2026 usa esta configuração em sandbox e emissão manual. O token deve ser fornecido por canal seguro e nunca incluído em commit, documento, captura de tela ou log. A fila automática só poderá ser avaliada depois do aceite dos cenários manuais.

A estrutura do adaptador SOAP direto para Goiás também está pronta, mas dormente e ainda não homologada:

```env
# Não habilitar fora de uma homologação controlada.
FISCAL_SEFAZ_ADAPTER=apps.fiscal.sefaz_direta.SefazDiretaAdapter
SEFAZ_DIRETA_NETWORK_ENABLED=False
SEFAZ_DIRETA_ALLOW_PRODUCTION=False
```

Consulte `docs/SEFAZ_DIRETA_GO.md`. Ter a estrutura implementada não substitui credenciamento, schemas oficiais, testes no ambiente da SEFAZ nem aceite fiscal.

Para outro provedor, implemente o mesmo contrato e configure sua classe no servidor.

5. Execute sem transmitir nada:

```powershell
python manage.py validar_adaptador_sefaz --exigir-eventos --exigir-configuracao --estrito
```

6. Registre as evidências em **Fiscal > Homologação GO**. Só depois execute os cenários no ambiente de homologação da SEFAZ.

O comando não envia XML, não testa o token na rede, não abre comunicação fiscal e não libera produção. Ele verifica o contrato, o schema e, com `--exigir-configuracao`, somente a presença local das credenciais, o ambiente e as travas declaradas pelo adaptador. Nenhum valor secreto aparece na saída.

## Interface mínima

A classe indicada por `FISCAL_SEFAZ_ADAPTER` deve implementar `transmitir`. Os demais métodos são necessários para uma operação completa:

```python
class Adapter:
    assina_xml = True       # ou False para assinatura A1 local pelo ERP
    valida_schema = True    # ou False quando o XSD local for usado

    def transmitir(self, *, documento, xml, idempotency_key, ambiente):
        return {
            "status": "AUTORIZADO",  # AUTORIZADO, REJEITADO ou PENDENTE
            "chave_acesso": documento.chave_acesso,
            "protocolo": "...",
            "mensagem": "...",
            "xml_autorizado": "<nfeProc>...</nfeProc>",
        }

    def cancelar(self, *, documento, chave_acesso, protocolo_autorizacao,
                 justificativa, idempotency_key, ambiente):
        return {"status": "CANCELADO", "protocolo": "...", "mensagem": "..."}

    def inutilizar(self, *, inutilizacao, cnpj, tipo_documento, ano, serie,
                   numero_inicial, numero_final, justificativa,
                   idempotency_key, ambiente):
        return {"status": "INUTILIZADA", "protocolo": "...", "mensagem": "..."}

    def consultar(self, *, documento, chave_acesso, idempotency_key, ambiente):
        return {"status": "AUTORIZADO", "protocolo": "...", "mensagem": "..."}
```

Os retornos são estritos e idempotentes. O ERP recusa autorização sem chave de 44 dígitos e protocolo, rejeições sem motivo e respostas em formato desconhecido.

## Reconciliação da NFC-e offline

A NFC-e preparada em contingência preserva `tpEmis=9`, a chave, `dhCont` e `xJust` mesmo depois de uma rejeição e do reprocessamento manual. Como o documento pode já ter sido entregue ao consumidor, uma rejeição não permite cancelamento apenas local: o cadastro deve ser corrigido e a regularização concluída na SEFAZ.

Quando uma transmissão fica sem resposta definitiva, a fila consulta a mesma chave antes de qualquer reenvio. Para NFC-e offline, uma única resposta `NAO_LOCALIZADO` não libera retransmissão. O ERP exige no mínimo duas confirmações consecutivas, persistidas no documento; timeout, falha ou outro resultado interrompem a sequência. O parâmetro seguro é:

```env
FISCAL_AUTO_QUERY_MAX_ATTEMPTS=12
FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS=2
```

O prazo excedido gera alerta no detalhe, diagnóstico e exportação de contingência, mas não apaga o documento nem ignora a reconciliação. Autorização grava protocolo/XML definitivo; rejeição exige correção; retorno pendente continua somente em consulta; ausência confirmada libera uma nova transmissão controlada no ciclo seguinte.
## Arquivo imutável de evidências fiscais

A migration `0031` cria um arquivo interno append-only por documento. O sistema preserva separadamente o XML entregue ao adaptador, o retorno normalizado, o XML autorizado devolvido pelo canal, os resultados de consulta e os eventos de cancelamento e Carta de Correção. Assim, atualizar o XML corrente do documento não elimina o que foi efetivamente enviado ou recebido antes.

Cada registro possui referência idempotente, hash SHA-256 do conteúdo, hash do registro anterior e hash da cadeia. A aplicação bloqueia `save`, alteração em lote e exclusão depois da criação. O verificador recalcula conteúdo, sequência e encadeamento para detectar adulteração direta. Na tela do documento, somente o Master recebe o estado da cadeia e sua âncora atual; o conteúdo fiscal não é exposto nesse diagnóstico.

Se o adaptador já tiver respondido e a gravação da evidência falhar, a transmissão passa a aguardar consulta de protocolo antes de qualquer reenvio. O comando `verificar_integridade_evidencias_fiscais --estrito` gera o contrato sanitizado `fiscal_evidence_anchor_v1` por promoção atômica. O backup diário mantém `fiscal-evidence-anchor-latest.json` fora do banco, compara quantidade e prefixo histórico antes de substituí-lo e inclui uma cópia com SHA-256 no ZIP. A restauração valida o arquivo e compara a cadeia restaurada antes de iniciar o serviço. Com `--registrar-alerta --origem backup|restauracao|manual`, o comando grava somente um resumo sanitizado na auditoria, não duplica o mesmo estado e alimenta o alerta exclusivo do Master no Super Admin e no Backup. Armazenamento fora da máquina e a política legal de retenção ainda pertencem à implantação definitiva.
## Limites de responsabilidade

O programador entrega o contrato, validações, logs de auditoria e tela de evidências. O contador define tributação e cronograma; a empresa providencia certificado/CSC e credenciamento; o provedor confirma endpoints, schemas, respostas e homologação de produção. Não coloque senha de certificado, token CSC, token de provedor ou XML de cliente neste documento ou no Git.