# Manifesto de qualificação fiscal

## Decisão do primeiro piloto

O primeiro piloto de supermercado em Goiás usa como alvo técnico o canal
`SEFAZ_DIRETA_GO`. A Focus NFe continua disponível como integração opcional e
secundária, sem remoção de compatibilidade, fallback automático ou dependência no
caminho direto. Essa decisão não habilita rede, homologação externa nem produção.

## Separação entre construção e execução

Durante a construção, `fiscal_channel_offline_qualification_matrix_v1` confere o
código de produção e a existência das provas automatizadas. Os arquivos
`test_*.py` permanecem excluídos do pacote comercial por `.gitattributes`.

O empacotador gera e inclui dois arquivos não sensíveis:

- `fiscal_channel_qualification_manifest.json`, contrato
  `fiscal_channel_qualification_manifest_v1`;
- `server_installation_identity.json`, contrato
  `local_server_installation_identity_v1`.

O primeiro registra versão, commit, data, canal-alvo, sete operações canônicas,
estado por canal, lacunas, provas do build, contrato/hash-base do pacote e flags
negativas de rede, credenciais, homologação real e produção. O segundo declara
independentemente a versão e o commit efetivamente empacotados. Ambos possuem
SHA-256 canônico próprio.

## Validação fail-closed

O runtime recusa qualificação ausente, malformada, adulterada, de contrato
desconhecido ou divergente em versão, commit, canal, operação ou conjunto
canônico. A conclusão técnica usa
`fiscal_channel_homologation_completion_gate_v2` e exige simultaneamente:

1. canal compatível com a UF da filial;
2. manifesto íntegro para o canal e versão instalados;
3. as sete operações com evidência real aprovada no canal atual.

A conclusão do registro técnico nunca libera produção.

## Matriz vigente

As operações canônicas são: Autorização, Consulta, Rejeição, Cancelamento,
Inutilização, Eventos e DF-e. Eventos representa conjuntamente CC-e e
manifestação do destinatário.

- SEFAZ direta GO: compatibilidade offline estrutural 7/7.
- Focus NFe: compatibilidade offline estrutural 6/7; Eventos permanece como
  lacuna interna.

A lacuna da Focus bloqueia somente a conclusão pelo canal Focus. Ela não bloqueia
o piloto direto.

## Limites e próximo marco

Não foram usados CNPJ, IE, A1, CSC ou credenciais reais. Nenhuma chamada externa
foi feita. As flags de rede e produção continuam desligadas. O CSC permanece uma
pendência P2 deliberadamente não iniciada.

Quando os insumos reais existirem, o próximo marco é preparar e executar a
homologação da filial piloto com SEFAZ direta GO, operação por operação, arquivar
as evidências e obter aceite fiscal/contábil antes de qualquer decisão de
produção.
