# SEFAZ direta / Deigo Fiscal

Este pacote concentra o núcleo da integração SOAP direta com a SEFAZ. O objetivo é reduzir o acoplamento ao ERP e permitir uma extração futura para um projeto/serviço próprio sem antecipar uma migração arriscada.

## Estrutura

- `adapter.py`: transporte SOAP, assinatura A1, interpretação de respostas e travas de rede/produção;
- `dfe.py`: distribuição sequencial de notas e eventos por NSU no Ambiente Nacional;
- `manifestacao.py`: eventos de manifestação do destinatário no Ambiente Nacional;
- `cce.py`: Carta de Correção Eletrônica para NF-e autorizada em Goiás;
- `capacidades.py`: contrato versionado com a situação real de cada capacidade;
- `__init__.py`: API pública do pacote.

O arquivo `apps/fiscal/sefaz_direta_adapter.py` é apenas uma fachada temporária para configurações antigas.

## Dependências que ainda ligam o pacote ao ERP

- `django.conf.settings` para configuração do ambiente;
- modelos fiscais recebidos pelos métodos do adaptador;
- abertura segura do certificado A1 em `apps.fiscal.certificados`;
- assinatura XML em `apps.fiscal.assinaturas`;
- contrato de retorno em `apps.fiscal.adapters`.

Antes de extrair o pacote, essas dependências devem virar interfaces injetáveis. Certificados, CSC, XMLs e dados de clientes não devem ser migrados para um serviço central compartilhado.

## Regra de evolução

Uma capacidade só pode mudar para `IMPLEMENTADO` quando possuir implementação, testes offline e contrato de retorno. Homologação real é acompanhada separadamente e continua obrigatória antes de produção.
