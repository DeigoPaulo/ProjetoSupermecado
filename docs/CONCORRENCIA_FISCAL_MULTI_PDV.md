# Concorrência fiscal multi-PDV

## Escopo da prova

O contrato interno usa locks no menor recurso necessário. A preparação bloqueia a origem
(`Venda` ou `PedidoOnline`) e a `SerieFiscal` específica por filial, modelo, ambiente e
série. A transmissão bloqueia somente o `DocumentoFiscal`; não há lock global por empresa,
servidor ou fila.

A suíte `apps.fiscal.test_concorrencia_multi_pdv` depende de PostgreSQL real para provar:

- cinco caixas da mesma filial preparando NFC-e simultaneamente na mesma série, com números
  100 a 104 e próximo número 105;
- séries independentes entre filiais e entre NF-e modelo 55 e NFC-e modelo 65;
- rollback integral quando a geração do XML falha, sem documento parcial nem avanço da série;
- unicidade do número no banco e não reutilização de número cancelado;
- dois workers processando documentos diferentes, com no máximo um envio por documento;
- exclusão mútua entre transmissão manual e reserva da fila;
- retomada de lease expirado e consulta obrigatória antes de retransmitir resultado incerto;
- uma única evidência de XML enviado, retorno e XML autorizado por envio lógico.

Os testes anteriores de mesma venda e mesmo pedido continuam garantindo um documento e um
número consumido, com erro controlado para a tentativa concorrente.

## Reserva, resultado incerto e contingência

O token e o horário da reserva formam uma unidade protegida por constraint. Um worker pode
assumir lease realmente expirado; se `aguardando_consulta_sefaz=True`, a retomada executa
consulta, nunca novo envio. A mesma regra vale para documento em contingência, pois a fila e
o serviço usam a mesma reserva e o mesmo estado de reconciliação para `PRONTO` e
`CONTINGENCIA`.

`tentativas_transmissao` é incrementada no instante em que o envio externo é marcado como
iniciado, depois de carregar o adaptador, validar assinatura/schema e arquivar o XML de
envio. Falhas de preflight não contam como tentativa externa. A marcação de resultado
incerto acontece antes da chamada ao adaptador, de modo que uma interrupção exige consulta.

## Idempotência e evidências

A chave entregue ao adaptador é determinística para o documento, número e geração do XML:
`fiscal:<documento>:<numero>:<xml_gerado_em>`. Retries do mesmo XML usam a mesma chave. Um
reprocessamento deliberado regenera o XML e seu instante de geração, portanto inicia uma
nova tentativa lógica com nova chave.

As evidências são append-only e únicas por documento, tipo e referência. Assim, repetir a
mesma tentativa lógica não duplica `XML_ENVIO`, `RETORNO_TRANSMISSAO` ou `XML_AUTORIZADO`,
e o histórico anterior não é apagado.

## Limites

Esta é uma prova interna, totalmente offline, com adaptadores fake. SQLite executa as provas
atômicas e ignora explicitamente os cenários concorrentes. A aprovação completa depende do
workflow `PostgreSQL integrity`. Ela não representa homologação externa, não habilita rede
SEFAZ/Focus e não altera regras tributárias, XML, assinatura, XSD ou endpoints.
