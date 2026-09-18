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

O contrato `fiscal_channel_homologation_completion_gate_v1` liga a conclusão da homologação
à cobertura completa. Ele falha fechado diante de evidência ausente, pendente, rejeitada ou
de qualquer lacuna interna. O checklist técnico automático também continua obrigatório.
Esse portão permanece separado da ativação de produção e não transforma teste offline em
aceite real.

A tela Master mostra o portão como bloqueado, com os motivos consolidados, ou liberado
quando todas as sete operações do canal possuem evidência aprovada. Um cenário isolado da
SEFAZ direta comprova que a conclusão técnica pode ocorrer com cobertura integral sem mudar
o ambiente de homologação e sem qualquer chamada externa.

## Troca de canal

Evidências são sempre consultadas pelo snapshot do canal em que foram registradas. Quando
já existe evidência ou homologação concluída, a troca entre Focus e SEFAZ direta exige
confirmação explícita do Master. A alteração preserva o histórico anterior, reinicializa o
registro técnico como pendente e não reaproveita aprovações no novo canal.

Uma bateria conjunta de 29 testes confirmou formulário, confirmação, reinicialização,
isolamento por canal, permissões, roteiros e regressões, sem nova migration.
