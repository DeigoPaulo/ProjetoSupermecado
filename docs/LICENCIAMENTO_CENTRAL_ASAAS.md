# Licenciamento central e cobrança Asaas

## Arquitetura

A instalação local nunca expõe o banco de dados ou o Django diretamente à internet. O servidor do supermercado inicia uma conexão HTTPS de saída com a central da Deigo Tecnologia, apresenta sua credencial individual e recebe uma concessão assinada com validade curta.

A concessão informa contrato, situação financeira, tolerância, próxima cobrança, link de pagamento e limites contratados. Em falha de internet, a última concessão válida permanece em uso até o prazo offline.

As concessões regulares e as liberações emergenciais usam Ed25519:

- A chave privada existe somente no servidor central da Deigo Tecnologia.
- Os servidores dos clientes recebem somente a chave pública.
- Um cliente consegue validar uma autorização, mas não consegue fabricar outra.
- Em produção, `LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA` deve permanecer desativado.

## Geração das chaves

Gere o par uma única vez, em diretório seguro e fora do repositório:

```powershell
.\.venv\Scripts\python.exe manage.py gerar_chaves_licenciamento --diretorio C:\ProgramData\DeigoTecnologia\chaves
```

Não use `--substituir` em chaves que já estejam em produção sem um plano de rotação.

## Servidor central

Configure no ambiente da central:

```env
LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO=C:\ProgramData\DeigoTecnologia\chaves\licenciamento_ed25519_private.pem
LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=0
ASAAS_API_URL=https://api-sandbox.asaas.com/v3
ASAAS_API_KEY=chave-da-conta-asaas
ASAAS_WEBHOOK_TOKEN=token-exclusivo-forte-com-32-ou-mais-caracteres
ASAAS_TIMEOUT_SEGUNDOS=15
```

Cadastre no Asaas o webhook `https://SEU-DOMINIO/licenciamento/webhooks/asaas/`. O endpoint persiste o identificador de cada evento e trata reenvios de forma idempotente.

O token de autenticação do webhook deve ter entre 32 e 255 caracteres, não conter espaços e não pode ser igual à API Key. O Asaas o envia no cabeçalho `asaas-access-token`; guarde-o somente no ambiente seguro da central.

A central possui o diagnóstico protegido `licensing_readiness_v1` em `/licenciamento/central/diagnostico.json`.

Antes de conectar o sandbox, valide a mesma prontidão pelo terminal:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_prontidao_licenciamento --json --estrito
```

Para a liberação definitiva, use `--producao`. Esse modo também rejeita a URL de sandbox e retorna código de erro enquanto qualquer requisito permanecer incompleto.

### Rotina diária

O comando gera uma fatura mensal por contrato sem duplicidade, publica cobranças pendentes no Asaas e recalcula aviso, tolerância e suspensão:

```powershell
.\.venv\Scripts\python.exe manage.py processar_cobrancas_licenca
```

No Windows Server, registre a execução diária com uma conta de serviço que possua acesso ao projeto e à internet:

```powershell
.\scripts\register_licensing_billing_task.ps1 -Horario 06:00 -ExecutarSemLogin
```

Sem `-ExecutarSemLogin`, a tarefa usa a sessão interativa atual e é indicada apenas para desenvolvimento.

## Servidor local do supermercado

Na Central de licenças, credencie a instalação e guarde o token exibido uma única vez. Configure no `.env` local:

```env
LICENCIAMENTO_CENTRAL_URL=https://central.deigotecnologia.com.br
LICENCIAMENTO_API_TOKEN=token-exibido-na-ativacao
LICENCIAMENTO_INSTALACAO_ID=uuid-da-instalacao
LICENCIAMENTO_CHAVE_PUBLICA_ARQUIVO=C:\ProgramData\DeigoTecnologia\chaves\licenciamento_ed25519_public.pem
LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=0
LICENCIAMENTO_CONCESSAO_HORAS=24
LICENCIAMENTO_OFFLINE_DIAS=3
LICENCIAMENTO_TIMEOUT_SEGUNDOS=10
```

A chave privada não pode existir no servidor do supermercado.

O comando `processar_sincronizacao_completa` renova a licença junto com as demais filas. Para testar isoladamente:

```powershell
.\.venv\Scripts\python.exe manage.py sincronizar_licenca
```

## Liberação emergencial offline

Quando o servidor local não conseguir renovar a licença e a tolerância terminar:

1. O administrador da empresa abre `Licença e mensalidades` e gera um desafio de uso único, válido por 30 minutos.
2. O super admin abre `Licenciamento > Central > Liberação offline`, informa o desafio, o motivo e escolhe 24 horas, 3 dias ou 7 dias.
3. A central assina a autorização com a chave privada.
4. O administrador cola a autorização no servidor local, que valida a assinatura usando a chave pública.
5. A liberação fica auditada localmente e na central.
6. Na primeira renovação online, a utilização é reconciliada automaticamente.

A senha do super admin nunca deve ser digitada no computador do cliente.

## Política operacional

- **Ativo:** operação normal.
- **Aviso:** alerta antes do vencimento.
- **Tolerância:** operação permitida até o prazo definido no contrato.
- **Suspenso:** o administrador acessa a regularização; os demais perfis recebem bloqueio.
- **Pagamento confirmado:** o webhook baixa a fatura e reativa o contrato.
- **Sem internet:** a última concessão permanece válida apenas até o prazo offline.
- **Contingência autorizada:** liberação temporária assinada, limitada e posteriormente reconciliada.

Antes da produção, homologue o sandbox do Asaas, HTTPS, webhook, conta de serviço, backup, monitoramento e rotação controlada das chaves.
