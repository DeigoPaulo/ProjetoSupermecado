# Política de identidades fiscais de desenvolvimento

14/09/2026 · ciclo 107 · contrato `fiscal_identity_development_policy_v1`.

## Princípio

Validade estrutural e titularidade são coisas diferentes. Um CNPJ com formato e DV corretos pode pertencer a uma pessoa jurídica real; por isso, ele não deve ser chamado de fictício nem usado como identidade do supermercado apenas porque apareceu em documentação ou teste.

Foram separadas quatro categorias:

- `EXEMPLO_NORMATIVO`: valor reproduzido de uma fonte oficial para testar formato ou algoritmo; não prova titularidade.
- `FICTICIO_DESENVOLVIMENTO`: marcador local criado para demonstração ou teste, inclusive quando deliberadamente possui DV inválido.
- `REAL_PENDENTE`: identidade real ainda não fornecida ou cuja titularidade não foi verificada.
- `REAL_VERIFICADA`: identidade acompanhada por verificação de titularidade e origem cadastral documentada.

A política apenas avalia elegibilidade cadastral. Mesmo uma identidade real verificada não é liberada automaticamente para homologação, produção, licença, credencial ou emissão; essas decisões continuam nos portões específicos.

## Ambientes

Exemplos normativos e dados fictícios só podem ser usados com finalidade de documentação, teste unitário, integração local ou demonstração local, nos ambientes explícitos `development` e `test`.

Eles são proibidos em homologação e produção e nunca podem:

- representar a empresa do cliente;
- receber credencial ou token fiscal;
- ser vinculados como identidade de licença;
- assinar certificado;
- emitir ou transmitir documento fiscal.

## Proteção dos comandos

Os comandos `criar_dados_iniciais` e `popular_demo` continham CNPJs deliberadamente fictícios e podiam ser chamados sem uma trava de ambiente. Ambos agora consultam a política antes de acessar o banco e lançam erro em homologação ou produção.

Os testes capturaram as consultas e confirmaram zero SQL antes da recusa. O comando de demonstração continua disponível em desenvolvimento e teste, inclusive com sua opção de simulação.

## Inventário inicial

Uma busca conservadora por padrões de 14 posições ou máscara encontrou candidatos em 48 arquivos de teste, três arquivos executáveis e cinco documentos. Esse número é um inventário inicial de arquivos, não uma afirmação de que todos os valores sejam CNPJs ou de que sejam fictícios.

Os três arquivos executáveis são:

- `popular_demo.py`, agora protegido por ambiente;
- `criar_dados_iniciais.py`, agora protegido por ambiente;
- `services_lookup.py`, que contém apenas a máscara visual de CNPJ.

Nenhum valor existente foi reescrito e a base local não foi alterada.

## Próximo passo

O inventário foi concluído no ciclo 108 em [INVENTARIO_ESTATICO_IDENTIDADES_FISCAIS.md](INVENTARIO_ESTATICO_IDENTIDADES_FISCAIS.md), e o catálogo central protegido foi definido no ciclo 109 em [CATALOGO_IDENTIDADES_FISCAIS_TESTE.md](CATALOGO_IDENTIDADES_FISCAIS_TESTE.md). O próximo passo é adotá-lo apenas em testes novos ou naturalmente modificados, sem substituição em massa.

Foram aprovados 37 testes focados e 498 testes da suíte fiscal completa. Nenhuma migração foi gerada.
