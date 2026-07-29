# Schemas fiscais NF-e/NFC-e

Este diretorio recebe o pacote XSD oficial usado pela instalacao.

1. Baixe a versao vigente no Portal Nacional da NF-e:
   https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D
2. Extraia o pacote preservando a estrutura e os imports relativos.
3. Configure `FISCAL_SCHEMA_DIR` com o diretorio extraido.
4. Configure `FISCAL_NFE_SCHEMA_FILE` com o XSD raiz da NF-e 4.00.
5. Configure `FISCAL_SCHEMA_SHA256` com o SHA-256 do arquivo raiz homologado.
6. Reinicie o servidor e confira `Fiscal > Diagnostico JSON`.

O sistema usa parser sem acesso de rede, bloqueia DTD/entidades externas e
recusa o pacote quando o hash configurado diverge.

Um adaptador externo pode declarar `valida_schema = True` quando o provedor
executa essa validacao. Sem schema local valido ou essa capacidade declarada,
a transmissao de producao permanece bloqueada.

Nao substitua os arquivos durante o expediente. Homologue uma nova versao em
ambiente de testes, atualize o hash e promova a configuracao de forma controlada.

## Assinatura XML local

Por padrao, `FISCAL_LOCAL_XML_SIGNATURE_ENABLED=True`. Quando o adaptador SEFAZ
nao declara `assina_xml = True`, o ERP usa o certificado A1 protegido da filial
para assinar o `infNFe`, valida a assinatura gerada e somente depois entrega o
XML ao adaptador.

A assinatura local exige certificado A1 RSA configurado e dentro da validade.
O documento registra apenas data e serial do certificado; senha e chave privada
permanecem no armazenamento criptografado e nunca sao inseridas no XML ou log.
Defina `FISCAL_LOCAL_XML_SIGNATURE_ENABLED=False` somente quando o provedor
configurado for responsavel pela assinatura.
## Instalacao controlada

Use o comando abaixo depois que o responsavel fiscal aprovar o pacote e registrar
o SHA-256 do ZIP recebido:

```powershell
python manage.py instalar_schemas_fiscais `
  --arquivo "C:\Pacotes\schemas-oficiais.zip" `
  --sha256 "HASH_SHA256_APROVADO" `
  --versao "IDENTIFICADOR_DO_PACOTE"
```

Tambem e possivel usar `--url` com um endereco HTTPS do Portal Nacional da
NF-e. O comando aceita somente os hosts oficiais, exige o hash esperado, bloqueia
caminhos inseguros e links simbolicos no ZIP, limita tamanho e quantidade de
arquivos, compila o XSD raiz sem rede e promove a instalacao de forma atomica.
Uma versao existente so e trocada com `--substituir`.

Ao concluir, o comando imprime `FISCAL_SCHEMA_DIR`,
`FISCAL_NFE_SCHEMA_FILE` e `FISCAL_SCHEMA_SHA256` para configuracao no `.env`,
e grava `manifesto.json` com origem, versao, hashes e inventario dos XSDs.

Em 28/07/2026, o Portal Nacional listava pacotes 010d e 010e publicados na
mesma data para notas tecnicas diferentes. O ERP nao escolhe automaticamente
entre eles: contador, provedor SEFAZ e cronograma da UF devem aprovar o conjunto
antes da promocao para homologacao e producao.