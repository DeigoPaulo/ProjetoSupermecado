# Cadastro fiscal estruturado do fornecedor

10/09/2026 · ciclo 86 · estrutura cadastral, sem emissão.

## Objetivo

Separar o endereço comercial livre dos dados que futuramente poderão compor a identificação fiscal do destinatário em uma devolução de compra. Esta etapa apenas cria e valida o cadastro; ela não escolhe os dados da NF-e e não consulta serviços externos.

## Campos adicionados

- Indicador de inscrição estadual: contribuinte, isento ou não contribuinte.
- Inscrição estadual.
- Logradouro, número, complemento e bairro fiscais.
- CEP, município, UF e código do município no IBGE.

Todos os campos são opcionais e os registros anteriores permanecem vazios. Não existe CNPJ, IE, endereço ou município fictício como valor padrão.

## Coerência local

- Contribuinte de ICMS exige inscrição estadual.
- Isento, não contribuinte ou indicador vazio não aceitam inscrição estadual preenchida.
- Iniciar qualquer parte obrigatória do endereço fiscal exige logradouro, número, bairro, CEP, município, UF e código IBGE.
- Código IBGE deve ter sete dígitos, UF deve ter duas letras e CEP deve ter oito dígitos, com ou sem hífen.
- Complemento permanece opcional.

## Limites de segurança

O campo antigo de endereço comercial não é alterado pelos novos campos. Os fluxos atuais de importação e preparação de devolução não gravam dados fiscais no fornecedor. O XML original é somente evidência histórica e não pode atualizar o cadastro atual. Esta entrega não gera XML, não acessa certificado ou credencial, não altera Focus/SEFAZ direta e não transmite documento.

## Próximo passo

Construir um contrato de confronto cadastro–XML que compare cada campo sem expor dados além da tela fiscal protegida. Ausência ou divergência deve virar pendência explícita; a comparação não poderá sobrescrever fontes nem autorizar emissão.

## Verificação

A regressão conjunta do cadastro, fluxo de devolução, contrato, identidade e inventário aprovou 101 testes. A migração é somente aditiva e não contém rotina de preenchimento de dados.
