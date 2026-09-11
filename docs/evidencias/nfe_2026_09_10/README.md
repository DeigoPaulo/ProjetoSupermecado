# Evidências oficiais obtidas em 10/09/2026

Estado: obtidas e identificadas; análise normativa integral e homologação pendentes.
Download público com sessão HTTP/cookies, que resolveu o redirecionamento observado pela ferramenta de pesquisa. Não foi necessário autenticar contribuinte. Nenhum arquivo foi instalado em fiscal_schemas, nenhuma variável de ambiente ou flag foi alterada.

## Proveniência

| Arquivo | Origem oficial | SHA-256 |
|---|---|---|
| schemas_010f.zip | https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=8ITFuBLltXs%3D | b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998 |
| moc_anexo_i.pdf | https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J%2BI%2Bv4eN00E%3D | 5eb4cf2010b10b0b62f78197c4eb64025f24535d4c6e61158bc7806dd008f55d |
| nt_2025_002_v1_51.pdf | https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=AKD%2FmuSmiIY%3D | a4aaaa181522b43cd90b502f8ccb9e4bdabea30fed838e2d0790be5ba77254a4 |
| nt_2026_007_v1_00.pdf | https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=jVEAeMhv83w%3D | 559fcd7d1b495549099498ff5c1ba4165f65d4b5ad5b34dbe802869d4619d917 |

Listagem de schemas consultada: https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D . Ela identifica o pacote 010f publicado em 31/08/2026, relacionado à NT 2025.002 v1.50 e NT 2026.007 v1.00. A pasta interna do ZIP se chama PL_010f_v1.04. Não confundir versão do pacote, versão da NT e data de publicação. A NT 2025.002 v1.51 foi obtida pela listagem de notas, não inferida do nome do ZIP.

## Verificações executadas

- ZIP legível, teste CRC sem falhas, cinco arquivos XSD e uma entrada de diretório.
- nfe_v4.00.xsd compilado por lxml em memória, com resolução dos imports exclusivamente a partir do ZIP e sem acesso à rede. Isso comprova consistência de compilação, não valida uma nota nem regras de negócio.
- PDFs reconhecidos por pypdf: MOC Anexo I versão 7.00/novembro de 2020, 153 páginas; NT 2025.002-RTC versão 1.51/julho de 2026, 95 páginas; NT 2026.007 versão 1.00/julho de 2026, 11 páginas. Conferida identificação da primeira página; leitura integral ainda não realizada.

| XSD | SHA-256 |
|---|---|
| DFeTiposBasicos_v1.00.xsd | 173577a4e3a9dc1d0deced85b89b955b6064bb5a4ae5a96f6727d2da8a694d09 |
| leiauteNFe_v4.00.xsd | 2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542 |
| nfe_v4.00.xsd | adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df |
| tiposBasico_v4.00.xsd | 772619c85723e598840667ca66e7298a250442df47eeb94b397d2a333ce62047 |
| xmldsig-core-schema_v1.01.xsd | f56744a5f51c03f027de13f39f869307091781a9ef1d91b1ebe14719ce28e1ac |

## Auditoria automatizada do ciclo 96

O comando `auditar_pacote_xsd` reproduziu o SHA-256 do ZIP, validou CRC, caminhos, cinco arquivos XSD, quatro dependências relativas e compilou offline `PL_010f_v1.04/nfe_v4.00.xsd`. O contrato retornado foi `fiscal_schema_package_audit_v1`, com estado `INTEGRO_TECNICAMENTE_SEM_PROMOCAO`. Nenhum arquivo foi instalado, nenhuma configuração foi alterada e o pacote permanece sem aprovação normativa/operacional.

Detalhes em [AUDITORIA_PACOTE_XSD.md](../../AUDITORIA_PACOTE_XSD.md).
## Constatações iniciais de estrutura, não política tributária

No leiaute baixado, finNFe usa TFinNFe e sua documentação identifica 4 como devolução/retorno. NFref admite de zero a 999 ocorrências no XSD e contém a alternativa refNFe. Essa opcionalidade estrutural não dispensa regras de negócio que exigem referência.

O grupo impostoDevol contém pDevol e IPI/vIPIDevol; há também vIPIDevol no total. Não confundir esse grupo com o IPI normal já presente na memória. O leiaute possui IBSCBS e vNFTot; presença no schema não estabelece obrigatoriedade por regime/vigência.

## Próxima ação

Atualização do ciclo 67: trechos de referência, pagamento e IPI foram confrontados em [REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md](../../REGRAS_DOCUMENTAIS_DEVOLUCAO_2026.md). A existência de NFref no XSD não autoriza seu uso no novo desenho de devolução: VC02-14 exige DFeReferenciado por item. Inspeção visual das páginas 6/71 registrou divergência histórica de data no PDF. O pacote continua não aprovado/não instalado; demais regras e vigências permanecem pendentes.

Ler os trechos integrais relevantes do MOC e das NT com histórico de alterações e vigências, documentar regras e exceções de devolução, confrontar cada campo com os dados locais e testes. Verificar outras NT/tabelas aplicáveis, inclusive CNPJ alfanumérico, antes de aprovar qualquer pacote. Manter o bloqueio do XML, assinatura e transmissão; não promover o pacote automaticamente.
