# Integração com adaptador SEFAZ

O ERP possui o contrato `sefaz_adapter_contract_v1` para integrar um provedor fiscal ou uma implementação direta dos web services. O adaptador roda somente no servidor, nunca no PDV desktop, e as credenciais ficam no ambiente (`.env` ou cofre de segredos), fora do banco, dos logs e do repositório.

## Antes de apontar para produção

1. Escolha o provedor fiscal ou o integrador responsável e obtenha credenciais de homologação.
2. Cadastre na filial o certificado A1, inscrição estadual, CSC, série NFC-e e natureza de operação.
3. Instale o schema XSD aprovado pelo contador e pelo provedor.
4. Configure a classe do adaptador no servidor:

```env
FISCAL_SEFAZ_ADAPTER=integracoes_fiscais.provedor_escolhido.Adapter
```

5. Execute sem transmitir nada:

```powershell
python manage.py validar_adaptador_sefaz --exigir-eventos --estrito
```

6. Registre as evidências em **Fiscal > Homologação GO**. Só depois execute os cenários no ambiente de homologação da SEFAZ.

O comando não envia XML, não testa token, não abre comunicação fiscal e não libera produção. Ele apenas verifica se a classe configurada carrega e declara as capacidades necessárias.

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

## Limites de responsabilidade

O programador entrega o contrato, validações, logs de auditoria e tela de evidências. O contador define tributação e cronograma; a empresa providencia certificado/CSC e credenciamento; o provedor confirma endpoints, schemas, respostas e homologação de produção. Não coloque senha de certificado, token CSC, token de provedor ou XML de cliente neste documento ou no Git.