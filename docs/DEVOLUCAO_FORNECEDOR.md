# Devolução ao fornecedor — preparação fiscal segura

Ciclo 72 — 10/09/2026: produtos receberam contrato puro, extração autenticada e painel na prévia. O item liga nItem, snapshot XML, parametrização e memória; valor e classificação só aparecem após aprovação e integridade da cadeia. Unidade/quantidade/valor tributáveis passaram a ser preservados no snapshot. O validador confere formatos, duplicidades e coerência aritmética, sem calcular ou preencher valores. Foram aprovados 99 testes. Próximo passo: bases e valores tributários por item.

Ciclo 71 — 10/09/2026: identificação, emitente e destinatário receberam contrato puro, extração protegida e visualização na prévia. Natureza vem do parecer; dados do emitente vêm da filial/configuração fiscal; dados do destinatário vêm do emitente da NF-e original vinculado ao fornecedor. Campos faltantes são listados, sem defaults. O escopo atual ainda exige CNPJ numérico, e CNPJ alfanumérico permanece bloqueado. Foram aprovados 95 testes. Próximo passo: grupo de produtos.

Ciclo 70 — 10/09/2026: o contrato chave+nItem foi ligado à extração autenticada. O serviço restrito a Administrador/Contabilidade confere empresa, filial, hash do XML, protocolo cStat 100, chave em todas as fontes, modelo 55, partes, nItem e snapshot original. A prévia mostra a matriz de conferências e falha fechado nas divergências. A regressão de 92 testes passou. XML e emissão permanecem bloqueados. Próximo passo: identificação, emitente e destinatário do contrato neutro.

Ciclo 68 — 10/09/2026: referências fiscais por item agora possuem validador puro, com chave/DV, nItem original, duplicidades, proibição de NFref simultâneo e bloqueio explícito de múltiplas origens no escopo inicial. São 10 testes novos, além dos 7 do envelope já existente. A validação não acessa o dossiê, não gera XML e não libera Focus ou SEFAZ. Próximo passo: extração autenticada e confronto com XML/partes.

## Retomada atual — ciclo 67, 10/09/2026

Confronto dos trechos oficiais de devolução registrado em [REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md](REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md). Corrigida a proposta de referência do cabeçalho para chave+nItem original em DFeReferenciado por item. A NT v1.51 indica 05/10/2026 na regra específica, mas tem divergência no histórico: confirmação operacional continua pendente. Documentados pagamento sem pagamento/valor zero e IPI devolvido separado; isso não decide enquadramento tributário nem acerto financeiro do fornecedor.

- [x] Confrontar referência, pagamento e estrutura de IPI devolvido com os trechos oficiais, registrando limites e divergências.
- [x] Implementar e testar validador puro e integrar a extração autenticada de referências por item, sem XML ou emissão (ciclos 68 e 70).
- [ ] Completar análise tributária/RTC, tabelas e vigências; confirmar pacote e hipóteses com o contador antes do gerador/homologação.

Apenas documentação alterada neste ciclo; sem mudança de código executável, banco, configuração, cobrança ou transmissão. Registros abaixo são históricos, não o ponto atual de retomada.

Ciclo 66 — 10/09/2026: bloqueio de obtenção das fontes superado com sessão HTTP/cookies. ZIP oficial 010f e PDFs MOC Anexo I, NT 2025.002 v1.51 e NT 2026.007 v1.00 preservados em docs/evidencias/nfe_2026_09_10, com inventário e hashes no README da pasta. ZIP passou CRC e XSD raiz compilou em memória sem rede; identificação dos PDFs conferida. Não houve instalação, alteração fiscal, banco ou emissão. Leitura normativa integral e validação de vigências permanecem pendentes: próximo passo é confrontar regras de devolução com o contrato e os dados do sistema. Os bloqueios históricos de acesso descritos abaixo não representam mais falta dos arquivos; a aprovação do pacote continua pendente.

- [ ] Bloqueio do ciclo 65: obter arquivos oficiais integrais (ZIP XSD, MOC Anexo I e NT aplicáveis, com origem/versão) para análise local; portal com falha de redirecionamento e sem XSD em fiscal_schemas. Não avançar para geração de XML enquanto a matriz normativa permanecer sem evidência.

Ciclo 64 (09/09/2026): prévia protegida das referências fiscais disponível pela tela de revisão da devolução. Rota somente GET, restrita a Administrador/Contabilidade e à empresa do usuário, com cache desabilitado. Mostra grupos, referências, hashes, pendências e bloqueios, sem edição ou emissão. A etapa de extração do ciclo 63 foi salva no commit 7efa868 após restabelecimento da execução. Próximo passo: obter e analisar integralmente as fontes oficiais e schemas pendentes para fechar a matriz de capacidade fiscal; a prévia não substitui essa validação.

- [x] Ciclo 63: extração de referências do dossiê em serviço somente leitura, restrita à empresa e aos perfis fiscais, com hashes conferidos e pendências separadas. Não equivale a validação completa dos dados fiscais.
- [x] Disponibilizar prévia protegida do contrato e bloqueios na tela de revisão, sem edição manual das referências, XML ou emissão (ciclos 64 e 70).

- [x] Ciclo 62: contrato preliminar de referências e validador estrutural isolado, com sete testes e bloqueios permanentes de XML/emissão.
- [x] Integrar extração autenticada do dossiê ao contrato, verificando escopo, hashes, protocolo, partes, nItem e atualidade no banco (ciclos 63 e 70).

- [x] Ciclo 61: mapeamento preliminar de dados e bloqueios do XML em [CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md](CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md). Não equivale a contrato implementado ou validação normativa.
- [ ] Obter MOC/NT/XSD integrais e confirmar versões/vigências antes de fechar o contrato e gerar XML; as tentativas de leitura integral retornaram erro neste ciclo.

- [x] Ciclo 60: painel de conferência consolidada com estados Registrado, Conferida, Referência, Pendente, Desatualizado, Inconsistente e Bloqueado. Registros com hash íntegro não equivalem a validação fiscal; o painel é somente consulta, sem liberar emissão.
- [ ] Especificar o contrato de dados para XML modelo 55 de devolução, mapeando origem, destino, itens, tributos, transporte, totais e campos ainda não suportados; verificar as fontes oficiais vigentes antes de implementar geração.

- [x] Ciclo 59: corrigir memória revisada devolvida mantendo reflexos, bases finais e histórico; nova versão ligada à decisão de devolução e submetida novamente à revisão (migration 0050). O bloqueio de reutilização direta dos reflexos permanece; somente correção explícita da memória atual devolvida permite nova versão.
- [x] Consolidar o dossiê e apresentar as pendências atuais de preparação, parâmetros, memória, transporte, composição e reflexos antes de desenvolver o XML (ciclo 60; consulta estrutural, sem autorização fiscal).

- [x] Ciclo 58: vínculo da memória revisada aos reflexos aprovados, com bases finais exatas, origem preservada e bloqueio de reaplicação (migration 0049). A seleção é explícita; memória independente não recebe esse vínculo. Alíquotas e impostos continuam informados e sujeitos a revisão.
- [ ] Tratar correção da memória revisada após devolução, preservando a origem aprovada e o histórico, sem reaplicar impactos. Nesta entrega, cada conjunto de reflexos pode originar uma única memória vinculada; repetir o vínculo é bloqueado.

- [x] Ciclo 57: conferência independente dos reflexos nas bases, com aprovação/devolução justificada, decisão única imutável, escopo da empresa e validação da origem atual (migration 0048). Aprovar confere apenas os reflexos declarados; não recalcula impostos nem libera emissão.
- [ ] Vincular os reflexos aprovados à preparação de uma memória tributária revisada, com rastreabilidade da base anterior e sem aplicar o mesmo impacto novamente. A memória aprovada existente permanece intacta.

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
