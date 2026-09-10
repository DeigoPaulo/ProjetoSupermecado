# Inventário atômico de dados da devolução

10/09/2026 · ciclo 85 · diagnóstico somente leitura.

O contrato `supplier_return_atomic_data_inventory_v1` acompanha 106 campos atômicos dos blocos de identificação, partes, referências, produtos, tributos, ajustes, transporte, totais, pagamento fiscal, observações, IPI devolvido, ICMS-ST/FCP e RTC. O inventário não inclui os valores: registra apenas fonte, ocorrências, quantidade preenchida e estado de disponibilidade.

## Fontes reconhecidas

| Fonte | Uso no contrato |
|---|---|
| Cadastro da filial e configuração fiscal | Emitente, endereço, município IBGE, IE e CRT. |
| XML original autorizado | Destinatário da devolução, identidade/classificação histórica dos produtos e unidades. |
| Rascunho | Quantidade efetivamente selecionada para devolução. |
| Parecer e parametrização do contador | Natureza, CFOP, códigos e hipóteses tributárias. |
| Memória aprovada | Valores, bases, alíquotas e tributos informados. |
| Rateio/reflexos aprovados | Frete, seguro, despesas e desconto por item. |
| Ficha de transporte | Modalidade, transportador e volumes. |
| Política documental | `tPag=90` e `vPag=0.00`. |
| Texto fiscal aprovado | Futuro `infAdic`/`infAdProd`, hoje intencionalmente vazios. |
| Vigência e contador | IPI devolvido, ST/FCP e RTC ainda não definidos. |

## Lacunas de modelagem confirmadas

1. `indIEDest` ainda não existe no contrato de destinatário.
2. Fornecedor possui CNPJ, razão social e endereço livre, mas não possui IE, indicador de IE, CEP/endereço fiscal estruturado, UF/município e código IBGE em campos próprios.
3. `indTot` ainda não está modelado no produto da devolução.
4. Modalidade de base do ICMS ainda não está modelada.
5. Redução da base de ICMS ainda não está modelada.
6. Enquadramento legal `cEnq` do IPI não está no contrato da devolução.
7. Variantes de cálculo de PIS/COFINS ainda não estão discriminadas.
8. Gerador específico de XML da devolução não existe.
9. O conversor Focus não possui paridade para todos os grupos da devolução.

## Regra de segurança cadastral

O XML original é evidência histórica e pode fornecer dados da operação recebida. Ele não atualiza nem substitui automaticamente o cadastro fiscal vigente do fornecedor. Uma futura conferência deve mostrar divergências entre cadastro e XML para decisão humana, sem sobrescrever nenhum dos dois lados.

## Próximo marco

Estruturar no cadastro do fornecedor IE, indicador de IE e endereço fiscal em campos próprios, com município IBGE e validações locais. Os campos devem permanecer opcionais enquanto não houver dados reais, sem defaults e sem importação automática do XML. Depois, o contrato de identidade poderá confrontar cadastro atual e XML histórico e manter qualquer divergência como bloqueio não emissivo.
