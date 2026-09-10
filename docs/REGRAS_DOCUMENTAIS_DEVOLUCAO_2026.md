# Devolução: confronto documental e plano de validação

10/09/2026 · atualizado no ciclo 82 · análise técnica parcial, sem homologação ou autorização de emissão.

O ciclo 82 acrescentou somente um portão diagnóstico sobre os 13 contratos internos. Ele não completa a leitura normativa descrita abaixo e mantém desligadas a geração, a homologação, Focus e SEFAZ direta. O próximo confronto será campo a campo entre o contrato neutro, o leiaute/XSD e cada adaptador, preservando como pendência tudo que a evidência ainda não resolver.

## Evidência e limite da análise

Foram lidos os trechos relevantes dos PDFs preservados em [evidências](evidencias/nfe_2026_09_10/README.md): MOC 7.0 Anexo I, páginas 57–58, 62 e 125–126; NT 2025.002 v1.51, páginas 6, 29–30 e 71–72; NT 2026.007 v1.00, páginas 3 e 7. As páginas 6 e 71 da NT 2025.002 foram também renderizadas e inspecionadas visualmente para distinguir datas riscadas. Não foi concluída a leitura integral de todas as notas, legislação, tabelas ou regras tributárias. Os hashes identificam as versões analisadas; não provam que sejam as últimas disponíveis nem que estejam implantadas em Goiás.

## Correção prioritária: referência por item

A proposta antiga de usar exclusivamente `ide/NFref` não atende ao desenho de devolução da NT 2025.002 v1.51. O destino previsto é `det/DFeReferenciado/chaveAcesso`, acompanhado de `nItem` da nota original. A sequência `det/@nItem` da nova nota é outra identificação e não deve substituir a original.

| Evidência | Exigência descrita no documento | Consequência para o projeto |
|---|---|---|
| NT p. 30, VC01–VC03 | Grupo por item, chave de 44 posições e nItem original; grupo e nItem opcionais no leiaute geral | Cardinalidade XSD não dispensa obrigatoriedade contextual |
| NT p. 71, VC02-14, rejeição 321 | finNFe=4 exige referência por item; observação proíbe refNFe na devolução | Não construir novo gerador usando somente NFref |
| NT p. 71, VC02-05, rejeição 1010 | Referência por item não pode coexistir com NFref no cabeçalho | Testar coexistência indevida, sem omitir silenciosamente dados |
| NT p. 71, VC02-20, rejeição 1072 | Rejeita repetição da combinação chave+nItem; sem nItem compara apenas a chave | Validar duplicidade antes de serializar |
| NT p. 72, VC03-20, rejeição 1048 | Exige nItem quando existe referência por item, exceto débito tipo 03 | Exceção não pertence ao escopo inicial de devolução de compra |
| NT p. 71, VC02-30, rejeição 1130 | Regra de documento único tem exceção para finNFe=4 | Uma nota de origem é limite inicial do produto, não proibição fiscal universal |
| NT p. 72, VC02-40/50, rejeições 1193/1194 | Mesmo emitente original nas referências; na devolução de saída, emitente original corresponde ao destinatário | Conferir partes no XML e cadastros; NFA exige tratar emitente real, não presumir identidade pela chave |

### Cronograma: divergência explícita no PDF

A observação de VC02-14 na página 71 substitui visualmente 01/09/2026 por **05/10/2026**. A linha v1.51 da página 6 também informa produção em 05/10/2026 para um conjunto que inclui VC02-14 e VC02-30, com homologação até 01/09/2026. Porém a linha histórica v1.40 da mesma página apresenta **05/10/2025** após riscar 01/09/2026. Registrar essa inconsistência documental, não corrigir a fonte nem usar a linha histórica como ativação retroativa. A data de 05/10/2026 é a indicada pela regra específica e pela linha v1.51; confirmar publicação/errata e implantação na UF antes de qualquer uso operacional. Não aplicar uma data única a todas as regras da nota.

## Pagamento e IPI devolvido

- MOC p. 62 e p. 125, YA02-04 (871): para modelo 55 de ajuste/devolução, o tratamento descrito é `tPag=90` (sem pagamento).
- MOC p. 126, YA03-30 (904): `tPag=90` com `vPag` diferente de zero é rejeitável; a regra está marcada como facultativa. O futuro contrato adotará `vPag=0.00` explicitamente, sem depender da execução facultativa pelo autorizador.
- Não gerar contas a receber, cobrança, troco ou operação de cartão nesta preparação é uma decisão de escopo do ERP. O campo fiscal “sem pagamento” não decide sozinho o acerto comercial com o fornecedor nem comprova inexistência de obrigações contábeis.
- MOC p. 57, UA01–UA04: `impostoDevol` é grupo próprio do item, com `pDevol` (máximo 100%), `IPI/vIPIDevol` e indicação do motivo em `infAdProd`. Não equivale a `det/imposto/IPI` nem ao grupo RTC `gDevTrib`.
- MOC p. 58, W12a: total `ICMSTot/vIPIDevol` corresponde à soma de UA04 e descreve aplicação nas devoluções por não contribuintes do IPI. Não inferir o enquadramento do supermercado; depende de dados reais e orientação contábil. O zero fixo no gerador de venda não implementa esse grupo.

## RTC e limites de enquadramento

A NT 2026.007 p. 3 informa homologação em 01/09/2026 e produção em 03/11/2026 para seus novos campos/regras. A p. 7 trata contribuinte exclusivamente de IBS/CBS, com regras e exceções próprias. Não enquadrar automaticamente um supermercado nessa hipótese, nem confundir esse cronograma com a referência da devolução. IBS/CBS/IS, classificações, totalização, CFOP, ST/FCP e regras complementares ainda exigem análise específica antes do contrato tributário completo.

## Confronto com o código

- `apps/fiscal/devolucao_fornecedor.py` preserva `numero_item_xml` e snapshot do item original; no ciclo 70, `extracao_contrato_devolucao.py` passou a confrontá-los com o XML autorizado e seu hash.
- `apps/fiscal/contrato_devolucao.py` mantém o envelope interno, enquanto `referencias_item_devolucao.py` valida o conjunto fiscal chave+nItem. A extração liga os dois diagnósticos, mas continua insuficiente para emitir.
- `apps/fiscal/focus_sefaz_adapter.py`: não foi localizado mapeamento de `NFref` ou `DFeReferenciado`; exigir documentação Focus e testes de paridade antes desse canal.
- `apps/fiscal/services.py`: despacho do modelo 55 para venda e total de IPI devolvido fixo continuam impedindo reutilização segura para esta operação.

## Checklist executável de retomada

- [x] Corrigir o destino documental proposto e separar restrição do produto de regra oficial.
- [x] Registrar pagamento, IPI e divergência de cronograma com versão/página/regra rastreáveis.
- [x] Implementar validador puro e não emissivo de referências por item, separado do envelope interno; entrada explícita da operação e versão da política, sem ativação automática por data (ciclo 68).
- [x] Testar estrutura: item ausente; chave inválida e dígito verificador; nItem original ausente/inválido; par duplicado; mesma chave com itens distintos; NFref simultâneo; modelo 65 e múltiplas origens fora do escopo inicial. Partes, NFA/CNPJ alfanumérico e XML original permanecem para a extração autenticada.
- [x] Integrar a extração autenticada usando chave e nItem conferidos no XML original; manter isolamento por empresa, integridade e bloqueios existentes (ciclo 70).
- [ ] Homologar a política de pagamento e o grupo IPI devolvido com casos aprovados pelo contador; completar matriz tributária e análise das NT/tabelas restantes. O contrato estrutural de pagamento foi implementado no ciclo 77, mas não substitui esse aceite.
- [ ] Confirmar cronograma oficial e pacote aplicável antes de instalar schemas ou criar gerador separado; homologar Focus e direta independentemente.

No ciclo 70, serviço, testes, prévia e documentação foram alterados. Nenhum XML foi gerado, schema instalado, certificado acessado, migração aplicada ou transmissão realizada.

## Implementação do ciclo 68

O contrato puro `supplier_return_item_references_v1`, em `apps/fiscal/referencias_item_devolucao.py`, valida modelo/operação/política explícitos, proíbe NFref no cabeçalho, exige chave de 44 dígitos com DV válido e nItem original, rejeita duplicidades do par chave+nItem e da sequência do novo documento e nunca libera XML ou emissão. Múltiplas chaves são estruturalmente reconhecidas, mas retornam bloqueio de escopo do produto. No ciclo 70, a extração passou a conferir o contrato contra banco, XML, protocolo, partes e snapshots; 92 testes conjuntos passaram. Vigência, assinatura digital, conteúdo tributário, XSD e canais externos permanecem pendentes.

## Implementação do ciclo 71

O contrato `supplier_return_identity_parties_v1` separa identificação, emitente e destinatário e registra a fonte de cada parte. A extração usa o parecer e os cadastros da filial/configuração para o emitente e preserva o emitente da NF-e original como destinatário proposto, sempre ligado ao fornecedor da entrada. Ausências de IE, CRT, endereço, município e decisões de identificação são pendências explícitas. O escopo numérico de CNPJ é temporário e bloqueia a futura forma alfanumérica até implementação e testes específicos. Nenhum resultado libera geração ou emissão.

## Implementação do ciclo 72

O contrato `supplier_return_products_v1` preserva o vínculo completo do item e só aceita valor/classificação da memória aprovada e íntegra. Campos comerciais e tributáveis são lidos do snapshot original; não são substituídos pelo cadastro atual. A coerência do valor informado é validada contra quantidade e unitário, mas o serviço não calcula nem preenche o valor. A validação continua anterior ao XML e mantém bloqueios de XSD, geração e homologação.

## Implementação do ciclo 73

O contrato `supplier_return_item_tax_values_v1` transporta bases, alíquotas e valores exatamente como aprovados na memória revisada. O vínculo de cada item com parametrização, rascunho e nItem é conferido antes da exposição. Os estados fixos dos grupos impedem usar os números como prova de hipótese fiscal: IPI da memória não vira `impostoDevol`, ST/FCP não ganha regra genérica e IBS/CBS não recebe vigência presumida. O resultado permanece não emissivo.

## Implementação do ciclo 74

O contrato `supplier_return_commercial_adjustments_v1` liga o rateio à cadeia final aprovada, mas preserva a memória anterior que originou os ajustes. Base, frete, seguro, despesas, desconto e total informado são conferidos por linha e no conjunto. O bloqueio `NAO_REAPLICAR_A_BASES_TRIBUTARIAS` impede tratar esses valores como novos impactos depois que os reflexos já foram incorporados e revisados.

## Implementação do ciclo 75

O contrato `supplier_return_transport_input_v1` usa somente a ficha vinculada à memória final aprovada e confere ficha, memória e revisão por identificadores e hashes. As regras condicionais impedem combinar modalidade sem transporte com transportador ou volumes, exigem identificação coerente quando informada e conferem pesos. O resultado apenas prepara e diagnostica dados; não cria `transp`, XML ou autorização de emissão.

## Implementação do ciclo 76

O contrato `supplier_return_diagnostic_totals_v1` totaliza separadamente os valores comerciais e cada base/valor tributário já informado, exigindo que produtos, tributos e ajustes pertençam à mesma memória aprovada. A comparação entre produtos e base comercial é diagnóstica. `vNF`, `vIPIDevol` e totais RTC permanecem vazios e qualquer preenchimento nessa etapa é erro bloqueante; nenhuma fórmula fiscal nova foi criada.

## Implementação do ciclo 77

O contrato `supplier_return_fiscal_payment_policy_v1` fixa `tPag=90` e `vPag=0.00` exclusivamente para a preparação da devolução de compra modelo 55/finalidade 4. O validador rejeita qualquer forma ou valor alternativo, o uso do total comercial e qualquer efeito operacional. A política aparece apenas na prévia fiscal restrita e não produz `pag/detPag`, XML ou transmissão.

## Implementação do ciclo 78

O contrato `supplier_return_fiscal_notes_policy_v1` classifica motivo, fundamentação e observações existentes como fontes internas por padrão. Somente IDs, hashes, presença e contagem entram no diagnóstico; os textos não são reproduzidos. `infAdic` e `infAdProd` permanecem vazios, e qualquer tentativa de preenchê-los ou habilitar exportação automática é bloqueada até existir conteúdo fiscal específico, aprovado e testado.

## Implementação do ciclo 79

O contrato `supplier_return_returned_ipi_policy_v1` representa `impostoDevol` separadamente do IPI da memória. Base, alíquota e valor anteriores aparecem apenas como referência vinculada à memória aprovada. A hipótese segue não aprovada e `pDevol`, `vIPIDevol`, justificativa fiscal e total permanecem vazios; qualquer cópia, cálculo ou preenchimento antecipado é bloqueado. A estrutura não produz XML.

## Implementação do ciclo 80

O contrato `supplier_return_icms_st_fcp_hypothesis_v1` preserva ICMS-ST e FCP da memória somente como referência. Hipótese, grupos de destino, informação complementar e totais permanecem vazios. As orientações GO 21305 e 21349 são registradas como evidências, sem aplicação automática ao caso. O validador proíbe inferir por CST/CSOSN, regime ou texto genérico e não produz XML.

## Implementação do ciclo 81

O contrato `supplier_return_rtc_vigency_policy_v1` registra a NT 2026.007 v1.00, o SHA-256 da evidência local, páginas analisadas e datas documentais de homologação/produção. Nenhuma data ou schema ativa o grupo. IBS/CBS da memória permanecem referência; enquadramento, classificação, grupos e totais RTC ficam vazios até confirmação da vigência, implantação em Goiás, leiaute aplicável e homologação independente.
