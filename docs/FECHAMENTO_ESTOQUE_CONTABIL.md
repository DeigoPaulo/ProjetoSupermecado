# Fechamento contábil do estoque

## Objetivo

O fechamento preserva uma fotografia imutável do estoque de cada filial no dia da captura. Ele existe para que o pacote do contador consiga reproduzir a quantidade e o custo do fim da competência mesmo quando for baixado meses depois.

O critério registrado é `CUSTO_MEDIO_PONDERADO_MOVEL`, o mesmo campo `custo_medio` mantido por filial e produto nas entradas do ERP. Cada item congela código interno, código de barras, nome, NCM, CEST, unidade, quantidade física, reserva, disponibilidade, custo médio e valor a custo. O cabeçalho guarda total, quantidade de itens e SHA-256 do conteúdo.

## Captura

Depois de conferir e encerrar as movimentações do dia, execute no servidor:

```text
python manage.py capturar_fechamento_estoque_contabil --filial ID_DA_FILIAL --usuario USUARIO_RESPONSAVEL --confirmar-fechamento
```

Sem `--filial`, o comando fecha todas as filiais ativas. A confirmação e a identificação de um usuário ativo responsável são obrigatórias; a captura gera auditoria. O responsável deve ser Master ou possuir perfil de Administração/Contabilidade na mesma empresa da filial. O sistema só permite capturar a data local atual e recusa criar fotografia retroativa.

A repetição com o mesmo conteúdo é idempotente. Se o estoque mudar depois do fechamento, uma nova tentativa para a mesma filial/data é recusada porque o registro original é imutável; a divergência precisa ser tratada operacionalmente, sem apagar o fechamento.

## Uso no pacote do contador

O pacote mensal usa `SNAPSHOT_IMUTAVEL_FECHAMENTO` somente quando todas as filiais selecionadas possuem fechamento na data final da competência. Na ausência de cobertura completa:

- para o próprio dia, exporta a posição atual como `POSICAO_NO_FECHAMENTO`;
- para uma competência passada, exporta a posição atual como `POSICAO_ATUAL_NAO_RETROATIVA` e apresenta alerta.

O fallback serve para diagnóstico e não deve ser tratado como inventário histórico. Períodos anteriores à implantação dos snapshots não podem ser reconstruídos automaticamente com garantia.

Os fechamentos podem ser consultados no administrativo, mas não editados nem excluídos pela aplicação.
