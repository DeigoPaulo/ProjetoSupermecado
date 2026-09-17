# Auditoria de pré-homologação SEFAZ-GO

## 1. Escopo e referência

Registro documental de preparação/prontidão, em 17/09/2026, sobre a branch main,
HEAD b7cf2b060d9b7f0aa6e6783cc635613d8245a5bb, com árvore limpa na abertura.
Não constitui certificação, conformidade tributária integral, homologação real ou aceite da SEFAZ.

O roteiro externo tomou como referência 2aba2170b136db0e2d2066c2328765e0febfdf6b.
O ciclo 126 é posterior: seus resultados foram incorporados abaixo sem reabrir correções
concluídas. Este registro não recebe número de ciclo técnico e preserva a retomada planejada.

Método: inspeção local de código e histórico do roadmap, sem rede, banco operacional,
certificado real, transmissão ou consulta a serviços fiscais. Regras legais propostas pelo
roteiro são hipóteses de revisão normativa; não foram verificadas em fontes oficiais neste
ciclo. Nenhum resultado novo de teste funcional é alegado.

## 2. Estado do código e significado dos estados

IMPLEMENTADO indica existência estrutural no código; PARCIAL indica cobertura limitada;
BLOQUEADO mantém emissão indisponível no cenário; DEPENDENCIA_EXTERNA exige evidência
fora da inspeção; PLANEJADO indica trabalho ainda por executar. Compatibilidade offline
não implica compatibilidade do canal externo.

| Área | Estado | Evidência local e limite |
|---|---|---|
| NF-e 55 / NFC-e 65 | IMPLEMENTADO | Geradores em apps/fiscal/services.py; cenários limitados |
| XML 4.00 / cUF GO 52 | IMPLEMENTADO | infNFe e tabela CODIGOS_UF_IBGE em services.py |
| Homologação/produção | IMPLEMENTADO | Modelos/configuração e séries por ambiente; sem comprovação de habilitação real |
| Endpoints GO | IMPLEMENTADO | apps/fiscal/perfis_uf.py e sefaz_direta/adapter.py; existência não prova disponibilidade |
| Certificado A1 / assinatura | IMPLEMENTADO | certificados.py e assinaturas.py; certificado real do piloto pendente |
| QR Code NFC-e v3 | IMPLEMENTADO | VERSAO_QRCODE_NFCE = 3 em qrcode_nfce.py; validação offline |
| DANFE HTML / Code 128 C/A | IMPLEMENTADO | barcode_chave.py e templates/fiscal/danfe_nfce.html; ciclo 125 |
| NFC-e tpEmis 9 | IMPLEMENTADO | Chave alfa reconhecida após ciclo 126; homologação real pendente |
| SVC-RS NF-e tpEmis 7 | IMPLEMENTADO | Estrutura em services.py; transporte alfa e homologação pendentes |
| NCM / CEST / CFOP | IMPLEMENTADO | Catálogos e validadores; classificação real dos produtos pendente |
| cBenef GO | PARCIAL | Catálogo por vigência/CST; cobertura de obrigatoriedade a revisar |
| CNPJ alfa interno | PARCIAL | Inventário v6: 16 pontos offline e Code 128 RAW ausente; não significa cobertura universal |
| Texto/QR no Desktop | IMPLEMENTADO | Servidor valida chave; Desktop preserva texto; ciclo 126 |
| Code 128 RAW/ESC-POS | PLANEJADO | Depende de compatibilidade e homologação por impressora |
| SEFAZ direta / inutilização / DF-e alfa | PLANEJADO | Normalizações numéricas ainda identificadas |
| XSD oficial aplicável instalado | DEPENDENCIA_EXTERNA | fiscal_schemas contém README.md; instalação externa não foi inspecionada |
| IBS/CBS | PARCIAL | Cadastro/estrutura; cronograma e implementação dependem do regime real |
| Homologação real GO | DEPENDENCIA_EXTERNA | Não realizada segundo o histórico; sem evidência real apresentada nesta auditoria |

## 3. Estrutura NF-e/NFC-e e consumidor PJ

CONFIRMADO NO CÓDIGO: services.py bloqueia NFC-e identificada por CNPJ e orienta modelo 55.
Essa é uma política atual do sistema; a inspeção não estabelece sua abrangência legal.

- [ ] P1.1: revisar com fontes oficiais vigentes a escolha entre modelos 55 e 65 para
  consumidor PJ; verificar consumidor final, operação interna, condição do destinatário,
  indicador de IE, cenário tributário e eventual crédito.
- [ ] Registrar a decisão com vigência, fonte e testes de aceitação antes de alterar a regra.

A alegação externa de que determinados cenários PJ poderiam usar NFC-e permanece sujeita
à confirmação normativa. Não foi acrescentada retrospectivamente ao escopo do ciclo 126.

## 4. Regras específicas GO

CONFIRMADO NO CÓDIGO: cbenef.py possui catálogo com vigência e compatibilidade por CST.
perfis_uf.py exige benefício principalmente quando há redução de base no regime normal.

- [ ] P1.2: tratar COBERTURA DE OBRIGATORIEDADE INCOMPLETA; confrontar a tabela oficial
  aplicável para redução, isenção, não incidência e demais situações, sem presumir que
  toda ocorrência dessas situações exige o mesmo tratamento.
- [ ] P1/P2: AUDITORIA REGULATÓRIA NECESSÁRIA sobre readiness/CSC: readiness.py ainda
  exige csc_id e csc_token, enquanto qrcode_nfce.py usa versão 3. Confirmar a regra
  vigente e o modo de emissão antes de alterar diagnóstico ou remover CSC.

## 5. Transporte SEFAZ e Fase 6

CONFIRMADO NO CÓDIGO: sefaz_direta/adapter.py remove não dígitos da chave antes da
verificação de 44 posições; services.py, em solicitar_inutilizacao_numeracao, reduz
o CNPJ a dígitos; dfe_adapters.py filtra letras da chave.

- [ ] F6.1: revisar autorização, consulta, protocolo, cancelamento, eventos, CC-e,
  manifestação e demais serviços que transportam chave no canal direto.
- [ ] F6.2: preservar CNPJ canônico na inutilização, com validação e testes próprios.
- [ ] F6.3: revisar separadamente distribuição DF-e, identidade CNPJ, chaves, manifestações
  e consultas por NSU; o NSU permanece numérico, não deve ser convertido em identidade alfa.
- [ ] F6.4: comprovar compatibilidade Focus em contrato/testes e homologação próprios.
- [ ] Validar cada canal com evidências independentes antes de habilitá-lo.

## 6. Contingência e impressão

P1.6 do roteiro externo foi tratado no ciclo 126: documento_em_contingencia_offline usa
normalizar_chave_acesso e consulta tpEmis na posição correta, preservando o caminho por status.
A correção offline não comprova emissão, recuperação ou prazo em ambiente real.

P1.4 foi tratado quanto à preservação textual e QR no Desktop. Não existe Code 128 RAW
homologado. O import direto do normalizador fiscal pelo Desktop foi evitado por acoplamento;
o servidor valida a chave e o Desktop confere o envelope estrutural recebido.

- [ ] Homologar contingência NFC-e, recuperação/reprocessamento e SVC-RS nos cenários aplicáveis.
- [ ] Homologar texto, QR, corte e leitura física por impressora/papel.
- [ ] Definir e validar Code 128 RAW C/A após comprovar suporte do hardware.

## 7. Tributação

DEPENDÊNCIA TRIBUTÁRIA: estados reproduzem apps/fiscal/cenarios_tributarios.py.
Estruturas de cadastro e contratos de devolução não significam emissão implementada.

| Cenário | Estado |
|---|---|
| Venda interna a consumidor final | PARCIAL |
| Venda interestadual | BLOQUEADO |
| Venda para contribuinte B2B | BLOQUEADO |
| ICMS-ST | BLOQUEADO |
| Tributação monofásica | BLOQUEADO |
| Devolução ao fornecedor | BLOQUEADO |
| Transferência / bonificação / remessa | BLOQUEADO |
| Frete | BLOQUEADO |
| cBenef | PARCIAL |
| PIS/COFINS/IPI | PARCIAL |
| IBS/CBS | PARCIAL |

IBS/CBS: a decisão sobre produção em 2026 depende do CRT real. Não presumir cronograma
igual para CRT 1, 2, 3 e 4.

- [ ] Confirmar CRT e cronograma aplicável com fontes oficiais/contador.
- [ ] Confirmar XSD vigente e grupos exigidos.
- [ ] Implementar grupos e cálculos necessários, criar testes e validar em homologação.

## 8. CNPJ alfanumérico e histórico

Resultados do ciclo 126, já registrados no roadmap e no commit de referência:

| Item externo | Estado atualizado |
|---|---|
| P1.3 — DV do emitente | Corrigido offline: normalizar_cnpj_emitente exige validar_dv_cnpj |
| P1.4 — Desktop | Texto/QR preservados; Code 128 RAW continua pendente |
| P1.5 — destinatário/marketplace | Canonicalização e DV integrados ao snapshot e XML |
| P1.6 — contingência alfa | Leitura central da chave integrada |

O DV próprio da chave não substitui o DV do CNPJ. Cadastros legados inválidos não devem
ser reparados automaticamente. O inventário v6 ampliou os 11 pontos originais para 17.
Os snapshots históricos permanecem referências de seus respectivos ciclos.

Próxima entrega técnica permanece: compatibilidade da identidade CNPJ alfa fora do fiscal,
incluindo credenciais/eventos de sincronização, resolução Empresa/Filial, licenciamento,
challenge/release offline e Asaas/provedor externo sem descarte de letras.

## 9. XSD

CONFIRMADO NO CÓDIGO: configuração FISCAL_SCHEMA_DIR, FISCAL_NFE_SCHEMA_FILE e
FISCAL_SCHEMA_SHA256; parser sem rede/entidades externas, hash e compilação offline em
validacoes.py; comandos instalar_schemas_fiscais e auditar_pacote_xsd.

O diretório fiscal_schemas versionado contém somente README.md. Isso não permite concluir
se há pacote instalado em outro diretório ou ambiente; nenhuma instalação foi auditada aqui.

- [ ] Obter o pacote oficial aplicável e registrar origem/versão.
- [ ] Calcular e conferir SHA-256 com a evidência de origem preservada.
- [ ] Compilar offline e instalar de forma controlada em homologação.
- [ ] Validar os XMLs efetivamente gerados pelo ERP.
- [ ] Congelar a versão utilizada pelo piloto, com procedimento de atualização.

## 10. Dependências externas e supermercado piloto

DEPENDENCIA_EXTERNA: testes unitários não comprovam credenciamento, regularidade ou titularidade.

- [ ] Confirmar CNPJ, IE regular, CRT, CNAE relevante e natureza das operações.
- [ ] Comprovar habilitação/credenciamento fiscal e eventuais autorizações estaduais.
- [ ] Obter A1 válido, configuração da filial e ambiente de homologação.
- [ ] Classificar produtos reais: NCM, CEST quando aplicável, CST/CSOSN, PIS/COFINS,
  cBenef quando aplicável, cenários ICMS e formas de pagamento.
- [ ] Classificar cada SKU/combinação de operação do piloto como SUPORTADO ou BLOQUEADO.
- [ ] Impedir emissão quando o cenário tributário do SKU/operação for desconhecido.

A classificação e os bloqueios devem ser demonstrados antes de produção, com revisão contábil.

## 11. Riscos e sequência

Riscos: confundir estrutura com conformidade; liberar SKU desconhecido; usar cadastro legado
inválido; perder letras nos canais externos; supor hardware compatível; usar XSD ou regra
tributária sem vigência confirmada.

Sequência recomendada, sem renumerar história nem iniciar trabalho técnico neste registro:

1. Ciclo 126 concluído offline, com pendência de hardware explícita.
2. Próximo ciclo técnico: identidade alfa fora do fiscal (sincronização/licenciamento).
3. Frente tributária GO: decisão consumidor PJ/modelo, cBenef, readiness/CSC e cenários do piloto.
4. Fase 6: SEFAZ direta, inutilização, eventos, DF-e e Focus.
5. Preparação: XSD aplicável, CRT/dados reais, A1, credenciamento e configuração de homologação.
6. Homologação real por canal e filial, com evidências.

## 12. Critérios e bateria futura de homologação real

PENDENTE DE HOMOLOGAÇÃO REAL: cada item exige evidência obtida no ambiente fiscal
de homologação, com data, canal, filial, versão/configuração e resultado esperado/obtido.
Cenário não aplicável exige justificativa e delimitação do escopo.

- [ ] Status do serviço SEFAZ-GO.
- [ ] Autorização e consulta NFC-e.
- [ ] Autorização e consulta NF-e.
- [ ] Rejeição controlada e sua correção.
- [ ] Cancelamento e inutilização.
- [ ] Contingência NFC-e e SVC-RS NF-e.
- [ ] Consulta cadastral.
- [ ] CC-e e manifestação, quando aplicáveis.
- [ ] Distribuição DF-e.
- [ ] QR Code e DANFE.
- [ ] Reimpressão e leitura no hardware do piloto.
- [ ] Armazenamento e recuperação de XML com protocolo.

Gerar XML, passar teste unitário, compilar schema, carregar adaptador ou ter endpoint não
autoriza declarar o sistema homologado para Goiás. O fechamento exige interações reais
documentadas no ambiente de homologação para o escopo aceito. Este documento registra
prontidão e pendências; não fornece esse aceite.
