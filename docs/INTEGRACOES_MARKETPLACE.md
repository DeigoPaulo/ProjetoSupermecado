# Integracoes de marketplace

## Objetivo

O contrato `marketplace_partner_adapter_v1` permite receber formatos proprios de parceiros sem misturar regras externas com o dominio interno do ERP.

Cada integracao escolhe um provedor. O provedor `PADRAO` recebe diretamente o contrato nativo. Os demais provedores exigem um adaptador permitido no ambiente do servidor.

## Configuracao

Os caminhos Python nunca sao gravados no banco e nao podem ser enviados pelo parceiro. Configure apenas no ambiente controlado do servidor:

```env
MARKETPLACE_PARTNER_ADAPTERS_JSON={"IFOOD":"integracoes.ifood.Adapter","RAPPI":"integracoes.rappi.Adapter"}
```

O codigo do provedor e convertido para maiusculas. Uma integracao de provedor especifico fica bloqueada quando seu adaptador nao esta configurado, nao pode ser carregado ou nao implementa o metodo exigido.

## Interface do adaptador

```python
class Adapter:
    nome = "Nome do provedor"

    def normalizar_pedido(self, *, payload, integracao):
        return {
            "referencia_externa": "PEDIDO-123",
            "nome_cliente": "Cliente",
            "documento_cliente_tipo": "CPF",
            "documento_cliente": "12345678909",
            "telefone": "",
            "tipo_entrega": "RETIRADA",
            "endereco_entrega": "",
            "taxa_entrega": "0.00",
            "desconto": "0.00",
            "observacoes": "",
            "itens": [
                {
                    "codigo_barras": "7890000000000",
                    "quantidade": "1",
                    "preco_unitario": "10.00",
                }
            ],
        }
```

O adaptador recebe uma copia do JSON original e deve devolver um dicionario. Excecoes internas e retornos em outro formato sao recusados sem criar pedido.

## Idempotencia

A chave de idempotencia e a combinacao da integracao autenticada com `referencia_externa` depois da normalizacao. Reenvios devolvem o pedido existente e nao duplicam estoque, pagamento ou separacao.

O adaptador deve manter a mesma referencia para o mesmo pedido externo.

## Respostas operacionais

- `201`: pedido normalizado e criado.
- `200`: referencia ja recebida; resposta indica `duplicado: true`.
- `400`: JSON, normalizacao ou item invalido.
- `401`: chave da integracao invalida.
- `413`: corpo maior que 1 MB.
- `503`: provedor exige adaptador ausente ou nao carregavel.

## Prontidao e homologacao

A Central de Integracoes e `GET /pedidos-online/integracoes/diagnostico.json` publicam o diagnostico do adaptador sem expor token ou segredo. O parceiro autenticado tambem recebe o bloco de prontidao em `GET /pedidos-online/api/status/`.

Antes da producao, homologar ao menos:

1. autenticacao e renovacao da chave;
2. pedido valido e reenvio idempotente;
3. produto inexistente ou indisponivel;
4. retirada e entrega com politica da filial;
5. cancelamento, pagamento e estorno;
6. indisponibilidade e timeout do parceiro;
7. documento do destinatario e emissao fiscal aplicavel;
8. isolamento entre empresas e filiais.
