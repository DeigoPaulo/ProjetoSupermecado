# Catálogo CFOP versionado

## Fonte oficial

- Ajuste SINIEF 07/01 consolidado no CONFAZ: `https://www.confaz.fazenda.gov.br/legislacao/ajustes/2001/AJ_007_01`
- O guia da EFD ICMS/IPI determina que o código informado exista na tabela instituída pelo Ajuste SINIEF 07/01.

## Snapshot local de desenvolvimento

- Referência de captura: `2026-08-31`
- Versão: `CONFAZ-AJ-SINIEF-07-01-CONSOLIDADO-2026-08-31`
- SHA-256: `f6a40c06d4e56bcf6a650f8cd6c50f1b04d4524f1e9729fbc961539b43ea25e6`
- Linhas codificadas analisadas: `528`
- Agrupadores terminados em `00` ou `50`: `68`
- CFOP utilizáveis importados: `460`
- Entrada: `213`
- Saída: `247`
- Alcance interno: `212`
- Alcance interestadual: `203`
- Alcance exterior: `45`
- Migration: `fiscal.0035`

O snapshot foi ativado somente no banco local. Nenhuma credencial, certificado, endpoint Focus/SEFAZ, rede fiscal ou produção foi habilitado.

## Classificação objetiva

O primeiro dígito permite derivar a direção e o alcance:

| Prefixo | Direção | Alcance |
|---|---|---|
| 1 | Entrada | Interno |
| 2 | Entrada | Interestadual |
| 3 | Entrada | Exterior |
| 5 | Saída | Interno |
| 6 | Saída | Interestadual |
| 7 | Saída | Exterior |

Códigos terminados em `00` ou `50` são títulos de agrupamentos e não podem ser usados como CFOP da operação.

## Controles implantados

- Importação somente a partir de arquivo HTML local, sem download ou ativação automáticos.
- Origem declarada restrita a HTTPS e ao host oficial do CONFAZ.
- Hash, referência, versão e quantidade esperada obrigatórios.
- Cada código utilizável precisa ter uma única nota explicativa oficial.
- Código, título, nota, direção e alcance ficam preservados no snapshot.
- Catálogo e itens são somente leitura no painel administrativo.
- A prontidão de homologação exige snapshot CFOP ativo.

## Validações operacionais

- A natureza de operação deve usar CFOP existente e utilizável.
- As emissões atuais do ERP exigem CFOP de saída.
- NFC-e modelo 65 exige saída interna, portanto prefixo `5`.
- NF-e modelo 55 emitida pelo fluxo atual aceita saída interna, interestadual ou exterior, conforme o cenário.
- A pré-emissão bloqueia a divergência antes da reserva de número fiscal.
- Sem catálogo ativo, o sistema preserva compatibilidade de atualização e valida formato/agrupador; a homologação continua bloqueada pelo checklist.

A existência e a direção não determinam qual CFOP deve ser escolhido. Finalidade, origem/destino, tributação, devolução, transferência, bonificação, remessa e demais características precisam estar cobertas pelo cenário fiscal e aprovadas pelo contador.

## Importação

```powershell
python manage.py importar_catalogo_cfop C:\caminho\confaz-ajuste-sinief-07-01.html --versao CONFAZ-AJ-SINIEF-07-01-CONSOLIDADO-2026-08-31 --sha256-esperado f6a40c06d4e56bcf6a650f8cd6c50f1b04d4524f1e9729fbc961539b43ea25e6 --referencia-esperada 2026-08-31 --quantidade-esperada 460 --ativar
```

## Próximo ciclo

Converter os cenários tributários catalogados em fixtures e testes de XML e ampliar o motor para ICMS/ST, PIS, COFINS, IPI e FCP. Em paralelo, iniciar o pacote do contador v2 com os dados fiscais já estruturados.