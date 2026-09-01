# Integração Contábil

## Entrega atual

O perfil **Contabilidade** acessa somente o Portal contábil da empresa vinculada à sua filial. Ele não recebe acesso ao PDV, cadastros, usuários, configurações ou dados de outra empresa.

No portal, escolha a competência e, quando permitido, a filial. O botão **Baixar pacote mensal** gera um arquivo ZIP auditado com:

- resumo gerencial financeiro e lançamentos do livro em JSON/CSV;
- documentos fiscais de saída e de entrada em relações separadas;
- itens fiscais extraídos do XML armazenado, incluindo CFOP, NCM, CEST, CST/CSOSN, cBenef, bases, alíquotas, ICMS/ST, FCP, PIS, COFINS e IPI quando presentes;
- XMLs de saída, entrada, cancelamento, CC-e, manifestação e eventos recebidos;
- situação, protocolos, data de emissão, data de autorização disponível e fonte usada para definir a competência;
- posição atual de estoque valorizada pelo custo médio ponderado móvel, com qualidade temporal explícita;
- reconciliação somente leitura de vendas, pagamentos confirmados, livro financeiro, documentos fiscais, entradas de compras, contas a pagar e movimentos de estoque, com códigos de divergência por origem;
- manifesto com contagens, tamanho e SHA-256 de cada arquivo.

O arquivo segue o contrato `accounting_monthly_package_v2`. Durante a transição, os caminhos principais do v1 (`fiscal/documentos.csv` e `fiscal/xml/`) são mantidos e o manifesto declara a compatibilidade. O download fica registrado na auditoria como `DOWNLOAD_PACOTE_CONTABIL`. O manifesto e a API também informam o estado do `accounting_integration_agreement_v1`, que registra formato, destino e responsabilidade externa pela EFD sem armazenar segredos ou dados comerciais.

A competência fiscal prioriza `dhEmi`/`dEmi` do XML. Documentos legados sem essa informação usam `xml_gerado_em` e, por último, `criado_em`; o fallback aparece no CSV para conferência. XML ausente ou inválido gera uma pendência explícita e não interrompe a exportação dos demais documentos.

## Como conceder acesso

1. Um administrador da empresa cria o usuário vinculado a uma filial da própria empresa.
2. Selecione o perfil **Contabilidade**.
3. Oriente o escritório a entrar no menu **Contabilidade > Portal contábil**.

Para um contador com acesso a mais de uma empresa, crie usuários distintos enquanto não houver uma matriz formal de delegação multiempresa. Isso preserva o isolamento de dados desde o início.

## Limites desta fase

O pacote é material gerencial para conferência e entrega ao escritório. Ele **não substitui** SPED, ECD, ECF, EFD ICMS/IPI, apurações, assinaturas, transmissão ou qualquer obrigação legal.

O inventário usa o `custo_medio` por filial/produto, calculado pelo ERP como custo médio ponderado móvel nas entradas. Um fechamento imutável por filial/data congela os dados dos itens e seu SHA-256; quando todas as filiais do pacote possuem fechamento na data final, o manifesto indica `SNAPSHOT_IMUTAVEL_FECHAMENTO`. Sem cobertura completa, o arquivo usa `POSICAO_NO_FECHAMENTO` no próprio dia ou `POSICAO_ATUAL_NAO_RETROATIVA` em períodos passados. Consulte `docs/FECHAMENTO_ESTOQUE_CONTABIL.md`.

A reconciliação operacional estrutural do v2 está concluída e é somente leitura: ela aponta diferenças, mas não altera venda, documento, estoque, conta ou obrigação. A estrutura versionada e imutável do contrato com a contabilidade também está pronta. O validador local `accounting_monthly_sample_validation_v1` confere integridade do ZIP, XMLs, reconciliação e fechamento imutável, e permite ao Master registrar um aceite imutável vinculado ao SHA-256. Ainda faltam para concluir e aceitar o v2 com dados reais: registrar a definição do software e do responsável pela EFD ICMS/IPI, submeter uma amostra real ao contador e arquivar sua referência de aceite. Consulte `docs/CONTRATO_INTEGRACAO_CONTABIL.md` e `docs/VALIDACAO_AMOSTRA_CONTABIL.md`.

Antes de automatizar obrigações oficiais, deve-se homologar com o contador responsável:

- regime tributário e enquadramento de cada empresa;
- UF, município, séries e documentos fiscais utilizados;
- plano de contas e centros de custo exigidos pelo escritório;
- layout, certificado, assinatura e validador oficial aplicável.

## API somente leitura

O administrador acessa **Sistema > Integração contábil** para gerar uma chave por empresa. A chave é exibida uma única vez, persistida somente como SHA-256 e pode ser revogada a qualquer momento.

```text
GET /api/contabilidade/v1/pacote-mensal/?competencia=AAAA-MM
X-Contabilidade-Key: dvc_sua_chave
```

Em produção, a API exige HTTPS. A chave nunca deve ser enviada por URL, e cada consulta registra uma auditoria. O retorno segue o contrato `accounting_monthly_api_v1` e respeita integralmente a empresa da chave; uma filial de outra empresa retorna bloqueio.
