# Contrato de integração contábil

## Objetivo

O contrato `accounting_integration_agreement_v1` registra, por empresa, qual software ou escritório receberá o pacote mensal, qual formato técnico foi combinado e quem é o responsável externo pela EFD ICMS/IPI.

Esse cadastro não envia arquivos, não ativa rede, não gera EFD e não cria obrigação. Ele também não armazena senha, token, certificado, preço ou condição comercial.

## Controle de acesso

- somente o Master registra uma nova versão ou confirma a validação;
- administradores consultam o estado, sem poder alterá-lo;
- o perfil Contabilidade consulta o resumo no Portal contábil;
- o pacote ZIP e a API incluem somente o resumo operacional do contrato.

## Versionamento

Cada gravação cria uma nova versão imutável. Versões existentes não podem ser editadas ou excluídas pela aplicação. O histórico e a auditoria permitem demonstrar qual combinação foi registrada em cada momento.

Uma versão pode ficar como **Rascunho** enquanto os dados reais não estiverem disponíveis. O rascunho não substitui a última versão validada e não representa aceite.

O envio automático pelo adaptador do servidor possui uma trava adicional: somente uma versão validada com o formato **Adaptador do servidor v1** autoriza a tentativa. Um adaptador configurado no ambiente, sozinho, não libera o botão nem o endpoint. Contratos de ZIP ou API também não autorizam esse envio.

Para criar uma versão **Validada com o contador**, são obrigatórios:

- software ou escritório destinatário;
- formato combinado: pacote ZIP v2, API JSON v1 ou adaptador de servidor v1;
- responsável externo pela EFD ICMS/IPI e sua identificação;
- referência interna do aceite do contador.

## Limite da responsabilidade

O Deigo Varejo fornece dados gerenciais e fiscais estruturados para conferência. O contrato deixa explícito onde a EFD ICMS/IPI será preparada, mas o ERP não passa a gerar, assinar ou transmitir essa obrigação.

A definição real continua pendente até a escolha do escritório/software, validação de uma amostra mensal e registro do aceite correspondente.

## Validação da amostra

A ferramenta local `accounting_monthly_sample_validation_v1` já está pronta. Ela exige contrato validado em Pacote ZIP v2, confere integridade, XMLs, reconciliação sem divergências e fechamento imutável do estoque. Somente o Master registra um aceite imutável e auditado, vinculado ao SHA-256 do pacote. A aprovação técnica não substitui a conferência externa. Consulte `docs/VALIDACAO_AMOSTRA_CONTABIL.md`.
