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

- O banco impede que um documento aponte simultaneamente para venda e pedido online.
- A validação de domínio exige exatamente uma dessas origens e confere que a origem
  pertence à mesma filial do documento.
- O Admin permite consulta, mas não permite adicionar, excluir ou editar documentos.
- A migration executa preflight não destrutivo e informa IDs antes de aplicar a
  constraint caso encontre dupla origem legada.
- A unicidade de documento ativo por venda e por pedido continua protegida pelas
  constraints anteriores.

## Legado sem origem

A auditoria somente leitura encontrou um documento local emitido sem venda e sem
pedido online. Não existe venda da mesma filial com o mesmo valor, e o registro não
possui chave fiscal que permita reconstruir o vínculo de forma inequívoca.

Por isso a migration 0056 preserva registros sem origem e bloqueia apenas a dupla
origem. O registro não foi apagado, alterado nem vinculado por aproximação.

## Pendência para a constraint final

Antes de exigir no banco exatamente uma origem, o responsável fiscal deve classificar
o legado com evidência operacional. As alternativas legítimas são localizar a venda
ou pedido real e registrar o vínculo correto, ou definir um fluxo explícito e auditado
para documentos históricos externos. Não é permitido inferir origem por valor, data
ou proximidade de numeração.

Também será necessário decidir qual relação representará futuras NF-e de devolução ao
fornecedor antes que esse fluxo passe a criar documentos. A constraint final deverá
aceitar exatamente uma origem entre todos os fluxos então suportados.

## Validação do ciclo

A seleção crítica atualizada passou com 21 testes em PostgreSQL 18 real, inclusive as
provas concorrentes. A regressão completa do módulo Fiscal passou com 653 testes e
três cenários ignorados por dependência explícita de ambiente. A migration 0056 foi
aplicada à base local sem alterar o documento legado.
