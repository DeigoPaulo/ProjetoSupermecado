# Inventário do cBenef legado do Produto

Data da auditoria: 21/09/2026
Contrato do inventário: `produto_cbenef_legado_inventory_v1`

## Decisão

- Estado do fallback: `AINDA_EXISTE_CONSUMIDOR_EMISSIVO`.
- Decisão sobre o esquema: `NAO_PODE_REMOVER_COLUNA`.
- A base local de desenvolvimento possui zero produtos com o campo legado preenchido.
- A ausência de dados locais não autoriza remover a coluna: o fallback ainda preserva o
  comportamento emissivo de instalações fora do recorte Goiás + CRT 2/3.
- Nenhum valor legado foi copiado, inferido ou convertido em
  `ParametrizacaoBeneficioFiscalProduto`.

## Inventário de leitores e escritores

| Local | Função/contrato | Acesso anterior | Finalidade | Ação do ciclo 155 | Bloqueia remover a coluna? |
| --- | --- | --- | --- | --- | --- |
| `apps/produtos/models.py` | `Produto.codigo_beneficio_fiscal` | leitura/escrita | armazenamento físico legado | preservado sem migration | sim, enquanto houver consumidor emissivo |
| `apps/produtos/forms.py` e `templates/produtos/produto_form.html` | `ProdutoForm` | escrita | cadastro manual no Produto | campo removido; tela orienta usar Fiscal por produto/natureza | não |
| `apps/produtos/services.py` e `templates/produtos/importar_csv.html` | `importar_produtos_csv` | escrita | importação cadastral | escritor removido; cabeçalho antigo é rejeitado com orientação clara | não |
| `apps/empresas/services_snapshots.py` | `produto_snapshot_payload` | leitura/publicação | snapshot loja-nuvem | contrato elevado para `produto_snapshot_v2`; campo não é publicado | não |
| `apps/empresas/services_eventos_entrada.py` | `_produto_salvar` | escrita | aplicação do snapshot recebido | campo removido do conjunto aplicado; eventos v1 continuam processáveis, mas o legado é ignorado e o valor local é preservado | não |
| `apps/fiscal/views.py` | `produtos_fiscais_exportar_csv` | leitura/publicação | exportação cadastral fiscal | coluna legada retirada; decisões explícitas por operação permanecem | não |
| `apps/fiscal/perfis_uf.py` | `codigo_beneficio_produto_operacao` | leitura emissiva | resolução do cBenef no XML | preservado somente como compatibilidade fora de GO + CRT 2/3 | **sim** |
| `apps/fiscal/services.py` | filtro de pendências fiscais | leitura | prontidão nos escopos ainda legados | preservado para manter o mesmo comportamento fora do recorte migrado | **sim** |
| `apps/fiscal/focus_sefaz_adapter.py` | mapeamento `codigo_beneficio_fiscal` para `cBenef` | leitura de payload fiscal | serialização XML genérica | preservado; não lê diretamente o campo de `Produto` | não |
| `apps/fiscal/models.py`, forms, admin e tela fiscal | `ParametrizacaoBeneficioFiscalProduto.codigo_beneficio_fiscal` | leitura/escrita | decisão nova por produto e natureza | preservado; é o modelo atual, não o campo legado | não |
| migrations históricas | criação/uso do campo | esquema | histórico imutável | preservadas | não por si só |
| testes automatizados | fixtures e caracterização | leitura/escrita sintética | provar bordas e fallback | preservados/atualizados para caracterizar o contrato | não |
| `apps/produtos/diagnosticos.py` e comando `inventariar_cbenef_legado` | `produto_cbenef_legado_inventory_v1` | somente leitura | contar e referenciar valores remanescentes | criado sem qualquer atualização de dados | não |

Não foram encontrados serializers ou APIs públicas adicionais que escrevam o campo legado.
Depois deste ciclo, também não há input de Produto nem exportação cadastral que o exponha.

## Compatibilidade dos snapshots

- `produto_snapshot_v2` é o contrato produzido a partir deste ciclo e não contém o campo
  legado.
- Eventos antigos `produto_snapshot_v1` continuam aceitos para compatibilidade.
- Se um v1 trouxer `codigo_beneficio_fiscal`, esse valor não é aplicado: em produto já
  existente, o valor local permanece; em produto novo, o campo permanece vazio.
- A recepção não cria decisão fiscal por operação e não tenta adivinhar natureza, situação
  ou cBenef.

## Critério futuro para remover a coluna

A remoção física só poderá ser reavaliada depois que o fallback de
`codigo_beneficio_produto_operacao` e as verificações legadas de prontidão forem substituídos
por uma regra explícita para todos os escopos atendidos. Nesse momento, o inventário deve
retornar zero registros em cada instalação e os testes devem provar zero diferença emissiva.
Até lá, não deve ser criada migration de remoção.
