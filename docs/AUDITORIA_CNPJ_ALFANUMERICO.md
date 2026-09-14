# Auditoria somente leitura do CNPJ alfanumérico

14/09/2026 · ciclo 104 · contrato `alphanumeric_cnpj_readonly_audit_v1`.

## Objetivo e proteção

A auditoria prepara a transição sem alterar cadastros. Ela consulta Empresa, Filial, Fornecedor, Cliente, documentos fiscais, documentos sincronizados, entradas de compra, evidências fiscais, DF-e recebidos e eventos DF-e.

O relatório não contém CNPJ nem chave completos. Cada ocorrência é identificada por modelo e ID, acompanhada apenas por valor parcialmente oculto e pelos 16 primeiros caracteres de uma impressão digital SHA-256. Credenciais, tokens, certificados e senhas não são consultados.

Os testes capturam as consultas executadas e exigem que todas comecem por `SELECT`. O contrato também fixa `altera_dados`, `aceite_producao`, `libera_migracao` e `libera_emissao` como falsos.

## Classificações

### CNPJ

- `VALIDO`: formato canônico e DV compatíveis.
- `DV_INVALIDO`: formato reconhecido, mas DV divergente.
- `FORMATO_INVALIDO`: não pode ser canonicalizado com segurança.
- `AUSENTE_OBRIGATORIO`: vazio em uma fronteira obrigatória.
- `VAZIO_PERMITIDO`: vazio em campo opcional.
- `IGNORADO_CPF`: documento de 11 dígitos reconhecido no campo misto de Cliente.

### Chave de acesso

- `VALIDA`, `DV_INVALIDO` e `FORMATO_INVALIDO` são avaliados separadamente.
- Vazios são classificados de acordo com a obrigatoriedade do campo.
- O padrão aceita letras somente nas 12 posições do CNPJ.

### Repetições canônicas

- `ESPERADA_EMPRESA_FILIAL`: empresa e filial vinculada representam a mesma matriz.
- `REVISAR_PAPEIS_DISTINTOS`: a mesma pessoa jurídica aparece em papéis diferentes, o que pode ser legítimo.
- `BLOQUEANTE`: há repetição dentro da mesma fronteira de unicidade ou vínculo empresa–filial incompatível.

## Ensaio na base local

O ensaio encontrou:

- 20 ocorrências de documento: 17 com DV inválido, uma válida, uma reconhecida como CPF e uma vazia permitida;
- três campos de chave vazios e permitidos;
- seis equivalências esperadas entre empresa e filial;
- uma repetição bloqueante envolvendo uma empresa e duas filiais;
- 18 bloqueios totais, somando DVs inválidos e a repetição bloqueante.

Por origem, os DVs inválidos estão em sete Empresas, nove Filiais e um Fornecedor. Esses dados têm aparência de cadastros fictícios usados no desenvolvimento. Nada foi corrigido, pois o resultado está marcado como `ENSAIO_LOCAL_NAO_ACEITE_PRODUCAO` e não representa o futuro cadastro real.

## Uso controlado

O comando abaixo gera JSON protegido e permanece somente leitura:

```text
python manage.py auditar_cnpj_alfanumerico
```

A opção `--estrito` termina com erro quando houver bloqueios, mas também não altera registros.

## Próximo passo

O portão puro foi concluído no ciclo 105 em [PORTAO_LEITURA_DUPLA_CNPJ.md](PORTAO_LEITURA_DUPLA_CNPJ.md). O próximo passo é ensaiar um adaptador somente leitura de Empresa e Filial, sem substituir as buscas atuais e sem liberar consumidores enquanto houver colisões bloqueantes.

Foram aprovados 11 testes focados da auditoria/estratégia e 472 testes da suíte fiscal completa.
