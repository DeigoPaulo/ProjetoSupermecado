# Confronto do cadastro do fornecedor com o XML histórico

10/09/2026 · ciclo 87 · diagnóstico não emissivo.

## Contrato

`supplier_return_supplier_registration_xml_comparison_v1` compara 13 campos: CNPJ, razão social, nome fantasia, indicador de IE, inscrição estadual, logradouro, número, complemento, bairro, município, código IBGE, UF e CEP.

Cada campo recebe um dos estados: coincidente, divergente, ausente no cadastro, ausente no XML, ausente em ambos ou informado somente no cadastro quando não existe equivalente direto no emitente histórico.

## Normalização

A comparação ignora apenas diferenças de apresentação: pontuação em CNPJ, IE e CEP; caixa; separadores; e acentos em texto. Os valores originais das duas fontes continuam intactos. Mudança de palavra, número, município, UF ou outro conteúdo permanece divergência.

## Proteções

- O contrato não define fonte preferencial.
- Cadastro e XML não podem ser sobrescritos.
- O resultado é calculado em memória e não é persistido.
- Estado, resumo e política são recalculados pelo validador para detectar adulteração.
- Mesmo sem divergências, decisão humana, indicador do destinatário, regras e homologação continuam pendentes.
- XML, Focus, SEFAZ direta e emissão permanecem bloqueados.
- A visualização usa a prévia já restrita aos perfis Administração e Contabilidade; Compras e Financeiro não recebem acesso.

## Resultado do ciclo

A antiga lacuna `CADASTRO_FORNECEDOR_NAO_CONFRONTADO_COM_XML` foi encerrada. O inventário passou a oito lacunas estruturais. A regressão conjunta aprovou 107 testes e confirmou que uma divergência não altera o cadastro nem cria documento fiscal.

## Próximo passo

O `indIEDest` candidato foi incorporado no ciclo 88 e permanece não confirmado. O próximo passo é modelar `indTot` por item sem valor padrão e sem alterar totalização.
