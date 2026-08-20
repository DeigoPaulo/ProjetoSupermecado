# Contrato de adaptador de extrato

## Identificação

- Contrato: `financial_statement_adapter_v1`
- Núcleo: `apps.financeiro.extrato_adapters`
- Limite padrão: 5 MB por arquivo
- Execução: servidor administrativo, nunca no PDV desktop

## Interface

```python
class MeuExtratoAdapter:
    nome = "Nome exibido na conferência"
    extensoes = (".ret", ".txt")

    def ler(self, *, conteudo, arquivo_nome):
        return [
            {
                "numero_linha": 1,  # opcional
                "data": "2026-08-18",
                "tipo": "entrada",
                "valor": "125.40",
                "descricao": "Liquidação",
                "referencia_externa": "NSU-OU-LOTE-UNICO",
            }
        ]
```

## Campos normalizados

- `data`: data Python ou texto `AAAA-MM-DD`, `DD/MM/AAAA` ou `DD-MM-AAAA`.
- `tipo`: entrada/crédito ou saída/débito.
- `valor`: sempre positivo e maior que zero.
- `descricao`: texto obrigatório, limitado a 255 caracteres pelo núcleo.
- `referencia_externa`: chave obrigatória e estável, limitada a 120 caracteres.
- `numero_linha`: inteiro opcional; o núcleo usa a posição quando omitido.

## Registro

No ambiente do servidor:

```env
FINANCEIRO_EXTRATO_ADAPTERS_JSON={"STONE_V1":"integracoes.stone.ExtratoStoneV1Adapter"}
```

O código aceita apenas letras maiúsculas, números e sublinhado. Adaptadores nativos não podem ser sobrescritos. Caminhos de classes nunca são recebidos em formulário ou API.

## Aceite técnico

1. Arquivo válido importa todas as linhas esperadas.
2. Arquivo repetido não cria nova importação.
3. Referências repetidas no arquivo são recusadas.
4. Reimportação do movimento não duplica o item.
5. Crédito e débito são normalizados corretamente.
6. Datas e valores inválidos falham antes de gravar dados.
7. Arquivo com extensão incompatível é recusado.
8. O histórico registra código, nome e contrato do adaptador.
9. Ambiguidades permanecem para revisão manual.
10. O teste usa amostra anonimizada e compara totais com o relatório do fornecedor.

## Evolução

Mudanças incompatíveis exigem novo código de adaptador e novo contrato. Um layout homologado não deve ser alterado silenciosamente.
