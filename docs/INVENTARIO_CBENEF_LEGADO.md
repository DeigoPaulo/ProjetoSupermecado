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

## Reavaliação do fallback — ciclo 165, 23/09/2026

O comando somente leitura retornou **zero** produtos preenchidos na base local de
desenvolvimento. Isto não altera a decisão `NAO_PODE_REMOVER_COLUNA`: a lógica
emissiva ainda lê o campo. Testes de caracterização fixam a matriz atual:

| Recorte | Fonte atual de `cBenef` no XML | Decisão por operação já criada |
| --- | --- | --- |
| GO, CRT 2 ou 3 | Parametrização produto + natureza; ausente/indefinida não usa legado | Aplicada |
| GO, CRT 1 ou 4 | Campo legado do Produto | Ignorada na emissão atual |
| Outras UFs, qualquer CRT | Campo legado do Produto | Ignorada na emissão atual |

Uma NFC-e sintética de SP confirma que uma parametrização explícita divergente
**não** substitui o legado no XML hoje. A regra de prontidão também conserva
leituras legadas, inclusive no caminho GO sem natureza informada. Portanto,
alterar a preferência do resolvedor, esvaziar o legado ou remover a coluna já
mudaria o comportamento fiscal; a contagem zero local não prova equivalência em
outra instalação. O código não foi alterado neste ciclo.

Desenho da substituição, ainda **não autorizado para execução emissiva**:

1. Delimitar as UFs/CRTs e naturezas realmente atendidas e confirmar com fonte
   oficial e responsável fiscal o significado e o formato de `cBenef` em cada
   recorte; não extrapolar a regra GO nem copiar códigos entre UFs.
2. Confrontar por produto/natureza os valores legado e explícito, inclusive
   ausência, conflito e decisão `SEM_BENEFICIO`, em relatório somente leitura.
   Divergências exigem decisão humana documentada, não migração automática.
3. Só depois alinhar prontidão e emissão à mesma decisão explícita, por recorte
   habilitado e com testes dos modelos 55/65. Recortes não avaliados ficam
   bloqueados ou mantêm compatibilidade declarada, nunca troca silenciosa.
4. Repetir o inventário em cada instalação, comprovar zero consumidor emissivo e
   zero diferença de comportamento aceita antes de propor remoção de coluna.

Pendência concreta para o próximo bloco: mapear UFs/CRTs efetivamente suportados
e os dois caminhos de prontidão por natureza, sem alterar XML ou schema ainda.

## Prontidão por recorte — ciclo 166, 23/09/2026

O cadastro aceita UFs brasileiras e CRT 1–4, mas o único perfil estadual técnico
em `PERFIS_FISCAIS_UF` é GO. Demais UFs seguem parametrização manual/genérica;
isso **não** equivale a homologação nem a suporte tributário completo. A matriz
local de ICMS admite apenas CST/CSOSN expressamente listados no serviço fiscal.

Os dois caminhos de prontidão (filtro SQL da listagem e mensagens detalhadas)
concordam entre si nos cenários sintéticos testados. Ambos, porém, mudam a
origem da avaliação do cBenef quando a natureza de operação não é fornecida:

| GO/CRT 3, redução de base | Com natureza | Sem natureza |
| --- | --- | --- |
| Legado válido; decisão explícita `SEM_BENEFICIO` sem código | Pendente | Pronto pelo legado |
| Legado vazio; decisão explícita `COM_BENEFICIO` com código válido | Pronto | Pendente pelo legado |

Para GO/CRT 1 e SP/CRT 3, os ensaios com legado válido não detectaram essa
alternância: a prontidão permanece no caminho de compatibilidade. Os resultados
acima **caracterizam o comportamento atual**, não aprovam um documento fiscal.
Em GO/CRT 2–3, uma listagem sem natureza pode portanto divergir do preflight
emissivo, que usa a natureza concreta. Nenhuma alteração operacional foi feita
neste ciclo para não trocar silenciosamente o significado de “pronto”.

Próxima decisão interna delimitada: definir uma sinalização fail-closed de
“natureza não determinada” na listagem/CSV GO/CRT 2–3 e provar que ela não
substitui o valor legado nem declara benefício fiscal. O relatório comparativo
somente leitura deve seguir por produto/natureza; a substituição emissiva e a
remoção da coluna continuam bloqueadas por validação normativa e contábil.

## Catálogo fail-closed sem natureza — ciclo 167, 23/09/2026

Quando uma empresa com filial GO/CRT 2–3 visível ao usuário não tem natureza
padrão NFC-e ativa, o catálogo fiscal global não classifica mais produtos como
“Prontos” pelo fallback legado. A listagem mostra aviso e pendência; o CSV
mantém o formato reimportável e acrescenta a coluna informativa
`situacao_prontidao_fiscal` com a causa. O filtro `prontos` fica vazio nesse
estado. Como o catálogo de produtos não é separado por filial, a restrição
conservadora alcança toda a listagem visível até a natureza ser definida.

Com natureza determinada, a seleção de cBenef e os filtros anteriores (inclusive
as pendências de naturezas NF-e) são preservados. Fora de GO/CRT 2–3, a ausência
de natureza padrão NFC-e não ativa essa
trava. Esta mudança é apenas da apresentação/prontidão; não muda o preflight,
o XML, a parametrização por operação nem a coluna legada.

Próxima etapa: relatório **somente leitura** que confronte, por produto,
natureza e recorte UF/CRT, o legado e a decisão explícita, distinguindo
concordância, divergência e ausência. Não migrar valores automaticamente.
