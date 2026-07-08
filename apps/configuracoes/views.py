import hashlib
from io import StringIO

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import TipoPerfil
from apps.accounts.permissions import SISTEMA, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, EventoSincronizacao, Filial, StatusSincronizacao
from apps.fiscal.models import ConfiguracaoFiscal
from apps.pdv.models import AcessoPdvNuvem, StatusAcessoPdvNuvem, StatusLicencaTerminal, TerminalPdv
from apps.vendas.models import FormaPagamento

from .forms import ConfiguracaoImpressaoForm, FormaPagamentoForm, ModeloEtiquetaForm, TerminalPdvForm
from .models import ConfiguracaoImpressao, ModeloEtiqueta
from .services import criar_configuracoes_padrao


CHECKLIST_GRUPOS = [
    {
        "titulo": "Base tecnica",
        "descricao": "Fundacao do projeto, arquitetura e seguranca inicial.",
        "itens": [
            ("Projeto Django com apps modulares", "done", "Estrutura separada por accounts, produtos, estoque, compras, PDV, vendas e relatorios."),
            ("Settings, timezone e ambiente local", "done", "Configuracao por ambiente via .env, seguranca de producao, logs e caminhos ajustaveis definidos."),
            ("Modelagem inicial e migrations", "done", "Modelos principais criados para usuarios, produtos, estoque, compras, PDV, vendas e auditoria."),
            ("Permissoes por perfil no backend", "done", "Perfis e bloqueios por modulo implementados com tela 403 amigavel."),
            ("Cadastro proprio de empresas e filiais", "done", "Sistema possui telas internas para empresa e filiais, incluindo municipio, UF e codigo IBGE fiscal, sem depender do admin padrao."),
            ("Auditoria de acoes criticas", "done", "Logs sensiveis possuem tela de consulta com filtros por periodo, modulo, acao, usuario e exportacao CSV."),
            ("Testes automatizados", "done", "Suite formal cobre venda com baixa de estoque, pagamento dividido, backup e configuracoes de impressao."),
        ],
    },
    {
        "titulo": "PDV e caixa",
        "descricao": "Fluxo operacional do caixa de supermercado.",
        "itens": [
            ("Tela PDV em layout de operador", "done", "PDV sem sidebar, cabendo em 100% de zoom no desktop testado."),
            ("Venda com carrinho e baixa de estoque", "done", "Venda finaliza com itens, pagamentos e baixa automatica."),
            ("Pagamento dividido", "done", "Popup aceita multiplas formas e calcula restante/troco."),
            ("PIX no pagamento do PDV", "done", "Forma PIX prevista nos dados iniciais e disponivel dentro da escolha de pagamento eletronico do F3."),
            ("Campos monetarios no PDV", "done", "Pagamento, fechamento, sangria e suprimento exibem prefixo R$ e valor de pagamento ganhou campo maior."),
            ("Cliente avulso", "done", "Venda presencial pode finalizar sem cliente identificado."),
            ("DAV / pre-venda", "done", "Criacao, listagem, recibo, carregamento no PDV e cancelamento com supervisor."),
            ("Abertura e fechamento de caixa", "done", "Operador abre/fecha; supervisor/admin confere depois."),
            ("Sangria e suprimento", "done", "Exigem senha de supervisor/admin e geram lancamentos automaticos de saida/entrada no livro financeiro da conta Caixa PDV."),
            ("Estorno no PDV", "done", "PDV possui atalho F6 para cancelamento total de venda recente com motivo e senha de supervisor/admin; devolucao parcial segue pela tela da venda."),
            ("Operacao principal por teclado", "done", "Enter inclui produto; F2-F9 acessam funcoes; no carrinho, setas selecionam, Del exclui o produto e Ctrl+Del limpa a venda com confirmacao; no pagamento, Shift+ adiciona forma, Del remove forma e Enter confirma; Shift+M retorna ao menu."),
            ("Bip e retorno automatico de foco", "done", "Leitor envia Enter, inclui o produto, soma repeticoes e devolve o foco ao campo apos o recarregamento."),
            ("Alertas rapidos no PDV", "done", "Mensagens simples viram toasts temporarios; operacoes criticas continuam exigindo confirmacao ou supervisor."),
            ("Autorizacao do PDV em nuvem", "done", "Operador comum fica bloqueado em ambiente de nuvem, tentativa gera solicitacao, admin/gerente recebe alerta visual no topo/menu e decide pelo painel de aprovacao."),
            ("Arquitetura PDV desktop local", "partial", "PDV dos caixas deve ser um aplicativo instalado na maquina do operador, fiel ao layout, atalhos e fluxo de venda do PDV web ja validado, para que o operador use a mesma experiencia nos dois ambientes. O desktop acrescenta integracoes locais com impressora, balanca, gaveta e TEF, operacao resiliente e acesso somente ao necessario para venda, pagamento, caixa, consulta e estorno autorizado, sem telas administrativas completas. O app se comunica com o servidor local da loja pela rede interna; esse servidor local conversa com os dispositivos e o banco operacional da filial. Cadastro por filial, chave individual protegida por hash e bootstrap com registro de conexao implementados. O bootstrap diario devolve a configuracao vigente de licenca, TEF, fiscal e balanca para o app instalado se atualizar sem novo pacote. A nuvem/sede sincroniza por API segura, filas e eventos, sem acessar diretamente o banco local do supermercado. Download/ativacao do app desktop deve exigir autorizacao do admin master, pois cada maquina instalada pode representar uma licenca comercial cobrada por terminal; pacote de ativacao so e entregue para terminal com licenca liberada."),
            ("Balanca integrada no PDV", "partial", "Produtos ja possuem marcacao de produto pesavel. Terminal PDV agora permite configurar balanca por caixa com protocolo, porta/endereco e modelo; manifesto, pacote JSON e bootstrap do app desktop entregam essa configuracao por maquina. Falta o app desktop ler peso automaticamente no PDV, devolver quantidade em KG, preencher a venda e registrar falhas sem bloquear vendas manuais."),
            ("TEF/API de maquininha", "partial", "Pagamentos possuem estados controlados, ID externo, NSU e autorizacao; venda rejeita transacao pendente, recusada ou estornada. Terminais PDV agora configuram provedor TEF e modo de integracao por adaptador, permitindo PagBank, Cielo, Stone, Getnet, Rede, SiTef ou outro fornecedor sem prender o sistema a uma operadora. O bootstrap do app desktop expõe o contrato pdv_tef_v1 com tipos credito, debito e PIX dinamico e retorno esperado. Pagamentos eletronicos confirmados sem retorno real recebem autorizacao simulada rastreavel, deixando o ponto de troca pronto para o app desktop enviar o valor para a maquininha/provedor e aguardar aprovado, recusado, cancelado ou expirado antes de liberar a venda."),
            ("Reversao de pagamento misto", "partial", "Cancelamento total estorna parcelas locais e marca PIX/TEF com transacao externa como estorno pendente, preservando motivo e rastreabilidade. Falta automatizar a chamada ao fornecedor e ratear devolucoes parciais."),
            ("Padrao R$ em todos os formularios", "done", "Campos numericos de preco, valor, custo, desconto, taxa, frete e total recebem automaticamente o prefixo R$ no PDV e nas telas administrativas."),
        ],
    },
    {
        "titulo": "Produtos, estoque e compras",
        "descricao": "Cadastros e controle fisico/financeiro do estoque.",
        "itens": [
            ("Produtos, categorias e marcas", "done", "Cadastro, edicao, busca, importacao CSV, etiquetas, kardex e formularios auxiliares com orientacao de uso operacional."),
            ("Pendencias fiscais de produtos", "done", "Tela fiscal lista produtos com NCM, CEST, origem, CST/CSOSN ou aliquota pendentes e direciona para correcao do cadastro."),
            ("Promocoes", "done", "Preco vigente considera promocao ativa; formulario destaca produto, preco promocional, vigencia e status para uso automatico no PDV."),
            ("Estoque por filial", "done", "Saldo fisico, reservado e disponivel por produto/filial."),
            ("Inventario", "done", "Contagem e aplicacao com autorizacao de supervisor/admin."),
            ("Perdas", "done", "Baixa de perdas com supervisor/admin e log."),
            ("Movimentacao manual", "done", "Entrada/saida/ajuste/reserva com supervisor/admin, auditoria e formulario separado entre operacao e autorizacao."),
            ("Compras", "done", "Entrada de compra com dados da nota, itens recebidos, finalizacao protegida, estoque e financeiro integrados."),
            ("Etiquetas de gondola profissionais", "partial", "O documento complementar de etiquetas foi incorporado ao checklist. A tela busca por nome, codigo de barras e SKU, aceita leitor que envia Enter, copias por produto e modelos compacto 110x30 mm, completo 100x50 mm, A4 e modelos profissionais salvos por empresa, filial e terminal, sempre sem fundo colorido forcado. Configuracao inclui medidas, gaps, colunas, orientacao, DPI, midia, impressora e linguagem; a tela envia o lote ao agente desktop, que gera ZPL ou EPL/PPLB e imprime em RAW sem pre-visualizacao. Ainda faltam homologacao PPLA e testes com equipamentos fisicos."),
        ],
    },
    {
        "titulo": "Relatorios e gestao",
        "descricao": "Visao administrativa para acompanhamento da operacao.",
        "itens": [
            ("Dashboard", "done", "Indicadores principais e atalhos por perfil."),
            ("Relatorios de vendas", "done", "Periodo, faturamento, descontos, devolucoes e produtos vendidos."),
            ("Curva ABC e reposicao", "done", "Analises para decisao de compra e estoque."),
            ("Relatorios de caixas", "done", "Abertos, aguardando conferencia, conferidos, declarado e conferido."),
            ("Relatorios de perdas/devolucoes/compras", "done", "Telas especificas criadas por periodo."),
            ("Exportacoes", "done", "Relatorios operacionais e gerenciais exportam CSV compativel com Excel e possuem versao para PDF."),
            ("Graficos de pizza no dashboard", "done", "Dashboard usa Chart.js para composicao por forma de pagamento, categorias e status dos caixas."),
        ],
    },
    {
        "titulo": "Revisao complementar v2",
        "descricao": "Requisitos acrescentados pelo documento de usabilidade, cadastros e entrega.",
        "itens": [
            ("Login sem caixa alta", "done", "Usuario, e-mail e senha preservam a digitacao original na tela de acesso."),
            ("Busca inteligente/autocomplete", "partial", "PDV possui buscas locais por teclado; Select2 aplicado em filial, produto, fornecedor, cliente, categoria e marca nos formularios mais extensos. Ainda falta busca remota por API para bases muito grandes."),
            ("Consulta de CNPJ e CEP", "partial", "Formularios de empresa e filial ja possuem mascaras, avisos e endpoint JSON preparado; falta escolher/conectar API externa para preencher dados automaticamente."),
            ("Cadastros complementares padronizados", "done", "Clientes, fornecedores, produtos e usuarios possuem formularios organizados por secoes operacionais, com textos de apoio para PDV, compras e etapas futuras."),
            ("Imagens de produto", "done", "Foto principal e galeria adicional com legenda, ordenacao e remocao integradas ao cadastro e preparadas para exibicao no marketplace."),
            ("Politicas de entrega por filial", "partial", "Raio, faixas por distancia, pedido minimo, frete gratis, bairros e horarios configuraveis implementados; geocodificacao automatica por mapa segue pendente."),
            ("Certificado digital protegido", "done", "Configuracao fiscal aceita upload A1 .pfx/.p12, criptografa arquivo e senha, le validade e mostra alertas de vencimento."),
            ("Identidade visual do supermercado", "done", "Logo no topo, marca dagua sutil no carrinho e paleta operacional restrita implementadas."),
        ],
    },
    {
        "titulo": "Etiquetas e impressoras profissionais",
        "descricao": "Requisitos do documento complementar de etiquetas de gondola e impressoras profissionais.",
        "itens": [
            ("Modelo compacto 110x30", "done", "Modelo recomendado para gondola horizontal criado no MVP, priorizando nome do produto, codigo de barras ou codigo interno, unidade e preco grande, sem foto, icones decorativos ou excesso de informacao."),
            ("Modelo completo 100x50", "done", "Modelo maior disponivel para etiquetas com mais espaco, mantendo preco como informacao principal e deixando logo, tributos e preco de referencia como evolucao configuravel."),
            ("Busca por codigo de barras nas etiquetas", "done", "Campo de busca aceita digitacao manual e leitor como teclado, mantendo foco automatico; a consulta prioriza codigo de barras/EAN/GTIN e codigo interno/SKU antes do nome."),
            ("Impressao em medidas reais", "done", "CSS de impressao usa medidas em mm, @media print e oculta menu, filtros e botoes; a cor da etiqueta fica a cargo do papel fisico, com impressao limpa em preto."),
            ("Configuracao profissional de etiquetas", "partial", "Configuracao por empresa/filial persiste impressora, DPI, densidade, velocidade, midia e linguagem. Modelos nomeados guardam largura, altura, gaps, colunas, orientacao, modelo padrao e vinculo opcional ao terminal; a tela de etiquetas aplica o modelo escolhido e o endpoint desktop sincroniza todos os parametros. Ainda falta o agente local gerar e enviar comandos nativos ao equipamento."),
            ("Linguagens nativas de impressoras", "partial", "Arquitetura contempla ZPL, EPL, PPLA e PPLB. A tela web monta um payload confiavel com modelo, produtos e copias e aciona printLabels somente no app desktop; o agente gera ZPL ou EPL/PPLB, converte medidas por DPI e envia ao spooler Windows em RAW com limite e retorno visivel. No navegador permanece a impressao convencional. PPLA segue bloqueado ate homologacao por modelo e ainda faltam testes fisicos."),
        ],
    },
    {
        "titulo": "Proximas fases",
        "descricao": "Itens previstos na documentacao, ainda fora do MVP atual.",
        "itens": [
            ("Fiscal/NFC-e", "partial", "Fila fiscal mostra vendas prontas, pendencias antes da acao e ultima tentativa automatica auditada; tela de produtos fiscais antecipa correcoes de NCM, CEST, origem, CST/CSOSN e aliquota. XML local usa UF e codigo IBGE da filial. A NFC-e segue a regra de ocorrer somente apos pagamento confirmado: por padrao a venda tenta preparar a NFC-e automaticamente, mas o admin pode desativar essa tentativa por terminal PDV quando a empresa decidir operar aquele caixa sem comunicacao fiscal automatica. O PDV exibe no topo se o terminal identificado esta com fiscal automatico ligado ou desligado. Se faltar cadastro fiscal, a venda nao trava e a pendencia fica auditada para correcao. Transmissao simulada em homologacao gera chave, protocolo e auditoria, mas ainda faltam assinatura, schema oficial, transmissao SEFAZ real e contingencia quando a SEFAZ estiver indisponivel."),
            ("Financeiro completo", "partial", "Contas a pagar/receber, baixas, cancelamentos, categorias, fluxo de caixa, conciliacao PDV x financeiro, contas de movimento, vendas a vista do PDV no livro, transferencias entre contas, livro financeiro imutavel, estornos por lancamento inverso, resultado por receitas/despesas, cards gerenciais e exportacoes criadas. A proxima evolucao inclui integracao final com fiscal/contabilidade e relatorios contabeis oficiais."),
            ("Entradas, saidas e livro contabil", "partial", "Contas de movimento por filial para caixa fisico, banco, PIX e outras foram criadas com saldo inicial e saldo atual. Baixas geram entrada ou saida no livro imutavel, vendas a vista do PDV geram entradas automaticas por forma de pagamento, sangria e suprimento geram saida/entrada automatica no Caixa PDV, transferencias geram lancamentos espelhados, atomicos e auditados entre contas da mesma empresa, e estornos rastreaveis criam lancamento inverso sem alterar o original. O livro possui origem, usuario, data, filtros, exportacao CSV, validacao de saldo e relatorio de receitas, despesas e resultado que ignora transferencias internas. Ainda faltam integracao automatica de origens fiscais/contabeis avancadas e relatorios contabeis oficiais. Referencia funcional identificada no ProjetoLimpoGitHub para migracao adaptada, sem alterar o projeto original."),
            ("Marketplace / pedido online", "partial", "Fluxo operacional completo, API segura com chave por plataforma, validacao de itens, idempotencia e acompanhamento visual de separacao/pagamento na listagem implementados; adaptadores especificos de cada parceiro seguem pendentes."),
            ("Impressao personalizada", "done", "Configuracoes de papel, margens, fonte, rodape, vias e impressao automatica aplicadas aos recibos. No app desktop, o botao pos-venda usa o payload autenticado existente, monta cupom operacional sem imagens e envia diretamente ao spooler Windows em RAW/ESC-POS, com ate tres vias, corte de papel e pulso opcional da gaveta, sem abrir pre-visualizacao."),
            ("Descoberta de impressoras locais", "done", "Central de impressao possui campo com sugestoes e endpoint de configuracao. A ponte do app desktop consulta as impressoras instaladas no Windows sem shell interativo e devolve nome, porta, driver, estado e impressora padrao para a mesma interface do PDV, tratando timeout ou falha sem bloquear a venda."),
            ("Gaveta de dinheiro opcional", "partial", "Central de impressao permite habilitar ou desabilitar gaveta automatica por empresa/filial e documento de caixa. Falta o app desktop acionar a impressora ESC-POS por pulso fisico em dinheiro, troco, sangria, suprimento, abertura e fechamento autorizados. Quando desabilitada ou indisponivel, a venda nao deve ser bloqueada; apenas registrar aviso/log operacional."),
            ("Backup/restauracao operacional", "done", "Tela de backup JSON e roteiro de restauracao segura disponiveis em Sistema."),
            ("Aplicativo desktop/PDF", "partial", "Endpoints de configuracao e payload de impressao da venda preparados para o app desktop, incluindo dados de pagamento eletronico, NSU, autorizacao e transacao externa para cupom e comprovante. A interface desktop reutiliza o mesmo design, componentes, atalhos e regras do PDV web em um shell WebView separado, adaptando apenas a camada de integracao com hardware e servicos locais. O esqueleto desktop_pdv possui ativacao guiada na primeira execucao, valida o bootstrap licenciado antes de salvar a credencial em LOCALAPPDATA e abrir /pdv/, permite reconfiguracao e protege a chave de versionamento. O build reproduzivel do executavel Windows com PyInstaller tambem foi preparado. A Central do App PDV desktop publica o instalador somente quando o artefato configurado existe, apresenta tamanho e SHA-256, restringe o download ao admin master e registra a entrega na auditoria. Um script de publicacao atomica confere integridade, impede arquivo parcial na central e grava metadados de versao; versao e caminho do artefato sao configuraveis por ambiente. O app informa sua versao no bootstrap, recebe versao vigente e minima, avisa atualizacao opcional e bloqueia versao insegura; a instalacao continua exigindo o admin master, sem atualizacao automatica fora do licenciamento. O manifesto JSON do app desktop expõe disponibilidade, integridade, contratos e terminais autorizados. Pacote JSON por terminal entrega bootstrap, URL da interface compartilhada, TEF, fiscal, impressao, gaveta, balanca configurada, licenca por maquina e sincronizacao; o bootstrap operacional tambem devolve a configuracao atual a cada inicializacao. Terminais pendentes, bloqueados ou cancelados nao recebem pacote de ativacao nem conseguem inicializar o bootstrap. O aplicativo continua sendo um projeto/artefato separado, baixado por dentro do sistema somente com autorizacao do admin master e configurado com o terminal autorizado. Falta assinar o executavel, gerar o instalador MSI, conectar dispositivos locais e implementar sincronizacao resiliente com servidor local/nuvem."),
            ("Sincronizacao loja-nuvem", "partial", "Empresa escolhe entre servidor local, hibrido e nuvem com agente. Caixa de saida, processador HTTP e caixa de entrada autenticada usam UUID, idempotencia, token fora do banco, timeout, lotes e retentativa exponencial. Eventos recebidos ficam armazenados antes de alterar dados e ja passam por processador interno com handlers por tipo, erro controlado para dominios ainda nao implementados, handler inicial de produtos, handler de saldo de estoque por filial, espelho de venda finalizada com painel de retaguarda, espelho fiscal sincronizado, detalhe auditavel de eventos com payload e diagnostico, resolucao manual de conflitos com responsavel e decisao registrada, exportacao CSV das filas de saida e entrada, comando unico agendavel e roteiro do Agendador de Tarefas do Windows no painel. Ainda faltam instalar o agendador Windows no servidor, transmissao SEFAZ real e politicas automaticas finais de resolucao de conflitos."),
            ("Super admin personalizado", "partial", "Painel proprio centraliza empresas, usuarios, fiscal, formas de pagamento, impressoes, backup, auditoria e checklist, sem atalho visual para o admin Django; ainda faltam telas internas para alguns modelos avancados."),
        ],
    },
]


def _instalador_pdv_desktop():
    caminho = settings.PDV_DESKTOP_INSTALLER_PATH
    if not caminho.is_file():
        return {
            "disponivel": False,
            "nome": caminho.name,
            "tamanho": 0,
            "sha256": "",
            "atualizado_em": None,
        }
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    stat = caminho.stat()
    return {
        "disponivel": True,
        "nome": caminho.name,
        "tamanho": stat.st_size,
        "sha256": digest.hexdigest(),
        "atualizado_em": timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
    }

DOCUMENTOS_PROJETO = [
    ("Complementar PDV, usabilidade, cadastros e entrega v2", "docs/protótipos/documento_complementar_pdv_usabilidade_cadastros_entrega_v2.docx"),
    ("Indice dos documentos finais", "docs/protótipos/00_indice_documentos_finais_supermercado.docx"),
    ("Arquitetura tecnica", "docs/protótipos/01_arquitetura_tecnica_sistema_supermercado.docx"),
    ("Modelagem banco de dados", "docs/protótipos/02_modelagem_banco_dados_sistema_supermercado.docx"),
    ("Regras de negocio", "docs/protótipos/03_regras_negocio_sistema_supermercado.docx"),
    ("MVP por fases", "docs/protótipos/04_mvp_por_fases_sistema_supermercado.docx"),
    ("Checklist de desenvolvimento", "docs/protótipos/05_checklist_desenvolvimento_sistema_supermercado.docx"),
    ("Mapa de telas e fluxos", "docs/protótipos/06_mapa_telas_fluxos_sistema_supermercado.docx"),
    ("Backup e restauracao", "docs/PLANO_BACKUP_RESTAURACAO_SUPERMERCADO.md"),
]
PDV_DESKTOP_VERSAO_PLANEJADA = settings.PDV_DESKTOP_VERSION


def _usuario_admin_master(user):
    if user.is_superuser:
        return True
    perfil = getattr(user, "perfil_supermercado", None)
    if perfil and perfil.is_active and perfil.tipo == TipoPerfil.ADMINISTRADOR:
        return True
    return False


def _exigir_admin_master(user):
    if _usuario_admin_master(user):
        return
    raise PermissionDenied


def _resumo_checklist(grupos):
    totais = {"done": 0, "partial": 0, "todo": 0}
    for grupo in grupos:
        grupo_totais = {"done": 0, "partial": 0, "todo": 0}
        for _, status, _ in grupo["itens"]:
            totais[status] += 1
            grupo_totais[status] += 1
        grupo["total"] = len(grupo["itens"])
        grupo["concluidos"] = grupo_totais["done"]
        grupo["percentual"] = round((grupo_totais["done"] / grupo["total"]) * 100) if grupo["total"] else 0
    total_itens = sum(totais.values())
    return {
        "total": total_itens,
        "concluidos": totais["done"],
        "parciais": totais["partial"],
        "pendentes": totais["todo"],
        "percentual": round((totais["done"] / total_itens) * 100) if total_itens else 0,
    }


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
                "total": total,
            }
        )
    return sorted(modelos, key=lambda item: (item["app"], item["modelo"]))


@login_required
@role_required(*SISTEMA)
def painel_sistema(request):
    modelos = _modelos_backup()
    total_registros = sum(item["total"] or 0 for item in modelos)
    checklist_grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    resumo_checklist = _resumo_checklist(checklist_grupos)
    configuracoes = ConfiguracaoImpressao.objects.all()
    configs_fiscais = ConfiguracaoFiscal.objects.select_related("filial")
    atalhos = [
        {
            "titulo": "Formas de pagamento",
            "descricao": "Meios aceitos no PDV, troco e autorizacao eletronica.",
            "icone": "fa-money-check-dollar",
            "url": "configuracoes:formas_pagamento",
            "status": f"{FormaPagamento.objects.filter(ativo=True).count()} ativa(s)",
        },
        {
            "titulo": "Empresas e filiais",
            "descricao": "Cadastro das lojas, logo, UF e codigo IBGE fiscal.",
            "icone": "fa-building",
            "url": "empresas:lista",
            "status": f"{Filial.objects.count()} filial(is)",
        },
        {
            "titulo": "Usuarios",
            "descricao": "Perfis, permissoes e vinculo de operador com filial.",
            "icone": "fa-user-gear",
            "url": "accounts:usuarios",
            "status": f"{User.objects.filter(is_active=True).count()} ativo(s)",
        },
        {
            "titulo": "Fiscal",
            "descricao": "NFC-e, certificado A1, series, natureza e produtos fiscais.",
            "icone": "fa-receipt",
            "url": "fiscal:documentos",
            "status": f"{configs_fiscais.count()} configuracao(oes)",
        },
        {
            "titulo": "Impressoes",
            "descricao": "Central de impressoras, papel, vias e impressao automatica.",
            "icone": "fa-print",
            "url": "configuracoes:impressoes",
            "status": f"{configuracoes.filter(is_active=True).count()} ativa(s)",
        },
        {
            "titulo": "Acessos PDV nuvem",
            "descricao": "Aprovacao de operadores que tentam acessar o PDV em nuvem.",
            "icone": "fa-user-lock",
            "url": "pdv:acessos_pdv_nuvem",
            "status": f"{AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count()} pendente(s)",
        },
        {
            "titulo": "Terminais PDV",
            "descricao": "Maquinas de caixa autorizadas por filial para o aplicativo local.",
            "icone": "fa-cash-register",
            "url": "configuracoes:terminais_pdv",
            "status": f"{TerminalPdv.objects.filter(ativo=True).count()} ativo(s)",
        },
        {
            "titulo": "App PDV desktop",
            "descricao": "Instalador, requisitos e contrato local do caixa.",
            "icone": "fa-desktop",
            "url": "configuracoes:pdv_desktop",
            "status": "Bridge local",
        },
        {
            "titulo": "Sincronizacao",
            "descricao": "Fila segura entre servidores locais e nuvem, com idempotencia e tentativas.",
            "icone": "fa-arrows-rotate",
            "url": "empresas:sincronizacao",
            "status": f"{EventoSincronizacao.objects.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).count()} aguardando",
        },
        {
            "titulo": "Backup",
            "descricao": "Exportacao operacional em JSON para contingencia.",
            "icone": "fa-database",
            "url": "configuracoes:backup",
            "status": f"{len(modelos)} modelos",
        },
        {
            "titulo": "Auditoria",
            "descricao": "Consulta de acoes criticas realizadas no sistema.",
            "icone": "fa-shield-halved",
            "url": "auditoria:logs",
            "status": "Logs",
        },
        {
            "titulo": "Checklist",
            "descricao": "Roteiro vivo do projeto e proximas fases.",
            "icone": "fa-list-check",
            "url": "configuracoes:checklist",
            "status": f"{resumo_checklist['percentual']}%",
        },
    ]
    context = {
        "atalhos": atalhos,
        "resumo_checklist": resumo_checklist,
        "total_empresas": Empresa.objects.count(),
        "total_filiais": Filial.objects.count(),
        "filiais_sem_ibge": Filial.objects.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
        "usuarios_ativos": User.objects.filter(is_active=True).count(),
        "impressoes_sem_impressora": configuracoes.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
        "certificados_vencidos": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
        "total_registros": total_registros,
    }
    return render(request, "configuracoes/painel_sistema.html", context)


@login_required
@role_required(*SISTEMA)
def checklist_projeto(request):
    grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    context = {
        "grupos": grupos,
        "resumo": _resumo_checklist(grupos),
        "documentos": DOCUMENTOS_PROJETO,
    }
    return render(request, "configuracoes/checklist.html", context)


@login_required
@role_required(*SISTEMA)
def pdv_desktop(request):
    _exigir_admin_master(request.user)
    instalador = _instalador_pdv_desktop()
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
    total_terminais = terminais.count()
    licencas_liberadas = terminais.filter(status_licenca=StatusLicencaTerminal.LIBERADA, ativo=True).count()
    licencas_pendentes = terminais.filter(status_licenca=StatusLicencaTerminal.PENDENTE).count()
    licencas_bloqueadas = terminais.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count()
    context = {
        "terminais": terminais,
        "total_terminais": total_terminais,
        "licencas_liberadas": licencas_liberadas,
        "licencas_pendentes": licencas_pendentes,
        "licencas_bloqueadas": licencas_bloqueadas,
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "instalador": instalador,
        "artefatos": [
            {
                "nome": "Windows x64",
                "status": "Fonte iniciado",
                "descricao": "Shell WebView com ativacao guiada reutiliza /pdv/; build do .exe preparado, faltando assinatura e instalador MSI.",
            },
            {
                "nome": "Bridge local",
                "status": "Contrato pronto",
                "descricao": "Conecta impressora, gaveta, TEF, balanca e servidor local da loja.",
            },
        ],
    }
    return render(request, "configuracoes/pdv_desktop.html", context)


def _pdv_desktop_manifest_payload(request):
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
    instalador = _instalador_pdv_desktop()
    return {
        "status": "ok",
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "distribuicao": "erp",
        "licenciamento": {
            "modelo": "por_terminal",
            "download_requer_admin_master": True,
            "ativacao_requer_terminal_autorizado": True,
            "observacao": "Cada maquina de caixa deve ser liberada pelo admin master antes de baixar/ativar o app desktop.",
        },
        "contratos": {
            "tef": "pdv_tef_v1",
            "impressao": "pdv_print_v1",
            "sincronizacao": "pdv_sync_v1",
        },
        "recursos": {
            "tef_integrado": True,
            "impressao_desktop": True,
            "gaveta_opcional": True,
            "balanca_local": True,
            "fiscal_por_terminal": True,
            "modo_offline": True,
        },
        "artefatos": {
            "windows_x64": {
                "status": "disponivel" if instalador["disponivel"] else "aguardando_build",
                "nome": instalador["nome"],
                "url": request.build_absolute_uri("/configuracoes/pdv-desktop/download/windows/") if instalador["disponivel"] else "",
                "tamanho_bytes": instalador["tamanho"],
                "sha256": instalador["sha256"],
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
                "provedor_tef": terminal.provedor_tef,
                "modo_integracao_tef": terminal.modo_integracao_tef,
                "balanca": {
                    "habilitada": terminal.usa_balanca,
                    "protocolo": terminal.protocolo_balanca,
                    "porta": terminal.porta_balanca,
                    "modelo": terminal.modelo_balanca,
                },
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
    caminho = settings.PDV_DESKTOP_INSTALLER_PATH
    if not caminho.is_file():
        raise Http404("Instalador do PDV desktop ainda nao publicado.")
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
            "observacao": "Pacote destinado apenas a maquina licenciada e autorizada pelo admin master.",
        },
        "filial": {
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
            "observacao": "Quando falso, este terminal nao tenta preparar NFC-e automaticamente.",
        },
        "tef": {
            "contrato": "pdv_tef_v1",
            "provedor": terminal.provedor_tef,
            "modo_integracao": terminal.modo_integracao_tef,
            "tipos_pagamento": ["CREDITO", "DEBITO", "PIX"],
            "retorno_esperado": ["status", "transacao_externa_id", "nsu", "codigo_autorizacao", "mensagem_processadora"],
        },
        "dispositivos": {
            "impressora": {"contrato": "pdv_print_v1", "config_url": request.build_absolute_uri("/configuracoes/impressoes/desktop.json")},
            "gaveta": {"opcional": True},
            "balanca": {
                "opcional": True,
                "habilitada": terminal.usa_balanca,
                "protocolo": terminal.protocolo_balanca,
                "porta": terminal.porta_balanca,
                "modelo": terminal.modelo_balanca,
            },
        },
        "sincronizacao": {
            "contrato": "pdv_sync_v1",
            "modo_offline_permitido": terminal.permite_modo_offline,
        },
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
def formas_pagamento(request):
    formas = FormaPagamento.objects.order_by("-ativo", "nome")
    return render(request, "configuracoes/formas_pagamento.html", {"formas": formas})


@login_required
@role_required(*SISTEMA)
def forma_pagamento_form(request, pk=None):
    forma = get_object_or_404(FormaPagamento, pk=pk) if pk else None
    form = FormaPagamentoForm(request.POST or None, instance=forma)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Forma de pagamento salva com sucesso.")
        return redirect("configuracoes:formas_pagamento")
    return render(request, "configuracoes/forma_pagamento_form.html", {"form": form, "object": forma})


@login_required
@role_required(*SISTEMA)
def terminais_pdv(request):
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
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
    chave_nova = request.session.pop("terminal_pdv_chave_nova", None)
    return render(
        request,
        "configuracoes/terminais_pdv.html",
        {
            "terminais": terminais,
            "chave_nova": chave_nova,
            "busca": busca,
            "filtro_licenca": filtro_licenca,
            "filtro_status": filtro_status,
            "status_licenca_choices": StatusLicencaTerminal.choices,
        },
    )


@login_required
@role_required(*SISTEMA)
def terminal_pdv_form(request, pk=None):
    terminal = get_object_or_404(TerminalPdv, pk=pk) if pk else None
    form = TerminalPdvForm(request.POST or None, instance=terminal)
    if request.method == "POST" and form.is_valid():
        terminal_anterior = terminal
        terminal = form.save(commit=False)
        if not _usuario_admin_master(request.user):
            if terminal_anterior:
                terminal.status_licenca = terminal_anterior.status_licenca
                terminal.licenca_liberada_em = terminal_anterior.licenca_liberada_em
                terminal.licenca_liberada_por = terminal_anterior.licenca_liberada_por
                terminal.observacao_licenca = terminal_anterior.observacao_licenca
            else:
                terminal.status_licenca = StatusLicencaTerminal.PENDENTE
                terminal.observacao_licenca = "Aguardando liberacao do admin master."
        elif terminal.status_licenca == StatusLicencaTerminal.LIBERADA and not terminal.licenca_liberada_em:
            terminal.licenca_liberada_em = timezone.now()
            terminal.licenca_liberada_por = request.user
        chave_nova = None
        if not terminal.chave_api_hash:
            chave_nova = terminal.gerar_chave_api()
        terminal.save()
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
    terminal = get_object_or_404(TerminalPdv, pk=pk)
    acoes = {
        "liberar": StatusLicencaTerminal.LIBERADA,
        "bloquear": StatusLicencaTerminal.BLOQUEADA,
        "cancelar": StatusLicencaTerminal.CANCELADA,
        "pendenciar": StatusLicencaTerminal.PENDENTE,
    }
    novo_status = acoes.get(acao)
    if not novo_status:
        messages.error(request, "Acao de licenca invalida.")
        return redirect("configuracoes:terminais_pdv")

    terminal.status_licenca = novo_status
    if novo_status == StatusLicencaTerminal.LIBERADA:
        terminal.licenca_liberada_em = timezone.now()
        terminal.licenca_liberada_por = request.user
        terminal.observacao_licenca = request.POST.get("observacao_licenca", "").strip() or "Licenca liberada pelo admin master."
    else:
        terminal.observacao_licenca = request.POST.get("observacao_licenca", "").strip() or f"Licenca marcada como {terminal.get_status_licenca_display()} pelo admin master."
    terminal.save(update_fields=["status_licenca", "licenca_liberada_em", "licenca_liberada_por", "observacao_licenca", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="LICENCA_TERMINAL_PDV",
        descricao=(
            f"Licenca do terminal {terminal.nome} ({terminal.identificador}) alterada para "
            f"{terminal.get_status_licenca_display()}. Observacao: {terminal.observacao_licenca or '-'}"
        ),
        objeto_tipo="TerminalPdv",
        objeto_id=str(terminal.id),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, f"Licenca do terminal {terminal.nome} atualizada para {terminal.get_status_licenca_display()}.")
    return redirect("configuracoes:terminais_pdv")


@login_required
@role_required(*SISTEMA)
def terminal_pdv_regenerar_chave(request, pk):
    if request.method != "POST":
        return redirect("configuracoes:terminais_pdv")
    terminal = get_object_or_404(TerminalPdv, pk=pk)
    chave_nova = terminal.gerar_chave_api()
    terminal.save(update_fields=["chave_api_hash", "chave_api_prefixo", "atualizado_em"])
    request.session["terminal_pdv_chave_nova"] = {
        "terminal": terminal.nome,
        "identificador": str(terminal.identificador),
        "chave": chave_nova,
    }
    messages.success(request, "Chave do terminal renovada. Atualize o aplicativo instalado nesta maquina.")
    return redirect("configuracoes:terminais_pdv")


@login_required
@role_required(*SISTEMA)
def backup_operacional(request):
    modelos = _modelos_backup()
    total_registros = sum(item["total"] or 0 for item in modelos)
    context = {
        "modelos": modelos,
        "total_modelos": len(modelos),
        "total_registros": total_registros,
        "gerado_em": timezone.localtime(),
        "exclusoes": [
            "Permissoes internas do Django",
            "Tipos de conteudo tecnicos",
            "Sessoes de login",
            "Logs administrativos do painel Django",
        ],
    }
    return render(request, "configuracoes/backup.html", context)


@login_required
@role_required(*SISTEMA)
def backup_download(request):
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
    configuracoes = ConfiguracaoImpressao.objects.select_related("empresa", "filial").order_by(
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
    return render(
        request,
        "configuracoes/impressoes.html",
        {
            "configuracoes": configuracoes,
            "resumo": resumo,
            "impressoras_cadastradas": impressoras_cadastradas,
            "modelos_etiqueta": ModeloEtiqueta.objects.select_related(
                "configuracao", "configuracao__empresa", "configuracao__filial", "terminal"
            ),
        },
    )


@login_required
@role_required(*SISTEMA)
def modelo_etiqueta_form(request, pk=None):
    modelo = get_object_or_404(ModeloEtiqueta, pk=pk) if pk else None
    if request.method == "POST":
        form = ModeloEtiquetaForm(request.POST, instance=modelo)
        if form.is_valid():
            with transaction.atomic():
                salvo = form.save()
                if salvo.padrao:
                    ModeloEtiqueta.objects.filter(configuracao=salvo.configuracao).exclude(pk=salvo.pk).update(padrao=False)
            messages.success(request, "Modelo de etiqueta salvo.")
            return redirect("configuracoes:impressoes")
    else:
        form = ModeloEtiquetaForm(instance=modelo)
    return render(request, "configuracoes/modelo_etiqueta_form.html", {"form": form, "modelo": modelo})


@login_required
@role_required(*SISTEMA)
def impressoras_locais(request):
    impressoras_cadastradas = list(
        ConfiguracaoImpressao.objects.exclude(impressora_padrao="")
        .values_list("impressora_padrao", flat=True)
        .distinct()
    )
    return JsonResponse(
        {
            "status": "desktop_bridge_required",
            "mensagem": "O navegador nao permite listar impressoras locais diretamente. O app desktop usara este ponto para sincronizar as impressoras da maquina.",
            "impressoras_cadastradas": impressoras_cadastradas,
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoes_desktop(request):
    configuracoes = ConfiguracaoImpressao.objects.select_related("empresa", "filial").prefetch_related(
        "modelos_etiqueta", "modelos_etiqueta__terminal"
    ).filter(is_active=True).order_by(
        "empresa_id",
        "filial_id",
        "tipo_documento",
    )
    payload = []
    for config in configuracoes:
        payload.append(
            {
                "id": config.id,
                "empresa_id": config.empresa_id,
                "empresa": str(config.empresa),
                "filial_id": config.filial_id,
                "filial": str(config.filial) if config.filial else None,
                "tipo_documento": config.tipo_documento,
                "tipo_documento_label": config.get_tipo_documento_display(),
                "impressora_padrao": config.impressora_padrao,
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
                        for modelo in config.modelos_etiqueta.all()
                        if modelo.is_active
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
    return JsonResponse(
        {
            "status": "ok",
            "mensagem": "Configuracoes preparadas para sincronizacao com o app desktop local.",
            "configuracoes": payload,
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoes_padroes(request):
    if request.method != "POST":
        return redirect("configuracoes:impressoes")
    criadas = criar_configuracoes_padrao()
    if criadas:
        messages.success(request, f"{criadas} configuracao(oes) de impressao criada(s).")
    else:
        messages.info(request, "As configuracoes padrao ja estavam criadas.")
    return redirect("configuracoes:impressoes")


@login_required
@role_required(*SISTEMA)
def impressao_form(request, pk=None):
    configuracao = get_object_or_404(ConfiguracaoImpressao, pk=pk) if pk else None
    if request.method == "POST":
        form = ConfiguracaoImpressaoForm(request.POST, instance=configuracao)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuracao de impressao salva.")
            return redirect("configuracoes:impressoes")
    else:
        form = ConfiguracaoImpressaoForm(instance=configuracao)
    impressoras_cadastradas = [
        nome
        for nome in ConfiguracaoImpressao.objects.exclude(impressora_padrao="")
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
