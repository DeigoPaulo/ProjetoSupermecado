from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, InvalidOperation
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.accounts.permissions import CADASTROS, SISTEMA, role_required
from apps.configuracoes.models import TipoDocumentoImpressao
from apps.configuracoes.services import configuracao_impressao_para, estilos_impressao
from apps.fiscal.services import preparar_documento_pedido_online

from .forms import CalcularEntregaForm, FaixaTaxaEntregaFormSet, IntegracaoMarketplaceForm, ItemPedidoOnlineForm, PagamentoPedidoForm, PedidoOnlineForm, PoliticaEntregaForm
from .models import CanalPedido, IntegracaoMarketplace, ItemPedidoOnline, PedidoOnline, PoliticaEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega
from .services import alterar_status_pedido, calcular_entrega_pedido, calcular_taxa_entrega, cancelar_pedido, gerar_token_integracao, registrar_pagamento, reservar_pedido
from apps.produtos.models import Produto


@role_required(*CADASTROS)
def pedidos(request):
    base_queryset = PedidoOnline.objects.select_related("filial", "cliente", "usuario")
    queryset = base_queryset
    termo = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if termo:
        filtro = Q(nome_cliente__icontains=termo) | Q(referencia_externa__icontains=termo)
        if termo.isdigit():
            filtro |= Q(pk=int(termo))
        queryset = queryset.filter(filtro)
    if status:
        queryset = queryset.filter(status=status)
    resumo = queryset.aggregate(valor=Sum("total"))
    painel = {
        "rascunho": base_queryset.filter(status=StatusPedido.RASCUNHO).count(),
        "separacao": base_queryset.filter(status=StatusPedido.EM_SEPARACAO).count(),
        "pronto": base_queryset.filter(status=StatusPedido.PRONTO).count(),
        "entrega": base_queryset.filter(status=StatusPedido.SAIU_ENTREGA).count(),
    }
    pedidos_lista = list(queryset.prefetch_related("itens")[:100])
    for pedido in pedidos_lista:
        total_pedido = sum((item.quantidade for item in pedido.itens.all()), Decimal("0"))
        total_separado = sum((item.quantidade_separada for item in pedido.itens.all()), Decimal("0"))
        pedido.total_itens_pedido = total_pedido
        pedido.total_itens_separados = total_separado
        pedido.percentual_separacao = int((total_separado / total_pedido) * 100) if total_pedido else 0
    return render(
        request,
        "marketplace/pedidos.html",
        {
            "pedidos": pedidos_lista,
            "status_opcoes": StatusPedido.choices,
            "valor_total": resumo["valor"] or 0,
            "painel": painel,
        },
    )


@role_required(*CADASTROS)
def novo_pedido(request):
    form = PedidoOnlineForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pedido = form.save(commit=False)
        pedido.usuario = request.user
        pedido.save()
        messages.success(request, "Pedido criado. Agora inclua os produtos.")
        return redirect("marketplace:detalhe", pk=pedido.pk)
    return render(request, "marketplace/pedido_form.html", {"form": form})


@role_required(*CADASTROS)
def detalhe(request, pk):
    pedido = get_object_or_404(PedidoOnline.objects.select_related("filial", "cliente", "usuario").prefetch_related("itens__produto"), pk=pk)
    form_item = ItemPedidoOnlineForm(request.POST or None)
    if request.method == "POST" and request.POST.get("acao") == "item" and pedido.status == StatusPedido.RASCUNHO and form_item.is_valid():
        item = form_item.save(commit=False)
        item.pedido = pedido
        try:
            item.full_clean()
            item.save()
        except ValidationError as exc:
            form_item.add_error(None, exc)
        else:
            pedido.recalcular()
            messages.success(request, "Produto incluido no pedido.")
            return redirect("marketplace:detalhe", pk=pedido.pk)
    pagamento_form = PagamentoPedidoForm(initial={"valor_pago": pedido.total})
    entrega_form = CalcularEntregaForm(initial={"distancia_entrega_km": pedido.distancia_entrega_km})
    tem_politica_entrega = PoliticaEntrega.objects.filter(filial=pedido.filial, is_active=True).exists()
    entrega_pendente = pedido.tipo_entrega == TipoEntrega.ENTREGA and tem_politica_entrega and not pedido.regra_entrega_aplicada
    pode_iniciar_separacao = pedido.status == StatusPedido.RASCUNHO and pedido.itens.exists() and not entrega_pendente
    return render(
        request,
        "marketplace/pedido_detalhe.html",
        {
            "pedido": pedido,
            "form_item": form_item,
            "pagamento_form": pagamento_form,
            "entrega_form": entrega_form,
            "StatusPedido": StatusPedido,
            "tem_politica_entrega": tem_politica_entrega,
            "entrega_pendente": entrega_pendente,
            "pode_iniciar_separacao": pode_iniciar_separacao,
        },
    )


@role_required(*CADASTROS)
def imprimir_separacao(request, pk):
    pedido = get_object_or_404(PedidoOnline.objects.select_related("filial__empresa", "cliente", "usuario").prefetch_related("itens__produto"), pk=pk)
    impressao = configuracao_impressao_para(pedido.filial, TipoDocumentoImpressao.PEDIDO_SEPARACAO)
    return render(request, "marketplace/pedido_separacao_imprimir.html", {"pedido": pedido, "impressao": impressao, "estilos_impressao": estilos_impressao(impressao)})


@role_required(*CADASTROS)
def remover_item(request, pk, item_id):
    pedido = get_object_or_404(PedidoOnline, pk=pk, status=StatusPedido.RASCUNHO)
    if request.method == "POST":
        item = get_object_or_404(pedido.itens, pk=item_id)
        item.delete()
        pedido.recalcular()
        messages.success(request, "Item removido.")
    return redirect("marketplace:detalhe", pk=pedido.pk)


@role_required(*CADASTROS)
def acao_pedido(request, pk):
    pedido = get_object_or_404(PedidoOnline, pk=pk)
    if request.method != "POST":
        return redirect("marketplace:detalhe", pk=pk)
    acao = request.POST.get("acao")
    try:
        if acao == "reservar":
            reservar_pedido(pedido=pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        elif acao == "cancelar":
            cancelar_pedido(pedido=pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        elif acao == "avancar":
            alterar_status_pedido(pedido=pedido, destino=request.POST.get("destino"), usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        elif acao == "separacao":
            if pedido.status != StatusPedido.EM_SEPARACAO:
                raise ValidationError("A separacao so pode ser informada durante essa etapa.")
            with transaction.atomic():
                for item in pedido.itens.select_for_update():
                    valor = request.POST.get(f"item_{item.pk}", "0").replace(",", ".")
                    item.quantidade_separada = valor
                    item.full_clean()
                    item.save(update_fields=["quantidade_separada"])
        elif acao == "pagamento":
            form = PagamentoPedidoForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Verifique a forma e o valor do pagamento.")
            registrar_pagamento(pedido=pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
        elif acao == "preparar_nfe":
            preparar_documento_pedido_online(pedido=pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        elif acao == "calcular_entrega":
            form = CalcularEntregaForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Informe uma distancia valida para a entrega.")
            calcular_entrega_pedido(pedido=pedido, **form.cleaned_data)
        else:
            raise ValidationError("Acao invalida.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Pedido atualizado com sucesso.")
    return redirect("marketplace:detalhe", pk=pk)


@role_required(*SISTEMA)
def integracoes(request):
    diagnostico = _diagnostico_integracoes_marketplace()
    return render(
        request,
        "marketplace/integracoes.html",
        {
            "integracoes": diagnostico["integracoes"],
            "diagnostico": diagnostico,
            "novo_token": request.session.pop("marketplace_novo_token", None),
        },
    )


def _diagnostico_integracoes_marketplace():
    integracoes = list(
        IntegracaoMarketplace.objects.select_related("filial__empresa", "usuario")
        .annotate(
            total_pedidos=Count("pedidos", distinct=True),
            pedidos_abertos=Count("pedidos", filter=~Q(pedidos__status__in=[StatusPedido.CONCLUIDO, StatusPedido.CANCELADO]), distinct=True),
            pagamentos_pendentes=Count(
                "pedidos",
                filter=Q(pedidos__status_pagamento=StatusPagamentoPedido.PENDENTE) & ~Q(pedidos__status=StatusPedido.CANCELADO),
                distinct=True,
            ),
            ultimo_pedido_em=Max("pedidos__criado_em"),
        )
        .order_by("nome")
    )
    alertas = []
    payload_integracoes = []
    for integracao in integracoes:
        alerta_integracao = []
        if not integracao.is_active:
            alerta_integracao.append("Integracao inativa.")
        if not integracao.ultimo_uso_em:
            alerta_integracao.append("Chave nunca usada por parceiro externo.")
        if integracao.pagamentos_pendentes:
            alerta_integracao.append(f"{integracao.pagamentos_pendentes} pedido(s) com pagamento pendente.")
        if integracao.pedidos_abertos:
            alerta_integracao.append(f"{integracao.pedidos_abertos} pedido(s) em fluxo operacional.")
        for alerta in alerta_integracao:
            alertas.append({"integracao": integracao.nome, "mensagem": alerta})
        integracao.alertas_operacionais = alerta_integracao
        payload_integracoes.append(
            {
                "id": integracao.pk,
                "nome": integracao.nome,
                "filial": str(integracao.filial),
                "ativa": integracao.is_active,
                "token_prefixo": integracao.token_prefixo,
                "total_pedidos": integracao.total_pedidos,
                "pedidos_abertos": integracao.pedidos_abertos,
                "pagamentos_pendentes": integracao.pagamentos_pendentes,
                "ultimo_uso_em": integracao.ultimo_uso_em.isoformat() if integracao.ultimo_uso_em else None,
                "ultimo_pedido_em": integracao.ultimo_pedido_em.isoformat() if integracao.ultimo_pedido_em else None,
                "alertas": alerta_integracao,
            }
        )
    resumo = {
        "integracoes": len(integracoes),
        "ativas": sum(1 for item in integracoes if item.is_active),
        "pedidos_recebidos": sum(item.total_pedidos for item in integracoes),
        "pedidos_abertos": sum(item.pedidos_abertos for item in integracoes),
        "pagamentos_pendentes": sum(item.pagamentos_pendentes for item in integracoes),
        "alertas": len(alertas),
    }
    return {"gerado_em": timezone.now(), "resumo": resumo, "integracoes": integracoes, "payload_integracoes": payload_integracoes, "alertas": alertas}


@role_required(*SISTEMA)
def integracoes_diagnostico(request):
    diagnostico = _diagnostico_integracoes_marketplace()
    return JsonResponse(
        {
            "gerado_em": diagnostico["gerado_em"].isoformat(),
            "resumo": diagnostico["resumo"],
            "integracoes": diagnostico["payload_integracoes"],
            "alertas": diagnostico["alertas"],
        }
    )


@role_required(*SISTEMA)
def nova_integracao(request):
    form = IntegracaoMarketplaceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        integracao = form.save(commit=False)
        integracao.usuario = request.user
        integracao.token_prefixo = "temporario"
        integracao.token_hash = "temporario"
        integracao.save()
        request.session["marketplace_novo_token"] = gerar_token_integracao(integracao)
        messages.success(request, "Integracao criada. Guarde a chave exibida, pois ela nao sera mostrada novamente.")
        return redirect("marketplace:integracoes")
    return render(request, "marketplace/integracao_form.html", {"form": form})


@role_required(*SISTEMA)
def renovar_token(request, pk):
    integracao = get_object_or_404(IntegracaoMarketplace, pk=pk)
    if request.method == "POST":
        request.session["marketplace_novo_token"] = gerar_token_integracao(integracao)
        messages.success(request, "Chave renovada. A chave anterior deixou de funcionar.")
    return redirect("marketplace:integracoes")


@role_required(*SISTEMA)
def politicas_entrega(request):
    politicas = PoliticaEntrega.objects.select_related("filial__empresa").prefetch_related("faixas")
    simulacao = None
    if request.GET.get("simular") == "1":
        simulacao = _simular_politica_entrega(request)
    return render(
        request,
        "marketplace/politicas_entrega.html",
        {
            "politicas": politicas,
            "simulacao": simulacao,
        },
    )


def _politicas_entrega_diagnostico():
    politicas = PoliticaEntrega.objects.select_related("filial__empresa").prefetch_related("faixas")
    itens = []
    resumo = {"politicas": 0, "ativas": 0, "sem_faixas": 0, "com_alerta": 0}
    for politica in politicas:
        faixas = list(politica.faixas.all())
        alertas = []
        if not politica.is_active:
            alertas.append("Politica inativa.")
        if not faixas:
            alertas.append("Nenhuma faixa de taxa cadastrada.")
        if faixas and faixas[-1].distancia_final_km < politica.raio_maximo_km:
            alertas.append("A ultima faixa nao cobre todo o raio maximo.")
        if politica.valor_minimo_pedido <= 0:
            alertas.append("Pedido minimo zerado.")
        resumo["politicas"] += 1
        resumo["ativas"] += 1 if politica.is_active else 0
        resumo["sem_faixas"] += 1 if not faixas else 0
        resumo["com_alerta"] += 1 if alertas else 0
        itens.append(
            {
                "id": politica.pk,
                "filial": str(politica.filial),
                "ativa": politica.is_active,
                "raio_maximo_km": str(politica.raio_maximo_km),
                "valor_minimo_pedido": str(politica.valor_minimo_pedido),
                "frete_gratis_acima": str(politica.frete_gratis_acima) if politica.frete_gratis_acima is not None else None,
                "permite_retirada": politica.permite_retirada,
                "faixas": [
                    {
                        "distancia_inicial_km": str(faixa.distancia_inicial_km),
                        "distancia_final_km": str(faixa.distancia_final_km),
                        "taxa": str(faixa.taxa),
                    }
                    for faixa in faixas
                ],
                "alertas": alertas,
            }
        )
    return {
        "resumo": resumo,
        "politicas": itens,
        "geocodificacao": {
            "contrato": "delivery_geocode_v1",
            "provider_configurado": bool(getattr(settings, "MARKETPLACE_GEOCODING_PROVIDER_URL", "")),
            "timeout_segundos": getattr(settings, "MARKETPLACE_GEOCODING_TIMEOUT_SEGUNDOS", 5),
            "fallback_manual_distancia": True,
        },
    }


def _montar_url_geocoding(base_url, *, politica, endereco):
    origem = ", ".join(
        parte
        for parte in [
            politica.filial.endereco,
            politica.filial.municipio,
            politica.filial.uf,
        ]
        if parte
    )
    valores = {
        "origem": origem,
        "destino": endereco,
        "endereco": endereco,
        "filial": str(politica.filial),
    }
    if "{" in base_url:
        return base_url.format(**valores)
    separador = "&" if "?" in base_url else "?"
    return f"{base_url}{separador}{urlencode(valores)}"


def _decimal_geocoding(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _politica_entrega_parceiro_payload(filial):
    politica = PoliticaEntrega.objects.filter(filial=filial, is_active=True).prefetch_related("faixas").first()
    geocoding_configurado = bool(getattr(settings, "MARKETPLACE_GEOCODING_PROVIDER_URL", ""))
    if not politica:
        return {
            "contrato": "delivery_policy_v1",
            "ativa": False,
            "permite_retirada": True,
            "permite_entrega": False,
            "calculo_entrega": {
                "manual_distancia": False,
                "geocoding": geocoding_configurado,
                "timeout_segundos": getattr(settings, "MARKETPLACE_GEOCODING_TIMEOUT_SEGUNDOS", 5),
            },
            "alertas": ["Filial sem politica de entrega ativa. Envie pedidos como retirada ou configure a politica."],
        }
    faixas = list(politica.faixas.all())
    alertas = []
    if not faixas:
        alertas.append("Nenhuma faixa de taxa cadastrada.")
    if faixas and faixas[-1].distancia_final_km < politica.raio_maximo_km:
        alertas.append("A ultima faixa nao cobre todo o raio maximo.")
    bairros_atendidos = bool(str(politica.bairros_atendidos or "").strip())
    bairros_bloqueados = bool(str(politica.bairros_bloqueados or "").strip())
    return {
        "contrato": "delivery_policy_v1",
        "ativa": True,
        "permite_retirada": politica.permite_retirada,
        "permite_entrega": True,
        "raio_maximo_km": str(politica.raio_maximo_km),
        "valor_minimo_pedido": str(politica.valor_minimo_pedido),
        "frete_gratis_acima": str(politica.frete_gratis_acima) if politica.frete_gratis_acima is not None else None,
        "bairro_obrigatorio": bairros_atendidos,
        "possui_bairros_bloqueados": bairros_bloqueados,
        "horarios_entrega": politica.horarios_entrega,
        "calculo_entrega": {
            "manual_distancia": True,
            "geocoding": geocoding_configurado,
            "timeout_segundos": getattr(settings, "MARKETPLACE_GEOCODING_TIMEOUT_SEGUNDOS", 5),
        },
        "faixas": [
            {
                "distancia_inicial_km": str(faixa.distancia_inicial_km),
                "distancia_final_km": str(faixa.distancia_final_km),
                "taxa": str(faixa.taxa),
            }
            for faixa in faixas
        ],
        "alertas": alertas,
    }


def _consultar_distancia_entrega(*, politica, endereco):
    provider_url = getattr(settings, "MARKETPLACE_GEOCODING_PROVIDER_URL", "")
    if not provider_url:
        return {"status": "manual_required", "mensagem": "Geocodificacao nao configurada. Informe a distancia manualmente."}
    url = _montar_url_geocoding(provider_url, politica=politica, endereco=endereco)
    timeout = getattr(settings, "MARKETPLACE_GEOCODING_TIMEOUT_SEGUNDOS", 5)
    requisicao = Request(url, headers={"Accept": "application/json", "User-Agent": "MercaFlowERP/delivery_geocode_v1"})
    try:
        resposta = urlopen(requisicao, timeout=timeout)
        try:
            status_code = getattr(resposta, "status", 200)
            conteudo = resposta.read().decode("utf-8")
        finally:
            close = getattr(resposta, "close", None)
            if close:
                close()
    except HTTPError as exc:
        return {"status": "provider_error", "mensagem": f"Provedor de geocodificacao respondeu HTTP {exc.code}."}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": "provider_error", "mensagem": f"Falha ao consultar geocodificacao: {exc}."}
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError:
        return {"status": "provider_error", "mensagem": "Provedor de geocodificacao retornou resposta que nao e JSON."}
    if status_code >= 400 or not isinstance(dados, dict):
        return {"status": "provider_error", "mensagem": "Provedor de geocodificacao retornou formato inesperado."}
    distancia = (
        _decimal_geocoding(dados.get("distancia_km"))
        or _decimal_geocoding(dados.get("distance_km"))
        or _decimal_geocoding(dados.get("distancia"))
        or _decimal_geocoding(dados.get("distance"))
    )
    if distancia is None:
        return {"status": "provider_error", "mensagem": "Provedor de geocodificacao nao retornou distancia_km."}
    return {"status": "ok", "distancia_km": distancia, "provider_payload": dados}


def _simular_politica_entrega(request):
    try:
        politica_id = int(request.GET.get("politica", "0"))
        subtotal = Decimal(str(request.GET.get("subtotal", "0")).replace(",", "."))
        distancia_raw = str(request.GET.get("distancia", "")).strip()
        distancia = Decimal(distancia_raw.replace(",", ".")) if distancia_raw else None
        bairro = request.GET.get("bairro", "").strip()
        endereco = request.GET.get("endereco", "").strip()
    except (TypeError, ValueError, InvalidOperation):
        return {"erro": "Informe politica, subtotal e distancia validos."}
    politica = PoliticaEntrega.objects.filter(pk=politica_id, is_active=True).prefetch_related("faixas").first()
    if not politica:
        return {"erro": "Politica ativa nao encontrada."}
    geocodificacao = None
    if distancia is None:
        if not endereco:
            return {"erro": "Informe a distancia ou o endereco para calcular a entrega."}
        geocodificacao = _consultar_distancia_entrega(politica=politica, endereco=endereco)
        if geocodificacao["status"] != "ok":
            return {"erro": geocodificacao["mensagem"], "politica": politica, "subtotal": subtotal, "bairro": bairro, "endereco": endereco, "geocodificacao": geocodificacao}
        distancia = geocodificacao["distancia_km"]
    try:
        resultado = calcular_taxa_entrega(politica=politica, subtotal=subtotal, distancia_km=distancia, bairro=bairro)
    except ValidationError as exc:
        return {"erro": "; ".join(exc.messages), "politica": politica, "subtotal": subtotal, "distancia": distancia, "bairro": bairro, "endereco": endereco, "geocodificacao": geocodificacao}
    total = subtotal + Decimal(resultado["taxa"])
    return {
        "politica": politica,
        "subtotal": subtotal,
        "distancia": distancia,
        "bairro": bairro,
        "endereco": endereco,
        "geocodificacao": geocodificacao,
        "taxa": Decimal(resultado["taxa"]),
        "regra": resultado["regra"],
        "total": total,
    }


@role_required(*SISTEMA)
def politicas_entrega_diagnostico(request):
    return JsonResponse(_politicas_entrega_diagnostico())


@role_required(*SISTEMA)
def politica_entrega_form(request, pk=None):
    politica = get_object_or_404(PoliticaEntrega, pk=pk) if pk else None
    form = PoliticaEntregaForm(request.POST or None, instance=politica)
    formset = FaixaTaxaEntregaFormSet(request.POST or None, instance=politica)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            politica = form.save()
            formset.instance = politica
            faixas = formset.save(commit=False)
            for faixa in faixas:
                faixa.full_clean()
                faixa.save()
            for removida in formset.deleted_objects:
                removida.delete()
        messages.success(request, "Politica de entrega salva com sucesso.")
        return redirect("marketplace:politicas_entrega")
    return render(request, "marketplace/politica_entrega_form.html", {"form": form, "formset": formset, "politica": politica})


def _autenticar_integracao(request):
    token = request.headers.get("X-Integration-Key", "").strip()
    if not token:
        return None
    for integracao in IntegracaoMarketplace.objects.filter(is_active=True, token_prefixo=token[:12]):
        if integracao.token_valido(token):
            return integracao
    return None


@csrf_exempt
def api_status_integracao(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Metodo nao permitido."}, status=405)
    integracao = _autenticar_integracao(request)
    if not integracao:
        return JsonResponse({"erro": "Chave de integracao invalida."}, status=401)
    pedidos = integracao.pedidos.all()
    pagamentos_pendentes = pedidos.filter(
        status_pagamento=StatusPagamentoPedido.PENDENTE
    ).exclude(status=StatusPedido.CANCELADO).count()
    pedidos_abertos = pedidos.exclude(status__in=[StatusPedido.CONCLUIDO, StatusPedido.CANCELADO]).count()
    alertas = []
    politica_entrega = _politica_entrega_parceiro_payload(integracao.filial)
    if pagamentos_pendentes:
        alertas.append(f"{pagamentos_pendentes} pedido(s) com pagamento pendente.")
    if pedidos_abertos:
        alertas.append(f"{pedidos_abertos} pedido(s) em fluxo operacional.")
    alertas.extend(politica_entrega.get("alertas", []))
    integracao.ultimo_uso_em = timezone.now()
    integracao.save(update_fields=["ultimo_uso_em"])
    return JsonResponse(
        {
            "status": "ok",
            "contrato": "marketplace_partner_v1",
            "integracao": {
                "id": integracao.id,
                "nome": integracao.nome,
                "token_prefixo": integracao.token_prefixo,
                "ativa": integracao.is_active,
            },
            "filial": {
                "id": integracao.filial_id,
                "nome": integracao.filial.nome,
                "empresa": integracao.filial.empresa.nome_fantasia,
            },
            "recursos": {
                "receber_pedido": True,
                "idempotencia_por_referencia": True,
                "documento_destinatario": True,
                "calculo_entrega_manual_ou_geocoding": True,
                "politica_entrega": True,
            },
            "politica_entrega": politica_entrega,
            "pedidos": {
                "total": pedidos.count(),
                "abertos": pedidos_abertos,
                "pagamentos_pendentes": pagamentos_pendentes,
            },
            "alertas": alertas,
            "servidor_em": timezone.localtime().isoformat(),
        }
    )


@csrf_exempt
def api_receber_pedido(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Metodo nao permitido."}, status=405)
    integracao = _autenticar_integracao(request)
    if not integracao:
        return JsonResponse({"erro": "Chave de integracao invalida."}, status=401)
    if len(request.body) > 1024 * 1024:
        return JsonResponse({"erro": "Conteudo excede o limite de 1 MB."}, status=413)
    try:
        dados = json.loads(request.body)
        referencia = str(dados["referencia_externa"]).strip()
        nome_cliente = str(dados["nome_cliente"]).strip()
        itens = dados["itens"]
        tipo_entrega = dados.get("tipo_entrega", TipoEntrega.RETIRADA)
        taxa_entrega = Decimal(str(dados.get("taxa_entrega", 0)))
        desconto = Decimal(str(dados.get("desconto", 0)))
    except (json.JSONDecodeError, KeyError, TypeError, InvalidOperation):
        return JsonResponse({"erro": "JSON invalido ou campos obrigatorios ausentes."}, status=400)
    if not referencia or not nome_cliente or not isinstance(itens, list) or not itens:
        return JsonResponse({"erro": "Informe referencia_externa, nome_cliente e ao menos um item."}, status=400)
    existente = PedidoOnline.objects.filter(integracao=integracao, referencia_externa=referencia).first()
    if existente:
        return JsonResponse({"pedido_id": existente.pk, "status": existente.status, "duplicado": True}, status=200)
    try:
        with transaction.atomic():
            pedido = PedidoOnline(
                integracao=integracao,
                filial=integracao.filial,
                nome_cliente=nome_cliente,
                documento_cliente_tipo=str(dados.get("documento_cliente_tipo", "") or "NAO_IDENTIFICADO"),
                documento_cliente=str(dados.get("documento_cliente", "")),
                telefone=str(dados.get("telefone", "")),
                canal=CanalPedido.MARKETPLACE,
                tipo_entrega=tipo_entrega,
                endereco_entrega=str(dados.get("endereco_entrega", "")),
                referencia_externa=referencia,
                taxa_entrega=taxa_entrega,
                desconto=desconto,
                observacoes=str(dados.get("observacoes", "")),
                usuario=integracao.usuario,
            )
            pedido.full_clean()
            pedido.save()
            for entrada in itens:
                produto = Produto.objects.get(codigo_barras=str(entrada["codigo_barras"]), vendido_no_marketplace=True)
                quantidade = Decimal(str(entrada["quantidade"]))
                preco = Decimal(str(entrada.get("preco_unitario", produto.preco_venda)))
                item = ItemPedidoOnline(pedido=pedido, produto=produto, quantidade=quantidade, preco_unitario=preco)
                item.full_clean()
                item.save()
            pedido.recalcular()
            if dados.get("distancia_entrega_km") is not None:
                calcular_entrega_pedido(pedido=pedido, distancia_km=Decimal(str(dados["distancia_entrega_km"])), bairro_entrega=dados.get("bairro_entrega", ""))
            integracao.ultimo_uso_em = timezone.now()
            integracao.save(update_fields=["ultimo_uso_em"])
    except Produto.DoesNotExist:
        return JsonResponse({"erro": "Produto inexistente ou indisponivel para marketplace."}, status=400)
    except (KeyError, TypeError, InvalidOperation, ValidationError) as exc:
        mensagem = " ".join(exc.messages) if isinstance(exc, ValidationError) else "Item do pedido invalido."
        return JsonResponse({"erro": mensagem}, status=400)
    return JsonResponse({"pedido_id": pedido.pk, "status": pedido.status, "duplicado": False}, status=201)
