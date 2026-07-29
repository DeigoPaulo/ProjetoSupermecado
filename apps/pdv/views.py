import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, ListView

from apps.accounts.permissions import ADMINISTRACAO, PDV, SUPERVISAO, RoleRequiredMixin, has_role, role_required, supervisor_from_request
from apps.auditoria.models import LogAuditoria
from apps.clientes.escopo import clientes_para_usuario
from apps.clientes.models import Cliente
from apps.configuracoes.artifacts import artefato_pdv_desktop as _artefato_atualizacao_pdv
from apps.configuracoes.models import TipoDocumentoImpressao
from apps.configuracoes.services import configuracao_impressao_para, estilos_impressao
from apps.empresas.models import Filial
from apps.estoque.models import Estoque
from apps.financeiro.models import LancamentoFinanceiro, TipoLancamentoFinanceiro
from apps.financeiro.services import conta_caixa_pdv, registrar_lancamento
from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.fiscal.qrcode_nfce import gerar_qrcode_data_uri, obter_url_qrcode_nfce
from apps.produtos.models import Produto
from apps.promocoes.models import PromocaoProduto
from apps.promocoes.services import preco_atual_produto, promocao_ativa_para_produto
from apps.vendas.models import EstornoParcialPagamento, FormaPagamento, PagamentoVenda, PreVenda, StatusEstornoParcial, StatusPagamento, StatusPreVenda, Venda
from apps.vendas.services import calcular_item, cancelar_pre_venda, cancelar_venda, confirmar_estorno_pagamento_eletronico, confirmar_estorno_parcial_eletronico, converter_pre_venda, criar_pre_venda, finalizar_venda, forma_pagamento_disponivel, formas_pagamento_disponiveis, quantidade_devolvida_item, registrar_devolucao_venda

from .forms import AbrirCaixaForm, AdicionarItemForm, ConferirCaixaForm, FecharCaixaForm, FinalizarVendaForm, PreVendaForm, SangriaForm, SuprimentoForm
from .models import AcessoPdvNuvem, Caixa, CanalAtualizacaoPdv, EventoDispositivoTerminal, Sangria, StatusAcessoPdvNuvem, StatusCaixa, Suprimento, TerminalPdv
from .services_acesso import acesso_pdv_nuvem_aprovado, decidir_acesso_pdv_nuvem, solicitar_acesso_pdv_nuvem


CART_SESSION_KEY = "pdv_cart"
PRE_VENDA_SESSION_KEY = "pdv_pre_venda_id"
CASH_DRAWER_SESSION_KEY = "pdv_cash_drawer_action"


def _versao_em_partes(valor):
    try:
        return tuple(int(parte) for parte in str(valor).split("."))
    except (TypeError, ValueError):
        return ()

def _politica_atualizacao_terminal(terminal, versao_cliente):
    canal_versao = str(getattr(settings, "PDV_DESKTOP_RELEASE_CHANNEL", CanalAtualizacaoPdv.ESTAVEL)).upper()
    if canal_versao not in CanalAtualizacaoPdv.values:
        canal_versao = CanalAtualizacaoPdv.ESTAVEL
    partes_cliente = _versao_em_partes(versao_cliente)
    possui_atualizacao = bool(partes_cliente and partes_cliente < _versao_em_partes(settings.PDV_DESKTOP_VERSION))
    obrigatoria = bool(partes_cliente and partes_cliente < _versao_em_partes(settings.PDV_DESKTOP_MIN_VERSION))
    elegivel_canal = canal_versao == CanalAtualizacaoPdv.ESTAVEL or terminal.canal_atualizacao == CanalAtualizacaoPdv.PILOTO
    liberada = obrigatoria or (elegivel_canal and not terminal.bloquear_atualizacoes)
    if obrigatoria:
        motivo = "versao_abaixo_do_minimo"
    elif terminal.bloquear_atualizacoes:
        motivo = "terminal_congelado"
    elif not elegivel_canal:
        motivo = "aguardando_canal_estavel"
    elif possui_atualizacao:
        motivo = "atualizacao_liberada"
    else:
        motivo = "versao_atual"
    return {
        "canal_terminal": terminal.canal_atualizacao,
        "canal_versao": canal_versao,
        "bloqueada_pelo_admin": terminal.bloquear_atualizacoes,
        "elegivel_canal": elegivel_canal,
        "possui_atualizacao": possui_atualizacao,
        "atualizacao_liberada": liberada,
        "atualizacao_disponivel": possui_atualizacao and liberada,
        "atualizacao_obrigatoria": obrigatoria,
        "motivo": motivo,
    }


def _autenticar_terminal_api(request, acao_sem_licenca):
    identificador = request.headers.get("X-Terminal-ID", "").strip()
    chave = request.headers.get("X-Terminal-Key", "").strip()
    if not identificador or not chave:
        return None, JsonResponse({"status": "nao_autorizado", "mensagem": "Credenciais do terminal ausentes."}, status=401)

    try:
        terminal = TerminalPdv.objects.select_related("filial", "filial__empresa").get(identificador=identificador)
    except (TerminalPdv.DoesNotExist, ValueError):
        return None, JsonResponse({"status": "nao_autorizado", "mensagem": "Credenciais do terminal invalidas."}, status=401)

    if not terminal.validar_chave_api(chave):
        return None, JsonResponse({"status": "nao_autorizado", "mensagem": "Credenciais do terminal invalidas."}, status=401)
    if not terminal.ativo:
        return None, JsonResponse({"status": "terminal_inativo", "mensagem": "Este terminal foi desativado pelo administrador."}, status=403)
    if not terminal.licenca_liberada:
        LogAuditoria.objects.create(
            usuario=None,
            modulo="pdv",
            acao=acao_sem_licenca,
            descricao=(
                f"Requisicao recusada para terminal {terminal.nome} ({terminal.identificador}) "
                f"com licenca {terminal.get_status_licenca_display()}."
            ),
            objeto_tipo="TerminalPdv",
            objeto_id=str(terminal.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return None, JsonResponse(
            {
                "status": "licenca_terminal_bloqueada",
                "mensagem": "Licenca do terminal pendente, bloqueada ou cancelada.",
                "licenca": {"status": terminal.status_licenca, "liberada": False},
            },
            status=403,
        )
    return terminal, None


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


def _agendar_abertura_gaveta(request, caixa, motivo, origem):
    impressao = configuracao_impressao_para(caixa.filial, TipoDocumentoImpressao.CUPOM_NAO_FISCAL)
    if not impressao or not impressao.gaveta_automatica:
        return
    if origem == "pagamento_em_dinheiro" and not impressao.abrir_gaveta_em_dinheiro:
        return
    if origem != "pagamento_em_dinheiro" and not impressao.abrir_gaveta_em_movimento_caixa:
        return
    request.session[CASH_DRAWER_SESSION_KEY] = {
        "motivo": motivo,
        "origem": origem,
        "caixa_id": caixa.id,
    }
    request.session.modified = True


@require_GET
def terminal_bootstrap(request):
    identificador = request.headers.get("X-Terminal-ID", "").strip()
    chave = request.headers.get("X-Terminal-Key", "").strip()
    versao_cliente = request.headers.get("X-PDV-Version", "").strip()
    if not identificador or not chave:
        return JsonResponse({"status": "nao_autorizado", "mensagem": "Credenciais do terminal ausentes."}, status=401)

    try:
        terminal = TerminalPdv.objects.select_related("filial", "filial__empresa").get(identificador=identificador)
    except (TerminalPdv.DoesNotExist, ValueError):
        return JsonResponse({"status": "nao_autorizado", "mensagem": "Credenciais do terminal invalidas."}, status=401)

    if not terminal.validar_chave_api(chave):
        return JsonResponse({"status": "nao_autorizado", "mensagem": "Credenciais do terminal invalidas."}, status=401)
    if not terminal.ativo:
        return JsonResponse({"status": "terminal_inativo", "mensagem": "Este terminal foi desativado pelo administrador."}, status=403)
    if not terminal.licenca_liberada:
        LogAuditoria.objects.create(
            usuario=None,
            modulo="pdv",
            acao="BOOTSTRAP_TERMINAL_SEM_LICENCA",
            descricao=(
                f"Bootstrap recusado para terminal {terminal.nome} ({terminal.identificador}) "
                f"com licenca {terminal.get_status_licenca_display()}."
            ),
            objeto_tipo="TerminalPdv",
            objeto_id=str(terminal.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return JsonResponse(
            {
                "status": "licenca_terminal_bloqueada",
                "mensagem": "Licenca do terminal pendente, bloqueada ou cancelada.",
                "licenca": {"status": terminal.status_licenca, "liberada": False},
            },
            status=403,
        )

    terminal.ultima_conexao = timezone.now()
    terminal.ultimo_ip = request.META.get("REMOTE_ADDR") or None
    terminal.save(update_fields=["ultima_conexao", "ultimo_ip", "atualizado_em"])
    versao_vigente = settings.PDV_DESKTOP_VERSION
    versao_minima = settings.PDV_DESKTOP_MIN_VERSION
    politica_atualizacao = _politica_atualizacao_terminal(terminal, versao_cliente)
    artefato_atualizacao = _artefato_atualizacao_pdv()
    pacote_atualizacao_liberado = artefato_atualizacao["disponivel"] and politica_atualizacao["atualizacao_disponivel"]
    return JsonResponse(
        {
            "status": "ok",
            "terminal": {
                "identificador": str(terminal.identificador),
                "nome": terminal.nome,
                "permite_modo_offline": terminal.permite_modo_offline,
                "emite_documento_fiscal": terminal.emite_documento_fiscal,
                "provedor_tef": terminal.provedor_tef,
                "modo_integracao_tef": terminal.modo_integracao_tef,
                "licenca": {"status": terminal.status_licenca, "liberada": True},
            },
            "licenciamento": {
                "modelo": "por_terminal",
                "status": terminal.status_licenca,
                "terminal_autorizado": terminal.licenca_liberada,
            },
            "aplicativo": {
                "versao_cliente": versao_cliente or None,
                "versao_vigente": versao_vigente,
                "versao_minima": versao_minima,
                "atualizacao_disponivel": politica_atualizacao["atualizacao_disponivel"],
                "atualizacao_obrigatoria": politica_atualizacao["atualizacao_obrigatoria"],
                "atualizacao_requer_admin_master": True,
                "politica_atualizacao": politica_atualizacao,
                "pacote": {
                    "disponivel": pacote_atualizacao_liberado,
                    "nome": artefato_atualizacao["nome"] if pacote_atualizacao_liberado else "",
                    "sha256": artefato_atualizacao["sha256"] if pacote_atualizacao_liberado else "",
                    "url": request.build_absolute_uri("/pdv/api/terminal/update/") if pacote_atualizacao_liberado else "",
                    "instalacao_automatica": False,
                },
            },
            "filial": {
                "id": terminal.filial_id,
                "nome": terminal.filial.nome,
                "empresa": str(terminal.filial.empresa),
            },
            "recursos": {
                "venda_local": True,
                "impressao_desktop": True,
                "sincronizacao_assincrona": True,
                "modo_offline_permitido": terminal.permite_modo_offline,
                "emissao_fiscal_automatica": terminal.emite_documento_fiscal,
                "tef_integrado": terminal.provedor_tef != "NAO_CONFIGURADO",
                "balanca_local": terminal.usa_balanca,
            },
            "dispositivos": {
                "balanca": terminal.balanca_configuracao(),
                "gaveta": _configuracao_gaveta_terminal(terminal.filial),
            },
            "tef": {
                "provedor": terminal.provedor_tef,
                "modo_integracao": terminal.modo_integracao_tef,
                "simulador_permitido": settings.PDV_TEF_SIMULATOR_ENABLED,
                "contrato": "pdv_tef_v1",
                "tipos_pagamento": ["CREDITO", "DEBITO", "PIX", "VALE_ALIMENTACAO", "VALE_REFEICAO"],
                "recursos_opcionais": ["captura_documento_consumidor"],
                "captura_documento_consumidor": "NEGOCIADA_NO_DESKTOP",
                "retorno_esperado": ["status", "transacao_externa_id", "nsu", "codigo_autorizacao", "mensagem_processadora"],
            },
            "servidor_em": timezone.localtime().isoformat(),
        }
    )

@require_GET
def terminal_update_download(request):
    terminal, erro = _autenticar_terminal_api(request, "DOWNLOAD_ATUALIZACAO_SEM_LICENCA")
    if erro:
        return erro
    politica_atualizacao = _politica_atualizacao_terminal(
        terminal,
        request.headers.get("X-PDV-Version", "").strip(),
    )
    if not politica_atualizacao["atualizacao_disponivel"]:
        LogAuditoria.objects.create(
            usuario=None,
            modulo="pdv",
            acao="DOWNLOAD_ATUALIZACAO_NAO_LIBERADA",
            descricao=f"Download recusado para terminal {terminal.nome}: {politica_atualizacao['motivo']}.",
            objeto_tipo="TerminalPdv",
            objeto_id=str(terminal.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return JsonResponse(
            {
                "status": "atualizacao_nao_liberada",
                "mensagem": "A atualizacao nao esta liberada para este terminal.",
                "politica_atualizacao": politica_atualizacao,
            },
            status=403,
        )
    artefato = _artefato_atualizacao_pdv()
    if not artefato["publicavel"]:
        raise Http404("Atualizacao do PDV desktop ainda nao publicada.")
    LogAuditoria.objects.create(
        usuario=None,
        modulo="pdv",
        acao="DOWNLOAD_ATUALIZACAO_PDV_DESKTOP",
        descricao=f"Terminal {terminal.nome} baixou o pacote {artefato['nome']}.",
        objeto_tipo="TerminalPdv",
        objeto_id=str(terminal.id),
        ip=request.META.get("REMOTE_ADDR"),
    )
    response = FileResponse(artefato["caminho"].open("rb"), as_attachment=True, filename=artefato["nome"])
    response["X-PDV-Version"] = settings.PDV_DESKTOP_VERSION
    response["X-PDV-SHA256"] = artefato["sha256"]
    return response

@csrf_exempt
@require_POST
def terminal_device_events(request):
    terminal, erro = _autenticar_terminal_api(request, "EVENTOS_DISPOSITIVO_TERMINAL_SEM_LICENCA")
    if erro:
        return erro
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"status": "erro", "mensagem": "JSON invalido."}, status=400)

    eventos = payload.get("eventos", [])
    if not isinstance(eventos, list):
        return JsonResponse({"status": "erro", "mensagem": "Campo eventos deve ser uma lista."}, status=400)

    lote = eventos[:100]
    ids_informados = {
        str(evento.get("id") or "").strip()[:80]
        for evento in lote
        if isinstance(evento, dict) and str(evento.get("id") or "").strip()
    }
    ids_existentes = set(
        EventoDispositivoTerminal.objects.filter(terminal=terminal, evento_id__in=ids_informados)
        .values_list("evento_id", flat=True)
    )
    ids_lote = set()
    objetos = []
    processados = 0
    duplicados = 0
    for evento in lote:
        if not isinstance(evento, dict):
            continue
        processados += 1
        evento_id = str(evento.get("id") or "").strip()[:80] or None
        if evento_id and (evento_id in ids_existentes or evento_id in ids_lote):
            duplicados += 1
            continue
        if evento_id:
            ids_lote.add(evento_id)
        evento_payload = evento.get("payload") if isinstance(evento.get("payload"), dict) else {}
        tipo = str(evento.get("tipo") or evento_payload.get("tipo") or "desconhecido")[:40]
        status = str(evento.get("status") or evento_payload.get("status") or "")[:40]
        mensagem = str(evento.get("mensagem") or evento_payload.get("mensagem") or "")[:255]
        ocorrido_em = parse_datetime(str(evento.get("em"))) if evento.get("em") else None
        if ocorrido_em and timezone.is_naive(ocorrido_em):
            ocorrido_em = timezone.make_aware(ocorrido_em)
        objetos.append(
            EventoDispositivoTerminal(
                terminal=terminal,
                evento_id=evento_id,
                tipo=tipo,
                status=status,
                mensagem=mensagem,
                payload=evento_payload or evento,
                ocorrido_em=ocorrido_em,
            )
        )

    if objetos:
        EventoDispositivoTerminal.objects.bulk_create(objetos, ignore_conflicts=True)
    return JsonResponse(
        {
            "status": "ok",
            "recebidos": len(objetos),
            "processados": processados,
            "duplicados": duplicados,
            "ignorados": len(lote) - processados,
        }
    )


def _filial_do_usuario(user):
    perfil = getattr(user, "perfil_supermercado", None)
    if not perfil or not perfil.is_active or not perfil.filial_id or not perfil.filial.is_active:
        return None
    return perfil.filial


def _empresa_id_do_usuario(user):
    if user.is_superuser:
        return None
    filial = _filial_do_usuario(user)
    return filial.empresa_id if filial else 0


def _escopo_empresa_pdv(user, queryset, campo="filial__empresa_id"):
    empresa_id = _empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    if not empresa_id:
        return queryset.none()
    if has_role(user, ADMINISTRACAO):
        return queryset.filter(**{campo: empresa_id})
    filial = _filial_do_usuario(user)
    if not filial:
        return queryset.none()
    campo_filial = "id" if campo == "empresa_id" else f"{campo.removesuffix('__empresa_id')}_id"
    return queryset.filter(**{campo_filial: filial.id})


def _documento_fiscal_imprimivel(venda):
    return (
        DocumentoFiscal.objects.select_related("filial__empresa", "venda__cliente", "natureza_operacao")
        .prefetch_related("venda__itens__produto", "venda__pagamentos__forma_pagamento")
        .filter(
            venda=venda,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            status__in=[StatusDocumentoFiscal.EMITIDO, StatusDocumentoFiscal.CONTINGENCIA],
        )
        .order_by("-criado_em")
        .first()
    )


def _contexto_danfe_pdv(documento):
    contexto = {"documento": documento, "qrcode_data_uri": "", "qrcode_erro": ""}
    try:
        url = obter_url_qrcode_nfce(documento)
        contexto["qrcode_data_uri"] = gerar_qrcode_data_uri(url)
    except (ValidationError, ConfiguracaoFiscal.DoesNotExist) as exc:
        contexto["qrcode_erro"] = "; ".join(getattr(exc, "messages", [str(exc)]))
    return contexto


def _terminal_da_requisicao(request):
    identificador = request.headers.get("X-Terminal-ID", "").strip()
    if not identificador:
        return None
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").filter(ativo=True)
    return _escopo_empresa_pdv(request.user, terminais).filter(identificador=identificador).first()


def _bloqueio_pdv_nuvem(request):
    if not settings.PDV_NUVEM_REQUER_APROVACAO or has_role(request.user, SUPERVISAO):
        return None
    filial = _filial_do_usuario(request.user)
    if acesso_pdv_nuvem_aprovado(request.user, filial):
        return None
    solicitacao, criada = solicitar_acesso_pdv_nuvem(
        usuario=request.user,
        filial=filial,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        justificativa="Tentativa de acesso ao PDV em nuvem.",
    )
    return render(request, "pdv/acesso_pdv_nuvem_pendente.html", {"solicitacao": solicitacao, "criada": criada}, status=403)


def _get_cart(request):
    return request.session.get(CART_SESSION_KEY, {})


def _save_cart(request, cart):
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def _cart_items(cart):
    produtos = Produto.objects.filter(id__in=cart.keys()).select_related("categoria", "marca")
    produtos_map = {str(produto.id): produto for produto in produtos}
    items = []
    total = Decimal("0.00")
    for produto_id, quantidade_texto in cart.items():
        produto = produtos_map.get(str(produto_id))
        if not produto:
            continue
        quantidade = Decimal(quantidade_texto)
        subtotal = calcular_item(produto, quantidade)
        total += subtotal
        items.append({"produto": produto, "quantidade": quantidade, "subtotal": subtotal})
    return items, total


def _decimal_from_text(value):
    try:
        return Decimal(str(value or "0").replace(".", "").replace(",", "."))
    except InvalidOperation:
        return Decimal("0.00")


def _moeda_json(valor):
    return f"{Decimal(valor or 0):.2f}"


def _quantidade_json(valor):
    quantidade = Decimal(valor or 0)
    if quantidade == quantidade.to_integral_value():
        return f"{quantidade:.0f}"
    return f"{quantidade:.3f}".replace(".", ",")


def _pagamentos_from_request(request, total_liquido, filial):
    formas = request.POST.getlist("pagamento_forma")
    valores = request.POST.getlist("pagamento_valor")
    status_list = request.POST.getlist("pagamento_status")
    transacoes = request.POST.getlist("pagamento_transacao_externa_id")
    nsus = request.POST.getlist("pagamento_nsu")
    autorizacoes = request.POST.getlist("pagamento_codigo_autorizacao")
    mensagens = request.POST.getlist("pagamento_mensagem_processadora")
    pagamentos_lancados = []
    formas_eletronicas = {"PIX", "CARTAO", "DEBITO", "CREDITO", "VALE_ALIMENTACAO", "VALE_REFEICAO"}
    for indice, (forma_id, valor_texto) in enumerate(zip(formas, valores)):
        valor = _decimal_from_text(valor_texto)
        if not forma_id and valor <= 0:
            continue
        if not forma_id:
            raise ValidationError("Informe a forma de pagamento.")
        if valor <= 0:
            raise ValidationError("Informe um valor de pagamento maior que zero.")
        forma = forma_pagamento_disponivel(filial, forma_id)
        if not forma:
            raise ValidationError("Forma de pagamento invalida.")
        tipo = (forma.tipo or "").upper()
        status = (status_list[indice] if indice < len(status_list) else "").strip()
        transacao = (transacoes[indice] if indice < len(transacoes) else "").strip()
        nsu = (nsus[indice] if indice < len(nsus) else "").strip()
        autorizacao = (autorizacoes[indice] if indice < len(autorizacoes) else "").strip()
        mensagem = (mensagens[indice] if indice < len(mensagens) else "").strip()
        if tipo in formas_eletronicas:
            if status != StatusPagamento.CONFIRMADO or not (transacao and nsu and autorizacao):
                raise ValidationError("Pagamento eletronico deve ser aprovado pela maquininha antes de finalizar.")
        pagamentos_lancados.append(
            {
                "forma_pagamento": forma,
                "valor": valor,
                "status": status or StatusPagamento.CONFIRMADO,
                "transacao_externa_id": transacao,
                "nsu": nsu,
                "codigo_autorizacao": autorizacao,
                "mensagem_processadora": mensagem,
            }
        )

    if not pagamentos_lancados:
        raise ValidationError("Informe ao menos uma forma de pagamento.")

    total_pago = sum((item["valor"] for item in pagamentos_lancados), Decimal("0.00"))
    if total_pago < total_liquido:
        raise ValidationError("A soma dos pagamentos nao pode ser menor que o total final.")

    restante = total_liquido
    pagamentos = []
    for item in pagamentos_lancados:
        if restante <= 0:
            break
        valor_registrado = min(item["valor"], restante)
        pagamento = item.copy()
        pagamento["valor"] = valor_registrado
        pagamentos.append(pagamento)
        restante -= valor_registrado
    return pagamentos, total_pago


@login_required
@role_required(*PDV)
def pdv(request):
    bloqueio = _bloqueio_pdv_nuvem(request)
    if bloqueio:
        return bloqueio

    cart = _get_cart(request)

    if request.method == "POST" and request.POST.get("action") == "add":
        add_form = AdicionarItemForm(request.POST)
        finish_form = FinalizarVendaForm(user=request.user)
        pre_venda_form = PreVendaForm(user=request.user)
        if add_form.is_valid():
            busca = add_form.cleaned_data["busca"].strip()
            quantidade = add_form.cleaned_data["quantidade"]
            produto = Produto.objects.filter(Q(codigo_barras=busca) | Q(nome__icontains=busca)).first()
            if produto:
                produto_id = str(produto.id)
                atual = Decimal(cart.get(produto_id, "0"))
                cart[produto_id] = str(atual + quantidade)
                _save_cart(request, cart)
                messages.success(request, "Item incluido no carrinho.")
                return redirect("pdv:pdv")
            messages.error(request, "Produto nao encontrado.")
    elif request.method == "POST" and request.POST.get("action") == "finish":
        add_form = AdicionarItemForm()
        finish_form = FinalizarVendaForm(request.POST, user=request.user)
        pre_venda_form = PreVendaForm(user=request.user)
        if finish_form.is_valid():
            items, total = _cart_items(cart)
            dados_venda = finish_form.cleaned_data.copy()
            valor_recebido = dados_venda.pop("valor_recebido", None)
            supervisor_desconto = None
            if dados_venda["desconto"] > 0:
                try:
                    supervisor_desconto = supervisor_from_request(request)
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
                    return redirect("pdv:pdv")
            total_liquido = total - dados_venda["desconto"]
            try:
                pagamentos, total_pago = _pagamentos_from_request(request, total_liquido, dados_venda["caixa"].filial)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("pdv:pdv")
            valor_base_troco = valor_recebido if valor_recebido is not None else total_pago
            if valor_base_troco is not None and valor_base_troco < total_liquido:
                messages.error(request, "Valor pago pelo cliente nao pode ser menor que o total final.")
                return redirect("pdv:pdv")
            try:
                terminal = _terminal_da_requisicao(request)
                venda = finalizar_venda(
                    usuario=request.user,
                    itens=items,
                    pagamentos=pagamentos,
                    preparar_fiscal=terminal.emite_documento_fiscal if terminal else True,
                    **dados_venda,
                )
                pre_venda_id = request.session.get(PRE_VENDA_SESSION_KEY)
                if pre_venda_id:
                    pre_venda = _escopo_empresa_pdv(
                        request.user,
                        PreVenda.objects.filter(status=StatusPreVenda.ABERTA),
                    ).filter(id=pre_venda_id).first()
                    if pre_venda:
                        converter_pre_venda(pre_venda=pre_venda, venda=venda)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                _save_cart(request, {})
                request.session.pop(PRE_VENDA_SESSION_KEY, None)
                request.session["pdv_ultima_venda_id"] = venda.id
                if supervisor_desconto:
                    LogAuditoria.objects.create(
                        usuario=supervisor_desconto,
                        modulo="pdv",
                        acao="AUTORIZACAO_DESCONTO_PDV",
                        descricao=(
                            f"Desconto de R$ {venda.desconto:.2f} autorizado na venda {venda.id}. "
                            f"Operador: {request.user.username}. Supervisor: {supervisor_desconto.username}."
                        ),
                        objeto_tipo="Venda",
                        objeto_id=str(venda.id),
                        ip=request.META.get("REMOTE_ADDR"),
                    )
                if any(pagamento["forma_pagamento"].tipo == "DINHEIRO" for pagamento in pagamentos):
                    _agendar_abertura_gaveta(request, venda.caixa, f"venda_{venda.id}_dinheiro", "pagamento_em_dinheiro")
                request.session.modified = True
                messages.success(request, f"Venda {venda.id} finalizada com sucesso.")
                return redirect("pdv:pdv")
    elif request.method == "POST" and request.POST.get("action") == "save_pre_venda":
        add_form = AdicionarItemForm()
        finish_form = FinalizarVendaForm(user=request.user)
        pre_venda_form = PreVendaForm(request.POST, user=request.user)
        if pre_venda_form.is_valid():
            items, _ = _cart_items(cart)
            try:
                pre_venda = criar_pre_venda(usuario=request.user, itens=items, **pre_venda_form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                _save_cart(request, {})
                request.session.pop(PRE_VENDA_SESSION_KEY, None)
                request.session.modified = True
                messages.success(request, f"DAV {pre_venda.id} salvo com sucesso.")
                return redirect("pdv:pre_venda_detalhe", pre_venda_id=pre_venda.id)
    else:
        add_form = AdicionarItemForm()
        finish_form = FinalizarVendaForm(user=request.user)
        pre_venda_form = PreVendaForm(user=request.user)

    items, total = _cart_items(cart)
    quantidade_itens = sum((item["quantidade"] for item in items), Decimal("0.000"))
    terminal_requisicao = _terminal_da_requisicao(request)
    caixas_escopo = _escopo_empresa_pdv(
        request.user,
        Caixa.objects.select_related("filial", "filial__empresa", "usuario_abertura", "usuario_fechamento"),
    )
    vendas_escopo = _escopo_empresa_pdv(
        request.user,
        Venda.objects.select_related("filial", "caixa", "cliente", "usuario"),
    )
    pre_vendas_escopo = _escopo_empresa_pdv(request.user, PreVenda.objects.all())
    filiais_escopo = _escopo_empresa_pdv(
        request.user,
        Filial.objects.select_related("empresa").filter(is_active=True),
        campo="empresa_id",
    )
    caixa_aberto = caixas_escopo.filter(status=StatusCaixa.ABERTO, usuario_abertura=request.user).first()
    filial_visual = caixa_aberto.filial if caixa_aberto else (_filial_do_usuario(request.user) or filiais_escopo.first())
    caixas_recentes = caixas_escopo.order_by("-data_abertura")[:8]
    caixas_aguardando_conferencia = caixas_escopo.filter(status=StatusCaixa.FECHADO).order_by("-data_fechamento")[:5]
    vendas_recentes = vendas_escopo.filter(status="FINALIZADA").order_by("-data")[:8]
    pre_venda_origem = None
    if request.session.get(PRE_VENDA_SESSION_KEY):
        pre_venda_origem = pre_vendas_escopo.filter(id=request.session[PRE_VENDA_SESSION_KEY]).first()
    ultima_venda = None
    ultima_venda_id = request.session.pop("pdv_ultima_venda_id", None)
    if ultima_venda_id:
        ultima_venda = vendas_escopo.filter(id=ultima_venda_id).first()
        request.session.modified = True
    produtos_rapidos = Produto.objects.select_related("categoria", "marca").filter(is_active=True, vendido_no_pdv=True).order_by("nome")[:24]
    promocoes_rapidas = PromocaoProduto.objects.select_related("produto").filter(ativa=True, inicio__lte=timezone.now(), fim__gte=timezone.now()).order_by("produto__nome")[:16]
    return render(
        request,
        "pdv/pdv.html",
        {
            "add_form": add_form,
            "finish_form": finish_form,
            "pre_venda_form": pre_venda_form,
            "items": items,
            "quantidade_itens": quantidade_itens,
            "total": total,
            "terminal_requisicao": terminal_requisicao,
            "caixa_aberto": caixa_aberto,
            "filial_visual": filial_visual,
            "formas_pagamento": formas_pagamento_disponiveis(caixa_aberto.filial) if caixa_aberto else FormaPagamento.objects.none(),
            "pre_venda_origem": pre_venda_origem,
            "produtos_rapidos": produtos_rapidos,
            "clientes_rapidos": clientes_para_usuario(request.user, Cliente.objects.filter(is_active=True)).order_by("nome")[:24],
            "caixas_recentes": caixas_recentes,
            "caixas_aguardando_conferencia": caixas_aguardando_conferencia,
            "vendas_recentes": vendas_recentes,
            "promocoes_rapidas": promocoes_rapidas,
            "ultima_venda": ultima_venda,
        },
    )


@login_required
@role_required(*PDV)
def remover_item(request, produto_id):
    cart = _get_cart(request)
    chave = str(produto_id)
    try:
        quantidade_atual = Decimal(str(cart.get(chave, "0")))
    except InvalidOperation:
        quantidade_atual = Decimal("0.000")
    if quantidade_atual > Decimal("1.000"):
        cart[chave] = str(quantidade_atual - Decimal("1.000"))
        mensagem = "Quantidade do item reduzida."
    else:
        cart.pop(chave, None)
        mensagem = "Item removido."
    _save_cart(request, cart)
    messages.success(request, mensagem)
    return redirect("pdv:pdv")


@login_required
@role_required(*PDV)
def limpar_carrinho(request):
    _save_cart(request, {})
    request.session.pop(PRE_VENDA_SESSION_KEY, None)
    request.session.modified = True
    messages.success(request, "Carrinho limpo.")
    return redirect("pdv:pdv")


@login_required
@role_required(*PDV)
def consulta_preco(request):
    termo = request.GET.get("q", "").strip()
    produto = None
    estoques = []
    promocao = None
    preco_atual = None

    if termo:
        produto = (
            Produto.objects.select_related("categoria", "marca")
            .filter(is_active=True)
            .filter(Q(codigo_barras=termo) | Q(codigo_interno=termo) | Q(nome__icontains=termo))
            .first()
        )
        if produto:
            promocao = promocao_ativa_para_produto(produto)
            preco_atual = preco_atual_produto(produto)
            estoques = list(
                _escopo_empresa_pdv(
                    request.user,
                    Estoque.objects.select_related("filial").filter(produto=produto),
                ).order_by("filial__nome")
            )
        else:
            messages.error(request, "Produto nao encontrado para consulta.")

    return render(
        request,
        "pdv/consulta_preco.html",
        {
            "termo": termo,
            "produto": produto,
            "promocao": promocao,
            "preco_atual": preco_atual,
            "estoques": estoques,
        },
    )


@login_required
@role_required(*ADMINISTRACAO)
def acessos_pdv_nuvem(request):
    acessos = AcessoPdvNuvem.objects.select_related("usuario", "filial", "filial__empresa", "decidido_por")
    if not request.user.is_superuser:
        perfil = getattr(request.user, "perfil_supermercado", None)
        empresa_id = perfil.filial.empresa_id if perfil and perfil.is_active and perfil.filial_id else 0
        acessos = acessos.filter(filial__empresa_id=empresa_id) if empresa_id else acessos.none()
    pendentes_qs = acessos.filter(status=StatusAcessoPdvNuvem.PENDENTE).order_by("criado_em")
    historico_qs = acessos.exclude(status=StatusAcessoPdvNuvem.PENDENTE).order_by("-atualizado_em")
    pendentes = Paginator(pendentes_qs, 50).get_page(request.GET.get("pendentes_page"))
    historico = Paginator(historico_qs, 50).get_page(request.GET.get("historico_page"))
    resumo = {
        "pendentes": pendentes_qs.count(),
        "aprovados": acessos.filter(status=StatusAcessoPdvNuvem.APROVADO).count(),
        "recusados": acessos.filter(status=StatusAcessoPdvNuvem.RECUSADO).count(),
    }
    return render(request, "pdv/acessos_pdv_nuvem.html", {
        "pendentes": pendentes, "historico": historico, "resumo": resumo,
    })

@login_required
@role_required(*ADMINISTRACAO)
def decidir_acesso_pdv_nuvem_view(request, acesso_id):
    acessos = AcessoPdvNuvem.objects.all()
    if not request.user.is_superuser:
        perfil = getattr(request.user, "perfil_supermercado", None)
        empresa_id = perfil.filial.empresa_id if perfil and perfil.is_active and perfil.filial_id else 0
        acessos = acessos.filter(filial__empresa_id=empresa_id) if empresa_id else acessos.none()
    solicitacao = get_object_or_404(acessos, id=acesso_id)
    if request.method != "POST":
        return redirect("pdv:acessos_pdv_nuvem")
    acao = request.POST.get("acao")
    if acao not in {"aprovar", "recusar"}:
        messages.error(request, "Acao invalida para a solicitacao.")
        return redirect("pdv:acessos_pdv_nuvem")
    try:
        decidir_acesso_pdv_nuvem(
            solicitacao=solicitacao,
            admin=request.user,
            aprovar=acao == "aprovar",
            justificativa=request.POST.get("justificativa", "").strip(),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Solicitacao de acesso atualizada.")
    return redirect("pdv:acessos_pdv_nuvem")


class PreVendaListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = PDV
    model = PreVenda
    template_name = "pdv/pre_venda_list.html"
    context_object_name = "pre_vendas"
    paginate_by = 25

    def get_queryset(self):
        queryset = PreVenda.objects.select_related("filial", "cliente", "usuario", "venda").order_by("-criada_em")
        queryset = _escopo_empresa_pdv(self.request.user, queryset)
        status = self.request.GET.get("status")
        termo = self.request.GET.get("q")
        if status:
            queryset = queryset.filter(status=status)
        if termo:
            filtros = Q(cliente__nome__icontains=termo)
            if termo.isdigit():
                filtros |= Q(id=int(termo))
            queryset = queryset.filter(filtros)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusPreVenda.choices
        return context


@login_required
@role_required(*PDV)
def pre_venda_detalhe(request, pre_venda_id):
    pre_vendas = _escopo_empresa_pdv(
        request.user,
        PreVenda.objects.select_related("filial", "cliente", "usuario", "venda").prefetch_related("itens__produto"),
    )
    pre_venda = get_object_or_404(pre_vendas, id=pre_venda_id)
    return render(request, "pdv/pre_venda_detalhe.html", {"pre_venda": pre_venda})


@login_required
@role_required(*PDV)
def recibo_pre_venda(request, pre_venda_id):
    pre_vendas = _escopo_empresa_pdv(
        request.user,
        PreVenda.objects.select_related("filial", "filial__empresa", "cliente", "usuario", "venda").prefetch_related("itens__produto"),
    )
    pre_venda = get_object_or_404(pre_vendas, id=pre_venda_id)
    impressao = configuracao_impressao_para(pre_venda.filial, TipoDocumentoImpressao.PEDIDO_SEPARACAO)
    return render(
        request,
        "pdv/recibo_pre_venda.html",
        {"pre_venda": pre_venda, "impressao": impressao, "estilos_impressao": estilos_impressao(impressao)},
    )


@login_required
@role_required(*PDV)
def carregar_pre_venda(request, pre_venda_id):
    pre_vendas = _escopo_empresa_pdv(request.user, PreVenda.objects.prefetch_related("itens__produto"))
    pre_venda = get_object_or_404(pre_vendas, id=pre_venda_id)
    if pre_venda.status != StatusPreVenda.ABERTA:
        messages.error(request, "Apenas DAVs abertos podem ser carregados no PDV.")
        return redirect("pdv:pre_venda_detalhe", pre_venda_id=pre_venda.id)

    cart = {str(item.produto_id): str(item.quantidade) for item in pre_venda.itens.all()}
    _save_cart(request, cart)
    request.session[PRE_VENDA_SESSION_KEY] = pre_venda.id
    request.session.modified = True
    messages.success(request, f"DAV {pre_venda.id} carregado no PDV.")
    return redirect("pdv:pdv")


@login_required
@role_required(*PDV)
def cancelar_pre_venda_view(request, pre_venda_id):
    pre_venda = get_object_or_404(_escopo_empresa_pdv(request.user, PreVenda.objects.all()), id=pre_venda_id)
    if request.method != "POST":
        return redirect("pdv:pre_venda_detalhe", pre_venda_id=pre_venda.id)
    motivo = request.POST.get("motivo", "").strip()
    try:
        supervisor = supervisor_from_request(request)
        cancelar_pre_venda(pre_venda=pre_venda, usuario=request.user, motivo=motivo, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "DAV cancelado com sucesso.")
    return redirect("pdv:pre_venda_detalhe", pre_venda_id=pre_venda.id)


@login_required
@role_required(*PDV)
def venda_detalhe(request, venda_id):
    vendas = _escopo_empresa_pdv(
        request.user,
        Venda.objects.select_related("filial", "caixa", "usuario").prefetch_related("itens__produto", "itens__itens_devolucao", "pagamentos__forma_pagamento", "devolucoes__itens__produto"),
    )
    venda = get_object_or_404(vendas, id=venda_id)
    for item in venda.itens.all():
        item.quantidade_devolvida = quantidade_devolvida_item(item)
        item.quantidade_disponivel_devolucao = item.quantidade - item.quantidade_devolvida
    return render(request, "pdv/venda_detalhe.html", {"venda": venda})


@login_required
@role_required(*PDV)
def devolver_venda(request, venda_id):
    vendas = _escopo_empresa_pdv(
        request.user,
        Venda.objects.select_related("filial", "caixa", "usuario").prefetch_related("itens__produto", "itens__itens_devolucao"),
    )
    venda = get_object_or_404(vendas, id=venda_id)
    itens = list(venda.itens.all())
    for item in itens:
        item.quantidade_devolvida = quantidade_devolvida_item(item)
        item.quantidade_disponivel_devolucao = item.quantidade - item.quantidade_devolvida

    if request.method == "POST":
        motivo = request.POST.get("motivo", "").strip()
        itens_devolucao = []
        for item in itens:
            quantidade_texto = request.POST.get(f"quantidade_{item.id}", "0").replace(",", ".")
            try:
                quantidade = Decimal(quantidade_texto or "0")
            except InvalidOperation:
                quantidade = Decimal("0")
            itens_devolucao.append({"item_venda": item, "quantidade": quantidade})
        try:
            supervisor = supervisor_from_request(request)
            devolucao = registrar_devolucao_venda(
                venda=venda,
                usuario=request.user,
                itens=itens_devolucao,
                motivo=motivo,
                supervisor=supervisor,
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, f"Devolucao {devolucao.id} registrada com sucesso.")
            return redirect("pdv:venda_detalhe", venda_id=venda.id)

    return render(request, "pdv/devolver_venda.html", {"venda": venda, "itens": itens})


@login_required
@role_required(*PDV)
def recibo_venda(request, venda_id):
    vendas = _escopo_empresa_pdv(
        request.user,
        Venda.objects.select_related("filial", "filial__empresa", "caixa", "usuario", "cliente").prefetch_related("itens__produto", "pagamentos__forma_pagamento"),
    )
    venda = get_object_or_404(vendas, id=venda_id)
    documento_fiscal = _documento_fiscal_imprimivel(venda)
    if request.GET.get("reimpressao") == "1":
        _registrar_reimpressao_cupom(request, venda, origem="navegador", documento_fiscal=documento_fiscal)
    if documento_fiscal:
        return render(request, "fiscal/danfe_nfce.html", _contexto_danfe_pdv(documento_fiscal))
    impressao = configuracao_impressao_para(venda.filial, TipoDocumentoImpressao.CUPOM_NAO_FISCAL)
    itens = list(venda.itens.all())
    pagamentos = list(venda.pagamentos.all())
    quantidade_total = sum((item.quantidade for item in itens), Decimal("0"))
    total_pago = sum((pagamento.valor for pagamento in pagamentos), Decimal("0"))
    troco = max(Decimal("0"), total_pago - venda.total_liquido)
    return render(
        request,
        "pdv/recibo_venda.html",
        {
            "venda": venda,
            "impressao": impressao,
            "estilos_impressao": estilos_impressao(impressao),
            "quantidade_total": quantidade_total,
            "total_pago": total_pago,
            "troco": troco,
        },
    )


@login_required
@role_required(*PDV)
def venda_impressao_desktop(request, venda_id):
    vendas = _escopo_empresa_pdv(
        request.user,
        Venda.objects.select_related("filial", "filial__empresa", "caixa", "usuario", "cliente")
        .prefetch_related("itens__produto", "pagamentos__forma_pagamento"),
    )
    venda = get_object_or_404(vendas, id=venda_id)
    reimpressao = request.GET.get("reimpressao") == "1"
    documento_fiscal = _documento_fiscal_imprimivel(venda)
    if reimpressao:
        _registrar_reimpressao_cupom(request, venda, origem="app_desktop", documento_fiscal=documento_fiscal)
    tipo_impressao = TipoDocumentoImpressao.CUPOM_FISCAL if documento_fiscal else TipoDocumentoImpressao.CUPOM_NAO_FISCAL
    impressao = configuracao_impressao_para(venda.filial, tipo_impressao)
    impressora_padrao = (impressao.impressora_padrao or "").strip() if impressao else ""
    impressora_configurada = bool(impressora_padrao)
    mensagem_impressao = ""
    if not impressao:
        mensagem_impressao = "Nenhuma configuração de impressão para cupom foi encontrada. Configure em Sistema > Impressões."
    elif not impressora_configurada:
        mensagem_impressao = "Configuração de cupom encontrada, mas sem impressora padrão definida. Informe a impressora em Sistema > Impressões."
    pagamentos = list(venda.pagamentos.all())
    itens = list(venda.itens.all())
    total_pago = sum((pagamento.valor for pagamento in pagamentos), Decimal("0"))
    troco = max(Decimal("0"), total_pago - venda.total_liquido)
    tem_dinheiro = any((pagamento.forma_pagamento.tipo or "").upper() == "DINHEIRO" for pagamento in pagamentos)
    abrir_gaveta = bool(not reimpressao and impressao and impressao.gaveta_automatica and impressao.abrir_gaveta_em_dinheiro and tem_dinheiro)
    fiscal_payload = {}
    documento_pronto = not documento_fiscal
    if documento_fiscal:
        qrcode_url = ""
        try:
            qrcode_url = obter_url_qrcode_nfce(documento_fiscal)
        except (ValidationError, ConfiguracaoFiscal.DoesNotExist) as exc:
            mensagem_impressao = "; ".join(getattr(exc, "messages", [str(exc)]))
        try:
            url_consulta = documento_fiscal.filial.configuracao_fiscal.url_consulta_nfce
        except ConfiguracaoFiscal.DoesNotExist:
            url_consulta = ""
        documento_pronto = bool(
            qrcode_url
            and len(documento_fiscal.chave_acesso) == 44
            and (documento_fiscal.protocolo or documento_fiscal.status == StatusDocumentoFiscal.CONTINGENCIA)
        )
        if not documento_pronto and not mensagem_impressao:
            mensagem_impressao = "A NFC-e ainda nao possui chave, protocolo ou QR Code validos para impressao."
        fiscal_payload = {
            "documento_id": documento_fiscal.id,
            "status": documento_fiscal.status,
            "ambiente": documento_fiscal.ambiente,
            "serie": documento_fiscal.serie,
            "numero": documento_fiscal.numero,
            "chave_acesso": documento_fiscal.chave_acesso,
            "protocolo": documento_fiscal.protocolo,
            "qrcode_url": qrcode_url,
            "url_consulta": url_consulta,
            "contingencia": documento_fiscal.status == StatusDocumentoFiscal.CONTINGENCIA,
            "emitido_em": timezone.localtime(documento_fiscal.criado_em).isoformat(),
            "consumidor_tipo": venda.get_documento_consumidor_tipo_display(),
            "consumidor_documento": venda.documento_consumidor,
        }
    logo_url = ""
    if venda.filial.empresa.logo:
        logo_url = request.build_absolute_uri(venda.filial.empresa.logo.url)
    return JsonResponse(
        {
            "status": "ok",
            "tipo": "danfe_nfce" if documento_fiscal else "cupom_nao_fiscal",
            "operacao": ("reimpressao_danfe_nfce" if reimpressao else "impressao_danfe_nfce") if documento_fiscal else ("reimpressao_cupom" if reimpressao else "impressao_cupom"),
            "reimpressao": reimpressao,
            "venda": {
                "id": venda.id,
                "status": venda.status,
                "data": timezone.localtime(venda.data).isoformat(),
                "filial": venda.filial.nome,
                "empresa": str(venda.filial.empresa),
                "cnpj": venda.filial.cnpj or venda.filial.empresa.cnpj,
                "endereco": venda.filial.endereco or venda.filial.empresa.endereco,
                "telefone": venda.filial.telefone or venda.filial.empresa.telefone,
                "logo_url": logo_url,
                "operador": str(venda.usuario),
                "cliente": str(venda.cliente) if venda.cliente else "Cliente avulso",
                "caixa": venda.caixa_id,
                "total_bruto": _moeda_json(venda.total_bruto),
                "desconto": _moeda_json(venda.desconto),
                "total_liquido": _moeda_json(venda.total_liquido),
                "total_pago": _moeda_json(total_pago),
                "troco": _moeda_json(troco),
                "quantidade_total": _quantidade_json(sum((item.quantidade for item in itens), Decimal("0"))),
            },
            "itens": [
                {
                    "sequencia": indice,
                    "produto": item.produto.nome,
                    "codigo_barras": item.produto.codigo_barras,
                    "quantidade": _quantidade_json(item.quantidade),
                    "preco_unitario": _moeda_json(item.preco_unitario_venda),
                    "desconto": _moeda_json(item.desconto),
                    "total": _moeda_json(item.total),
                }
                for indice, item in enumerate(itens, start=1)
            ],
            "pagamentos": [
                {
                    "forma": pagamento.forma_pagamento.nome,
                    "tipo": pagamento.forma_pagamento.tipo,
                    "valor": _moeda_json(pagamento.valor),
                    "status": pagamento.status,
                    "transacao_externa_id": pagamento.transacao_externa_id,
                    "nsu": pagamento.nsu,
                    "codigo_autorizacao": pagamento.codigo_autorizacao,
                    "mensagem_processadora": pagamento.mensagem_processadora,
                }
                for pagamento in pagamentos
            ],
            "impressao": {
                "configurada": bool(impressao),
                "impressora_configurada": impressora_configurada,
                "impressora_padrao": impressora_padrao,
                "modelo_papel": impressao.modelo_papel if impressao else "",
                "numero_vias": impressao.numero_vias if impressao else 1,
                "impressao_automatica": impressao.impressao_automatica if impressao else False,
                "mensagem_rodape": impressao.mensagem_rodape if impressao else "",
                "mensagem": mensagem_impressao,
                "documento_pronto": documento_pronto,
            },
            "fiscal": fiscal_payload,
            "gaveta": {
                "abrir": abrir_gaveta,
                "motivo": "pagamento_em_dinheiro" if abrir_gaveta else "nao_aplicavel",
                "bloqueia_venda_se_indisponivel": False,
            },
        }
    )


def _registrar_reimpressao_cupom(request, venda, *, origem, documento_fiscal=None):
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="pdv",
        acao="REIMPRESSAO_DANFE_NFCE" if documento_fiscal else "REIMPRESSAO_CUPOM",
        descricao=(
            f"Reimpressao do DANFE NFC-e {documento_fiscal.id} da venda {venda.id} pela origem {origem}."
            if documento_fiscal
            else f"Reimpressao do cupom da venda {venda.id} pela origem {origem}."
        ),
        objeto_tipo="Venda",
        objeto_id=str(venda.id),
        ip=request.META.get("REMOTE_ADDR"),
    )


@login_required
@role_required(*PDV)
def cancelar_venda_view(request, venda_id):
    venda = get_object_or_404(_escopo_empresa_pdv(request.user, Venda.objects.all()), id=venda_id)
    if request.method != "POST":
        return redirect("pdv:venda_detalhe", venda_id=venda.id)
    motivo = request.POST.get("motivo", "").strip()
    try:
        supervisor = supervisor_from_request(request)
        cancelar_venda(venda=venda, usuario=request.user, motivo=motivo, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Venda cancelada e estoque devolvido.")
    if request.POST.get("next") == "pdv":
        return redirect("pdv:pdv")
    return redirect("pdv:venda_detalhe", venda_id=venda.id)


@login_required
@role_required(*SUPERVISAO)
def confirmar_estorno_pagamento_view(request, pagamento_id):
    pagamentos = _escopo_empresa_pdv(
        request.user,
        PagamentoVenda.objects.select_related("venda"),
        campo="venda__filial__empresa_id",
    )
    pagamento = get_object_or_404(pagamentos, id=pagamento_id)
    if request.method != "POST":
        return redirect("pdv:venda_detalhe", venda_id=pagamento.venda_id)
    motivo = request.POST.get("motivo", "").strip()
    autorizacao = request.POST.get("autorizacao", "").strip()
    mensagem_processadora = request.POST.get("mensagem_processadora", "").strip()
    try:
        supervisor_from_request(request)
        confirmar_estorno_pagamento_eletronico(
            pagamento=pagamento,
            usuario=request.user,
            motivo=motivo,
            autorizacao=autorizacao,
            mensagem_processadora=mensagem_processadora,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Estorno eletrônico confirmado e financeiro revertido.")
    if request.POST.get("next") == "estornos_eletronicos":
        return redirect("pdv:estornos_eletronicos")
    return redirect("pdv:venda_detalhe", venda_id=pagamento.venda_id)


@login_required
@role_required(*SUPERVISAO)
def confirmar_estorno_parcial_view(request, estorno_id):
    estornos = _escopo_empresa_pdv(
        request.user,
        EstornoParcialPagamento.objects.select_related("pagamento__venda"),
        campo="pagamento__venda__filial__empresa_id",
    )
    estorno = get_object_or_404(estornos, id=estorno_id)
    if request.method != "POST":
        return redirect("pdv:venda_detalhe", venda_id=estorno.pagamento.venda_id)
    try:
        supervisor_from_request(request)
        confirmar_estorno_parcial_eletronico(
            estorno=estorno,
            usuario=request.user,
            autorizacao=request.POST.get("autorizacao", "").strip(),
            transacao_estorno_id=request.POST.get("transacao_estorno_id", "").strip(),
            mensagem_processadora=request.POST.get("mensagem_processadora", "").strip(),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Estorno eletrônico parcial confirmado e financeiro revertido.")
    if request.POST.get("next") == "estornos_eletronicos":
        return redirect("pdv:estornos_eletronicos")
    return redirect("pdv:venda_detalhe", venda_id=estorno.pagamento.venda_id)


def _estornos_eletronicos_payload(user):
    agora = timezone.now()
    limite_alerta_minutos = 15
    pendentes_integrais = list(
        _escopo_empresa_pdv(
            user,
            PagamentoVenda.objects.filter(status=StatusPagamento.ESTORNO_PENDENTE),
            campo="venda__filial__empresa_id",
        )
        .select_related("venda__filial", "venda__caixa", "forma_pagamento")
        .order_by("estorno_solicitado_em", "data")[:100]
    )
    pendentes_parciais = list(
        _escopo_empresa_pdv(
            user,
            EstornoParcialPagamento.objects.filter(status=StatusEstornoParcial.PENDENTE),
            campo="pagamento__venda__filial__empresa_id",
        )
        .select_related("pagamento__venda__filial", "pagamento__venda__caixa", "pagamento__forma_pagamento", "devolucao")
        .order_by("solicitado_em", "id")[:100]
    )
    itens = []
    for pagamento in pendentes_integrais:
        solicitado_em = pagamento.estorno_solicitado_em or pagamento.data
        itens.append({
            "chave": f"pagamento-{pagamento.pk}", "tipo_estorno": "TOTAL",
            "pagamento_id": pagamento.pk, "devolucao_id": None,
            "venda_id": pagamento.venda_id, "filial": str(pagamento.venda.filial),
            "caixa_id": pagamento.venda.caixa_id, "forma_pagamento": pagamento.forma_pagamento.nome,
            "tipo": pagamento.forma_pagamento.tipo, "valor": _moeda_json(pagamento.valor),
            "transacao_externa_id": pagamento.transacao_externa_id, "nsu": pagamento.nsu,
            "codigo_autorizacao": pagamento.codigo_autorizacao, "solicitado_em_obj": solicitado_em,
            "confirmar_url": reverse("pdv:confirmar_estorno_pagamento", kwargs={"pagamento_id": pagamento.pk}),
        })
    for estorno in pendentes_parciais:
        pagamento = estorno.pagamento
        itens.append({
            "chave": f"estorno-parcial-{estorno.pk}", "tipo_estorno": "PARCIAL",
            "pagamento_id": pagamento.pk, "devolucao_id": estorno.devolucao_id,
            "venda_id": pagamento.venda_id, "filial": str(pagamento.venda.filial),
            "caixa_id": pagamento.venda.caixa_id, "forma_pagamento": pagamento.forma_pagamento.nome,
            "tipo": pagamento.forma_pagamento.tipo, "valor": _moeda_json(estorno.valor),
            "transacao_externa_id": pagamento.transacao_externa_id, "nsu": pagamento.nsu,
            "codigo_autorizacao": pagamento.codigo_autorizacao, "solicitado_em_obj": estorno.solicitado_em,
            "confirmar_url": reverse("pdv:confirmar_estorno_parcial", kwargs={"estorno_id": estorno.pk}),
        })
    itens.sort(key=lambda item: item["solicitado_em_obj"])
    itens = itens[:100]
    vencidos = 0
    valor_total = Decimal("0.00")
    for item in itens:
        solicitado_em = item.pop("solicitado_em_obj")
        idade_minutos = max(0, int((agora - solicitado_em).total_seconds() // 60))
        item["solicitado_em"] = solicitado_em.isoformat()
        item["idade_minutos"] = idade_minutos
        item["atrasado"] = idade_minutos >= limite_alerta_minutos
        vencidos += 1 if item["atrasado"] else 0
        valor_total += Decimal(item["valor"])
    return {
        "contrato": "payment_refund_readiness_v1",
        "status": "attention_required" if itens else "clear",
        "limite_alerta_minutos": limite_alerta_minutos,
        "resumo": {"pendentes": len(itens), "atrasados": vencidos, "valor_pendente": _moeda_json(valor_total)},
        "recomendacoes": (["Processar os estornos na adquirente e confirmar cada retorno aprovado no sistema."] if itens else []),
        "estornos": itens,
    }

@login_required
@role_required(*SUPERVISAO)
def estornos_eletronicos(request):
    return render(
        request,
        "pdv/estornos_eletronicos.html",
        {"diagnostico": _estornos_eletronicos_payload(request.user)},
    )


@login_required
@role_required(*SUPERVISAO)
def estornos_eletronicos_diagnostico(request):
    return JsonResponse(_estornos_eletronicos_payload(request.user))


def _resumo_caixa(caixa):
    total_vendas = caixa.vendas.filter(status="FINALIZADA").aggregate(total=Sum("total_liquido"))["total"] or Decimal("0.00")
    total_sangrias = caixa.sangrias.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    total_suprimentos = caixa.suprimentos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    total_esperado = caixa.valor_inicial + total_vendas + total_suprimentos - total_sangrias
    divergencia_declarada = caixa.valor_final - total_esperado if caixa.valor_final is not None else None
    divergencia_conferida = caixa.valor_conferido - total_esperado if caixa.valor_conferido is not None else None
    pagamentos_por_forma = PagamentoVenda.objects.filter(
        venda__caixa=caixa,
        venda__status="FINALIZADA",
    ).values("forma_pagamento__nome").annotate(total=Sum("valor")).order_by("forma_pagamento__nome")
    return {
        "total_vendas": total_vendas,
        "total_sangrias": total_sangrias,
        "total_suprimentos": total_suprimentos,
        "total_esperado": total_esperado,
        "divergencia_declarada": divergencia_declarada,
        "divergencia_conferida": divergencia_conferida,
        "pagamentos_por_forma": pagamentos_por_forma,
    }


@login_required
@role_required(*PDV)
def caixa_detalhe(request, caixa_id):
    caixas = _escopo_empresa_pdv(
        request.user,
        Caixa.objects.select_related("filial", "usuario_abertura", "usuario_fechamento", "usuario_conferencia").prefetch_related("vendas", "sangrias", "suprimentos"),
    )
    caixa = get_object_or_404(caixas, id=caixa_id)
    context = {
        "caixa": caixa,
        "resumo": _resumo_caixa(caixa),
        "sangria_form": SangriaForm(),
        "suprimento_form": SuprimentoForm(),
        "fechar_form": FecharCaixaForm(instance=caixa),
        "conferir_form": ConferirCaixaForm(instance=caixa),
        "has_movimentos": caixa.suprimentos.exists() or caixa.sangrias.exists(),
    }
    return render(request, "pdv/caixa_detalhe.html", context)


def _caixa_aberto_or_redirect(request, caixa_id):
    caixa = get_object_or_404(_escopo_empresa_pdv(request.user, Caixa.objects.all()), id=caixa_id)
    if caixa.status != StatusCaixa.ABERTO:
        messages.error(request, "Este caixa nao esta aberto.")
        return caixa, False
    return caixa, True


def _redirect_after_caixa_action(request, caixa):
    if request.POST.get("next") == "pdv":
        return redirect("pdv:pdv")
    return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)


@login_required
@role_required(*PDV)
def registrar_sangria(request, caixa_id):
    caixa, ok = _caixa_aberto_or_redirect(request, caixa_id)
    if not ok:
        return _redirect_after_caixa_action(request, caixa)
    if request.method == "POST":
        form = SangriaForm(request.POST)
        if form.is_valid():
            try:
                supervisor_from_request(request)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                sangria = form.save(commit=False)
                sangria.caixa = caixa
                sangria.usuario = request.user
                sangria.save()
                if not LancamentoFinanceiro.objects.filter(sangria=sangria).exists():
                    registrar_lancamento(
                        conta=conta_caixa_pdv(caixa.filial),
                        tipo=TipoLancamentoFinanceiro.SAIDA,
                        descricao=f"Sangria caixa #{caixa.id}: {sangria.motivo}",
                        valor=sangria.valor,
                        data=timezone.localdate(),
                        usuario=request.user,
                        origem="PDV_SANGRIA",
                        sangria=sangria,
                    )
                _agendar_abertura_gaveta(request, caixa, f"sangria_{sangria.id}", "sangria")
                messages.success(request, "Sangria registrada com sucesso.")
    return _redirect_after_caixa_action(request, caixa)


@login_required
@role_required(*PDV)
def registrar_suprimento(request, caixa_id):
    caixa, ok = _caixa_aberto_or_redirect(request, caixa_id)
    if not ok:
        return _redirect_after_caixa_action(request, caixa)
    if request.method == "POST":
        form = SuprimentoForm(request.POST)
        if form.is_valid():
            try:
                supervisor_from_request(request)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                suprimento = form.save(commit=False)
                suprimento.caixa = caixa
                suprimento.usuario = request.user
                suprimento.save()
                if not LancamentoFinanceiro.objects.filter(suprimento=suprimento).exists():
                    registrar_lancamento(
                        conta=conta_caixa_pdv(caixa.filial),
                        tipo=TipoLancamentoFinanceiro.ENTRADA,
                        descricao=f"Suprimento caixa #{caixa.id}: {suprimento.motivo}",
                        valor=suprimento.valor,
                        data=timezone.localdate(),
                        usuario=request.user,
                        origem="PDV_SUPRIMENTO",
                        suprimento=suprimento,
                    )
                _agendar_abertura_gaveta(request, caixa, f"suprimento_{suprimento.id}", "suprimento")
                messages.success(request, "Suprimento registrado com sucesso.")
    return _redirect_after_caixa_action(request, caixa)


@login_required
@role_required(*PDV)
def fechar_caixa(request, caixa_id):
    caixa, ok = _caixa_aberto_or_redirect(request, caixa_id)
    if not ok:
        return _redirect_after_caixa_action(request, caixa)
    if request.method == "POST":
        form = FecharCaixaForm(request.POST, instance=caixa)
        if form.is_valid():
            caixa = form.save(commit=False)
            caixa.usuario_fechamento = request.user
            caixa.data_fechamento = timezone.now()
            caixa.status = StatusCaixa.FECHADO
            caixa.save()
            _agendar_abertura_gaveta(request, caixa, f"fechamento_caixa_{caixa.id}", "fechamento")
            messages.success(request, "Caixa fechado com sucesso.")
    return _redirect_after_caixa_action(request, caixa)


@login_required
@role_required(*PDV)
def conferir_caixa(request, caixa_id):
    caixa = get_object_or_404(_escopo_empresa_pdv(request.user, Caixa.objects.all()), id=caixa_id)
    if request.method != "POST":
        return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)
    if caixa.status != StatusCaixa.FECHADO:
        messages.error(request, "Apenas caixas fechados pelo operador podem ser conferidos.")
        return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)
    try:
        supervisor = supervisor_from_request(request)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)

    form = ConferirCaixaForm(request.POST, instance=caixa)
    if form.is_valid():
        caixa = form.save(commit=False)
        caixa.usuario_conferencia = supervisor
        caixa.data_conferencia = timezone.now()
        caixa.status = StatusCaixa.CONFERIDO
        caixa.save(
            update_fields=[
                "valor_conferido",
                "observacao_conferencia",
                "usuario_conferencia",
                "data_conferencia",
                "status",
            ]
        )
        messages.success(request, "Caixa conferido com sucesso.")
    else:
        messages.error(request, "Confira os dados da conferencia.")
    return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)


class CaixaListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = PDV
    model = Caixa
    template_name = "pdv/caixa_list.html"
    context_object_name = "caixas"
    paginate_by = 25

    def get_queryset(self):
        queryset = Caixa.objects.select_related("filial", "usuario_abertura", "usuario_fechamento", "usuario_conferencia")
        return _escopo_empresa_pdv(self.request.user, queryset).order_by("-data_abertura")


class AbrirCaixaView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = PDV
    model = Caixa
    form_class = AbrirCaixaForm
    template_name = "pdv/caixa_form.html"
    success_url = reverse_lazy("pdv:caixas")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.usuario_abertura = self.request.user
        messages.success(self.request, "Caixa aberto com sucesso.")
        response = super().form_valid(form)
        _agendar_abertura_gaveta(self.request, self.object, f"abertura_caixa_{self.object.id}", "abertura")
        return response

# Create your views here.
