# Prontidão de implantação

O comando consolidado valida a configuração do servidor sem exibir segredos. Ele possui dois perfis distintos:

- **central**: servidor da Deigo Tecnologia, com licenciamento, cobrança e integrações globais;
- **servidor-local**: servidor instalado no supermercado, sem exigir a chave privada da central, Asaas ou webhook público.

~~~powershell
python manage.py verificar_prontidao_implantacao
python manage.py verificar_prontidao_implantacao --perfil central --estrito
python manage.py verificar_prontidao_implantacao --perfil servidor-local --estrito
python manage.py verificar_prontidao_implantacao --perfil servidor-local --producao
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

O contrato local_post_deployment_health_v1 exige resposta HTTP, PostgreSQL conectado e sem migrações pendentes, escrita nos diretórios de estáticos, mídia e logs, além de backup local recente. A idade máxima padrão do backup é 36 horas e pode ser alterada com --backup-max-horas.


Consolide o dossiê validado e o healthcheck no anexo técnico do termo de aceite:

~~~powershell
python manage.py gerar_evidencia_aceite --dossie artifacts/dossie_implantacao.json --saida artifacts/evidencia_aceite.json --estrito
~~~

A evidência local_installation_acceptance_evidence_v1 grava somente o hash do dossiê de origem, sua validação e o diagnóstico pós-instalação. O JSON e seu arquivo SHA-256 devem ser arquivados junto ao termo assinado.

O super admin também pode gerar esses documentos em **Sistema > Servidor local > Baixar evidências**. A ação entrega um ZIP com o dossiê, a evidência de aceite, os dois arquivos SHA-256 e as instruções de arquivamento. O download é auditado e permanece disponível quando o aceite estiver bloqueado, para registrar as pendências encontradas.

A homologação executada em uma máquina limpa deve ser registrada na mesma tela. O histórico é exclusivo do super admin, paginado em 20 registros e vincula máquina, sistema operacional, versão testada, resultado, responsável e SHA-256 único da evidência. O registro recebe o JSON e seu arquivo SHA-256, compara a integridade e valida o contrato de aceite antes de persistir somente o hash e os metadados; uma aprovação exige status liberável. Uma reprovação exige observações para manter explícita a ação corretiva.

