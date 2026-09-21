# Proteção do CSC

O token CSC da NFC-e é tratado como segredo fiscal. A partir da migration
`fiscal.0055`, ele não existe mais como coluna de texto aberto em
`ConfiguracaoFiscal`: o banco mantém apenas a cifra Fernet e a data da última
atualização.

## Operação

- somente o usuário Master pode visualizar o estado e cadastrar, rotacionar ou
  revogar o CSC;
- o formulário nunca devolve o token já armazenado ao navegador;
- campo de novo token vazio preserva o segredo atual;
- inclusão, rotação e revogação geram auditoria sanitizada;
- admin, prontidão e diagnósticos trabalham somente com a indicação de que o CSC
  está ou não configurado;
- a abertura do valor exige chamada explícita a `abrir_csc` no ponto técnico que
  realmente necessitar do segredo.

## Chave e recuperação

A cifra usa `FISCAL_CERTIFICATE_KEY`, a mesma raiz de proteção do certificado A1.
Essa chave deve ser longa, exclusiva do ambiente, mantida fora do repositório e
incluída no procedimento seguro de backup. Trocá-la sem recriptografar os segredos
torna A1 e CSC anteriores ilegíveis; o sistema falha fechado e não inclui o valor
na mensagem de erro.

A migration converte tokens legados antes de remover a coluna antiga. Recomenda-se
backup testado antes da aplicação em cada ambiente. Rollback técnico recria o campo
legado e descriptografa o valor antes de remover as novas colunas, exigindo a mesma
chave usada na conversão.

## Limite desta entrega

A proteção local não equivale a credenciamento ou homologação. O CSC real somente
deve ser cadastrado por canal seguro na filial piloto, e rede/produção continuam
bloqueadas até as evidências externas exigidas no roadmap.
