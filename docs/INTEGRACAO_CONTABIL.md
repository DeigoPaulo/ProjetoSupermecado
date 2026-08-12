# Integração Contábil

## Entrega atual

O perfil **Contabilidade** acessa somente o Portal contábil da empresa vinculada à sua filial. Ele não recebe acesso ao PDV, cadastros, usuários, configurações ou dados de outra empresa.

No portal, escolha a competência e, quando permitido, a filial. O botão **Baixar pacote mensal** gera um arquivo ZIP auditado com:

- resumo gerencial financeiro em JSON;
- lançamentos do livro financeiro em CSV;
- relação dos documentos fiscais do período em CSV;
- XMLs fiscais já gerados e armazenados no ERP;
- manifesto e instruções de uso.

O arquivo segue o contrato `accounting_monthly_package_v1`. O download fica registrado na auditoria como `DOWNLOAD_PACOTE_CONTABIL`.

## Como conceder acesso

1. Um administrador da empresa cria o usuário vinculado a uma filial da própria empresa.
2. Selecione o perfil **Contabilidade**.
3. Oriente o escritório a entrar no menu **Contabilidade > Portal contábil**.

Para um contador com acesso a mais de uma empresa, crie usuários distintos enquanto não houver uma matriz formal de delegação multiempresa. Isso preserva o isolamento de dados desde o início.

## Limites desta fase

O pacote é material gerencial para conferência e entrega ao escritório. Ele **não substitui** SPED, ECD, ECF, apurações, assinaturas, transmissão ou qualquer obrigação legal.

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