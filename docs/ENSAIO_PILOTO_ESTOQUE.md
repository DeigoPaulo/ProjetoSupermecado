# Ensaio ponta a ponta de estoque e validade

Atualizado em 01/09/2026.

## Objetivo

Confirmar, em um único fluxo verificável, que a entrada cria camadas de lote, a venda respeita o FEFO e não consome lote vencido, a perda autorizada alcança o lote exato, o inventário reconcilia a divergência por lote e o fechamento preserva a posição final.

## Contrato de evidência

O contrato `inventory_pilot_end_to_end_evidence_v3` é somente leitura. Ele recebe os identificadores de uma entrada finalizada, venda finalizada, perda, inventário aplicado e fechamento de estoque. Todos devem pertencer à mesma filial e compartilhar exatamente um produto do cenário analisado.

O relatório verifica:

- entrada finalizada e camadas de lote criadas;
- venda com alocação em lote não vencido segundo a validade fotografada no momento do consumo;
- código, validade e tratamento do lote da venda preservados com SHA-256;
- consumo limitado aos estados de tratamento liberados para venda no snapshot;
- ausência de documento fiscal criado para a venda do ensaio;
- perda vinculada ao lote vencido exato;
- inventário originado e ajustado no lote divergente;
- igualdade entre saldo agregado e soma das camadas;
- igualdade entre saldo final e fechamento;
- presença do SHA-256 imutável do fechamento;
- SHA-256 do próprio relatório.

Nenhuma dessas verificações altera dados ou realiza comunicação externa.

A Central do servidor também publica ao Master o diagnóstico agregado `inventory_lot_snapshot_coverage_v1`, separando por filial registros íntegros, legados e inconsistentes. O estado Sem vendas por lote não equivale a aceite do piloto.
A versão v2 não usa o estado atual do lote para provar uma venda passada. Cada nova alocação preserva código, validade e tratamento no instante do movimento e calcula um SHA-256 sobre a identidade do movimento, lote, quantidade, custo e snapshots. Alterar posteriormente o cadastro do lote não altera essa fotografia. Alocações anteriores à migration 0034 permanecem com campos vazios e são tratadas honestamente como legado sem evidência histórica v2.

A versão v3 acrescenta o gate `inventory_real_pilot_readiness_v1`. Para dados reais, a filial só pode produzir evidência válida quando possui vendas por lote e todas as respectivas fotografias históricas estão íntegras. Ausência de base, legado ou inconsistência reprova o aceite em modo estrito. Com `--dados-sinteticos`, o JSON registra explicitamente que o gate não foi aplicado ao aceite; essa opção nunca converte ensaio em homologação real.

## Comando

Antes de escolher os cinco IDs, o Master pode consultar candidatos recentes de uma filial:

```powershell
.\.venv\Scripts\python.exe manage.py previsualizar_fluxo_estoque_piloto --filial-id ID --estrito
```

A prévia usa o contrato `inventory_pilot_candidate_preview_v1`, limita cada categoria a 20 registros por padrão e aceita `--limite` entre 1 e 100. Ela mostra produtos presentes nas cinco etapas e impedimentos, mas não combina nem escolhe IDs automaticamente. A janela limitada não substitui a conferência humana nem a validação final.

Depois da escolha manual, gere a ficha antes do verificador final:

```powershell
.\.venv\Scripts\python.exe manage.py gerar_ficha_execucao_piloto --entrada-id ID --venda-id ID --perda-id ID --inventario-id ID --fechamento-id ID --responsavel-execucao "NOME OPERACIONAL" --responsavel-conferencia "NOME DO CONFERENTE" --observacoes "OBSERVACAO OPCIONAL" --estrito
```

A ficha usa o contrato `inventory_pilot_execution_sheet_v2`, repete as condições básicas de compatibilidade, incorpora a prontidão da filial, lista impedimentos, inclui um roteiro operacional fixo e produz SHA-256 sobre todo o conteúdo. Execução e conferência devem ser identificadas por nome ou referência operacional, preferencialmente por pessoas distintas. Não informe CPF, CNPJ ou e-mail. Esses campos aparecem somente no JSON baixado: não são gravados no banco, não constituem aceite, não executam o ensaio e a ficha declara `aprovacao_automatica=false`. Somente depois de revisar a ficha o Master deve executar o verificador v3 abaixo.

Na Central do servidor, o painel exclusivo do Master oferece cinco passos sem exigir digitação de comandos: seleção da filial para baixar a prévia; preenchimento dos cinco IDs, dos dois responsáveis e das observações opcionais para baixar a ficha; geração do relatório final v3; conferência da ficha com o relatório; e montagem do dossiê ZIP. A ficha exige confirmação de que os IDs foram escolhidos manualmente. O relatório exige nova confirmação e escolha obrigatória entre `sinteticos` e `reais`; somente a opção real aplica a trava histórica ao aceite. A interface não emite documento fiscal, não transmite dados e não registra aprovação.

```powershell
.\.venv\Scripts\python.exe manage.py verificar_fluxo_estoque_piloto --entrada-id ID --venda-id ID --perda-id ID --inventario-id ID --fechamento-id ID --estrito
```

Para arquivar o relatório e conferir offline sua ligação com a ficha, salve a saída e execute:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_fluxo_estoque_piloto --entrada-id ID --venda-id ID --perda-id ID --inventario-id ID --fechamento-id ID --estrito | Out-File -FilePath .\relatorio_piloto.json -Encoding utf8
.\.venv\Scripts\python.exe manage.py verificar_artefatos_piloto --ficha .\ficha_piloto.json --relatorio .\relatorio_piloto.json --estrito
```

O contrato `inventory_pilot_artifact_integrity_v1` recalcula os SHA-256 da ficha v2 e do relatório v3 e confere contratos, horários, filial, produto, os cinco IDs e os estados finais. Ele lê somente arquivos locais de até 5 MB, não consulta o banco, não repete os nomes dos responsáveis, não persiste o resultado e não acessa a rede. O JSON produzido pelo comando possui hash próprio e também não representa aceite operacional.

O SHA-256 comprova a consistência do conteúdo em relação ao hash que acompanha cada arquivo, mas não é assinatura digital e não prova autoria caso arquivo e hash sejam substituídos juntos. Preserve os originais em local controlado; qualquer futura exigência de autenticidade deverá usar assinatura ou ancoragem externa separada.

O mesmo verificador está disponível no quarto cartão da Central do servidor, somente para o Master. Selecione a ficha v2 e o relatório v3, cada um com no máximo 5 MB, e confirme a operação. O endpoint instala um handler exclusivo antes da validação CSRF, mantém os uploads apenas em memória, baixa o resultado `inventory_pilot_artifact_integrity_v1` e descarta o conteúdo ao terminar a requisição. Nenhum arquivo, nome, responsável ou resultado é persistido pelo sistema.

Depois da conferência, o quinto cartão pode reunir ficha, relatório e resultado da conferência no contrato `inventory_pilot_dossier_v1`. Os três JSON são novamente validados em memória; qualquer hash, vínculo, contrato ou proteção divergente impede o download. O ZIP usa nomes internos fixos e inclui `manifesto.json` com filial, produto, cinco IDs, tamanho e SHA-256 dos três arquivos efetivamente empacotados. O manifesto também possui SHA-256 próprio e declara que o pacote não é assinatura digital, não registra aceite, não consulta banco, não é persistido e não acessa a rede.

O ZIP arquivado pode ser novamente conferido, sem extração, pelo comando:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_dossie_piloto --dossie .\dossie_piloto.zip --estrito
```

O contrato `inventory_pilot_dossier_integrity_v1` exige exatamente os quatro nomes internos esperados, sem duplicidades, diretórios ou entradas criptografadas. Ele limita o tamanho do ZIP e de cada JSON, aceita apenas armazenamento simples ou Deflate, confere CRC, codificação, objetos JSON, contrato e SHA-256 do manifesto e reconstrói o manifesto esperado a partir da ficha, do relatório e da verificação. O resultado não inclui o caminho local nem os responsáveis, não extrai arquivos, não consulta banco e não acessa a rede.

Use `--dados-sinteticos` somente quando os registros forem de ensaio. Sem essa opção, o relatório não classifica os dados como sintéticos.

O modo `--estrito` retorna falha quando qualquer verificação for reprovada, inclusive a prontidão histórica da filial quando o ensaio usa dados reais. O JSON é escrito na saída padrão para que a equipe possa arquivá-lo pelo procedimento de implantação escolhido, sem o sistema inventar uma aprovação.

## Ensaio automatizado executado

O teste `apps.estoque.test_fluxo_piloto_ponta_a_ponta` executa o seguinte cenário em banco temporário:

1. entrada de dez unidades em dois lotes, sendo três vencidas e sete válidas;
2. venda de duas unidades com emissão fiscal desativada;
3. confirmação de que o lote vencido permaneceu intacto e o válido caiu de sete para cinco;
4. planejamento, conferência e baixa de uma unidade vencida no lote exato;
5. nova conferência divergente, inventário com contagem de todos os lotes e reconciliação do saldo para seis unidades;
6. fechamento do estoque com seis unidades;
7. emissão do relatório válido e rejeição de tentativa de misturar fechamento de outra filial.

Resultado em 01/09/2026: teste integrado aprovado, Central do servidor aprovada e regressão completa de Estoque aprovada com 114 testes. O banco temporário foi destruído ao final; nenhum dado sintético foi gravado no banco local.

## Próximo marco externo

Repetir o roteiro em uma filial piloto com registros reais já existentes, informar os cinco IDs ao comando, arquivar o JSON e seu SHA-256 e obter a conferência operacional responsável. Esse marco não libera emissão fiscal nem comunicação externa.
