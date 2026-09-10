# Contrato proposto do XML de devolução ao fornecedor

Ciclo 92 — 10/09/2026: `cEnq` foi modelado como candidato vazio e não confirmado, com destino futuro `det/imposto/IPI/cEnq`. O XSD o exige apenas quando o grupo IPI existe; a aplicação do grupo e o código permanecem decisões contábeis. Cadastro, XML histórico e memória não são fontes automáticas. O inventário soma 111 campos e três lacunas; 153 testes passaram. Próximo passo: variantes de PIS/COFINS.

Ciclo 91 — 10/09/2026: o grupo ICMS recebeu `reducao_base_candidata`, fonte contábil pendente e confirmação falsa. Percentual com formato válido continua bloqueado e não altera a base da memória. Nenhuma fonte cadastral ou histórica é copiada. O inventário soma 110 campos e quatro lacunas; 149 testes passaram. Próximo passo: `cEnq` do IPI.

Ciclo 90 — 10/09/2026: o grupo ICMS recebeu `modalidade_base_candidata`, fonte contábil pendente e confirmação falsa. Códigos 0 a 3 são apenas formatos reconhecidos pelo XSD; candidato preenchido continua bloqueado. A decisão não altera `vBC`, memória ou totalização e não chega aos adaptadores. O inventário soma 109 campos e cinco lacunas; 147 testes passaram. Próximo passo: `pRedBC`.

Ciclo 89 — 10/09/2026: `indTot` entrou no contrato de produtos somente como candidato vazio, fonte `DECISAO_FISCAL_PENDENTE` e confirmação falsa. 0 e 1 não são aplicados automaticamente. A totalização diagnóstica passou a distinguir origem comercial completa de decisão fiscal pendente e continua sem formar `vNF`. O inventário soma 108 campos e seis lacunas; 145 testes passaram. Próximo passo: modalidade da base do ICMS (`modBC`).

Ciclo 88 — 10/09/2026: o destinatário recebeu `indicador_ie_candidato`, fonte cadastral fixa e confirmação falsa. O validador aceita 1, 2 ou 9 apenas como candidato pendente, recusa confirmação direta e não permite aplicação, XML ou emissão. A prévia restrita mostra o bloqueio. O inventário soma 107 campos e sete lacunas; 107 testes passaram. Próximo passo: modelar `indTot` sem default.

Ciclo 87 — 10/09/2026: criado `supplier_return_supplier_registration_xml_comparison_v1` para confrontar 13 campos atuais e históricos. O validador recalcula estados e resumo, recusa política alterada e nunca permite sobrescrita ou canal fiscal. A prévia restrita exibe as duas fontes para conferência humana. O inventário passou a oito lacunas e 107 testes integrados passaram. Próximo passo: `indIEDest` candidato no contrato de identidade, ainda não emissivo.

Ciclo 86 — 10/09/2026: o cadastro fiscal estruturado do fornecedor foi criado com dez campos opcionais e validações locais. O contrato ainda usa o XML original como fonte histórica do destinatário; por isso, a antiga lacuna cadastral foi substituída por `CADASTRO_FORNECEDOR_NAO_CONFRONTADO_COM_XML`. Nenhuma fonte é sobrescrita, os canais continuam bloqueados e 101 testes integrados passaram. Próximo passo: contrato explícito de comparação cadastro–XML.

Ciclo 85 — 10/09/2026: implementado `supplier_return_atomic_data_inventory_v1`, com 106 campos e nove lacunas fixadas por validador. O resultado nunca inclui valores, não aceita remover lacunas, expor conteúdo ou liberar serialização. A principal lacuna cadastral é o fornecedor sem IE, indicador IE, endereço fiscal estruturado e município IBGE. O XML original continua apenas como origem histórica. A prévia foi ampliada e 138 testes passaram.

Ciclo 84 — 10/09/2026: implementada a classificação `supplier_return_field_requirement_matrix_v1`. Cada família registra cardinalidade, categoria, fontes, dependência do contador e vigência operacional. O validador rejeita promoção de regra, aprovação antecipada e qualquer aplicação. `DFeReferenciado`, pagamento, IPI devolvido e RTC mantêm as distinções documentais próprias. A prévia foi ampliada e 135 testes passaram. Próximo passo: granularidade atômica e inventário de disponibilidade dos dados.

Ciclo 83 — 10/09/2026: implementada a matriz executável `supplier_return_layout_traceability_v1`, cobrindo 37 famílias dos 13 contratos. Cada linha registra caminho neutro, destino XSD, cobertura do conversor Focus, passagem sem reconstrução pela SEFAZ direta e serialização local obrigatoriamente falsa. Isso demonstra que o transporte direto não completa conteúdo e que o conversor Focus atual perderia grupos relevantes. A prévia foi ampliada e 132 testes passaram. A classificação normativa de obrigatoriedade é o próximo bloqueio.

Ciclo 82 — 10/09/2026: implementado `supplier_return_readiness_gate_v1`, que consolida os 13 subcontratos sem convertê-los em autorização. O validador falha fechado diante de contrato divergente, origem incompleta ou tentativa de liberar XML/emissão. Análise normativa integral, matriz tributária aprovada, dados reais, casos do contador, schema aplicável e paridade separada de Focus/SEFAZ direta permanecem falsas e visíveis. A prévia protegida foi ampliada e 129 testes passaram. O próximo passo é a matriz campo a campo contrato–leiaute/XSD–adaptadores, sem serialização.

Ciclo 81 — 10/09/2026: implementado `supplier_return_rtc_vigency_policy_v1`. O contrato registra a NT 2026.007 v1.00, hash, páginas e datas documentais, sem ativação por calendário. IBS/CBS da memória são apenas referência; enquadramento, classificação, grupos e totais ficam vazios até confirmação de vigência, implantação GO, leiaute e homologação. Foram aprovados 126 testes.

Ciclo 80 — 10/09/2026: implementado `supplier_return_icms_st_fcp_hypothesis_v1`. A memória é preservada apenas como referência; hipótese, grupos de destino, informação complementar e totais ficam vazios. Inferência por código/regime e generalização das orientações GO 21305/21349 são proibidas. Não há serialização; 123 testes passaram.

Ciclo 79 — 10/09/2026: implementado `supplier_return_returned_ipi_policy_v1`. O contrato preserva o IPI informado na memória somente como referência e cria campos separados, vazios e bloqueados para `pDevol`, `vIPIDevol`, justificativa e total. Cópia ou cálculo automático é erro. Não há serialização de `impostoDevol`; 120 testes passaram.

Ciclo 78 — 10/09/2026: implementado `supplier_return_fiscal_notes_policy_v1`. O contrato inventaria fontes internas por IDs, hashes e contagens, sem copiar seu conteúdo. `infAdic` e `infAdProd` ficam vazios e o validador rejeita exportação automática ou texto não aprovado. Ainda não há serialização; 117 testes passaram.

Ciclo 77 — 10/09/2026: implementado `supplier_return_fiscal_payment_policy_v1`. A política isolada exige `tPag=90`, `vPag=0.00`, devolução modelo 55/finalidade 4 e nenhum efeito operacional. Total comercial não pode alimentar o pagamento. Ainda não há serialização de `pag/detPag`; regras complementares e homologação permanecem bloqueadas. Foram aprovados 114 testes.

Ciclo 76 — 10/09/2026: implementado `supplier_return_diagnostic_totals_v1`. Ele consolida valores comerciais e tributários já informados quando produtos, tributos e ajustes pertencem à mesma memória aprovada. A soma é apenas conferência; `vNF`, IPI devolvido e totais RTC não podem ser preenchidos. O mapeamento XML segue bloqueado e 111 testes passaram.

Ciclo 75 — 10/09/2026: implementado `supplier_return_transport_input_v1`. O contrato somente lê a ficha logística vinculada à memória final aprovada, confere a cadeia de hashes e valida modalidade, transportador, CPF/CNPJ, volumes e pesos. Ficha ausente ou superada permanece pendente. O grupo XML `transp` não é produzido; 108 testes passaram.

Ciclo 74 — 10/09/2026: implementado `supplier_return_commercial_adjustments_v1`. O contrato replica o rateio somente quando a cadeia final de reflexos e memória está aprovada, confere linhas e totais e mantém hashes das duas etapas históricas. Frete, seguro, despesas e desconto não são somados novamente a bases já revisadas. O mapeamento XML continua bloqueado; 105 testes passaram.

Ciclo 73 — 10/09/2026: implementado `supplier_return_item_tax_values_v1`. O contrato replica os números da memória aprovada, exige seus hashes e vínculo por item e não contém fórmula tributária. Os estados dos grupos impedem confundir números informados com suporte ao XML: matriz de ICMS/PIS/COFINS, hipótese ST/FCP, grupo próprio de IPI devolvido e vigência IBS/CBS continuam pendentes. A prévia protegida foi ampliada e 102 testes passaram.

Ciclo 72 — 10/09/2026: implementado `supplier_return_products_v1`. O contrato recebe dados comerciais do snapshot original e CFOP, valor da operação e classificação da cadeia de memória aprovada. A extração não usa o cadastro mutável para substituir o retrato fiscal nem calcula valores ausentes. Quantidade × unitário é somente uma conferência do valor expressamente informado. Unidade, quantidade e valor tributáveis foram incluídos no analisador documental. Geração, XSD e transmissão seguem bloqueados; 99 testes passaram.

Ciclo 71 — 10/09/2026: implementado o contrato não emissivo `supplier_return_identity_parties_v1`. Identificação fixa apenas modelo/finalidade/direção; natureza vem do parecer e decisões ainda não confirmadas permanecem vazias. Emitente usa filial e configuração fiscal sem credenciais. Destinatário usa o emitente preservado no XML original e o ID do fornecedor. O validador separa formato de completude e bloqueia CNPJ alfanumérico, vigências, XML e homologação. A prévia protegida mostra as pendências; 95 testes passaram.

Ciclo 70 — 10/09/2026: a referência por item deixou de ser apenas uma entrada arbitrária do validador. A extração protegida monta chave+nItem do rascunho e cruza DF-e, empresa, filial, hash congelado, protocolo autorizado, modelo, chave em todas as fontes, emitente/fornecedor, destinatário/filial e snapshot de cada nItem. A prévia somente leitura apresenta os resultados. Isso autentica a origem interna da referência, mas não valida assinatura digital, mérito tributário, vigência ou XSD e não gera XML.

Ciclo 68 — 10/09/2026: validador puro de referências por item implementado com política explícita, DV da chave, nItem original, duplicidades e proibição de NFref no cabeçalho. Múltiplas origens não são declaradas inválidas pela SEFAZ, mas ficam fora do escopo inicial. O resultado sempre bloqueia XML e emissão. Dez testes novos e sete testes do envelope passaram; próximo passo é extrair e confrontar esses dados com o XML original no serviço autenticado.

Ciclo 67 — 10/09/2026: [confronto documental](REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md) corrigiu a proposta de referência para `det/DFeReferenciado` com chave e nItem original, conforme NT 2025.002 v1.51. Cronograma contém divergência histórica registrada; não há ativação automática. Pagamento sem pagamento/valor zero e grupo próprio de IPI devolvido documentados, sem implementação fiscal. Próximo passo: validador isolado de referências por item e testes, mantendo XML/emissão bloqueados.

Ciclo 66 — 10/09/2026: bloqueio de obtenção das fontes superado com sessão HTTP/cookies. ZIP oficial 010f e PDFs MOC Anexo I, NT 2025.002 v1.51 e NT 2026.007 v1.00 preservados em docs/evidencias/nfe_2026_09_10, com inventário e hashes no README da pasta. ZIP passou CRC e XSD raiz compilou em memória sem rede; identificação dos PDFs conferida. Não houve instalação, alteração fiscal, banco ou emissão. Leitura normativa integral e validação de vigências permanecem pendentes: próximo passo é confrontar regras de devolução com o contrato e os dados do sistema. Os bloqueios históricos de acesso descritos abaixo não representam mais falta dos arquivos; a aprovação do pacote continua pendente.

Verificação do ciclo 65 (09/09/2026): nenhum XSD foi encontrado em `fiscal_schemas`; a pasta contém apenas README.md. O endereço de schemas indicado no README retornou redirecionamento circular na nova consulta. A leitura integral dos documentos e a fixação do pacote permanecem bloqueadas. Solicitar ZIP oficial, MOC Anexo I e NT aplicáveis, com URL/versão de origem, para análise local. Não instalar ou ativar o pacote antes de conferir o conjunto. Nenhuma regra fiscal foi implementada nesta verificação.

Ciclo 64 (09/09/2026): prévia protegida das referências fiscais disponível pela tela de revisão da devolução. Rota somente GET, restrita a Administrador/Contabilidade e à empresa do usuário, com cache desabilitado. Mostra grupos, referências, hashes, pendências e bloqueios, sem edição ou emissão. A etapa de extração do ciclo 63 foi salva no commit 7efa868 após restabelecimento da execução. Próximo passo: obter e analisar integralmente as fontes oficiais e schemas pendentes para fechar a matriz de capacidade fiscal; a prévia não substitui essa validação.

Atualização do ciclo 63: `extrair_contrato_devolucao(rascunho_id, usuario)` consulta o banco com escopo de empresa e perfil fiscal, extrai IDs/hashes e retorna `conteudo`, `validacao` e `pendencias_dossie`. Os grupos sem mapeamento fiscal permanecem NAO_SUPORTADO. A extração inclui decisões disponíveis e cadeia de memórias; referências íntegras não substituem aprovações pendentes. Não expõe XML ou credenciais, não grava dados e não fornece endpoint público. A prévia em tela ainda está pendente. O validador puro continua sem autenticar entradas arbitrárias: a autorização pertence ao serviço de extração.

09/09/2026 · ciclo 61 · especificação preliminar, não implementada.

Atualização do ciclo 62: implementado somente o envelope de referências e seu validador estrutural em `apps/fiscal/contrato_devolucao.py`. Ainda não é o contrato completo de dados fiscais nem possui extração autenticada, tela ou endpoint. Sete testes passaram.

O envelope exige `contrato`, `rascunho_id`, `empresa_id`, `modelo=55`, `operacao=DEVOLUCAO_COMPRA`, `permite_emissao=false` e `grupos`. Cada grupo conhecido contém `estado` e lista `referencias` (tipo, ID positivo, SHA-256). Os estados são AUSENTE, DIVERGENTE, SUPERADO, NAO_SUPORTADO e REFERENCIADO. Este último indica apenas presença sintática de evidência, nunca aprovação. Campos desconhecidos são rejeitados; não enviar tokens, certificado, XML ou dados pessoais no envelope. O resultado separa erros estruturais de bloqueios fiscais e sempre retorna `permite_gerar_xml=false` e `permite_emissao=false`. IDs e hashes ainda precisam ser resolvidos e conferidos por serviço autenticado.

Nova evidência oficial: o [aviso de 04/08/2026](https://www.nfe.fazenda.gov.br/pOrtal/informe.aspx?AspxAutoDetectCookieSupport=1&Informe=k7zG06n5M6I%3D&ehCTG=false) confirma a publicação da NT 2025.002 v1.51, juntamente com outras notas. Isso resolve a dúvida sobre a existência dessa versão, não confirma ausência de versões posteriores nem substitui a leitura integral e verificação de vigência/XSD, que permanecem pendentes.

## Decisão de engenharia

Criar futuramente um contrato neutro `supplier_return_nfe_input_v1`, independente de Focus e SEFAZ direta. Seu primeiro consumidor será um validador somente leitura. Não reutilizar o despacho de venda para emitir devolução. O dossiê atual informa pendências, mas não é autorização fiscal.

Escopo inicial proposto: devolução de compra pelo supermercado ao fornecedor, uma NF-e de origem, modelo 55. Retorno, recusa de entrega, entrada emitida pelo vendedor, múltiplas referências e operações especiais ficam fora desse primeiro contrato. Não inferir CFOP, CST, regime, incidência ou pagamento a partir do XML de compra.

## Mapeamento e bloqueios

| Grupo do contrato | Fonte existente | Destino XML proposto | Condição para avançar |
|---|---|---|---|
| origem | rascunho, chave, XML e hashes | `det/DFeReferenciado/chaveAcesso` e `nItem`, conforme política/vigência conferida | Validar chave, modelo, partes, duplicidade e ausência de NFref simultâneo; não confundir nItem original com a sequência do novo documento; ver confronto do ciclo 67 |
| identificação | parecer, filial e configuração | `ide`: modelo, finalidade, direção, destino e natureza | Contrato/extrator implementados no ciclo 71; consumidor final, presença, vigência e caso real ainda pendentes |
| emitente | filial/configuração fiscal | `emit` e endereço | Contrato/extrator implementados; completar IE, CRT, município e endereço reais na filial |
| destinatário | fornecedor e XML de origem | `dest` e endereço | Snapshot original estruturado; cadastro atual ainda não possui IE/endereço estruturado e exige evolução antes da emissão |
| produtos | itens selecionados, snapshot original e memória aprovada | `det/prod` | Contrato/extrator implementados no ciclo 72; paridade XSD, conversões especiais e cenários reais ainda pendentes |
| classificação | parametrização aprovada por item | grupos CST/CSOSN e CFOP | Matriz de capacidade por grupo, regime e vigência; código cadastrado não garante suporte à serialização |
| bases e valores | memória revisada aprovada | `det/imposto` | Contrato/extrator implementados no ciclo 73; matriz por hipótese e serialização continuam bloqueadas |
| ajustes comerciais | composição, rateio, reflexos e memória final | frete, seguro, despesas e desconto por produto | Contrato/extrator implementados no ciclo 74; mapeamento XML permanece bloqueado |
| IPI devolvido | contrato separado com IPI da memória apenas como referência | eventual `impostoDevol` e total correspondente | Estrutura bloqueada implementada no ciclo 79; hipótese, valores, justificativa, total e serialização dependem de aprovação específica |
| ICMS-ST/FCP | contrato de hipótese com memória apenas como referência | grupos específicos e/ou informações complementares conforme hipótese | Estrutura bloqueada implementada no ciclo 80; hipótese, grupos, texto, totais e serialização exigem aprovação do caso real |
| IBS/CBS | contrato de vigência com memória apenas como referência | grupos RTC do leiaute vigente | Estrutura bloqueada implementada no ciclo 81; implantação GO, enquadramento, classificação, leiaute, totais e homologação não confirmados |
| transporte | ficha logística | `transp` | Contrato/extrator implementados no ciclo 75; serialização, paridade XSD e casos reais continuam bloqueados |
| total fiscal | diagnóstico de produtos, ajustes e tributos informados | `total` | Contrato/extrator diagnóstico no ciclo 76; `vNF`, IPI devolvido, totais RTC e serialização permanecem bloqueados |
| pagamento | política isolada e não emissiva | `pag/detPag`: `tPag=90`, `vPag=0.00` no escopo proposto | Contrato/extrator implementados no ciclo 77; serialização e regras complementares continuam bloqueadas; nenhum efeito operacional |
| observações | inventário de parecer, itens, memória e transporte | `infAdic` e `infAdProd` | Contrato/extrator implementados no ciclo 78; textos permanecem vazios até aprovação específica e serialização segue bloqueada |
| envelope técnico | somente na futura emissão | número, série, chave, datas, ambiente, assinatura | Fora do validador preliminar; sem reserva de número, certificado, chamada externa ou XML nesta etapa |

O contrato deve transportar IDs e hashes de todas as origens e decisões, além da cadeia de correção da memória. Deve registrar `permite_emissao=false` no estágio preliminar. O resultado do validador deverá distinguir ausência, divergência, origem superada e grupo não suportado. Qualquer grupo desconhecido bloqueia; nunca omitir silenciosamente.

## Acoplamentos constatados no código

- `apps/fiscal/services.py`: `salvar_xml_documento` encaminha todo modelo 55 para `gerar_xml_nfe_pedido_online`. O gerador escreve finalidade normal e consumidor final. É necessário despacho explícito por origem/operação antes de acrescentar devolução.
- `apps/fiscal/services.py`: a totalização atual escreve `vIPIDevol` zero. Não representa suporte a imposto devolvido.
- `apps/fiscal/focus_sefaz_adapter.py`: `_payload_xml` lê finalidade, mas não mapeia `NFref` no payload observado. `_item` cobre apenas parte dos grupos tributários e comerciais necessários. Antes de liberar o canal Focus, auditar a documentação oficial do provedor e testar paridade campo a campo. Ler finalidade não basta.
- SEFAZ direta deve consumir XML validado por schema/regras; a existência do transporte SOAP não demonstra suporte ao conteúdo de devolução. Não mudar flags, permissões ou ambientes nesta especificação.

## Fontes consultadas e limitações

- [Portal Nacional: MOC e anexos](https://www.nfe.fazenda.gov.br/PORTAl/listaConteudo.aspx?AspxAutoDetectCookieSupport=1&tipoConteudo=ndIjl+iEFdE%3D). A listagem confirma MOC 7.0. As tentativas de leitura integral do Anexo I retornaram erro/redirecionamento. Portanto cardinalidades, códigos de rejeição e regras finais NÃO foram certificados neste ciclo.
- [Portal Nacional: notas técnicas](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?AspxAutoDetectCookieSupport=1&tipoConteudo=6WfrpZYE4Ik%3D). A busca encontrou listagens com NT 2025.002 v1.50 e outra indexação com v1.51; a leitura desta última falhou. Não fixar a versão vigente por esses resultados. Obter documento integral e pacote XSD, registrar versão/hash e conferir vigências antes do gerador. A listagem também identifica adequação ao CNPJ alfanumérico pela NT 2026.004; exige análise específica.
- [Economia GO, orientação 21305](https://orientacaotributaria.economia.go.gov.br/spo-web/perguntasfrequentes/perguntafrequente/21305): descreve alternativas de recuperação de ICMS-ST na devolução com tratamentos diferentes. Isso impede adotar uma regra genérica automática de destaque/restituição.
- [Economia GO, orientação 21349](https://orientacaotributaria.economia.go.gov.br/spo-web/perguntasfrequentes/perguntafrequente/21349): indica CSOSN 900 para a hipótese específica de devolução de compra com ST por optante do Simples. Não generalizar para toda devolução; obter enquadramento do contador.

As orientações foram consultadas para identificar riscos e requisitos. Não substituem legislação consolidada, vigência por operação ou aceite profissional. Nenhuma configuração tributária do cliente foi alterada.

## Sequência de implementação

- [x] Mapear fontes existentes, acoplamentos e lacunas (ciclo 61).
- [ ] Obter e ler integralmente MOC/NT e XSD aplicáveis; fixar versões e hashes em evidência local.
- [ ] Completar o contrato neutro e seu validador somente leitura; grupos gerais e políticas de pagamento/observações estão estruturados, mas total fiscal serializável e grupos tributários especiais ainda não.
- [ ] Fechar dados faltantes e casos esperados com o contador, especialmente ST, IPI devolvido, RTC, total fiscal e pagamento.
- [ ] Implementar gerador separado com casos sintéticos e validação XSD; manter transmissão bloqueada.
- [ ] Testar paridade de conteúdo Focus/direta e homologar separadamente com credenciais reais autorizadas.
