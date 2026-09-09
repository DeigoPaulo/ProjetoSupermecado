# Devolução ao fornecedor — preparação fiscal segura

Atualizado em 09/09/2026. Documento interno de engenharia e homologação.

## Estado atual

O contrato `supplier_return_fiscal_preparation_v1` faz o diagnóstico documental de uma entrada de compra finalizada. O contrato `supplier_return_draft_v1` preserva o motivo operacional, a seleção de itens e quantidades, o vínculo ao `nItem` e o retrato tributário original. A tela da entrada permite salvar, cancelar ou submeter essa preparação à revisão fiscal, mas não cria NF-e, não reserva série ou número, não escolhe CFOP ou tributação, não movimenta estoque e não chama Focus ou SEFAZ direta.

O cenário continua **bloqueado para emissão**. “Base documental disponível” significa apenas que a entrada possui chave válida, XML integral vinculado pelo DF-e, modelo 55, identidades coincidentes e itens fiscais legíveis.

## Evidências exigidas antes do preenchimento

- [x] Entrada de compra finalizada.
- [x] Chave original com 44 dígitos.
- [x] XML integral preservado em `DocumentoDFeRecebido` e vinculado à entrada.
- [x] Chave do XML idêntica à chave da compra.
- [x] Documento original modelo 55.
- [x] CNPJ do fornecedor igual ao emitente original.
- [x] CNPJ da filial igual ao destinatário original.
- [x] Itens e retrato tributário lidos do XML original, sem consultar o cadastro mutável do produto.

Uma entrada criada por upload direto hoje preserva os dados normalizados e a chave, mas não o XML integral no mesmo registro fiscal. Nesse caso o diagnóstico permanece incompleto; a solução não reconstrói impostos a partir do custo da compra.

## Rascunho operacional

- [x] Criar rascunho próprio ligado à entrada e à chave original, preservando histórico dos cancelados.
- [x] Selecionar itens e quantidades com até três casas decimais e sem exceder o recebido.
- [x] Permitir atualização de apenas um rascunho ativo por entrada.
- [x] Cancelar a preparação para liberar quantidades, sem excluir o histórico.
- [x] Auditar criação, atualização e cancelamento sem gerar efeito fiscal ou de estoque.
- [x] Impedir cancelamento da entrada enquanto houver preparação ativa.
- [x] Preservar o `nItem` em novas importações de NF-e; migration compras 0011.
- [x] Mapear rascunhos legados somente quando existir correspondência única entre os identificadores do produto e do XML.
- [x] Congelar em cada seleção o item fiscal original, incluindo CFOP e valores tributários apenas como evidência.
- [x] Validar a soma dos lotes contra a quantidade do `nItem` original.
- [x] Submeter para revisão com responsável, horário e SHA-256 do XML; migration fiscal 0037.
- [x] Bloquear alterações enquanto o rascunho aguarda revisão fiscal.
- [ ] Considerar no saldo as devoluções efetivamente autorizadas quando essa etapa existir.

## Decisões ainda pendentes

- [ ] Criar a decisão segregada do revisor fiscal, permitindo devolver para correção ou aprovar somente a preparação.
- [ ] Registrar justificativa e responsável pela decisão sem transformar aprovação em autorização para emitir.
- [ ] Definir natureza, CFOP, tratamento de ICMS/ICMS-ST/FCP/IPI/PIS/COFINS e cBenef com o contador.
- [ ] Definir frete, transportador, volumes e motivo quando aplicáveis.
- [ ] Gerar XML modelo 55 com finalidade de devolução e documento referenciado.
- [ ] Validar totais, schemas e regras vigentes com casos aprovados pelo contador.
- [ ] Somente depois homologar, separadamente, Focus e SEFAZ direta.

## Referências oficiais consultadas

- Portal Nacional da NF-e: Manual de Orientação do Contribuinte 7.0, Anexo I, leiaute e regras de validação.
- Portal Nacional da NF-e: notas técnicas vigentes, incluindo as adequações da Reforma Tributária do Consumo.
- Secretaria da Economia de Goiás: página oficial da NF-e e Guia Prático da EFD Goiás.
- CONFAZ: Ajuste SINIEF 07/2005 e tabelas nacionais aplicáveis.

Essas fontes definem o leiaute e as regras técnicas, mas não substituem a interpretação do contador para a operação, produto, regime e vigência reais.
