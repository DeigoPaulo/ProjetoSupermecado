# Registro auditável de evidências de homologação por canal

Contrato de serviço: `fiscal_channel_homologation_evidence_v1`.

O registro vincula uma evidência externa à configuração fiscal, filial, canal, ambiente e
operação. Ele não armazena certificado, CSC, token, senha, XML ou arquivo bruto. O sistema
guarda somente a referência protegida, SHA-256 do pacote, versão da aplicação, código de
status, protocolo e o confronto entre resultado esperado e obtido.

## Regras de segurança

- somente o Master pode registrar ou revisar;
- o ambiente deve ser homologação;
- o canal é copiado da configuração da filial, não informado livremente;
- a operação precisa possuir roteiro no canal selecionado;
- uma lacuna interna, como Eventos Focus, impede o registro;
- todo registro nasce pendente, mesmo com testes offline aprovados;
- aprovação ou rejeição exige justificativa e torna a decisão imutável pelo serviço;
- exclusão pelo modelo é proibida e registro/revisão geram auditoria;
- restrições do banco impedem ambiente de produção e revisão incoerente.

A migration `fiscal.0054_evidenciahomologacaocanal` cria a estrutura. Sua existência não
significa homologação executada e não altera qualquer trava de rede ou produção.

## Interface Master

A tela de homologação da filial lista e cadastra somente metadados/referências, sem upload
de arquivos ou segredos. O registro e a decisão são ações separadas: toda evidência nasce
pendente e somente depois pode ser aprovada ou rejeitada, sempre com justificativa. Tanto a
visualização quanto os endpoints recusam usuários que não sejam Master.

## Próxima integração

O contrato `fiscal_channel_homologation_coverage_v1` apresenta um diagnóstico somente
leitura da cobertura exigida pelo canal. Ele distingue operações aprovadas, pendentes,
rejeitadas e ausentes e mantém visível a lacuna interna de Eventos Focus. O diagnóstico
declara explicitamente que não altera a homologação e não libera produção.

O próximo passo é ligar a conclusão da homologação a um portão formal que exija cobertura
completa e falhe fechado diante de qualquer pendência ou lacuna. Esse portão continuará
separado da ativação de produção e não poderá transformar teste offline em aceite real.
