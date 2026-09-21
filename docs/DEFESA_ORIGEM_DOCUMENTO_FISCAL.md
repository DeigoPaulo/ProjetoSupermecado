# Defesa da origem do DocumentoFiscal

## Escopo auditado

O inventário do ciclo 149 revisou as criações de `DocumentoFiscal` no código
operacional, no Admin, nas migrations, nos testes e na base local.

Os únicos serviços operacionais que criam o documento fiscal são:

- `preparar_documento_venda`, que vincula uma NFC-e a uma venda;
- `preparar_documento_pedido_online`, que vincula uma NF-e a um pedido online.

A sincronização recebida de outros servidores usa o modelo separado
`DocumentoFiscalSincronizado`; DF-e de entrada também possui modelo próprio. Os
rascunhos de devolução ao fornecedor ainda não geram `DocumentoFiscal`.

As demais criações diretas encontradas estão em fixtures de teste. Elas representam
documentos autorizados, cancelados ou rejeitados usados para testar relatórios,
consulta, inutilização, CC-e e auditorias, mas não constituem uma rota operacional.

## Proteções aplicadas

- O banco exige que um documento aponte para exatamente uma origem: venda ou pedido
  online. Origem ausente e origem dupla são recusadas.
- A validação de domínio exige exatamente uma dessas origens e confere que a origem
  pertence à mesma filial do documento.
- O Admin permite consulta, mas não permite adicionar, excluir ou editar documentos.
- A migration 0057 executa preflight não destrutivo e informa IDs antes de aplicar a
  constraint caso encontre origem ausente ou dupla.
- A unicidade de documento ativo por venda e por pedido continua protegida pelas
  constraints anteriores.

## Tratamento do registro demonstrativo local

A auditoria somente leitura encontrou um documento local emitido sem venda e sem
pedido online. Não existe venda da mesma filial com o mesmo valor, e o registro não
possui chave fiscal que permita reconstruir o vínculo de forma inequívoca.

O XML armazenado identifica somente `NFeDemo9001` e não contém os campos fiscais
estruturais de modelo, número, série, data de emissão ou total. Isso reforça que o
registro parece demonstrativo, mas não autoriza sua exclusão automática.

Após confirmação expressa de que toda a base local contém apenas dados de
desenvolvimento/demonstração, foi verificado que o registro `id=1` não possuía
dependências. Somente esse registro demonstrativo foi removido da base local; nenhum
outro documento ou dado de domínio foi apagado ou recriado.

Essa limpeza não faz parte da migration. Em uma instalação com dados legados, a
migration 0057 para antes de alterar a constraint, lista os IDs incompatíveis e exige
classificação com evidência. Ela não exclui registros, não infere vínculos e não
inventa origem fiscal.

## Evolução para devolução ao fornecedor

A regra atual cobre integralmente os dois criadores operacionais existentes. Antes que
a devolução ao fornecedor passe a criar NF-e, o documento receberá uma relação
protegida e dedicada ao registro aprovado de `RascunhoDevolucaoFornecedor`. A alteração
de modelo e a troca da constraint ocorrerão na mesma migration, ampliando o XOR para
exatamente uma entre venda, pedido online ou devolução.

Até essa evolução ser implementada, o fluxo de devolução não pode criar
`DocumentoFiscal`. Não será usado vínculo genérico, origem manual nem associação por
valor, data, numeração ou proximidade.

## Validação do ciclo

A regressão completa do módulo Fiscal passou com 654 testes e três cenários ignorados
por dependência explícita de ambiente. A seleção integral da CI passou com 22 testes
em PostgreSQL 18 real, incluindo as provas de ausência de origem, dupla origem, mesma
filial, unicidade e concorrência. A migration 0057 foi aplicada à base local, que
permaneceu sem documentos incompatíveis. A validação hospedada deste ciclo deve ser
registrada no roadmap após o push.
