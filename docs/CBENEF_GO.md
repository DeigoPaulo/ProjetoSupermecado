# Catálogo cBenef de Goiás

Atualizado em 28/08/2026. Este documento descreve o controle técnico do catálogo e não define o enquadramento tributário de produtos.

## Fonte oficial validada

- Órgão: Secretaria da Economia de Goiás.
- Página pública: https://goias.gov.br/economia/codigos-de-beneficios-fiscais/
- Anexo consolidado da IN 1.518/22-GSE: https://goias.gov.br/economia/wp-content/uploads/sites/45/2022/07/IN-1dc.docx
- SHA-256 conferido em 28/08/2026: `a4fbbeff5ff431a17cf38011d1d8c095558e2bee44121afaee7cbe07bf9e292e`.
- Resultado da consolidação: 282 códigos; o documento contém duas redações para `SEM CBENEF` e o importador preserva a última, registrando a duplicidade.
- A tabela consolidada inclui as colunas CST 02, 15, 53 e 61 acrescentadas pela IN 1.563/23, com vigência indicada no documento em 22/06/2023.

A página oficial informa obrigatoriedade do cBenef desde 01/07/2023 para NF-e/NFC-e com benefício de ICMS e orienta compatibilidade com o CST. A IN 1.523/22 registra a exceção para optante pelo Simples Nacional.

## Controles implementados

- Nenhum download ou atualização ocorre automaticamente.
- A importação exige arquivo DOCX local, URL HTTPS no domínio oficial, versão, vigência, hash esperado e, opcionalmente, quantidade esperada.
- Hash, fonte, publicação, vigência, quantidade e redações duplicadas permanecem registrados.
- O catálogo nasce inativo; a ativação depende da opção explícita `--ativar`.
- O Admin permite consulta, mas não criação ou exclusão manual.
- Código ausente do catálogo, versão sem vigência ou incompatibilidade com CST bloqueiam a preparação fiscal antes da numeração.
- Sem catálogo vigente, códigos informados são tratados como pendência; o formato isolado não libera emissão.
- Para CRT 1 ou 4, redução de base não cria por si só a obrigação estadual de cBenef. Um código informado continua sujeito à tabela.
- O sistema não decide se o benefício cabe ao produto. Essa parametrização depende do contador responsável.

## Importação controlada

```powershell
python manage.py importar_catalogo_cbenef_go <arquivo.docx> \
  --versao <identificador> \
  --fonte-url <url-oficial> \
  --sha256-esperado <sha256> \
  --publicado-em AAAA-MM-DD \
  --vigencia-inicio AAAA-MM-DD \
  --quantidade-esperada <quantidade> \
  --ativar
```

Antes de substituir uma versão, deve-se conferir nova publicação, hash, quantidade, alterações legais e impactos nos produtos. Ativar catálogo não habilita Focus, SEFAZ direta, rede nem produção.
