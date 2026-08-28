# Prontidão de implantação

O comando consolidado valida a configuração do servidor sem exibir segredos. Ele possui dois perfis distintos:

- **central**: servidor da Deigo Tecnologia, com licenciamento, cobrança e integrações globais;
- **servidor-local**: servidor instalado no supermercado, sem exigir a chave privada da central, Asaas ou webhook público.

~~~powershell
python manage.py verificar_prontidao_implantacao
python manage.py verificar_prontidao_implantacao --perfil central --estrito
python manage.py verificar_prontidao_implantacao --perfil servidor-local --estrito
python manage.py verificar_prontidao_implantacao --perfil servidor-local --producao
python manage.py verificar_prontidao_implantacao --perfil servidor-local --producao --exigir-midia-offline
python manage.py verificar_prontidao_implantacao --perfil central --producao --json
~~~

## Critérios comuns

- segurança básica do Django: chave própria, hosts explícitos e DEBUG=False em produção;
- HTTPS em produção com cookies seguros, redirecionamento, HSTS e proxy reverso configurado;
- conexão real com o banco, migrações aplicadas e PostgreSQL obrigatório em produção.

## Perfil central

Também são obrigatórios:

- licenciamento central pronto para o ambiente escolhido;
- SMTP da recuperação de senha configurado.

O perfil central é o único que valida os segredos e integrações privadas de licenciamento. Eles nunca devem ser copiados para o servidor do cliente.

## Perfil servidor local

Também é obrigatória a presença dos artefatos operacionais para:

- instalar, testar e remover o serviço Windows;
- empacotar, publicar e atualizar o servidor;
- executar e restaurar backup;
- registrar tarefas de backup e sincronização;
- consultar os manuais de implantação e instalação.

SMTP, consulta externa de CNPJ/CEP e HTTPS em homologação aparecem como recomendações. Em produção, HTTPS passa a ser obrigatório. A ativação comercial, a concessão de licença e a sincronização continuam sendo homologadas na instalação real.

## Modos estritos

--estrito encerra com código diferente de zero quando um critério obrigatório falha. --producao já é estrito. Use --exigir-recomendados quando o pipeline também precisar bloquear recomendações pendentes.

## Limite do diagnóstico

O comando não substitui a homologação por empresa, filial e terminal. Fiscal, TEF, impressoras, gaveta, balança, etiquetas, sincronização e dispositivos devem seguir seus roteiros próprios no ambiente real.

Antes da liberação, arquive a saída JSON junto ao registro técnico:

~~~powershell
python manage.py verificar_prontidao_implantacao --perfil servidor-local --producao --json
~~~

## Dossiê de implantação

O comando abaixo reúne a prontidão, as versões do Django/Python, as versões planejadas e a integridade dos artefatos do PDV e do servidor local:

~~~powershell
python manage.py gerar_dossie_implantacao --perfil servidor-local --producao --saida artifacts/dossie_implantacao.json
python manage.py gerar_dossie_implantacao --perfil servidor-local --producao --exigir-midia-offline --saida artifacts/dossie_implantacao-offline.json
~~~

São produzidos o JSON sanitizado e o arquivo dossie_implantacao.json.sha256. O relatório não inclui tokens, senhas, URLs privadas nem caminhos absolutos da máquina. Um dossiê bloqueado continua sendo gerado para registrar com precisão o que falta antes da liberação.


Valide o arquivo recebido antes do aceite:

~~~powershell
python manage.py verificar_dossie_implantacao artifacts/dossie_implantacao.json
python manage.py verificar_dossie_implantacao artifacts/dossie_implantacao.json --estrito
~~~

O modo estrito encerra com erro quando o hash divergir, a estrutura estiver inválida, a prontidão estiver bloqueada ou o pacote obrigatório do servidor local não estiver publicável.


## Aceite pós-instalação

Depois de instalar e iniciar o serviço na loja, valide o ambiente em execução:

~~~powershell
python manage.py verificar_pos_implantacao
python manage.py verificar_pos_implantacao --estrito
python manage.py verificar_pos_implantacao --json
~~~

O contrato local_post_deployment_health_v1 exige resposta HTTP, PostgreSQL conectado e sem migrações pendentes, escrita nos diretórios de estáticos, mídia e logs, além de backup local recente. A idade máxima vem da mesma política `backup_age_policy_v1` usada pelo painel Master: configure `LOCAL_BACKUP_MAX_AGE_HOURS=36` após homologar o agendamento. O valor `0` mantém o painel desligado e bloqueia o aceite técnico. `--backup-max-horas` continua disponível somente como substituição explícita para uma execução e sua origem fica registrada no diagnóstico. O subcontrato `local_backup_package_validation_v1` recalcula o SHA-256 do pacote mais recente e exige sidecar vinculado ao nome, ZIP integral sem caminhos inseguros, `erp_local_backup_v2`, `dados.json`, banco declarado e âncora fiscal coerente. Pacotes `.zip.aes` são descriptografados apenas em área temporária local quando `BACKUP_ENCRYPTION_PASSPHRASE` está disponível; ausência ou erro da senha bloqueia o aceite e o JSON nunca inclui caminho, senha ou hash. Para comprovar que o conteúdo é utilizável sem tocar na instalação, o SQLite também pode passar por `restore_local_backup.ps1 -EnsaiarIsolado`, produzindo o contrato `local_restore_rehearsal_v1` após integridade, migrations, Django check e verificação fiscal. Esse ensaio complementa o aceite. PostgreSQL requer base previamente criada, vazia, com prefixo `deigo_rehearsal_`, variáveis `RESTORE_REHEARSAL_POSTGRES_*` no processo protegido e confirmação explícita; o script recusa origem/ativo, não cria nem remove banco e preserva o alvo restaurado para inspeção.


Consolide o dossiê validado e o healthcheck no anexo técnico do termo de aceite:

~~~powershell
python manage.py gerar_evidencia_aceite --dossie artifacts/dossie_implantacao.json --saida artifacts/evidencia_aceite.json --estrito
~~~

A evidência local_installation_acceptance_evidence_v1 grava somente o hash do dossiê de origem, sua validação e o diagnóstico pós-instalação. O JSON e seu arquivo SHA-256 devem ser arquivados junto ao termo assinado.

O super admin também pode gerar esses documentos em **Sistema > Servidor local > Baixar evidências**. A ação entrega um ZIP com o dossiê, a evidência de aceite, os dois arquivos SHA-256 e as instruções de arquivamento. O download é auditado e permanece disponível quando o aceite estiver bloqueado, para registrar as pendências encontradas.

Antes do download, `publish_detech_server_offline.ps1` deve ter revalidado origem e cópia temporária, promovido ZIP/checksum e mantido rollback automático. A Central repete o aceite pelo contrato `detech_server_offline_publication_validation_v1` e não libera o instalador sem sidecar íntegro e vinculado ao nome final. A mídia usada nessa máquina só deve ser baixada quando a Central confirmar `detech_server_offline_package_validation_v2`: todos os componentes declarados, ZIP interno do servidor, wheelhouse `.whl`, aplicativos e manifestos íntegros, sem duplicidade, caminho inseguro ou arquivo extra. Essa validação não instala serviço, não abre firewall e não toca no banco.

A política `local_installation_media_policy_v1` é escolhida por implantação. **Evidências com rede** mantêm a mídia offline opcional: uma publicação pendente aparece como recomendação, mas não bloqueia o dossiê. **Evidências offline** registram `midia_offline_exigida=true`; nesse modo, prontidão, dossiê e aceite ficam bloqueados até ZIP e SHA-256 passarem pela validação de publicação. As duas opções existem somente na área Master do servidor local.

A homologação executada em uma máquina limpa deve ser registrada na mesma tela. O histórico é exclusivo do super admin, paginado em 20 registros e vincula máquina, sistema operacional, versão testada, resultado, responsável e SHA-256 único da evidência. O registro recebe o JSON e seu arquivo SHA-256, compara a integridade e valida o contrato de aceite antes de persistir somente o hash e os metadados; uma aprovação exige status liberável. O diagnóstico operacional compara o aceite à versão vigente e apresenta pendente, reprovada, desatualizada, incompleta ou aprovada; aceites legados sem todos os testes críticos nunca liberam uma versão. Uma reprovação exige observações para manter explícita a ação corretiva.



## Verificacao automatica da homologacao do servidor local

Antes de publicar ou instalar uma versao, valide se o artefato possui uma
homologacao aprovada e com todo o checklist critico concluido:

~~~powershell
python manage.py verificar_homologacao_servidor_local
python manage.py verificar_homologacao_servidor_local --json
python manage.py verificar_homologacao_servidor_local --estrito
python manage.py verificar_homologacao_servidor_local --versao 1.2.0 --estrito
~~~

O modo `--estrito` encerra com erro quando a versao esta pendente, reprovada,
incompleta ou desatualizada. Ele deve ser usado pelo instalador e pelo pipeline
para impedir a distribuicao de um servidor local ainda nao homologado.


## Regressao automatizada

Antes de gerar um pacote, execute o roteiro de regressao. O perfil rapido separa
os grupos de modulos para mostrar com clareza onde ocorreu uma falha; o completo
deve ser usado pela maquina de build ou CI, com uma janela de execucao maior.

~~~powershell
.\scripts\test_regression.ps1
.\scripts\test_regression.ps1 -Perfil rapido -KeepDb
.\scripts\test_regression.ps1 -Perfil completo
~~~
