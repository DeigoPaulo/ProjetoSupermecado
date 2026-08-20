# Adaptador SEFAZ direta - Goiás

## Estado

A estrutura técnica do adaptador SOAP direto está implementada em `apps.fiscal.sefaz_direta.SefazDiretaAdapter`, porém permanece **dormente e não homologada**.

Implementado significa que o ERP já sabe montar envelopes SOAP, usar o certificado A1 no TLS, assinar XML localmente, interpretar respostas e respeitar o contrato fiscal interno. Isso não autoriza uso comercial: ainda faltam testes contra a SEFAZ de homologação, schemas oficiais completos, credenciamento da empresa, validação tributária e aceite formal.

Nenhuma chamada real foi executada nesta etapa.

## Proteções padrão

```env
FISCAL_SEFAZ_ADAPTER=
SEFAZ_DIRETA_NETWORK_ENABLED=False
SEFAZ_DIRETA_ALLOW_PRODUCTION=False
SEFAZ_DIRETA_TIMEOUT_SECONDS=30
SEFAZ_DIRETA_ENDPOINTS_JSON={}
```

Há três travas independentes:

1. O adaptador só é carregado quando sua classe é escolhida em `FISCAL_SEFAZ_ADAPTER`.
2. Mesmo selecionado, não abre conexão enquanto `SEFAZ_DIRETA_NETWORK_ENABLED=False`.
3. Produção continua bloqueada enquanto `SEFAZ_DIRETA_ALLOW_PRODUCTION=False`.

Não altere essas opções no servidor de produção antes da homologação documentada.

## Escopo preparado

- autorização síncrona NF-e/NFC-e 4.00;
- consulta por chave de acesso;
- cancelamento por evento `110111`;
- inutilização de numeração;
- assinatura XML local de `infNFe`, `infEvento` e `infInut` com A1 RSA;
- autenticação mútua TLS usando o A1 da filial;
- montagem do `nfeProc` a partir do protocolo autorizado;
- rejeição de hosts que não pertençam ao domínio oficial configurado para Goiás;
- transporte injetável para testes offline sem comunicação externa.

## Homologação futura

Somente em um servidor isolado de homologação:

```env
FISCAL_SEFAZ_ADAPTER=apps.fiscal.sefaz_direta.SefazDiretaAdapter
SEFAZ_DIRETA_NETWORK_ENABLED=True
SEFAZ_DIRETA_ALLOW_PRODUCTION=False
```

Antes do primeiro envio:

1. confirmar credenciamento NF-e/NFC-e da filial em Goiás;
2. instalar A1 válido, IE, CSC, série e numeração de homologação;
3. baixar e conferir os schemas oficiais vigentes;
4. revalidar URLs, ações SOAP, cadeias TLS e regras da nota técnica vigente;
5. executar `python manage.py validar_adaptador_sefaz --exigir-eventos --estrito`;
6. emitir cenários mínimos de autorização, rejeição, consulta, cancelamento e inutilização;
7. comparar XML, protocolo e DANFE com o retorno oficial;
8. obter aceite do responsável fiscal e do contador;
9. registrar evidências em Fiscal > Homologação GO.

A liberação de produção deve ser uma mudança separada, revisada e auditada. Nunca copie certificado, senha, CSC ou XML real para o Git.

## Endpoints

O catálogo padrão contém os web services NF-e/NFC-e de Goiás para autorização, consulta, evento, inutilização e status. Como URLs e notas técnicas podem mudar, o catálogo precisa ser revalidado no Portal Nacional da NF-e e na Secretaria da Economia de Goiás imediatamente antes da homologação.

Referências oficiais:

- Secretaria da Economia de Goiás: https://goias.gov.br/economia/documentos-fiscais/
- Endereços da versão 4.00 em homologação: https://goias.gov.br/economia/enderecos-da-versao-4-0-em-homologacao/
- Portal Nacional NF-e: https://www.nfe.fazenda.gov.br/portal/
## Monitor de publicações oficiais

O ERP possui um monitor separado do adaptador de emissão. Ele acompanha páginas oficiais e cria alertas para revisão humana, mas não baixa nem instala schemas e não altera o emissor. Consulte `docs/MONITOR_ATUALIZACOES_FISCAIS.md`.
## Organização para extração futura

O núcleo está em `apps/fiscal/sefaz_direta/` e sua matriz de capacidades em `docs/MATRIZ_PARIDADE_DEIGO_FISCAL.md`. O caminho antigo permanece somente como fachada de compatibilidade.

## Distribuição direta de DF-e pelo Ambiente Nacional

O adaptador `apps.fiscal.sefaz_direta.SefazDiretaDFeAdapter` implementa a consulta sequencial `distNSU` por CNPJ. Ele usa o certificado A1 da configuração fiscal da filial, armazena NF-e, resumos e eventos e mantém cursor independente por filial.

```env
FISCAL_DFE_ADAPTER=apps.fiscal.sefaz_direta.SefazDiretaDFeAdapter
SEFAZ_DIRETA_DFE_NETWORK_ENABLED=False
SEFAZ_DIRETA_DFE_ALLOW_PRODUCTION=False
SEFAZ_DIRETA_DFE_TIMEOUT_SECONDS=30
SEFAZ_DIRETA_DFE_MAX_XML_BYTES=5242880
SEFAZ_DIRETA_DFE_ENDPOINTS_JSON={}
```

A rede permanece desligada por padrão. A consulta não manifesta documento, não cria compra, não altera estoque e não lança financeiro. Eventos são guardados separadamente, com XML e auditoria. O cursor só avança após o lote ser persistido por completo.

A sequência de NSU não pode ser pulada. Quando o Ambiente Nacional informa que não há mais documentos, o ERP registra uma espera de uma hora e bloqueia tentativas antecipadas por filial. Isso reduz o risco de uso indevido (`cStat 656`).

Antes de habilitar rede, valide o A1 e o CNPJ em ambiente de homologação, execute os testes controlados e registre as evidências. Produção continua bloqueada por uma configuração independente.

Endpoints oficiais padrão:

- homologação: `https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx`;
- produção: `https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx`.
## Manifestação do Destinatário pelo Ambiente Nacional

O adaptador `apps.fiscal.sefaz_direta.SefazDiretaManifestacaoAdapter` transmite os quatro eventos oficiais de manifestação e mantém o recurso separado da distribuição DF-e. A interface fica no detalhe do documento recebido e preserva XML assinado, retorno, protocolo, `cStat`, usuário e auditoria.

```env
FISCAL_MANIFESTACAO_ADAPTER=apps.fiscal.sefaz_direta.SefazDiretaManifestacaoAdapter
SEFAZ_DIRETA_MANIFESTACAO_NETWORK_ENABLED=False
SEFAZ_DIRETA_MANIFESTACAO_ALLOW_PRODUCTION=False
SEFAZ_DIRETA_MANIFESTACAO_ENDPOINTS_JSON={}
```

A rede e a produção permanecem bloqueadas por padrão. Antes de liberar homologação, valide configuração fiscal ativa, certificado A1, CNPJ da filial, relógio do servidor e acesso ao endpoint oficial do Ambiente Nacional. Produção exige uma decisão separada e aceite fiscal documentado.
## Carta de Correção Eletrônica

O adaptador `apps.fiscal.sefaz_direta.SefazDiretaCartaCorrecaoAdapter` monta e assina o evento `110110` para NF-e modelo 55 autorizada. O ERP controla sequência de 1 a 20, texto consolidado de 15 a 1.000 caracteres, prazo preventivo de 720 horas, protocolo, XMLs, auditoria e isolamento por empresa.

```env
FISCAL_CCE_ADAPTER=apps.fiscal.sefaz_direta.SefazDiretaCartaCorrecaoAdapter
SEFAZ_DIRETA_CCE_NETWORK_ENABLED=False
SEFAZ_DIRETA_CCE_ALLOW_PRODUCTION=False
```

A CC-e mais recente substitui as anteriores. Ela não pode alterar base de cálculo, alíquota, preço, quantidade, valor, remetente, destinatário, data de emissão ou data de saída. A rede deve ser liberada primeiro em homologação, com certificado A1 válido e evidência do retorno oficial. Produção permanece bloqueada até aceite fiscal documentado.