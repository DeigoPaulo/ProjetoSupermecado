# Contrato de distribuição de DF-e

## Objetivo

O contrato fiscal_dfe_distribution_v1 separa o ERP do fornecedor fiscal. Ele
pode ser implementado por um adaptador Focus NFe, outro provedor homologado ou
integração direta com o serviço nacional de distribuição, sem alterar o fluxo de
compras.

A consulta ocorre por filial/CNPJ. Cada filial preserva seu próprio ultimo_nsu
e max_nsu. O cursor somente avança depois que o lote inteiro é validado e
armazenado.

## Configuração

No arquivo .env, configure FISCAL_DFE_ADAPTER com a referência Python da classe,
por exemplo:

    FISCAL_DFE_ADAPTER=apps.fiscal.focus_dfe_adapter.FocusNFeDFeAdapter

A classe não deve guardar token, senha ou certificado no código-fonte. Segredos
devem vir do ambiente ou do cofre de credenciais da implantação.

## Interface do adaptador

A classe deve expor consultar(cnpj, ultimo_nsu, limite) e retornar um dicionário
com contrato, ultimo_nsu, max_nsu, mensagem, documentos e, opcionalmente,
aguardar_segundos. Cada documento pode conter nsu e xml completo. Quando o XML
ainda não estiver disponível, pode informar chave_acesso, destinatario_cnpj,
emitente_cnpj, emitente_nome, numero_documento, data_emissao, valor_total e
schema.

O campo `tipo_documento` aceita `NFE` (padrão, inclusive quando omitido) ou
`EVENTO`. Eventos devem sempre fornecer XML e chave de acesso com 44 dígitos;
podem incluir tipo_evento, sequencia, data_evento e descricao. O núcleo os
armazena separadamente e não os encaminha ao parser de entrada de mercadoria.
O campo `aguardar_segundos` aceita de 0 a 86400 e cria um bloqueio persistente
por filial antes de uma nova consulta.

O adaptador deve:

- autenticar o CNPJ no provedor homologado;
- respeitar limites e regras de consumo do serviço;
- devolver somente documentos do CNPJ solicitado;
- usar timeout finito e TLS válido;
- nunca registrar token, certificado ou XML em logs externos;
- lançar exceção em falha de transporte ou resposta inválida.

## Execução agendada

    .\.venv\Scripts\python.exe manage.py consultar_dfe_recebidos --usuario usuario.tecnico --estrito

Filtros opcionais:

    .\.venv\Scripts\python.exe manage.py consultar_dfe_recebidos --usuario usuario.tecnico --empresa-id 1
    .\.venv\Scripts\python.exe manage.py consultar_dfe_recebidos --usuario usuario.tecnico --filial-id 3

O usuário técnico precisa estar ativo. Administradores de empresa ficam
restritos à própria empresa; um superusuário técnico pode processar todas as
empresas.

## Garantias do núcleo

- isolamento por empresa e filial;
- cursor independente por CNPJ;
- cooldown persistente por filial quando o provedor/SEFAZ exigir intervalo;
- deduplicação de notas por empresa/chave e de eventos por empresa/NSU;
- lote atômico: erro impede avanço do cursor;
- auditoria da consulta e de cada documento novo;
- nenhuma entrada, manifestação, movimentação de estoque ou lançamento
  financeiro é criado automaticamente;
- XML completo continua exigindo revisão autorizada antes de virar entrada.
## Cursor de provedor

O contrato chama o cursor normalizado de `ultimo_nsu` por compatibilidade com a distribuição direta da SEFAZ. Na Focus NFe, esse valor corresponde ao campo numérico `versao`, mantido separadamente para cada CNPJ/filial e avançado somente até o último documento efetivamente processado.
