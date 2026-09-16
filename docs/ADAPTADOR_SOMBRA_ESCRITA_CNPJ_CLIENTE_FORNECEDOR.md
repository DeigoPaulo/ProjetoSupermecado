# Comparação sombra de CNPJ em Cliente e Fornecedor

16/09/2026 · ciclo 118 · contrato
`alphanumeric_cnpj_customer_supplier_shadow_write_adapter_v1`.

## Escopo

O comparador executa `ClienteForm` e `FornecedorForm` sem salvar. Cliente separa CPF de CNPJ;
CPF permanece fora desta etapa e não é submetido ao portão de CNPJ. Documento vazio continua
permitido nas duas fronteiras. CNPJ é comparado canonicamente apenas dentro da Empresa dona do
cadastro.

## Resultado

Os dois formulários atuais aceitam CNPJ com DV inválido e identidades canonicamente duplicadas.
CNPJ válido mascarado é estruturalmente aceito pelo formulário e pelo portão. CPF do cliente e
campos vazios permanecem preservados. O diagnóstico contém apenas estados e contagens, sem CPF,
CNPJ ou identificadores internos.

## Limites e próximo passo

Nenhum formulário, modelo ou dado foi alterado. A integração futura deve tratar CPF sem aplicar
as regras do CNPJ, canonicalizar somente Cliente PJ/Fornecedor PJ, detectar colisão no escopo da
Empresa e bloquear legado inválido ou troca de identidade. Credenciais, certificados, Focus,
SEFAZ direta, ambientes e emissão continuam fora desta etapa.
