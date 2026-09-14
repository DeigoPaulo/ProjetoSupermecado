# Plano de compatibilidade do emitente com o XSD

14/09/2026 · ciclo 101 · contrato `issuer_xsd_compatibility_plan_v1`.

O plano transforma as lacunas do bloco `emit` em uma sequência controlada de trabalho. Ele não contém dados reais, não altera modelos, não cria migração e não modifica geradores, credenciais, ambientes ou canais.

## Diagnóstico do armazenamento atual

- `Empresa.cnpj` e `Filial.cnpj` possuem largura 18, suficiente tanto para o formato numérico mascarado atual quanto para os 14 caracteres do tipo `TCnpj`. A largura não prova que a semântica seja compatível.
- A interface aplica máscara exclusivamente numérica e as rotinas de sincronização, licenciamento, consultas, DF-e, importação e geração de chave removem tudo que não seja dígito.
- `ConfiguracaoFiscal.inscricao_estadual` aceita até 30 caracteres genéricos; o XSD permite `IE` com até 14 caracteres e padrão de 2 a 14 dígitos ou `ISENTO`.
- Os campos textuais do cadastro têm largura superior à exigida pelo XSD. Portanto, a primeira estratégia é validar na fronteira fiscal sem truncar nem estreitar colunas.
- `Empresa.uf` e `Filial.uf` já usam as 27 escolhas compatíveis com `TUfEmi`; a lacuna está no validador do contrato fiscal, não no domínio do modelo.
- Os geradores existentes de NFC-e e NF-e de pedido online montam `emit` sem `enderEmit`, embora o XSD o exija como 1–1. Os canais Focus e SEFAZ direta continuam desligados; esta constatação não significa emissão ativa.

## Cinco frentes

1. CNPJ alfanumérico: confirmar a regra oficial da chave de acesso e dos demais identificadores antes de escolher a representação canônica.
2. Mínimos textuais: auditar dados reais e criar validação fiscal explícita, sem truncamento silencioso.
3. Inscrição estadual: separar a capacidade ampla do banco da validação aplicável ao XML e ao caso tributário.
4. UF: reutilizar uma única lista oficial entre modelo e fronteira fiscal.
5. `enderEmit`: incluir o subgrupo nos geradores somente depois que os oito dados mapeados passarem pelo portão de prontidão.

## Pontos de acoplamento

O CNPJ também identifica empresa/filial no licenciamento, sincronização, consultas cadastrais, importação de compras, distribuição DF-e, configuração de tokens e rotinas fiscais. Uma troca direta da normalização poderia causar colisão de identidades, perda de credenciais ou associação à empresa errada. Por isso a possível migração do CNPJ permanece `NAO_DEFINIDA`.

O XML é produzido antes do adaptador de canal; portanto, a futura correção de `enderEmit` deve ser validada offline uma vez e depois homologada separadamente no Focus e na SEFAZ direta.

## Ordem obrigatória

1. Confirmar regra normativa do CNPJ alfanumérico.
2. Definir normalização canônica e retrocompatibilidade.
3. Auditar dados reais somente em leitura.
4. Implementar validadores compatíveis e testes.
5. Incluir `enderEmit` nos geradores offline.
6. Homologar Focus e SEFAZ direta separadamente.

Todos os portões e permissões de execução nascem falsos. A ausência do CNPJ real impede a auditoria da etapa 3, mas não impede avançar na etapa 1 com as fontes oficiais já preservadas.

A implementação passou em 28 testes focados da cadeia e em 456 testes da suíte fiscal completa.

## Próximo passo

Confrontar a regra do CNPJ alfanumérico com a Nota Técnica oficial preservada, especialmente composição da chave de acesso, identificação em serviços e cronograma de vigência. O resultado continuará sem alterar dados ou código operacional.
