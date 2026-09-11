# Roadmap de evolucao pos-piloto

## Ponto de retomada — ciclo 95, 11/09/2026

O limite de entrada do futuro gerador foi formalizado no contrato `supplier_return_offline_generator_input_plan_v1`, ainda sem serialização. A leitura direta da evidência arquivada confirmou os 21 filhos de `NFe/infNFe`, suas posições e cardinalidades. Os oito blocos usados pela devolução foram distinguidos dos treze blocos atualmente fora de escopo, sem tratar estes últimos como dispensados. Os hashes do ZIP 010f e do XSD principal foram reproduzidos. A evidência existe no repositório, mas o pacote continua não instalado em `fiscal_schemas`, não aprovado e não promovido para operação.

- [x] Reproduzir os hashes do ZIP arquivado e do `leiauteNFe_v4.00.xsd` interno.
- [x] Corrigir a distinção entre evidência arquivada e schema instalado/aprovado.
- [x] Registrar a ordem e cardinalidade dos 21 blocos diretos de `infNFe`.
- [x] Marcar separadamente blocos mapeados e blocos fora do escopo atual.
- [x] Definir requisitos explícitos para os subcontratos e portões externos.
- [x] Recusar qualquer campo indisponível, destino pendente ou decisão/origem incompleta.
- [x] Tornar obrigatórios os bloqueios de instalação, aprovação, ordem operacional e serializador.
- [x] Integrar o portão à extração e à prévia fiscal somente leitura.
- [x] Validar 158 testes da devolução e 428 testes da suíte fiscal completa.
- [x] Manter XML, assinatura, certificado, Focus, SEFAZ direta e emissão desativados.
- [ ] Próximo passo: automatizar a auditoria offline do pacote XSD e definir a promoção versionada para `fiscal_schemas`, sem instalar, aprovar, ativar ou gerar XML automaticamente.

Arquivos: `apps/fiscal/plano_gerador_devolucao.py`, `apps/fiscal/extracao_contrato_devolucao.py`, `apps/fiscal/rastreabilidade_leiaute_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Documentação: [PLANO_GERADOR_OFFLINE_DEVOLUCAO.md](PLANO_GERADOR_OFFLINE_DEVOLUCAO.md). Migrações: nenhuma.

## Ponto de retomada — ciclo 94, 11/09/2026

Os 115 campos do inventário da devolução foram consolidados no contrato `supplier_return_atomic_xml_matrix_v1`. Cada registro contém campo, fonte primária, tratamento da ausência, regra de aplicação, destino futuro no XML e estado do inventário. As 115 referências de destino são verificáveis e não duplicadas; pontos cujo leiaute vigente ainda não foi aprovado ficam marcados explicitamente como pendentes. O mapeamento distingue dados exigidos antes do gerador, campos condicionados e decisões que só podem existir após aprovação. Destino documentado não significa aplicabilidade fiscal nem autorização de serialização.

- [x] Reunir os 115 campos do inventário em uma matriz única e validável.
- [x] Associar a cada campo sua fonte primária e regra de ausência/aplicação.
- [x] Documentar 115 destinos futuros no leiaute da NF-e.
- [x] Preservar a evidência e o hash do pacote XSD já inventariado.
- [x] Registrar explicitamente que bases totais informativas de PIS/COFINS não possuem tag total própria em `ICMSTot`.
- [x] Rejeitar campo duplicado, fonte/regra/destino divergente e evidência XSD adulterada.
- [x] Manter `serializacao_implementada=False` para todos os campos.
- [x] Integrar a matriz à extração e à prévia fiscal somente leitura.
- [x] Manter Focus, SEFAZ direta, XML e emissão bloqueados.
- [x] Validar a regressão conjunta de 164 testes da devolução.
- [x] Próximo passo concluído no ciclo 95: limite de entrada e ordem estrutural apurados, com recusa fechada e sem assinatura ou transmissão.

Arquivos de implementação: `apps/fiscal/matriz_atomica_devolucao.py`, `apps/fiscal/extracao_contrato_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Testes: `apps/fiscal/test_matriz_atomica_devolucao.py` e `apps/fiscal/test_devolucao_fornecedor.py`. Documentação: [MATRIZ_ATOMICA_XML_DEVOLUCAO.md](MATRIZ_ATOMICA_XML_DEVOLUCAO.md), `INVENTARIO_DADOS_DEVOLUCAO.md`, `MATRIZ_RASTREABILIDADE_DEVOLUCAO.md` e este roadmap. Migrações: nenhuma.

Decisões tributárias continuam pendentes do contador e da análise normativa. O pacote XSD continua não promovido, a paridade Focus não foi fechada e a SEFAZ direta apenas transportará um futuro XML integral. Nenhuma credencial, certificado, ambiente ou feature flag foi acessado ou alterado.

## Ponto de retomada — ciclo 93, 11/09/2026

Os grupos PIS e COFINS do contrato `supplier_return_item_tax_values_v1` passaram a representar separadamente a variante estrutural candidata e sua modalidade de cálculo candidata. O XSD preservado confirma quatro escolhas exclusivas por contribuição (`Aliq`, `Qtde`, `NT` e `Outr`); em `Outr`, percentual e quantidade continuam alternativas internas. Os candidatos nascem vazios, com fonte `DECISAO_CONTADOR_PENDENTE`, estado `NAO_DEFINIDA` e confirmação falsa. O sistema não deduz a escolha pelo CST nem pelos números da memória. Quando uma escolha é fornecida para validação, apenas a compatibilidade estrutural com o CST e a modalidade é conferida, sem aplicar cálculo ou gerar grupo XML. O inventário passou a 115 campos e duas lacunas; rastreabilidade e obrigatoriedade passaram a 42 famílias.

- [x] Confirmar no XSD preservado os grupos opcionais e as quatro escolhas de PIS/COFINS.
- [x] Representar variante e modalidade de cálculo separadamente para PIS e COFINS.
- [x] Iniciar todos os candidatos vazios e não confirmados, dependentes do contador.
- [x] Registrar cardinalidade, fonte e destino XML futuro sem criar serializador.
- [x] Validar compatibilidade entre variante explicitamente candidata, CST informado e modalidade escolhida.
- [x] Exigir modalidade explícita para `PISOutr` e `COFINSOutr`.
- [x] Recusar variante inválida, CST incompatível, fonte trocada e confirmação antecipada.
- [x] Provar que base, alíquota, valor, totalização e canais não sofrem alteração.
- [x] Manter `permite_aplicar_variantes_pis_cofins=False`, XML e emissão bloqueados.
- [x] Exibir variantes e modalidades pendentes na prévia somente leitura.
- [x] Remover `VARIANTES_PIS_COFINS_NAO_MODELADAS`; restam duas lacunas.
- [x] Validar a regressão conjunta de 156 testes.
- [x] Próximo passo concluído no ciclo 94: matriz atômica consolidada com 115 destinos, sem serialização.

Arquivos de implementação alterados: `apps/fiscal/tributos_itens_devolucao.py`, `apps/fiscal/extracao_contrato_devolucao.py`, `apps/fiscal/inventario_dados_devolucao.py`, `apps/fiscal/rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/obrigatoriedade_campos_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Testes alterados: `apps/fiscal/test_tributos_itens_devolucao.py`, `apps/fiscal/test_inventario_dados_devolucao.py`, `apps/fiscal/test_rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/test_obrigatoriedade_campos_devolucao.py` e `apps/fiscal/test_devolucao_fornecedor.py`. Migrações: nenhuma. Decisões ainda pendentes: aplicabilidade dos grupos, variantes reais, modalidades, CSTs e valores do caso concreto. Dependências externas: decisão do contador, análise normativa integral e posterior homologação de cada canal. Detalhes em [VARIANTES_PIS_COFINS_DEVOLUCAO.md](VARIANTES_PIS_COFINS_DEVOLUCAO.md).

Sem cálculo novo, decisão tributária, XML, credencial, certificado, mudança de ambiente ou transmissão.

## Ponto de retomada — ciclo 92, 10/09/2026

O contrato `supplier_return_returned_ipi_policy_v1` passou a representar o enquadramento legal do IPI por item como decisão própria, separada tanto do IPI informativo da memória quanto de `impostoDevol`. O XSD preservado confirma `cEnq` com cardinalidade 1-1 dentro de `IPI` e tipo `TString` de 1 a 3 caracteres; ele não prova, isoladamente, que o grupo IPI se aplique ao caso nem qual código deva ser usado. Por isso o candidato nasce vazio, com fonte `DECISAO_CONTADOR_PENDENTE`, disponibilidade `NAO_DEFINIDO`, confirmação falsa e destino futuro `NFe/infNFe/det/imposto/IPI/cEnq`. O inventário passou a 111 campos e três lacunas; a rastreabilidade e a matriz de obrigatoriedade passaram a 38 famílias.

- [x] Confirmar no XSD preservado cardinalidade, posição e formato lexical de `cEnq`.
- [x] Separar `cEnq`, IPI da memória e `impostoDevol` em estruturas independentes.
- [x] Iniciar o candidato vazio, sem copiar cadastro atual, XML histórico ou memória.
- [x] Registrar fonte, disponibilidade, obrigação estrutural, obrigação contextual, dependência do contador e destino XML futuro.
- [x] Aceitar candidato de 1 a 3 caracteres apenas como hipótese não confirmada, sem presumir restrição numérica ausente do XSD.
- [x] Rejeitar formato inválido, fonte trocada, metadados divergentes e confirmação antecipada.
- [x] Separar integridade da origem de completude fiscal e manter `permite_aplicar_enquadramento_ipi=False`.
- [x] Provar que o candidato não altera IPI da memória, `impostoDevol`, totalização ou emissão.
- [x] Exibir `cEnq` pendente na prévia somente leitura.
- [x] Remover `ENQUADRAMENTO_IPI_NAO_MODELADO_NA_DEVOLUCAO`; restam três lacunas.
- [x] Validar a regressão conjunta de 153 testes.
- [x] Próximo passo concluído no ciclo 93: variantes e modalidades de PIS/COFINS modeladas como decisões vazias e não confirmadas.

Arquivos de implementação alterados: `apps/fiscal/ipi_devolvido_contrato.py`, `apps/fiscal/inventario_dados_devolucao.py`, `apps/fiscal/rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/obrigatoriedade_campos_devolucao.py` e `templates/fiscal/previa_contrato_devolucao.html`. Testes alterados: `apps/fiscal/test_ipi_devolvido_contrato.py`, `apps/fiscal/test_inventario_dados_devolucao.py`, `apps/fiscal/test_rastreabilidade_leiaute_devolucao.py`, `apps/fiscal/test_obrigatoriedade_campos_devolucao.py` e `apps/fiscal/test_devolucao_fornecedor.py`. Documentos alterados ou criados: este roadmap, [ENQUADRAMENTO_IPI_DEVOLUCAO.md](ENQUADRAMENTO_IPI_DEVOLUCAO.md), `INVENTARIO_DADOS_DEVOLUCAO.md`, `MATRIZ_RASTREABILIDADE_DEVOLUCAO.md`, `CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md`, `DEVOLUCAO_FORNECEDOR.md`, `CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md`, `MATRIZ_CONFORMIDADE_FISCAL_CONTABIL_GO_2026.md` e `REDUCAO_BASE_ICMS_DEVOLUCAO.md`.

Migrações: nenhuma. Riscos remanescentes: tabela/código aplicável não aprovados, hipótese de IPI devolvido ainda aberta, pacote XSD não promovido e paridade Focus/SEFAZ não homologada. Decisões não tomadas: código `cEnq`, presença do grupo IPI, CST, valores, justificativa, geração de XML, provedor e ambiente. Dependências externas: validação do contador para casos reais, confirmação normativa integral e futura homologação separada dos canais.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. O trabalho para antes de PIS/COFINS conforme o plano aprovado.

## Ponto de retomada — ciclo 91, 10/09/2026

O grupo ICMS do contrato tributário passou a representar `pRedBC` como candidata vazia, fonte `DECISAO_CONTADOR_PENDENTE` e confirmação falsa. O formato foi confrontado com `TDec_0302a04` do XSD preservado e o contrato limita o percentual candidato à faixa segura de 0 a 100, com duas a quatro casas quando houver parte decimal. Nem o campo existente no cadastro atual do produto, nem o XML histórico, nem diferenças entre bases preenchem a decisão. A base aprovada continua somente reproduzida. O inventário passou a 110 campos e quatro lacunas.

- [x] Confirmar no XSD preservado o formato lexical usado por `pRedBC`.
- [x] Manter a redução exclusivamente no grupo ICMS.
- [x] Iniciar candidata vazia, sem copiar cadastro atual, XML histórico ou memória.
- [x] Fixar fonte em decisão pendente do contador e confirmação falsa.
- [x] Validar percentuais candidatos de 0 a 100, sem aplicá-los.
- [x] Rejeitar formato/percentual inválido, fonte alterada e confirmação direta.
- [x] Manter `permite_aplicar_reducao_base_icms=False`, XML e emissão bloqueados.
- [x] Provar que a candidata não modifica `vBC`, alíquota, valor ou totalização.
- [x] Exibir `pRedBC` pendente na prévia somente leitura.
- [x] Remover `REDUCAO_BASE_ICMS_NAO_MODELADA`; restam quatro lacunas.
- [x] Validar a regressão conjunta de 149 testes.
- [x] Próximo passo concluído no ciclo 92: `cEnq` modelado como decisão contábil vazia e não confirmada, sem copiar cadastro, XML ou memória.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [REDUCAO_BASE_ICMS_DEVOLUCAO.md](REDUCAO_BASE_ICMS_DEVOLUCAO.md).

## Ponto de retomada — ciclo 90, 10/09/2026

O grupo ICMS do contrato `supplier_return_item_tax_values_v1` passou a transportar a modalidade de base como candidata vazia, fonte `DECISAO_CONTADOR_PENDENTE` e confirmação falsa. O XSD oficial preservado confirma os códigos 0, 1, 2 e 3, mas nenhum deles é escolhido pelo sistema; em especial, o valor 3 fixado no emissor antigo não é herdado. A integridade da memória tributária permanece separada da completude da decisão fiscal, portanto bases e totais continuam somente conferíveis e não são recalculados. O inventário passou a 109 campos e cinco lacunas.

- [x] Confirmar no XSD preservado os códigos 0, 1, 2 e 3 de `modBC`.
- [x] Manter a modalidade exclusivamente no grupo ICMS.
- [x] Iniciar candidata vazia, sem copiar XML, cadastro ou emissor antigo.
- [x] Fixar a fonte em decisão pendente do contador e confirmação falsa.
- [x] Rejeitar código fora da enumeração, fonte alterada e confirmação direta.
- [x] Manter `permite_aplicar_modalidade_base_icms=False`, XML e emissão bloqueados.
- [x] Separar origem tributária íntegra de decisão fiscal completa.
- [x] Provar que a candidata não modifica base, alíquota, valor ou totalização.
- [x] Exibir `modBC` pendente na prévia somente leitura.
- [x] Remover a lacuna `MODALIDADE_BASE_ICMS_NAO_MODELADA`; restam cinco.
- [x] Validar a regressão conjunta de 147 testes.
- [x] Próximo passo concluído no ciclo 91: `pRedBC` modelado como hipótese contábil vazia e não confirmada, sem copiar cadastro nem recalcular a base.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [MODALIDADE_BASE_ICMS_DEVOLUCAO.md](MODALIDADE_BASE_ICMS_DEVOLUCAO.md).

## Ponto de retomada — ciclo 89, 10/09/2026

O contrato `supplier_return_products_v1` passou a representar `indTot` por item como candidato explicitamente vazio, com fonte fiscal pendente e confirmação falsa. O validador reconhece 0 e 1 somente como candidatos não confirmados, recusa fonte trocada ou confirmação direta e nunca permite aplicação, XML ou emissão. A completude da origem dos valores foi separada da decisão fiscal para que a totalização diagnóstica continue conferindo a memória aprovada sem usar o novo campo. O inventário passou a 108 campos atômicos e seis lacunas.

- [x] Incluir candidato, fonte e estado de confirmação de `indTot` por item.
- [x] Iniciar o candidato vazio, sem copiar o XML original nem assumir 0 ou 1.
- [x] Rejeitar fonte alterada e promoção direta para confirmado.
- [x] Manter `permite_aplicar_indtot=False`, geração de XML e emissão bloqueadas.
- [x] Separar origem comercial completa de decisão fiscal completa.
- [x] Provar que o campo não altera `valor_produtos`, soma diagnóstica ou `vNF`.
- [x] Exibir o estado pendente na prévia fiscal somente leitura.
- [x] Remover `INDTOT_NAO_MODELADO` do inventário; restam seis lacunas.
- [x] Validar a regressão conjunta de 145 testes.
- [x] Próximo passo concluído no ciclo 90: `modBC` modelado como candidato do contador, sem default, cálculo ou serialização.

Sem migração, decisão tributária, geração de XML, acesso a credencial/certificado, alteração de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [INDTOT_DEVOLUCAO.md](INDTOT_DEVOLUCAO.md).

## Ponto de retomada — ciclo 88, 10/09/2026

O contrato `supplier_return_identity_parties_v1` passou a transportar `indicador_ie_candidato`, sua fonte cadastral e a confirmação obrigatoriamente falsa. Valores 1, 2 e 9 são aceitos somente como candidatos; valor ausente continua pendente e qualquer tentativa de confirmação direta é erro estrutural. A prévia protegida mostra o candidato como não confirmado. O inventário passou a 107 campos atômicos e sete lacunas de modelagem.

- [x] Incluir o indicador de IE candidato no destinatário sem usar o XML como origem.
- [x] Fixar a fonte em `CADASTRO_FORNECEDOR_ATUAL`.
- [x] Manter `indicador_ie_confirmado=False` e rejeitar promoção direta para confirmado.
- [x] Tratar candidato ausente e candidato válido como pendências distintas.
- [x] Proibir aplicação do candidato, XML e emissão no resultado da validação.
- [x] Exibir o candidato e o bloqueio na prévia fiscal somente leitura.
- [x] Adicionar o campo ao inventário e encerrar a lacuna `IND_IE_DESTINATARIO_NAO_MODELADO`.
- [x] Validar o fluxo afetado em regressão conjunta de 107 testes.
- [x] Próximo passo concluído no ciclo 89: `indTot` modelado como candidato explícito e não confirmado, sem valor padrão nem efeito na totalização.

Sem migração, confirmação fiscal, geração de XML, acesso a credencial/certificado, mudança de Focus/SEFAZ direta, ambiente ou transmissão. Detalhes em [INDICADOR_IE_DESTINATARIO_DEVOLUCAO.md](INDICADOR_IE_DESTINATARIO_DEVOLUCAO.md).

## Ponto de retomada — ciclo 87, 10/09/2026

Criado `supplier_return_supplier_registration_xml_comparison_v1`, que confronta 13 campos do cadastro atual do fornecedor com o emitente da NF-e original. A comparação normaliza somente apresentação equivalente — pontuação de CNPJ/IE/CEP, caixa e acentos — e mantém diferenças reais como divergência. Cadastro, XML e resultado não são gravados ou sobrescritos. A prévia protegida de Administração/Contabilidade mostra as duas fontes e o diagnóstico; Compras e Financeiro continuam sem acesso.

- [x] Comparar identidade, IE e endereço fiscal campo a campo.
- [x] Distinguir coincidência, divergência e ausência em cada fonte.
- [x] Tratar indicador de IE como dado atual sem equivalente direto no emitente histórico.
- [x] Rejeitar adulteração de estado, resumo ou política do contrato.
- [x] Proibir fonte preferencial automática, sobrescrita, XML, Focus, SEFAZ direta e emissão.
- [x] Integrar a comparação à extração e à prévia fiscal somente leitura.
- [x] Remover do inventário a lacuna de confronto concluída; restam oito lacunas estruturais.
- [x] Validar o fluxo afetado em regressão conjunta de 107 testes.
- [x] Modelar `indIEDest` no contrato de identidade usando o indicador atual apenas como dado candidato, sem resolver divergências nem liberar emissão.
- [ ] Modelar `indTot` por item como decisão explícita, vazia e não confirmada.

Sem migração, atualização cadastral, geração de XML, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão. Detalhes em [CONFRONTO_CADASTRO_XML_FORNECEDOR.md](CONFRONTO_CADASTRO_XML_FORNECEDOR.md).

## Ponto de retomada — ciclo 86, 10/09/2026

O fornecedor passou a possuir cadastro fiscal estruturado opcional: indicador de IE, inscrição estadual, logradouro, número, complemento, bairro, CEP, município, UF e código IBGE. Campos vazios continuam aceitos sem valor fiscal presumido; quando IE ou endereço são iniciados, as validações exigem coerência e completude. O endereço comercial livre foi preservado e nenhum importador XML escreve nos novos campos.

- [x] Criar dez campos fiscais opcionais sem preencher registros existentes.
- [x] Exigir IE somente para indicador contribuinte e exigir IE quando ele for selecionado.
- [x] Validar endereço fiscal como conjunto completo, com IBGE de sete dígitos, UF de duas letras e CEP de oito dígitos.
- [x] Exibir uma seção fiscal separada no cadastro, explicando que o XML não a atualiza.
- [x] Preservar endereço comercial, isolamento por empresa e administração do cadastro.
- [x] Substituir no inventário a lacuna cadastral pela lacuna de confronto cadastro–XML.
- [x] Validar cadastro e integração fiscal em regressão conjunta de 101 testes.
- [x] Criar confronto não emissivo entre o cadastro atual do fornecedor e o emitente histórico do XML, exibindo divergências sem sobrescrever nenhuma fonte.
- [ ] Modelar o indicador de IE do destinatário como candidato não emissivo no contrato de identidade.

Migração `fornecedores.0004` somente aditiva e 101 testes aprovados. Sem consulta externa, importação automática, geração de XML, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão. Detalhes em [CADASTRO_FISCAL_FORNECEDOR.md](CADASTRO_FISCAL_FORNECEDOR.md).

## Ponto de retomada — ciclo 85, 10/09/2026

Criado `supplier_return_atomic_data_inventory_v1`, que decompõe os blocos fiscais em 106 campos acompanhados e informa somente fonte, ocorrências e disponibilidade, sem expor valores. O inventário confirmou nove lacunas de modelagem: cadastro fiscal estruturado do fornecedor, `indIEDest`, `indTot`, modalidade/redução de base ICMS, `cEnq` do IPI, variantes PIS/COFINS, gerador específico e paridade Focus. O XML original permanece evidência histórica e não pode atualizar cadastro automaticamente.

- [x] Decompor famílias mistas e grupos críticos em 106 campos atômicos.
- [x] Identificar fonte primária e estado de disponibilidade sem expor valores.
- [x] Separar ausência bloqueante, campo condicionado e vazio imposto por política.
- [x] Registrar nove lacunas de cadastro, contrato, hipótese, código e adaptador.
- [x] Impedir uso do XML histórico como cadastro atual ou preenchimento por default.
- [x] Integrar o diagnóstico à prévia protegida e validar 138 testes conjuntos.
- [x] Estruturar IE, indicador de IE, endereço fiscal e município IBGE no fornecedor, opcionais e sem importação automática do XML.
- [ ] Confrontar cadastro atual e XML histórico sem emitir ou sobrescrever dados.

Sem migração, exposição de valores, geração de XML, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão neste ciclo. Detalhes em [INVENTARIO_DADOS_DEVOLUCAO.md](INVENTARIO_DADOS_DEVOLUCAO.md).

## Ponto de retomada — ciclo 84, 10/09/2026

Criado `supplier_return_field_requirement_matrix_v1` para classificar as 37 famílias rastreadas por cardinalidade XSD, regra contextual, hipótese tributária, vigência e necessidade de decisão do contador. A matriz registra que XSD isolado não define aplicação: `DFeReferenciado` é opcional na estrutura e obrigatório no contexto documentado; pagamento usa `tPag=90`/`vPag=0`; IPI devolvido, ST/FCP e RTC permanecem condicionados. Famílias com regra contextual ou hipótese ainda não fechada aparecem como pendentes na prévia.

- [x] Separar obrigatoriedade estrutural de obrigatoriedade contextual MOC/NT.
- [x] Classificar campos dependentes de valor, transporte, hipótese e enquadramento.
- [x] Marcar expressamente quais famílias exigem decisão do contador.
- [x] Manter vigência GO, análise integral e caso real como não confirmados.
- [x] Recusar alteração da classificação, aplicação antecipada ou liberação de canal.
- [x] Integrar o diagnóstico à prévia protegida e validar 135 testes conjuntos.
- [ ] Próximo passo: decompor famílias mistas em campos atômicos e inventariar quais dados existem no sistema, quais faltam no cadastro e quais dependem do XML/contador, sem gerar XML.

Sem migração, geração de XML, instalação de schema, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão neste ciclo. Detalhes em [CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md](CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md).

## Ponto de retomada — ciclo 83, 10/09/2026

Criado o contrato `supplier_return_layout_traceability_v1`, com 37 famílias de campos distribuídas pelos 13 subcontratos. A matriz liga cada origem neutra ao destino no leiaute, à cobertura observada no conversor Focus e ao comportamento do adaptador SEFAZ direto. Foram confirmadas lacunas Focus em referências por item, ajustes, transporte completo, totais, `infAdProd`, IPI devolvido e RTC. O canal direto preserva a `NFe` recebida, mas continua dependente de um gerador específico que não existe.

- [x] Vincular os 13 contratos aos destinos principais do `leiauteNFe_v4.00.xsd` preservado.
- [x] Separar cobertura do conversor Focus de capacidades não comprovadas da API externa.
- [x] Registrar que a SEFAZ direta não reconstrói conteúdo, sem confundir transporte integral com prontidão.
- [x] Proibir serialização, Focus, SEFAZ direta e emissão em todas as linhas da matriz.
- [x] Exibir o resumo na prévia protegida e validar 132 testes conjuntos.
- [ ] Próximo passo: classificar as 37 famílias como obrigatórias, opcionais ou condicionadas por fonte normativa, mantendo decisões tributárias dependentes do contador e sem criar XML.

Sem migração, geração de XML, instalação de schema, acesso a credencial/certificado, mudança de canal/ambiente ou transmissão neste ciclo. Detalhes em [MATRIZ_RASTREABILIDADE_DEVOLUCAO.md](MATRIZ_RASTREABILIDADE_DEVOLUCAO.md).

## Ponto de retomada — ciclo 82, 10/09/2026

Criado o portão diagnóstico `supplier_return_readiness_gate_v1`. Ele confere em ordem os 13 subcontratos da devolução, separa estrutura consolidada de origens conferidas, agrega os bloqueios e impede que qualquer bloco libere XML ou emissão. Os sete portões externos — análise normativa integral, matriz tributária, dados reais, casos aprovados pelo contador, schema aplicável, paridade Focus e paridade SEFAZ direta — permanecem explicitamente desligados.

- [x] Consolidar envelope, referências, partes, produtos, tributos, ajustes, transporte, totais, pagamento fiscal, observações, IPI devolvido, ICMS-ST/FCP e RTC.
- [x] Recusar divergência de contrato, ausência estrutural e tentativa de liberação de XML/emissão por qualquer subcontrato.
- [x] Exibir o diagnóstico na prévia protegida, distinguindo estrutura reunida de NF-e pronta.
- [x] Manter Focus, SEFAZ direta, certificados, ambientes e configurações inalterados.
- [x] Validar 129 testes conjuntos dos contratos e do fluxo de devolução.
- [ ] Próximo passo: construir a matriz campo a campo entre o contrato neutro, o leiaute/XSD aplicável e os adaptadores Focus/SEFAZ direta, sem serializar XML, e usar as lacunas para concluir a leitura normativa.

Sem migração, geração de XML, instalação de schema, acesso a credencial/certificado, mudança de feature flag ou transmissão neste ciclo.

## Ponto de retomada — ciclo 81, 10/09/2026

Criado o contrato `supplier_return_rtc_vigency_policy_v1` para manter IBS/CBS/RTC condicionado à confirmação normativa e operacional. A NT 2026.007 v1.00, seu SHA-256 e as datas documentais são registrados como evidência, mas não ativam nada. Os valores da memória são apenas referência; enquadramento, classificação, grupos e totais ficam vazios enquanto leitura integral, implantação em Goiás, leiaute aplicável e homologação não estiverem confirmados.

- [x] Preservar IBS/CBS da memória somente como referência vinculada.
- [x] Registrar versão, hash, páginas e datas documentais da NT analisada.
- [x] Impedir ativação automática por data ou mera presença de schema.
- [x] Manter enquadramento, classificação, grupos e totais RTC não definidos.
- [x] Integrar o diagnóstico à prévia protegida sem produzir grupo XML.
- [x] Validar 126 testes conjuntos dos contratos e do fluxo de devolução.
- [ ] Próximo passo: consolidar um portão de prontidão que confira todos os subcontratos e liste, sem ambiguidade, o que ainda impede a futura geração de XML.

Sem migração, ativação de RTC, instalação de schema, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 80, 10/09/2026

Criado o contrato `supplier_return_icms_st_fcp_hypothesis_v1` para separar valores de referência da futura decisão sobre ICMS-ST/FCP. Cada item preserva base, alíquota e valor informados na memória, mas hipótese, grupos fiscais, informação complementar e totais ficam vazios. O validador proíbe copiar valores ou inferir tratamento por código ICMS, regime ou generalização das orientações GO 21305/21349.

- [x] Estruturar ICMS-ST e FCP por item com origem e hashes comuns.
- [x] Preservar os valores da memória somente como referência.
- [x] Manter hipótese, destino fiscal, texto complementar e totais não definidos.
- [x] Bloquear inferência por CST/CSOSN, regime ou orientação genérica de Goiás.
- [x] Integrar o diagnóstico à prévia protegida sem produzir grupo XML.
- [x] Validar 123 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar IBS/CBS/RTC com política explícita de vigência e leiaute, mantendo grupos e totais bloqueados até confirmação normativa e homologação (ciclo 81).

Sem migração, definição de hipótese ST/FCP, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 79, 10/09/2026

Criado o contrato `supplier_return_returned_ipi_policy_v1` para manter `impostoDevol` separado do IPI informado na memória. Cada item preserva a referência aprovada de IPI, mas permanece no estado `HIPOTESE_NAO_APROVADA`; `pDevol`, `vIPIDevol`, justificativa fiscal e total ficam vazios. O validador rejeita cópia, cálculo automático ou preenchimento desses campos.

- [x] Estruturar `impostoDevol` por item sem confundi-lo com `det/imposto/IPI`.
- [x] Preservar IDs e hashes da memória/revisão que contém o IPI de referência.
- [x] Manter hipótese, percentual, valor, justificativa e total não definidos.
- [x] Rejeitar cópia do IPI da memória e cálculo automático de percentual.
- [x] Integrar o diagnóstico à prévia protegida sem produzir grupo XML.
- [x] Validar 120 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar ICMS-ST/FCP por hipótese explícita, mantendo destaque/restituição e valores bloqueados até orientação aprovada para o caso real (ciclo 80).

Sem migração, cálculo de IPI devolvido, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 78, 10/09/2026

Criado o contrato `supplier_return_fiscal_notes_policy_v1` para separar anotações internas de futuros textos fiscais. A extração confere parecer, parametrização, memória e revisão, mas expõe somente IDs, hashes e um inventário de presença/contagem. Motivo operacional, fundamentações e observações não são copiados para a prévia nem para os campos fiscais. `infAdic` e `infAdProd` permanecem vazios, e qualquer preenchimento ou exportação automática é rejeitado.

- [x] Inventariar fontes internas sem reproduzir seus textos no contrato ou na prévia.
- [x] Exigir cadeia final aprovada e hashes de parecer, parâmetros, memória e revisão.
- [x] Manter `infAdic` e `infAdProd` vazios até aprovação fiscal específica.
- [x] Rejeitar cópia automática ou injeção antecipada de texto fiscal.
- [x] Integrar o diagnóstico à prévia protegida sem expor conteúdo interno.
- [x] Validar 117 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar o grupo específico de IPI devolvido por item, separado do IPI da memória e sem presumir hipótese, percentual ou valor (ciclo 79).

Sem migração, cópia de texto para XML, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 77, 10/09/2026

Criado o contrato `supplier_return_fiscal_payment_policy_v1`, isolado do fluxo comum de vendas. Para devolução de compra modelo 55/finalidade 4, a única política aceita nesta etapa é `tPag=90` e `vPag=0.00`. O contrato proíbe usar o total comercial e exige que geração de título, movimento de caixa, acionamento de meio de pagamento e cálculo de troco permaneçam falsos.

- [x] Estruturar `tPag=90` e `vPag=0.00` como política fiscal explícita.
- [x] Restringir o contrato à devolução de compra, modelo 55 e finalidade 4.
- [x] Rejeitar uso do total comercial ou valor diferente de zero.
- [x] Rejeitar qualquer efeito operacional e manter o fluxo de vendas desacoplado.
- [x] Integrar a política à prévia protegida, sem gerar `pag/detPag`.
- [x] Validar 114 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar observações fiscais separando conteúdo interno de `infAdic` e `infAdProd`, sem copiar texto livre automaticamente para o XML (ciclo 78).

Sem migração, lançamento operacional, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 76, 10/09/2026

Criado o contrato `supplier_return_diagnostic_totals_v1` para consolidar somente valores já informados nas origens aprovadas. Produtos, base comercial, frete, seguro, despesas, desconto, bases e valores tributários são somados para conferência e precisam apontar para a mesma memória. O diagnóstico não forma `vNF`: valor da nota, IPI devolvido e totais RTC permanecem deliberadamente vazios e bloqueados.

- [x] Consolidar totais comerciais sem reaplicar componentes às bases.
- [x] Somar bases e valores informados de cada grupo tributário sem recalcular imposto.
- [x] Exigir produtos, tributos e ajustes completos, íntegros e ligados à mesma memória.
- [x] Recusar preenchimento antecipado de `vNF`, IPI devolvido e totais RTC.
- [x] Integrar o diagnóstico à prévia protegida.
- [x] Validar 111 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar a política fiscal de pagamento `tPag=90` e `vPag=0.00` como contrato não emissivo, sem produzir efeitos operacionais (ciclo 77).

Sem migração, cálculo de `vNF`, geração de XML, acesso a certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 75, 10/09/2026

Criado o contrato `supplier_return_transport_input_v1` para expor a ficha logística sem transformá-la em XML. A extração só aceita a ficha ligada à última memória final aprovada e confere novamente os hashes da ficha, da memória e da revisão. Modalidade, transportador, documento, volumes e pesos são validados com suas regras condicionais; a ausência da ficha ou uma origem superada aparecem como pendência explícita.

- [x] Estruturar transporte com IDs e hashes da ficha, memória e revisão.
- [x] Exigir a última memória final aprovada e íntegra como origem.
- [x] Validar modalidade sem transporte, dados do transportador, CPF/CNPJ, volumes e pesos.
- [x] Integrar estado e bloqueios à prévia protegida, sem gerar o grupo `transp`.
- [x] Validar 108 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar a totalização diagnóstica, separando total comercial, bases, tributos e grupos ainda não suportados, sem calcular ou declarar `vNF` (ciclo 76).

Sem migração, geração de XML, acesso a certificado, alteração de ambiente ou transmissão neste ciclo.

## Ponto de retomada — ciclo 74, 10/09/2026

Criado o contrato `supplier_return_commercial_adjustments_v1` para os ajustes informados no rateio. A extração exige a cadeia composição/rateio/reflexos aprovados/memória revisada aprovada e preserva a memória histórica que originou cada linha. Frete, seguro, despesas, desconto, base e total são apenas reproduzidos e conferidos por item e no total; o contrato proíbe reaplicar esses componentes às bases tributárias.

- [x] Estruturar ajustes por item e totais com IDs e hashes de toda a origem.
- [x] Exigir reflexos e memória final aprovados, além da integridade do rateio.
- [x] Preservar a distinção entre memória histórica do rateio e memória revisada final.
- [x] Conferir somas informadas sem preencher valores nem alterar bases.
- [x] Integrar o diagnóstico à prévia protegida.
- [x] Validar 105 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar o grupo de transporte a partir da ficha ligada à memória final, validando campos condicionais sem gerar XML (ciclo 75).

Sem migração, reaplicação de valores, cálculo tributário, XML ou transmissão neste ciclo.

## Ponto de retomada — ciclo 73, 10/09/2026

Criado o contrato `supplier_return_item_tax_values_v1` para transportar, sem recalcular, as bases, alíquotas e valores da memória revisada aprovada. Cada linha exige vínculo exato entre rascunho, parametrização, memória, revisão e nItem. ICMS, PIS e COFINS permanecem pendentes da matriz; ICMS-ST/FCP ficam em hipótese não confirmada; IPI da memória não é tratado como `impostoDevol`; IBS/CBS permanecem bloqueados por vigência e leiaute. A prévia apresenta esses estados sem declarar suporte fiscal.

- [x] Estruturar bases, alíquotas, valores, códigos e hashes por item.
- [x] Exigir memória revisada aprovada, íntegra e ligada ao mesmo item/parametrização/nItem.
- [x] Manter ICMS-ST/FCP, IPI devolvido e IBS/CBS em estados separados e bloqueantes.
- [x] Validar formatos decimais sem criar fórmulas ou recalcular tributos.
- [x] Integrar a extração e a prévia protegida.
- [x] Validar 102 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar ajustes comerciais por item a partir do rateio aprovado, conferindo os totais informados sem aplicá-los novamente às bases (ciclo 74).

Sem migração, cálculo tributário, XML, certificado ou transmissão neste ciclo.

## Ponto de retomada — ciclo 72, 10/09/2026

Criado o contrato puro `supplier_return_products_v1` e integrado à extração protegida. Cada item preserva o vínculo com rascunho, produto, nItem original, XML, parametrização e memória. Quantidade vem da seleção congelada; código, descrição, NCM, CEST, unidades e valores unitários vêm do snapshot do XML; CFOP, valor da operação e classificações só são expostos quando a memória está aprovada e toda a cadeia de hashes confere. O serviço apenas compara quantidade × unitário com o valor informado, sem preencher ou recalcular esse valor.

- [x] Preservar no snapshot documental unidade, quantidade e valor unitário tributáveis.
- [x] Estruturar produtos com origem explícita para identidade, quantidade, valor e classificação.
- [x] Bloquear valores/classificações enquanto a memória não estiver aprovada e íntegra.
- [x] Validar nItem, identificadores, hashes, NCM/CEST/CFOP, unidades, decimais, duplicidades e total informado.
- [x] Expor produtos e pendências na prévia protegida.
- [x] Validar 99 testes conjuntos dos contratos e do fluxo de devolução.
- [x] Estruturar bases e valores tributários por item a partir da memória aprovada, mantendo ICMS-ST/FCP, IPI devolvido e IBS/CBS separados por hipótese e vigência (ciclo 73).

Sem migração, alteração de cadastro, cálculo tributário automático, XML ou transmissão neste ciclo.

## Ponto de retomada — ciclo 71, 10/09/2026

Criado o contrato puro `supplier_return_identity_parties_v1` para identificação, emitente e destinatário da NF-e de devolução. A extração protegida usa natureza do parecer, cadastro atual da filial, IE/CRT da configuração fiscal e identidade/endereço do fornecedor preservados no XML original. Estrutura e completude são resultados separados: campos ausentes aparecem na prévia, sem preenchimento presumido. O contrato mantém bloqueios de vigência, CNPJ alfanumérico, XML e homologação.

- [x] Estruturar identificação como modelo 55, finalidade de devolução e operação de saída.
- [x] Estruturar emitente a partir da filial e configuração fiscal, sem expor credenciais.
- [x] Estruturar destinatário a partir do XML original e vínculo cadastral do fornecedor.
- [x] Validar campos, fontes, formatos e tentativa de habilitar emissão em serviço puro.
- [x] Integrar o diagnóstico à extração e à prévia exclusiva de Administrador/Contabilidade.
- [x] Validar 95 testes conjuntos do contrato e do fluxo de devolução.
- [x] Estruturar o grupo de produtos da devolução com quantidades, unidades, valores e classificações vindos dos snapshots aprovados, sem cálculo automático (ciclo 72).

Sem migração, gravação cadastral, certificado, XML ou transmissão neste ciclo.

## Ponto de retomada — ciclo 70, 10/09/2026

A extração protegida da devolução agora produz as referências fiscais chave+nItem a partir do rascunho e as confronta com o XML integral preservado. A conferência exige DF-e da mesma empresa e filial, hash congelado, protocolo com cStat 100, chave idêntica no XML/protocolo/DF-e/compra/rascunho, modelo 55, fornecedor como emitente, filial como destinatária e igualdade do nItem e de seu snapshot. A prévia somente leitura de Administrador/Contabilidade mostra o resultado e os bloqueios, sem permitir edição.

- [x] Integrar o validador de referências à extração autenticada e ao escopo da empresa.
- [x] Conferir protocolo, chave, modelo, partes, nItem e snapshot do XML original.
- [x] Falhar fechado diante de hash, protocolo ou retrato do item divergente.
- [x] Expor a conferência na prévia protegida, mantendo XML e emissão bloqueados.
- [x] Validar 92 testes dos contratos e do fluxo completo de devolução; check do Django sem problemas.
- [x] Estruturar os grupos de identificação, emitente e destinatário do contrato neutro, com snapshots e validação somente leitura (ciclo 71).

Sem migração, acesso a certificado, geração de XML ou chamada a Focus/SEFAZ neste ciclo.

## Ponto de retomada — ciclo 69, 10/09/2026

O pagamento do PDV agora começa com a decisão clara “CPF na nota? Não/Sim”. Nenhuma opção vem escolhida na tela; o operador precisa responder antes de finalizar. “Sim” abre e focaliza o CPF, admite digitação ou pinpad e exige 11 dígitos com verificadores válidos. “Não” limpa o documento e grava consumidor não identificado. O CPF de cliente cadastrado não é mais incluído automaticamente sem essa escolha. CNPJ permanece fora desse atalho e deve seguir NF-e modelo 55.

- [x] Tornar a decisão de CPF explícita antes do recebimento e adequada ao teclado do caixa.
- [x] Validar CPF no navegador e novamente no servidor, inclusive dígitos verificadores e sequências repetidas.
- [x] Impedir inclusão automática do documento do cadastro sem escolha expressa do consumidor.
- [x] Manter captura opcional pelo pinpad e digitação manual, sem expor documento em diagnóstico.
- [x] Validar sintaxe JavaScript, check do Django, 88 testes completos de PDV/vendas e testes fiscais focados.
- [x] Retomar no ciclo seguinte a extração autenticada de chave+nItem da devolução a partir do XML original (ciclo 70).

Sem migração, mudança de banco, transmissão fiscal ou alteração financeira neste ciclo.

## Ponto de retomada — ciclo 68, 10/09/2026

Implementado o contrato puro e não emissivo de referências da devolução por item. Valida chave de 44 dígitos e DV, nItem original, unicidade, política/operação/modelo explícitos e ausência de NFref no cabeçalho. Múltiplas origens recebem bloqueio de escopo, sem serem tratadas como proibição fiscal. A validação ampliada aprovou 91 testes do novo contrato, envelope e fluxo de devolução; check do Django sem problemas. Não houve banco, XML, schema, certificado, cobrança ou transmissão.

- [x] Implementar e testar o validador estrutural de DFeReferenciado por item.
- [x] Extração autenticada de chave+nItem a partir do dossiê/XML original, conferindo integridade, modelo e partes no escopo da empresa (ciclo 70).
- [ ] Depois: completar matriz tributária, totais e vigências antes de criar o gerador separado e homologar cada canal.

## Retomada atual — ciclo 67, 10/09/2026

Confronto dos trechos oficiais de devolução registrado em [REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md](REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md). Corrigida a proposta de referência do cabeçalho para chave+nItem original em DFeReferenciado por item. A NT v1.51 indica 05/10/2026 na regra específica, mas tem divergência no histórico: confirmação operacional continua pendente. Documentados pagamento sem pagamento/valor zero e IPI devolvido separado; isso não decide enquadramento tributário nem acerto financeiro do fornecedor.

- [x] Confrontar referência, pagamento e estrutura de IPI devolvido com os trechos oficiais, registrando limites e divergências.
- [ ] Próximo passo: implementar e testar validador puro de referências fiscais por item; depois integrar extração autenticada, sem XML ou emissão.
- [ ] Completar análise tributária/RTC, tabelas e vigências; confirmar pacote e hipóteses com o contador antes do gerador/homologação.

Apenas documentação alterada neste ciclo; sem mudança de código executável, banco, configuração, cobrança ou transmissão. Registros abaixo são históricos, não o ponto atual de retomada.

Ciclo 66 — 10/09/2026: bloqueio de obtenção das fontes superado com sessão HTTP/cookies. ZIP oficial 010f e PDFs MOC Anexo I, NT 2025.002 v1.51 e NT 2026.007 v1.00 preservados em docs/evidencias/nfe_2026_09_10, com inventário e hashes no README da pasta. ZIP passou CRC e XSD raiz compilou em memória sem rede; identificação dos PDFs conferida. Não houve instalação, alteração fiscal, banco ou emissão. Leitura normativa integral e validação de vigências permanecem pendentes: próximo passo é confrontar regras de devolução com o contrato e os dados do sistema. Os bloqueios históricos de acesso descritos abaixo não representam mais falta dos arquivos; a aprovação do pacote continua pendente.

## Ponto de retomada — ciclo 65, 09/09/2026

Bloqueio documental confirmado: `fiscal_schemas` contém somente README.md, sem pacote XSD. Nova tentativa de abrir a página oficial de schemas indicada pelo projeto retornou redirecionamento circular; a leitura integral do MOC/NT permanece pendente. Não houve alteração de regras, configuração, certificado, banco ou emissão. Não contar esta verificação como módulo fiscal concluído.

Para retomar a matriz normativa: obter o ZIP oficial dos schemas, o MOC Anexo I e as notas técnicas aplicáveis em arquivos locais, com URL de origem e identificação da versão. Conferir o conteúdo e gerar inventário/hash antes de qualquer instalação. O comando existente `instalar_schemas_fiscais` exige hash esperado e versão: não executá-lo para promover um pacote ainda não validado. Nenhuma decisão de tributação ou versão de produção deve ser inferida por disponibilidade de um ZIP.

Próxima ação necessária: disponibilizar os arquivos oficiais ou restabelecer acesso ao portal; depois analisar campos/regras de devolução e vigências, completar a matriz e implementar testes antes do gerador. A prévia e a extração já existentes continuam somente leitura e não autorizam transmissão.

Validação do ciclo 64: suíte de 94 testes executada, com 93 aprovados inicialmente e uma asserção de ausência de formulário ajustada para ignorar formulários globais da página. Os dois testes da prévia foram reexecutados e aprovados após o ajuste. Verificação da aplicação e git diff --check sem erros. Sem nova migração ou transmissão.

Ciclo 64 (09/09/2026): prévia protegida das referências fiscais disponível pela tela de revisão da devolução. Rota somente GET, restrita a Administrador/Contabilidade e à empresa do usuário, com cache desabilitado. Mostra grupos, referências, hashes, pendências e bloqueios, sem edição ou emissão. A etapa de extração do ciclo 63 foi salva no commit 7efa868 após restabelecimento da execução. Próximo passo: obter e analisar integralmente as fontes oficiais e schemas pendentes para fechar a matriz de capacidade fiscal; a prévia não substitui essa validação.

- Ciclo 63 (09/09/2026): extração somente leitura do envelope a partir do banco em apps/fiscal/extracao_contrato_devolucao.py. Exige Administrador/Contabilidade e filtra preparação pela empresa antes de ler suas referências; consulta atual sem reutilizar relações em cache, confere hashes e reutiliza pendências do dossiê. Preserva referências da memória atual, origem e predecessoras de correção, além de decisões disponíveis. Não inclui XML, credenciais ou conteúdo pessoal no envelope. Referência encontrada não significa aprovada: pendências do dossiê seguem separadas e campos fiscais não mapeados continuam NAO_SUPORTADO. Sem endpoint/tela próprios ou validação normativa. Próximo passo: apresentar a prévia protegida do contrato e bloqueios na tela, sem permitir edição manual ou emissão.

- Ciclo 62 (09/09/2026): envelope preliminar supplier_return_nfe_input_v1 e validador puro implementados em apps/fiscal/contrato_devolucao.py, com sete testes aprovados. Exige identificação da preparação/empresa, grupos conhecidos, estados explícitos e referências tipo/id/SHA-256. Distingue ausência, divergência, superação e não suporte; rejeita extras e referências duplicadas. Estrutura válida não significa autenticidade ou conformidade: XML e emissão sempre bloqueados. Ainda sem extração do banco, autorização por empresa, tela ou endpoint próprios. Próximo passo: construir o envelope a partir do dossiê em serviço somente leitura com escopo e integridade verificados. Confirmado aviso oficial de publicação da NT 2025.002 v1.51; leitura integral e XSD ainda pendentes.

- Ciclo 61 (09/09/2026): especificação preliminar do contrato supplier_return_nfe_input_v1 em docs/CONTRATO_XML_DEVOLUCAO_FORNECEDOR.md. Mapeados grupos, fontes locais e bloqueios, incluindo ausência de referência documental no payload Focus observado e despacho de modelo 55 para venda online. Consulta às orientações oficiais GO 21305/21349 confirma necessidade de enquadramento específico para ST. Leitura integral do MOC/NT não concluída por erro no portal; versões e schemas ainda não fixados. Próximo passo: obter fontes integrais e implementar contrato/validador neutro somente leitura. Sem geração de XML, migração ou mudança de emissor.

Validação do ciclo 60: 82 testes aprovados após corrigir reutilização de relações em cache na consulta do XML. Sem alterações de modelos ou novas migrations; sem divergências de migrations e sem erros em git diff --check. Nenhuma transmissão, cobrança ou aplicação de migrations ao banco operacional.

- Ciclo 60 (09/09/2026): conferência consolidada da devolução na tela fiscal, contrato supplier_return_dossier_status_v1. Consulta restrita a Administrador/Contabilidade no escopo da empresa; não grava documentos ou auditorias. Apresenta pendências de preparação, parecer/parâmetros atuais, memória e sua revisão, composição, rateio, reflexos, vínculo à memória revisada e transporte. Distingue referências históricas legítimas da memória revisada de versões superadas. Confere hash dos registros e usa o validador existente de integridade da memória/XML. Não é validador normativo completo nem gate de emissão: XML e homologação continuam explicitamente bloqueados. Próximo passo: especificar o contrato de dados do XML modelo 55 da devolução a partir do dossiê, com matriz de campos suportados e bloqueios antes de gerar XML.

Validação do ciclo 59: 79 testes aprovados; sem divergências de migrations e sem erros em git diff --check. Migration 0050 gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Nenhuma cobrança ou transmissão liberada.

- Ciclo 59 (09/09/2026): correção rastreável da memória revisada implementada (migration 0050). Reflexos passam a admitir versões de memória, mas cada memória devolvida só pode originar uma sucessora. A seleção explícita da memória a corrigir exige versão atual, decisão de devolução íntegra, origem preservada e bases finais idênticas às aprovadas. Nova versão conserva hashes da memória devolvida e da decisão, sem reaplicar impactos; exige nova revisão. Reenvio da correção já utilizada é bloqueado. Próximo passo: consolidar a situação do dossiê da devolução e suas pendências em uma conferência única antes do trabalho de XML. Emissão e homologação permanecem pendentes.

Validação do ciclo 58: 76 testes aprovados. Migration 0049 gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Nenhuma transmissão ou cobrança liberada.

- Ciclo 58 (09/09/2026): memória tributária revisada vinculada explicitamente aos reflexos aprovados, migration 0049. O vínculo único preserva IDs e hashes da memória anterior, dos reflexos e da aprovação. As bases informadas devem corresponder exatamente às bases finais aprovadas; valor da operação e parametrização permanecem os da origem. Não soma impactos, não presume alíquotas ou impostos e exige a revisão independente já existente da nova memória. A opção é apresentada para reflexos atuais aprovados ainda não utilizados. Reenvio do mesmo vínculo é bloqueado, não cria outra memória. Próximo passo: tratar a devolução para correção da memória revisada com nova versão rastreável, sem reutilizar impactos como novo ajuste. Aceite real e homologação continuam pendentes.

Validação do ciclo 57: 73 testes de devolução, transporte, rateio e reflexos aprovados. Migration 0048 gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Sem transmissão externa ou alteração de cobrança.

- Ciclo 57 (09/09/2026): revisão independente dos reflexos nas bases implementada, contrato supplier_return_tax_base_impacts_review_v1, migration 0048. Outro Administrador/Contabilidade da empresa aprova ou devolve com justificativa; uma decisão imutável por versão. O serviço bloqueia o rascunho, exige reflexos/rateio/composição/memória atuais, confere hashes, vínculos, bases e totais e XML de origem. Correção cria nova versão sem apagar a decisão. A tela mostra autoria, justificativa e decisão e não oferece revisão ao autor ou para versões superadas. Próximo passo: vincular os reflexos aprovados à preparação de uma memória tributária revisada, sem reaplicar impactos ou substituir a memória original. Cálculo dos impostos, aceite real e homologação continuam pendentes.

Validação do ciclo 56: 67 testes aprovados; sem divergências de migrations e sem erros em git diff --check. Migration 0047 gerada e exercitada no banco de testes, não aplicada ao banco operacional. Sem transmissão externa.

- Ciclo 56 (09/09/2026): reflexos das bases integrados ao histórico imutável e à tela de revisão, contrato supplier_return_tax_base_impacts_v1, migration 0047. Serviço transacional bloqueia a preparação, exige Administrador/Contabilidade no escopo, composição/memória aprovadas atuais e rateio mais recente, verifica hashes, itens, totais e XML de origem. Conteúdo repetido é idempotente; alterações criam versão. A conferência continua apenas aritmética: não recalcula impostos nem libera emissão. Próximo passo: conferência independente dos reflexos e definição do vínculo com uma memória tributária revisada; aprovação contábil real e homologação permanecem pendentes.

Validação do ciclo 55: 63 testes de devolução, transporte, rateio e reflexos aprovados. Sem alterações de modelo ou novas migrations; sem comunicação externa e sem aplicação de migrations ao banco operacional.

- Ciclo 55 (09/09/2026): núcleo de conferência dos reflexos nas bases implementado em `ReflexosBasesDevolucaoForm`, contrato provisório `supplier_return_tax_base_impacts_draft_v1`. Exige impactos assinados explícitos de frete, seguro, despesas e desconto para cada item e cada um dos oito tributos, base final declarada e totais por tributo. Confere base anterior + impactos = base final sem inferir incidência, alíquota ou valor do imposto. Etapa parcial: ainda sem persistência, rota ou tela; não está disponível para uso operacional. Próximo passo: serviço transacional e histórico vinculados ao rateio atual, com escopo, integridade e auditoria, seguidos da tela. Aceite contábil real e homologação continuam pendentes.

- Ciclo 54 concluído estruturalmente em 09/09/2026: rateio comercial por item `supplier_return_commercial_allocation_v1` implementado, migration 0046. Exige composição e memória atuais aprovadas, valores explícitos inclusive zeros e somas exatas por componente e total. Histórico imutável, idempotência, escopo e hashes preservados. 56 testes de devolução, transporte e rateio aprovados; nenhuma divergência de migrations. Migration gerada e exercitada no banco de testes, ainda não aplicada ao banco operacional. Não gera cobrança, imposto, XML ou transmissão. Próximo passo: estruturar os reflexos sobre bases tributárias com orientação contábil; aceite real e homologação permanecem pendentes.

Atualizado em 01/09/2026 a partir das notas técnicas de evolução contábil, integração SEFAZ, comparativo iSOLIDUS e auditoria do estado executável do repositório.

## Principio de produto

O DeTecServer nao deve copiar telas, nomes ou componentes proprietarios de outros ERPs. A evolucao busca resultados operacionais mensuraveis: menos digitacao, menor divergencia, estoque confiavel, margem protegida, fechamento mais rapido e operacao resiliente.

## Estado atual

O ERP ja possui uma base operacional, financeira gerencial, fiscal preparada por adaptador, auditoria, empresas/filiais, PDV e sincronizacao. O livro financeiro e o pacote contabil sao gerenciais e de integracao; eles nao substituem razao contabil por partidas dobradas, ECD, ECF, EFD ou a responsabilidade do contador.

## Prioridade fiscal e contábil definida em 28/08/2026

- Focus e SEFAZ direta estão estruturalmente avançados, mas o motor tributário e o pacote do contador ainda são parciais.
- Antes da homologação real, deve ser implementada a MATRIZ_CONFORMIDADE_FISCAL_CONTABIL_GO_2026.md.
- Produção permanece bloqueada; selecionar um canal não significa homologá-lo ou liberar sua rede.
- A ordem passa a ser: definição fiscal, cobertura tributária/XML, pacote do contador v2 e homologação separada dos canais.
- IBS/CBS é portão obrigatório conforme regime e vigência aplicáveis.
- Primeiro ciclo concluído em 28/08/2026: perfil provisório sem identidade fiscal, catálogo fiscal_tax_scenarios_go_v1, emissão direta reclassificada como parcial e 25 testes offline aprovados. Próxima ação: validador central de cenário e testes de XML da venda interna.
- Segundo ciclo concluído em 28/08/2026: validador central conectado à NFC-e GO, venda interna documentada no XML, CFOP interestadual bloqueado antes da reserva de número e regressão fiscal completa com 229 testes aprovados. Próxima ação: dados fiscais estruturados do destinatário da NF-e 55.
- Terceiro ciclo concluído em 28/08/2026: cliente e pedido ganharam dados fiscais estruturados, o pedido preserva snapshot imutável, a NF-e gera enderDest completo e a preparação incompleta é bloqueada antes da numeração. Migrations clientes 0004 e marketplace 0011 criadas; 61 testes conjuntos e 229 fiscais aprovados. Próxima ação: catálogo cBenef GO versionado.

- Quarto ciclo concluído em 28/08/2026: catálogo cBenef GO versionado pela migration fiscal 0032, importador local com fonte, hash, vigência e contagem obrigatórios, validação de código x CST no cadastro e no pré-fluxo e falha segura sem catálogo. O anexo oficial consolidado foi conferido pelo SHA-256 `a4fbbeff5ff431a17cf38011d1d8c095558e2bee44121afaee7cbe07bf9e292e`, resultou em 282 códigos e foi ativado somente no banco local de desenvolvimento. Seis testes focados e a regressão fiscal completa com 233 testes passaram. Focus, SEFAZ direta, rede e produção permanecem desligados. Próxima ação: versionar NCM/CEST/CFOP e iniciar o pacote do contador v2 com dados já confiáveis.
- Quinto ciclo, subciclo NCM concluído em 28/08/2026: catálogo oficial Siscomex versionado por snapshot, SHA-256, ato e vigência individual; 10.515 códigos finais importados e ativados localmente pela migration fiscal 0033, com validação na emissão, gate de prontidão, 10 testes focados e 239 testes fiscais aprovados. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: CEST e sua relação com NCM.
- Sexto ciclo, subciclo CEST concluído em 31/08/2026: página consolidada oficial do Convênio ICMS 142/18 preservada por snapshot e SHA-256; 1.561 linhas normativas analisadas, 1.035 CEST vigentes em 25 segmentos e 8 códigos revogados excluídos. A migration fiscal 0034, o importador offline, o cadastro, a pré-emissão e o gate de prontidão validam existência e compatibilidade objetiva CEST x NCM sem presumir enquadramento por descrição. Sessenta e seis testes focados e 244 testes fiscais passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: CFOP.
- Sétimo ciclo, subciclo CFOP concluído em 31/08/2026: página consolidada oficial do Ajuste SINIEF 07/01 preservada por snapshot e SHA-256; 528 linhas codificadas analisadas, 68 agrupadores excluídos e 460 CFOP utilizáveis importados, sendo 213 de entrada e 247 de saída. A migration fiscal 0035, o importador offline, as naturezas, a pré-emissão e o gate de prontidão validam existência, direção, alcance interno/interestadual/exterior e modelo documental. A escolha do código específico continua dependente do cenário e da aprovação fiscal/contábil. Onze testes focados e 249 testes fiscais passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: ampliar os cenários tributários/XML e iniciar o pacote do contador v2.
- Oitavo ciclo, pacote do contador v2 iniciado em 31/08/2026: o ZIP mensal passou ao contrato `accounting_monthly_package_v2`, mantendo caminhos legados do v1 durante a transição. A competência fiscal prioriza `dhEmi`/`dEmi`, registra `dhRecbto` quando disponível e explicita o fallback; saídas, entradas, itens, cancelamentos, CC-e, manifestações e eventos recebidos são exportados por filial a partir dos XMLs armazenados. O manifesto contém contagens, tamanho e SHA-256 de cada arquivo, e o filtro de filial deixou de incluir outras lojas da mesma empresa. Quatro testes focados cobriram extração tributária, XML inválido, competência, integridade, entradas/eventos e isolamento; as regressões completas passaram com 252 testes fiscais e 49 financeiros (301 no total). Focus, SEFAZ direta, rede e produção não foram alterados e permaneceram desligados. A posição atual de estoque também passou a ser exportada pelo custo médio ponderado móvel, com quantidade física/reservada/disponível, valor total e qualidade temporal explícita; competências passadas são marcadas como não retroativas. Próxima ação: snapshots auditáveis de quantidade e custo para fechamento histórico.
- Nono ciclo, fechamento contábil do estoque concluído estruturalmente em 31/08/2026: as migrations estoque 0023/0024 criaram cabeçalhos e itens imutáveis por filial/data, responsável autorizado e auditoria, com dados cadastrais congelados, quantidades, custo médio ponderado móvel, valor e SHA-256. O comando `capturar_fechamento_estoque_contabil` exige confirmação, aceita somente o dia atual, é idempotente e recusa divergência posterior. O pacote usa o snapshot apenas com cobertura completa das filiais e mantém fallback temporal explícito. Quatro testes do fechamento e o teste integrado do pacote passaram; a regressão completa de estoque e financeiro aprovou 121 testes. Próxima ação: reconciliação ampliada do pacote v2.
- Décimo ciclo, reconciliação operacional do pacote v2 concluída estruturalmente em 31/08/2026: o contrato `accounting_operational_reconciliation_v1` cruza, por filial e competência, vendas finalizadas, pagamentos confirmados, livro financeiro, documentos emitidos, itens e movimentos de estoque; nas compras, cruza totais dos itens, DF-e vinculado, contas a pagar e entrada de estoque. O ZIP inclui resumo JSON e CSVs separados, o manifesto contabiliza registros e divergências, e nenhuma diferença altera dados ou cria obrigação automaticamente. Consultas de estoque são processadas em lotes para suportar volumes mensais. Três testes focados cobrem coerência, divergências e isolamento; o teste integrado do pacote e a regressão financeira completa com 52 testes também passaram. Focus, SEFAZ direta, rede e produção não foram alterados. Próxima ação: definir o contrato do software contábil e o responsável pela EFD ICMS/IPI, então validar uma amostra mensal e registrar o aceite.
- Décimo primeiro ciclo, contrato de integração contábil estruturado em 31/08/2026: a migration financeiro 0021 criou versões imutáveis por empresa sob o contrato `accounting_integration_agreement_v1`. Somente o Master registra rascunhos ou valida versões; administrador e Contabilidade consultam o resumo. A validação exige software/escritório destinatário, formato técnico, responsável externo pela EFD ICMS/IPI e referência do aceite. ZIP e API declaram o estado sem expor segredos, preços ou condições comerciais; nenhum cadastro envia arquivo ou gera obrigação. O envio preexistente por adaptador passou a exigir versão validada especificamente no formato de adaptador: configuração de servidor, rascunho, ZIP ou API não liberam a chamada. Os testes focados e integrados e a regressão financeira completa com 57 testes passaram. A definição real permanece pendente enquanto não houver contador/software e dados da empresa. Próxima ação: estruturar o validador da amostra mensal e o registro de aceite, mantendo tudo inativo até dados reais.
- Décimo segundo ciclo, validação da amostra contábil concluída estruturalmente em 31/08/2026: a migration financeiro 0022 criou o aceite imutável por empresa, competência, versão de contrato e SHA-256 do pacote. O contrato `accounting_monthly_sample_validation_v1` valida ZIP v2, empresa, versão contratual, manifesto, hashes, arquivos obrigatórios, XMLs de entrada/saída, reconciliação sem divergências e fechamento imutável completo de estoque; caminhos inseguros, duplicidades e limites excessivos são recusados. Somente o Master acessa a tela e registra aceite mediante referência e confirmação explícita; o processo é idempotente e auditado. Quatro testes focados e a regressão financeira completa com 61 testes passaram. Nenhum arquivo é transmitido, nenhuma EFD é gerada e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação externa: com dados reais, registrar o contrato validado, gerar a amostra, obter conferência do contador e arquivar a referência do aceite.
- Décimo terceiro ciclo, reposição integrada a Compras concluída estruturalmente em 31/08/2026: o relatório de sugestão passou a permitir que perfis de Compras selecionem até 500 itens de uma única filial e criem uma cotação em rascunho pelo contrato `replenishment_quote_draft_v1`. Período, filial, produtos e quantidades são recalculados no servidor; adulterações, duplicidades, itens externos e perfis sem permissão são recusados. Uma chave SHA-256 única garante idempotência sob repetição e concorrência. A ação é auditada e não abre a cotação, não escolhe fornecedor, não envia pedido e não altera estoque, preço, financeiro ou fiscal. A migration compras 0010 materializou a chave técnica. Três testes focados e, após o endurecimento concorrente, a regressão conjunta de Relatórios/Compras com 76 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: avaliar o fechamento operacional de validade/perdas sem automatizar descarte ou baixa.
- Décimo quarto ciclo, planejamento de validade concluído estruturalmente em 31/08/2026: lotes vencidos ou a vencer em até 30 dias ganharam o contrato `inventory_expiry_treatment_plan_v1`, com estados de separação, devolução, promoção ou descarte planejados, observação, responsável, horário e auditoria. Promoção de lote vencido é recusada; itens fora da janela ou de outra empresa também são bloqueados. Repetir o mesmo plano é idempotente. Nenhuma dessas decisões reduz saldo, cria perda, altera preço, financeiro ou fiscal; a baixa continua separada e exige o fluxo de perda com supervisor. A migration estoque 0025 materializou o plano. Três testes focados e a regressão completa de Estoque com 75 testes passaram. Próxima ação: vincular uma baixa de perda autorizada ao lote exato, evitando que o FEFO consuma outra camada.
- Décimo quinto ciclo, perda por vencimento no lote exato concluída estruturalmente em 31/08/2026: `PerdaEstoque` passou a guardar o lote e o núcleo de movimentação recebeu direcionamento obrigatório por `lote_id`. A baixa só ocorre em lote efetivamente vencido com descarte previamente planejado, quantidade positiva dentro do saldo e autorização de supervisor; custo histórico do lote, movimento agregado e alocação da camada são gravados na mesma transação. O FEFO não consome outra camada e saldo zerado muda o plano para Baixa concluída. A migration estoque 0026 materializou o vínculo e o novo estado. Três testes focados e a regressão completa de Estoque com 78 testes passaram. Nenhuma operação fiscal, financeira ou externa foi ativada. Próxima ação: consolidar um relatório operacional de perdas por lote, causa e valor para conferência gerencial.
- Décimo sexto ciclo, relatório gerencial de perdas concluído estruturalmente em 31/08/2026: o relatório existente passou ao contrato `inventory_loss_management_report_v1`, preservando registros legados sem lote e acrescentando filtros por causa e vínculo de lote, quantidade total, consolidação por lote/produto/filial e valores estimados de custo e venda. A tela, o CSV e a impressão aplicam o mesmo escopo e exibem lote, validade, causa e motivo; usuários de uma empresa não acessam dados de outra. O fluxo é somente leitura e não movimenta estoque, não cria lançamento financeiro e não aciona emissão fiscal ou serviço externo. Três testes focados e a regressão completa de Relatórios com 15 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: consolidar uma fila diária de lotes com tratamento de validade pendente, priorizada por vencimento e status, sem automatizar descarte ou baixa.
- Décimo sétimo ciclo, fila diária de validade concluída estruturalmente em 31/08/2026: a própria tela de lotes recebeu o contrato `inventory_expiry_daily_queue_v1`, sem duplicar cadastros. A fila inclui somente camadas com saldo e validade vencida ou em até 30 dias, exclui baixa concluída e prioriza, nesta ordem, vencidos sem tratamento, vencidos em tratamento, próximos sem tratamento e próximos em tratamento; dentro de cada grupo, a validade mais antiga aparece primeiro. Contadores destacam fila total e itens ainda não iniciados, o filtro por estado é validado no servidor e a tela informa dias de atraso ou prazo restante. A consulta respeita o escopo da empresa e não movimenta estoque, não registra perda, não altera preço e não aciona financeiro, fiscal ou serviço externo. Três testes focados e a regressão completa de Estoque com 81 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: registrar uma conferência física auditável do lote, com quantidade observada e dados congelados, antes de decisões irreversíveis, sem ajustar saldo automaticamente.
- Décimo oitavo ciclo, conferência física auditável da validade concluída estruturalmente em 31/08/2026: a migration estoque 0027 criou o registro imutável sob o contrato `inventory_expiry_physical_check_v1`. Cada conferência congela empresa, filial, produto, código e validade do lote, custo, saldo do sistema, quantidade observada, diferença, estado do tratamento, responsável, horário, observação e SHA-256. Divergência exige justificativa e nunca ajusta estoque automaticamente. A perda no lote vencido agora exige uma conferência do mesmo dia, ainda compatível com código, validade, custo e saldo atuais, e não pode superar a quantidade observada; uma baixa parcial invalida a evidência anterior e exige nova contagem para a próxima baixa. A tela preserva o histórico, informa se a evidência está válida e mantém autorização de supervisor para a perda. Dez testes focados e a regressão completa de Estoque com 85 testes passaram. O banco local contém zero conferências fictícias. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: integrar o estado da conferência à fila diária, distinguindo pendente, divergente e pronto para decisão, sem ajustar saldo automaticamente.
- Décimo nono ciclo, estados de conferência integrados à fila diária concluídos em 31/08/2026: o contrato `inventory_expiry_daily_queue_v2` classifica em tempo real cada lote da janela como Pendente ou desatualizado, Divergente ou Pronto para decisão. A classificação usa somente a conferência mais recente do dia e exige correspondência de código, validade, custo e saldo; qualquer alteração retorna o item para Pendente. A fila ganhou contadores, filtro validado no servidor e coluna com saldo observado, mantendo a prioridade de vencimento e tratamento e ordenando pendências antes de divergências e itens prontos dentro de cada grupo. Os três contadores são calculados em uma única agregação e nenhuma classificação grava dados, ajusta estoque ou cria perda. Cinco testes focados e a regressão completa de Estoque com 87 testes passaram. Não houve nova migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: permitir que divergências selecionadas originem um inventário em rascunho para a filial e o produto, com recálculo no servidor e sem aplicar ajuste automaticamente.
- Vigésimo ciclo, divergências encaminhadas ao inventário em rascunho concluído estruturalmente em 31/08/2026: o contrato `inventory_expiry_divergence_inventory_draft_v1` reutiliza o inventário auditado existente. A fila permite selecionar somente lotes classificados como divergentes; o servidor revalida escopo, limite de 200, filial única, saldo e conferência vigente antes de criar. Produtos repetidos em vários lotes viram um único item, sempre com quantidade contada pendente e orientação para contagem total do produto. A migration estoque 0028 registra a origem Manual, Fila de risco ou Divergência de validade e uma chave SHA-256 idempotente baseada nas evidências selecionadas; repetição retorna o mesmo inventário. Aplicação continua bloqueada até todas as contagens e ainda exige supervisor. Nove testes focados e a regressão completa de Estoque com 91 testes passaram. A migration foi aplicada localmente; o inventário anterior foi preservado e nenhum rascunho fictício de divergência foi criado. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: persistir o vínculo relacional entre os itens do inventário e cada conferência/lote de origem, exibindo essa trilha no detalhe sem permitir alteração das evidências.
- Vigésimo primeiro ciclo, trilha relacional e bloqueio de aplicação por lote concluídos estruturalmente em 31/08/2026: a migration estoque 0029 criou `OrigemItemInventarioValidade`, vínculo imutável e único entre item do inventário, conferência e lote. Vários lotes do mesmo produto preservam vínculos separados no item deduplicado; repetição idempotente não duplica a trilha. O detalhe do inventário abre a evidência exata, a evidência retorna aos inventários originados, o histórico do lote ganhou acesso ao registro somente leitura e o Admin não permite inclusão, alteração ou exclusão. A revisão do aplicador revelou que reduções agregadas reconciliam camadas por FEFO e poderiam consumir lote diferente do divergente; por segurança, inventários originados por validade agora permanecem bloqueados mesmo após a contagem agregada, até existir contagem específica por lote. Dez testes focados e duas regressões completas de Estoque, ambas com 92 testes, passaram. A migration foi aplicada localmente e não criou vínculos fictícios. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: criar contagem por lote para cada vínculo, validar a soma contra a contagem total do produto e aplicar a reconciliação diretamente nas camadas corretas, de forma atômica e com supervisor.
- Vigésimo segundo ciclo, contagem completa e reconciliação atômica por lote concluídos estruturalmente em 31/08/2026: a migration estoque 0030 criou o escopo imutável de lotes do inventário e o histórico imutável de contagens sob o contrato inventory_expiry_lot_count_v1. Ao abrir o rascunho, todos os lotes positivos dos produtos selecionados entram no escopo congelado; somente os lotes divergentes mantêm vínculo com a evidência original, enquanto os demais são identificados como complementares para fechar a contagem total. Cada recontagem preserva saldo do sistema, quantidade física, responsável, horário, observação e SHA-256. A aplicação exige contagem total do produto, contagem de cada lote, igualdade exata entre as somas, saldo agregado integralmente rastreado, ausência de lote novo, ausência de alteração após a contagem e supervisor. A transação cria ajustes diretamente nos lotes exatos, atualiza o agregado e registra auditoria; qualquer falha reverte tudo, sem FEFO. O escopo fechado também remove a inclusão manual de produtos. Doze testes focados e a regressão completa de Estoque com 99 testes passaram. A migration foi aplicada localmente e registrou zero escopos e zero contagens fictícias. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: modelar uma retificação auditável para sobra física que ultrapasse a quantidade inicial registrada do lote, sem reescrever o histórico original, e cobrir cancelamento/expiração segura de rascunhos de contagem.

- Vigésimo terceiro ciclo, retificação auditável de sobra física concluída estruturalmente em 31/08/2026: a migration estoque 0031 preserva quantidade_inicial e acrescenta ao lote somente a capacidade adicional acumulada por eventos autorizados. RetificacaoCapacidadeLoteEstoque registra de forma imutável inventário, contagem, quantidade inicial, capacidade anterior, acréscimo, nova capacidade, quantidade contada, justificativa, solicitante, supervisor, horário e SHA-256 sob o contrato inventory_lot_capacity_rectification_v1. Uma contagem acima da capacidade exige justificativa e não altera saldo sozinha; a ampliação é criada apenas durante a aplicação atômica já autorizada, junto com movimento, camada, saldo agregado, status e auditoria. Falha posterior em qualquer lote reverte também a retificação. A tela exibe quantidade inicial e capacidade auditada, e o Admin é somente leitura. Quinze testes focados e a regressão completa de Estoque com 102 testes passaram. A migration foi aplicada localmente e registrou zero retificações fictícias. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: implementar cancelamento explícito e expiração segura dos rascunhos de inventário não concluídos, preservando escopos, contagens e evidências para auditoria.
- Vigésimo quarto ciclo, cancelamento, expiração e nova tentativa segura concluídos estruturalmente em 31/08/2026: a migration estoque 0032 acrescenta prazo, encerramento, responsável, motivo, status Expirado e chave-base de origem. Rascunhos de divergência recebem prazo operacional de 24 horas; contagem e aplicação são bloqueadas assim que o prazo vence, mesmo antes da materialização. O cancelamento exige justificativa mínima e supervisor, não movimenta saldo e preserva itens, escopos, contagens e evidências. A rotina explícita expirar_inventarios_validade encerra somente rascunhos de validade vencidos, exige confirmação, gera auditoria sistêmica e não ajusta estoque. A migração atribui chave-base e prazo aos rascunhos antigos sem expirá-los. Após cancelamento ou expiração, as mesmas evidências podem abrir uma nova tentativa com chave única, enquanto repetições de uma tentativa ativa continuam idempotentes. Lista e detalhe exibem prazo e encerramento; o Admin de inventários e itens tornou-se estritamente somente leitura. Vinte e um testes focados e a regressão completa de Estoque com 108 testes passaram. A migration foi aplicada localmente; não havia inventário de validade antigo para converter. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: integrar a rotina de expiração ao ciclo de manutenção do servidor local com execução idempotente e visibilidade operacional, e então consolidar um cenário piloto ponta a ponta de compra, lote, venda, perda, inventário e fechamento.
- Vigésimo quinto ciclo, manutenção automática dos inventários de validade concluída estruturalmente em 01/09/2026: a migration estoque 0033 criou o histórico imutável `ExecucaoManutencaoInventarioValidade` sob os contratos `inventory_expiry_maintenance_run_v1` e `inventory_expiry_maintenance_status_v1`. Cada execução diária registra identificador, início, fim, sucesso ou falha, quantidade encerrada, código de erro sanitizado e SHA-256, sem guardar caminho, credencial ou conteúdo sensível. O comando agora registra sucesso mesmo quando não há rascunhos, mantém repetição idempotente e grava falha fora da transação revertida. O script `register_inventory_expiry_maintenance_task.ps1` agenda a rotina diariamente, pode usar `SYSTEM`, inicia quando possível, impede sobreposição e limita a execução a dez minutos. A lista de inventários e a Central do servidor mostram última execução, atraso, falha e rascunhos vencidos; o Admin preserva o histórico somente leitura. A migration foi aplicada localmente e confirmou zero históricos artificiais e zero rascunhos vencidos. Seis testes focados, o teste integrado da Central e a regressão completa de Estoque com 113 testes passaram. Nenhum saldo foi alterado, nenhuma chamada externa foi realizada e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: preparar e executar um ensaio ponta a ponta isolado de compra, lote, venda, perda, inventário e fechamento, com dados sintéticos e relatório de evidências, sem emissão ou transmissão fiscal.
- Vigésimo sexto ciclo, ensaio ponta a ponta de estoque e validade concluído estruturalmente em 01/09/2026: o verificador somente leitura `inventory_pilot_end_to_end_evidence_v1` cruza entrada finalizada, camadas de lote, venda, alocação FEFO, perda no lote vencido exato, origem e ajuste do inventário e fechamento imutável. O relatório exige uma única filial e um produto comum, confirma saldo agregado contra as camadas, saldo final contra o fechamento, ausência de documento fiscal na venda do ensaio e gera SHA-256 próprio. O comando `verificar_fluxo_estoque_piloto` aceita modo estrito e distingue explicitamente dados sintéticos de um futuro piloto real. O teste integrado criou dez unidades em dois lotes, vendeu duas somente do lote válido, baixou uma vencida, reconciliou uma divergência por lote e fechou seis unidades; também confirmou que registros de filiais diferentes são recusados. A Central do servidor expõe o comando ao Master. O ensaio integrado, o teste da Central e a regressão completa de Estoque com 114 testes passaram. O banco temporário foi destruído e nenhum dado sintético foi gravado localmente. Nenhum documento fiscal foi criado, nenhuma chamada externa ocorreu e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação externa: repetir o roteiro com registros reais da filial piloto, arquivar o JSON/SHA-256 e obter a conferência operacional; enquanto isso, seguir para melhorias internas que não dependam de CNPJ ou enquadramento real.

- Vigésimo sétimo ciclo, saldo vendável e quarentena por lote concluídos estruturalmente em 01/09/2026: o núcleo de estoque passou a separar saldo físico de saldo efetivamente liberado ao caixa. Vendas consomem somente lotes não vencidos nos estados Não iniciado ou Promoção planejada; lotes Separado, Devolução planejada, Descarte planejado e Baixa concluída permanecem bloqueados. A validação ocorre dentro da transação da venda, antes da baixa, inclusive para produtos que não exigem lote, e a recusa reverte venda, itens, pagamentos e movimentos. Perdas direcionadas continuam alcançando o lote segregado autorizado. A tela de estoque distingue físico, reservado, disponível físico, vendável e bloqueado por lote, calculando a página em lote para evitar consultas repetidas. Não houve migration. Cinco testes focados, incluindo o fluxo completo do caixa, e a regressão conjunta de Estoque e Vendas com 137 testes passaram. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: ampliar a evidência do piloto para preservar e validar a situação de tratamento dos lotes no momento do consumo, sem depender do estado atual mutável do lote.
- Vigésimo oitavo ciclo, evidência histórica da liberação do lote concluída estruturalmente em 01/09/2026: a migration estoque 0034 acrescentou à alocação por lote os snapshots de código, validade e estado de tratamento, além de SHA-256 calculado sobre movimento, lote, quantidade, custo e fotografia. Novas alocações são preenchidas automaticamente e protegidas contra alteração ou exclusão pelo modelo e pelo Admin; registros anteriores permanecem vazios, identificados honestamente como legado sem prova retroativa. O contrato do piloto evoluiu para `inventory_pilot_end_to_end_evidence_v2`, passou a comparar validade com a data da venda, validar integridade e tratamento liberado e publicar as fotografias no JSON. O teste integrado altera validade e tratamento do lote depois da venda e comprova que a evidência original permanece íntegra. A migration foi aplicada localmente: havia zero alocações, portanto zero registros legados ou alterados. Sete testes focados e a regressão conjunta de Estoque, Vendas e Configurações com 277 testes passaram; a prova negativa confirmou que snapshot ausente torna a evidência v2 inválida. Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: criar um diagnóstico somente leitura de cobertura dos snapshots por filial, com contagem de registros íntegros, legados e inconsistentes, visível apenas ao Master.
- Vigésimo nono ciclo, diagnóstico de cobertura dos snapshots de venda por lote concluído em 01/09/2026: o contrato `inventory_lot_snapshot_coverage_v1` percorre as alocações de venda em lotes de até 1.000 registros e classifica por filial snapshots íntegros, legados sem fotografia e inconsistentes. Integridade exige SHA-256 válido, tratamento liberado e validade compatível com a data do movimento; a consulta usa duas queries, não altera nem corrige dados e inclui filiais sem vendas. A Central e seu manifesto mostram totais, percentual e estado somente ao Master; administradores de empresa não veem o painel e continuam sem acesso ao manifesto. No banco local, nove filiais foram consultadas e não havia vendas por lote, resultando em estado Sem vendas por lote, com zero registros alterados. Três testes focados e a regressão completa de Estoque e Configurações com 260 testes passaram. Não houve migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação: incorporar o diagnóstico ao gate de prontidão do piloto real, bloqueando aceite diante de inconsistência e mantendo legado como pendência explícita.
- Trigésimo ciclo, trava de prontidão do piloto real concluída em 01/09/2026: o contrato `inventory_real_pilot_readiness_v1` transforma a cobertura histórica da filial em estados objetivos. Ausência de vendas por lote fica como Sem base; qualquer registro legado ou inconsistente bloqueia o aceite; somente uma base existente e integralmente íntegra fica Pronta estruturalmente. O relatório ponta a ponta evoluiu para `inventory_pilot_end_to_end_evidence_v3` e aplica essa trava como verificação obrigatória quando os IDs informados são reais. Ensaios marcados com `--dados-sinteticos` continuam verificáveis, mas declaram que a trava não foi aplicada ao aceite. A Central do servidor explica a regra somente ao Master. Quatro testes focados e a regressão completa de Estoque e Configurações com 261 testes passaram. Não houve migration nem correção retroativa, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: criar uma prévia somente leitura do ensaio por filial que liste candidatos aos cinco registros e impedimentos antes da execução do comando, sem selecionar ou aprovar dados automaticamente.
- Trigésimo primeiro ciclo, prévia dos candidatos do piloto concluída em 01/09/2026: o contrato `inventory_pilot_candidate_preview_v1` lista, por filial e em janela limitada, entradas finalizadas, vendas finalizadas sem documento fiscal, perdas por vencimento vinculadas a lote, inventários aplicados e fechamentos de estoque. O relatório mostra os produtos presentes nas cinco categorias, incorpora a prontidão histórica e explicita ausência de base, categorias vazias ou falta de produto comum. Ele não combina nem escolhe IDs automaticamente, não altera dados e não acessa a rede. O comando `previsualizar_fluxo_estoque_piloto` aceita limite de 1 a 100 e modo estrito; a Central exibe seu uso somente dentro do painel do Master, sem mostrá-lo ao administrador da empresa. Seis testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: produzir uma ficha de execução do piloto a partir de IDs escolhidos pelo Master, validando compatibilidade antes da operação e sem criar aprovação automática.
- Trigésimo segundo ciclo, ficha de execução do piloto concluída estruturalmente em 08/09/2026: o contrato `inventory_pilot_execution_sheet_v1` recebe os cinco IDs escolhidos manualmente e, antes do verificador final, confirma filial única, produto comum único, estados finalizados, venda sem documento fiscal, perda por vencimento vinculada ao lote, inventário aplicado, hash do fechamento e prontidão histórica. A ficha lista cada impedimento, monta o comando final somente com IDs inteiros e gera SHA-256 próprio, mas declara `aprovacao_automatica=false`. O comando `gerar_ficha_execucao_piloto` possui modo estrito e fica visível somente no painel Master; seleção entre filiais diferentes é recusada sem acessar rede ou alterar dados. Três testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, e Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: permitir ao Master gerar a prévia e a ficha pela interface visual, com seleção explícita de filial e IDs, mantendo confirmação humana e sem executar o ensaio automaticamente.
- Trigésimo terceiro ciclo, interface Master do piloto concluída estruturalmente em 08/09/2026: o painel exclusivo de snapshots na Central ganhou dois cartões responsivos. O primeiro exige seleção explícita de filial e baixa a prévia JSON com limite validado; o segundo exige os cinco IDs positivos e uma confirmação humana antes de baixar a ficha JSON assinada. As rotas recusam administradores de empresa, devolvem erros sanitizados para entradas inválidas e não oferecem ação para executar automaticamente o verificador final. Os nomes dos arquivos identificam filial ou hash sem expor conteúdo fiscal. Três testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, gravação operacional ou chamada externa; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: adicionar à ficha orientações operacionais e campos de responsáveis pela execução e conferência, ainda sem persistir aceite ou dados pessoais automaticamente.
- Trigésimo quarto ciclo, responsabilidade operacional da ficha do piloto concluída estruturalmente em 08/09/2026: o contrato evoluiu para `inventory_pilot_execution_sheet_v2` e passou a exigir identificação manual de quem executa e de quem confere, recomendar separação de funções, aceitar observação operacional limitada e incluir um roteiro fixo de conferência, execução isolada e arquivamento. CPF, CNPJ e e-mail são recusados; os dados informados existem somente no JSON baixado, entram no SHA-256 da ficha e não são persistidos no banco nem registrados como aceite. Linha de comando e interface Master seguem as mesmas regras, enquanto administradores de empresa continuam sem acesso. Três testes focados e a regressão completa de Estoque e Configurações com 262 testes passaram. Não houve migration, emissão, transmissão ou chamada externa; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: criar um verificador offline de integridade que confira o SHA-256 da ficha baixada e seu vínculo com o relatório final v3, sem persistir aceite ou executar integrações.
- Trigésimo quinto ciclo, verificação offline dos artefatos do piloto concluída estruturalmente em 08/09/2026: o contrato `inventory_pilot_artifact_integrity_v1` recalcula os SHA-256 da ficha v2 e do relatório final v3, valida contratos, horários, filial, produto, os cinco IDs e os estados apta/válida. O leitor aceita JSON UTF-8 com ou sem BOM, limita cada arquivo local a 5 MB e recusa links simbólicos e caminhos de rede. O relatório resultante não repete responsáveis, possui SHA-256 próprio e declara que não consulta banco, não persiste resultado nem registra aceite. O comando `verificar_artefatos_piloto` possui modo estrito e aparece somente no painel Master; quatro testes focados, incluindo o cenário ponta a ponta real do sistema, e a regressão completa de Estoque e Configurações com 265 testes passaram. Não houve migration, emissão, transmissão ou chamada externa; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: permitir ao Master baixar o relatório final v3 pela interface após confirmação explícita, sem executar emissão fiscal e mantendo a conferência offline como etapa separada.
- Trigésimo sexto ciclo, download visual do relatório final v3 concluído estruturalmente em 08/09/2026: o painel exclusivo do Master ganhou uma terceira etapa que recebe os cinco IDs, exige confirmação própria e obriga a escolha consciente entre ensaio sintético e piloto real. O primeiro declara que a trava histórica não foi aplicada ao aceite; o segundo aplica e publica a prontidão real da filial. O servidor reutiliza o gerador `inventory_pilot_end_to_end_evidence_v3`, revalida todos os vínculos e entrega inclusive relatórios reprovados como evidência, sem transformá-los em aprovação. Arquivos identificam tipo, filial e prefixo do SHA-256; erros são sanitizados e administradores da empresa não veem o cartão nem acessam a rota. Três testes focados, incluindo as duas modalidades e as recusas por falta de confirmação ou tipo, e a regressão completa de Estoque e Configurações com 265 testes passaram. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: oferecer ao Master a conferência dos dois arquivos pela interface local, processando uploads apenas em memória, com limite de 5 MB e sem persistir conteúdo ou resultado.
- Trigésimo sétimo ciclo, conferência visual dos artefatos em memória concluída estruturalmente em 08/09/2026: o quarto cartão do painel Master recebe a ficha v2 e o relatório final v3, exige confirmação e entrega para download o resultado `inventory_pilot_artifact_integrity_v1`. Um handler dedicado, instalado antes da validação CSRF, mantém os arquivos somente em memória; cada JSON é limitado a 5 MB, a requisição total também é limitada e extensão, codificação, raiz e conteúdo são validados. A proteção CSRF permanece ativa e foi testada com e sem token. Resultado íntegro ou reprovado não persiste arquivo, nome, responsável ou aceite, não consulta banco e não acessa rede; administradores da empresa não veem o cartão nem acessam a rota. Oito testes focados cobriram o fluxo real da interface, adulteração, tamanho, confirmação, CSRF e permissão; a regressão completa de Estoque e Configurações passou com 267 testes. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: consolidar um dossiê ZIP local do piloto com ficha, relatório e verificação já fornecidos pelo Master, validando tudo em memória e sem registrar aceite automático.
- Trigésimo oitavo ciclo, dossiê ZIP local do piloto concluído estruturalmente em 08/09/2026: o quinto cartão exclusivo do Master recebe ficha v2, relatório v3 e o resultado `inventory_pilot_artifact_integrity_v1`, exige confirmação e somente gera o pacote `inventory_pilot_dossier_v1` quando todo o conjunto continua íntegro e coerente. Os três uploads permanecem em memória, são limitados individualmente a 5 MB e têm limite total; a proteção CSRF continua ativa. O servidor recalcula contratos, hashes, filial, produto, cinco IDs, estados e proteções contra persistência ou aceite, recusando conferência adulterada ou pertencente a outro ensaio. O ZIP usa quatro nomes internos fixos e inclui manifesto com tamanhos e SHA-256 dos bytes empacotados, além de hash próprio e declaração explícita de que não é assinatura digital. Administradores da empresa não veem o cartão nem acessam a rota. Seis testes focados e a regressão completa de Estoque e Configurações com 270 testes passaram. Não houve migration, gravação operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: criar um verificador offline do dossiê ZIP que valide entradas, manifesto e hashes sem extrair arquivos ou consultar o banco.
- Trigésimo nono ciclo, verificação offline do dossiê ZIP concluída estruturalmente em 08/09/2026: o comando `verificar_dossie_piloto` publica o contrato `inventory_pilot_dossier_integrity_v1` e, em modo estrito, reprova qualquer pacote inconsistente. O leitor aceita somente arquivo local limitado, recusa links simbólicos e exige exatamente os quatro nomes fixos, sem entradas extras, duplicadas, criptografadas ou métodos de compressão inesperados. Antes de ler o conteúdo, limita cada entrada e a soma descompactada; depois confere CRC, JSON UTF-8, contrato, SHA-256 próprio do manifesto e reconstrói o manifesto esperado a partir da ficha, relatório e conferência. Alteração interna continua sendo detectada mesmo com o ZIP recomposto e CRC válido. O relatório possui hash próprio, não inclui caminho nem responsáveis, não extrai arquivos, não persiste resultado, não consulta banco e não acessa rede. O comando aparece somente no painel Master. Quatro testes novos e a regressão completa de Estoque e Configurações com 274 testes passaram. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: oferecer a mesma conferência do ZIP na interface Master, mantendo upload em memória, confirmação explícita e ausência de armazenamento.
- Quadragésimo ciclo, conferência visual do dossiê ZIP concluída estruturalmente em 08/09/2026: o sexto cartão exclusivo do Master recebe o dossiê, exige confirmação e baixa o relatório `inventory_pilot_dossier_integrity_v1`. Um handler dedicado limita a requisição e mantém o ZIP integralmente em memória; nenhuma entrada é extraída. Pacotes estruturalmente válidos ou reprovados produzem relatório sanitizado, enquanto extensão, ausência, tamanho ou confirmação inválidos retornam erro controlado. A proteção CSRF foi testada com e sem token, e administradores da empresa não veem o cartão nem acessam a rota. O nome do ZIP gerado passou a conter o prefixo do SHA-256 do arquivo inteiro, que é publicado integralmente pelo relatório visual para comparação. Onze testes focados cobriram fluxo real completo, pacote inválido, confirmação, CSRF, permissão, ausência de extração e hash; a regressão completa de Estoque e Configurações passou com 275 testes, seguida da revalidação integrada do vínculo entre nome e hash. Não houve migration, persistência, aceite, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: organizar as seis ferramentas do piloto como roteiro visual numerado, com arquivos esperados e critérios claros de parada, sem automatizar aprovação ou execução.
- Quadragésimo primeiro ciclo, roteiro visual numerado do piloto concluído estruturalmente em 08/09/2026: o painel exclusivo do Master agora apresenta as seis etapas na ordem 1 a 6 e repete o número em cada cartão. O guia informa os arquivos esperados da prévia, ficha, relatório, conferência dos JSON, dossiê e conferência do ZIP, além dos critérios objetivos que obrigam o operador a parar. A etapa final esclarece que integridade confirmada não constitui aceite real. O layout usa três colunas em telas amplas e uma coluna em telas menores, sem criar estado oculto, encadear requisições, reaproveitar uploads ou executar aprovação automática. Um teste novo verifica a ordem real no HTML, os seis nomes de saída e os avisos de parada; a regressão completa de Estoque e Configurações passou com 276 testes. Não houve migration, escrita operacional, emissão ou transmissão; Focus, SEFAZ direta, rede e produção permaneceram desligados. Próxima ação interna: retomar a matriz fiscal GO pelos cenários ainda bloqueados, começando pela preparação segura da devolução ao fornecedor, sem emissão e sem presumir tributação antes dos dados reais e da revisão do contador.
- Quadragésimo segundo ciclo, pré-diagnóstico da devolução ao fornecedor concluído estruturalmente em 09/09/2026: o contrato `supplier_return_fiscal_preparation_v1` passou a conferir, na entrada finalizada, chave de 44 dígitos, XML integral preservado pelo DF-e, modelo 55, vínculo entre chaves, CNPJ do emitente/fornecedor, CNPJ do destinatário/filial e presença dos itens fiscais originais. A leitura reaproveita o retrato tributário do XML e não reconstrói impostos pelo cadastro ou custo. A tela de compras exibe somente a situação documental e as decisões pendentes; “base disponível” não libera emissão. CFOP e tributação permanecem vazios, e o contrato afirma `permite_emissao=False` e `permite_transmissao=False`. Os 17 testes focados e a regressão conjunta de Compras e Fiscal com 320 testes passaram. Não houve migration, documento fiscal, numeração, estoque, rede ou transmissão; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar um rascunho persistente de devolução, ligado à entrada e com seleção limitada de itens e quantidades, sem ainda gerar XML ou assumir tratamento tributário.
- Quadragésimo terceiro ciclo, rascunho operacional da devolução ao fornecedor concluído estruturalmente em 09/09/2026: o contrato `supplier_return_draft_v1` e a migration fiscal 0036 passaram a preservar entrada, chave referenciada, motivo, autor, última atualização e itens com quantidade recebida em snapshot. A seleção aceita até três casas decimais, rejeita números inválidos ou acima do recebido e permite somente uma preparação ativa por entrada. Atualizações substituem os itens dentro de uma transação; cancelamentos liberam a seleção sem apagar o histórico. A entrada não pode ser cancelada enquanto houver preparação ativa, e as rotas respeitam o isolamento por empresa. A interface permite salvar e cancelar o rascunho, sempre declarando que nenhuma nota, estoque ou transmissão foi gerada. Os 16 testes focados e de isolamento e a regressão conjunta de Compras e Fiscal com 326 testes passaram. Nenhum `DocumentoFiscal`, série, número, XML, tributo, movimento de estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar a submissão do rascunho para revisão fiscal e mapear cada seleção ao `nItem` do XML original, sem ainda calcular tributos ou gerar NF-e.
- Quadragésimo quarto ciclo, mapeamento ao XML e submissão para revisão concluídos estruturalmente em 09/09/2026: a migration compras 0011 preserva o `nItem` em cada camada/lote criada por novas importações. Para entradas legadas, o vínculo automático só ocorre quando os identificadores do produto correspondem a um único item do XML; ausência, divergência ou ambiguidade bloqueiam o rascunho. Cada seleção guarda o `nItem` e o snapshot completo do item fiscal original, e a soma de lotes não pode ultrapassar a quantidade daquele item. A migration fiscal 0037 adiciona responsável, horário e SHA-256 do XML à submissão e uma restrição de banco impede o estado “aguardando revisão” sem essas três evidências. Depois de submetido, o rascunho não pode ser alterado, embora possa ser cancelado sem efeitos externos. A tela mostra o `nItem`, a situação e o hash, mas não oferece emissão. Os 35 testes focados de devolução, importação e isolamento e a regressão conjunta de Compras e Fiscal com 329 testes passaram. Nenhum cálculo novo, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: implementar a decisão segregada do revisor fiscal, permitindo devolver para correção ou aprovar apenas a preparação, sem liberar emissão automaticamente.
- Quadragésimo quinto ciclo, revisão fiscal segregada da devolução ao fornecedor concluída estruturalmente em 09/09/2026: o contrato `supplier_return_fiscal_review_v1` e a migration fiscal 0038 criam decisões sequenciais e imutáveis, com aprovação da preparação ou devolução para correção, justificativa obrigatória, responsável, horário, snapshot integral e SHA-256 do conteúdo decidido. A fila visual é isolada por empresa e exclusiva de Administrador e Contabilidade; Compras e Financeiro não acessam nem decidem. O XML original é novamente conferido pelo hash no instante da decisão. A devolução para correção reabre o mesmo rascunho e preserva o histórico; a aprovação bloqueia edição e cancelamento pelo comprador, mas não autoriza emissão. Os 19 testes focados e a regressão conjunta de Compras e Fiscal com 335 testes passaram. Nenhum cálculo tributário, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: modelar um parecer tributário versionado para receber natureza, CFOP e tratamento por tributo somente quando validados pelo contador, sem valores presumidos nem emissão.
- Quadragésimo sexto ciclo, parecer tributário versionado da devolução ao fornecedor concluído estruturalmente em 09/09/2026: o contrato `supplier_return_tax_opinion_v1` e a migration fiscal 0039 preservam versões append-only e idempotentes somente sobre preparação aprovada. Cada parecer exige data, regime e natureza informados pelo responsável, CFOP de saída do modelo 55 presente no catálogo oficial vigente e manifestação textual explícita sobre ICMS, ICMS-ST/FCP, IPI, PIS, COFINS, cBenef e IBS/CBS, inclusive quando não aplicáveis. Snapshot e SHA-256 vinculam o conteúdo ao catálogo CFOP, à revisão aprovada e ao XML original; perda de integridade bloqueia o registro. A mesma fila exclusiva de Administrador/Contabilidade exibe o histórico e o formulário sem defaults. Os 24 testes focados e a regressão conjunta de Compras, Fiscal e checklist visual com 342 testes passaram. Nenhum cálculo tributário, cadastro operacional, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: estruturar parâmetros fiscais por `nItem` vinculados a uma versão explícita do parecer, ainda sem defaults, cálculo ou emissão.
- Quadragésimo sétimo ciclo, parâmetros fiscais por item da devolução ao fornecedor concluídos estruturalmente em 09/09/2026: o contrato `supplier_return_item_tax_parameters_v1` e a migration fiscal 0040 criam versões append-only e idempotentes de uma ficha atômica que deve cobrir todos os `nItem` da preparação aprovada. O responsável escolhe conscientemente a versão do parecer e informa, sem defaults, origem e CST/CSOSN do ICMS, CST ou `NA` de IPI/PIS/COFINS, código cBenef GO ou `NA` e orientações para ICMS-ST/FCP, cBenef e IBS/CBS. Formatos e completude são validados antes de qualquer escrita; snapshot e SHA-256 vinculam a ficha ao parecer íntegro e ao XML original. A tela exclusiva de Administrador/Contabilidade mostra evidência da entrada sem copiá-la automaticamente. Os 29 testes focados e a regressão conjunta de Compras, Fiscal e checklist visual com 347 testes passaram. Nenhuma base, alíquota, valor calculado, alteração cadastral, `DocumentoFiscal`, série, número, XML de saída, estoque, rede ou transmissão foi criado; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar memória de cálculo não emissiva por item, recebendo somente valores explicitamente informados e validando totais sem gerar XML.
- Quadragésimo oitavo ciclo, memória de cálculo não emissiva da devolução ao fornecedor concluída estruturalmente em 09/09/2026: o contrato `supplier_return_item_tax_calculation_memory_v1` e a migration fiscal 0041 criam versões append-only e idempotentes ligadas à versão exata da ficha por item. Administrador ou Contabilidade informa, sem defaults, o valor da operação e base, alíquota e valor de ICMS, ICMS-ST, FCP, IPI, PIS, COFINS, IBS e CBS para todos os `nItem`, inclusive zeros explícitos; tributos classificados como não aplicáveis recusam qualquer valor diferente de zero. O serviço valida formato, precisão, não negatividade, cobertura integral dos itens e integridade de ficha, parecer e XML antes de comparar o total da operação e cada total de base/valor com a soma dos itens. Divergência impede toda a gravação. A interface exibe histórico, critério informado, totais e hash somente na fila de Administrador/Contabilidade. Os 34 testes focados e a regressão conjunta de Compras, Fiscal e checklist visual com 352 testes passaram. O sistema não define fórmula tributária, não copia a entrada, não altera cadastro e não cria `DocumentoFiscal`, série, número, XML, estoque, rede ou transmissão; Focus, SEFAZ direta e produção continuaram desligados. Próxima ação: criar revisão segregada da memória completa, permitindo aprovação ou devolução para correção sem liberar XML ou emissão.
- Quadragésimo nono ciclo concluído estruturalmente em 09/09/2026: revisão da memória pelo contrato `supplier_return_item_tax_calculation_review_v1`, migration fiscal 0042. Outro Administrador/Contabilidade pode aprovar ou devolver a versão mais recente, com justificativa e decisão única imutável vinculada aos hashes da memória, parâmetros, parecer e XML. Autorrevisão e versões superadas são bloqueadas. Correções geram nova memória, preservando decisões anteriores. Os 38 testes focados passaram. Aprovação não libera XML, numeração, estoque ou transmissão. Próxima ação: estruturar transporte e composição do valor da devolução para posterior conferência contábil.

## Continuidade registrada em 24/08/2026

- Ciclo 53 concluído estruturalmente em 09/09/2026: revisão da composição comercial `supplier_return_commercial_review_v1`, migration fiscal 0045. Outro responsável fiscal aprova ou devolve somente a composição atual ligada à memória atual; decisão única imutável e hashes preservam a trilha. Aprovação exige orientação textual para ICMS/ST/FCP, IPI, PIS/COFINS, IBS/CBS e fundamentação. Devolução exige justificativa e permite nova composição sem apagar a decisão anterior. 51 testes de devolução/transporte aprovados. Não há incidência ou cálculo automático, XML, cobrança ou transmissão. Próxima etapa interna: rateio informado dos componentes por item, conferindo bases e totalizações. Aceite e orientação do contador com dados reais permanecem pendentes.

- Ciclo 52 concluído estruturalmente em 09/09/2026: composição comercial `supplier_return_commercial_composition_v1`, migration fiscal 0044. A ficha exige base igual ao valor da operação da memória aprovada mais recente, frete, seguro, despesas, desconto e total declarado, todos explícitos. Confere base + frete + seguro + despesas − desconto e exige confirmação de que os ajustes não estão embutidos no valor base. Versões imutáveis e idempotentes preservam responsável, memória e revisão por SHA-256; integridade do XML é revalidada. 47 testes de devolução/transporte aprovados. Não representa vNF, não define incidência tributária, não cria cobrança ou movimentação e não libera emissão. Próxima etapa: revisão contábil da composição e definição dos reflexos tributários antes de qualquer XML.

- Ciclo 51 concluído em 09/09/2026: ficha logística valida dígitos verificadores de CPF/CNPJ numéricos e identidade no transporte próprio (modalidades 3/4). Referências vêm do XML preservado, com remetente/destinatário invertidos na devolução; CNPJ compara raiz e CPF compara o documento completo. Ausência de documento respeita a exceção oficial. 44 testes aprovados. Sem migration, emissão ou transmissão. CNPJ alfanumérico e demais regras de transporte continuam pendentes. Próxima etapa: composição dos valores da devolução para revisão contábil.

- Ciclo 50 concluído estruturalmente em 09/09/2026: ficha logística `supplier_return_transport_v1`, migration fiscal 0043, ligada à memória aprovada mais recente. Modalidade explícita, dados opcionais do transportador, volumes e pesos validados, versões imutáveis e deduplicação por SHA-256. A gravação reconfere a integridade da revisão, memória e XML. 41 testes de devolução aprovados. Nenhuma emissão ou movimentação é realizada. Próxima ação: compor frete, seguro, desconto e despesas, com revisão contábil. Validação completa dos documentos do transportador e regras fiscais de transporte próprio permanecem pendentes antes de alimentar XML.

- A auditoria do checkout confirmou o núcleo fiscal, o adaptador de emissão e recebimento Focus NFe e o pacote SEFAZ direta GO implementados, com produção bloqueada por padrão.
- A trilha técnica inicial ativa passa a ser a homologação Focus NFe em sandbox, começando por uma única filial piloto e emissão manual. Esta escolha técnica não libera produção nem substitui a contratação e o aceite comercial do provedor.
- O banco local de desenvolvimento continua sem configuração fiscal por filial, credenciais Focus ou evidência de homologação real. A migration fiscal `0028_consultacadastrocontribuinte` foi aplicada localmente em 24/08/2026.
- A fila automática, a produção Focus e as redes da SEFAZ direta, DF-e direto, manifestação e CC-e devem permanecer desligadas até cada aceite documentado.
- O diagnóstico pré-homologação foi endurecido em 24/08/2026: pode exigir configuração operacional, informa apenas presença de credencial e travas, distingue sandbox de produção e bloqueia prontidão real quando token, endpoint e liberação de produção não coincidem. Oito testes direcionados passaram sem comunicação externa.
- O preflight por filial foi concluído em 24/08/2026 e consolida no terminal o mesmo checklist seguro da tela de homologação GO. A seleção de token Focus é validada pelo CNPJ da filial, impedindo que a credencial de outra loja produza falsa prontidão; uma filial marcada como produção também é recusada no roteiro de sandbox. Oito testes direcionados e a suíte fiscal completa com 195 testes passaram sem comunicação externa.
- O roteamento fiscal por filial foi concluído em 24/08/2026: somente o Master visualiza e altera o canal técnico entre Focus NFe, SEFAZ direta GO, compatibilidade do servidor ou emissão externa desativada. Emissão, consulta, cancelamento, inutilização, preflight e prontidão agregada respeitam a escolha; alterações geram auditoria. A opção direta é recusada fora de Goiás, e selecionar um canal não habilita rede nem produção. A suíte fiscal completa passou com 199 testes, sem comunicação externa.
- A resiliência do transporte SOAP direto foi concluída em 24/08/2026: consultas idempotentes possuem retentativa exponencial limitada, emissão e eventos mantêm uma única tentativa diante de resposta incerta, falhas consecutivas abrem circuito por host e a recuperação usa sonda controlada. A telemetria fica somente em memória e registra tipo de resultado, serviço, host e duração, sem XML, chave, CNPJ, certificado, credencial ou mensagem bruta. Dezesseis testes offline do adaptador direto e a suíte fiscal completa com 204 testes passaram sem comunicação externa.
- A contingência NF-e SVC-RS para Goiás foi concluída estruturalmente em 24/08/2026. O Master pode preparar uma NF-e modelo 55 do canal direto com justificativa; o ERP regenera chave e XML com `tpEmis=7`, `dhCont` e `xJust`, invalida assinatura anterior e roteia autorização, consulta, status e evento para o catálogo SVC-RS. A chave `SEFAZ_DIRETA_SVC_ENABLED` é independente e permanece desligada, produção continua bloqueada e operadores comuns não visualizam nem transmitem o fluxo. Testes offline confirmam o endpoint separado, o bloqueio seguro e o fluxo visual; a validação ampla de fiscal, marketplace e checklist passou com 314 testes. A homologação real continua dependente de CNPJ/IE/A1 válidos.
- A reconciliação da contingência NFC-e offline foi concluída estruturalmente em 24/08/2026. A fila mantém consulta antes de qualquer reenvio, exige duas confirmações consecutivas de documento não localizado, reinicia a sequência após timeout, preserva `tpEmis=9` e a chave ao corrigir rejeições, bloqueia cancelamento apenas local e sinaliza prazo excedido sem descartar a nota. A migration fiscal `0030` persiste o contador de confirmações. A validação ampla de fiscal e configurações passou com 276 testes. A homologação real da emissão offline e da regularização continua externa.
- O arquivo interno de evidências fiscais foi concluído estruturalmente em 24/08/2026 pela migration `0031`. Cada documento preserva, sem substituir versões anteriores, o XML entregue ao adaptador, o retorno normalizado, o XML autorizado, as consultas e os eventos de cancelamento/CC-e. Os registros são append-only, idempotentes por referência e encadeados por SHA-256; alterações/exclusões pela aplicação são bloqueadas e o Master visualiza somente o diagnóstico de integridade, sem conteúdo fiscal. A validação anterior passou com 280 testes. Após a implementação da âncora externa, a validação ampla de fiscal e configurações passou com 283 testes. A etapa seguinte acrescentou o comando estrito `verificar_integridade_evidencias_fiscais`, manifesto sanitizado `fiscal_evidence_anchor_v1`, promoção atômica, comparação com a âncora externa anterior, bloqueio de regressão/remoção da cauda, inclusão no backup com SHA-256 e conferência após restauração antes do serviço iniciar. Dois backups temporários consecutivos confirmaram a continuidade externa. O ciclo seguinte concluiu o alerta operacional sanitizado: backup, restauração e verificação manual podem registrar o resultado na auditoria sem XML, chave, CNPJ, certificado ou credencial; estados repetidos não duplicam o histórico e somente o Master visualiza a situação, a origem e o horário no Super Admin e na tela de Backup. Após esse alerta, a validação ampla de fiscal e configurações passou com 285 testes. Em 25/08/2026, a cópia secundária criptografada foi concluída estruturalmente: permanece desligada por padrão, exige confirmação explícita de NAS/rede/disco externo, recusa destino igual ou interno ao principal, copia somente `.zip.aes`, recalcula SHA-256, promove atomicamente e possui retenção independente. Uma execução completa com banco e destinos temporários confirmou hashes idênticos, ausência de ZIP aberto e limpeza dos arquivos parciais; a repetição após o endurecimento concorrente confirmou o mesmo resultado. A validação ampla de fiscal e configurações permaneceu aprovada com 285 testes. O ciclo seguinte concluiu o histórico operacional sanitizado: cada execução real gera identificação idempotente, registra sucesso ou falha, etapa, criptografia, destino secundário e confirmação do hash sem armazenar caminhos, nomes de rede, arquivos, senha ou conteúdo. Somente o Master vê as últimas execuções no Super Admin e em Backup; a última falha vira pendência alta, enquanto `-ValidarSomente` não polui o histórico. Uma simulação com banco temporário confirmou um sucesso e uma falha controlada na cópia secundária sem vazamento de caminho ou senha. A validação ampla de fiscal e configurações passou com 286 testes. O ciclo seguinte acrescentou o monitor sanitizado `backup_freshness_v1`: desligado por padrão com `LOCAL_BACKUP_MAX_AGE_HOURS=0`, ele usa a idade do último backup bem-sucedido, diferencia “Sem sucesso”, “Em dia” e “Atrasado” e gera pendência alta somente ao Master quando a política ativa é descumprida. Os testes focados cobriram os estados e a separação entre última execução e último sucesso; a validação ampla de fiscal e configurações passou com 287 testes. O ciclo seguinte unificou o painel, `verificar_pos_implantacao` e `gerar_evidencia_aceite` pela política `backup_age_policy_v1`: o ambiente é a fonte padrão, `0` bloqueia o aceite, o argumento opcional é identificado como substituição explícita e a checagem física do pacote continua sem expor caminhos. Sete testes focados confirmaram política ausente, ambiente ativo, substituição por argumento, aceite e manifesto; a suíte ampliada de fiscal, configurações, pós-instalação e aceite passou com 292 testes. O ciclo atual endureceu a checagem física pelo contrato `local_backup_package_validation_v1`: o pacote mais recente só libera o aceite depois de validar o arquivo SHA-256 correspondente, nome vinculado, ZIP integral e seguro, contrato `erp_local_backup_v2`, dump lógico, banco declarado e âncora fiscal. Pacotes AES-256 também são descriptografados e inspecionados localmente quando `BACKUP_ENCRYPTION_PASSPHRASE` está disponível; sem a senha, o checksum pode ser confirmado, mas o aceite permanece bloqueado sem expor segredo ou caminho. Sete testes focados cobrem pacote válido, adulteração, contrato incompatível, caminho inseguro e AES-256; a suíte ampliada de fiscal, configurações, pós-instalação e aceite passou com 296 testes. Em 28/08/2026, o restaurador ganhou o ensaio `local_restore_rehearsal_v1`: depois da validação completa, `-EnsaiarIsolado` copia o snapshot SQLite para uma área temporária, verifica `PRAGMA integrity_check` antes e depois, aplica migrations, executa o Django check e compara a cadeia fiscal com a âncora do pacote, sempre declarando que serviço e dados ativos não foram alterados e limpando a área ao final. Um ciclo real com banco temporário gerou somente `.zip.aes`, removeu o ZIP aberto e aprovou a restauração isolada sem expor caminho ou senha. O ciclo seguinte estendeu o mesmo contrato ao PostgreSQL: o operador precisa fornecer um banco já criado, vazio e nomeado com o prefixo `deigo_rehearsal_`, confirmar explicitamente o alvo e manter a senha somente no ambiente. O restaurador recusa o banco ativo/origem, confirma zero objetos antes de executar `pg_restore --single-transaction`, não usa `--clean`, aplica migrations, Django check e integridade fiscal e preserva o banco temporário para inspeção. Como `pg_restore` e um servidor PostgreSQL não estão disponíveis neste ambiente, as travas e a sintaxe foram validadas localmente, mas o restore real continua pendente para a máquina de homologação. Um pacote PostgreSQL sintético confirmou, sem conexão, os bloqueios por ausência de confirmação, nome fora do prefixo e host ausente. A regressão completa do caminho SQLite revelou que `Compress-Archive` omitia mídia declarada quando a pasta estava vazia; o backup agora cria entradas de diretório vazias no ZIP, e um novo ciclo AES-256 com mídia vazia aprovou restauração, migrations, âncora fiscal, ausência de alteração ativa e limpeza temporária. O ciclo seguinte endureceu a mídia de instalação limpa pelo contrato `detech_server_offline_package_validation_v2`: a Central só libera o pacote offline depois de exigir servidor, runtime Python, wheelhouse, PostgreSQL, WinSW, iniciador e apps desktop declarados uma única vez; conferir hashes e tamanhos; bloquear caminhos, links, duplicidades e arquivos extras; abrir o ZIP interno do servidor; validar que o wheelhouse contém pacotes `.whl`; e comparar os manifestos dos apps com os executáveis. Dez testes focados cobrem o pacote válido e adulterações, inclusive a falha antes silenciosa de wheelhouse ausente. O ciclo seguinte integrou o mesmo contrato ao empacotador: a mídia nasce em ZIP temporário, só é promovida após aprovação e preserva o artefato anterior em falha. Dois ensaios completos com componentes sintéticos confirmaram a promoção válida e o bloqueio sem resíduos quando o wheelhouse continha arquivo indevido. O ensaio também revelou e corrigiu duas dependências ocultas do build antigo: o hash agora usa SHA-256 nativo do .NET sem depender do perfil PowerShell, e a cópia intermediária não declarada do wheelhouse é removida antes da compactação final. ZIP e checksum são preparados antes da promoção, e qualquer exceção limpa os temporários. O ciclo seguinte criou `publish_detech_server_offline.ps1`: ele exige o checksum vinculado da origem, revalida origem e cópia temporária, promove ZIP e sidecar com cópias de rollback e remove todos os resíduos. Três ensaios reais confirmaram publicação válida, recusa de origem adulterada e preservação byte a byte do pacote anterior durante substituição forçada inválida. O ciclo seguinte adicionou `detech_server_offline_publication_validation_v1` à Central: o download offline agora exige `.zip.sha256` presente, hash correspondente e nome final vinculado, sem expor caminhos. Três testes novos cobrem publicação íntegra, sidecar ausente e hash/nome divergentes. A interface Master separa o estado do instalador offline do pacote técnico, evitando que a indisponibilidade de um esconda o outro. A suíte completa de fiscal e configurações permaneceu aprovada com 351 testes. O ciclo seguinte integrou a publicação offline à prontidão e ao aceite pelo contrato `local_installation_media_policy_v1`: cada implantação de servidor local é registrada como **com rede** ou **offline**. Com rede, a mídia pendente permanece recomendação; offline, ZIP e SHA-256 íntegros tornam-se obrigatórios e bloqueiam prontidão, dossiê e aceite. O Master ganhou ações separadas para gerar os dois tipos de evidência, e a política escolhida fica registrada na auditoria sem expor caminhos ou segredos. Sete testes novos cobrem mídia opcional, bloqueio offline, liberação íntegra, validação do dossiê e escolha na interface. A suíte completa de fiscal e configurações permaneceu aprovada com 358 testes. A homologação sob a conta `SYSTEM` em NAS ou disco externo real e a política legal de retenção continuam dependentes da infraestrutura definitiva.
- Próximo marco externo: quando existirem dados reais, registrar software/responsável EFD, validar uma amostra real com o contador e arquivar a referência do aceite. Até lá, continuar somente frentes internas que não dependam de inventar enquadramento tributário; Focus, SEFAZ direta e produção permanecem desligados.

## Frente prioritária — fechamento financeiro e gerencial pós-piloto

Esta frente registra as lacunas financeiras, contábeis e fiscais identificadas na auditoria sem recriar os módulos operacionais já existentes. PDV, caixa, contas a pagar e receber, contas de movimento, transferências, livro financeiro, plano de contas, centros de custo, conciliação, recebíveis eletrônicos, compras, estoque, pacote do contador e núcleo fiscal permanecem como base. Os itens abaixo tratam somente de evolução, reconciliação, proteção e homologação ainda não comprovadas.

### DRE 2.0 e CMV

- [ ] Evoluir a DRE gerencial para separar explicitamente receita bruta, cancelamentos, devoluções, descontos, receita líquida, CMV, lucro bruto, despesas operacionais, perdas, taxas financeiras, resultado operacional, resultado antes dos tributos e resultado líquido.
- [ ] Formalizar o cálculo de CMV por período com base no custo congelado no momento da venda e reconciliação com o fechamento contábil de estoque.
- [ ] Validar devoluções, cancelamentos, perdas e ajustes para que não distorçam CMV, receita líquida ou margem.
- [ ] Garantir que taxas de cartão, PIX, antecipações, chargebacks e divergências de adquirentes tenham classificação financeira/contábil coerente e impacto correto na DRE.
- [ ] Criar testes de reconciliação entre vendas, CMV, estoque final, perdas e resultado gerencial.

Critério de aceite:

A DRE de um período deve ser reproduzível, conciliável com vendas, estoque e financeiro, e explicável por conta contábil e centro de custo.

### Fechamento mensal financeiro-contábil

- [ ] Definir um fechamento mensal formal por empresa/filial, com data de corte e responsável.
- [ ] Exigir conciliação bancária, recebíveis eletrônicos, contas a pagar/receber e inventário contábil em estado aceitável antes do fechamento.
- [ ] Criar snapshot ou referência imutável dos saldos, DRE, CMV, inventário valorizado e documentos fiscais do período.
- [ ] Bloquear alterações retroativas que afetem período fechado ou exigir fluxo formal de reabertura/ajuste auditado.
- [ ] Registrar divergências pendentes no fechamento em vez de ocultá-las.
- [ ] Integrar o fechamento mensal ao pacote do contador v2.

Critério de aceite:

Um mês fechado deve poder ser reprocessado para conferência sem alterar seus totais históricos, salvo mediante reabertura ou ajuste auditado.

### Concorrência e integridade da numeração fiscal

- [ ] Auditar a reserva de numeração de NF-e/NFC-e sob concorrência real com vários PDVs simultâneos.
- [ ] Garantir lock transacional ou estratégia equivalente na combinação filial + modelo + série + ambiente.
- [ ] Criar testes concorrentes para impedir número duplicado, salto indevido por retry e dupla emissão da mesma venda.
- [ ] Validar idempotência ponta a ponta entre venda, DocumentoFiscal, fila, retransmissão e consulta SEFAZ.

Critério de aceite:

Nenhum cenário de concorrência, retry ou falha de rede pode gerar dois documentos para a mesma operação nem reutilizar a mesma numeração fiscal.

### Proteção de CSC e segredos fiscais

- [ ] Revisar o armazenamento de CSC e confirmar proteção criptografada em repouso no mesmo nível de criticidade do certificado A1 e sua senha.
- [ ] Impedir exposição de CSC em logs, admin, formulários, serializações, traces, exportações e pacotes de diagnóstico.
- [ ] Definir fluxo auditado de inclusão, rotação e revogação do CSC.
- [ ] Criar testes específicos de não exposição de segredo.

Critério de aceite:

CSC, senha e material privado do certificado não podem ser recuperados em texto claro por interfaces comuns, logs ou exportações.

### Homologação real SEFAZ GO

- [ ] Revalidar endpoints, schemas e Notas Técnicas vigentes antes do primeiro teste externo.
- [ ] Configurar filial piloto com CNPJ/IE, certificado A1, CSC, séries e credenciamento válidos por canal seguro.
- [ ] Executar em homologação: autorização, consulta, rejeições controladas, cancelamento, inutilização, status do serviço e contingência NFC-e.
- [ ] Testar recuperação após timeout ou queda de rede sem duplicidade.
- [ ] Validar DF-e, manifestação e eventos com credenciais reais de homologação quando aplicável.
- [ ] Arquivar evidências técnicas e obter aceite fiscal/contábil antes de qualquer liberação de produção.
- [ ] Manter `SEFAZ_DIRETA_NETWORK_ENABLED` e `SEFAZ_DIRETA_ALLOW_PRODUCTION` sob liberação explícita e independente.

Critério de aceite:

Nenhuma capacidade deve ser classificada como pronta para produção somente por testes offline; deve existir evidência de homologação real da filial piloto.

### IBS/CBS e evolução tributária

- [ ] Manter IBS/CBS como parcial enquanto cálculo, grupos XML, schemas vigentes e aceite fiscal não estiverem confirmados.
- [ ] Implementar regras por vigência e versão de leiaute sem hard-code no PDV.
- [ ] Exigir validação do contador para classificações tributárias e cenários que dependam de enquadramento.
- [ ] Criar regressão fiscal com cenários legado e transição antes de ativar emissão homologada.

Critério de aceite:

A ativação de IBS/CBS deve depender de configuração explícita, schema homologado e evidência de testes; nenhuma data isolada deve habilitar o recurso automaticamente.

### Dependências externas desta frente

- Credenciais reais/sandbox, A1, CSC, IE e credenciamento da filial piloto.
- Arquivos reais anonimizados de adquirentes/bancos para homologação de conciliação.
- Aceite do contador sobre plano de contas, CMV, DRE, classificações, IBS/CBS e pacote contábil.
- Ambiente de homologação com banco e infraestrutura equivalentes ao piloto.

## Frente futura — UX 2.0 e usabilidade

A avaliação de interface registrada como referência identifica oportunidades de melhoria em navegação, hierarquia de informação, responsividade, acessibilidade e redução de carga cognitiva, sem necessidade de redesign completo. O plano detalhado está em [ROADMAP_UX_USABILIDADE.md](ROADMAP_UX_USABILIDADE.md).

A frente deve ser iniciada após a conclusão da trilha fiscal interna atual e da primeira etapa da DRE 2.0/CMV, salvo correção crítica de usabilidade que afete operação ou segurança. O PDV atual deve ser preservado como referência de operação orientada a teclado; mudanças futuras devem priorizar redução de erro, tempo operacional e clareza.

- [ ] Iniciar UX 2.0 conforme o roadmap próprio após os marcos técnicos anteriores.

## Disciplina de atualização

- Toda frente iniciada deve ser marcada no checklist com data, estado atual, travas de segurança e próximo marco verificável.
- Uma entrega só muda para concluída quando código, migration, testes e documentação aplicáveis estiverem alinhados; dependências externas continuam como parciais até a evidência real.
- Ao encerrar cada ciclo, registrar aqui o que mudou, o que foi validado e qual dependência passa a ser a próxima ação.

## Sequencia aprovada

1. Piloto operacional: validar instalacao, PDV, impressao, caixa, estoque, backup e recuperacao em uma filial real.
2. Fiscal: concluir a matriz GO 2026, ampliar o motor tributario/XML e só depois escolher o canal piloto e configurar a homologacao.
3. Entrada fiscal: o XML só se vincula automaticamente a pedido único com produtos, quantidades e totais idênticos; divergências não vinculam pedido nem movimentam estoque ou financeiro. O vínculo manual autorizado, a conferência física guiada e a política por empresa já estão disponíveis: por padrão, uma divergência impede a finalização até que a conferência física seja registrada. A caixa de entrada de DF-e já permite importar e armazenar XMLs recebidos, isolados por empresa. O responsável pode encaminhar manualmente um XML para uma entrada de compra em rascunho, com vínculo e auditoria; também pode desconsiderar documento não aplicável mediante motivo auditado. Essas ações não movimentam estoque nem financeiro e a finalização continua exigindo revisão. O núcleo da consulta por CNPJ/NSU está preparado com cursor independente por filial, lote atômico, deduplicação, auditoria, botão protegido e comando agendável. O adaptador real de recebimento pela Focus NFe já está implementado em homologação, com autenticação segura, versão por CNPJ, consulta opcional do XML completo e bloqueio de produção. Falta configurar credenciais válidas, executar os cenários com a conta sandbox e registrar o aceite antes de produção.
4. Conciliação: o núcleo usa o contrato versionado `financial_statement_adapter_v1`, oferece CSV genérico e OFX nativos e aceita adapters privados registrados no servidor. Cada importação preserva layout, contrato, SHA-256, deduplicação, auditoria e fila paginada. A agenda calcula prazo, taxa, bruto, líquido previsto e atrasos; o matching prioriza NSU, transação ou autorização e classifica liquidação, antecipação, divergência e chargeback. Depósitos agrupados podem ser rateados manualmente com saldo parcial e proteção contra dupla conciliação. A próxima evolução depende de arquivos reais anonimizados para homologar adapters proprietários e automatizar sugestões de lotes.
5. Estoque e preco: inventario orientado a risco, validade, perdas classificadas, simulacao de margem e regras de preco/publicacao. Lotes recebidos por XML ja preservam fabricacao e validade; as vendas consomem FEFO sem selecionar lotes vencidos e produtos configurados para exigir lote bloqueiam a baixa quando nao houver saldo rastreado valido. Perdas e ajustes seguem sendo os fluxos auditados para tratar mercadoria vencida. O reajuste em massa agora simula custo e margem nova, rejeita preco zerado ou negativo e bloqueia produtos abaixo da margem desejada; a excecao exige autorizacao explicita de supervisor ou administrador e gera auditoria. O preco normal possui agenda versionada, vigencia automatica, cancelamento sem apagar historico e auditoria; promocoes validas continuam tendo prioridade no PDV. O inventario orientado a risco agora prioriza produtos por saldo minimo, lotes vencidos ou proximos, perdas recentes, ausencia de contagem e divergencias anteriores. A fila e filtrada por filial, gera um plano com itens pendentes e nao permite aplicar ajustes antes de todas as contagens fisicas, mantendo autorizacao e auditoria. A sugestão de reposição também pode gerar uma cotação em rascunho pelo contrato `replenishment_quote_draft_v1`, sempre para uma única filial, com seleção humana, recálculo no servidor, idempotência e sem envio ou impacto operacional.
6. Contabilidade: entregar primeiro o pacote do contador v2; depois do aceite, decidir com o escritorio se partidas dobradas, EFD, ECD e ECF pertencem ao ERP ou ao sistema integrado.
7. BI e IA: construir sobre metricas conciliadas e permissoes, inicialmente apenas leitura.

## Melhorias operacionais concluídas em 18/08/2026

- Select2 remoto abre com os primeiros registros e pagina em lotes de 20, sem exigir que o usuário memorize três letras; a pesquisa continua disponível para localizar rapidamente bases grandes.
- A gestão de caixas separa o escopo do operador e da supervisão: operador vê e movimenta somente o próprio caixa; supervisor e administrador filtram por filial, operador e situação, abrem o caixa escolhido e imprimem a conferência individual.
- O detalhe do caixa pagina vendas e movimentos manuais separadamente em lotes de 25, preservando os totais da conferência sobre todo o movimento.
- A revisão de codificação removeu textos quebrados das telas financeiras e manteve UTF-8 nas exportações e interfaces.
## Decisoes pendentes do cliente

- Confirmar a Focus NFe como provedor comercial inicial ou registrar outra decisão; para a trilha técnica atual, disponibilizar credenciais sandbox por canal seguro.
- Validar certificado A1, CSC, IE, series e regras tributarias com o contador.
- Definir adquirentes/TEF, bancos e layouts de conciliacao utilizados pela loja.
- Escolher a filial piloto e responsaveis por operacao, fiscal e contabilidade.

## Limites de responsabilidade

Classificacao tributaria, CFOP, CST/CSOSN, IBS/CBS, plano de contas, regras de contabilizacao e obrigacoes oficiais precisam de aprovacao do contador responsavel. O sistema deve oferecer configuracao, validacao, evidencias e bloqueios, sem inventar tributacao.
## Evolução DF-e concluída em 18/08/2026

- Criado o contrato versionado fiscal_dfe_distribution_v1 para desacoplar o ERP do provedor fiscal.
- O cursor de distribuição passou a ser controlado por filial/CNPJ, evitando mistura de NSU entre matriz e filiais.
- A caixa de entrada mostra prontidão do adaptador, último NSU, maior NSU, retorno e consulta manual por filial.
- Lotes são validados integralmente antes de gravar documentos ou avançar o cursor.
- Documentos permanecem isolados por empresa, deduplicados por chave e sem movimentar estoque ou financeiro.
- O comando consultar_dfe_recebidos permite agendamento com usuário técnico e modo estrito.
- Contrato e implantação estão documentados em docs/CONTRATO_DISTRIBUICAO_DFE.md.
- O adaptador Focus NFe foi implementado com HTTP Basic, seleção de token por CNPJ, homologação padrão, TLS obrigatório e bloqueio explícito de produção.
- A paginação por `versao` usa `X-Max-Version`, mas o cursor só avança até o último item efetivamente processado, evitando perda quando o lote é limitado.
- A busca do XML completo não manifesta a NF-e; quando indisponível, o resumo permanece pendente e nenhuma operação é criada.
- Dependência externa restante: configurar/rotacionar as credenciais sandbox, executar a homologação real e registrar o aceite fiscal por filial.

## Evolução da emissão Focus NFe concluída em 20/08/2026

- O adaptador `FocusNFeSefazAdapter` cobre emissão de NFC-e/NF-e, consulta, cancelamento e inutilização pelo contrato fiscal do ERP.
- O payload preserva ICMS, PIS, COFINS, IPI, pagamentos, destinatário e os dados operacionais já validados pelo XML local.
- A referência por documento é estável para evitar duplicidade em repetição ou recuperação de falha.
- Autorizações gravam a chave, o protocolo e o XML processado devolvidos pela Focus; o ERP não mantém como definitivo um XML local diferente do autorizado.
- Respostas pendentes seguem para consulta antes de qualquer retransmissão, e documento não localizado volta ao fluxo controlado da fila.
- O endpoint de produção continua bloqueado por configuração explícita; nenhum teste desta etapa enviou documento real.
- Testes automatizados cobrem autenticação, seleção de token por CNPJ, IPI, retorno autorizado, processamento, consulta 404, host oficial, bloqueio de produção e fila real de homologação.
- Em 24/08/2026, a prontidão Focus passou a validar localmente presença de token, ambiente e liberação de produção sem expor segredo ou testar a credencial na rede; sandbox pronto não é mais confundido com produção liberada.
- Pendência externa: configurar token sandbox, emitir os cenários reais por filial, validar NF-e com endereço estruturado, reunir evidências e obter aceite fiscal/contábil antes de habilitar produção.
## Estrutura da SEFAZ direta GO concluída em 20/08/2026

- Criado o adaptador SOAP direto para autorização, consulta, cancelamento e inutilização de NF-e/NFC-e 4.00 em Goiás.
- O A1 local atende assinatura XML e autenticação mútua TLS; segredos continuam fora do repositório.
- Rede e produção possuem travas independentes e permanecem desligadas por padrão.
- Hosts externos ao catálogo oficial de Goiás são recusados.
- Testes offline cobrem SOAP, autorização, consulta, eventos, inutilização, assinatura real com A1 temporário e bloqueios de segurança.
- Nenhum documento foi transmitido nesta etapa.
- Pendência externa: revalidar endpoints e schemas vigentes, credenciar a filial, executar a homologação real e obter aceite fiscal/contábil. Até lá, Focus NFe e SEFAZ direta continuam opções técnicas sem produção liberada.
## Monitor fiscal oficial concluído em 20/08/2026

- O contrato `fiscal_update_monitor_v1` acompanha notas técnicas, schemas e publicações fiscais oficiais sem executar alterações automáticas.
- A primeira consulta registra uma linha de base; novidades posteriores são deduplicadas e encaminhadas para revisão administrativa auditada.
- HTTPS, hosts oficiais, timeout, limite de resposta e cache condicional reduzem risco operacional.
- O comando de gerenciamento e o agendamento diário no Windows estão preparados, mas o recurso permanece desabilitado por padrão.
- Schemas, cálculos e endpoints continuam exigindo implementação separada, testes em homologação e aceite fiscal/contábil.
- A arquitetura permite extrair o monitor como serviço/API futuramente sem acoplar certificados ou dados operacionais dos clientes.
## Pacote isolável do Deigo Fiscal iniciado em 20/08/2026

- O núcleo SEFAZ direto foi movido para `apps/fiscal/sefaz_direta/`, preservando uma fachada no caminho antigo.
- O contrato `deigo_fiscal_capabilities_v1` registra capacidades implementadas, parciais, planejadas e dependências externas.
- A consulta de status do autorizador foi acrescentada ao adaptador e coberta por teste SOAP offline.
- A matriz Focus x Deigo Fiscal está documentada sem declarar paridade antes da homologação.
- A distribuição DF-e direta por NSU foi implementada com notas, resumos, eventos, cursor por filial e cooldown. A manifestação do destinatário, a CC-e e a consulta cadastral do contribuinte em Goiás também foram concluídas estruturalmente. Próxima sequência de produto após a homologação ativa: contingência NF-e e catálogo multi-UF.
## Distribuição DF-e direta concluída estruturalmente em 20/08/2026

- O pacote isolado consulta o serviço oficial `NFeDistribuicaoDFe` por `distNSU`, usando o A1 da filial.
- NF-e, resumos e eventos fiscais são validados e persistidos antes do avanço do cursor.
- Eventos possuem armazenamento e download próprios; não são tratados como entrada de mercadoria.
- O intervalo solicitado pela SEFAZ fica salvo por filial e bloqueia repetição antecipada da consulta.
- Rede e produção permanecem desligadas por padrão e nenhum web service real foi chamado nesta etapa.
- Pendência externa: validar A1/CNPJ no Ambiente Nacional, executar homologação real e obter aceite técnico e fiscal.
## Manifestação do Destinatário concluída estruturalmente em 20/08/2026

- Implementados os eventos 210200 (confirmação), 210210 (ciência), 210220 (desconhecimento) e 210240 (operação não realizada).
- Operação não realizada exige justificativa de 15 a 255 caracteres; os demais eventos recusam justificativa indevida.
- Ciência pode anteceder uma manifestação conclusiva, mas manifestações conclusivas conflitantes ou simultâneas ficam bloqueadas por transação.
- A regra preventiva considera 90 dias para manifestação conclusiva, conforme atualização oficial vigente desde 01/06/2026; a data efetiva de autorização deve ser confirmada na homologação.
- Histórico, cStat, protocolo, XML de envio/retorno, usuário e auditoria ficam preservados e isolados por empresa.
- O adaptador SOAP usa o Ambiente Nacional, certificado A1 e configurações independentes para rede e produção; ambas permanecem desligadas por padrão.
- Nenhum evento real foi enviado. Pendência externa: testar com certificado/CNPJ válidos em homologação e obter aceite fiscal antes de produção.
## Carta de Correção Eletrônica concluída estruturalmente em 20/08/2026

- Implementado o contrato `fiscal_cce_v1` e o evento oficial `110110` para NF-e modelo 55 autorizada.
- O serviço controla concorrência, sequências de 1 a 20, texto de 15 a 1.000 caracteres, prazo preventivo de 720 horas, histórico, XML, protocolo, auditoria e isolamento por empresa.
- A tela exige confirmação explícita dos limites legais e informa que a CC-e mais recente substitui as anteriores; alterações de imposto, preço, quantidade, remetente, destinatário e datas fiscais permanecem proibidas.
- Rede e produção ficam bloqueadas por configuração independente. Nenhum evento real foi enviado.
- Pendência externa: testar assinatura A1 e retorno do `NFeRecepcaoEvento4` em homologação de Goiás e obter aceite fiscal antes de produção.

## Consulta cadastral do contribuinte concluída estruturalmente em 20/08/2026

- Implementado o serviço `ConsCad` 2.00 para Goiás com CNPJ, CPF ou IE, histórico, XML de envio/retorno, auditoria e isolamento por empresa.
- Rede e produção possuem bloqueios independentes e permanecem desligadas por padrão.
- A migration `fiscal.0028_consultacadastrocontribuinte` materializa o histórico no banco e deve estar aplicada em cada ambiente antes do uso.
- Em 24/08/2026 foram acrescentados sete testes offline para montagem e interpretação do SOAP, validação de contrato, bloqueios independentes de rede e produção, persistência, falha auditada e ausência de adaptador; todos passaram sem comunicação externa.
- Nenhuma consulta real foi enviada. Pendência externa: revalidar endpoint e retorno vigente, testar com A1/IE válidos em homologação e obter aceite fiscal.
