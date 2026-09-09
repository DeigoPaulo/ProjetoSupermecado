# Devolução ao fornecedor — preparação fiscal segura

- [x] Ciclo 56: serviço protegido, histórico imutável e tela dos reflexos vinculados ao rateio atual (migration 0047). Registra responsável, versão e hashes, verifica origem, somas, escopo e atualidade sem mudar a memória aprovada. Somente Administrador/Contabilidade. A etapa operacional antes pendente do ciclo 55 foi implementada.
- [ ] Conferir os reflexos por responsável independente e vinculá-los a uma memória tributária revisada, antes de qualquer geração de XML. Bases declaradas não equivalem a imposto calculado ou validação normativa.

- [x] Ciclo 55: validador isolado dos impactos declarados nas bases por item/tributo, com valores explícitos inclusive zeros, precisão de centavos e totais conferidos. Não valida mérito fiscal nem calcula impostos.
- [x] Integrar o validador a serviço transacional e histórico imutável vinculado ao rateio atual, conferindo empresa, permissões e hashes; tela disponibilizada no ciclo 56. O serviço valida a origem antes do formulário; registro não autoriza emissão.

- [x] Rateio comercial por item (ciclo 54, migration 0046): frete, seguro, despesas e desconto informados, sem distribuição automática. Cada soma confere com a composição aprovada atual; totais por item não podem ser negativos. Histórico versionado e imutável com hashes da composição, revisão e memória. Somente Administrador/Contabilidade. Não define bases tributárias nem libera emissão.

Atualizado em 09/09/2026. Documento interno de engenharia e homologação.

## Estado atual

O contrato `supplier_return_fiscal_preparation_v1` faz o diagnóstico documental de uma entrada finalizada. `supplier_return_draft_v1` preserva motivo, itens, quantidades, `nItem` e retrato tributário original. `supplier_return_fiscal_review_v1` registra a decisão imutável de Administrador ou Contabilidade. Depois da aprovação, `supplier_return_tax_opinion_v1` preserva a orientação profissional global. `supplier_return_item_tax_parameters_v1` registra, em lote completo e versionado, origem e CST ou CSOSN do ICMS, CST/“NA” de IPI, PIS e COFINS, código cBenef GO/“NA” e orientações de ICMS-ST/FCP, cBenef e IBS/CBS para cada item. Por fim, `supplier_return_item_tax_calculation_memory_v1` preserva bases, alíquotas e valores expressamente informados, confere os totais declarados contra a soma dos itens e exige zeros para tributos classificados como não aplicáveis. Nenhuma dessas ações cria NF-e, reserva série ou número, define fórmulas tributárias, movimenta estoque ou chama Focus/SEFAZ direta.

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
- [x] Restringir a fila de revisão a Administrador e Contabilidade, excluindo Compras e Financeiro.
- [x] Registrar aprovação ou devolução para correção com responsável, justificativa, sequência, snapshot do conteúdo e SHA-256 imutáveis; migration fiscal 0038.
- [x] Reabrir o mesmo rascunho quando devolvido para correção e preservar todo o histórico anterior.
- [x] Manter a preparação aprovada bloqueada para edição/cancelamento em Compras e sem qualquer autorização emissiva.
- [x] Registrar parecer tributário append-only somente sobre preparação aprovada, com versões idempotentes e snapshot integral; migration fiscal 0039.
- [x] Exigir data, regime e natureza informados pelo responsável e CFOP de saída presente no catálogo oficial vigente.
- [x] Exigir declaração explícita para ICMS, ICMS-ST/FCP, IPI, PIS, COFINS, cBenef e IBS/CBS, sem defaults ou cálculo automático.
- [x] Registrar ficha completa por `nItem`, vinculada a uma versão explícita do parecer e sem copiar automaticamente a tributação de entrada; migration fiscal 0040.
- [x] Validar origem e formato de CST/CSOSN e exigir `NA` explícito para IPI/PIS/COFINS e cBenef quando não aplicáveis.
- [x] Versionar e deduplicar o lote inteiro, preservando responsável, parecer, XML e conteúdo por SHA-256.
- [x] Registrar memória de cálculo completa por `nItem`, vinculada à versão explícita dos parâmetros, com bases, alíquotas e valores informados e sem copiar o XML original; migration fiscal 0041.
- [x] Exigir zeros explícitos para ICMS/IPI/PIS/COFINS classificados como não aplicáveis e validar casas decimais, não negatividade e limite dos valores.
- [x] Conferir o total da operação e os totais de base/valor de ICMS, ICMS-ST, FCP, IPI, PIS, COFINS, IBS e CBS contra a soma de todos os itens antes de gravar atomicamente.
- [x] Preservar memória, parâmetros, parecer e XML por snapshot/SHA-256, com versões append-only e idempotentes exclusivas de Administrador/Contabilidade.
- [ ] Considerar no saldo as devoluções efetivamente autorizadas quando essa etapa existir.

## Decisões ainda pendentes

- [x] Criar a decisão segregada do revisor fiscal, permitindo devolver para correção ou aprovar somente a preparação.
- [x] Registrar justificativa e responsável pela decisão sem transformar aprovação em autorização para emitir.
- [x] Modelar o parecer tributário versionado que recebe as decisões explícitas do contador, sem sugerir valores por padrão.
- [x] Estruturar parâmetros fiscais por `nItem`, vinculados a uma versão do parecer e sem preenchimento automático.
- [x] Criar memória de cálculo por item com bases, alíquotas e valores exclusivamente informados, sem gerar XML.
- [x] Criar revisão segregada da memória completa; migration fiscal 0042. Somente outro Administrador/Contabilidade decide sobre a versão mais recente, com justificativa, hash e decisão única imutável. Correções exigem nova versão. Aprovação não libera XML/emissão.
- [ ] Estruturar dados de transporte e composição do valor da devolução para posterior conferência contábil.
- [ ] Definir natureza, CFOP, tratamento de ICMS/ICMS-ST/FCP/IPI/PIS/COFINS e cBenef com o contador.
- [x] Registrar modalidade de frete, transportador e volumes em ficha logística versionada vinculada à memória aprovada mais recente; migration 0043. Dados informados, ainda sem geração fiscal.
- [x] Registrar composição comercial versionada: base da memória aprovada + frete + seguro + despesas − desconto, total declarado conferido, zeros explícitos e confirmação de ausência de duplicidade; migration 0044. Não representa vNF nem cálculo tributário.
- [x] Implementar revisão da composição por outro responsável, decisão única por versão e orientação explícita para ICMS/ST/FCP, IPI, PIS/COFINS e IBS/CBS na aprovação; migration 0045. Devolução preserva histórico e exige nova composição.
- [ ] Obter orientação e aceite do contador com dados reais; converter orientações em regras estruturadas e validar reflexos sobre as bases antes do XML.
- [ ] Gerar XML modelo 55 com finalidade de devolução e documento referenciado.
- [ ] Validar totais, schemas e regras vigentes com casos aprovados pelo contador.
- [ ] Somente depois homologar, separadamente, Focus e SEFAZ direta.

## Referências oficiais consultadas

A ficha logística é uma preparação de dados, não uma validação fiscal completa. CPF/CNPJ numérico informado é validado por dígitos verificadores. Nas modalidades 3/4, a identidade corresponde à raiz do CNPJ ou CPF do remetente/destinatário da devolução, invertendo os papéis do XML original. Documento ausente não dispara essa comparação. CNPJ alfanumérico, demais regras de transporte e homologação ainda permanecem pendentes. A modalidade 9 bloqueia o grupo transportador conforme X03-30 da [NT 2021.004 v1.33](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=i0rK6ogxnx8%3D), consultada em 09/09/2026. A composição de valores e a conferência contábil permanecem pendentes.

- Portal Nacional da NF-e: Manual de Orientação do Contribuinte 7.0, Anexo I, leiaute e regras de validação.
- Portal Nacional da NF-e: notas técnicas vigentes, incluindo as adequações da Reforma Tributária do Consumo.
- Secretaria da Economia de Goiás: página oficial da NF-e e Guia Prático da EFD Goiás.
- CONFAZ: Ajuste SINIEF 07/2005 e tabelas nacionais aplicáveis.

Essas fontes definem o leiaute e as regras técnicas, mas não substituem a interpretação do contador para a operação, produto, regime e vigência reais.
