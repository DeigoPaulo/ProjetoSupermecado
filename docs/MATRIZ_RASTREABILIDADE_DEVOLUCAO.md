# Matriz de rastreabilidade da devolução — leiaute e canais

10/09/2026 · ciclo 83 · diagnóstico local, sem geração, homologação ou emissão.

Atualização do ciclo 84: as 37 famílias receberam classificação de obrigatoriedade e condicionantes em [CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md](CLASSIFICACAO_OBRIGATORIEDADE_DEVOLUCAO.md). A rastreabilidade de canais abaixo permanece inalterada e não emissiva.

Atualização do ciclo 85: o [inventário de dados](INVENTARIO_DADOS_DEVOLUCAO.md) acompanha 106 campos atômicos e fixa as lacunas locais que precisam ser resolvidas antes de qualquer serializador.

Atualização do ciclo 89: `indTot` foi modelado como candidato vazio e não confirmado, sem efeito na totalização. O inventário acompanha 108 campos e seis lacunas; nenhum canal foi liberado.

Atualização do ciclo 90: `modBC` foi isolado no grupo ICMS como candidato contábil vazio e não confirmado. O inventário acompanha 109 campos e cinco lacunas; bases, XML e canais permanecem inalterados.

Atualização do ciclo 91: `pRedBC` foi modelado como hipótese contábil vazia e não confirmada, sem copiar cadastro, XML ou memória e sem alterar a base. O inventário acompanha 110 campos e quatro lacunas.

Atualização do ciclo 92: `cEnq` foi isolado do IPI da memória e de `impostoDevol`, vazio e dependente do contador. A matriz passou a 38 famílias e o inventário a 111 campos com três lacunas; nenhum canal foi liberado.

Esta matriz confronta o contrato neutro da devolução com o pacote XSD preservado e com o código atual dos dois canais. “Focus” significa apenas a cobertura observada no conversor do ERP; não afirma limite comercial ou técnico da API externa. “SEFAZ direta” indica que o adaptador transporta a `NFe` local sem reconstruir seus campos; isso não resolve a ausência do gerador nem comprova schema, assinatura, regra de negócio ou homologação.

Evidência XSD: `PL_010f_v1.04/leiauteNFe_v4.00.xsd`, SHA-256 `2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542`. O pacote está preservado, mas não aprovado nem instalado para uso operacional.

| Bloco neutro | Destino principal no leiaute | Conversor Focus atual | SEFAZ direta atual | Situação |
|---|---|---|---|---|
| Envelope | `ide/mod`, `ide/finNFe` | Parcial | Preserva XML recebido | Bloqueado |
| Referências por item | `det/DFeReferenciado/chaveAcesso`, `nItem` | Não mapeado | Preserva XML recebido | Bloqueado |
| Identificação e partes | `ide`, `emit`, `dest` | Parcial | Preserva XML recebido | Bloqueado |
| Produtos | `det/prod` | Campos básicos mapeados | Preserva XML recebido | Bloqueado |
| Tributos por item | `det/imposto/ICMS`, `PIS`, `COFINS` | Parcial | Preserva XML recebido | Bloqueado |
| Ajustes comerciais | `prod/vFrete`, `vSeg`, `vOutro`, `vDesc` | Apenas desconto mapeado | Preserva XML recebido | Bloqueado |
| Transporte | `transp/modFrete`, `transporta`, `vol` | Apenas modalidade mapeada | Preserva XML recebido | Bloqueado |
| Totalização | `total/ICMSTot` e grupos aplicáveis | Não mapeada explicitamente | Preserva XML recebido | Bloqueado |
| Pagamento fiscal | `pag/detPag/tPag`, `vPag` | Mapeado | Preserva XML recebido | Bloqueado |
| Observações | `infAdic/infCpl`, `det/infAdProd` | Somente `infCpl` mapeado | Preserva XML recebido | Bloqueado |
| IPI e IPI devolvido | `det/imposto/IPI/cEnq`, `det/impostoDevol`, `ICMSTot/vIPIDevol` | `cEnq` parcial; devolução não mapeada | Preserva XML recebido | Hipótese pendente |
| ICMS-ST/FCP | grupos ICMS e totais conforme hipótese | Não comprovado | Preserva XML recebido | Hipótese pendente |
| IBS/CBS/RTC | `det/imposto/IBSCBS`, `total/IBSCBSTot` | Não mapeado | Preserva XML recebido | Vigência/leiaute pendentes |

## Conclusões verificáveis

- O gerador local de modelo 55 existente é próprio de pedido online: usa finalidade normal e dados do pedido. Ele não pode ser reaproveitado para devolução.
- A Focus recebe, no fluxo atual, JSON reconstruído de um XML local. Grupos ausentes dessa conversão podem ser perdidos mesmo que um futuro XML os contenha.
- A SEFAZ direta encapsula a `NFe` local no lote de autorização sem converter seu conteúdo. Isso evita uma segunda perda de campos, mas não cria os campos ausentes.
- Nenhum canal possui paridade de conteúdo da devolução validada. Nenhum campo desta matriz está liberado para serialização.

## Próximo marco

Classificar cada uma das 37 famílias como obrigatória, opcional ou condicionada, distinguindo a origem da regra — XSD, MOC/NT, regra estadual de Goiás ou decisão do contador. Somente depois dessa classificação deve ser especificado um serializador neutro e offline. Focus e SEFAZ direta deverão consumir exatamente a mesma representação aprovada e passar por homologações separadas.
