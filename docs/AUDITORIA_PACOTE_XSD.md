# Auditoria offline e promoção versionada de schemas fiscais

11/09/2026 · ciclo 96 · contrato `fiscal_schema_package_audit_v1`.

A auditoria foi separada da instalação. O comando `auditar_pacote_xsd` recebe exclusivamente um ZIP local, o SHA-256 esperado, a versão candidata e o nome do schema raiz. Ele não acessa rede, não escreve em `fiscal_schemas`, não altera configuração e não aprova o pacote.

## Verificações automáticas

- arquivo local regular, sem link simbólico e limitado a 25 MB;
- SHA-256 integral do ZIP;
- ZIP legível e CRC de todos os membros;
- até 500 arquivos e 100 MB descompactados;
- somente XSD, sem criptografia e com compressão permitida;
- caminhos relativos seguros, sem travessia, letra de unidade ou duplicidade inclusive por diferença de caixa;
- exatamente um schema raiz solicitado;
- XML bem formado em todos os XSDs;
- `include`, `import` e `redefine` exclusivamente locais e com destino presente;
- compilação do schema raiz sem rede.

A compilação usa diretório temporário privado e descartável somente durante a execução. Nenhuma extração persiste após a auditoria.

## Resultado do pacote 010f arquivado

O pacote `docs/evidencias/nfe_2026_09_10/schemas_010f.zip` foi aprovado apenas quanto à integridade técnica:

- ZIP: 41.682 bytes, SHA-256 `b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`;
- cinco arquivos XSD;
- quatro dependências relativas resolvidas;
- raiz `PL_010f_v1.04/nfe_v4.00.xsd`;
- SHA-256 da raiz `adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df`;
- CRC íntegro e compilação offline concluída.

O estado retornado é `INTEGRO_TECNICAMENTE_SEM_PROMOCAO`. Aplicabilidade normativa, aprovação fiscal, homologação e configuração explícita continuam bloqueadas.

A validação passou em 17 testes focados e na suíte fiscal completa com 435 testes. O diretório real `fiscal_schemas` permaneceu contendo somente seu README.

## Uso

```powershell
python manage.py auditar_pacote_xsd `
  --arquivo docs/evidencias/nfe_2026_09_10/schemas_010f.zip `
  --sha256 b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998 `
  --versao PL_010f_v1.04
```

A saída JSON é determinística para o mesmo pacote e não inclui caminho absoluto da máquina.

## Plano de promoção, ainda não executado

1. Confirmar a aplicabilidade integral do pacote e das NT para o cenário e a data de homologação.
2. Registrar aprovação humana do responsável fiscal/contábil e o hash exato.
3. Reexecutar a auditoria no mesmo ZIP.
4. Somente depois, executar conscientemente `instalar_schemas_fiscais`, que promove para `pacotes/<versão>` e grava manifesto.
5. Configurar separadamente diretório, raiz e hash no ambiente de homologação.
6. Validar XMLs sintéticos e cenários reais em homologação por canal.
7. Tratar produção como liberação independente, nunca decorrente automática da auditoria ou instalação.

Nenhuma dessas etapas posteriores foi executada no ciclo 96.

## Próximo passo

O confronto foi concluído no ciclo 97 em [COMPATIBILIDADE_MATRIZ_XSD_DEVOLUCAO.md](COMPATIBILIDADE_MATRIZ_XSD_DEVOLUCAO.md): 105 destinos confirmados, oito pendentes e duas ausências totais documentadas, sem divergência. O próximo passo é criar um plano de construção por bloco, ainda sem valores ou XML.