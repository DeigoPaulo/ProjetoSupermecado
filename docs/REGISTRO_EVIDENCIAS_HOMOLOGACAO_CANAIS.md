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

## Próxima integração

A tela Master deverá listar e cadastrar somente metadados/referências, sem upload de
segredos. A conclusão da homologação passará posteriormente a consultar evidências
aprovadas por operação, mas esse bloqueio só será conectado após a interface de revisão e os
testes de permissão estarem concluídos.
