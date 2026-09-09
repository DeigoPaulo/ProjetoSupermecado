import csv
import hashlib
import json
import os
import re
import unicodedata
import zipfile
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.paginator import Paginator
from django.core.exceptions import (
    ObjectDoesNotExist,
    PermissionDenied,
    RequestDataTooBig,
    ValidationError,
)
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.accounts.permissions import ADMINISTRACAO, SISTEMA, has_role, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, ModoImplantacao, StatusEventoEntrada, StatusSincronizacao
from apps.fiscal.integridade_operacional import diagnostico_integridade_operacional
from apps.fiscal.models import ConfiguracaoFiscal
from apps.financeiro.models import ContaMovimentoFinanceiro
from apps.estoque.diagnostico_snapshots import diagnostico_cobertura_snapshots_lote
from apps.estoque.dossie_piloto import gerar_dossie_piloto
from apps.estoque.evidencia_piloto import gerar_evidencia_fluxo_estoque_piloto
from apps.estoque.ficha_execucao_piloto import gerar_ficha_execucao_piloto
from apps.estoque.previsualizacao_piloto import previsualizar_candidatos_piloto
from apps.estoque.verificador_artefatos_piloto import (
    ArtefatoPilotoMemoryUploadHandler,
    carregar_artefato_upload,
    verificar_integridade_artefatos_piloto,
)
from apps.estoque.verificador_dossie_piloto import (
    DossiePilotoMemoryUploadHandler,
    verificar_dossie_piloto_upload,
)
from apps.estoque.services import diagnostico_manutencao_inventarios_validade
from apps.pdv.models import AcessoPdvNuvem, CanalAtualizacaoPdv, EventoDispositivoTerminal, StatusAcessoPdvNuvem, StatusLicencaTerminal, TerminalPdv
from apps.vendas.models import FormaPagamento, FormaPagamentoFilial, PagamentoVenda, StatusPagamento
from apps.vendas.services import inicializar_formas_pagamento_filial

from .artifacts import artefato_admin_desktop, artefato_pdv_desktop, artefato_servidor_local
from .backup_operacional import diagnostico_periodicidade_backup, historico_backup_operacional
from .offline_bundle import artefato_servidor_offline
from .acceptance_evidence import gerar_evidencia_aceite
from .deployment_evidence import gerar_dossie_implantacao
from .homologation import diagnostico_homologacao_servidor_local
from .homologacao_operacional import ROTEIRO_HOMOLOGACAO_OPERACIONAL
from .forms import ConfiguracaoImpressaoForm, FormaPagamentoFilialForm, FormaPagamentoForm, HomologacaoServidorLocalForm, ModeloEtiquetaForm, TerminalPdvForm
from .models import ConfiguracaoImpressao, HomologacaoOperacional, HomologacaoServidorLocal, ModeloEtiqueta, ResultadoHomologacaoServidor, TipoDocumentoImpressao
from .post_deployment import diagnostico_pos_implantacao_local
from .readiness import diagnostico_prontidao_servidor_local
from .services import configuracao_impressao_para, criar_configuracoes_padrao


CHECKLIST_GRUPOS = [
    {
        "titulo": "Base técnica",
        "descricao": "Fundação do projeto, arquitetura e segurança inicial.",
        "itens": [
            ("Projeto Django com apps modulares", "done", "Estrutura separada por accounts, produtos, estoque, compras, PDV, vendas e relatórios."),
            ("Settings, timezone e ambiente local", "done", "Configuração por ambiente via .env, segurança de produção, logs e caminhos ajustáveis definidos."),
            ("Perfis de prontidão da implantação", "done", "O pré-deploy diferencia servidor central e servidor local. O perfil central valida licenciamento, Asaas e recuperação de senha; o perfil da loja valida serviço, pacote, atualização, backup, restauração e sincronização sem exigir ou expor segredos privados da Deigo Tecnologia. Ambos verificam segurança Django, banco, migrações e HTTPS conforme o ambiente."),
            ("Modelagem inicial e migrations", "done", "Modelos principais criados para usuários, produtos, estoque, compras, PDV, vendas e auditoria."),
            ("Permissoes por perfil no backend", "done", "Perfis e bloqueios por módulo implementados com tela 403 amigável. O super admin mantém visão global; administradores de cada cliente listam, criam e editam somente usuários obrigatoriamente vinculados à própria matriz ou filiais, não acessam equipes de outras empresas e não podem conceder acesso ao admin Django. Gerentes não acessam cadastro de usuários, auditoria administrativa nem o painel administrativo geral; checklist técnico, backup global, sincronização central, distribuição desktop e painel master ficam ocultos e protegidos por rota para uso exclusivo do super admin."),
            ("Cadastro próprio de empresas e filiais", "done", "Sistema possui telas internas para empresa e filiais, incluindo município, UF e código IBGE fiscal, sem depender do admin padrão. Como matriz e cada filial representam unidades comerciais licenciadas, somente o super admin do software pode criá-las; toda criação gera auditoria. O administrador da empresa consulta e atualiza apenas a própria matriz e suas filiais, sem enxergar estruturas de outros clientes. O endereço agora é estruturado em CEP, logradouro, número, complemento, bairro, município e UF; consultas de CNPJ e CEP possuem ações separadas e o endereço completo legado continua preservado para documentos e integrações."),
            ("Licenciamento comercial e cobrança central", "partial", "Módulo separado do financeiro operacional criado com planos por matriz, filial e terminal, contratos, faturas mensais idempotentes, instalações locais com token individual protegido por hash, concessão assinada de 24 horas, renovação automática no sincronizador, aviso pré-vencimento, tolerância configurável, bloqueio gradual e tela de regularização para o administrador. A central exclusiva do super admin gera cobrança Pix/boleto pelo Asaas, recebe webhook autenticado e idempotente e reativa o contrato após confirmação. O servidor local inicia somente conexão HTTPS de saída, preserva a última concessão em falha de internet e não expõe banco ou porta administrativa. A contingência presencial agora usa desafio local de uso único por 30 minutos e autorização Ed25519 emitida exclusivamente pelo super admin, vinculada à empresa e instalação, com validade máxima de 7 dias, rejeição de adulteração/reuso, auditoria local/central e reconciliação automática quando a internet retorna; a senha master nunca é digitada no cliente. As concessões automáticas regulares também usam envelope Ed25519; em produção a ausência da chave privada falha de forma segura e o fallback compartilhado permanece permitido somente por configuração explícita de transição. O diagnóstico protegido licensing_readiness_v1 mostra chave, HTTPS, Asaas, webhook, fallback e script de automação. O comando verificar_prontidao_licenciamento oferece saída humana ou JSON e modo estrito para bloquear pipelines incompletos, distinguindo sandbox pronto de produção liberada. A rotina diária idempotente agora gera cobranças, tenta publicá-las no Asaas e recalcula aviso, tolerância e suspensão; o script scripts/register_licensing_billing_task.ps1 registra a tarefa no Windows Server, inclusive com conta de serviço sem login interativo. Documentação em docs/LICENCIAMENTO_CENTRAL_ASAAS.md. A central exclusiva do super admin agora página contratos, servidores credenciados e liberações emergenciais de forma independente em blocos de 50, preserva os demais filtros ao navegar, mantém métricas com os totais reais e deixou de carregar todas as faturas dos contratos sem necessidade. Faltam credenciais reais, registrar a tarefa no servidor definitivo e homologar sandbox/produção do Asaas e o webhook externo."),
            ("Proteção do código e distribuição endurecida", "partial", "A implantação comercial não deve entregar repositório Git, ambiente de desenvolvimento, testes, segredos ou código-fonte aberto ao cliente. O empacotamento atual exige commit limpo e rastreável, gera manifesto e SHA-256, pode exigir commit assinado, publica o artefato pela Central e mantém dados, mídia, logs e segredos fora do pacote. O contrato local_server_package_content_v1 agora abre e inspeciona o ZIP no empacotamento, novamente na publicação e na Central: limita entradas e tamanho expandido, exige a estrutura mínima do Django e bloqueia caminhos inseguros, repositório Git, ambientes virtuais, bancos, `.env`, certificados/chaves, mídia, logs, backups e artefatos mesmo quando o manifesto declarar ausência de dados do cliente. O git archive exclui testes Python, documentos iniciais, protótipos e referências internas por export-ignore; o validador também rejeita esses arquivos se forem reinseridos manualmente. Licenciamento Ed25519, conta de serviço com ACL mínima e atualização validada reduzem cópia e adulteração. A política está documentada no manual de instalação. O pipeline opcional local_server_protected_modules_v1 agora compila serviços sensíveis com Nuitka, vincula o overlay ao commit, ABI do CPython, plataforma e hashes, remove os fontes substituídos do ZIP e recusa binário adulterado ou incompatível; o pacote de produção pode exigir -RequireProtectedModules. Ainda faltam executar a compilação em uma estação Windows de build homologada, assinar executável, MSI e pacote do servidor com certificado definitivo, homologar a instalação em Windows limpo e concluir os termos jurídicos de licença e confidencialidade."),
            ("Identidade Deigo Varejo e DeTec PDV", "partial", "A marca provisória foi alterada para Deigo Varejo na plataforma e DeTec PDV no aplicativo, sempre com Deigo Tecnologia identificada como fabricante. Foram criados símbolo próprio, favicon, assinatura discreta no PDV, ícone multirresolução para Windows e integração do ícone no EXE, MSI e atalhos. Serviços, pacotes, caminhos e documentação deixaram a marca anterior, enquanto o app preserva migração da configuração legada. Falta realizar busca formal por classe no INPI, validar domínio e redes sociais, aprovar a identidade final e depositar o pedido de registro antes do lançamento comercial."),
            ("Liberação emergencial offline", "done", "Contingência comercial concluída com desafio local de uso único válido por 30 minutos, autorização Ed25519 emitida somente pelo super admin, vínculo obrigatório com CNPJ e instalação, validade limitada a 24 horas, 3 dias ou 7 dias, rejeição de código adulterado ou reutilizado, chave privada restrita à central, chave pública nos clientes, auditoria em ambos os lados, histórico operacional e reconciliação automática na primeira renovação após o retorno da internet. A senha do super admin nunca é informada no servidor do supermercado."),
            ("Auditoria de ações críticas", "done", "Logs sensíveis possuem tela de consulta com filtros por período, módulo, acao e usuário, exportação CSV, isolamento pela empresa do administrador e paginação real de 50 registros. Gerentes não acessam a auditoria administrativa e o super admin preserva a visão global."),
            ("Testes automatizados", "done", "Suíte formal cobre venda com baixa de estoque, pagamento dividido, backup e configurações de impressão."),
            ("Limpeza e estabilização do repositório", "done", "Auditoria conservadora concluída sobre a base bfe40f6: ambientes virtuais e saídas de build indevidamente versionados foram removidos, os artefatos publicados e identificadores legados ainda usados foram preservados, builds desktop ficaram reproduzíveis, referências documentais foram validadas e nomes, caminhos, UTF-8, acentuação, dependências, segurança Django, migrations e regressões automatizadas foram conferidos. Relatório em docs/LIMPEZA_ESTABILIZACAO.md."),
        ],
    },
    {
        "titulo": "PDV e caixa",
        "descricao": "Fluxo operacional do caixa de supermercado.",
        "itens": [
            ("Tela PDV em layout de operador", "done", "PDV sem sidebar, cabendo em 100% de zoom no desktop testado. Após a venda, uma camada de tela cheia informa CAIXA LIVRE e aceita Enter, Escape ou o início da leitura do próximo código de barras para liberar imediatamente a nova compra. A tela principal isola filial, caixas, vendas recentes, DAV de origem, última venda e terminal pela empresa autenticada; o operador finaliza somente no próprio caixa aberto e um identificador de terminal de outra empresa é recusado pelo escopo do backend."),
            ("Venda com carrinho e baixa de estoque", "done", "Venda finaliza com itens, pagamentos e baixa automática."),
            ("Pagamento dividido", "done", "Popup aceita múltiplas formas e calcula restante/troco. Atalhos F1/F2/F3/F4 preenchem a linha atual e só criam nova forma quando ainda existe saldo restante; se o pagamento já cobre o total, o PDV avisa o operador em vez de duplicar parcelas automaticamente. Para dois cartões, PIX + cartão ou outra divisão real, o operador informa o valor parcial e adiciona a próxima forma, ficando cada parcela registrada na venda. Vale alimentacao e vale refeicao são modalidades voucher separadas do debito, exigem confirmacao TEF e usam os codigos fiscais 10 e 11."),
            ("Formas de pagamento por filial", "done", "O super admin mantem apenas o catalogo tecnico global. Cada administrador configura, para as proprias filiais, quais formas ficam disponiveis no PDV e a conta financeira de destino. A migration preenche filiais existentes e o servico inicializa novos itens globais automaticamente. O backend rejeita forma inativa ou de outra filial mesmo em POST forjado, o lançamento financeiro usa a conta especifica da filial e toda alteracao fica na auditoria."),
            ("Desconto supervisionado no PDV", "done", "Todo desconto informado no pagamento exige usuário e senha de supervisor ou administrador. A venda é bloqueada sem credencial válida e a autorização registra desconto, venda, operador, supervisor e IP no log de auditoria."),
            ("Credencial rápida de supervisor", "partial", "A central de credenciais já permite ao administrador vincular cartão NFC/MIFARE, magnético ou crachá com código de barras a um supervisor/admin da própria empresa. O identificador bruto nunca é persistido: fica somente o HMAC, com validade, revogação, PIN opcional e trilha de cada uso. O helper central das operações protegidas aceita credencial ou login e senha, e leitores em modo teclado já funcionam no navegador e no PDV desktop. O app desktop agora possui adaptador PC/SC nativo para leitores NFC dedicados via winscard.dll, obtém o UID por APDU sem gravá-lo em diagnóstico, entrega a credencial diretamente ao formulário protegido e preserva leitor em modo teclado ou login e senha como fallback. A política por empresa agora identifica cada operação protegida, permite ao administrador escolher quais ações exigem cartão cadastrado com PIN e traz como padrão estorno/devolução de venda, cancelamento de entrada de compra e cancelamentos de produção ou desmembramento. Login e senha permanecem como contingência, e o histórico grava a ação autorizada. Falta somente homologar leitores e cartões com equipamentos físicos."),
            ("PIX no pagamento do PDV", "done", "Forma PIX disponível dentro da escolha eletrônica do F3. O app desktop gera e exibe QR Code com valor destacado, mantém a parcela pendente e consulta o terminal até receber confirmação; somente o retorno aprovado libera a finalização. O QR do simulador é identificado como teste e o adaptador real poderá usar a tela do PDV, o pinpad compatível ou ambos."),
            ("Campos monetarios no PDV", "done", "Pagamento, fechamento, sangria e suprimento exibem prefixo R$ e valor de pagamento ganhou campo maior."),
            ("Cliente avulso", "done", "Venda presencial pode finalizar sem cliente identificado."),
            ("DAV / pré-venda", "done", "Criacao, listagem, recibo, carregamento no PDV e cancelamento com supervisor."),
            ("Reimpressao de cupom", "done", "Detalhe da venda e modal de estorno/vendas recentes no PDV possuem acao separada para reimprimir o cupom ja registrado, usando a impressora do app desktop quando disponível ou fallback do navegador, sem recriar venda, sem movimentar estoque e sem reabrir gaveta de dinheiro. No modal de estorno, vendas e comandos ficam em duas áreas independentes e responsivas: a lista possui busca, cards compactos, paginação e rolagem própria, enquanto Abrir, Reimprimir e Estornar permanecem visíveis no painel da venda selecionada sem sobrepor a autorização em 100% de zoom. Setas selecionam a venda, PageUp/PageDown trocam página, Enter abre o detalhe, F10 reimprime, F6 abre o estorno da venda selecionada e Ctrl+Enter confirma o estorno quando o formulário estiver preenchido. Cada reimpressao fica registrada na auditoria com usuário, venda, origem e IP."),
            ("Abertura e fechamento de caixa", "done", "Operador abre/fecha; supervisor/admin confere depois. Modal de caixas no PDV possui atalhos de teclado: F2 abre caixa ou foca suprimento, F5 foca fechamento, setas selecionam caixas da lista, Enter abre o caixa selecionado e Ctrl+Enter confirma o formulário ativo."),
            ("Sangria e suprimento", "done", "Exigem senha de supervisor/admin e geram lançamentos automáticos de saída/entrada no livro financeiro da conta Caixa PDV. No modal de caixas, F2 foca suprimento, F3 foca sangria e Ctrl+Enter registra o movimento com os campos preenchidos."),
            ("Estorno no PDV", "done", "PDV possui atalho F6 para cancelamento total de venda recente com motivo e autorização por credencial ou senha de supervisor/admin; o modal responsivo separa lista e comandos, preserva navegação completa por teclado e orienta que a devolução parcial seja registrada pela tela da venda."),
            ("Operação principal por teclado", "done", "Enter inclui produto; F2-F9 acessam funções; no carrinho, setas selecionam o produto mesmo quando o foco está em outro campo, Del reduz uma unidade do item selecionado e remove a linha apenas quando zerar, e Ctrl+Del limpa a venda com confirmacao; no pagamento, Shift+ adiciona forma, Del remove forma e Enter confirma; supervisores/admin usam Shift+M para o menu, enquanto operador usa Shift+S para sair com confirmação."),
            ("Bip e retorno automático de foco", "done", "Leitor envia Enter, inclui o produto, soma repetições e devolve o foco ao campo após o recarregamento."),
            ("Alertas rapidos no PDV", "done", "Mensagens simples viram toasts temporarios; operações críticas continuam exigindo confirmacao ou supervisor."),
            ("Autorização do PDV em nuvem", "done", "Operador comum fica bloqueado em ambiente de nuvem, tentativa gera solicitacao, admin/gerente recebe alerta visual no topo/menu e decide pelo painel de aprovação."),
            ("Arquitetura PDV desktop local", "partial", "PDV dos caixas deve ser um aplicativo instalado na máquina do operador, fiel ao layout, atalhos e fluxo de venda do PDV web já validado, para que o operador use a mesma experiência nos dois ambientes. O desktop acrescenta integrações locais com impressora, balanca, gaveta e TEF, operação resiliente e acesso somente ao necessário para venda, pagamento, caixa, consulta e estorno autorizado, sem telas administrativas completas. O app se comunica com o servidor local da loja pela rede interna; esse servidor local conversa com os dispositivos e o banco operacional da filial. Cadastro por filial, chave individual protegida por hash e bootstrap com registro de conexão implementados. O bootstrap diário devolve a configuração vigente de licença, TEF, fiscal e balanca para o app instalado se atualizar sem novo pacote. A nuvem/sede sincroniza por API segura, filas e eventos, sem acessar diretamente o banco local do supermercado. Download/ativacao do app desktop exige autorização do admin master, pois cada máquina instalada pode representar uma licenca comercial cobrada por terminal; pacote de ativação so e entregue para terminal com licença liberada. A Central do App oferece pré-homologação consolidada pelo contrato pdv_device_homologation_v1: inspeciona impressoras, balança, gaveta e TEF, não imprime nem cria cobrança no modo padrão, exige seleção e confirmação para leitura/pulso físico e grava a evidência em devices.log.jsonl para sincronização central. A fila local agora segue o contrato pdv_device_event_queue_v1: cada evento recebe ID estável, lotes são enviados do mais antigo ao mais novo a partir de cursor confirmado, reenvios são deduplicados por terminal no servidor e a compactação atômica remove somente registros já confirmados, preservando todos os pendentes. Durante o turno, uma thread exclusiva sincroniza periodicamente em intervalo local configurável de 15 a 3.600 segundos e é encerrada de forma limpa junto com a WebView, sem depender de reiniciar o caixa. O bootstrap agora publica o pacote vigente e o canal de atualização autenticado aceita somente terminal ativo com licença liberada pelo admin master; o rollout pdv_update_rollout_v1 permite promover uma versão primeiro em caixas piloto e depois no canal estável, congelar atualizações opcionais por máquina e sobrepor o congelamento quando a versão instalada ficar abaixo do mínimo de segurança. O app baixa para arquivo temporário, valida SHA-256, descarta pacote divergente, registra diagnóstico e mantém a instalação manual, sem atualização silenciosa. A contingência de conexão agora usa bootstrap local autorizado com validade padrão de 24 horas: em queda do servidor mostra uma tela local identificando o caixa, bloqueia venda, pagamento e estoque e permite reconectar por F5/Enter e sair com botão dedicado ou Ctrl+F5 (Ctrl+Q tambem aceito); somente uma nova validação de terminal e licença abre o PDV, enquanto cache vencido ou terminal recusado permanece bloqueado. A chave de ativação e os parâmetros sensíveis do adaptador TEF deixaram de permanecer em texto no config.json: o agente usa o contrato pdv_local_secret_v1 e DPAPI vinculado ao usuário do Windows, restaura os valores somente em memória, migra automaticamente instalações legadas, bloqueia conteúdo corrompido ou copiado para outro usuário e expõe ao diagnóstico somente o estado da proteção. O contrato pdv_single_instance_v1 usa mutex nomeado por hash da identidade do terminal para impedir duas janelas do mesmo caixa na sessão do Windows, sem expor o identificador e liberando o bloqueio ao encerrar. O shell desktop oferece encerramento global por Ctrl+F5 (Ctrl+Q tambem aceito) em qualquer tela, com confirmação para evitar fechamento acidental; ativação e contingência também aceitam o mesmo comando, sem interferir no navegador comum. A reconfiguração também reserva primeiro a identidade atual, impedindo troca de ativação enquanto aquele caixa estiver em execução. O administrador pode rotacionar a credencial pela lista de terminais, copiá-la uma única vez e reconfigurar o app pela tela principal ou pela contingência; a chave antiga fica invalidada, o segredo não é persistido em log e a ação gera auditoria. Ainda faltam drivers/adaptadores reais e homologação presencial dos equipamentos."),
            ("Balança integrada no PDV", "partial", "Produtos já possuem marcacao de produto pesável. Terminal PDV agora permite configurar balança por caixa com protocolo, porta/endereço e modelo; manifesto, pacote JSON e bootstrap do app desktop entregam essa configuração por máquina usando o contrato pdv_scale_v1, com leitura automática, unidade KG, precisão de 3 casas, timeout e fallback manual quando a balanca estiver ausente ou falhar. O app desktop já possui ponte local para expor a configuração da balanca e retornar leitura estruturada com peso simulado para homologação. A tela do PDV já chama a ponte local pelo botão Peso e atalho F12, preenchendo a quantidade quando recebe o peso ou orientando digitação manual no navegador comum. Falhas e retornos manuais da balanca ficam registrados no log local devices.log.jsonl da máquina do caixa e podem ser consultados pela ponte deviceLogs; a Central do App PDV desktop já possui leitura visual desse diagnóstico quando aberta dentro do aplicativo instalado. O servidor já possui endpoint autenticado por terminal para receber lotes de diagnósticos locais e armazenar EventoDispositivoTerminal por caixa, e o app desktop tenta enviar automaticamente os eventos ainda não sincronizados na inicialização sem bloquear a abertura do PDV. A Central do App PDV desktop exibe histórico consolidado dos eventos recebidos pelo servidor, e uma tela operacional própria oferece resumo, filtros por máquina/tipo/status/período, paginação e exportação CSV. A pré-homologação consolidada permite solicitar explicitamente uma leitura com peso conhecido e inclui protocolo, porta, modelo, peso e resultado na evidência sincronizável. O agente agora possui driver genérico real para Serial RS-232/USB via pyserial, TCP/IP e arquivo texto local, com timeout limitado, leitura máxima controlada, parser decimal, fator de conversão e rejeição de peso instável, zero, valor negativo e sobrecarga. O cadastro valida TCP/IP no formato endereço:porta e exige identificação do modelo para adaptadores proprietários. Falta validar parâmetros e comandos do fabricante escolhido, conectar a balança física e homologar precisão, estabilidade e timeout para ler peso automaticamente no PDV real."),
            ("TEF/API de maquininha", "partial", "Pagamentos possuem estados controlados, ID externo, NSU e autorização; venda rejeita transação pendente, recusada ou estornada. Terminais PDV agora configuram provedor TEF e modo de integração por adaptador, permitindo PagBank, Cielo, Stone, Getnet, Rede, SiTef ou outro fornecedor sem prender o sistema a uma operadora. O bootstrap do app desktop expõe o contrato pdv_tef_v1 com tipos crédito, débito e PIX dinâmico e retorno esperado. No PDV, pagamento eletrônico chama a ponte processPayment do app desktop, aguarda resposta da maquininha/simulador, grava transação, NSU e autorização na linha de pagamento e bloqueia a finalizacao se não houver retorno confirmado; terminal sem TEF configurado retorna aviso ao operador. O app desktop possui simulador TEF rastreável para desenvolvimento enquanto o adaptador real da adquirente não estiver conectado, incluindo pagamento e refundPayment para estorno autorizado pela maquininha, e grava eventos locais tef em devices.log.jsonl, além de tef_estorno, para diagnóstico central de aprovações, falhas e terminais sem maquininha configurada. Antes de chamar o adaptador, a ponte valida modalidade liberada pelo bootstrap, valor monetário positivo e precisão máxima de centavos tanto no pagamento quanto no estorno. O front envia chave idempotente por tentativa e o bridge reutiliza a autorização ou estorno já aprovado quando a mesma solicitação for repetida na sessão, rejeitando a chave caso os dados mudem. Para PIX, o contrato também expõe checkPayment: primeiro retorna QR Code e estado pendente, depois consulta a transação até a adquirente confirmar, sem tratar a mera geração do QR como pagamento. A camada local agora possui contrato único de adaptadores para processar, consultar e estornar; o driver é escolhido na configuração protegida da máquina e respostas incompletas são rejeitadas sem aprovar a venda. O simulador deixou de ser implícito: depende de autorização explícita do servidor por PDV_TEF_SIMULATOR_ENABLED e fica bloqueado em produção, enquanto provedor configurado sem driver instalado falha de forma segura. Para operações em Goiás, a orientação da Secretaria da Economia vinculada à IN 1.608/2025 exige integração direta, imediata e sem intervenção manual entre pagamento eletrônico e documento fiscal nos casos aplicáveis, incluindo PIX e débito no balcão; o simulador permanece somente para desenvolvimento e não comprova conformidade. Falta conectar e homologar o pacote real do provedor escolhido em equipamento físico, que também deverá honrar a chave idempotente."),
            ("Reversão de pagamento misto", "done", "Cancelamento total estorna parcelas locais e mantém PIX/TEF com transação externa em fila supervisionada até a confirmação da adquirente. Devoluções parciais rateiam o valor entre todos os pagamentos confirmados: a parcela local gera saída financeira imediata, enquanto cada fração eletrônica recebe solicitação própria, valor, motivo, vínculo com a devolução, estado e chave idempotente. O diagnóstico protegido payment_refund_readiness_v1 reúne estornos totais e parciais por antiguidade; a tela permite seleção por teclado e processamento com F10 ou Ctrl+Enter. A supervisão pode confirmar o estorno eletrônico aprovado pela operadora. A fila processa diretamente a parcela selecionada, aguarda a resposta da maquininha e, no navegador, exige evidência informada da adquirente. No app desktop, refundPayment chama o adaptador da maquininha com o valor proporcional e a transação original; somente a resposta aprovada cria o lançamento financeiro inverso, registra autorização, ID externo, usuário e auditoria. Reenvios confirmados são bloqueados, solicitações iguais do mesmo pagamento permanecem independentes e uma venda que já teve devolução parcial não aceita cancelamento total posterior, evitando duplicidade de estoque e reembolso. A conexão e homologação física de cada adquirente continuam controladas no item TEF/API de maquininha."),
            ("Padrão R$ em todos os formulários", "done", "Campos numéricos de preço, valor, custo, desconto, taxa, frete e total recebem automaticamente o prefixo R$ no PDV e nas telas administrativas."),
        ],
    },
    {
        "titulo": "Produtos, estoque e compras",
        "descricao": "Cadastros e controle físico/financeiro do estoque.",
        "itens": [
            ("Produtos, categorias e marcas", "done", "Cadastro central em uma unica tela organizada, com edicao, busca, importacao CSV, etiquetas e kardex. O codigo interno e gerado automaticamente no padrao PRD-000001. Ao salvar, PDVs conectados ao mesmo servidor usam o dado imediatamente e instalacoes hibridas recebem evento automatico; carga manual fica restrita a implantacao inicial ou recuperacao."),
            ("Cadastro comercial avancado de produtos", "partial", "A mesma página de produto já reúne tipo comercial, classificação hierárquica em departamento, seção, grupo e subgrupo, unidade-base, unidade de compra, fator de conversão, pesos e múltiplos códigos EAN para unidade, pacote, fardo ou caixa. A busca mostra o caminho completo da classificação; a leitura no PDV converte automaticamente a embalagem em unidades-base, a consulta calcula o preço da apresentação, pesquisas e etiquetas encontram qualquer EAN e a sincronização híbrida publica tipo, árvore comercial e embalagens sem carga manual. Fornecedores vinculados por empresa, margem desejada e preço sugerido também ficam na mesma tela. A configuração de balança agora usa setor e PLU únicos por empresa, com tara, validade, busca no PDV e sincronização híbrida, sem misturar cadastros de clientes diferentes. As informações nutricionais e os produtos similares agora ficam em uma seção opcional e recolhida, com busca Select2, ficha por porção/100 g/100 ml, ingredientes, alergênicos, glúten e lactose; o snapshot híbrido transporta esses dados sem obrigar cadastros que não os utilizam. O perfil fiscal avançado opcional agora armazena redução de base do ICMS, FCP, cBenef, CST e alíquotas de PIS, COFINS e IPI, além de CST e cClassTrib de IBS/CBS; valida formatos e percentuais e sincroniza os dados entre loja e nuvem. O CFOP permanece vinculado à natureza da operação. A importação CSV agora permite criar ou atualizar em lote os campos fiscais de ICMS, PIS, COFINS, IPI e IBS/CBS, preserva dados cujas colunas não foram enviadas, aceita decimais brasileiros ou com ponto, valida códigos e percentuais por linha e registra auditoria resumida; a Central Fiscal oferece acesso direto a esse fluxo e exporta em streaming o filtro atual já preenchido, com busca, valores brasileiros e colunas reimportáveis, registrando a operação na auditoria. A planilha exportada carrega modo fiscal protegido: ao reimportar, altera somente os campos tributários de produtos existentes, preserva nome, categoria, preço e demais dados comerciais e recusa criar duplicata quando o código não for localizado. Falta homologar as regras de geração do XML com contador, provedor fiscal e tabelas vigentes antes de transmitir esses campos automaticamente."),
            ("Custo medio por produto e filial", "done", "Cada estoque de filial mantem custo medio ponderado movel. Novas entradas recalculam o custo sem reescrever compras ou lotes anteriores; a venda congela o custo medio da filial no item vendido para margem e auditoria. O ultimo custo de compra continua separado como referencia comercial do cadastro."),
            ("Pendências fiscais de produtos", "done", "Tela fiscal lista produtos com NCM, CEST, origem, CST/CSOSN ou alíquota pendentes e direciona para correção do cadastro."),
            ("Promoções", "done", "Preço vigente considera promocao ativa; formulário destaca produto, preço promocional, vigência e status para uso automático no PDV."),
            ("Estoque por filial", "done", "Saldo físico, reservado e disponível por produto/filial."),
            ("Inventário", "done", "Contagem e aplicacao com autorização de supervisor/admin."),
            ("Perdas", "done", "Baixa de perdas com supervisor/admin e log."),
            ("Movimentação manual", "done", "Entrada/saída/ajuste/reserva com supervisor/admin, auditoria e formulário separado entre operação e autorização."),
            ("Compras", "done", "Entrada de compra com dados da nota, itens recebidos, rascunho sem movimentar estoque, finalizacao direta com supervisor/admin, atualizacao automática de estoque, custo do produto, movimentacao de entrada e conta a pagar, baixa direta da conta vinculada com retorno para a entrada, rastreio financeiro da baixa no detalhe da compra, impressão/PDF individual auditável da entrada com itens, financeiro, rastreio financeiro do livro e rastreio de estoque, lista operacional separada do relatório com situação financeira da entrada, retorno seguro do detalhe e da edição de rascunho para a lista filtrada, filtros por status da entrada e situação financeira aberta, paga, cancelada, vencida ou sem conta, exportacao Excel/CSV e impressão/PDF da visão operacional filtrada, limpeza rapida de filtros ativos, chips visuais dos filtros aplicados, cards de resumo financeiro de contas abertas, vencidas e pagas com atalho para filtro preservando busca e status atuais, alerta de rascunhos pendentes, rastreio no estoque da entrada com movimentações de entrada e cancelamento vinculadas, e cancelamento protegido de compra finalizada com reversao de estoque, cancelamento da conta aberta, bloqueio quando a conta já foi paga, bloqueio quando o produto já foi consumido a ponto de não existir saldo para reverter e aviso antecipado desses bloqueios na tela da entrada."),
            ("Etiquetas de gôndola profissionais", "partial", "O documento complementar de etiquetas foi incorporado ao checklist. A tela busca por nome, código de barras e SKU, aceita leitor que envia Enter, cópias por produto e modelos compacto 110x30 mm, completo 100x50 mm, A4 e modelos profissionais salvos por empresa, filial e terminal, sempre sem fundo colorido forçado. Configuração inclui medidas, gaps, colunas, orientação, DPI, mídia, impressora e linguagem; a tela envia o lote ao agente desktop, que gera ZPL, EPL, PPLA ou PPLB e imprime em RAW sem pré-visualização. O agente agora valida obrigatoriamente o contrato label_print_v1, impressora e código de barras/SKU, limita 500 produtos, 100 cópias por produto e 2.000 etiquetas por lote e grava diagnóstico local de sucesso ou falha para sincronização central. Ainda faltam testes com equipamentos físicos."),
            ("Desmembramento e fracionamento de produtos", "partial", 'Novo documento complementar incorporado ao checklist para estoque avançado. A frente ja possui models DesmembramentoProduto, ItemDesmembramentoProduto e ReceitaDesmembramento, receitas/conversões por empresa/filial, busca remota por código de barras, SKU e nome, simulação antes de confirmar, múltiplos destinos, lote/validade, rendimento esperado e alerta de rendimento abaixo do previsto. O serviço transacional faz baixa da origem, entrada dos destinos vendáveis ou subprodutos, descarte/perda vinculada sem aumentar saldo vendável, custo proporcional, auditoria e cancelamento seguro com movimentos inversos. Para açougue e hortifruti em KG, a prévia mostra rendimento total e excesso, e a confirmação exige fechamento exato da massa antes de qualquer movimento: produtos, subprodutos e perdas devem somar a origem, sem criação de peso nem desaparecimento de quebra não classificada; conversões de caixa/fardo para unidades continuam permitidas. As telas de lista, detalhe e receitas exibem quantidades no padrão brasileiro com quantidade_br, evitando 1,000 ou 20,000 quando o valor representa unidade inteira. Também foram iniciados kits/composições, produção interna, planejamento por demanda mínima, ordens de produção por setor, etapas, responsáveis, SLA, fila operacional, alertas auditáveis e relatórios/CSV gerenciais. Ainda faltam homologar fluxos reais de açougue, padaria e hortifruti com operação de loja.'),
        ],
    },
    {
        "titulo": "Relatórios e gestão",
        "descricao": "Visão administrativa para acompanhamento da operação.",
        "itens": [
            ("Dashboard", "done", "Indicadores principais e atalhos por perfil."),
            ("Relatórios de vendas", "done", "Período, faturamento, descontos, devoluções e produtos vendidos. Painel, CSV e PDF respeitam o escopo empresarial: gerente consulta sua filial, administrador consolida ou filtra matriz/filial da própria empresa e filial externa é recusada pelo backend."),
            ("Curva ABC e reposição", "done", "Análises para decisão de compra e estoque com isolamento empresarial em painel, CSV e PDF. A reposição calcula vendas e devoluções por produto e filial, sem misturar a demanda entre lojas."),
            ("Relatórios de caixas", "done", 'Abertos, aguardando conferência, conferidos, declarado e conferido. O relatório de vendas filtra por funcionário para conciliar o movimento daquele operador na tela, no CSV e no PDF. Relatório de caixas/PDV por funcionário possui filtro por operador, resumo por operador com caixas, vendas, total vendido, sangrias, suprimentos, saldo operacional, valores inicial/declarado/conferido, diferença de conferência por caixa e por operador, formas de pagamento no relatório impresso/PDF, exportação Excel/CSV com valores monetários em duas casas e impressão/PDF preservando o filtro. O resumo agora permite abrir o detalhe de cada funcionário, mostra entradas líquidas por forma de pagamento, exclui pagamentos integralmente estornados e abate estornos parciais confirmados. O escopo foi endurecido: gerente e financeiro consultam somente a filial vinculada, administrador consolida matriz e filiais da própria empresa e apenas o super admin possui visão global. O filtro de filial alterna entre consolidado, matriz e loja específica, restringe a lista de operadores e é preservado no CSV e PDF; operador ou filial externa são recusados em todos os formatos. A gestão de caixas permite ao supervisor ou administrador escolher por filial, operador e status, abrir o caixa fechado, conferir valores e imprimir a conferência individual; vendas e movimentos do detalhe são paginados em blocos de 25. O operador vê e movimenta apenas o próprio caixa.'),
            ("Relatórios de perdas/devoluções/compras", "done", "Telas específicas por período com filtro de filial e isolamento empresarial no painel, CSV e PDF. Gerente e financeiro ficam na filial vinculada, administrador consolida ou seleciona uma filial da própria empresa e filial externa é recusada pelo backend."),
            ("Exportacoes", "done", "Relatórios operacionais e gerenciais exportam CSV compatível com Excel, com separador brasileiro, valores localizados e marcador UTF-8 para preservar acentos, e possuem versão para PDF. Vendas, Curva ABC, estoque baixo, reposição, movimentações, perdas, devoluções, compras e caixas preservam o filtro de filial e aplicam o mesmo escopo empresarial em todas as saidas. A revisão de linguagem corrigiu os rótulos visíveis dos templates e mensagens do PDV, e uma migração de dados trata o cadastro legado MAÇĂ sem alterar outros nomes."),
            ("Gráficos de pizza no dashboard", "done", "Dashboard usa Chart.js para composição por forma de pagamento, categorias e status dos caixas. Indicadores, gráficos e caixas recentes agora respeitam o escopo empresarial e o filtro de filial: gerente e financeiro ficam na filial vinculada, administrador consolida ou seleciona matriz/filial da própria empresa e super admin mantém visão global. Produtos são contabilizados pelos estoques das filiais selecionadas, pagamentos representam entradas líquidas e filial externa é recusada pelo backend."),
        ],
    },
    {
        "titulo": "Revisão complementar v2",
        "descricao": "Requisitos acrescentados pelo documento de usabilidade, cadastros e entrega.",
        "itens": [
            ("Login sem caixa alta", "done", "Usuário, e-mail e senha preservam a digitação original na tela de acesso."),
            ("Paginação e proteção de grandes listagens", "done", "Auditoria, usuários, clientes, fornecedores, produtos, compras, financeiro, fiscal, relatórios, marketplace, Kardex, estoque avançado, filas visuais de PDV e sincronização usam paginação de até 50 registros por página. Totais gerenciais continuam calculados sobre o filtro completo; autocompletes, dashboards, exportações e lotes técnicos mantêm limites próprios adequados ao contrato. O detalhe de caixa pagina separadamente vendas e movimentos manuais em blocos de 25 registros."),
            ("Busca inteligente/autocomplete", "done", "PDV possui buscas locais por teclado; Select2 aplicado em filial, produto, fornecedor, cliente, categoria e marca nos formulários mais extensos. A busca remota por API foi ativada no Select2, com endpoints JSON para produtos, clientes, fornecedores, filiais, categorias e marcas, uso em compras, financeiro, marketplace, produtos, etiquetas e configuracoes, filtro para produtos vendidos no marketplace e permissões coerentes com os módulos operacionais. Os campos remotos abrem mostrando os primeiros 20 registros do banco e carregam as páginas seguintes ao rolar, mantendo a digitação apenas como atalho de filtro."),
            ("Consulta de CNPJ e CEP", "partial", "Formularios de empresa e filial possuem mascaras, avisos, campo auxiliar de CEP, botao de consulta CNPJ/CEP, contrato JSON cadastro_lookup_v1, validacao formal de CNPJ, validacao de CEP, reaproveitamento de dados locais de empresas/filiais por CNPJ ou CEP e preenchimento automático dos campos vazios quando houver cadastro local correspondente. O endpoint aceita provedores externos configurados por CADASTRO_CNPJ_PROVIDER_URL, CADASTRO_CEP_PROVIDER_URL e CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS, normaliza respostas de CNPJ/CEP, expõe diagnóstico JSON com status dos provedores, timeout, modo local/offline, volume reaproveitável da base local e prontidão cadastro_lookup_readiness_v1 para distinguir fallback local, configuração parcial, URL insegura e provedores HTTPS prontos para homologação. O comando verificar_prontidao_consulta_cadastro oferece JSON e modo estrito sem revelar URLs; o roteiro está em docs/CONSULTA_CNPJ_CEP.md. O fallback local/offline permanece ativo e o front aplica retorno local ou externo. Falta escolher e homologar a API oficial de produção para CNPJ e CEP."),
            ("Cadastros complementares padronizados", "done", "Clientes, fornecedores, produtos e usuários possuem formulários organizados por seções operacionais, com textos de apoio para PDV, compras e etapas futuras."),
            ("Clientes isolados por empresa", "done", "Cliente agora possui vínculo explícito com a empresa. Lista, edição, busca Select2, PDV, DAV, marketplace e financeiro filtram pelo perfil autenticado; IDs forjados são rejeitados no formulário e os serviços bloqueiam venda, pedido ou conta com cliente de outra empresa. A migration atribui legados somente quando existe evidência unívoca por venda, DAV, conta ou pedido, preservando casos ambíguos para revisão."),
            ("Fornecedores isolados por empresa", "done", "Fornecedor possui vínculo explícito com a empresa. Cadastro, edição, listagem, busca Select2, cotação, pedido, entrada, financeiro e importação de NF-e respeitam a empresa; combinações entre fornecedor e filial de empresas diferentes são rejeitadas. A migração atribui legados apenas com evidência unívoca e os testes cobrem acesso cruzado."),
            ("Fluxos de compras isolados por empresa", "done", "Listagens, indicadores, detalhes, formulários, propostas, exportações CSV, impressões e ações diretas de cotações, pedidos e entradas usam o escopo da empresa autenticada. Alterar IDs na URL retorna 404 antes de abrir, enviar, converter, finalizar, cancelar ou excluir documentos de outra empresa; o super admin preserva a visão global."),
            ("Pedidos do marketplace isolados por empresa", "done", "Pedidos, separação, pagamentos, preparação fiscal, integrações, diagnósticos, renovação de chaves, políticas e simulações de entrega respeitam a empresa autenticada. URLs cruzadas retornam 404, formulários rejeitam filiais externas e a API continua isolada pela chave do parceiro, inclusive quando existe uma sessão web de outra empresa."),
            ("Documentos fiscais isolados por empresa", "done", "Configurações, séries, documentos, vendas pendentes, contingência, diagnósticos, XML, impressão, transmissão e cancelamento agora respeitam a empresa do perfil autenticado. IDs de outra empresa retornam 404, formulários rejeitam filiais externas e o super admin preserva a visão global; testes cobrem consultas, exportações e ações forjadas."),
            ("Estoque e produção isolados por empresa", "done", "Estoque, lotes, reconciliação, inventários, perdas, desmembramentos, receitas, composições, produções, ordens e SLA respeitam a empresa autenticada nas listagens, indicadores, relatórios, CSV, JSON, formulários e ações por ID. Filiais, empresas, receitas, composições, responsáveis e credenciais de supervisor externos são rejeitados, enquanto o super admin preserva a visão global."),
            ("PDV isolado por empresa e filial", "done", "DAVs, vendas, recibos, cargas, cancelamentos, devolucoes, estornos eletronicos, caixas, sangrias, suprimentos, fechamento e consulta de estoque bloqueiam IDs externos. O administrador acessa as filiais da própria empresa, os perfis operacionais permanecem na filial vinculada e o super admin preserva a visao global. Testes cobrem listagens e URLs forjadas."),
            ("Operacoes financeiras isoladas", "done", "Contas financeiras e de movimento, transferências recentes, livro, estornos, edicao, baixa e cancelamento respeitam o escopo do perfil. Formularios limitam filiais e contas disponiveis: administrador consolida a própria empresa, demais perfis ficam na filial e super admin mantem visao global."),
            ("Categorias financeiras por empresa", "done", "Categoria financeira agora pertence a uma empresa, possui unicidade por empresa e nome, e a migration preserva categorias existentes, criando copias quando houver uso por mais de uma empresa. Formularios, telas e compras usam somente categorias do escopo permitido."),
            ("Curva ABC com horarios de pico", "done", "A Curva ABC agora combina relevancia dos produtos com os cinco horarios de maior movimento, calculados por faturamento e quantidade de vendas no período e escopo de filial. A tela destaca o principal horario de pico."),
            ("Pedido de entrega pelo PDV", "done", "O operador pode converter o carrinho em pedido para entrega por botão ou Ctrl+E. O pedido é criado no canal telefone, com endereço e contato, sem finalizar venda ou receber pagamento. Como os produtos foram lidos no PDV, o sistema reserva o estoque, marca os itens separados e deixa o pedido pronto para envio, sem exigir a conferência manual exclusiva dos pedidos online. No modal de pagamento, o operador escolhe entre receber agora e finalizar a venda presencial ou abrir Entrega: pagar depois, que cria o pedido e abre sua conferência; nela o pagamento informado no caixa fica vinculado e marcado como pago depois da validação do endereço/frete, ou o operador pode manter cobrança na entrega. Shift+E abre no PDV a fila de entregas pendentes da filial; setas selecionam e Enter abre uma conferência interna em popup, sem levar o operador ao menu administrativo. A conferência possui atalhos F2 para reservar, F3 para pronto, F4 para sair para entrega, F5 para concluir e F6 para pagamento; cada ação retorna ao mesmo pedido no PDV. A criação da entrega também emite automaticamente uma comanda operacional com cliente, endereço, itens, observações e situação de pagamento; F10 a reimprime pela fila de entregas. No aplicativo desktop, a comanda usa o spooler nativo e a impressora configurada especificamente como Pedido de separação, independente das configurações de cupom fiscal e não fiscal. A criação da entrega busca clientes salvos da mesma empresa por nome, telefone ou documento, permite seleção integral por teclado, preenche telefone e endereço e mantém duas alternativas seguras para nomes novos: atendimento avulso sem cadastro ou salvamento opcional vinculado ao pedido."),
            ("Cartão pago na entrega", "partial", "Pedidos com entrega oferecem cartão de crédito ou débito cobrado pelo entregador. O pedido permanece pendente até a confirmação e exige NSU ou referência da maquininha ao registrar o pagamento, preservando rastreabilidade para conciliação. Cartão na entrega é aceito somente em pedido de entrega já despachado, nunca em retirada nem antes da saída do pedido; no popup do PDV, a seleção de cartão exige visualmente o NSU da maquininha. Pedidos criados pelo PDV agora tambem aplicam a política ativa da filial, validando bairro, distância, área atendida e frete antes da separação. Falta integrar o retorno automático do aplicativo de entrega ou maquininha homologada."),
            ("Configuração portatil do PDV desktop", "done", "O executavel instalado ignora arquivos de desenvolvimento ao lado do app e usa o perfil local do Windows em %LOCALAPPDATA%\\DeTecPDV. Cada computador ativa seu proprio terminal sem herdar caminho ou configuração de outra maquina."),
            ("Imagens de produto", "done", "Foto principal e galeria adicional com legenda, ordenacao e remoção integradas ao cadastro e preparadas para exibicao no marketplace."),
            ("Políticas de entrega por filial", "partial", "Raio, faixas por distancia, pedido mínimo, frete grátis, bairros e horários configuraveis implementados. O cálculo de entrega agora valida bairros atendidos e bloqueados, exigindo bairro quando a filial possui area atendida restrita; o bairro fica gravado no pedido, na separação impressa e no payload de integração; a conferência reabre bairro e distância preenchidos para recalcular sem redigitação. A tela de politicas permite simular subtotal, distancia manual, endereço para geocodificacao e bairro por filial usando a mesma regra do pedido real. O diagnóstico JSON informa os contratos delivery_geocode_v1 e delivery_policy_readiness_v1, valida ausência, lacunas, sobreposição e cobertura das faixas, classifica prontidão por filial, informa se MARKETPLACE_GEOCODING_PROVIDER_URL está configurado, timeout e fallback manual de distancia. O endpoint de status do parceiro marketplace_partner_v1 agora expõe a política delivery_policy_v1 da filial, com retirada, entrega, raio, pedido mínimo, frete gratis, bairros, faixas, geocoding e alertas antes do pedido real. Falta escolher e homologar provedor de mapa/rota de produção."),
            ("Certificado digital protegido", "done", "Configuração fiscal aceita upload A1 .pfx/.p12, criptografa arquivo e senha, lê validade e mostra alertas de vencimento."),
            ("Identidade visual do supermercado", "done", "Logo no topo, marca d'água sutil no carrinho e paleta operacional restrita implementadas. A identidade do supermercado permanece em destaque; a assinatura do fornecedor Deigo Tecnologia será aplicada de forma discreta no aplicativo desktop, sem competir com a marca da loja."),
        ],
    },
    {
        "titulo": "Etiquetas e impressoras profissionais",
        "descricao": "Requisitos do documento complementar de etiquetas de gôndola e impressoras profissionais.",
        "itens": [
            ("Modelo compacto 110x30", "done", "Modelo recomendado para gôndola horizontal criado no MVP, priorizando nome do produto, código de barras ou código interno, unidade e preço grande, sem foto, icones decorativos ou excesso de informação."),
            ("Modelo completo 100x50", "done", "Modelo maior disponível para etiquetas com mais espaco, mantendo preço como informação principal e deixando logo, tributos e preço de referência como evolucao configuravel."),
            ("Busca por código de barras nas etiquetas", "done", "Campo de busca aceita digitação manual e leitor como teclado, mantendo foco automático; a consulta prioriza código de barras/EAN/GTIN e código interno/SKU antes do nome."),
            ("Impressão em medidas reais", "done", "CSS de impressão usa medidas em mm, @media print e oculta menu, filtros e botoes; a cor da etiqueta fica a cargo do papel físico, com impressão limpa em preto."),
            ("Configuração profissional de etiquetas", "partial", "Configuração por empresa/filial persiste impressora, DPI, densidade, velocidade, mídia e linguagem. Modelos nomeados guardam largura, altura, gaps, colunas, orientação, modelo padrão e vínculo opcional ao terminal; a tela de etiquetas aplica o modelo escolhido e o endpoint desktop sincroniza todos os parâmetros e expõe prontidão print_readiness_v1 com impressoras configuradas, linguagem nativa e modelos profissionais. A central de impressão também prepara etiqueta de teste por modelo para envio direto pelo app desktop. Ainda faltam testes físicos com equipamentos reais."),
            ("Linguagens nativas de impressoras", "partial", "Arquitetura contempla ZPL, EPL, PPLA e PPLB. A tela web monta um payload confiável no contrato label_print_v1, com modelo, produtos e cópias em chaves ASCII, consulta a prontidão print_readiness_v1 e aciona printLabels somente no app desktop; o agente gera ZPL, EPL, PPLA ou PPLB, converte medidas por DPI e envia ao spooler Windows em RAW com limite e retorno visível. No navegador permanece a impressão convencional. O teste de modelo usa a mesma ponte local e o mesmo contrato do lote real. A ponte bloqueia contrato incompatível ou lote excessivo antes do spooler e retorna ao operador a quantidade de produtos e cópias efetivamente enviada. Ainda faltam homologação por modelo e testes físicos."),
        ],
    },
    {
        "titulo": "Escopo original a decidir",
        "descricao": "Itens previstos nos documentos iniciais que não devem desaparecer do roadmap sem uma decisão explícita de produto.",
        "itens": [
            ("Recuperação de senha", "partial", "Fluxo seguro por e-mail implementado com resposta pública neutra, link temporário de uso único, validação de senha do Django, telas próprias e configuração SMTP por ambiente. Em desenvolvimento, o backend de console permite testar sem provedor externo. O diagnóstico protegido não expõe host, senha ou credenciais e publica a prontidão password_reset_readiness_v1, distinguindo backend de desenvolvimento, configuração incompleta e SMTP pronto para homologação real. O comando verificar_prontidao_recuperacao_senha oferece saída humana ou JSON e modo estrito para bloquear implantações com backend de desenvolvimento ou SMTP incompleto; o roteiro está em docs/RECUPERACAO_SENHA_SMTP.md. Falta configurar o provedor definitivo, validar SPF/DKIM/DMARC e homologar entrega e recuperação ponta a ponta para concluir o item."),
            ("Cotação e pedido de compra", "done", "Ciclo prévio completo com cotação por filial e itens, abertura controlada, propostas únicas por fornecedor, preços e disponibilidade por produto, comparação de totais e prazos e seleção auditada da proposta. A proposta escolhida gera pedido em rascunho sem estoque ou financeiro. O pedido possui envio, cancelamento e conversão única em entrada vinculada; excluir a entrada enquanto rascunho reabre o pedido. Somente a finalização da entrada usa o serviço existente para movimentar estoque e criar financeiro."),
            ("Importação de XML de entrada", "done", "Importação segura de NF-e autorizada implementada com limite de arquivo, bloqueio de DTD/entidades, validação da chave e prevenção de duplicidade. O sistema identifica fornecedor e filial por CNPJ, associa todos os produtos por GTIN ou código cadastrado e rejeita integralmente arquivos com itens sem correspondência. A NF-e cria somente uma entrada em rascunho auditada para revisão, separa total dos produtos do total fiscal usado no financeiro e não movimenta estoque ou contas antes da finalização pelo fluxo existente."),
            ("Estoque geral por lote, validade e custo histórico", "done", "Camada retrocompatível implementada sem substituir o saldo agregado: entradas manuais, compras e NF-e com grupo rastro podem gerar lotes com fabricação, validade, quantidade e custo histórico; saidas e vendas consomem as camadas por FEFO e registram a alocação por movimento. O painel lista saldos, vencidos e itens a vencer em 30 dias, enquanto estoque legado sem lote continua utilizável. A reconciliação permite atribuir saldo histórico a lotes com limite, autorização, motivo e auditoria sem alterar o físico; reduções de inventário ajustam camadas somente quando o rastreado excederia a nova contagem, e aumentos permanecem sem lote até atribuição explícita. Produção e desmembramento consomem lotes de componentes/origens por FEFO, criam camadas nos destinos identificados e seus cancelamentos restauram as alocações originais de forma transacional. A política de lote obrigatório por produto é opcional e vem desativada: quando ativada, bloqueia novas entradas, NF-e sem rastro e produtos gerados por produção ou desmembramento sem lote, sem impedir vendas e demais usos do saldo legado."),
        ],
    },
    {
        "titulo": "Próximas fases",
        "descricao": "Itens previstos na documentacao, ainda fora do MVP atual.",
        "itens": [
            ("Núcleo fiscal NFC-e e NF-e", "done", "Fila fiscal mostra vendas prontas, pendencias antes da acao e ultima tentativa automática auditada; tela de produtos fiscais antecipa correcoes de NCM, CEST, origem, CST/CSOSN e alíquota. XML local usa UF e código IBGE da filial. A NFC-e segue a regra de ocorrer somente após pagamento confirmado: por padrão a venda tenta preparar a NFC-e automaticamente, mas o admin pode desativar essa tentativa por terminal PDV quando a empresa decidir operar aquele caixa sem comunicacao fiscal automática. O PDV exibe no topo se o terminal identificado está com fiscal automático ligado ou desligado. A venda presencial agora aceita CPF opcional na nota sem cadastro de cliente, pergunta o documento dentro do popup de pagamento, grava o dado na venda e inclui o CPF no XML local da NFC-e; CNPJ solicitado no caixa é bloqueado para NFC-e automática e orientado para NF-e modelo 55. Pedidos online/marketplace agora possuem documento do destinatário e podem preparar NF-e modelo 55 local, com série e natureza fiscal próprias, vinculada ao pedido. As naturezas de operação agora pertencem à empresa: listagem, edição, diagnóstico e emissores de NFC-e/NF-e respeitam o isolamento multiempresa; a migração replica cadastros legados por empresa e preserva o vínculo dos documentos existentes. Cada empresa também possui uma única natureza padrão por tipo de documento; a primeira ativa é promovida automaticamente, a troca usa ação POST auditada e os emissores recusam seleção implícita de outro cadastro. Painel fiscal agora traz prontidão por filial, certificado, séries, vendas aguardando documento, produtos com pendência e diagnóstico JSON fiscal_readiness_v1 para suporte. O diagnóstico também separa homologação simulada de produção real pelo contrato fiscal_production_readiness_v1, alertando quando existe filial em produção sem adaptador oficial SEFAZ configurado. Se faltar cadastro fiscal, a venda não trava e a pendencia fica auditada para correção. Transmissao simulada em homologação gera chave, protocolo e auditoria. A contingência offline da NFC-e agora depende de autorização explícita por filial, aceita somente documento pronto e modelo 65, exige justificativa técnica, grava início e prazo de 24 horas, regenera o XML com tpEmis 9, dhCont e xJust, mantém o documento sem protocolo até a regularização e registra toda a decisão em auditoria. A central e o diagnóstico destacam documentos em contingência e prazos vencidos; a exportação fiscal_contingencia_v1 inclui os dados necessários para suporte e posterior transmissão. A transmissão SEFAZ real agora passa pelo contrato único de adaptadores SEFAZ: a classe configurada precisa ser carregável, recebe XML, ambiente e chave idempotente determinística, e somente retornos estritos de autorizado, rejeitado ou pendente alteram o documento. Autorização exige chave de acesso de 44 dígitos e protocolo; falhas, rejeições e pendências preservam evidência e auditoria, e o botão de produção só aparece quando o adaptador é válido, há validação XSD e a assinatura está disponível pelo provedor ou pelo certificado A1 local válido. A preparação agora calcula e persiste a chave de acesso de 44 dígitos com DV módulo 11, usa o mesmo identificador no infNFe, recalcula a chave ao mudar para tpEmis 9 e executa pré-validação de XML, modelo, cDV, assinatura e coerência da chave retornada antes de aceitar autorização. A validação XSD local agora usa lxml com parser sem rede, DTD ou entidades, pacote versionado por diretório, arquivo raiz e SHA-256; a prontidão aceita schema local homologado ou capacidade valida_schema declarada pelo provedor e bloqueia produção quando nenhuma opção está disponível. A assinatura XMLDSig local com certificado A1 está implementada com C14N, referência envelopada, RSA-SHA1 e SHA1 conforme o leiaute NF-e, valida período do certificado, identificador, algoritmos, digest e assinatura antes da transmissão, impede referências duplicadas e registra data e serial sem persistir a chave privada no XML; provedores que declaram assina_xml continuam responsáveis pela assinatura no fluxo alternativo. O comando instalar_schemas_fiscais agora recebe ZIP local ou URL HTTPS restrita ao Portal Nacional, exige SHA-256 aprovado, bloqueia traversal, links e pacotes abusivos, compila o XSD sem rede, promove versões atomicamente e grava manifesto auditável; ele foi validado também contra o pacote oficial 010e v1.01 em área temporária, sem ativação automática. O DANFE NFC-e térmico agora possui layout compacto próprio, valores em R$, chave, protocolo, consumidor e QR Code 3.0 de consulta; as URLs oficiais são configuradas por filial/ambiente, o XML inclui infNFeSupl e a contingência assina os parâmetros com o mesmo certificado A1. Documento não autorizado recebe aviso de sem valor fiscal e não exibe QR; esse QR não pertence ao cupom não fiscal. O pós-venda e a reimpressão do PDV agora priorizam automaticamente a NFC-e emitida ou em contingência: o endpoint entrega o contrato danfe_nfce com chave, série, número, protocolo, consumidor e QR original do XML; o app desktop monta DANFE compacto e QR nativo ESC/POS, envia direto ao spooler sem pré-visualização e informa falhas ao operador. Sem documento fiscal imprimível, permanece o cupom não fiscal explicitamente identificado. A opção central de impressão automática agora é efetivamente respeitada no app desktop ao abrir o pós-venda CAIXA LIVRE; no navegador comum o operador mantém o comando F10. A transmissão automática ganhou a fila fiscal_transmission_queue_v1: comando agendável por lote, habilitação explícita, produção separada da simulação de homologação, limite de tentativas, espera exponencial, lease contra concorrência, diagnóstico visual/JSON e script Windows para execução recorrente; o painel e o JSON respeitam o escopo da empresa, enquanto o serviço central processa todas as filiais autorizadas do servidor; falhas não travam o caixa nem perdem o documento. A Central Fiscal agora permite que gerente ou administrador corrija a origem e recoloque rejeições ou falhas na fila mediante motivo obrigatório: o XML é regenerado, a assinatura anterior é invalidada, as tentativas são reiniciadas e o estado anterior fica registrado em auditoria; documentos autorizados, cancelados ou inutilizados não podem ser reabertos. O cancelamento de documento já emitido exige justificativa fiscal de 15 a 255 caracteres, chave e protocolo de autorização; chama o método idempotente do adaptador, mantém o documento emitido em falha ou rejeição e só grava o status cancelado após receber o protocolo do evento SEFAZ. A Central Fiscal também registra e transmite inutilização de faixas nunca usadas, bloqueia números já ocupados ou faixas sobrepostas e exige protocolo para autorizar. A consulta síncrona de protocolo por chave de 44 dígitos reconcilia respostas perdidas: autorização, cancelamento e denegação atualizam o estado somente após retorno estrito do adaptador; pendência, ausência e falha preservam o estado local e ficam auditadas. A fila automática agora marca transmissões pendentes para consultar a chave antes de qualquer reenvio: autorização, cancelamento ou denegação encerram o ciclo, consulta ainda pendente permanece em espera e somente a confirmação de documento não localizado libera uma nova transmissão no ciclo seguinte. Para NFC-e offline são exigidas no mínimo duas confirmações consecutivas; timeout reinicia essa sequência. Rejeições preservam tpEmis 9, chave, dhCont e xJust durante a correção, e uma nota já entregue offline não pode ser cancelada apenas localmente. Prazos excedidos ficam destacados sem retirar a nota da reconciliação. O arquivo técnico interno agora preserva em registros append-only o XML entregue ao adaptador, retornos normalizados, XML autorizado, consultas e eventos de cancelamento/CC-e; referências idempotentes evitam duplicação, cada registro possui SHA-256 e encadeamento com o anterior, alterações e exclusões pela aplicação são bloqueadas e somente o Master vê o diagnóstico de integridade sem acessar o conteúdo por essa tela. O backup diário verifica a cadeia em modo estrito, compara a âncora externa anterior, recusa regressão histórica, inclui o manifesto sanitizado no ZIP e o restaurador compara a cadeia antes de iniciar o serviço. A verificação operacional registra na auditoria somente estado, origem e totais sanitizados, evita duplicação do mesmo estado e exibe o alerta apenas ao Master no Super Admin e no Backup. As consultas possuem contador e limite próprios, espera exponencial e diagnóstico de reconciliações esgotadas; ao atingir o limite, a automação libera o documento sem retransmitir e exige análise ou consulta manual. A Central Fiscal oferece retomada explícita somente das consultas, com motivo obrigatório, contador reiniciado e auditoria, mantendo a retransmissão bloqueada. O catálogo estadual fiscal agora possui arquitetura extensível por UF e o primeiro perfil homologável é Goiás: preenche e valida por ambiente os endpoints HTTPS vigentes do QR Code e da consulta NFC-e conforme o Informe Técnico 2025.003, bloqueia URLs antigas e diagnostica cBenef no padrão GO mais seis dígitos, exigindo-o quando o cadastro informa redução de base do ICMS. UFs ainda não catalogadas continuam com configuração manual, sem herdar regras de GO. O CRT agora é estruturado por filial com os códigos oficiais 1, 2, 3 e 4; Lucro Real e Presumido usam CRT 3, a migração converte cadastros legados e NFC-e/NF-e deixam de inferir o regime pelo texto livre. O emissor local agora calcula e totaliza ICMS para CST 00 e CST 20, aplica redução de base, FCP e cBenef, rateia o desconto pelos itens e mantém vBC, vICMS, vFCP, vProd, vDesc e vNF coerentes nos modelos 55 e 65. Os CST 40, 41 e 50 agora usam o grupo ICMS40 sem débito de ICMS nos dois modelos; cadastro, filtro de produtos e emissão compartilham a mesma matriz fiscal_tax_capability_v1, visível na tela e no diagnóstico JSON. A prontidão e a listagem agora reutilizam um único filtro SQL para ICMS, PIS, COFINS, IPI e regras objetivas de Goiás, contam todo o catálogo sem corte em 500 itens e paginam somente os registros solicitados. CST 60 e demais grupos que dependem de dados ainda não modelados permanecem bloqueados para evitar tributação incompatível silenciosamente. PIS e COFINS agora geram grupos e totais para CST 01/02, não tributados 04 a 09 e outras operações 49/99, usando a base líquida após o rateio do desconto. IPI permanece opcional: os CST não tributados 01 a 05 e 51 a 55 geram IPINT com cEnq. Os CST tributados 00, 49, 50 e 99 agora geram IPITrib somente quando a natureza da operação confirma explicitamente que o imposto já está incluído no preço; a mesma natureza define, com orientação contábil, se o IPI compõe as bases de ICMS e PIS/COFINS. O emissor decompõe produto, desconto e IPI, mantém o total pago e usa a mesma regra nos modelos 55 e 65; sem essa política, a preparação permanece bloqueada. A composição tributária permanece bloqueada por configuração até receber a parametrização contábil de cada operação real. A captura opcional de CPF/CNPJ pelo pinpad agora negocia capacidade com cada driver TEF, oferece atalho Shift+F4 no pagamento, preserva digitação manual quando indisponível, valida CPF/CNPJ recebido e não grava o documento pessoal no diagnóstico local; a integração física permanece protegida até a homologação dos equipamentos selecionados."),
            ("Contrato de adaptador SEFAZ", "partial", "O contrato técnico independente de canal cobre transmissão, consulta, cancelamento, inutilização, schema e assinatura. O Master agora escolhe por filial entre compatibilidade do servidor, Focus NFe, conexão direta SEFAZ GO ou emissão externa desativada; administradores e gerentes não veem nem alteram essa decisão. O roteador central aplica a escolha também na emissão, consulta, cancelamento, inutilização, preflight e diagnóstico agregado, com auditoria da alteração. Credenciais, rede e produção permanecem protegidas pelas configurações do servidor. O transporte direto agora possui retry somente para consultas idempotentes, circuit breaker por host e telemetria sanitizada em memória; emissão e eventos não são repetidos automaticamente diante de resposta incerta. A contingência NF-e SVC-RS de Goiás também está pronta estruturalmente: gera tpEmis 7, nova chave/XML e usa catálogo separado, mas somente o Master vê e aciona o fluxo; a feature flag permanece desligada. Faltam credenciais e CNPJ válidos, execução dos cenários reais em homologação e aceite fiscal/contábil."),
            ("Devolução fiscal ao fornecedor", "partial", "O fluxo não emissivo confere entrada/XML, preserva chave, nItem e snapshot, limita quantidades e submete com SHA-256. A fila exclusiva de Administrador/Contabilidade permite corrigir ou aprovar somente a preparação; Compras e Financeiro não decidem. O parecer append-only registra natureza, regime, CFOP oficial e orientação humana. A ficha `supplier_return_item_tax_parameters_v1` exige escolha explícita do parecer e classifica atomicamente todos os nItem com origem e CST/CSOSN do ICMS, CST ou NA de IPI/PIS/COFINS, código cBenef GO ou NA e orientações complementares. A memória `supplier_return_item_tax_calculation_memory_v1` recebe bases, alíquotas e valores informados para todos os itens, exige zeros quando não aplicáveis e confere cada total antes de gravar. Versões idempotentes preservam parecer, ficha, XML e conteúdo por hash, sem copiar a entrada, definir fórmula ou alimentar XML. Nada cria documento, numeração, estoque ou Focus/SEFAZ. A revisão da memória exige outro Administrador/Contabilidade, versão mais recente e decisão única imutável. Correções exigem nova versão. Ficha logística versionada registra modalidade, transportador, volumes e pesos sobre a memória aprovada mais recente. CPF/CNPJ numérico do transportador tem validação dos dígitos verificadores; transporte próprio compara a identidade com as partes do XML original. Composição comercial versionada confere base, frete, seguro, despesas e desconto contra o total declarado, exige confirmação de que os ajustes não estão embutidos e preserva o vínculo à memória aprovada. A revisão exige outro responsável e orientações explícitas sobre os reflexos tributários, preserva decisão única e bloqueia versões superadas. Rateio comercial por item implementado: componentes explícitos, somas exatas, composição aprovada atual, histórico imutável e integridade da origem. Reflexos declarados nas bases integrados ao serviço protegido, histórico imutável e tela, vinculados ao rateio atual e com integridade verificada. Não recalculam impostos. Conferência independente dos reflexos implementada: outro responsável, decisão única imutável, justificativa e origem atual íntegra. Memória revisada vinculada aos reflexos aprovados, com bases finais exatas e bloqueio de reaplicação. Correção rastreável da memória revisada implementada, preservando bases e decisão anterior e exigindo nova revisão. Painel de consulta consolidada do dossiê implementado, distinguindo pendências e referências históricas. Próxima etapa: especificar o contrato de dados do XML e os bloqueios por campo; emissão bloqueada."),
            ("Homologação fiscal em produção", "partial", "O núcleo fiscal interno está concluído e protegido por diagnóstico de prontidão. Goiás possui agora um roteiro técnico por filial que registra evidência, responsável e checagens automáticas de certificado, CSC, série, natureza, schema, adaptador e documento de homologação. Para liberar produção em cada cliente, ainda faltam contratar e configurar o provedor/adaptador fiscal oficial, instalar credenciais e schemas vigentes, parametrizar impostos com o contador, executar cenários de autorização, rejeição, cancelamento, inutilização, contingência e reconciliação no ambiente de homologação da SEFAZ e homologar pinpads físicos. Esta etapa depende de contador, credenciais, fornecedor fiscal e infraestrutura real do supermercado."),
            ("Transição tributária IBS/CBS", "partial", "Modo legado e preparação por vigência; CST IBS/CBS e cClassTrib validados no cadastro. Emissão XML ficará bloqueada até schema oficial e homologação."),
            ("Financeiro completo", "partial", "Categorias financeiras, centros de custo e plano de contas são isolados por empresa, com seleção explícita da empresa somente para o super admin e bloqueio de vínculos cruzados. O plano de contas possui código único por empresa, natureza, contas sintéticas e analíticas, hierarquia protegida contra ciclos, paginação e auditoria; categorias só podem usar contas analíticas da mesma empresa. Centros de custo classificam contas a pagar e receber. A conta contábil e o centro de custo ficam preservados como fotografias históricas no livro financeiro imutável e nos estornos. O módulo possui contas a pagar e receber, baixas, cancelamentos, fluxo de caixa, conciliação PDV x financeiro, contas de movimento, vendas do PDV no livro, transferências e estornos por lançamento inverso. O Resultado Financeiro apresenta receitas, despesas, margem, DRE gerencial, visão por origem, categoria, centro de custo, conta contábil e conta de movimento, saldos por filial, balancete, conciliação bancária, conferência fiscal x financeiro, CSV e pacote contábil JSON financial_accounting_package_v1. A ponte contábil oferece diagnóstico, envio administrativo idempotente, protocolo, hash, histórico protegido e auditoria. Para concluir o item, ainda é necessário escolher e homologar o provedor fiscal/contábil real e implementar os relatórios oficiais SPED, ECD e ECF."),
            ("Portal contábil e pacote mensal", "partial", "Perfil Contabilidade criado com acesso somente leitura e escopo limitado à empresa vinculada. O portal permite escolher competência e filial autorizada, consulta receitas, despesas, resultado, documentos fiscais e XMLs disponíveis, e baixa ZIP auditado pelo contrato accounting_monthly_package_v1 com resumo financeiro, lançamentos CSV, relação fiscal e XMLs já gerados. Administradores também podem gerar e revogar chave própria por empresa; a API GET accounting_monthly_api_v1 usa cabeçalho X-Contabilidade-Key, armazena apenas SHA-256, exige HTTPS em produção, não aceita filial fora do escopo e audita cada consulta. Não libera PDV, cadastros, usuários, configurações ou dados de outra empresa. Próxima etapa: homologar o layout e os campos com o escritório contábil e, em frente separada, implementar/exportar obrigações oficiais SPED, ECD e ECF conforme regime, UF e validação profissional."),
            ("Entradas, saídas e livro contábil", "partial", "Contas de movimento por filial para caixa físico, banco, PIX e outras foram criadas com saldo inicial e saldo atual. Baixas geram entrada ou saída no livro imutável, vendas à vista do PDV geram entradas automáticas por forma de pagamento, sangria e suprimento geram saída/entrada automática no Caixa PDV, transferências entre contas geram lançamentos espelhados, atômicos e auditados dentro da mesma empresa, e estornos por lançamento inverso preservam o original. O livro possui origem, usuário, data, filtros, exportação CSV, validação de saldo e conciliação bancária separada e imutável com referência de extrato, responsável e auditoria, relatório de receitas, despesas e resultado que ignora transferências internas, e balancete gerencial que considera transferências para refletir o saldo real das contas. A origem de vendas do livro já é confrontada com os documentos fiscais correspondentes no fechamento gerencial, sem alterar o livro imutável. Cada lançamento também publica o contrato financeiro_lancamento_v1 para a retaguarda, com idempotência, empresa, filial e classificações históricas. A exportação gerencial pode ser entregue por adaptador contábil configurável, com protocolo, histórico e auditoria; ainda faltam homologar o provedor escolhido e as integrações contábeis oficiais. Referência funcional identificada no ProjetoLimpoGitHub para migração adaptada, sem alterar o projeto original."),
            ("Marketplace / pedido online", "done", "Fluxo operacional completo, API segura com chave por plataforma, validacao de itens, idempotência e acompanhamento visual de separação/pagamento na listagem implementados. Pedidos agora guardam CPF, CNPJ ou documento estrangeiro do destinatário, inclusive pela API do parceiro, e o detalhe do pedido permite preparar NF-e modelo 55 local vinculada ao pedido online. A central de integracoes agora mostra saude operacional por canal, pedidos recebidos, pedidos abertos, pagamentos pendentes, alertas de homologação e prontidão marketplace_partner_readiness_v1 por parceiro, com diagnóstico JSON para suporte sem expor a chave completa. API de parceiros tambem possui endpoint autenticado marketplace_partner_v1 para validar chave, filial, recursos, idempotência, política de entrega e prontidão antes de enviar pedido real. A camada marketplace_partner_adapter_v1 agora seleciona o provedor por integração, mantém os caminhos Python exclusivamente no ambiente do servidor, traduz payloads externos antes da transação, preserva idempotência pela referência normalizada, bloqueia com segurança provedores sem driver e publica prontidão na Central e na API do parceiro. O contrato e o roteiro de homologação estão documentados em docs/INTEGRACOES_MARKETPLACE.md. O núcleo interno de marketplace e pedidos online está concluído; parceiros comerciais e transmissão fiscal de produção permanecem acompanhados separadamente como homologações externas."),
            ("Homologação de parceiros marketplace", "partial", "A integração específica depende da escolha comercial de cada parceiro. Falta definir os canais prioritários, obter documentação e credenciais de sandbox, implementar os drivers sobre o contrato marketplace_partner_adapter_v1 e homologar criação, atualização, cancelamento, pagamento, entrega e idempotência ponta a ponta. A transmissão fiscal em produção continua controlada no item Homologação fiscal em produção."),
            ("Impressão personalizada", "done", "Configurações de papel, margens, fonte, rodapé, vias e impressão automática aplicadas aos recibos. No app desktop, o botão pós-venda usa o payload autenticado existente, monta cupom operacional sem imagens e envia diretamente ao spooler Windows em RAW/ESC-POS, com até três vias, corte de papel e pulso opcional da gaveta, sem abrir pré-visualização. O cupom não fiscal foi padronizado para bobinas de 58 e 80 mm com fonte compacta, CNPJ, endereço, descrições acentuadas, quantidade total, valores identificados em R$, pagamentos, troco, operador, caixa e aviso explícito de documento sem valor fiscal; o recibo web segue a mesma hierarquia. Quando existe NFC-e autorizada ou em contingência, F10 e a reimpressão usam o DANFE fiscal com QR Code no navegador e no app desktop; o cupom não fiscal é usado somente quando não há documento fiscal imprimível."),
            ("Descoberta de impressoras locais", "done", "Central de impressão possui campo com sugestões e endpoint de configuração. A ponte do app desktop consulta as impressoras instaladas no Windows sem shell interativo e devolve nome, porta, driver, estado e impressora padrão para a mesma interface do PDV, tratando timeout ou falha sem bloquear a venda."),
            ("Gaveta de dinheiro opcional", "partial", "Central de impressão permite habilitar ou desabilitar gaveta automática por empresa/filial e documento de caixa. Bootstrap e pacote do terminal entregam o contrato pdv_cash_drawer_v1 com impressora, abertura em dinheiro e movimentos de caixa. O app desktop possui ponte openCashDrawer, envia pulso ESC/POS pela impressora configurada e registra diagnóstico local da gaveta em sucesso, falha ou desabilitado sem bloquear a venda. Venda em dinheiro, sangria, suprimento, abertura e fechamento de caixa agendam abertura somente depois da operação ser aceita pelo servidor, preservando senha de supervisor/admin quando exigida. A pré-homologação não aciona a gaveta por padrão e só envia o pulso após seleção explícita e confirmação de segurança pelo operador, registrando a evidência consolidada. Falta testar com gavetas físicas reais."),
            ("Backup/restauracao operacional", "done", "Tela de backup JSON, backup local erp_local_backup_v2 e restaurador scripts/restore_local_backup.ps1 disponíveis em Sistema. A validação confere SHA-256, AES-256, contrato e ZIP antes da janela; o ensaio local_restore_rehearsal_v1 restaura SQLite em área temporária ou PostgreSQL em banco dedicado, previamente criado e vazio, aplicando migrations, Django check e integridade fiscal sem serviço ou dados ativos; a execução real exige confirmação e privilégio administrativo, cria backup anterior, restaura SQLite ou PostgreSQL e mídia com o serviço parado, valida a âncora fiscal externa e a cadeia restaurada, registra o resultado sanitizado para alerta exclusivo do Master, pode promover somente o pacote AES-256 com SHA-256 para NAS/rede/disco externo confirmado e retenção separada, registra histórico sanitizado de cada execução, destaca a última falha somente ao Master e monitora separadamente a idade do último sucesso pelo contrato backup_freshness_v1, desligado por padrão até a política LOCAL_BACKUP_MAX_AGE_HOURS ser configurada, compartilha a política backup_age_policy_v1 com o pós-instalação e bloqueia o aceite enquanto o prazo estiver desativado; o aceite também recalcula o SHA-256, inspeciona integralmente o ZIP, exige o contrato erp_local_backup_v2, banco declarado e âncora fiscal válida, inclusive após descriptografar AES-256 com o segredo operacional, aplica migrations, exige healthcheck e faz rollback automático em falha."),
            ("Modo local administrativo", "partial", "Para supermercados sem internet ou sem rede estruturada, o produto deve permitir instalação local do servidor administrativo na própria loja, em um computador servidor ou máquina principal, acessado por navegador em localhost ou rede interna. Não é necessário duplicar todo o ERP em um segundo app desktop administrativo; a abordagem profissional é empacotar o servidor local, banco, serviços, backup, atualizações controladas e um atalho/app shell opcional para abrir o painel administrativo. A central Sistema > Servidor local já apresenta arquitetura, requisitos, modos por empresa, riscos pendentes, manifesto JSON erp_local_admin_v1, guia docs/IMPLANTACAO_SERVIDOR_LOCAL.md e scripts scripts/run_local_server.ps1, scripts/install_local_server_service.ps1, scripts/test_local_server_service.ps1, scripts/uninstall_local_server_service.ps1, server_local/windows/DeigoVarejoServidorLocal.xml.template, scripts/register_local_server_task.ps1, scripts/backup_local.ps1, scripts/register_backup_task.ps1 e scripts/register_sync_task.ps1 para operação local inicial, backup e sincronização recorrente no Windows. O backup local usa o contrato erp_local_backup_v2, descobre as fontes pela configuração efetiva do Django ou pelo XML WinSW, gera dump lógico, snapshot SQLite consistente, mídia, manifesto e SHA-256; verifica as evidências fiscais em modo estrito, mantém uma âncora externa atômica no destino, recusa regressão e inclui o manifesto fiscal no ZIP; suporta criptografia opcional AES-256 por BACKUP_ENCRYPTION_PASSPHRASE e remoção do zip aberto com -RemoverOriginalCriptografado. O restaurador scripts/restore_local_backup.ps1 valida SHA-256, descriptografa AES-256 quando necessario, rejeita ZIP inseguro e contrato incompativel, exige confirmacao explicita e privilegio administrativo, cria um backup anterior, restaura SQLite ou PostgreSQL e midia com o servico parado, aplica migrations, exige healthcheck e recupera automaticamente os dados anteriores em caso de falha. O agendamento valida primeiro o contrato local_backup_sources_v1 e executa como SYSTEM sem depender de usuário conectado. Manifesto e tela do servidor local agora especificam o contrato de servico Windows DeigoVarejoServidorLocal, comando WSGI via Waitress, healthcheck, restart, logs, fallback operacional e contrato de prontidao local_admin_readiness_v1 validando scripts, guia, backup criptografado e modos de implantação. O PDV desktop continua separado e restrito ao operador, enquanto gerente/admin acessa o mesmo sistema web local com permissões completas. O servico Windows real agora possui instalador WinSW validado por SHA-256, Waitress, inicio automático, reinicio em falha, logs, diagnóstico e remocao; a tarefa agendada fica como contingência. A política final de sincronização operacional opcional está aplicada no modelo: modo local força sincronização automática desligada, limpa a URL externa, pausa filas existentes, rejeita novos eventos operacionais da nuvem e retoma os eventos ao voltar para híbrido com URL HTTPS; a consulta de licenciamento comercial permanece independente. O instalador do serviço agora usa por padrão a conta virtual NT SERVICE\\DeigoVarejoServidorLocal, sem senha armazenada, separa banco SQLite, mídia, estáticos e logs em ProgramData e aplica ACL mínima. O script scripts/package_local_server.ps1 gera pacote somente de commit Git limpo, com versão, manifesto, SHA-256 e opção de exigir commit assinado, sem dados ou segredos do cliente. O script scripts/publish_local_server.ps1 promove o ZIP e seu manifesto de forma atômica para a Central, que valida contrato, versão, commit rastreável, integridade, ausência de dados do cliente e exigência de commit assinado antes de liberar download exclusivo ao admin master e registrar auditoria. O atualizador scripts/update_local_server.ps1 valida o pacote antes da janela, rejeita ZIP inseguro, preserva .env e dados, cria snapshot do código e SQLite, para o serviço, aplica dependências, migrations e estáticos, exige healthcheck e restaura automaticamente código e banco em caso de falha, mantendo histórico local auditável. Backup e restauração PostgreSQL usam pg_dump/pg_restore em formato custom com transação e rollback automático; atualização de código com reversão de migrations destrutivas continua exigindo janela assistida e DBA. Falta homologar instalação, atualização, rollback e restauração em uma máquina Windows limpa e assinar o artefato definitivo."),
            ("Manual completo de instalação no supermercado", "partial", "Primeira versão criada em docs/MANUAL_INSTALACAO_SUPERMERCADO.md. O README do PDV documenta que MSI e manifesto são artefatos externos ao Git, como transferi-los ao servidor, quais variáveis configurar e que o servidor Linux apenas distribui o pacote produzido no Windows. O roteiro cobre responsabilidade técnica, distribuição sem código-fonte, topologia local/híbrida, requisitos, PostgreSQL, variáveis de ambiente, serviço Windows, licenciamento, instalação dos PDVs, dispositivos, fiscal, backup, restauração, sincronização, atualização, rollback, testes de aceite, entrega e registro da implantação. O comando verificar_prontidao_implantacao usa o contrato deployment_readiness_v2, separa os perfis central e servidor-local, aceita JSON e modo estrito sem expor segredos. O comando gerar_dossie_implantacao cria a evidência deployment_evidence_v1 com prontidão, versões e integridade dos artefatos, grava JSON atomicamente e produz SHA-256 separado, sem caminhos absolutos ou credenciais. O verificador deployment_evidence_validation_v1 detecta adulteração e, no modo estrito, impede o aceite enquanto prontidão ou pacote obrigatório estiverem pendentes. Depois da instalação, verificar_pos_implantacao aplica o contrato local_post_deployment_health_v1 e bloqueia o aceite sem HTTP, PostgreSQL/migrações, diretórios operacionais graváveis e backup local recente e integralmente validado por SHA-256, estrutura, contrato, banco e âncora fiscal. O comando gerar_evidencia_aceite vincula o hash do dossiê ao healthcheck no contrato local_installation_acceptance_evidence_v1, grava JSON e SHA-256 e fornece o anexo técnico do termo assinado; o roteiro está em docs/PRONTIDAO_IMPLANTACAO.md. A tela protegida Sistema > Servidor local gera um ZIP com dossiê, aceite e respectivos SHA-256, registra o download na auditoria e permite arquivar também diagnósticos bloqueados sem usar o PowerShell. A mesma tela mantém um histórico paginado, exclusivo do super admin, com máquina, sistema operacional, versão, SHA-256, resultado, observações, responsável e auditoria. O registro recebe o JSON e seu checksum, valida integridade, contrato, perfil, alvo, pós-instalação e segurança, e só aceita aprovação liberável; compara o aceite com a versão vigente e sinaliza pendência, reprovação, checklist incompleto ou evidência desatualizada. Reprovações exigem justificativa e uma evidência não pode ser reutilizada. O comando verificar_homologacao_servidor_local permite consultar a versão vigente, emitir JSON e usar --estrito para bloquear o instalador ou pipeline quando o aceite estiver pendente, reprovado, incompleto ou desatualizado; a mesma orientação aparece na Central do servidor local. O manual deve evoluir junto com o produto e será parte obrigatória do pacote de prontidão. Faltam acrescentar capturas das telas definitivas, comandos finais do pipeline assinado, modelos de equipamentos homologados e validar o procedimento completo em uma máquina Windows limpa antes da versão 1.0."),
            ("Aplicativo desktop/PDF", "done", "Endpoints de configuração e payload de impressão da venda preparados para o app desktop, incluindo dados de pagamento eletrônico, NSU, autorização e transação externa para cupom e comprovante. A interface desktop reutiliza o mesmo design, componentes, atalhos e regras do PDV web em um shell WebView separado, adaptando apenas a camada de integração com hardware e serviços locais. O esqueleto desktop_pdv possui ativação guiada na primeira execução, valida o bootstrap licenciado antes de salvar a credencial em LOCALAPPDATA e abrir /pdv/, permite reconfiguração e protege a chave de versionamento. O build reproduzível do executável Windows com PyInstaller também foi preparado. O spec usa a própria pasta do projeto em vez de caminhos absolutos de uma estação, o ambiente .build-venv é local e ignorado pelo Git, e um teste impede divergência entre a versão interna do app, a versão vigente do servidor e a publicação. A Central do App PDV desktop publica o instalador somente quando o artefato configurado existe, apresenta tamanho e SHA-256, restringe o download ao admin master e registra a entrega na auditoria. Um script de publicação atômica confere integridade, impede arquivo parcial na central e grava metadados de versão; versão e caminho do artefato são configuráveis por ambiente. O app informa sua versão no bootstrap, recebe versão vigente e mínima, avisa atualização opcional e bloqueia versão insegura; a instalacao continua exigindo o admin master, sem atualização automática fora do licenciamento. O app desktop agora salva cache local do bootstrap autorizado e, se o servidor estiver indisponível, abre com esse cache somente quando o terminal permite modo offline, registrando diagnóstico local; recusa de licença, chave ou terminal bloqueado nunca usa o cache como atalho. O manifesto JSON do app desktop expõe disponibilidade, integridade, contratos, terminais autorizados e prontidão de distribuição pelo contrato pdv_desktop_readiness_v1, alertando falta de instalador assinado, ausência de terminais e licenças pendentes. Pacote JSON por terminal entrega bootstrap, URL da interface compartilhada, TEF, fiscal, impressão, gaveta, balança configurada, licença por máquina e sincronização; o bootstrap operacional também devolve a configuração atual a cada inicialização. Terminais pendentes, bloqueados ou cancelados não recebem pacote de ativação nem conseguem inicializar o bootstrap. O aplicativo continua sendo um projeto/artefato separado, baixado por dentro do sistema somente com autorização do admin master e configurado com o terminal autorizado. O canal de manutenção por terminal licenciado baixa o artefato publicado pelo ERP, confere SHA-256 antes de promovê-lo na pasta local de updates e nunca instala silenciosamente; pacote adulterado ou incompleto é descartado. A estrutura pdv_windows_installer_v1 usa WiX v4 para MSI por máquina, upgrade, atalhos, desinstalação, metadados SHA-256, exigência opcional de executável assinado e assinatura do MSI via signtool; a publicação atômica prioriza o MSI da versão. A Central, o download administrativo, o bootstrap e a atualização do terminal compartilham o mesmo validador: exigem manifesto .version.json, versão vigente e SHA-256 correspondente; em produção, PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER também exige as assinaturas válidas declaradas pelo pipeline antes de distribuir. O núcleo de distribuição e sincronização resiliente está concluído; assinatura comercial, homologação em Windows limpo e dispositivos reais permanecem controlados separadamente nos itens de proteção/distribuição, arquitetura desktop, balança, TEF e etiquetas."),
            ("Sincronização loja-nuvem", "done", "Empresa escolhe entre servidor local, híbrido e nuvem com agente. Caixa de saída, processador HTTP e caixa de entrada autenticada usam UUID, idempotência, token fora do banco, timeout, lotes e retentativa exponencial. A autenticação operacional agora usa credencial exclusiva por CNPJ nos dois lados, impede que o token de uma loja envie eventos por outra empresa, limita o tamanho de cada evento e mantém o token global somente como fallback de migração explicitamente habilitado; a rotação sem indisponibilidade aceita temporariamente até três credenciais anteriores por empresa no receptor, enquanto o emissor usa somente a atual, e a prontidão sinaliza rotações ainda abertas; o diagnóstico mostra credenciais individuais, fallback transitório e empresas sem configuração. Eventos recebidos ficam armazenados antes de alterar dados e já passam por processador interno com handlers por tipo, erro controlado para domínios ainda não implementados, handler inicial de produtos, handler de saldo de estoque por filial, espelho de venda finalizada com painel de retaguarda, espelho fiscal sincronizado, detalhe auditável de eventos com payload e diagnóstico, resolução manual de conflitos com responsável, decisão e LogAuditoria, reprocessamento de entrada/saída também auditado, exportação CSV das filas de saída e entrada, diagnóstico JSON operacional com filas, alertas, próximos eventos, idade da fila mais antiga, eventos de saída com tentativas esgotadas, empresas por modo, contrato de prontidão sync_readiness_v1 e comando sugerido, comando único agendável, roteiro do Agendador de Tarefas do Windows no painel e script scripts/register_sync_task.ps1 para registrar a rotina recorrente. Movimentações locais de venda, compra, inventário, perda, produção e ajustes agora publicam automaticamente primeiro o snapshot do produto e depois o saldo consolidado da filial, pelos contratos produto_snapshot_v1 e estoque_saldo_v1. Revisões usam hash do conteúdo, saldos usam chave idempotente por movimento e atualizações recebidas da nuvem são marcadas para não gerar eco de produto ou estoque. O comando gerar_snapshot_sincronizacao e a ação protegida no painel preparam a carga inicial de catálogo e saldos já existentes por empresa ou filial, podem ser repetidos sem duplicar eventos, bloqueiam empresas que escolheram o modo somente local e registram a operação web no log de auditoria. Política automática opcional de conflito por empresa implementada: manual por padrão, com escolha entre a nuvem ou a loja prevalecer para produtos e saldo de estoque quando o dado local for mais recente; o descarte seguro do evento remoto fica registrado com motivo e horário, enquanto venda e fiscal permanecem manuais por desenho para decisão auditável. Painel, diagnóstico JSON, listagem de empresas e detalhe do evento exibem a política aplicada, e o admin técnico permite filtrar esse campo. A política operacional agora é centralizada no modelo: empresas locais ou com sincronização desativada pausam entrada e saída sem perder eventos, o receptor rejeita novos eventos, os processadores ignoram filas pausadas e a retomada para modo híbrido reabre as filas; o contrato sync_readiness_v1 contabiliza os eventos pausados. O licenciamento comercial continua consultando a central mesmo quando a sincronização operacional está desligada. O livro financeiro agora publica cada lançamento local pelo contrato financeiro_lancamento_v1; a retaguarda mantém um espelho idempotente por empresa e filial, rejeita tipo ou valor divergente para o mesmo ID e oferece totais de entradas, saídas e resultado, busca, paginação de 50 registros, diagnóstico JSON e CSV sem recriar lançamentos no livro operacional. O núcleo de sincronização operacional está concluído; transmissão SEFAZ real e homologação na infraestrutura definitiva permanecem controladas separadamente como dependências externas."),
            ("Super admin personalizado", "done", "Painel próprio centraliza empresas, usuários, fiscal, formas de pagamento, impressões, backup, auditoria e checklist, sem atalho visual para o admin Django. O acesso master agora é exclusivo de usuário superuser, representante do dono do software; administradores, gerentes e demais perfis das empresas recebem 403 em todas as rotas HTML, JSON, CSV e inspeção de modelos, e não visualizam o atalho do Super admin. A tela Sistema > Super admin reúne visão executiva, atalhos críticos, pendências acionáveis, saúde da sincronização, estornos eletrônicos pendentes com quantidade, valor e tela operacional própria, cobertura de telas próprias, atividade recente, atalhos de investigação, diagnóstico de ambiente/segurança, inventário de modelos, inspeção protegida e paginada por modelo, diagnóstico JSON e exportação CSV restritos ao admin master para acompanhar dados avançados sem entrar no admin padrão. Séries fiscais e naturezas de operação já possuem CRUD guiado, validação e auditoria próprios; sincronização e diagnósticos de dispositivos também possuem consultas protegidas, A fila interna de modelos avançados está concluída. Homologações externas e de hardware permanecem acompanhadas nos itens técnicos específicos."),
        ],
    },
]

CHECKLIST_GRUPOS.append(
    {
        "titulo": "Homologação operacional",
        "descricao": "Validação assistida por filial antes do início da operação real.",
        "itens": [
            ("Roteiro operacional por filial", "done", "Tela interna criada para registrar cadastros, compra, PDV, pagamentos, impressões, financeiro, fiscal e backup; a execução é isolada por empresa, auditada e possui histórico paginado."),
            ("Base demonstrativa controlada", "done", "Comando idempotente popular_demo cria uma empresa demonstrativa e os perfis admin, supervisor, caixa, estoque e contador apenas para testes controlados."),
            ("Aceite de equipamentos e fiscal reais", "partial", "Exige ambiente limpo, impressora, balança, TEF, certificado e credenciais reais do cliente antes da liberação comercial."),
        ],
    }
)

CHECKLIST_GRUPOS.append(
    {
        "titulo": "Evolução pós-piloto",
        "descricao": "Automação e governança priorizadas a partir da comparação técnica com ERPs de mercado.",
        "itens": [
            ("Piloto operacional de loja", "partial", "Validar em uma filial real a instalação, PDV, caixa, impressão, estoque, backup e recuperação, com responsáveis definidos e evidências de aceite."),
            ("Integração fiscal real em homologação", "partial", "Etapa ativa desde 24/08/2026 pela trilha Focus NFe sandbox. O adaptador está pronto, mas o ambiente local continua sem token, configuração fiscal por filial ou evidência real. Próximas ações: definir a filial piloto, receber credenciais de homologação por canal seguro, configurar certificado A1, CSC, IE, séries e regras validadas pelo contador, executar emissão manual de NFC-e/NF-e, consulta, rejeição, cancelamento e inutilização e registrar o aceite. A fila automática, a produção Focus, toda a rede SEFAZ direta e a feature flag SVC-RS permanecem desligadas."),
            ("Preflight fiscal por filial", "done", "O comando verificar_prontidao_fiscal e a tela de Homologação GO usam o mesmo diagnóstico local por filial. A checagem consolida dados cadastrais, CSC, endpoints, certificado A1, série, natureza, schema, adaptador, credencial Focus específica do CNPJ e evidência emitida, sem acessar Focus/SEFAZ e sem retornar token, CSC, certificado ou senha. Credencial de outra filial não produz falsa prontidão; a homologação real continua pendente."),
            ("Entrada de XML e conferência em três vias", "partial", "A primeira etapa já associa automaticamente a NF-e somente a um único pedido enviado com produtos, quantidades e totais idênticos; XML divergente continua em rascunho, sem vínculo automático nem movimentação. O vínculo manual autorizado, a conferência física guiada e a política por empresa já estão disponíveis: por padrão, divergências exigem conferência física antes da finalização, preservando responsável, observações e auditoria. A caixa de entrada já recebe XML manual por empresa. O responsável pode encaminhar um DF-e para entrada em rascunho com vínculo e auditoria ou desconsiderá-lo com motivo; sem estoque ou financeiro automáticos, a revisão e a finalização continuam obrigatórias. O núcleo da consulta por CNPJ/cursor está preparado com cursor independente por filial, lote atômico, deduplicação, auditoria, botão protegido e comando agendável. O adaptador Focus NFe já implementa autenticação Basic sem expor token, versão por CNPJ, consulta opcional do XML completo, TLS obrigatório, homologação por padrão e bloqueio explícito de produção. A manifestação do destinatário foi implementada estruturalmente com os quatro eventos oficiais, histórico, XML, protocolo, auditoria, isolamento por empresa e bloqueio de produção. A Carta de Correção Eletrônica também foi implementada estruturalmente para NF-e autorizada, com evento 110110, sequência de 1 a 20, prazo preventivo de 720 horas, texto consolidado, confirmação dos limites legais, XML, protocolo, auditoria e bloqueios independentes de rede e produção. Faltam configurar credenciais/certificado válidos, executar distribuição, manifestação e CC-e reais em homologação e registrar o aceite fiscal; a importação manual continua disponível."),
            ("Conciliação de cartões e bancos", "partial", "O núcleo usa o contrato financial_statement_adapter_v1, com CSV genérico e OFX nativos, adaptadores privados registrados somente no servidor, validação de extensão, deduplicação por SHA-256 e movimento, auditoria e rastreabilidade do layout usado. A agenda calcula prazo, taxa, bruto, líquido previsto e atraso por filial e forma eletrônica. O extrato prioriza NSU, transação ou autorização para registrar liquidação, antecipação, divergência ou chargeback em movimentos imutáveis; ambiguidades permanecem na revisão protegida. Depósitos agrupados podem ser rateados manualmente entre vários recebíveis, com saldo parcial e bloqueio de dupla conciliação. Faltam receber arquivos reais anonimizados, homologar os adapters proprietários dos fornecedores escolhidos e automatizar a identificação dos lotes."),
            ("Motor de preço, margem, validade e inventário", "done", "Lotes, validade, FEFO, perdas, reajuste, margem e preços normais versionados já possuem fluxo operacional e auditoria. Vendas ignoram lotes vencidos; produtos que exigem lote bloqueiam a baixa sem saldo rastreado válido; promoções válidas continuam prioritárias no PDV. O inventário orientado a risco prioriza saldo mínimo, validade, perdas, ausência de contagem e divergências anteriores, cria planos por filial com itens pendentes e bloqueia qualquer aplicação até a conclusão de todas as contagens físicas."),
            ("Contabilidade por competência", "todo", "Separar definitivamente livro financeiro de razão contábil: eventos, regras versionadas, partidas dobradas, lotes, períodos fechados e relatórios conciliáveis, sempre com aprovação contábil."),
            ("BI semântico e assistente de gestão", "todo", "Consolidar métricas reconciliadas por loja, produto, fornecedor e canal antes de oferecer painéis avançados, alertas e consultas de IA somente leitura."),
        ],
    }
)
def _instalador_pdv_desktop():
    return artefato_pdv_desktop()




DOCUMENTOS_PROJETO = [
    ("Complementar PDV, usabilidade, cadastros e entrega v2", "docs/protótipos/documento_complementar_pdv_usabilidade_cadastros_entrega_v2.docx"),
    ("Complementar desmembramento e fracionamento de produtos", "docs/protótipos/documento_complementar_desmembramento_fracionamento_produtos.docx"),
    ("Complementar etiquetas de gôndola e impressoras profissionais v2", "docs/protótipos/documento_complementar_etiquetas_gondola_impressoras_profissionais_v2.docx"),
    ("Índice dos documentos finais", "docs/protótipos/00_indice_documentos_finais_supermercado.docx"),
    ("Arquitetura técnica", "docs/protótipos/01_arquitetura_tecnica_sistema_supermercado.docx"),
    ("Modelagem banco de dados", "docs/protótipos/02_modelagem_banco_dados_sistema_supermercado.docx"),
    ("Regras de negócio", "docs/protótipos/03_regras_negocio_sistema_supermercado.docx"),
    ("MVP por fases", "docs/protótipos/04_mvp_por_fases_sistema_supermercado.docx"),
    ("Checklist de desenvolvimento", "docs/protótipos/05_checklist_desenvolvimento_sistema_supermercado.docx"),
    ("Mapa de telas e fluxos", "docs/protótipos/06_mapa_telas_fluxos_sistema_supermercado.docx"),
    ("Backup e restauracao", "docs/PLANO_BACKUP_RESTAURACAO_SUPERMERCADO.md"),
    ("Manual completo de instalação no supermercado", "docs/MANUAL_INSTALACAO_SUPERMERCADO.md"),
    ("Plano mestre de evolução comparativo", "docs/referencias_evolucao/Plano_Mestre_Evolucao_DeTecServer_Comparativo_iSOLIDUS.docx"),
    ("Nota técnica de evolução contábil", "docs/referencias_evolucao/Nota_Tecnica_Evolucao_Contabil_DeTecServer.docx"),
    ("Nota técnica de integração SEFAZ", "docs/referencias_evolucao/Nota_Tecnica_Integracao_SEFAZ_DeTecServer.docx"),
    ("Roadmap de evolução pós-piloto", "docs/ROADMAP_EVOLUCAO_POS_PILOTO.md"),
    ("Roteiro de homologação Focus NFe", "docs/FOCUS_NFE_HOMOLOGACAO.md"),
]
PDV_DESKTOP_VERSAO_PLANEJADA = settings.PDV_DESKTOP_VERSION


def _usuario_admin_master(user):
    return bool(user.is_authenticated and user.is_superuser)


def _empresa_id_administrativa(user):
    if user.is_superuser:
        return None
    perfil = getattr(user, "perfil_supermercado", None)
    if perfil and perfil.is_active and perfil.filial_id and perfil.tipo == TipoPerfil.ADMINISTRADOR:
        return perfil.filial.empresa_id
    return 0

def _empresa_id_operacional(user):
    if user.is_superuser:
        return None
    perfil = getattr(user, "perfil_supermercado", None)
    if perfil and perfil.is_active and perfil.filial_id:
        return perfil.filial.empresa_id
    return 0


def _empresas_visiveis(user):
    empresa_id = _empresa_id_operacional(user)
    queryset = Empresa.objects.all()
    return queryset if empresa_id is None else queryset.filter(pk=empresa_id)


def _filiais_visiveis(user):
    empresa_id = _empresa_id_operacional(user)
    queryset = Filial.objects.select_related("empresa")
    return queryset if empresa_id is None else queryset.filter(empresa_id=empresa_id)


def _terminais_visiveis(user):
    empresa_id = _empresa_id_operacional(user)
    queryset = TerminalPdv.objects.select_related("filial", "filial__empresa")
    return queryset if empresa_id is None else queryset.filter(filial__empresa_id=empresa_id)


def _configuracoes_impressao_visiveis(user):
    empresa_id = _empresa_id_operacional(user)
    queryset = ConfiguracaoImpressao.objects.select_related("empresa", "filial")
    return queryset if empresa_id is None else queryset.filter(empresa_id=empresa_id)


def _modelos_etiqueta_visiveis(user):
    empresa_id = _empresa_id_operacional(user)
    queryset = ModeloEtiqueta.objects.select_related(
        "configuracao", "configuracao__empresa", "configuracao__filial", "terminal"
    )
    return queryset if empresa_id is None else queryset.filter(configuracao__empresa_id=empresa_id)

def _exigir_admin_master(user):
    if _usuario_admin_master(user):
        return
    raise PermissionDenied


def _classificar_dependencia_roadmap(titulo, descricao):
    texto = _normalizar_texto_pesquisa(f"{titulo} {descricao}")
    trabalho_interno = [
        "compilar ou empacotar os modulos sensiveis",
        "implementar relatorios oficiais",
        "implementar e homologar os adaptadores reais",
        "implementar sincronizacao resiliente",
        "transmissao sefaz real",
    ]
    if any(marcador in texto for marcador in trabalho_interno):
        return {"codigo": "interno", "dependencia": "Desenvolvimento interno"}
    return {"codigo": "externo", "dependencia": "Homologa\u00e7\u00e3o externa"}


def _resumo_checklist(grupos):
    totais = {"done": 0, "partial": 0, "todo": 0}
    dependencias = {"interno": 0, "externo": 0}
    for grupo in grupos:
        grupo_totais = {"done": 0, "partial": 0, "todo": 0}
        for titulo, status, descricao in grupo["itens"]:
            totais[status] += 1
            grupo_totais[status] += 1
            if status == "partial":
                codigo = _classificar_dependencia_roadmap(titulo, descricao)["codigo"]
                dependencias[codigo] += 1
        grupo["total"] = len(grupo["itens"])
        grupo["concluidos"] = grupo_totais["done"]
        grupo["parciais"] = grupo_totais["partial"]
        grupo["pendentes"] = grupo_totais["todo"]
        grupo["percentual"] = round((grupo_totais["done"] / grupo["total"]) * 100) if grupo["total"] else 0
        grupo_pontos = grupo_totais["done"] + (grupo_totais["partial"] * 0.5)
        grupo["percentual_ponderado"] = round((grupo_pontos / grupo["total"]) * 100) if grupo["total"] else 0
    total_itens = sum(totais.values())
    pontos = totais["done"] + (totais["partial"] * 0.5)
    return {
        "total": total_itens,
        "concluidos": totais["done"],
        "parciais": totais["partial"],
        "pendentes": totais["todo"],
        "trabalho_interno": dependencias["interno"],
        "dependencias_externas": dependencias["externo"],
        "percentual": round((totais["done"] / total_itens) * 100) if total_itens else 0,
        "percentual_ponderado": round((pontos / total_itens) * 100) if total_itens else 0,
    }


def _proximas_etapas_checklist(grupos, limite=6):
    proximas = []
    for grupo in grupos:
        for titulo, status, descricao in grupo["itens"]:
            if status == "partial":
                classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao)
                dependencia = _classificar_dependencia_roadmap(titulo, descricao)
                proximas.append(
                    {
                        "grupo": grupo["titulo"],
                        "titulo": titulo,
                        "descricao": descricao,
                        **classificacao,
                        **dependencia,
                    }
                )
    prioridades = {"Alta": 0, "M\u00e9dia": 1}
    proximas.sort(key=lambda item: (item["codigo"] == "externo", prioridades.get(item["prioridade"], 2)))
    return proximas[:limite]


def _classificar_etapa_roadmap(grupo, titulo, descricao):
    titulo_texto = _normalizar_texto_pesquisa(titulo)
    texto = _normalizar_texto_pesquisa(f"{grupo} {titulo} {descricao}")
    if any(chave in titulo_texto for chave in ["financeiro", "contab", "contabil", "livro contabil"]):
        return {
            "trilha": "Financeiro",
            "prioridade": "Média",
            "acao": "Consolidar relatórios contábeis e conciliar origem fiscal, PDV e livro financeiro.",
        }
    if any(chave in titulo_texto for chave in ["marketplace", "pedido online"]):
        return {
            "trilha": "Integrações",
            "prioridade": "Média",
            "acao": "Escolher fornecedor/API, definir contrato e deixar fallback operacional.",
        }
    if any(chave in titulo_texto for chave in ["fiscal", "nf-e", "nfc-e"]):
        return {
            "trilha": "Fiscal",
            "prioridade": "Alta",
            "acao": "Separar homologação fiscal, certificado, series e contingência antes da transmissao real.",
        }
    if any(chave in titulo_texto for chave in ["balanca", "gaveta", "impressora", "etiqueta", "zpl", "epl", "ppla", "pplb"]):
        return {
            "trilha": "Dispositivos",
            "prioridade": "Média",
            "acao": "Planejar teste em equipamento real e manter fallback manual para o operador.",
        }
    if any(chave in titulo_texto for chave in ["tef", "maquininha", "pagamento misto"]):
        return {
            "trilha": "Hardware/TEF",
            "prioridade": "Alta",
            "acao": "Homologar o adaptador TEF com provedor escolhido e manter simulador para desenvolvimento.",
        }
    if any(chave in texto for chave in ["arquitetura pdv desktop", "servidor local", "desktop", "instalador", "windows", "sincronizacao"]):
        return {
            "trilha": "Implantação",
            "prioridade": "Alta",
            "acao": "Fechar pacote instalável, servico local e política de sincronização/atualizacao.",
        }
    if any(chave in texto for chave in ["sefaz", "certificado", "nf-e", "nfc-e", "fiscal"]):
        return {
            "trilha": "Fiscal",
            "prioridade": "Alta",
            "acao": "Separar homologação fiscal, certificado, series e contingência antes da transmissao real.",
        }
    if (
        any(chave in texto for chave in ["maquininha", "tef", "adquirente", "pix dinamico", "pagbank", "cielo", "stone", "getnet", "sitef"])
        or re.search(r"(?<!\w)rede(?!\w)", texto)
    ):
        return {
            "trilha": "Hardware/TEF",
            "prioridade": "Alta",
            "acao": "Homologar o adaptador TEF com provedor escolhido e manter simulador para desenvolvimento.",
        }
    if any(chave in texto for chave in ["balanca", "gaveta", "impressora", "etiqueta", "zpl", "epl", "ppla", "pplb", "equipamentos fisicos"]):
        return {
            "trilha": "Dispositivos",
            "prioridade": "Média",
            "acao": "Planejar teste em equipamento real e manter fallback manual para o operador.",
        }
    if any(chave in texto for chave in ["financeiro", "contáb", "contabil", "livro"]):
        return {
            "trilha": "Financeiro",
            "prioridade": "Média",
            "acao": "Consolidar relatórios contabeis e conciliar origem fiscal, PDV e livro financeiro.",
        }
    if any(chave in texto for chave in ["api externa", "geocodificacao", "marketplace", "adaptadores", "smtp", "spf", "dkim", "dmarc"]):
        return {
            "trilha": "Integrações",
            "prioridade": "Média",
            "acao": "Escolher fornecedor/API, definir contrato e deixar fallback operacional.",
        }
    return {
        "trilha": "Produto",
        "prioridade": "Média",
        "acao": "Quebrar em tarefa menor, implementar no sistema e cobrir com teste automatizado.",
    }


def _mapa_trilhas_roadmap(grupos):
    trilhas = {}
    for grupo in grupos:
        for titulo, status, descricao in grupo["itens"]:
            if status != "partial":
                continue
            classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao)
            trilha = classificacao["trilha"]
            item = trilhas.setdefault(
                trilha,
                {
                    "trilha": trilha,
                    "total": 0,
                    "alta": 0,
                    "media": 0,
                    "grupos": set(),
                    "acao": classificacao["acao"],
                },
            )
            item["total"] += 1
            item["grupos"].add(grupo["titulo"])
            if classificacao["prioridade"] == "Alta":
                item["alta"] += 1
            else:
                item["media"] += 1
    ordenadas = sorted(trilhas.values(), key=lambda item: (-item["alta"], -item["total"], item["trilha"]))
    for item in ordenadas:
        item["grupos"] = ", ".join(sorted(item["grupos"]))
        item["impacto_estimado"] = item["alta"] + (item["media"] * 0.5)
        item["peso_label"] = f"{item['impacto_estimado']:.1f}".replace(".", ",")
    return ordenadas


def _normalizar_texto_pesquisa(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(char for char in texto if not unicodedata.combining(char)).casefold()

def _filtrar_checklist(grupos, *, termo="", status="", grupo_titulo="", trilha="", prioridade="", dependencia=""):
    termo = _normalizar_texto_pesquisa(termo).strip()
    status = (status or "").strip()
    grupo_titulo = (grupo_titulo or "").strip()
    trilha = (trilha or "").strip()
    prioridade = (prioridade or "").strip()
    dependencia = (dependencia or "").strip()
    filtrados = []
    for grupo in grupos:
        if grupo_titulo and grupo["titulo"] != grupo_titulo:
            continue
        itens = []
        for titulo, item_status, descricao in grupo["itens"]:
            if status and item_status != status:
                continue
            if trilha or prioridade or dependencia:
                if item_status != "partial":
                    continue
                classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao)
                if trilha and classificacao["trilha"] != trilha:
                    continue
                if prioridade and classificacao["prioridade"] != prioridade:
                    continue
                classificacao_dependencia = _classificar_dependencia_roadmap(titulo, descricao)
                if dependencia and classificacao_dependencia["codigo"] != dependencia:
                    continue
            texto = _normalizar_texto_pesquisa(f"{grupo['titulo']} {titulo} {descricao}")
            if termo and termo not in texto:
                continue
            itens.append((titulo, item_status, descricao))
        if itens:
            filtrados.append({**grupo, "itens": itens})
    return filtrados


def _modelos_backup():
    modelos = []
    ignorar = {"Permission", "ContentType", "Session", "LogEntry"}
    for modelo in apps.get_models():
        if modelo._meta.object_name in ignorar:
            continue
        try:
            total = modelo._default_manager.count()
        except Exception:
            total = None
        modelos.append(
            {
                "app": modelo._meta.app_label,
                "modelo": modelo._meta.verbose_name_plural.title(),
                "modelo_tecnico": modelo._meta.object_name,
                "total": total,
                "inspecao_url": reverse("configuracoes:super_admin_modelo", args=[modelo._meta.app_label, modelo._meta.model_name]),
            }
        )
    return sorted(modelos, key=lambda item: (item["app"], item["modelo"]))


@login_required
@role_required(*ADMINISTRACAO)
def painel_sistema(request):
    empresa_id = _empresa_id_administrativa(request.user)
    if empresa_id == 0:
        raise PermissionDenied("Usuário sem empresa administrativa vinculada.")
    modelos = _modelos_backup() if request.user.is_superuser else []
    total_registros = sum(item["total"] or 0 for item in modelos)
    checklist_grupos = [{**grupo, "itens": list(grupo["itens"])} for grupo in CHECKLIST_GRUPOS]
    resumo_checklist = _resumo_checklist(checklist_grupos)
    configuracoes = ConfiguracaoImpressao.objects.all()
    configs_fiscais = ConfiguracaoFiscal.objects.select_related("filial")
    filiais_painel = Filial.objects.all()
    usuarios_painel = User.objects.filter(is_active=True)
    acessos_painel = AcessoPdvNuvem.objects.all()
    terminais_painel = TerminalPdv.objects.all()
    eventos_painel = EventoSincronizacao.objects.all()
    if empresa_id:
        configuracoes = configuracoes.filter(Q(empresa_id=empresa_id) | Q(filial__empresa_id=empresa_id))
        configs_fiscais = configs_fiscais.filter(filial__empresa_id=empresa_id)
        filiais_painel = filiais_painel.filter(empresa_id=empresa_id)
        usuarios_painel = usuarios_painel.filter(
            is_superuser=False, perfil_supermercado__is_active=True,
            perfil_supermercado__filial__empresa_id=empresa_id,
        )
        acessos_painel = acessos_painel.filter(filial__empresa_id=empresa_id)
        terminais_painel = terminais_painel.filter(filial__empresa_id=empresa_id)
        eventos_painel = eventos_painel.filter(empresa_id=empresa_id)
    atalhos = [
        {
            "titulo": "Formas de pagamento",
            "descricao": "Meios aceitos no PDV, troco e autorização eletrônica.",
            "icone": "fa-money-check-dollar",
            "url": "configuracoes:formas_pagamento",
            "status": f"{FormaPagamento.objects.filter(ativo=True).count()} ativa(s)",
        },
        {
            "titulo": "Empresas e filiais",
            "descricao": "Cadastro das lojas, logo, UF e código IBGE fiscal.",
            "icone": "fa-building",
            "url": "empresas:lista",
            "status": f"{filiais_painel.count()} filial(is)",
        },
        {
            "titulo": "Usuários",
            "descricao": "Perfis, permissões e vínculo de operador com filial.",
            "icone": "fa-user-gear",
            "url": "accounts:usuarios",
            "status": f"{usuarios_painel.count()} ativo(s)",
        },
        {
            "titulo": "Fiscal",
            "descricao": "NFC-e, certificado A1, séries, natureza e produtos fiscais.",
            "icone": "fa-receipt",
            "url": "fiscal:documentos",
            "status": f"{configs_fiscais.count()} configuração(ões)",
        },
        {
            "titulo": "Impressões",
            "descricao": "Central de impressoras, papel, vias e impressão automática.",
            "icone": "fa-print",
            "url": "configuracoes:impressoes",
            "status": f"{configuracoes.filter(is_active=True).count()} ativa(s)",
        },
        {
            "titulo": "Acessos PDV nuvem",
            "descricao": "Aprovação de operadores que tentam acessar o PDV em nuvem.",
            "icone": "fa-user-lock",
            "url": "pdv:acessos_pdv_nuvem",
            "status": f"{acessos_painel.filter(status=StatusAcessoPdvNuvem.PENDENTE).count()} pendente(s)",
        },
        {
            "titulo": "Terminais PDV",
            "descricao": "Máquinas de caixa autorizadas por filial para o aplicativo local.",
            "icone": "fa-cash-register",
            "url": "configuracoes:terminais_pdv",
            "status": f"{terminais_painel.filter(ativo=True).count()} ativo(s)",
        },
        {
            "titulo": "App PDV desktop",
            "descricao": "Instalador, requisitos e contrato local do caixa.",
            "icone": "fa-desktop",
            "url": "configuracoes:pdv_desktop",
            "status": "Bridge local",
        },
        {
            "titulo": "Servidor local/admin",
            "descricao": "Modo de implantação para lojas sem internet ou com operação em rede interna.",
            "icone": "fa-server",
            "url": "configuracoes:servidor_local",
            "status": "Admin local",
        },
        {
            "titulo": "Sincronização",
            "descricao": "Fila segura entre servidores locais e nuvem, com idempotência e tentativas.",
            "icone": "fa-arrows-rotate",
            "url": "empresas:sincronizacao",
            "status": f"{eventos_painel.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).count()} aguardando",
        },
        {
            "titulo": "Backup",
            "descricao": "Exportação operacional em JSON para contingência.",
            "icone": "fa-database",
            "url": "configuracoes:backup",
            "status": f"{len(modelos)} modelos",
        },
        {
            "titulo": "Auditoria",
            "descricao": "Consulta de ações críticas realizadas no sistema.",
            "icone": "fa-shield-halved",
            "url": "auditoria:logs",
            "status": "Logs",
        },
        {
            "titulo": "Super admin",
            "descricao": "Central avançada para admin master, sem depender do admin Django.",
            "icone": "fa-user-shield",
            "url": "configuracoes:super_admin",
            "status": "Master",
        },
        {
            "titulo": "Checklist",
            "descricao": "Roteiro vivo do projeto e próximas fases.",
            "icone": "fa-list-check",
            "url": "configuracoes:checklist",
            "status": f"{resumo_checklist['percentual']}%",
        },
    ]
    if not _usuario_admin_master(request.user):
        urls_exclusivas_master = {
            "configuracoes:super_admin", "configuracoes:checklist", "configuracoes:backup",
            "configuracoes:pdv_desktop", "configuracoes:servidor_local", "empresas:sincronizacao",
        }
        atalhos = [item for item in atalhos if item["url"] not in urls_exclusivas_master]
    context = {
        "atalhos": atalhos,
        "resumo_checklist": resumo_checklist,
        "total_empresas": Empresa.objects.count() if request.user.is_superuser else 1,
        "total_filiais": filiais_painel.count(),
        "filiais_sem_ibge": filiais_painel.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
        "usuarios_ativos": usuarios_painel.count(),
        "impressoes_sem_impressora": configuracoes.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
        "certificados_vencidos": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
        "total_registros": total_registros,
        "is_admin_master": request.user.is_superuser,
    }
    return render(request, "configuracoes/painel_sistema.html", context)


def _super_admin_payload(request):
    modelos = _modelos_backup()
    configs_fiscais = ConfiguracaoFiscal.objects.select_related("filial")
    integridade_fiscal = diagnostico_integridade_operacional()
    historico_backup = historico_backup_operacional(limite=8)
    ultimo_backup = historico_backup[0] if historico_backup else None
    periodicidade_backup = diagnostico_periodicidade_backup()
    checklist_grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    resumo_checklist = _resumo_checklist(checklist_grupos)
    perfis = PerfilUsuario.objects.select_related("usuario", "filial")
    sync_saida_alertas = EventoSincronizacao.objects.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).count()
    sync_entrada_alertas = EventoEntradaSincronizacao.objects.filter(
        status__in=[StatusEventoEntrada.RECEBIDO, StatusEventoEntrada.ERRO, StatusEventoEntrada.CONFLITO]
    ).count()
    sync_conflitos = EventoEntradaSincronizacao.objects.filter(status=StatusEventoEntrada.CONFLITO).count()
    sync_total_alertas = sync_saida_alertas + sync_entrada_alertas
    estornos_pendentes_qs = PagamentoVenda.objects.filter(status=StatusPagamento.ESTORNO_PENDENTE)
    estornos_pendentes = estornos_pendentes_qs.count()
    valor_estornos_pendentes = estornos_pendentes_qs.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    diagnosticos = [
        {
            "titulo": "Admin masters",
            "valor": User.objects.filter(is_superuser=True, is_active=True).count(),
            "descricao": "Usuários com acesso total ao painel avançado.",
            "status": "Acesso",
        },
        {
            "titulo": "Usuários sem perfil",
            "valor": User.objects.filter(perfil_supermercado__isnull=True).count(),
            "descricao": "Devem receber perfil e filial antes de operar.",
            "status": "Permissões",
        },
        {
            "titulo": "Filiais sem IBGE",
            "valor": Filial.objects.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
            "descricao": "Pendência crítica para emissão fiscal correta.",
            "status": "Fiscal",
        },
        {
            "titulo": "Certificados vencidos",
            "valor": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
            "descricao": "Certificados não configurados ou fora da validade.",
            "status": "Fiscal",
        },
        {
            "titulo": "PDV nuvem pendente",
            "valor": AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count(),
            "descricao": "Tentativas aguardando liberação do admin/gerente.",
            "status": "PDV",
        },
        {
            "titulo": "Terminais bloqueados",
            "valor": TerminalPdv.objects.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count(),
            "descricao": "Máquinas sem licença operacional ativa.",
            "status": "Licença",
        },
        {
            "titulo": "Alertas de sincronização",
            "valor": sync_total_alertas,
            "descricao": "Eventos de saída/entrada aguardando processamento, erro ou resolução de conflito.",
            "status": "Sincronização",
        },
        {
            "titulo": "Estornos eletrônicos pendentes",
            "valor": estornos_pendentes,
            "descricao": f"PIX/TEF aguardando retorno da adquirente. Valor pendente: R$ {valor_estornos_pendentes:.2f}.",
            "status": "Pagamentos",
        },
        {
            "titulo": "Integridade das evidências fiscais",
            "valor": integridade_fiscal["status"],
            "descricao": integridade_fiscal["descricao"],
            "status": "Proteção fiscal",
            "gera_alerta": integridade_fiscal["alerta"],
        },
        {
            "titulo": "Último backup operacional",
            "valor": ultimo_backup["status"] if ultimo_backup else "Pendente",
            "descricao": (
                ultimo_backup["descricao"]
                if ultimo_backup
                else "Nenhuma execução real de backup foi registrada ainda."
            ),
            "status": "Proteção de dados",
            "gera_alerta": not ultimo_backup or not ultimo_backup["sucesso"],
        },
        {
            "titulo": "Periodicidade do backup",
            "valor": periodicidade_backup["status"],
            "descricao": periodicidade_backup["descricao"],
            "status": "Proteção de dados",
            "gera_alerta": periodicidade_backup["alerta"],
        },
    ]
    secoes = [
        {
            "titulo": "Estrutura e acessos",
            "itens": [
                ("Empresas e filiais", "empresas:lista", "Cadastro multiempresa, filiais, logo, UF e IBGE."),
                ("Central de licenças", "licenciamento:central", "Planos, mensalidades, Asaas e servidores locais credenciados."),
                ("Usuários", "accounts:usuarios", "Perfis, filiais e permissões por função."),
                ("Auditoria", "auditoria:logs", "Rastreamento de ações críticas."),
            ],
        },
        {
            "titulo": "Operação sensível",
            "itens": [
                ("Terminais PDV", "configuracoes:terminais_pdv", "Licença por máquina, fiscal, TEF, balança e chave API."),
                ("Acessos PDV nuvem", "pdv:acessos_pdv_nuvem", "Aprovação de operadores fora do ambiente permitido."),
                ("Servidor local/admin", "configuracoes:servidor_local", "Implantação local, manifesto e scripts operacionais."),
                ("App PDV desktop", "configuracoes:pdv_desktop", "Instalador e pacote por terminal autorizado."),
            ],
        },
        {
            "titulo": "Fiscal, impressão e contingência",
            "itens": [
                ("Fiscal", "fiscal:documentos", "NFC-e, certificado e pendências fiscais."),
                ("Impressões", "configuracoes:impressoes", "Cupom, etiquetas, gaveta e impressoras locais."),
                ("Backup", "configuracoes:backup", "Exportação operacional e plano de restauração."),
                ("Sincronização", "empresas:sincronizacao", "Filas local/nuvem, conflitos e eventos."),
            ],
        },
        {
            "titulo": "Governança do projeto",
            "itens": [
                ("Checklist", "configuracoes:checklist", "Roadmap vivo e itens em andamento."),
                ("Formas de pagamento", "configuracoes:formas_pagamento", "Meios aceitos, TEF e contas financeiras."),
            ],
        },
    ]
    perfis_por_tipo = [
        {
            "tipo": label,
            "total": perfis.filter(tipo=valor, is_active=True).count(),
        }
        for valor, label in TipoPerfil.choices
    ]
    alertas = [
        item for item in diagnosticos
        if item["titulo"] != "Admin masters"
        and item.get("gera_alerta", bool(item["valor"]))
    ]
    pendencias_acionaveis = [
        {
            "prioridade": "Alta",
            "titulo": "Usuários sem perfil",
            "total": User.objects.filter(perfil_supermercado__isnull=True).count(),
            "acao": "Vincular perfil e filial antes de liberar acesso operacional.",
            "url_name": "accounts:usuarios",
        },
        {
            "prioridade": "Alta",
            "titulo": "Filiais sem IBGE",
            "total": Filial.objects.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
            "acao": "Corrigir UF, município e código IBGE para emissão fiscal.",
            "url_name": "empresas:lista",
        },
        {
            "prioridade": "Alta",
            "titulo": "Fiscal sem certificado válido",
            "total": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
            "acao": "Atualizar certificado A1 e validar configuração da filial.",
            "url_name": "fiscal:documentos",
        },
        {
            "prioridade": "Alta" if ultimo_backup and not ultimo_backup["sucesso"] else "Média",
            "titulo": "Último backup operacional",
            "total": 1 if not ultimo_backup or not ultimo_backup["sucesso"] else 0,
            "acao": "Abrir o histórico sanitizado, corrigir a etapa indicada e executar novamente o backup.",
            "url_name": "configuracoes:backup",
        },
        {
            "prioridade": "Alta",
            "titulo": "Periodicidade do backup",
            "total": 1 if periodicidade_backup["alerta"] else 0,
            "acao": "Revisar o agendamento e executar um backup completo até restabelecer o prazo configurado.",
            "url_name": "configuracoes:backup",
        },
        {
            "prioridade": "Alta" if integridade_fiscal["integra"] is False else "Média",
            "titulo": "Integridade das evidências fiscais",
            "total": 1 if integridade_fiscal["alerta"] else 0,
            "acao": "Abrir o backup operacional e revisar a última verificação sanitizada antes de qualquer liberação fiscal.",
            "url_name": "configuracoes:backup",
        },
        {
            "prioridade": "Média",
            "titulo": "PDV nuvem aguardando liberação",
            "total": AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count(),
            "acao": "Aprovar ou recusar tentativas de operadores em ambiente de nuvem.",
            "url_name": "pdv:acessos_pdv_nuvem",
        },
        {
            "prioridade": "Média",
            "titulo": "Terminais bloqueados/cancelados",
            "total": TerminalPdv.objects.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count(),
            "acao": "Revisar licenças por máquina e substituir terminais inválidos.",
            "url_name": "configuracoes:terminais_pdv",
        },
        {
            "prioridade": "Média",
            "titulo": "Impressões sem impressora",
            "total": ConfiguracaoImpressao.objects.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
            "acao": "Definir impressora por documento, filial e terminal quando necessário.",
            "url_name": "configuracoes:impressoes",
        },
        {
            "prioridade": "Alta" if sync_conflitos else "Média",
            "titulo": "Sincronização com alerta",
            "total": sync_total_alertas,
            "acao": "Abrir o painel de sincronização, revisar diagnóstico JSON e reprocessar filas ou resolver conflitos.",
            "url_name": "empresas:sincronizacao",
        },
        {
            "prioridade": "Alta",
            "titulo": "Estornos eletrônicos pendentes",
            "total": estornos_pendentes,
            "acao": f"Processar na adquirente e confirmar o retorno aprovado. Valor pendente: R$ {valor_estornos_pendentes:.2f}.",
            "url_name": "pdv:estornos_eletronicos",
        },
    ]
    cobertura_telas = [
        {
            "area": "Empresas e filiais",
            "modelos": "Empresa, Filial",
            "status": "Completa",
            "observacao": "Cadastro, edição, logo, UF, IBGE e modo de implantação.",
            "url_name": "empresas:lista",
        },
        {
            "area": "Usuários e perfis",
            "modelos": "User, PerfilUsuario",
            "status": "Completa",
            "observacao": "Cadastro próprio com filial, perfil e permissão operacional.",
            "url_name": "accounts:usuarios",
        },
        {
            "area": "Fiscal",
            "modelos": "ConfiguracaoFiscal, SerieFiscal, NaturezaOperacao, DocumentoFiscal, InutilizacaoNumeracaoFiscal",
            "status": "Completa",
            "observacao": "Configuração, séries e naturezas auditadas, documentos, XML, cancelamento autorizado e inutilização de faixa com protocolo SEFAZ, isolamento por empresa e paginação.",
            "url_name": "fiscal:documentos",
        },
        {
            "area": "Pagamentos",
            "modelos": "FormaPagamento",
            "status": "Completa",
            "observacao": "Formas de pagamento, TEF, PIX e conta financeira padrão.",
            "url_name": "configuracoes:formas_pagamento",
        },
        {
            "area": "Impressão e etiquetas",
            "modelos": "ConfiguracaoImpressão, ModeloEtiqueta",
            "status": "Completa",
            "observacao": "Cupom, etiquetas, impressora, gaveta, linguagem e modelos profissionais.",
            "url_name": "configuracoes:impressoes",
        },
        {
            "area": "Terminais PDV",
            "modelos": "TerminalPdv",
            "status": "Completa",
            "observacao": "Licença, chave API, fiscal por terminal, TEF, balança, pacote desktop e diagnóstico paginado por máquina com filtros e CSV.",
            "url_name": "configuracoes:terminais_pdv",
        },
        {
            "area": "Sincronização",
            "modelos": "EventoSincronizacao, EventoEntradaSincronizacao, VendaSincronizada, DocumentoFiscalSincronizado",
            "status": "Completa",
            "observacao": "Painel protegido com filtros, espelhos de vendas e documentos, detalhes, CSV, conflitos e reprocessamento auditado; CRUD direto não é permitido.",
            "url_name": "empresas:sincronizacao",
        },
        {
            "area": "Auditoria e backup",
            "modelos": "LogAuditoria, modelos exportáveis",
            "status": "Completa",
            "observacao": "Logs filtráveis, exportação CSV e backup operacional protegidos em telas próprias.",
            "url_name": "auditoria:logs",
        },
    ]
    modelos_avancados_pendentes = []
    atividade_recente = [
        {
            "data": timezone.localtime(log.criado_em).isoformat(),
            "data_label": timezone.localtime(log.criado_em).strftime("%d/%m/%Y %H:%M"),
            "modulo": log.modulo,
            "acao": log.acao,
            "usuario": log.usuario.username if log.usuario else "sistema",
            "objeto": log.objeto_tipo,
            "objeto_id": log.objeto_id,
            "descricao": log.descricao,
        }
        for log in LogAuditoria.objects.select_related("usuario").order_by("-criado_em")[:8]
    ]
    auditoria_url = reverse("auditoria:logs")
    checklist_url = reverse("configuracoes:checklist")
    investigacoes = [
        {
            "titulo": "Auditoria de configurações",
            "descricao": "Filtra ações recentes em configurações, licenças, impressões e servidor local.",
            "url": f"{auditoria_url}?{urlencode({'modulo': 'configuracoes'})}",
        },
        {
            "titulo": "Auditoria do PDV",
            "descricao": "Investiga caixa, terminal, acesso em nuvem, estorno e eventos do operador.",
            "url": f"{auditoria_url}?{urlencode({'modulo': 'pdv'})}",
        },
        {
            "titulo": "Checklist em andamento",
            "descricao": "Mostra somente itens parciais para orientar a próxima fase de desenvolvimento.",
            "url": f"{checklist_url}?{urlencode({'status': 'partial'})}",
        },
        {
            "titulo": "Checklist Super admin",
            "descricao": "Filtra o roadmap pelo tema do painel master e dependências do admin próprio.",
            "url": f"{checklist_url}?{urlencode({'q': 'Super admin'})}",
        },
        {
            "titulo": "Diagnóstico da sincronização",
            "descricao": "Abre o contrato JSON com filas, alertas, empresas por modo e próximo evento.",
            "url": request.build_absolute_uri("/empresas/sincronizacao/diagnostico.json"),
        },
    ]
    database_engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    media_root = Path(settings.MEDIA_ROOT)
    static_root = Path(settings.STATIC_ROOT) if getattr(settings, "STATIC_ROOT", None) else None
    ambiente_operacional = [
        {
            "item": "DEBUG",
            "valor": "Ligado" if settings.DEBUG else "Desligado",
            "status": "Atenção" if settings.DEBUG else "OK",
            "descricao": "Em produção deve ficar desligado.",
        },
        {
            "item": "Banco padrão",
            "valor": database_engine.rsplit(".", 1)[-1] or "não identificado",
            "status": "OK",
            "descricao": "Motor de banco configurado para a instalação atual.",
        },
        {
            "item": "Hosts permitidos",
            "valor": str(len(settings.ALLOWED_HOSTS)),
            "status": "OK" if settings.ALLOWED_HOSTS else "Atenção",
            "descricao": ", ".join(settings.ALLOWED_HOSTS) if settings.ALLOWED_HOSTS else "Nenhum host configurado.",
        },
        {
            "item": "Pasta media",
            "valor": str(media_root),
            "status": "OK" if media_root.exists() else "Atenção",
            "descricao": "Logos, imagens de produtos, certificados criptografados e anexos dependem deste caminho.",
        },
        {
            "item": "Pasta static",
            "valor": str(static_root) if static_root else "não configurada",
            "status": "OK" if static_root and static_root.exists() else "Atenção",
            "descricao": "Em produção deve apontar para a pasta coletada pelo collectstatic.",
        },
        {
            "item": "Timezone",
            "valor": settings.TIME_ZONE,
            "status": "OK",
            "descricao": "Afeta caixa, vendas, fiscal, auditoria e sincronização.",
        },
    ]
    ambiente_alertas = sum(1 for item in ambiente_operacional if item["status"] != "OK")
    pendencias_altas = sum(1 for item in pendencias_acionaveis if item["prioridade"] == "Alta" and item["total"])
    total_alertas = len(alertas) + ambiente_alertas
    penalidade = (pendencias_altas * 15) + (ambiente_alertas * 8) + (len(alertas) * 5)
    prontidao_percentual = max(0, 100 - penalidade)
    if pendencias_altas:
        prontidao_status = "Crítica"
        prontidao_descricao = "Existem pendências altas antes de considerar a operação pronta."
    elif total_alertas:
        prontidao_status = "Atenção"
        prontidao_descricao = "A operação está funcional, mas há alertas que merecem revisão."
    else:
        prontidao_status = "Pronta"
        prontidao_descricao = "Nenhuma pendência crítica detectada no diagnóstico atual."
    prontidao_operacional = {
        "percentual": prontidao_percentual,
        "status": prontidao_status,
        "descricao": prontidao_descricao,
        "pendencias_altas": pendencias_altas,
        "alertas": total_alertas,
        "ambiente_alertas": ambiente_alertas,
    }
    return {
        "gerado_em": timezone.localtime().isoformat(),
        "usuario": request.user.username,
        "diagnosticos": diagnosticos,
        "secoes": secoes,
        "modelos": modelos,
        "total_modelos": len(modelos),
        "total_registros": sum(item["total"] or 0 for item in modelos),
        "perfis_por_tipo": perfis_por_tipo,
        "resumo_checklist": resumo_checklist,
        "integridade_fiscal": integridade_fiscal,
        "historico_backup": historico_backup,
        "periodicidade_backup": periodicidade_backup,
        "alertas": alertas,
        "pendencias_acionaveis": pendencias_acionaveis,
        "cobertura_telas": cobertura_telas,
        "modelos_avancados_pendentes": modelos_avancados_pendentes,
        "atividade_recente": atividade_recente,
        "investigacoes": investigacoes,
        "ambiente_operacional": ambiente_operacional,
        "prontidao_operacional": prontidao_operacional,
        "links": {
            "super_admin": request.build_absolute_uri("/configuracoes/super-admin/"),
            "diagnostico_json": request.build_absolute_uri("/configuracoes/super-admin/diagnostico.json"),
            "diagnostico_csv": request.build_absolute_uri("/configuracoes/super-admin/diagnostico.csv"),
            "sincronizacao_diagnostico_json": request.build_absolute_uri("/empresas/sincronizacao/diagnostico.json"),
            "checklist": request.build_absolute_uri("/configuracoes/checklist/"),
            "auditoria": request.build_absolute_uri("/auditoria/"),
        },
    }


@login_required
@role_required(*SISTEMA)
def super_admin(request):
    _exigir_admin_master(request.user)
    context = _super_admin_payload(request)
    context["modelos_pagina"] = Paginator(context["modelos"], 25).get_page(
        request.GET.get("inventory_page")
    )
    return render(request, "configuracoes/super_admin.html", context)


@login_required
@role_required(*SISTEMA)
def super_admin_diagnostico(request):
    _exigir_admin_master(request.user)
    return JsonResponse(_super_admin_payload(request))


@login_required
@role_required(*SISTEMA)
def super_admin_diagnostico_csv(request):
    _exigir_admin_master(request.user)
    payload = _super_admin_payload(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="super_admin_diagnostico.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Seção", "Item", "Status/Prioridade", "Total/Valor", "Descrição/Ação"])
    for item in payload["diagnosticos"]:
        writer.writerow(["Diagnostico", item["titulo"], item["status"], item["valor"], item["descricao"]])
    for item in payload["pendencias_acionaveis"]:
        writer.writerow(["Pendencia", item["titulo"], item["prioridade"], item["total"], item["acao"]])
    for item in payload["cobertura_telas"]:
        writer.writerow(["Cobertura", item["area"], item["status"], item["modelos"], item["observacao"]])
    for item in payload["modelos_avancados_pendentes"]:
        writer.writerow(["Modelo avancado", item["area"], item["prioridade"], item["status"], item["acao"]])
    for item in payload["atividade_recente"]:
        writer.writerow(["Atividade", item["acao"], item["modulo"], item["data_label"], item["descricao"]])
    for item in payload["investigacoes"]:
        writer.writerow(["Investigacao", item["titulo"], "Link", item["url"], item["descricao"]])
    for item in payload["ambiente_operacional"]:
        writer.writerow(["Ambiente", item["item"], item["status"], item["valor"], item["descricao"]])
    prontidao = payload["prontidao_operacional"]
    writer.writerow(["Prontidao", prontidao["status"], prontidao["percentual"], prontidao["alertas"], prontidao["descricao"]])
    for item in payload["perfis_por_tipo"]:
        writer.writerow(["Perfil", item["tipo"], "Ativo", item["total"], "Usuários ativos por perfil"])
    return response


def _modelo_super_admin(app_label, model_name):
    ignorar = {"Permission", "ContentType", "Session", "LogEntry"}
    modelo = apps.get_model(app_label, model_name)
    if not modelo or modelo._meta.object_name in ignorar:
        raise Http404("Modelo indisponivel para inspecao.")
    return modelo


def _campos_inspecao_modelo(modelo):
    campos = []
    for campo in modelo._meta.fields:
        if campo.get_internal_type() == "BinaryField":
            continue
        campos.append(campo)
        if len(campos) >= 8:
            break
    return campos


def _valor_inspecao(objeto, campo):
    nome = campo.name.lower()
    if any(chave in nome for chave in ["password", "senha", "token", "secret", "chave", "hash"]):
        return "••••"
    valor = getattr(objeto, campo.name, None)
    if valor in (None, ""):
        return "-"
    if hasattr(valor, "name") and campo.get_internal_type() == "FileField":
        return valor.name or "-"
    texto = str(valor)
    return f"{texto[:117]}..." if len(texto) > 120 else texto


@login_required
@role_required(*SISTEMA)
def super_admin_modelo(request, app_label, model_name):
    _exigir_admin_master(request.user)
    modelo = _modelo_super_admin(app_label, model_name)
    termo = (request.GET.get("q") or "").strip()
    queryset = modelo._default_manager.all()
    campos_busca = [
        campo.name
        for campo in modelo._meta.fields
        if campo.get_internal_type() in {"CharField", "TextField", "EmailField", "SlugField", "URLField"}
    ]
    if termo and campos_busca:
        filtro = Q()
        for campo in campos_busca:
            filtro |= Q(**{f"{campo}__icontains": termo})
        queryset = queryset.filter(filtro)
    if modelo._meta.pk:
        queryset = queryset.order_by(modelo._meta.pk.name)
    campos = _campos_inspecao_modelo(modelo)
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    linhas = [
        {
            "pk": objeto.pk,
            "valores": [_valor_inspecao(objeto, campo) for campo in campos],
        }
        for objeto in page_obj.object_list
    ]
    context = {
        "modelo": modelo,
        "modelo_nome": str(modelo._meta.verbose_name_plural).capitalize(),
        "modelo_tecnico": modelo._meta.object_name,
        "modelo_app": modelo._meta.app_label,
        "app_label": app_label,
        "model_name": model_name,
        "termo": termo,
        "campos": campos,
        "linhas": linhas,
        "page_obj": page_obj,
        "total": paginator.count,
        "campos_busca": campos_busca,
    }
    return render(request, "configuracoes/super_admin_modelo.html", context)



@login_required
@role_required(*SISTEMA)
def checklist_projeto(request):
    _exigir_admin_master(request.user)
    grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    filtros = {
        "q": (request.GET.get("q") or "").strip(),
        "status": (request.GET.get("status") or "").strip(),
        "grupo": (request.GET.get("grupo") or "").strip(),
        "trilha": (request.GET.get("trilha") or "").strip(),
        "prioridade": (request.GET.get("prioridade") or "").strip(),
        "dependencia": (request.GET.get("dependencia") or "").strip(),
    }
    grupos_filtrados = _filtrar_checklist(
        grupos,
        termo=filtros["q"],
        status=filtros["status"],
        grupo_titulo=filtros["grupo"],
        trilha=filtros["trilha"],
        prioridade=filtros["prioridade"],
        dependencia=filtros["dependencia"],
    ) if any(filtros.values()) else [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in grupos
    ]
    mapa_trilhas = _mapa_trilhas_roadmap(grupos)
    resumo = _resumo_checklist(grupos)
    resumo["diferenca_ponderada"] = max(0, resumo["percentual_ponderado"] - resumo["percentual"])
    resumo_filtrado = _resumo_checklist(grupos_filtrados)
    context = {
        "grupos": grupos_filtrados,
        "resumo": resumo,
        "resumo_filtrado": resumo_filtrado,
        "mapa_trilhas": mapa_trilhas,
        "proximas_etapas": _proximas_etapas_checklist(grupos_filtrados if any(filtros.values()) else grupos),
        "filtros": filtros,
        "grupos_opcoes": [grupo["titulo"] for grupo in grupos],
        "trilhas_opcoes": [item["trilha"] for item in mapa_trilhas],
        "prioridades_opcoes": ["Alta", "Média"],
        "status_opcoes": [
            ("", "Todos os status"),
            ("done", "Concluído"),
            ("partial", "Em andamento"),
            ("todo", "Pendente"),
        ],
        "documentos": DOCUMENTOS_PROJETO,
    }
    return render(request, "configuracoes/checklist.html", context)


@login_required
@role_required(*SISTEMA)
def checklist_projeto_csv(request):
    _exigir_admin_master(request.user)
    grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    grupos = _filtrar_checklist(
        grupos,
        termo=request.GET.get("q"),
        status=request.GET.get("status"),
        grupo_titulo=request.GET.get("grupo"),
        trilha=request.GET.get("trilha"),
        prioridade=request.GET.get("prioridade"),
        dependencia=request.GET.get("dependencia"),
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="checklist_projeto.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Grupo", "Item", "Status", "Dependência", "Trilha", "Prioridade", "Próxima ação", "Descrição"])
    status_labels = {"done": "Concluído", "partial": "Em andamento", "todo": "Pendente"}
    for grupo in grupos:
        for titulo, status, descricao in grupo["itens"]:
            classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao) if status == "partial" else {"trilha": "", "prioridade": "", "acao": ""}
            dependencia = _classificar_dependencia_roadmap(titulo, descricao)["dependencia"] if status == "partial" else ""
            writer.writerow([grupo["titulo"], titulo, status_labels.get(status, status), dependencia, classificacao["trilha"], classificacao["prioridade"], classificacao["acao"], descricao])
    return response


def _pdv_desktop_readiness_payload(instalador, terminais_qs):
    total_terminais = terminais_qs.count()
    ativos = terminais_qs.filter(ativo=True).count()
    liberados = terminais_qs.filter(status_licenca=StatusLicencaTerminal.LIBERADA, ativo=True).count()
    pendentes = terminais_qs.filter(status_licenca=StatusLicencaTerminal.PENDENTE).count()
    bloqueados = terminais_qs.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count()
    sem_tef = terminais_qs.filter(ativo=True, provedor_tef="").count()
    sem_fiscal = terminais_qs.filter(ativo=True, emite_documento_fiscal=False).count()
    com_balanca = terminais_qs.filter(ativo=True, usa_balanca=True).count()
    pilotos = terminais_qs.filter(ativo=True, canal_atualizacao=CanalAtualizacaoPdv.PILOTO).count()
    atualizacoes_congeladas = terminais_qs.filter(ativo=True, bloquear_atualizacoes=True).count()
    build_msi_script = settings.BASE_DIR / "desktop_pdv" / "build_msi.ps1"
    build_msi_template = settings.BASE_DIR / "desktop_pdv" / "installer" / "Product.wxs.template"
    build_msi_preparado = build_msi_script.is_file() and build_msi_template.is_file()
    bloqueios = []
    recomendacoes = []
    if not instalador["disponivel"]:
        bloqueios.extend(instalador["problemas"] or ["Publicar o instalador Windows assinado antes de distribuir o app PDV desktop."])
    if not build_msi_preparado:
        bloqueios.append("Preparar script e template reproduziveis para gerar o instalador MSI.")
    if not total_terminais:
        bloqueios.append("Cadastrar ao menos um terminal PDV antes da instalacao.")
    if ativos and not liberados:
        bloqueios.append("Liberar a licença de pelo menos um terminal ativo para baixar o pacote de ativação.")
    if pendentes:
        recomendacoes.append(f"Revisar {pendentes} terminal(is) com licença pendente.")
    if bloqueados:
        recomendacoes.append(f"Manter {bloqueados} terminal(is) bloqueado(s)/cancelado(s) fora da distribuicao.")
    if sem_tef:
        recomendacoes.append(f"{sem_tef} terminal(is) ativo(s) sem provedor TEF configurado usarao somente fallback/manual.")
    if sem_fiscal:
        recomendacoes.append(f"{sem_fiscal} terminal(is) ativo(s) com fiscal automatico desligado.")
    if atualizacoes_congeladas:
        recomendacoes.append(f"{atualizacoes_congeladas} terminal(is) com atualizacoes opcionais congeladas pelo admin master.")
    if bloqueios:
        status = "Bloqueada"
        percentual = 45
        proximo_passo = bloqueios[0]
    elif recomendacoes:
        status = "Pronta com ressalvas"
        percentual = 85
        proximo_passo = recomendacoes[0]
    else:
        status = "Pronta"
        percentual = 100
        proximo_passo = "Distribuicao pronta para terminais licenciados."
    return {
        "contrato": "pdv_desktop_readiness_v1",
        "status": status,
        "percentual": percentual,
        "proximo_passo": proximo_passo,
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "instalador": {
            "disponivel": instalador["disponivel"],
            "nome": instalador["nome"],
            "sha256": instalador["sha256"],
            "build_msi_preparado": build_msi_preparado,
            "assinatura_obrigatoria_producao": True,
        },
        "terminais": {
            "total": total_terminais,
            "ativos": ativos,
            "licencas_liberadas": liberados,
            "licencas_pendentes": pendentes,
            "bloqueados_cancelados": bloqueados,
            "sem_tef": sem_tef,
            "sem_fiscal_automatico": sem_fiscal,
            "com_balanca": com_balanca,
            "canal_piloto": pilotos,
            "atualizacoes_congeladas": atualizacoes_congeladas,
        },
    }


@login_required
@role_required(*SISTEMA)
def pdv_desktop(request):
    _exigir_admin_master(request.user)
    instalador = _instalador_pdv_desktop()
    terminais = _terminais_visiveis(request.user).order_by("filial__nome", "nome")
    total_terminais = terminais.count()
    licencas_liberadas = terminais.filter(status_licenca=StatusLicencaTerminal.LIBERADA, ativo=True).count()
    licencas_pendentes = terminais.filter(status_licenca=StatusLicencaTerminal.PENDENTE).count()
    licencas_bloqueadas = terminais.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count()
    eventos_dispositivo = EventoDispositivoTerminal.objects.select_related("terminal", "terminal__filial").order_by("-recebido_em")
    resumo_eventos_dispositivo = eventos_dispositivo.values("tipo", "status").annotate(total=Count("id")).order_by("tipo", "status")
    prontidao_desktop = _pdv_desktop_readiness_payload(instalador, terminais)
    context = {
        "terminais": terminais,
        "total_terminais": total_terminais,
        "licencas_liberadas": licencas_liberadas,
        "licencas_pendentes": licencas_pendentes,
        "licencas_bloqueadas": licencas_bloqueadas,
        "eventos_dispositivo": eventos_dispositivo[:50],
        "total_eventos_dispositivo": eventos_dispositivo.count(),
        "resumo_eventos_dispositivo": resumo_eventos_dispositivo,
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "instalador": instalador,
        "prontidao_desktop": prontidao_desktop,
        "artefatos": [
            {
                "nome": "Windows x64",
                "status": "Empacotamento pronto",
                "descricao": "PyInstaller gera o executavel e WiX v4 monta MSI por máquina com upgrade, atalhos, desinstalação, SHA-256 e assinatura opcional.",
            },
            {
                "nome": "Bridge local",
                "status": "Contrato pronto",
                "descricao": "Conecta impressora, gaveta, TEF, balanca e servidor local, mantendo a chave do terminal protegida pelo DPAPI do Windows.",
            },
            {
                "nome": "Atualização controlada",
                "status": "Canal pronto",
                "descricao": "Terminal licenciado baixa o pacote publicado, valida SHA-256 e mantém a instalacao manual.",
            },
        ],
    }
    return render(request, "configuracoes/pdv_desktop.html", context)


def _pdv_desktop_manifest_payload(request):
    terminais = _terminais_visiveis(request.user).order_by("filial__nome", "nome")
    instalador = _instalador_pdv_desktop()
    prontidao_desktop = _pdv_desktop_readiness_payload(instalador, terminais)
    return {
        "status": "ok",
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "distribuicao": "erp",
        "politica_atualizacao": {
            "contrato": "pdv_update_rollout_v1",
            "canal_versao": settings.PDV_DESKTOP_RELEASE_CHANNEL,
            "instalacao_automatica": False,
            "versao_minima_sobrepoe_congelamento": True,
        },
        "licenciamento": {
            "modelo": "por_terminal",
            "download_requer_admin_master": True,
            "ativacao_requer_terminal_autorizado": True,
            "observacao": "Cada máquina de caixa deve ser liberada pelo admin master antes de baixar/ativar o app desktop.",
        },
        "prontidao": prontidao_desktop,
        "contratos": {
            "tef": "pdv_tef_v1",
            "impressao": "pdv_print_v1",
            "sincronizacao": "pdv_sync_v1",
            "fila_eventos_dispositivo": "pdv_device_event_queue_v1",
            "instalador_windows": "pdv_windows_installer_v1",
            "credencial_local": "pdv_local_secret_v1",
            "instancia_local": "pdv_single_instance_v1",
        },
        "recursos": {
            "tef_integrado": True,
            "impressao_desktop": True,
            "gaveta_opcional": True,
            "balanca_local": True,
            "fiscal_por_terminal": True,
            "modo_offline": True,
            "credencial_terminal_dpapi": True,
            "configuracao_tef_dpapi": True,
            "instancia_unica_por_terminal": True,
            "eventos_dispositivo_idempotentes": True,
            "compactacao_preserva_pendentes": True,
            "sincronizacao_periodica_eventos": True,
        },
        "artefatos": {
            "windows_x64": {
                "status": "disponivel" if instalador["disponivel"] else "aguardando_build",
                "nome": instalador["nome"],
                "url": request.build_absolute_uri("/configuracoes/pdv-desktop/download/windows/") if instalador["disponivel"] else "",
                "tamanho_bytes": instalador["tamanho"],
                "sha256": instalador["sha256"],
                "integridade_valida": instalador["integridade_valida"],
                "versao_valida": instalador["versao_valida"],
                "assinatura_valida": instalador["assinatura_valida"],
                "assinatura_exigida": instalador["assinatura_exigida"],
                "problemas": instalador["problemas"],
            }
        },
        "terminais": [
            {
                "identificador": str(terminal.identificador),
                "nome": terminal.nome,
                "filial": terminal.filial.nome,
                "empresa": str(terminal.filial.empresa),
                "ativo": terminal.ativo,
                "licenca": {
                    "status": terminal.status_licenca,
                    "liberada": terminal.licenca_liberada,
                    "liberada_em": terminal.licenca_liberada_em.isoformat() if terminal.licenca_liberada_em else None,
                },
                "emite_documento_fiscal": terminal.emite_documento_fiscal,
                "permite_modo_offline": terminal.permite_modo_offline,
                "atualizacao": {
                    "canal": terminal.canal_atualizacao,
                    "bloqueada_pelo_admin": terminal.bloquear_atualizacoes,
                },
                "provedor_tef": terminal.provedor_tef,
                "modo_integracao_tef": terminal.modo_integracao_tef,
                "balanca": terminal.balanca_configuracao(),
                "chave_api_prefixo": terminal.chave_api_prefixo,
                "bootstrap_url": request.build_absolute_uri("/pdv/api/terminal/bootstrap/"),
            }
            for terminal in terminais
        ],
    }


@login_required
@role_required(*SISTEMA)
def pdv_desktop_manifest(request):
    _exigir_admin_master(request.user)
    return JsonResponse(_pdv_desktop_manifest_payload(request))


@login_required
@role_required(*SISTEMA)
def pdv_desktop_download_windows(request):
    _exigir_admin_master(request.user)
    instalador = artefato_pdv_desktop()
    if not instalador["publicavel"]:
        raise Http404("Instalador do PDV desktop indisponivel ou reprovado na validacao.")
    caminho = instalador["caminho"]
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="DOWNLOAD_PDV_DESKTOP",
        descricao=f"Download do instalador PDV desktop {caminho.name}.",
        objeto_tipo="PdvDesktopInstaller",
        objeto_id=PDV_DESKTOP_VERSAO_PLANEJADA,
        ip=request.META.get("REMOTE_ADDR"),
    )
    return FileResponse(caminho.open("rb"), as_attachment=True, filename=caminho.name)


def _documento_json_com_hash(payload, nome):
    conteudo = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    digest = hashlib.sha256(conteudo).hexdigest()
    return conteudo, f"{digest}  {nome}\n".encode("ascii")


@login_required
@role_required(*SISTEMA)
def servidor_local_evidencias(request):
    _exigir_admin_master(request.user)
    exigir_midia_offline = request.GET.get("modo") == "offline"
    dossie = gerar_dossie_implantacao(
        perfil="servidor-local",
        producao=True,
        exigir_midia_offline=exigir_midia_offline,
    )
    dossie_nome = "dossie_implantacao.json"
    dossie_bytes, dossie_hash = _documento_json_com_hash(dossie, dossie_nome)
    http_resultado = {
        "contrato": "local_http_health_v1",
        "pronto": True,
        "status_http": 200,
        "erro_tipo": "",
        "url_exposta": False,
    }
    pos_implantacao = diagnostico_pos_implantacao_local(http_resultado=http_resultado)
    with TemporaryDirectory() as temporario:
        caminho_dossie = Path(temporario) / dossie_nome
        caminho_dossie.write_bytes(dossie_bytes)
        caminho_dossie.with_name(dossie_nome + ".sha256").write_bytes(dossie_hash)
        evidencia = gerar_evidencia_aceite(
            caminho_dossie,
            pos_implantacao=pos_implantacao,
        )
    evidencia_nome = "evidencia_aceite.json"
    evidencia_bytes, evidencia_hash = _documento_json_com_hash(evidencia, evidencia_nome)
    leia_me = (
        "PACOTE DE EVIDENCIAS DE IMPLANTACAO\r\n"
        f"Status do aceite: {'LIBERAVEL' if evidencia['liberavel'] else 'BLOQUEADO'}\r\n"
        "Valide os arquivos pelos respectivos SHA-256 e arquive-os com o termo assinado.\r\n"
    ).encode("utf-8")
    memoria = BytesIO()
    with zipfile.ZipFile(memoria, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr(dossie_nome, dossie_bytes)
        pacote.writestr(dossie_nome + ".sha256", dossie_hash)
        pacote.writestr(evidencia_nome, evidencia_bytes)
        pacote.writestr(evidencia_nome + ".sha256", evidencia_hash)
        pacote.writestr("LEIA-ME.txt", leia_me)
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="DOWNLOAD_EVIDENCIAS_IMPLANTACAO",
        descricao=(
            "Pacote técnico de implantação gerado pela Central do servidor local. "
            f"Mídia offline {'obrigatória' if exigir_midia_offline else 'opcional'}. "
            f"Aceite {'liberável' if evidencia['liberavel'] else 'bloqueado'}."
        ),
        objeto_tipo="LocalInstallationEvidence",
        objeto_id=settings.LOCAL_SERVER_VERSION,
        ip=request.META.get("REMOTE_ADDR"),
    )
    resposta = HttpResponse(memoria.getvalue(), content_type="application/zip")
    resposta["Content-Disposition"] = 'attachment; filename="evidencias_implantacao.zip"'
    return resposta


def _configuracao_gaveta_terminal(filial):
    impressao = configuracao_impressao_para(filial, TipoDocumentoImpressao.CUPOM_NAO_FISCAL)
    return {
        "contrato": "pdv_cash_drawer_v1",
        "opcional": True,
        "habilitada": bool(impressao and impressao.gaveta_automatica),
        "impressora_padrao": impressao.impressora_padrao if impressao else "",
        "abrir_em_dinheiro": bool(impressao and impressao.abrir_gaveta_em_dinheiro),
        "abrir_em_movimento_caixa": bool(impressao and impressao.abrir_gaveta_em_movimento_caixa),
        "bloqueia_venda_se_indisponivel": False,
    }


def _pdv_desktop_terminal_payload(request, terminal):
    return {
        "status": "ok",
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "terminal": {
            "identificador": str(terminal.identificador),
            "nome": terminal.nome,
            "descricao": terminal.descricao,
            "ativo": terminal.ativo,
            "chave_api_prefixo": terminal.chave_api_prefixo,
        },
        "licenciamento": {
            "modelo": "por_terminal",
            "download_requer_admin_master": True,
            "terminal_autorizado": terminal.licenca_liberada,
            "status": terminal.status_licenca,
            "observacao": "Pacote destinado apenas a máquina licenciada e autorizada pelo admin master.",
        },
        "atualizacao": {
            "contrato": "pdv_update_rollout_v1",
            "canal_terminal": terminal.canal_atualizacao,
            "canal_versao": settings.PDV_DESKTOP_RELEASE_CHANNEL,
            "bloqueada_pelo_admin": terminal.bloquear_atualizacoes,
            "instalacao_automatica": False,
            "versao_minima_sobrepoe_congelamento": True,
        },        "filial": {
            "id": terminal.filial_id,
            "nome": terminal.filial.nome,
            "empresa": str(terminal.filial.empresa),
        },
        "servidor": {
            "base_url": request.build_absolute_uri("/").rstrip("/"),
            "bootstrap_url": request.build_absolute_uri("/pdv/api/terminal/bootstrap/"),
            "manifest_url": request.build_absolute_uri("/configuracoes/pdv-desktop/manifest.json"),
        },
        "interface": {
            "modo": "webview_compartilhada",
            "pdv_url": request.build_absolute_uri("/pdv/"),
            "mesmo_layout_do_pdv_web": True,
            "atalhos_compartilhados": True,
        },
        "fiscal": {
            "emissao_automatica": terminal.emite_documento_fiscal,
            "observacao": "Quando falso, este terminal não tenta preparar NFC-e automaticamente.",
        },
        "tef": {
            "contrato": "pdv_tef_v1",
            "provedor": terminal.provedor_tef,
            "modo_integracao": terminal.modo_integracao_tef,
            "tipos_pagamento": ["CREDITO", "DEBITO", "PIX", "VALE_ALIMENTACAO", "VALE_REFEICAO"],
            "retorno_esperado": ["status", "transacao_externa_id", "nsu", "codigo_autorizacao", "mensagem_processadora"],
        },
        "dispositivos": {
            "impressora": {"contrato": "pdv_print_v1", "config_url": request.build_absolute_uri("/configuracoes/impressoes/desktop.json")},
            "gaveta": _configuracao_gaveta_terminal(terminal.filial),
            "balanca": terminal.balanca_configuracao(),
        },
        "sincronizacao": {
            "contrato": "pdv_sync_v1",
            "modo_offline_permitido": terminal.permite_modo_offline,
        },
    }


def _servidor_local_prontidao(base_dir, scripts, pendencias, modos):
    return diagnostico_prontidao_servidor_local(
        base_dir=base_dir,
        scripts=scripts,
        pendencias=pendencias,
        modos=modos,
    )

def _servidor_local_payload(request):
    empresas = Empresa.objects.prefetch_related("filiais").order_by("nome_fantasia")
    pacote_servidor = artefato_servidor_local()
    pacote_offline = artefato_servidor_offline()
    modos = {
        modo: empresas.filter(modo_implantacao=modo).count()
        for modo in ModoImplantacao.values
    }
    servico_windows = {
        "contrato": "local_windows_service_v1",
        "nome": "DeigoVarejoServidorLocal",
        "status": "instalador_preparado",
        "banco_recomendado": "PostgreSQL",
        "ferramentas_banco": ["pg_dump", "pg_restore"],
        "sqlite_uso": "Somente desenvolvimento, teste ou instalação explicitamente simplificada.",
        "tipo": "Windows Service via WinSW",
        "usuario_recomendado": r"NT SERVICE\DeigoVarejoServidorLocal (conta virtual sem senha)",
        "diretorio_dados": r"%ProgramData%\DeigoVarejo\Dados",
        "permissoes": "Leitura e execução no código; modificação somente nos diretórios de dados e do wrapper.",
        "comando_producao": r".\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 config.wsgi:application",
        "instalador": "scripts/install_local_server_service.ps1",
        "desinstalador": "scripts/uninstall_local_server_service.ps1",
        "diagnostico": "scripts/test_local_server_service.ps1",
        "template": "server_local/windows/DeigoVarejoServidorLocal.xml.template",
        "wrapper": "WinSW fornecido pelo administrador e validado por SHA-256 antes da instalacao",
        "fallback_operacional": "scripts/register_local_server_task.ps1 -Bind 0.0.0.0 -Port 8000 -AtStartup",
        "healthcheck": "/login/",
        "restart": "Início automático com o Windows e reinicio 10 segundos após falha",
        "logs": [r"%ProgramData%\DeigoVarejo\ServidorLocal\logs", "logs/django.log"],
        "observacao": "Scripts e contrato do servico estao preparados; a conclusão depende de instalar o WinSW verificado e homologar em uma maquina Windows da loja.",
    }
    pendencias = [
        {
            "titulo": "Serviço Windows/Linux",
            "status": "iniciado",
            "descricao": "Servico Windows preparado com WinSW, Waitress, inicio automático, reinicio em falha, logs rotativos, healthcheck e scripts de instalacao, diagnóstico e remocao. O instalador configura a conta virtual NT SERVICE\\DeigoVarejoServidorLocal sem senha, separa dados em ProgramData e aplica ACL de leitura no código e modificação somente nas areas gravaveis. A tarefa agendada permanece como fallback; falta homologar o servico em Windows de loja.",
        },
        {
            "titulo": "Backup local automático",
            "status": "iniciado",
            "descricao": "O backup erp_local_backup_v2 descobre banco, mídia e logs pela configuração efetiva do Django ou pelo XML WinSW, gera dump lógico, snapshot SQLite consistente, manifesto, SHA-256 e criptografia AES-256 opcional. Também valida a cadeia fiscal contra a âncora externa anterior, bloqueia regressões, inclui a âncora no ZIP e registra o estado sanitizado no alerta exclusivo do Master. A cópia secundária opcional permanece desligada, exige pacote criptografado, confirmação de NAS/rede/disco externo, SHA-256 antes da promoção e retenção própria. A tarefa diária valida as fontes antes do registro e executa como SYSTEM, sem depender de usuário conectado.",
        },
        {
            "titulo": "Atualização controlada",
            "status": "iniciado",
            "descricao": "Empacotamento, publicação atômica e atualizador controlado preparados. O atualizador valida ZIP e manifesto, limita a extracao, preserva .env e dados, cria snapshot do código e SQLite, aplica dependencias/migrations/estaticos com o servico parado, exige healthcheck e executa rollback automático em falha. PostgreSQL permanece em procedimento assistido com DBA; falta homologar em maquina Windows limpa.",
        },
        {
            "titulo": "Sincronização opcional",
            "status": "iniciado",
            "descricao": "Reusar filas existentes para lojas híbridas, com scripts/register_sync_task.ps1 agendando a rotina recorrente e mantendo operação local quando a internet cair.",
        },
    ]
    scripts = {
        "subir_servidor": "scripts/run_local_server.ps1",
        "registrar_servidor": "scripts/register_local_server_task.ps1",
        "instalar_servico": "scripts/install_local_server_service.ps1",
        "empacotar_servidor": "scripts/package_local_server.ps1",
        "empacotar_servidor_offline": "scripts/package_detech_server_offline.ps1",
        "publicar_servidor_offline": "scripts/publish_detech_server_offline.ps1",
        "publicar_servidor": "scripts/publish_local_server.ps1",
        "atualizar_servidor": "scripts/update_local_server.ps1",
        "diagnosticar_servico": "scripts/test_local_server_service.ps1",
        "remover_servico": "scripts/uninstall_local_server_service.ps1",
        "template_servico": "server_local/windows/DeigoVarejoServidorLocal.xml.template",
        "backup_local": "scripts/backup_local.ps1",
        "registrar_resultado_backup": "apps/configuracoes/management/commands/registrar_resultado_backup_operacional.py",
        "verificar_evidencias_fiscais": "apps/fiscal/management/commands/verificar_integridade_evidencias_fiscais.py",
        "restaurar_backup": "scripts/restore_local_backup.ps1",
        "registrar_backup": "scripts/register_backup_task.ps1",
        "registrar_sincronizacao": "scripts/register_sync_task.ps1",
        "registrar_manutencao_validade": "scripts/register_inventory_expiry_maintenance_task.ps1",
        "verificar_fluxo_estoque_piloto": "apps/estoque/management/commands/verificar_fluxo_estoque_piloto.py",
        "guia": "docs/IMPLANTACAO_SERVIDOR_LOCAL.md",
        "manual_instalacao": "docs/MANUAL_INSTALACAO_SUPERMERCADO.md",
        "backup_criptografia_env": "BACKUP_ENCRYPTION_PASSPHRASE",
        "backup_criptografia_flag": "-RemoverOriginalCriptografado",
        "backup_validacao_flag": "-ValidarSomente",
        "restauracao_ensaio_flag": "-EnsaiarIsolado",
        "restauracao_ensaio_postgres_db_env": "RESTORE_REHEARSAL_POSTGRES_DB",
        "restauracao_ensaio_postgres_host_env": "RESTORE_REHEARSAL_POSTGRES_HOST",
        "restauracao_ensaio_postgres_user_env": "RESTORE_REHEARSAL_POSTGRES_USER",
        "restauracao_ensaio_postgres_password_env": "RESTORE_REHEARSAL_POSTGRES_PASSWORD",
        "restauracao_ensaio_postgres_confirmacao_flag": "-ConfirmarBancoPostgresTemporario",
        "backup_destino_env": "LOCAL_BACKUP_DIR",
        "backup_destino_secundario_env": "LOCAL_BACKUP_SECONDARY_DIR",
        "backup_destino_secundario_confirmacao_env": "LOCAL_BACKUP_SECONDARY_CONFIRMED",
        "backup_idade_maxima_env": "LOCAL_BACKUP_MAX_AGE_HOURS",
        "backup_destino_secundario_confirmacao_flag": "-ConfirmarDestinoSecundario",
        "backup_conta_tarefa": "SYSTEM",
    }
    prontidao = _servidor_local_prontidao(Path(settings.BASE_DIR), scripts, pendencias, modos)
    return {
        "status": "ok",
        "contrato": "erp_local_admin_v1",
        "recomendacao": "Servidor local administrativo com acesso via navegador; app desktop completo apenas para PDV.",
        "prontidao": prontidao,
        "distribuicao": {
            "contrato": "local_server_distribution_v1",
            "status": "disponivel" if pacote_servidor["publicavel"] else "indisponivel",
            "versao": settings.LOCAL_SERVER_VERSION,
            "nome": pacote_servidor["nome"],
            "tamanho_bytes": pacote_servidor["tamanho"],
            "sha256": pacote_servidor["sha256"],
            "integridade_valida": pacote_servidor["integridade_valida"],
            "tamanho_valido": pacote_servidor["tamanho_valido"],
            "origem_rastreavel": pacote_servidor["origem_rastreavel"],
            "sem_dados_cliente": pacote_servidor["sem_dados_cliente"],
            "conteudo_valido": pacote_servidor["conteudo_valido"],
            "diagnostico_conteudo": pacote_servidor["diagnostico_conteudo"],
            "commit_assinado_exigido": pacote_servidor["assinatura_commit_exigida"],
            "commit_assinado_confirmado": pacote_servidor["assinatura_commit_confirmada"],
            "url": request.build_absolute_uri("/configuracoes/servidor-local/download/") if pacote_servidor["publicavel"] else "",
            "problemas": pacote_servidor["problemas"],
        },
        "distribuicao_offline": {
            "status": "disponivel" if pacote_offline["publicavel"] else "indisponivel",
            "versao": settings.LOCAL_SERVER_VERSION,
            "nome": pacote_offline["nome"],
            "tamanho_bytes": pacote_offline["tamanho"],
            "sha256": pacote_offline["sha256"],
            "contrato_validacao": pacote_offline["contrato"],
            "contrato_publicacao": pacote_offline["contrato_publicacao"],
            "checksum_encontrado": pacote_offline["checksum_encontrado"],
            "checksum_hash_valido": pacote_offline["checksum_hash_valido"],
            "checksum_nome_vinculado": pacote_offline["checksum_nome_vinculado"],
            "publicacao_valida": pacote_offline["publicacao_valida"],
            "integridade_valida": pacote_offline["integridade_valida"],
            "componentes_obrigatorios_validos": pacote_offline["componentes_obrigatorios_validos"],
            "conteudo_servidor_valido": pacote_offline["conteudo_servidor_valido"],
            "wheelhouse_valido": pacote_offline["wheelhouse_valido"],
            "validacao_no_empacotamento": True,
            "promocao_somente_apos_validacao": True,
            "preserva_artefato_anterior_em_falha": True,
            "empacotador": "scripts/package_detech_server_offline.ps1",
            "publicador": "scripts/publish_detech_server_offline.ps1",
            "publicacao_revalida_origem_e_copia": True,
            "publicacao_checksum_vinculado": True,
            "publicacao_rollback_automatico": True,
            "publicacao_preserva_anterior_em_falha": True,
            "url": request.build_absolute_uri("/configuracoes/servidor-local/offline/download/") if pacote_offline["publicavel"] else "",
            "problemas": pacote_offline["problemas"],
        },
        "atualizacao_local": {
            "contrato_validacao": "local_server_update_validation_v1",
            "contrato_rollback": "local_server_rollback_v1",
            "contrato_historico": "local_server_update_history_v1",
            "script": "scripts/update_local_server.ps1",
            "validar_comando": r".\scripts\update_local_server.ps1 -PackagePath pacote.zip -ValidarSomente",
            "janela_manutencao": True,
            "healthcheck_obrigatorio": True,
            "rollback_codigo": True,
            "rollback_sqlite": True,
            "preserva_env_dados": True,
            "postgresql": "Procedimento assistido com backup nativo e DBA.",
        },
        "restauracao_local": {
            "contrato_validacao": "local_restore_validation_v1",
            "contrato_historico": "local_restore_history_v1",
            "script": "scripts/restore_local_backup.ps1",
            "validar_comando": r".\scripts\restore_local_backup.ps1 -BackupPath backup.zip -ValidarSomente",
            "ensaio_contrato": "local_restore_rehearsal_v1",
            "ensaio_comando": r".\scripts\restore_local_backup.ps1 -BackupPath backup.zip -EnsaiarIsolado",
            "ensaio_sqlite_automatico": True,
            "ensaio_postgresql_automatico_em_banco_preparado": True,
            "ensaio_postgresql_prefixo_banco": "deigo_rehearsal_",
            "ensaio_postgresql_exige_banco_vazio": True,
            "ensaio_postgresql_exige_confirmacao": True,
            "ensaio_postgresql_transacao_unica": True,
            "ensaio_postgresql_nao_cria_nem_remove_banco": True,
            "ensaio_sem_servico": True,
            "ensaio_sem_dados_ativos": True,
            "restaurar_comando": r".\scripts\restore_local_backup.ps1 -BackupPath backup.zip -ConfirmarRestauracao",
            "confirmacao_explicita": True,
            "backup_anterior_obrigatorio": True,
            "healthcheck_obrigatorio": True,
            "rollback_sqlite_media": True,
            "suporta_aes256": True,
            "motores": ["sqlite", "postgresql"],
            "postgresql_formato": "custom",
            "postgresql_transacao_unica": True,
            "postgresql": "Restauração automática com pg_restore custom, transação unica, backup anterior e rollback.",
        },
        "manutencao_inventario_validade": diagnostico_manutencao_inventarios_validade(),
        "diagnostico_snapshots_lote": (
            diagnostico_cobertura_snapshots_lote() if request.user.is_superuser else None
        ),
        "ensaio_estoque": {
            "contrato": "inventory_pilot_end_to_end_evidence_v3",
            "contrato_prontidao_real": "inventory_real_pilot_readiness_v1",
            "contrato_previa": "inventory_pilot_candidate_preview_v1",
            "contrato_ficha": "inventory_pilot_execution_sheet_v2",
            "contrato_verificacao_artefatos": "inventory_pilot_artifact_integrity_v1",
            "contrato_dossie": "inventory_pilot_dossier_v1",
            "download_relatorio_master": True,
            "verificacao_artefatos_visual_master": True,
            "dossie_visual_master": True,
            "verificacao_dossie_visual_master": True,
            "somente_leitura": True,
            "comunicacao_externa": False,
            "previa_comando": "manage.py previsualizar_fluxo_estoque_piloto --filial-id ID --estrito",
            "ficha_comando": "manage.py gerar_ficha_execucao_piloto --entrada-id ID --venda-id ID --perda-id ID --inventario-id ID --fechamento-id ID --responsavel-execucao NOME --responsavel-conferencia NOME --estrito",
            "comando": "manage.py verificar_fluxo_estoque_piloto --entrada-id ID --venda-id ID --perda-id ID --inventario-id ID --fechamento-id ID --estrito",
            "verificacao_artefatos_comando": "manage.py verificar_artefatos_piloto --ficha FICHA.json --relatorio RELATORIO.json --estrito",
            "verificacao_dossie_comando": "manage.py verificar_dossie_piloto --dossie DOSSIE.zip --estrito",
            "dados_sinteticos_flag": "--dados-sinteticos",
        },
        "backup_local": {
            "contrato": "erp_local_backup_v2",
            "fontes_contrato": "local_backup_sources_v1",
            "fontes": "Configuração efetiva do Django, priorizando o XML WinSW quando o serviço estiver instalado.",
            "sqlite_snapshot_consistente": True,
            "postgresql_dump_custom": True,
            "postgresql_ferramenta": "pg_dump",
            "inclui_dump_logico": True,
            "evidencias_fiscais_contrato": "fiscal_evidence_anchor_v1",
            "evidencias_fiscais_modo_estrito": True,
            "evidencias_fiscais_verificar_comando": "manage.py verificar_integridade_evidencias_fiscais --estrito --registrar-alerta --origem backup",
            "evidencias_fiscais_alerta_master": True,
            "evidencias_fiscais_ancora_externa": "fiscal-evidence-anchor-latest.json",
            "evidencias_fiscais_valida_restauracao": True,
            "destino_padrao": r"%ProgramData%\DeigoVarejo\Backups",
            "destino_env": "LOCAL_BACKUP_DIR",
            "copia_secundaria_opcional": True,
            "copia_secundaria_destino_env": "LOCAL_BACKUP_SECONDARY_DIR",
            "copia_secundaria_confirmacao_env": "LOCAL_BACKUP_SECONDARY_CONFIRMED",
            "copia_secundaria_somente_criptografada": True,
            "copia_secundaria_sha256_obrigatorio": True,
            "copia_secundaria_promocao_atomica": True,
            "copia_secundaria_retencao_independente": True,
            "historico_sanitizado_master": True,
            "historico_comando": "manage.py registrar_resultado_backup_operacional",
            "historico_limite_tela": 20,
            "periodicidade_contrato": "backup_freshness_v1",
            "politica_idade_contrato": "backup_age_policy_v1",
            "pos_implantacao_mesma_politica": True,
            "aceite_validacao_contrato": "local_backup_package_validation_v1",
            "aceite_valida_sha256": True,
            "aceite_valida_estrutura": True,
            "aceite_valida_contrato_backup": True,
            "aceite_valida_ancora_fiscal": True,
            "aceite_suporta_aes256": True,
            "periodicidade_env": "LOCAL_BACKUP_MAX_AGE_HOURS",
            "periodicidade_desligada_por_padrao": True,
            "tarefa_conta": "SYSTEM",
            "depende_usuario_conectado": False,
            "validar_comando": r".\scripts\backup_local.ps1 -ValidarSomente",
            "criptografia_opcional": True,
        },
        "acesso": {
            "admin_local_url": request.build_absolute_uri("/configuracoes/"),
            "usa_navegador": True,
            "app_shell_opcional": True,
            "pdv_desktop_separado": True,
        },
        "servico_windows": servico_windows,
        "scripts": scripts,
        "modos_implantacao": {
            "local": {
                "codigo": ModoImplantacao.LOCAL,
                "descricao": "Loja opera sem depender da internet; backups e atualizações são controlados localmente.",
                "empresas": modos.get(ModoImplantacao.LOCAL, 0),
            },
            "hibrido": {
                "codigo": ModoImplantacao.HIBRIDO,
                "descricao": "Loja opera no servidor local e sincroniza com a nuvem quando houver conexão.",
                "empresas": modos.get(ModoImplantacao.HIBRIDO, 0),
            },
            "nuvem_agente": {
                "codigo": ModoImplantacao.NUVEM_AGENTE,
                "descricao": "Retaguarda em nuvem usa agente local para dispositivos e contingência.",
                "empresas": modos.get(ModoImplantacao.NUVEM_AGENTE, 0),
            },
        },
        "empresas": [
            {
                "id": empresa.id,
                "nome": empresa.nome_fantasia,
                "modo_implantacao": empresa.modo_implantacao,
                "modo_implantacao_label": empresa.get_modo_implantacao_display(),
                "sincronizacao_automatica": empresa.sincronizacao_automatica,
                "filiais": empresa.filiais.count(),
            }
            for empresa in empresas
        ],
        "pendencias": pendencias,
    }


@login_required
@role_required(*SISTEMA)
def pdv_desktop_terminal_pacote(request, pk):
    _exigir_admin_master(request.user)
    terminal = get_object_or_404(TerminalPdv.objects.select_related("filial", "filial__empresa"), pk=pk)
    if not terminal.licenca_liberada:
        raise PermissionDenied
    return JsonResponse(_pdv_desktop_terminal_payload(request, terminal))


@login_required
@role_required(*SISTEMA)
def servidor_local(request):
    payload = _servidor_local_payload(request)
    formulario_homologacao = None
    homologacoes = None
    resumo_homologacoes = None
    homologacao_status = None
    if request.user.is_superuser:
        homologacao_status = diagnostico_homologacao_servidor_local()
        formulario_homologacao = HomologacaoServidorLocalForm(
            request.POST or None,
            request.FILES or None,
            prefix="homologacao",
        )
        if request.method == "POST":
            if formulario_homologacao.is_valid():
                homologacao = formulario_homologacao.save(commit=False)
                homologacao.registrada_por = request.user
                homologacao.save()
                LogAuditoria.objects.create(
                    usuario=request.user,
                    modulo="configuracoes",
                    acao="REGISTRO_HOMOLOGACAO_SERVIDOR_LOCAL",
                    descricao=(
                        f"Homologação {homologacao.get_resultado_display().lower()} "
                        f"da máquina {homologacao.maquina}, versão {homologacao.versao_artefato}."
                    ),
                    objeto_tipo="HomologacaoServidorLocal",
                    objeto_id=str(homologacao.pk),
                    ip=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, "Resultado da homologação registrado com evidência.")
                return redirect(f"{reverse('configuracoes:servidor_local')}#homologacoes")
            messages.error(request, "Revise os dados da homologação.")
        queryset = HomologacaoServidorLocal.objects.select_related("registrada_por")
        homologacoes = Paginator(queryset, 20).get_page(request.GET.get("homologacao_page"))
        params = request.GET.copy()
        if homologacoes.has_previous():
            params["homologacao_page"] = homologacoes.previous_page_number()
            homologacoes.previous_url = f"?{params.urlencode()}#homologacoes"
        else:
            homologacoes.previous_url = ""
        if homologacoes.has_next():
            params["homologacao_page"] = homologacoes.next_page_number()
            homologacoes.next_url = f"?{params.urlencode()}#homologacoes"
        else:
            homologacoes.next_url = ""
        totais = dict(
            HomologacaoServidorLocal.objects.values_list("resultado")
            .annotate(total=Count("id"))
        )
        resumo_homologacoes = {
            "total": sum(totais.values()),
            "aprovadas": totais.get(ResultadoHomologacaoServidor.APROVADA, 0),
            "reprovadas": totais.get(ResultadoHomologacaoServidor.REPROVADA, 0),
        }
    elif request.method == "POST":
        raise PermissionDenied
    return render(
        request,
        "configuracoes/servidor_local.html",
        {
            "payload": payload,
            "empresas": payload["empresas"],
            "modos": payload["modos_implantacao"],
            "pendencias": payload["pendencias"],
            "prontidao": payload["prontidao"],
            "formulario_homologacao": formulario_homologacao,
            "homologacoes": homologacoes,
            "resumo_homologacoes": resumo_homologacoes,
            "homologacao_status": homologacao_status,
            "diagnostico_snapshots_lote": payload.get("diagnostico_snapshots_lote"),
            "filiais_piloto": (
                Filial.objects.select_related("empresa").order_by(
                    "empresa__nome_fantasia", "nome", "id"
                )
                if request.user.is_superuser
                else None
            ),
        },
    )


@login_required
@role_required(*SISTEMA)
def servidor_local_manifest(request):
    _exigir_admin_master(request.user)
    return JsonResponse(_servidor_local_payload(request))


def _resposta_json_download(payload, arquivo):
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{arquivo}"'
    return response


@login_required
@role_required(*SISTEMA)
def servidor_local_previa_piloto(request):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        raise PermissionDenied
    try:
        filial_id = int(request.POST.get("filial_id", ""))
        limite = int(request.POST.get("limite", "20"))
        if filial_id < 1:
            raise ValueError
        previa = previsualizar_candidatos_piloto(
            filial_id=filial_id, limite_por_tipo=limite
        )
    except (ObjectDoesNotExist, TypeError, ValueError):
        return JsonResponse(
            {"erro": "Filial ou limite inválido para a prévia do piloto."},
            status=400,
        )
    return _resposta_json_download(
        previa, f"previa_piloto_filial_{filial_id}.json"
    )


@login_required
@role_required(*SISTEMA)
def servidor_local_ficha_piloto(request):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        raise PermissionDenied
    if request.POST.get("confirmar_selecao") != "sim":
        return JsonResponse(
            {"erro": "Confirme que os cinco IDs foram escolhidos manualmente."},
            status=400,
        )
    try:
        ids = {
            nome: int(request.POST.get(f"{nome}_id", ""))
            for nome in ("entrada", "venda", "perda", "inventario", "fechamento")
        }
        if any(valor < 1 for valor in ids.values()):
            raise ValueError
        ficha = gerar_ficha_execucao_piloto(
            entrada_id=ids["entrada"],
            venda_id=ids["venda"],
            perda_id=ids["perda"],
            inventario_id=ids["inventario"],
            fechamento_id=ids["fechamento"],
            responsavel_execucao=request.POST.get("responsavel_execucao", ""),
            responsavel_conferencia=request.POST.get("responsavel_conferencia", ""),
            observacoes_operacionais=request.POST.get("observacoes_operacionais", ""),
        )
    except (ObjectDoesNotExist, TypeError, ValueError):
        return JsonResponse(
            {"erro": "Revise os IDs, responsáveis e observações da ficha."},
            status=400,
        )
    return _resposta_json_download(
        ficha, f"ficha_piloto_{ficha['conteudo_sha256'][:12]}.json"
    )


@login_required
@role_required(*SISTEMA)
def servidor_local_relatorio_piloto(request):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        raise PermissionDenied
    if request.POST.get("confirmar_relatorio") != "sim":
        return JsonResponse(
            {"erro": "Confirme a geração somente leitura do relatório final."},
            status=400,
        )
    tipo_dados = request.POST.get("tipo_dados", "")
    if tipo_dados not in {"sinteticos", "reais"}:
        return JsonResponse(
            {"erro": "Selecione se os dados do ensaio são sintéticos ou reais."},
            status=400,
        )
    try:
        ids = {
            nome: int(request.POST.get(f"{nome}_id", ""))
            for nome in ("entrada", "venda", "perda", "inventario", "fechamento")
        }
        if any(valor < 1 for valor in ids.values()):
            raise ValueError
        evidencia = gerar_evidencia_fluxo_estoque_piloto(
            entrada_id=ids["entrada"],
            venda_id=ids["venda"],
            perda_id=ids["perda"],
            inventario_id=ids["inventario"],
            fechamento_id=ids["fechamento"],
            dados_sinteticos=tipo_dados == "sinteticos",
        )
    except (ObjectDoesNotExist, TypeError, ValidationError, ValueError):
        return JsonResponse(
            {"erro": "Revise os cinco IDs e a compatibilidade do fluxo selecionado."},
            status=400,
        )
    return _resposta_json_download(
        evidencia,
        (
            f"relatorio_piloto_{tipo_dados}_filial_{evidencia['filial_id']}_"
            f"{evidencia['conteudo_sha256'][:12]}.json"
        ),
    )


@csrf_protect
def _processar_verificacao_artefatos_piloto(request):
    try:
        if request.POST.get("confirmar_verificacao") != "sim":
            raise ValueError
        ficha = carregar_artefato_upload(request.FILES.get("ficha_json"))
        relatorio = carregar_artefato_upload(request.FILES.get("relatorio_json"))
        resultado = verificar_integridade_artefatos_piloto(
            ficha=ficha, relatorio=relatorio
        )
    except (RequestDataTooBig, TypeError, ValueError):
        return JsonResponse(
            {"erro": "Revise a confirmação e os dois arquivos JSON de até 5 MB."},
            status=400,
        )
    return _resposta_json_download(
        resultado,
        f"integridade_piloto_{resultado['conteudo_sha256'][:12]}.json",
    )


@csrf_exempt
@login_required
@role_required(*SISTEMA)
def servidor_local_verificar_artefatos_piloto(request):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        raise PermissionDenied
    request.upload_handlers = [ArtefatoPilotoMemoryUploadHandler(request)]
    return _processar_verificacao_artefatos_piloto(request)


@csrf_protect
def _processar_dossie_piloto(request):
    try:
        if request.POST.get("confirmar_dossie") != "sim":
            raise ValueError
        ficha = carregar_artefato_upload(request.FILES.get("ficha_json"))
        relatorio = carregar_artefato_upload(request.FILES.get("relatorio_json"))
        verificacao = carregar_artefato_upload(
            request.FILES.get("verificacao_json")
        )
        conteudo, manifesto = gerar_dossie_piloto(
            ficha=ficha, relatorio=relatorio, verificacao=verificacao
        )
    except (RequestDataTooBig, TypeError, ValueError):
        return JsonResponse(
            {
                "erro": (
                    "Revise a confirmação e os três arquivos JSON coerentes "
                    "de até 5 MB."
                )
            },
            status=400,
        )
    resposta = HttpResponse(conteudo, content_type="application/zip")
    sha256_dossie = hashlib.sha256(conteudo).hexdigest()
    resposta["Content-Disposition"] = (
        "attachment; filename=\"dossie_piloto_filial_"
        f"{manifesto['filial_id']}_{sha256_dossie[:12]}.zip\""
    )
    return resposta


@csrf_exempt
@login_required
@role_required(*SISTEMA)
def servidor_local_dossie_piloto(request):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        raise PermissionDenied
    request.upload_handlers = [
        ArtefatoPilotoMemoryUploadHandler(request, quantidade_arquivos=3)
    ]
    return _processar_dossie_piloto(request)


@csrf_protect
def _processar_verificacao_dossie_piloto(request):
    try:
        if request.POST.get("confirmar_verificacao_dossie") != "sim":
            raise ValueError
        resultado = verificar_dossie_piloto_upload(
            request.FILES.get("dossie_zip")
        )
    except (RequestDataTooBig, TypeError, ValueError):
        return JsonResponse(
            {
                "erro": (
                    "Revise a confirmação e selecione um dossiê ZIP local "
                    "dentro do limite permitido."
                )
            },
            status=400,
        )
    return _resposta_json_download(
        resultado,
        f"integridade_dossie_{resultado['conteudo_sha256'][:12]}.json",
    )


@csrf_exempt
@login_required
@role_required(*SISTEMA)
def servidor_local_verificar_dossie_piloto(request):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        raise PermissionDenied
    request.upload_handlers = [DossiePilotoMemoryUploadHandler(request)]
    return _processar_verificacao_dossie_piloto(request)


@login_required
@role_required(*SISTEMA)
def servidor_local_download(request):
    _exigir_admin_master(request.user)
    pacote = artefato_servidor_local()
    if not pacote["publicavel"]:
        raise Http404("Pacote do servidor local indisponivel ou reprovado na validacao.")
    caminho = pacote["caminho"]
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="DOWNLOAD_SERVIDOR_LOCAL",
        descricao=f"Download do pacote do servidor local {caminho.name}.",
        objeto_tipo="LocalServerPackage",
        objeto_id=settings.LOCAL_SERVER_VERSION,
        ip=request.META.get("REMOTE_ADDR"),
    )
    return FileResponse(caminho.open("rb"), as_attachment=True, filename=caminho.name)


@login_required
@role_required(*SISTEMA)
def servidor_local_offline_download(request):
    _exigir_admin_master(request.user)
    pacote = artefato_servidor_offline()
    if not pacote["publicavel"]:
        raise Http404("Pacote offline do servidor indisponivel ou reprovado na validacao.")
    caminho = pacote["caminho"]
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="DOWNLOAD_SERVIDOR_LOCAL_OFFLINE",
        descricao=f"Download do pacote offline do servidor local {caminho.name}.",
        objeto_tipo="LocalServerOfflinePackage",
        objeto_id=settings.LOCAL_SERVER_VERSION,
        ip=request.META.get("REMOTE_ADDR"),
    )
    return FileResponse(caminho.open("rb"), as_attachment=True, filename=caminho.name)


@login_required
@role_required(*ADMINISTRACAO)
def formas_pagamento(request):
    formas = FormaPagamento.objects.order_by("-ativo", "nome")
    if request.user.is_superuser:
        pagina = Paginator(formas, 50).get_page(request.GET.get("page"))
        return render(request, "configuracoes/formas_pagamento.html", {"formas": pagina, "page_obj": pagina, "catalogo_global": True})

    filiais = list(_filiais_visiveis(request.user).filter(is_active=True).order_by("nome"))
    for filial in filiais:
        inicializar_formas_pagamento_filial(filial)
    configuracoes = {
        (config.filial_id, config.forma_pagamento_id): config
        for config in FormaPagamentoFilial.objects.select_related(
            "filial", "forma_pagamento", "conta_movimento_padrao"
        ).filter(filial__in=filiais)
    }
    linhas = []
    for filial in filiais:
        for forma in formas:
            configuracao = configuracoes.get((filial.id, forma.id))
            linhas.append({
                "filial": filial,
                "forma": forma,
                "configuracao": configuracao,
                "ativo": configuracao.ativo if configuracao else forma.ativo,
                "conta": configuracao.conta_movimento_padrao if configuracao else None,
            })
    pagina = Paginator(linhas, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "configuracoes/formas_pagamento.html",
        {"formas_filiais": pagina, "page_obj": pagina, "catalogo_global": False},
    )


@login_required
@role_required(*ADMINISTRACAO)
def forma_pagamento_form(request, pk=None):
    if request.user.is_superuser:
        forma = get_object_or_404(FormaPagamento, pk=pk) if pk else None
        form = FormaPagamentoForm(request.POST or None, instance=forma)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Forma de pagamento salva com sucesso.")
            return redirect("configuracoes:formas_pagamento")
        return render(
            request,
            "configuracoes/forma_pagamento_form.html",
            {"form": form, "object": forma, "catalogo_global": True},
        )

    if not pk:
        raise PermissionDenied("Somente o admin master pode criar itens no catálogo global.")
    forma = get_object_or_404(FormaPagamento, pk=pk)
    filiais = _filiais_visiveis(request.user).filter(is_active=True).order_by("nome")
    filial_id = request.POST.get("filial") or request.GET.get("filial")
    filial = get_object_or_404(filiais, pk=filial_id) if filial_id else filiais.first()
    if not filial:
        raise PermissionDenied("O administrador não possui filial ativa vinculada.")
    inicializar_formas_pagamento_filial(filial)
    configuracao = FormaPagamentoFilial.objects.filter(filial=filial, forma_pagamento=forma).first()
    instance = configuracao or FormaPagamentoFilial(filial=filial, forma_pagamento=forma, ativo=forma.ativo)
    contas = ContaMovimentoFinanceiro.objects.filter(
        filial__in=filiais,
        ativa=True,
    ).select_related("filial").order_by("filial__nome", "nome")
    form = FormaPagamentoFilialForm(
        request.POST or None,
        instance=instance,
        filiais_queryset=filiais,
        contas_queryset=contas,
    )
    if request.method == "POST" and form.is_valid():
        configuracao = form.save(commit=False)
        configuracao.forma_pagamento = forma
        configuracao.full_clean()
        configuracao.save()
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="configuracoes",
            acao="CONFIGURAR_FORMA_PAGAMENTO_FILIAL",
            descricao=(
                f"Forma {forma.nome} configurada para {configuracao.filial}: "
                f"{'ativa' if configuracao.ativo else 'inativa'}."
            ),
            objeto_tipo="FormaPagamentoFilial",
            objeto_id=str(configuracao.pk),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Configuração da forma de pagamento salva para a filial.")
        return redirect("configuracoes:formas_pagamento")
    return render(
        request,
        "configuracoes/forma_pagamento_form.html",
        {"form": form, "object": forma, "catalogo_global": False, "forma_catalogo": forma},
    )

@login_required
@role_required(*SISTEMA)
def terminais_pdv(request):
    terminais = _terminais_visiveis(request.user).order_by("filial__nome", "nome")
    busca = request.GET.get("q", "").strip()
    filtro_licenca = request.GET.get("licenca", "").strip()
    filtro_status = request.GET.get("status", "").strip()
    if busca:
        terminais = terminais.filter(
            Q(nome__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(filial__nome__icontains=busca)
            | Q(filial__empresa__nome_fantasia__icontains=busca)
            | Q(filial__empresa__razao_social__icontains=busca)
            | Q(identificador__icontains=busca)
            | Q(chave_api_prefixo__icontains=busca)
        )
    if filtro_licenca in StatusLicencaTerminal.values:
        terminais = terminais.filter(status_licenca=filtro_licenca)
    if filtro_status == "ativo":
        terminais = terminais.filter(ativo=True)
    elif filtro_status == "inativo":
        terminais = terminais.filter(ativo=False)
    pagina = Paginator(terminais, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    pode_gerenciar_chave = has_role(request.user, ADMINISTRACAO)
    chave_nova = request.session.pop("terminal_pdv_chave_nova", None) if pode_gerenciar_chave else None
    return render(
        request,
        "configuracoes/terminais_pdv.html",
        {
            "terminais": pagina,
            "pagina": pagina,
            "query_sem_pagina": query.urlencode(),
            "chave_nova": chave_nova,
            "busca": busca,
            "filtro_licenca": filtro_licenca,
            "filtro_status": filtro_status,
            "status_licenca_choices": StatusLicencaTerminal.choices,
            "pode_gerenciar_chave": pode_gerenciar_chave,
        },
    )



def _eventos_dispositivo_filtrados(request):
    eventos = EventoDispositivoTerminal.objects.select_related(
        "terminal",
        "terminal__filial",
        "terminal__filial__empresa",
    ).filter(terminal__in=_terminais_visiveis(request.user)).order_by("-recebido_em")
    filtros = {
        "q": request.GET.get("q", "").strip(),
        "terminal": request.GET.get("terminal", "").strip(),
        "tipo": request.GET.get("tipo", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "inicio": request.GET.get("inicio", "").strip(),
        "fim": request.GET.get("fim", "").strip(),
    }
    if filtros["q"]:
        eventos = eventos.filter(
            Q(terminal__nome__icontains=filtros["q"])
            | Q(terminal__filial__nome__icontains=filtros["q"])
            | Q(terminal__filial__empresa__nome_fantasia__icontains=filtros["q"])
            | Q(tipo__icontains=filtros["q"])
            | Q(status__icontains=filtros["q"])
            | Q(mensagem__icontains=filtros["q"])
        )
    if filtros["terminal"].isdigit():
        eventos = eventos.filter(terminal_id=filtros["terminal"])
    if filtros["tipo"]:
        eventos = eventos.filter(tipo=filtros["tipo"])
    if filtros["status"]:
        eventos = eventos.filter(status=filtros["status"])
    inicio = parse_date(filtros["inicio"])
    fim = parse_date(filtros["fim"])
    if inicio:
        eventos = eventos.filter(recebido_em__date__gte=inicio)
    if fim:
        eventos = eventos.filter(recebido_em__date__lte=fim)
    return eventos, filtros


@login_required
@role_required(*SISTEMA)
def terminais_pdv_diagnosticos(request):
    eventos, filtros = _eventos_dispositivo_filtrados(request)
    resumo = eventos.values("tipo", "status").annotate(total=Count("id")).order_by("tipo", "status")
    pagina = Paginator(eventos, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "configuracoes/terminais_pdv_diagnosticos.html",
        {
            "pagina": pagina,
            "filtros": filtros,
            "query_sem_pagina": query.urlencode(),
            "terminais": _terminais_visiveis(request.user).order_by("filial__nome", "nome"),
            "tipos": EventoDispositivoTerminal.objects.exclude(tipo="").values_list("tipo", flat=True).distinct().order_by("tipo"),
            "status_opcoes": EventoDispositivoTerminal.objects.exclude(status="").values_list("status", flat=True).distinct().order_by("status"),
            "resumo": resumo,
            "total": eventos.count(),
        },
    )


@login_required
@role_required(*SISTEMA)
def terminais_pdv_diagnosticos_csv(request):
    eventos, _ = _eventos_dispositivo_filtrados(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="diagnosticos_terminais_pdv.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Recebido", "Ocorrido no caixa", "Empresa", "Filial", "Terminal", "Identificador", "Tipo", "Status", "Mensagem"])
    for evento in eventos:
        writer.writerow([
            timezone.localtime(evento.recebido_em).strftime("%d/%m/%Y %H:%M:%S"),
            timezone.localtime(evento.ocorrido_em).strftime("%d/%m/%Y %H:%M:%S") if evento.ocorrido_em else "",
            evento.terminal.filial.empresa.nome_fantasia,
            evento.terminal.filial.nome,
            evento.terminal.nome,
            evento.terminal.identificador,
            evento.tipo,
            evento.status,
            evento.mensagem,
        ])
    return response


@login_required
@role_required(*SISTEMA)
def terminal_pdv_form(request, pk=None):
    terminal = get_object_or_404(_terminais_visiveis(request.user), pk=pk) if pk else None
    politica_anterior = (
        terminal.canal_atualizacao,
        terminal.bloquear_atualizacoes,
    ) if terminal else None
    form = TerminalPdvForm(request.POST or None, instance=terminal, filiais_queryset=_filiais_visiveis(request.user))
    if not _usuario_admin_master(request.user):
        form.fields["canal_atualizacao"].disabled = True
        form.fields["bloquear_atualizacoes"].disabled = True
    if request.method == "POST" and form.is_valid():
        terminal_anterior = terminal
        terminal = form.save(commit=False)
        if not _usuario_admin_master(request.user):
            if terminal_anterior:
                terminal.status_licenca = terminal_anterior.status_licenca
                terminal.licenca_liberada_em = terminal_anterior.licenca_liberada_em
                terminal.licenca_liberada_por = terminal_anterior.licenca_liberada_por
                terminal.observacao_licenca = terminal_anterior.observacao_licenca
                terminal.canal_atualizacao = politica_anterior[0]
                terminal.bloquear_atualizacoes = politica_anterior[1]
            else:
                terminal.status_licenca = StatusLicencaTerminal.PENDENTE
                terminal.observacao_licenca = "Aguardando liberação do admin master."
        elif terminal.status_licenca == StatusLicencaTerminal.LIBERADA and not terminal.licenca_liberada_em:
            terminal.licenca_liberada_em = timezone.now()
            terminal.licenca_liberada_por = request.user
        chave_nova = None
        if not terminal.chave_api_hash and has_role(request.user, ADMINISTRACAO):
            chave_nova = terminal.gerar_chave_api()
        terminal.save()
        politica_atual = (terminal.canal_atualizacao, terminal.bloquear_atualizacoes)
        if politica_anterior != politica_atual and _usuario_admin_master(request.user):
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="configuracoes",
                acao="POLITICA_ATUALIZACAO_TERMINAL_PDV",
                descricao=(
                    f"Politica de atualizacao do terminal {terminal.nome}: "
                    f"canal {terminal.get_canal_atualizacao_display()}, "
                    f"congelada {'sim' if terminal.bloquear_atualizacoes else 'nao'}."
                ),
                objeto_tipo="TerminalPdv",
                objeto_id=str(terminal.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
        if chave_nova:
            request.session["terminal_pdv_chave_nova"] = {
                "terminal": terminal.nome,
                "identificador": str(terminal.identificador),
                "chave": chave_nova,
            }
        messages.success(request, "Terminal PDV salvo com sucesso.")
        return redirect("configuracoes:terminais_pdv")
    return render(request, "configuracoes/terminal_pdv_form.html", {"form": form, "object": terminal})


@login_required
@role_required(*SISTEMA)
def terminal_pdv_alterar_licenca(request, pk, acao):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        return redirect("configuracoes:terminais_pdv")
    terminal = get_object_or_404(_terminais_visiveis(request.user), pk=pk)
    acoes = {
        "liberar": StatusLicencaTerminal.LIBERADA,
        "bloquear": StatusLicencaTerminal.BLOQUEADA,
        "cancelar": StatusLicencaTerminal.CANCELADA,
        "pendenciar": StatusLicencaTerminal.PENDENTE,
    }
    novo_status = acoes.get(acao)
    if not novo_status:
        messages.error(request, "Ação de licença inválida.")
        return redirect("configuracoes:terminais_pdv")

    terminal.status_licenca = novo_status
    if novo_status == StatusLicencaTerminal.LIBERADA:
        terminal.licenca_liberada_em = timezone.now()
        terminal.licenca_liberada_por = request.user
        terminal.observacao_licenca = request.POST.get("observacao_licenca", "").strip() or "Licença liberada pelo admin master."
    else:
        terminal.observacao_licenca = request.POST.get("observacao_licenca", "").strip() or f"Licença marcada como {terminal.get_status_licenca_display()} pelo admin master."
    terminal.save(update_fields=["status_licenca", "licenca_liberada_em", "licenca_liberada_por", "observacao_licenca", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="LICENCA_TERMINAL_PDV",
        descricao=(
            f"Licença do terminal {terminal.nome} ({terminal.identificador}) alterada para "
            f"{terminal.get_status_licenca_display()}. Observação: {terminal.observacao_licenca or '-'}"
        ),
        objeto_tipo="TerminalPdv",
        objeto_id=str(terminal.id),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, f"Licença do terminal {terminal.nome} atualizada para {terminal.get_status_licenca_display()}.")
    return redirect("configuracoes:terminais_pdv")


@login_required
@role_required(*ADMINISTRACAO)
def terminal_pdv_regenerar_chave(request, pk):
    if request.method != "POST":
        return redirect("configuracoes:terminais_pdv")
    terminal = get_object_or_404(_terminais_visiveis(request.user), pk=pk)
    chave_nova = terminal.gerar_chave_api()
    terminal.save(update_fields=["chave_api_hash", "chave_api_prefixo", "atualizado_em"])
    request.session["terminal_pdv_chave_nova"] = {
        "terminal": terminal.nome,
        "identificador": str(terminal.identificador),
        "chave": chave_nova,
    }
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="RENOVACAO_CHAVE_TERMINAL_PDV",
        descricao=(
            f"Credencial do terminal {terminal.nome} ({terminal.identificador}) renovada. "
            "A chave anterior foi invalidada; o segredo novo não foi persistido no log."
        ),
        objeto_tipo="TerminalPdv",
        objeto_id=str(terminal.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, "Chave do terminal renovada. Reconfigure o aplicativo instalado nesta máquina.")
    return redirect("configuracoes:terminais_pdv")


@login_required
@role_required(*SISTEMA)
def backup_operacional(request):
    _exigir_admin_master(request.user)
    modelos = _modelos_backup()
    total_registros = sum(item["total"] or 0 for item in modelos)
    pagina_modelos = Paginator(modelos, 50).get_page(request.GET.get("page"))
    context = {
        "modelos": pagina_modelos,
        "page_obj": pagina_modelos,
        "total_modelos": len(modelos),
        "total_registros": total_registros,
        "is_admin_master": request.user.is_superuser,
        "gerado_em": timezone.localtime(),
        "integridade_fiscal": diagnostico_integridade_operacional(),
        "historico_backup": historico_backup_operacional(limite=20),
        "periodicidade_backup": diagnostico_periodicidade_backup(),
        "exclusoes": [
            "Permissões internas do Django",
            "Tipos de conteúdo técnicos",
            "Sessões de login",
            "Logs administrativos do painel Django",
        ],
        "backup_local_script": "scripts/backup_local.ps1",
        "backup_evidencias_comando": "manage.py verificar_integridade_evidencias_fiscais --estrito --registrar-alerta --origem backup",
        "backup_criptografia_env": "BACKUP_ENCRYPTION_PASSPHRASE",
        "backup_criptografia_flag": "-RemoverOriginalCriptografado",
        "backup_validacao_flag": "-ValidarSomente",
        "restauracao_ensaio_flag": "-EnsaiarIsolado",
        "restauracao_ensaio_postgres_db_env": "RESTORE_REHEARSAL_POSTGRES_DB",
        "restauracao_ensaio_postgres_host_env": "RESTORE_REHEARSAL_POSTGRES_HOST",
        "restauracao_ensaio_postgres_user_env": "RESTORE_REHEARSAL_POSTGRES_USER",
        "restauracao_ensaio_postgres_password_env": "RESTORE_REHEARSAL_POSTGRES_PASSWORD",
        "restauracao_ensaio_postgres_confirmacao_flag": "-ConfirmarBancoPostgresTemporario",
        "backup_destino_env": "LOCAL_BACKUP_DIR",
        "backup_destino_secundario_env": "LOCAL_BACKUP_SECONDARY_DIR",
        "backup_destino_secundario_confirmacao_env": "LOCAL_BACKUP_SECONDARY_CONFIRMED",
        "backup_idade_maxima_env": "LOCAL_BACKUP_MAX_AGE_HOURS",
        "backup_destino_secundario_confirmacao_flag": "-ConfirmarDestinoSecundario",
        "backup_conta_tarefa": "SYSTEM",
    }
    return render(request, "configuracoes/backup.html", context)


@login_required
@role_required(*SISTEMA)
def backup_download(request):
    _exigir_admin_master(request.user)
    agora = timezone.localtime()
    arquivo = f"backup_supermercado_{agora:%Y%m%d_%H%M%S}.json"
    saida = StringIO()
    call_command(
        "dumpdata",
        exclude=["auth.permission", "contenttypes", "sessions", "admin.logentry"],
        indent=2,
        stdout=saida,
    )
    response = HttpResponse(saida.getvalue(), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{arquivo}"'
    return response


@login_required
@role_required(*SISTEMA)
def impressoes(request):
    configuracoes = _configuracoes_impressao_visiveis(request.user).order_by(
        "empresa__nome_fantasia",
        "filial__nome",
        "tipo_documento",
    )
    resumo = {
        "total": configuracoes.count(),
        "ativas": configuracoes.filter(is_active=True).count(),
        "automaticas": configuracoes.filter(impressao_automatica=True, is_active=True).count(),
        "gavetas": configuracoes.filter(gaveta_automatica=True, is_active=True).count(),
        "sem_impressora": configuracoes.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
    }
    impressoras_cadastradas = [
        nome
        for nome in configuracoes.exclude(impressora_padrao="").values_list("impressora_padrao", flat=True).distinct()
        if nome
    ]
    modelos = _modelos_etiqueta_visiveis(request.user).order_by("configuracao__empresa__nome_fantasia", "nome")
    pagina_configuracoes = Paginator(configuracoes, 25).get_page(request.GET.get("config_page"))
    pagina_modelos = Paginator(modelos, 25).get_page(request.GET.get("model_page"))
    return render(
        request,
        "configuracoes/impressoes.html",
        {
            "configuracoes": pagina_configuracoes,
            "pagina_configuracoes": pagina_configuracoes,
            "pagina_modelos": pagina_modelos,
            "resumo": resumo,
            "impressoras_cadastradas": impressoras_cadastradas,
            "modelos_etiqueta": pagina_modelos,
            "tem_empresas_visiveis": _empresas_visiveis(request.user).filter(is_active=True).exists(),
        },
    )


@login_required
@role_required(*SISTEMA)
def modelo_etiqueta_form(request, pk=None):
    modelo = get_object_or_404(_modelos_etiqueta_visiveis(request.user), pk=pk) if pk else None
    if request.method == "POST":
        form = ModeloEtiquetaForm(request.POST, instance=modelo, configuracoes_queryset=_configuracoes_impressao_visiveis(request.user), terminais_queryset=_terminais_visiveis(request.user))
        if form.is_valid():
            with transaction.atomic():
                salvo = form.save()
                if salvo.padrao:
                    ModeloEtiqueta.objects.filter(configuracao=salvo.configuracao).exclude(pk=salvo.pk).update(padrao=False)
            messages.success(request, "Modelo de etiqueta salvo.")
            return redirect("configuracoes:impressoes")
    else:
        form = ModeloEtiquetaForm(instance=modelo, configuracoes_queryset=_configuracoes_impressao_visiveis(request.user), terminais_queryset=_terminais_visiveis(request.user))
    return render(request, "configuracoes/modelo_etiqueta_form.html", {"form": form, "modelo": modelo})


@login_required
@role_required(*SISTEMA)
def modelo_etiqueta_teste(request, pk):
    modelo = get_object_or_404(
        _modelos_etiqueta_visiveis(request.user).select_related("configuracao", "terminal"),
        pk=pk,
        is_active=True,
        configuracao__is_active=True,
    )
    config = modelo.configuracao
    return JsonResponse(
        {
            "status": "ok",
            "contrato": "label_print_v1",
            "origem": "configuracoes_modelo_etiqueta_teste",
            "mensagem": "Etiqueta de teste preparada para impressão direta no app desktop.",
            "impressora_padrao": config.impressora_padrao,
            "linguagem": config.linguagem_impressora,
            "dpi": config.dpi_impressora,
            "densidade": config.densidade_impressao,
            "velocidade": config.velocidade_impressao,
            "tipo_midia": config.tipo_midia_etiqueta,
            "modelo": {
                "id": modelo.id,
                "nome": modelo.nome,
                "largura_mm": float(modelo.largura_mm),
                "altura_mm": float(modelo.altura_mm),
                "gap_horizontal_mm": float(modelo.gap_horizontal_mm),
                "gap_vertical_mm": float(modelo.gap_vertical_mm),
                "colunas": modelo.colunas,
                "orientacao": modelo.orientacao,
            },
            "itens": [
                {
                    "nome": "ETIQUETA TESTE",
                    "codigo": "789000000001",
                    "unidade": "UN",
                    "preco": "9.99",
                    "copias": 1,
                }
            ],
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoras_locais(request):
    impressoras_cadastradas = list(
        _configuracoes_impressao_visiveis(request.user).exclude(impressora_padrao="")
        .values_list("impressora_padrao", flat=True)
        .distinct()
    )
    return JsonResponse(
        {
            "status": "desktop_bridge_required",
            "mensagem": "O navegador não permite listar impressoras locais diretamente. O app desktop usara este ponto para sincronizar as impressoras da máquina.",
            "impressoras_cadastradas": impressoras_cadastradas,
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoes_desktop(request):
    configuracoes = _configuracoes_impressao_visiveis(request.user).prefetch_related(
        "modelos_etiqueta", "modelos_etiqueta__terminal"
    ).filter(is_active=True).order_by(
        "empresa_id",
        "filial_id",
        "tipo_documento",
    )
    resumo = {
        "total": configuracoes.count(),
        "com_impressora": 0,
        "sem_impressora": 0,
        "etiquetas": 0,
        "etiquetas_com_linguagem_nativa": 0,
        "modelos_profissionais": 0,
    }
    alertas = []
    payload = []
    for config in configuracoes:
        impressora_padrao = (config.impressora_padrao or "").strip()
        impressora_configurada = bool(impressora_padrao)
        mensagem_impressora = ""
        if not impressora_configurada:
            mensagem_impressora = (
                f"{config.get_tipo_documento_display()} sem impressora padrão definida. "
                "Configure a impressora da máquina antes de usar impressão direta no app desktop."
            )
        modelos_ativos = [modelo for modelo in config.modelos_etiqueta.all() if modelo.is_active]
        resumo["com_impressora" if impressora_configurada else "sem_impressora"] += 1
        if mensagem_impressora:
            alertas.append(mensagem_impressora)
        if config.tipo_documento == TipoDocumentoImpressao.ETIQUETA:
            resumo["etiquetas"] += 1
            if config.linguagem_impressora:
                resumo["etiquetas_com_linguagem_nativa"] += 1
            else:
                alertas.append("Configuração de etiqueta sem linguagem nativa de impressora.")
            if modelos_ativos:
                resumo["modelos_profissionais"] += len(modelos_ativos)
            else:
                alertas.append("Configuração de etiqueta sem modelo profissional ativo.")
        payload.append(
            {
                "id": config.id,
                "empresa_id": config.empresa_id,
                "empresa": str(config.empresa),
                "filial_id": config.filial_id,
                "filial": str(config.filial) if config.filial else None,
                "tipo_documento": config.tipo_documento,
                "tipo_documento_label": config.get_tipo_documento_display(),
                "impressora_padrao": impressora_padrao,
                "impressora_configurada": impressora_configurada,
                "mensagem": mensagem_impressora,
                "modelo_papel": config.modelo_papel,
                "modelo_papel_label": config.get_modelo_papel_display(),
                "numero_vias": config.numero_vias,
                "impressao_automatica": config.impressao_automatica,
                "etiqueta": {
                    "largura_mm": float(config.largura_etiqueta_mm),
                    "altura_mm": float(config.altura_etiqueta_mm),
                    "gap_horizontal_mm": float(config.gap_horizontal_mm),
                    "gap_vertical_mm": float(config.gap_vertical_mm),
                    "colunas": config.colunas_etiqueta,
                    "dpi": config.dpi_impressora,
                    "densidade": config.densidade_impressao,
                    "velocidade": config.velocidade_impressao,
                    "tipo_midia": config.tipo_midia_etiqueta,
                    "linguagem": config.linguagem_impressora,
                    "modelos": [
                        {
                            "id": modelo.id,
                            "nome": modelo.nome,
                            "terminal_id": modelo.terminal_id,
                            "largura_mm": float(modelo.largura_mm),
                            "altura_mm": float(modelo.altura_mm),
                            "gap_horizontal_mm": float(modelo.gap_horizontal_mm),
                            "gap_vertical_mm": float(modelo.gap_vertical_mm),
                            "colunas": modelo.colunas,
                            "orientacao": modelo.orientacao,
                            "padrao": modelo.padrao,
                        }
                        for modelo in modelos_ativos
                    ],
                },
                "gaveta": {
                    "automatica": config.gaveta_automatica,
                    "abrir_em_dinheiro": config.gaveta_automatica and config.abrir_gaveta_em_dinheiro,
                    "abrir_em_movimento_caixa": config.gaveta_automatica and config.abrir_gaveta_em_movimento_caixa,
                    "bloqueia_venda_se_indisponivel": False,
                },
            }
        )
    alertas_unicos = list(dict.fromkeys(alertas))
    if resumo["sem_impressora"]:
        status_prontidao = "Atencao"
        percentual = 75
    elif alertas_unicos:
        status_prontidao = "Pronta com ressalvas"
        percentual = 88
    else:
        status_prontidao = "Pronta"
        percentual = 100
    prontidao = {
        "contrato": "print_readiness_v1",
        "status": status_prontidao,
        "percentual": percentual,
        "alertas": alertas_unicos,
        "resumo": resumo,
        "proximo_passo": alertas_unicos[0] if alertas_unicos else "Impressões preparadas para o app desktop local.",
    }
    return JsonResponse(
        {
            "status": "ok",
            "mensagem": "Configurações preparadas para sincronização com o app desktop local.",
            "prontidao": prontidao,
            "configuracoes": payload,
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoes_padroes(request):
    if request.method != "POST":
        return redirect("configuracoes:impressoes")
    empresas = list(_empresas_visiveis(request.user).filter(is_active=True).order_by("id"))
    if not empresas:
        messages.warning(
            request,
            "Cadastre ao menos uma empresa antes de criar os padrões de impressão.",
        )
        return redirect("configuracoes:impressoes")
    criadas = sum(criar_configuracoes_padrao(empresa=empresa) for empresa in empresas)
    if criadas:
        messages.success(request, f"{criadas} configuração(ões) de impressão criada(s).")
    else:
        messages.info(request, "As configurações padrão já estavam criadas para as empresas visíveis.")
    return redirect("configuracoes:impressoes")


@login_required
@role_required(*SISTEMA)
def impressao_form(request, pk=None):
    configuracao = get_object_or_404(_configuracoes_impressao_visiveis(request.user), pk=pk) if pk else None
    if request.method == "POST":
        form = ConfiguracaoImpressaoForm(request.POST, instance=configuracao, empresas_queryset=_empresas_visiveis(request.user), filiais_queryset=_filiais_visiveis(request.user))
        if form.is_valid():
            form.save()
            messages.success(request, "Configuração de impressão salva.")
            return redirect("configuracoes:impressoes")
    else:
        form = ConfiguracaoImpressaoForm(instance=configuracao, empresas_queryset=_empresas_visiveis(request.user), filiais_queryset=_filiais_visiveis(request.user))
    impressoras_cadastradas = [
        nome
        for nome in _configuracoes_impressao_visiveis(request.user).exclude(impressora_padrao="")
        .values_list("impressora_padrao", flat=True)
        .distinct()
        if nome
    ]
    return render(
        request,
        "configuracoes/impressao_form.html",
        {
            "form": form,
            "configuracao": configuracao,
            "impressoras_cadastradas": impressoras_cadastradas,
        },
    )

# Create your views here.

@login_required
@role_required(*SISTEMA)
def admin_desktop_download_windows(request):
    instalador = artefato_admin_desktop()
    if not instalador["publicavel"]:
        raise Http404("Instalador administrativo ainda não foi publicado ou falhou na validação.")
    caminho = instalador["caminho"]
    LogAuditoria.objects.create(usuario=request.user, modulo="configuracoes", acao="DOWNLOAD_ADMIN_DESKTOP", descricao=f"Download do instalador administrativo {caminho.name}.", objeto_tipo="AdminDesktopInstaller", objeto_id=settings.ADMIN_DESKTOP_VERSION, ip=request.META.get("REMOTE_ADDR"))
    return FileResponse(caminho.open("rb"), as_attachment=True, filename=caminho.name)
@login_required
@role_required(*SISTEMA)
def admin_desktop(request):
    contexto = {"instalador_admin": artefato_admin_desktop()}
    return render(request, "configuracoes/admin_desktop.html", contexto)

@login_required
@role_required(*ADMINISTRACAO)
def homologacao_operacional(request):
    empresa_id = _empresa_id_administrativa(request.user)
    if empresa_id == 0:
        raise PermissionDenied("Usuário sem empresa administrativa vinculada.")

    filiais = _filiais_visiveis(request.user).filter(is_active=True).order_by("empresa__nome_fantasia", "nome")
    filial_id = request.POST.get("filial") or request.GET.get("filial")
    filial = get_object_or_404(filiais, pk=filial_id) if filial_id else filiais.first()
    if filial is None:
        messages.warning(request, "Cadastre uma filial ativa antes de iniciar a homologação operacional.")
        return redirect("empresas:lista")

    homologacao, _ = HomologacaoOperacional.objects.get_or_create(
        empresa=filial.empresa,
        filial=filial,
        nome="Roteiro de homologação operacional",
        defaults={"responsavel": request.user},
    )
    etapas_validas = {codigo for codigo, _, _ in ROTEIRO_HOMOLOGACAO_OPERACIONAL}
    if request.method == "POST":
        etapas = [codigo for codigo in request.POST.getlist("etapas") if codigo in etapas_validas]
        homologacao.etapas_concluidas = etapas
        homologacao.observacoes = request.POST.get("observacoes", "").strip()
        homologacao.responsavel = request.user
        homologacao.save(update_fields=["etapas_concluidas", "observacoes", "responsavel", "atualizada_em"])
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="configuracoes",
            acao="ATUALIZAR_HOMOLOGACAO_OPERACIONAL",
            descricao=(
                f"Homologação operacional da filial {filial.nome} atualizada para "
                f"{homologacao.percentual}%."
            ),
            objeto_tipo="HomologacaoOperacional",
            objeto_id=str(homologacao.pk),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Roteiro de homologação operacional atualizado.")
        return redirect(f"{reverse('configuracoes:homologacao_operacional')}?{urlencode({'filial': filial.pk})}")

    historico = HomologacaoOperacional.objects.select_related("empresa", "filial", "responsavel")
    if empresa_id is not None:
        historico = historico.filter(empresa_id=empresa_id)
    historico_pagina = Paginator(historico, 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "configuracoes/homologacao_operacional.html",
        {
            "filiais": filiais,
            "filial_selecionada": filial,
            "homologacao": homologacao,
            "etapas": ROTEIRO_HOMOLOGACAO_OPERACIONAL,
            "etapas_concluidas": set(homologacao.etapas_concluidas or []),
            "historico_pagina": historico_pagina,
        },
    )
