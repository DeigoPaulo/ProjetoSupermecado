# Matriz atômica para o XML da devolução

11/09/2026 · ciclo 94 · contrato somente diagnóstico.

O contrato `supplier_return_atomic_xml_matrix_v1` reúne, em uma única estrutura validável, os 115 campos já inventariados para a devolução de compra. Para cada campo registra:

- bloco e caminho no contrato neutro;
- fonte primária permitida;
- tratamento da ausência;
- regra de aplicação;
- destino futuro no leiaute da NF-e;
- estado observado no inventário;
- serialização ainda não implementada.

A matriz usa como evidência estrutural o pacote preservado `PL_010f_v1.04`, mas esse pacote continua sem promoção para uso operacional. O destino documentado indica onde o dado deverá ser tratado por um futuro gerador; não confirma que o campo seja aplicável ao caso concreto. Nos pontos de RTC/IBS/CBS sem leiaute vigente aprovado no projeto, o destino contém um marcador explícito de pendência em vez de presumir uma tag.

## Regras de aplicação

| Tratamento | Regra consolidada |
|---|---|
| Bloqueio | O dado precisa estar aprovado antes do futuro gerador. |
| Condicionado | O campo só será considerado quando a condição fiscal ou operacional se aplicar. |
| Política | O campo permanece vazio até existir decisão humana ou normativa aprovada. |

PIS, COFINS, IPI devolvido, ICMS-ST/FCP e IBS/CBS continuam condicionados às decisões já documentadas. A matriz não infere grupo tributário, CST, modalidade, base, alíquota ou valor.

As bases totais informativas de PIS e COFINS não possuem campo total específico em `ICMSTot`; a matriz registra explicitamente essa ausência, sem inventar tag. Elas continuam úteis para conferência da memória, não para serialização direta.

## Segurança

A validação rejeita matriz incompleta, campo duplicado, alteração de fonte, regra ou destino, evidência XSD divergente e qualquer tentativa de marcar serialização como implementada. As políticas mantêm geração XML, Focus, SEFAZ direta e emissão desativados.

A prévia protegida mostra a matriz em uma seção recolhida por padrão. Nenhum valor fiscal é exposto por esse quadro.

## Próximo passo

O limite e a ordem estrutural foram concluídos no ciclo 95 em [PLANO_GERADOR_OFFLINE_DEVOLUCAO.md](PLANO_GERADOR_OFFLINE_DEVOLUCAO.md). O próximo passo é automatizar a auditoria offline do pacote XSD e definir sua promoção versionada, sem instalar, aprovar, ativar ou gerar XML automaticamente.
