# Contrato proposto do XML de devolução ao fornecedor

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
| produtos | itens selecionados e snapshot original | `det/prod` | Mapear código, descrição, NCM, unidades, quantidades, preços, GTIN e eventual CEST; tratar conversões e precisão explicitamente |
| classificação | parametrização aprovada por item | grupos CST/CSOSN e CFOP | Matriz de capacidade por grupo, regime e vigência; código cadastrado não garante suporte à serialização |
| bases e valores | memória revisada aprovada | `det/imposto` | Exigir vínculo íntegro a reflexos aprovados, bases finais exatas, valores/aliquotas conferidos; não recalcular pela política de vendas |
| ajustes comerciais | composição e rateio de origem | frete, seguro, despesas e desconto por produto | Conferir totais e não reaplicar impactos já incorporados às bases |
| IPI devolvido | ainda sem grupo específico | eventual `impostoDevol` e total correspondente | Modelar os campos e a hipótese aplicável; IPI informado na memória não implica IPI devolvido |
| ICMS-ST/FCP | orientação e memória, ainda genéricas | grupos específicos e/ou informações complementares conforme hipótese | Bloquear até parametrizar a hipótese contábil e os campos exigidos; não destacar ST automaticamente |
| IBS/CBS | bases/valores e orientação textual | grupos RTC do leiaute vigente | Falta fechar classificações, grupos, totais e regras por vigência; não considerar memória genérica suficiente |
| transporte | ficha logística | `transp` | Usar ficha ligada à memória final aprovada; validar grupos condicionais e documento do transportador |
| total fiscal | ainda não definido | `total` | Total comercial não é `vNF`; especificar cada parcela, exceção e total novo da RTC com fonte e teste |
| pagamento | política documentada, não implementada | `pag/detPag`: `tPag=90`, `vPag=0.00` no escopo proposto | MOC YA02-04/YA03-30; confirmar regras complementares aplicáveis; não gerar recebíveis, cobrança, troco ou pagamentos de venda |
| observações | parecer e fundamento aprovado | `infAdic` | Separar texto interno de informação fiscal exigida, sem credenciais ou dados indevidos |
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
- [ ] Completar o contrato neutro e seu validador somente leitura; envelope e referência chave+nItem com escopo da empresa estão implementados, mas identificação, partes, produtos, tributos e totais ainda não.
- [ ] Fechar dados faltantes e casos esperados com o contador, especialmente ST, IPI devolvido, RTC, total fiscal e pagamento.
- [ ] Implementar gerador separado com casos sintéticos e validação XSD; manter transmissão bloqueada.
- [ ] Testar paridade de conteúdo Focus/direta e homologar separadamente com credenciais reais autorizadas.
