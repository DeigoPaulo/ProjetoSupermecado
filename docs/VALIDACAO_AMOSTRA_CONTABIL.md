# Validação da amostra contábil mensal

## Objetivo

O contrato `accounting_monthly_sample_validation_v1` verifica localmente se um pacote `accounting_monthly_package_v2` está tecnicamente coerente antes de apresentá-lo ao contador. A validação não transmite arquivos, não gera EFD ICMS/IPI e não cria obrigação fiscal ou financeira.

## Portões automáticos

A amostra somente é aprovada quando:

- pertence à empresa selecionada e usa uma versão validada do contrato contábil no formato Pacote ZIP v2;
- contém manifesto, relatórios fiscais, reconciliação e inventário obrigatórios;
- todos os arquivos declarados conferem em tamanho e SHA-256, sem caminhos inseguros, duplicidades ou extras;
- existe ao menos um documento fiscal de saída e cada documento possui XML correspondente;
- documentos de entrada, quando existentes, também possuem XML correspondente;
- a reconciliação segue `accounting_operational_reconciliation_v1` e não apresenta divergências de vendas ou entradas;
- o inventário foi capturado por fechamento imutável com cobertura completa das filiais do pacote.

O leitor limita quantidade de arquivos, tamanho comprimido, conteúdo descompactado, manifesto e resumo da reconciliação. Isso reduz o risco de pacotes malformados ou excessivos.

## Acesso e aceite

Somente o Master acessa **Sistema > Integração contábil > Validar amostra mensal** e pode registrar o aceite. A validação pode ser executada sem gravar aceite. Para gravá-lo, são exigidos competência, referência formal e confirmação explícita.

O aceite preserva empresa, competência, versão do contrato, SHA-256 do pacote, relatório completo, referência e responsável. O registro é imutável, idempotente para o mesmo pacote e auditado. Um pacote alterado possui outro hash e precisa de nova validação.

## Limites

A aprovação automática demonstra coerência técnica do material produzido pelo ERP; ela não substitui a conferência do contador. O checklist externo continua pendente até existir empresa real, versão de contrato confirmada, amostra real conferida e referência do aceite do escritório.

Focus NFe, SEFAZ direta, rede e produção não são consultados ou habilitados neste fluxo.
