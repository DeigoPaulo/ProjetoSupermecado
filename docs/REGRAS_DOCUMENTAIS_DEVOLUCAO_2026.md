# Devolução: confronto documental e plano de validação

10/09/2026 · atualizado no ciclo 70 · análise técnica parcial, sem homologação ou autorização de emissão.

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
- [ ] Testar pagamento sem cobrança e grupo IPI devolvido com casos aprovados pelo contador; completar matriz tributária/totalização e análise das NT/tabelas restantes.
- [ ] Confirmar cronograma oficial e pacote aplicável antes de instalar schemas ou criar gerador separado; homologar Focus e direta independentemente.

No ciclo 70, serviço, testes, prévia e documentação foram alterados. Nenhum XML foi gerado, schema instalado, certificado acessado, migração aplicada ou transmissão realizada.

## Implementação do ciclo 68

O contrato puro `supplier_return_item_references_v1`, em `apps/fiscal/referencias_item_devolucao.py`, valida modelo/operação/política explícitos, proíbe NFref no cabeçalho, exige chave de 44 dígitos com DV válido e nItem original, rejeita duplicidades do par chave+nItem e da sequência do novo documento e nunca libera XML ou emissão. Múltiplas chaves são estruturalmente reconhecidas, mas retornam bloqueio de escopo do produto. No ciclo 70, a extração passou a conferir o contrato contra banco, XML, protocolo, partes e snapshots; 92 testes conjuntos passaram. Vigência, assinatura digital, conteúdo tributário, XSD e canais externos permanecem pendentes.
