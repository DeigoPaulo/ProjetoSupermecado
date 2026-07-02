from io import StringIO

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import SISTEMA, role_required

from .forms import ConfiguracaoImpressaoForm
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
            ("Sangria e suprimento", "done", "Exigem senha de supervisor/admin."),
            ("Estorno no PDV", "done", "PDV possui atalho F6 para cancelamento total de venda recente com motivo e senha de supervisor/admin; devolucao parcial segue pela tela da venda."),
            ("Operacao principal por teclado", "done", "Enter inclui produto; F2-F9 acessam funcoes; no carrinho, setas selecionam, Del exclui o produto e Ctrl+Del limpa a venda com confirmacao; no pagamento, Shift+ adiciona forma, Del remove forma e Enter confirma; Shift+M retorna ao menu."),
            ("Bip e retorno automatico de foco", "done", "Leitor envia Enter, inclui o produto, soma repeticoes e devolve o foco ao campo apos o recarregamento."),
            ("Alertas rapidos no PDV", "done", "Mensagens simples viram toasts temporarios; operacoes criticas continuam exigindo confirmacao ou supervisor."),
            ("Autorizacao do PDV em nuvem", "done", "Operador comum fica bloqueado em ambiente de nuvem, tentativa gera solicitacao, admin/gerente recebe alerta visual no topo/menu e decide pelo painel de aprovacao."),
            ("TEF/API de maquininha", "partial", "Pagamentos possuem estados controlados, ID externo, NSU e autorizacao; venda rejeita transacao pendente, recusada ou estornada. Falta conectar o adaptador do fornecedor TEF."),
            ("Reversao de pagamento misto", "partial", "Cancelamento total estorna parcelas locais e marca PIX/TEF com transacao externa como estorno pendente, preservando motivo e rastreabilidade. Falta automatizar a chamada ao fornecedor e ratear devolucoes parciais."),
            ("Padrao R$ em todos os formularios", "done", "Campos numericos de preco, valor, custo, desconto, taxa, frete e total recebem automaticamente o prefixo R$ no PDV e nas telas administrativas."),
        ],
    },
    {
        "titulo": "Produtos, estoque e compras",
        "descricao": "Cadastros e controle fisico/financeiro do estoque.",
        "itens": [
            ("Produtos, categorias e marcas", "done", "Cadastro, edicao, busca, importacao CSV, etiquetas e kardex."),
            ("Pendencias fiscais de produtos", "done", "Tela fiscal lista produtos com NCM, CEST, origem, CST/CSOSN ou aliquota pendentes e direciona para correcao do cadastro."),
            ("Promocoes", "done", "Preco vigente considera promocao ativa."),
            ("Estoque por filial", "done", "Saldo fisico, reservado e disponivel por produto/filial."),
            ("Inventario", "done", "Contagem e aplicacao com autorizacao de supervisor/admin."),
            ("Perdas", "done", "Baixa de perdas com supervisor/admin e log."),
            ("Movimentacao manual", "done", "Entrada/saida/ajuste/reserva com supervisor/admin e auditoria."),
            ("Compras", "done", "Entrada de compra com itens, finalizacao protegida e entrada em estoque."),
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
            ("Busca inteligente/autocomplete", "partial", "PDV possui buscas locais por teclado; Select2/autocomplete nos cadastros extensos ainda sera ampliado."),
            ("Consulta de CNPJ e CEP", "todo", "Preenchimento por API para empresas, fornecedores, clientes e enderecos ainda pendente."),
            ("Imagens de produto", "partial", "Foto principal cadastravel no produto para uso futuro no marketplace; galeria e processamento de multiplas imagens seguem pendentes."),
            ("Politicas de entrega por filial", "partial", "Raio, faixas por distancia, pedido minimo, frete gratis, bairros e horarios configuraveis implementados; geocodificacao automatica por mapa segue pendente."),
            ("Certificado digital protegido", "done", "Configuracao fiscal aceita upload A1 .pfx/.p12, criptografa arquivo e senha, le validade e mostra alertas de vencimento."),
            ("Identidade visual do supermercado", "done", "Logo no topo, marca dagua sutil no carrinho e paleta operacional restrita implementadas."),
        ],
    },
    {
        "titulo": "Proximas fases",
        "descricao": "Itens previstos na documentacao, ainda fora do MVP atual.",
        "itens": [
            ("Fiscal/NFC-e", "partial", "Fila fiscal mostra vendas prontas e pendencias antes da acao; tela de produtos fiscais antecipa correcoes de NCM, CEST, origem, CST/CSOSN e aliquota. XML local usa UF e codigo IBGE da filial; ainda faltam assinatura, schema oficial e transmissao SEFAZ."),
            ("Financeiro completo", "partial", "Contas a pagar/receber, baixas, cancelamentos, categorias, fluxo de caixa, conciliacao PDV x financeiro e exportacoes criadas."),
            ("Marketplace / pedido online", "partial", "Fluxo operacional completo e API segura com chave por plataforma, validacao de itens e idempotencia implementados; adaptadores especificos de cada parceiro seguem pendentes."),
            ("Impressao personalizada", "done", "Configuracoes de papel, margens, fonte, rodape, vias e impressao automatica aplicadas aos recibos."),
            ("Descoberta de impressoras locais", "todo", "No app desktop, listar as impressoras instaladas na maquina e gravar a escolha na central de impressao."),
            ("Backup/restauracao operacional", "done", "Tela de backup JSON e roteiro de restauracao segura disponiveis em Sistema."),
            ("Aplicativo desktop/PDF", "todo", "Planejado para etapa posterior."),
            ("Super admin personalizado", "todo", "Criar painel administrativo proprio e substituir o uso visual do admin padrao do Django."),
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
        "sem_impressora": configuracoes.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
    }
    return render(request, "configuracoes/impressoes.html", {"configuracoes": configuracoes, "resumo": resumo})


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
    return render(request, "configuracoes/impressao_form.html", {"form": form, "configuracao": configuracao})

# Create your views here.
