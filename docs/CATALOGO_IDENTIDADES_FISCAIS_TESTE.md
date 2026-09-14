# Catálogo de identidades fiscais de teste

14/09/2026 · ciclo 109 · contrato `fiscal_test_identity_catalog_v1`.

## Objetivo

O catálogo fornece identidades determinísticas para **testes novos ou modificados** nos papéis de empresa matriz, filial, fornecedor e cliente pessoa jurídica. Ele não inicia uma troca em massa dos 331 candidatos inventariados no ciclo 108.

As bases usam o prefixo textual `TST`, e os dígitos verificadores são calculados pelo normalizador oficial já isolado. Isso oferece casos estruturalmente válidos sem afirmar titularidade. Nenhuma identidade do catálogo representa a empresa do cliente ou uma pessoa jurídica confirmada.

## Barreiras

- o arquivo começa com `test_` e é excluído dos artefatos gerados por `git archive` pelas regras de `.gitattributes`;
- a obtenção lê o ambiente configurado pelo sistema, sem aceitar que o chamador declare um ambiente mais permissivo;
- apenas `development` ou `test` são aceitos;
- somente `TESTE_UNITARIO` e `TESTE_INTEGRACAO_LOCAL` são aceitos;
- homologação, produção e finalidade operacional são recusadas;
- a descrição do catálogo não expõe os documentos completos;
- as identidades não podem receber credencial, certificado ou licença e não liberam emissão, Focus ou SEFAZ direta.

## Adoção

Novos testes devem selecionar um papel por código e informar explicitamente a finalidade; o ambiente é lido da configuração real do sistema. Testes existentes só adotarão o catálogo quando forem modificados por outro motivo e quando a alteração não reduzir a cobertura de formatos inválidos, exemplos normativos, XML ou chaves fiscais.

O primeiro uso gradual foi concluído no ciclo 110 em um novo caso do portão de leitura dupla. O teste usa o papel `FILIAL`, comprova equivalência entre forma pura e mascarada, ausência do documento no diagnóstico e preservação da entrada. Nenhum literal anterior foi substituído.

O catálogo não deve ser importado por código operacional. Validade estrutural e dígito verificador correto continuam sem provar propriedade, situação cadastral ou autorização fiscal.

## Próximo passo

O portão estático foi criado no ciclo 111 em [PORTAO_IMPORTACOES_CATALOGO_IDENTIDADES_TESTE.md](PORTAO_IMPORTACOES_CATALOGO_IDENTIDADES_TESTE.md), não encontrou uso em runtime e foi integrado à regressão padrão no ciclo 112. O próximo passo é verificar automaticamente sua exclusão do empacotamento de produção. Nenhuma migração, configuração fiscal, credencial, certificado ou ambiente foi alterado.

No ciclo 109 foram aprovados os seis testes próprios. Após a integração do ciclo 112, a cadeia acumula 61 testes focados e 522 testes da suíte fiscal completa aprovados.
