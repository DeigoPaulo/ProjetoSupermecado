from io import StringIO

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import SISTEMA, role_required
from apps.empresas.models import Empresa, EventoSincronizacao, Filial, StatusSincronizacao
from apps.fiscal.models import ConfiguracaoFiscal
from apps.pdv.models import AcessoPdvNuvem, StatusAcessoPdvNuvem, TerminalPdv
from apps.vendas.models import FormaPagamento

from .forms import ConfiguracaoImpressaoForm, FormaPagamentoForm, TerminalPdvForm
from .models import ConfiguracaoImpressao
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
            ("Arquitetura PDV desktop local", "partial", "PDV dos caixas deve ser um aplicativo instalado na maquina do operador, com tela enxuta de venda, pagamento, caixa, consulta e estorno autorizado, sem telas administrativas completas. O app se comunica com o servidor local da loja pela rede interna; esse servidor local conversa com impressora, balanca, gaveta, TEF e banco operacional da filial. Cadastro por filial, chave individual protegida por hash e bootstrap com registro de conexao implementados. A nuvem/sede sincroniza por API segura, filas e eventos, sem acessar diretamente o banco local do supermercado."),
            ("TEF/API de maquininha", "partial", "Pagamentos possuem estados controlados, ID externo, NSU e autorizacao; venda rejeita transacao pendente, recusada ou estornada. Pagamentos eletronicos confirmados sem retorno real recebem autorizacao simulada rastreavel, deixando o ponto de troca pronto para o app desktop conectar credito, debito e PIX dinamico ao TEF/API, enviar o valor para a maquininha/provedor e aguardar aprovado, recusado, cancelado ou expirado antes de liberar a venda."),
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
        "titulo": "Proximas fases",
        "descricao": "Itens previstos na documentacao, ainda fora do MVP atual.",
        "itens": [
            ("Fiscal/NFC-e", "partial", "Fila fiscal mostra vendas prontas e pendencias antes da acao; tela de produtos fiscais antecipa correcoes de NCM, CEST, origem, CST/CSOSN e aliquota. XML local usa UF e codigo IBGE da filial. A NFC-e deve ser emitida somente apos pagamento confirmado, com contingencia quando a SEFAZ estiver indisponivel; ainda faltam assinatura, schema oficial e transmissao SEFAZ."),
            ("Financeiro completo", "partial", "Contas a pagar/receber, baixas, cancelamentos, categorias, fluxo de caixa, conciliacao PDV x financeiro, contas de movimento, vendas a vista do PDV no livro, transferencias entre contas, livro financeiro imutavel, estornos por lancamento inverso, resultado por receitas/despesas, cards gerenciais e exportacoes criadas. A proxima evolucao inclui integracao final com fiscal/contabilidade e relatorios contabeis oficiais."),
            ("Entradas, saidas e livro contabil", "partial", "Contas de movimento por filial para caixa fisico, banco, PIX e outras foram criadas com saldo inicial e saldo atual. Baixas geram entrada ou saida no livro imutavel, vendas a vista do PDV geram entradas automaticas por forma de pagamento, sangria e suprimento geram saida/entrada automatica no Caixa PDV, transferencias geram lancamentos espelhados, atomicos e auditados entre contas da mesma empresa, e estornos rastreaveis criam lancamento inverso sem alterar o original. O livro possui origem, usuario, data, filtros, exportacao CSV, validacao de saldo e relatorio de receitas, despesas e resultado que ignora transferencias internas. Ainda faltam integracao automatica de origens fiscais/contabeis avancadas e relatorios contabeis oficiais. Referencia funcional identificada no ProjetoLimpoGitHub para migracao adaptada, sem alterar o projeto original."),
            ("Marketplace / pedido online", "partial", "Fluxo operacional completo, API segura com chave por plataforma, validacao de itens, idempotencia e acompanhamento visual de separacao/pagamento na listagem implementados; adaptadores especificos de cada parceiro seguem pendentes."),
            ("Impressao personalizada", "done", "Configuracoes de papel, margens, fonte, rodape, vias e impressao automatica aplicadas aos recibos."),
            ("Descoberta de impressoras locais", "partial", "Central de impressao ja possui campo com sugestoes, aviso operacional e endpoint JSON preparado para o app desktop listar impressoras instaladas na maquina."),
            ("Gaveta de dinheiro opcional", "partial", "Central de impressao permite habilitar ou desabilitar gaveta automatica por empresa/filial e documento de caixa. Falta o app desktop acionar a impressora ESC-POS por pulso fisico em dinheiro, troco, sangria, suprimento, abertura e fechamento autorizados. Quando desabilitada ou indisponivel, a venda nao deve ser bloqueada; apenas registrar aviso/log operacional."),
            ("Backup/restauracao operacional", "done", "Tela de backup JSON e roteiro de restauracao segura disponiveis em Sistema."),
            ("Aplicativo desktop/PDF", "partial", "Endpoints de configuracao e payload de impressao da venda preparados para o app desktop, incluindo dados de pagamento eletronico, NSU, autorizacao e transacao externa para cupom e comprovante. Falta empacotar o aplicativo dos caixas, conectar dispositivos locais e implementar sincronizacao resiliente com servidor local/nuvem."),
            ("Sincronizacao loja-nuvem", "partial", "Empresa escolhe entre servidor local, hibrido e nuvem com agente. Caixa de saida, processador HTTP e caixa de entrada autenticada usam UUID, idempotencia, token fora do banco, timeout, lotes e retentativa exponencial. Eventos recebidos ficam armazenados antes de alterar dados e ja passam por processador interno com handlers por tipo, erro controlado para dominios ainda nao implementados, handler inicial de produtos, handler de saldo de estoque por filial, espelho de venda finalizada com painel de retaguarda, espelho fiscal sincronizado, detalhe auditavel de eventos com payload e diagnostico, resolucao manual de conflitos com responsavel e decisao registrada, exportacao CSV das filas de saida e entrada, comando unico agendavel e roteiro do Agendador de Tarefas do Windows no painel. Ainda faltam instalar o agendador Windows no servidor, transmissao SEFAZ real e politicas automaticas finais de resolucao de conflitos."),
            ("Super admin personalizado", "partial", "Painel proprio centraliza empresas, usuarios, fiscal, formas de pagamento, impressoes, backup, auditoria e checklist, sem atalho visual para o admin Django; ainda faltam telas internas para alguns modelos avancados."),
        ],
    },
]

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
    chave_nova = request.session.pop("terminal_pdv_chave_nova", None)
    return render(request, "configuracoes/terminais_pdv.html", {"terminais": terminais, "chave_nova": chave_nova})


@login_required
@role_required(*SISTEMA)
def terminal_pdv_form(request, pk=None):
    terminal = get_object_or_404(TerminalPdv, pk=pk) if pk else None
    form = TerminalPdvForm(request.POST or None, instance=terminal)
    if request.method == "POST" and form.is_valid():
        terminal = form.save(commit=False)
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
        },
    )


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
    configuracoes = ConfiguracaoImpressao.objects.select_related("empresa", "filial").filter(is_active=True).order_by(
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
