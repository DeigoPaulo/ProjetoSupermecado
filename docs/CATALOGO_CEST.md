# Catálogo CEST versionado

## Fonte e fundamento

- Convênio ICMS 142/18 consolidado no CONFAZ: `https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18`
- O CEST possui sete dígitos: segmento, item e especificação.
- Os anexos relacionam CEST, NCM/SH e descrição da mercadoria.

A classificação não pode ser decidida somente pela NCM. Quando a descrição do item limitar o alcance, essa descrição também precisa ser conferida pelo responsável fiscal/contador, além da legislação aplicável à unidade federada.

## Snapshot local de desenvolvimento

- Referência de captura: `2026-08-31`
- Versão: `CONFAZ-CV142-18-CONSOLIDADO-2026-08-31`
- SHA-256: `d7fb7e8da0ace05123d35c13d04486b70440cfa7323f983d8fc2f2fcfd1d54d3`
- Tabelas de anexos processadas: `26`
- Linhas CEST normativas analisadas: `1.561`
- CEST vigentes importados: `1.035`
- Segmentos com itens vigentes: `25`
- Códigos cuja redação atual consta como revogada e foram excluídos: `8`
- Migration: `fiscal.0034`

O snapshot foi ativado apenas no banco local. Nenhuma credencial, certificado, endpoint de emissão, Focus NFe, conexão SEFAZ ou produção foi habilitado.

## Controles

- O comando aceita somente arquivo HTML local; não baixa nem ativa conteúdo automaticamente.
- A URL declarada deve usar HTTPS e o host oficial do CONFAZ.
- SHA-256, referência, versão e quantidade esperada são obrigatórios.
- A primeira redação consolidada de cada CEST é preservada; redações históricas repetidas são ignoradas.
- Quando a redação atual é `REVOGADO`, o código não entra no catálogo vigente.
- NCM/SH é preservada como publicada e também convertida em prefixos comparáveis.
- Referências por capítulo e itens genéricos sem NCM específica são representados sem inventar uma classificação.
- O catálogo e seus itens não podem ser criados ou excluídos manualmente pelo painel administrativo.

## Regra de validação

- CEST continua opcional porque a tabela nacional indica mercadorias passíveis de substituição tributária; aplicação efetiva depende da descrição e da legislação estadual.
- Quando informado, o CEST precisa existir no snapshot ativo.
- Quando houver relação objetiva por NCM/SH, a NCM do produto precisa ser compatível com ao menos um prefixo oficial.
- Relação compatível não comprova sozinha que o produto está sujeito a ST. A descrição e o enquadramento estadual continuam exigindo aprovação fiscal/contábil.
- Sem catálogo ativo, o sistema preserva compatibilidade e valida apenas o formato de sete dígitos; a prontidão de homologação, porém, permanece bloqueada.

## Importação

```powershell
python manage.py importar_catalogo_cest C:\caminho\confaz-cv142-18.html --versao CONFAZ-CV142-18-CONSOLIDADO-2026-08-31 --sha256-esperado d7fb7e8da0ace05123d35c13d04486b70440cfa7323f983d8fc2f2fcfd1d54d3 --referencia-esperada 2026-08-31 --quantidade-esperada 1035 --ativar
```

## Próximo subciclo

Versionar CFOP e vincular cada código à direção de entrada/saída, ao alcance interno/interestadual/exterior, ao modelo documental permitido e aos cenários tributários homologados.