# Monitor de atualizações fiscais oficiais

## Objetivo

O componente `fiscal_update_monitor_v1` acompanha publicações fiscais oficiais e cria uma fila de revisão humana dentro do ERP. Nesta etapa ele permanece no módulo `apps.fiscal`, mas seus limites são explícitos para permitir extração posterior como serviço independente.

O monitor **não** baixa anexos, instala schemas, altera cálculos, muda endpoints, publica código nem habilita transmissão fiscal. Uma publicação nova é somente um aviso técnico.

## Fontes padrão

- Portal Nacional da NF-e: notas técnicas e informes;
- Portal Nacional da NF-e: pacotes de schemas XML;
- Secretaria da Economia de Goiás: documentos fiscais.

Somente URLs HTTPS dos hosts oficiais autorizados são aceitas. Fontes adicionais podem ser configuradas por JSON, mas continuam sujeitas à lista de hosts do código.

## Segurança

- desabilitado por padrão;
- timeout configurável;
- resposta limitada a 2 MB;
- validação do endereço inicial e do endereço final após redirecionamentos;
- cache condicional com `ETag` e `Last-Modified`;
- parser HTML sem execução de scripts;
- linha de base na primeira consulta, sem alertas retroativos;
- deduplicação por impressão SHA-256;
- revisão/ignorar restritos a administradores e registrados na auditoria;
- nenhuma alteração fiscal automática.

## Configuração

No `.env` do servidor:

```env
FISCAL_UPDATE_MONITOR_ENABLED=True
FISCAL_UPDATE_MONITOR_TIMEOUT_SECONDS=20
FISCAL_UPDATE_MONITOR_SOURCES_JSON=[]
```

Lista vazia usa as fontes oficiais padrão. Para uma configuração futura:

```env
FISCAL_UPDATE_MONITOR_SOURCES_JSON=[{"codigo":"portal-nfe-notas-tecnicas","nome":"Portal Nacional NF-e - Notas técnicas","url":"https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=6WfrpZYE4Ik="}]
```

Não habilite uma fonte privada nem armazene credenciais nessa lista.

## Operação

Consulta manual, mesmo antes de ativar o agendamento:

```powershell
.\.venv\Scripts\python.exe manage.py monitorar_atualizacoes_fiscais --forcar --estrito
```

A primeira execução cria a linha de base. A partir da segunda, itens novos aparecem em **Fiscal > Atualizações**.

Agendamento diário no Windows, executando como `SYSTEM`:

```powershell
.\scripts\register_fiscal_update_monitor_task.ps1 -Horario "07:00" -ExecutarSemLogin
```

Para atualizar uma tarefa existente:

```powershell
.\scripts\register_fiscal_update_monitor_task.ps1 -Horario "07:00" -ExecutarSemLogin -Force
```

Em Linux, execute diariamente o mesmo comando de gerenciamento por timer do systemd ou cron, com o diretório do projeto e o ambiente virtual corretos.

## Fluxo de revisão

1. O coletor consulta as páginas oficiais.
2. A primeira coleta grava apenas a linha de base.
3. Uma alteração posterior cria alertas deduplicados.
4. O administrador abre a publicação oficial e marca o alerta como revisado ou ignorado.
5. Uma nota técnica relevante gera uma tarefa separada de engenharia.
6. Schemas e código só entram após conferência de hash/origem, testes offline, homologação SEFAZ e aceite fiscal/contábil.

## Extração futura

Para transformar o monitor em serviço isolado, preservar o contrato `fiscal_update_monitor_v1` e substituir apenas a persistência/entrega por uma API autenticada. O serviço externo poderá publicar metadados de alertas; o ERP continuará responsável pela decisão humana. Ele não deve receber certificados A1, CSC, XML de clientes ou acesso ao banco operacional.
