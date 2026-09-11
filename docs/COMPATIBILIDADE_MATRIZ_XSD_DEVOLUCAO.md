# Compatibilidade da matriz atômica com o XSD auditado

11/09/2026 · ciclo 97 · contrato `supplier_return_atomic_xsd_compatibility_v1`.

O relatório confronta os 115 destinos documentados da matriz atômica da devolução com a estrutura do pacote 010f previamente auditado. Ele verifica existência de caminhos e alternativas; não cria elementos, não avalia regras tributárias e não conclui que um grupo se aplica ao caso concreto.

## Resultado reproduzido

| Estado | Quantidade | Significado |
|---|---:|---|
| `CONFIRMADO_NO_XSD_AUDITADO` | 105 | O caminho estrutural existe; quando havia alternativas, todas foram localizadas. |
| `PENDENTE_DE_LEIAUTE_APROVADO` | 8 | A matriz contém marcador explícito de RTC/IBS/CBS ainda não aprovado. |
| `SEM_TAG_TOTAL_DOCUMENTADA` | 2 | Bases informativas de PIS/COFINS não apontam para tag total própria. |
| `DIVERGENTE_DO_XSD_AUDITADO` | 0 | Nenhum destino não pendente divergiu do pacote auditado. |

O resultado “sem divergências” significa apenas que o mapa estrutural conhecido é compatível com essa evidência. Não aprova o pacote, sua vigência, a aplicabilidade do campo, valores, cálculos, obrigatoriedade contextual ou canais de transmissão.

## Expressões verificadas

Caminhos literais são percorridos desde o elemento global `NFe`. O verificador também entende:

- `*`: qualquer variante estrutural naquele nível;
- `(A|B)` e `A|B`: todas as alternativas listadas precisam existir em algum caminho válido;
- `[...PENDENTE]`: marcador deliberado, não procurado como tag;
- `SEM_CAMPO_TOTAL_ESPECIFICO`: ausência de destino total deliberadamente documentada.

O modelo resolve tipos complexos globais, tipos internos, escolhas, sequências, grupos referenciados e extensões. Os XSDs são relidos sem rede e o hash do ZIP é reconferido depois da auditoria para impedir confronto com conteúdo trocado.

## Uso

```powershell
python manage.py confrontar_matriz_xsd_devolucao `
  --arquivo docs/evidencias/nfe_2026_09_10/schemas_010f.zip `
  --sha256 b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998 `
  --versao PL_010f_v1.04
```

A saída JSON contém cada campo, destino, estado e quantidade de alternativas exigidas. Ela não inclui valores fiscais nem caminhos absolutos da máquina.

## Segurança

O contrato mantém `serializacao_liberada=false` para todos os 115 itens e fixa como falsas a aprovação de aplicabilidade, promoção do schema, geração de XML, assinatura e transmissão. O validador rejeita matriz adulterada, troca de campo/destino, classificação incompatível com marcador, resumo divergente ou política liberada.

Focus e SEFAZ direta continuam bloqueados. O relatório não testa paridade de adaptadores: apenas a estrutura do XSD.

A validação passou em 21 testes focados e na suíte fiscal completa com 440 testes. Não há migrações, e o diretório real `fiscal_schemas` permaneceu contendo somente seu README.

## Próximo passo

Transformar os 105 caminhos confirmados em um plano de construção por bloco, sem valores e sem criar XML, registrando cardinalidade, ordem, alternativas e condições que ainda impedem cada campo de chegar a um serializador.