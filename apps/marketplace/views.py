from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, InvalidOperation
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.accounts.permissions import CADASTROS, PDV, SISTEMA, role_required
from apps.configuracoes.models import TipoDocumentoImpressao
from apps.configuracoes.services import configuracao_impressao_para, estilos_impressao
from apps.fiscal.services import preparar_documento_pedido_online

from .adapters import MarketplaceAdapterError, diagnosticar_adaptador_marketplace, normalizar_payload_marketplace
from .escopo import integracoes_para_usuario, pedidos_para_usuario, politicas_para_usuario
from .forms import CalcularEntregaForm, FaixaTaxaEntregaFormSet, IntegracaoMarketplaceForm, ItemPedidoOnlineForm, PagamentoPedidoForm, PedidoOnlineForm, PoliticaEntregaForm
from .models import CanalPedido, IntegracaoMarketplace, ItemPedidoOnline, PedidoOnline, PoliticaEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega
from .services import alterar_status_pedido, calcular_entrega_pedido, calcular_taxa_entrega, cancelar_pedido, gerar_token_integracao, registrar_pagamento, reservar_pedido
from apps.produtos.models import Produto


@role_required(*CADASTROS)
def pedidos(request):
    base_queryset = pedidos_para_usuario(request.user).select_related("filial", "cliente", "usuario")
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
    pagina = Paginator(queryset.prefetch_related("itens"), 50).get_page(request.GET.get("page"))
    pedidos_lista = list(pagina.object_list)
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
            "page_obj": pagina,
            "status_opcoes": StatusPedido.choices,
            "valor_total": resumo["valor"] or 0,
            "painel": painel,
        },
    )


@role_required(*CADASTROS)
def novo_pedido(request):
    form = PedidoOnlineForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        pedido = form.save(commit=False)
        pedido.usuario = request.user
        pedido.save()
        messages.success(request, "Pedido criado. Agora inclua os produtos.")
        return redirect("marketplace:detalhe", pk=pedido.pk)
    return render(request, "marketplace/pedido_form.html", {"form": form})


@role_required(*CADASTROS, *PDV)
def detalhe(request, pk):
    pedido = get_object_or_404(pedidos_para_usuario(request.user).select_related("filial", "cliente", "usuario").prefetch_related("itens__produto"), pk=pk)
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
    pagamento_form = PagamentoPedidoForm(initial={"valor_pago": pedido.total}, pedido=pedido)
    entrega_form = CalcularEntregaForm(initial={"distancia_entrega_km": pedido.distancia_entrega_km, "bairro_entrega": pedido.bairro_entrega})
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
            "origem_pdv": request.GET.get("origem") == "pdv",
        },
    )


@role_required(*CADASTROS, *PDV)
def imprimir_separacao(request, pk):
    pedido = get_object_or_404(pedidos_para_usuario(request.user).select_related("filial__empresa", "cliente", "usuario").prefetch_related("itens__produto"), pk=pk)
    impressao = configuracao_impressao_para(pedido.filial, TipoDocumentoImpressao.PEDIDO_SEPARACAO)
    return render(
        request,
        "marketplace/pedido_separacao_imprimir.html",
        {
            "pedido": pedido,
            "impressao": impressao,
            "estilos_impressao": estilos_impressao(impressao),
            "auto_imprimir": request.GET.get("auto") == "1",
        },
    )

@role_required(*CADASTROS, *PDV)
def impressao_separacao_desktop(request, pk):
    pedido = get_object_or_404(
        pedidos_para_usuario(request.user)
        .select_related("filial__empresa", "cliente", "usuario")
        .prefetch_related("itens__produto"),
        pk=pk,
    )
    impressao = configuracao_impressao_para(pedido.filial, TipoDocumentoImpressao.PEDIDO_SEPARACAO)
    impressora_padrao = (impressao.impressora_padrao or "").strip() if impressao else ""
    mensagem = ""
    if not impressao:
        mensagem = "Nenhuma configuração para Pedido de separação foi encontrada em Sistema > Impressoes."
    elif not impressora_padrao:
        mensagem = "A configuração de Pedido de separação não possui impressora padrão."

    def quantidade_br(valor):
        decimal = Decimal(valor or 0)
        if decimal == decimal.to_integral_value():
            return f"{decimal:.0f}"
        return f"{decimal:.3f}".replace(".", ",")

    return JsonResponse(
        {
            "status": "ok",
            "tipo": "comanda_entrega",
            "pedido": {
                "id": pedido.id,
                "empresa": str(pedido.filial.empresa),
                "filial": pedido.filial.nome,
                "criado_em": timezone.localtime(pedido.criado_em).isoformat(),
                "status": pedido.get_status_display(),
                "cliente": pedido.nome_cliente,
                "telefone": pedido.telefone,
                "endereco": pedido.endereco_entrega,
                "bairro": pedido.bairro_entrega,
                "observacoes": pedido.observacoes,
                "total": f"{pedido.total:.2f}".replace(".", ","),
                "pagamento": pedido.get_status_pagamento_display(),
                "forma_pagamento": pedido.get_forma_pagamento_display() if pedido.forma_pagamento else "",
                "referencia_pagamento": pedido.referencia_pagamento,
            },
            "itens": [
                {
                    "produto": item.produto.nome,
                    "codigo_barras": item.produto.codigo_barras,
                    "quantidade": quantidade_br(item.quantidade),
                    "unidade": item.produto.unidade,
                }
                for item in pedido.itens.all()
            ],
            "impressao": {
                "configurada": bool(impressao),
                "impressora_configurada": bool(impressora_padrao),
                "impressora_padrao": impressora_padrao,
                "modelo_papel": impressao.modelo_papel if impressao else "",
                "numero_vias": impressao.numero_vias if impressao else 1,
                "impressao_automatica": impressao.impressao_automatica if impressao else False,
                "mensagem_rodape": impressao.mensagem_rodape if impressao else "",
                "mensagem": mensagem,
                "documento_pronto": True,
            },
            "gaveta": {"abrir": False},
        }
    )

@role_required(*CADASTROS)
def remover_item(request, pk, item_id):
    pedido = get_object_or_404(pedidos_para_usuario(request.user), pk=pk, status=StatusPedido.RASCUNHO)
    if request.method == "POST":
        item = get_object_or_404(pedido.itens, pk=item_id)
        item.delete()
        pedido.recalcular()
        messages.success(request, "Item removido.")
    return redirect("marketplace:detalhe", pk=pedido.pk)


@role_required(*CADASTROS, *PDV)
def acao_pedido(request, pk):
    pedido = get_object_or_404(pedidos_para_usuario(request.user), pk=pk)
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
                raise ValidationError("A separação so pode ser informada durante essa etapa.")
            with transaction.atomic():
                for item in pedido.itens.select_for_update():
                    valor = request.POST.get(f"item_{item.pk}", "0").replace(",", ".")
                    item.quantidade_separada = valor
                    item.full_clean()
                    item.save(update_fields=["quantidade_separada"])
        elif acao == "pagamento":
            form = PagamentoPedidoForm(request.POST, pedido=pedido)
            if not form.is_valid():
                raise ValidationError("Verifique a forma e o valor do pagamento.")
            registrar_pagamento(pedido=pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
        elif acao == "preparar_nfe":
            preparar_documento_pedido_online(pedido=pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        elif acao == "calcular_entrega":
            form = CalcularEntregaForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Informe uma distância válida para a entrega.")
            calcular_entrega_pedido(pedido=pedido, **form.cleaned_data)
        else:
            raise ValidationError("Acao inválida.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Pedido atualizado com sucesso.")
    if request.POST.get("origem_pdv") == "1":
        return redirect(f"{reverse('pdv:pdv')}?delivery={pedido.pk}")
    return redirect("marketplace:detalhe", pk=pk)


@role_required(*SISTEMA)
def integracoes(request):
    diagnostico = _diagnostico_integracoes_marketplace(request.user)
    return render(
        request,
        "marketplace/integracoes.html",
        {
            "integracoes": diagnostico["integracoes"],
            "diagnostico": diagnostico,
            "novo_token": request.session.pop("marketplace_novo_token", None),
        },
    )



def _prontidao_integracao_marketplace(integracao, alertas, politica_entrega):
    bloqueios = []
    recomendacoes = []
    adaptador = diagnosticar_adaptador_marketplace(integracao.provedor)
    if not adaptador["carregavel"]:
        bloqueios.append(adaptador["erro"] or "Adaptador do parceiro indisponível.")
    if not integracao.is_active:
        bloqueios.append("Integração inativa.")
    if not politica_entrega.get("ativa") and not politica_entrega.get("permite_retirada"):
        bloqueios.append("Filial sem retirada ou entrega liberada para parceiro.")
    if not integracao.token_prefixo or not integracao.token_hash:
        bloqueios.append("Chave de integração incompleta.")
    if not integracao.ultimo_uso_em:
        recomendacoes.append("Executar chamada de status com a chave do parceiro antes do primeiro pedido real.")
    if politica_entrega.get("alertas"):
        recomendacoes.extend(politica_entrega["alertas"])
    if getattr(integracao, "pagamentos_pendentes", 0):
        recomendacoes.append("Conferir pedidos com pagamento pendente antes de liberar produção.")
    if bloqueios:
        status = "Bloqueada"
        percentual = 40
    elif recomendacoes or alertas:
        status = "Atenção"
        percentual = 75
    else:
        status = "Pronta para homologação"
        percentual = 100
    return {
        "contrato": "marketplace_partner_readiness_v1",
        "status": status,
        "percentual": percentual,
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "adaptador": adaptador,
        "proximo_passo": bloqueios[0] if bloqueios else (recomendacoes[0] if recomendacoes else "Enviar pedido piloto com idempotência e acompanhar separação, pagamento e fiscal."),
    }

def _diagnostico_integracoes_marketplace(user=None):
    integracoes = list(
        integracoes_para_usuario(user).select_related("filial__empresa", "usuario")
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
        diagnostico_adaptador = diagnosticar_adaptador_marketplace(integracao.provedor)
        if not diagnostico_adaptador["carregavel"]:
            alerta_integracao.append(diagnostico_adaptador["erro"] or "Adaptador do parceiro indisponível.")
        if not integracao.is_active:
            alerta_integracao.append("Integração inativa.")
        if not integracao.ultimo_uso_em:
            alerta_integracao.append("Chave nunca usada por parceiro externo.")
        if integracao.pagamentos_pendentes:
            alerta_integracao.append(f"{integracao.pagamentos_pendentes} pedido(s) com pagamento pendente.")
        if integracao.pedidos_abertos:
            alerta_integracao.append(f"{integracao.pedidos_abertos} pedido(s) em fluxo operacional.")
        for alerta in alerta_integracao:
            alertas.append({"integracao": integracao.nome, "mensagem": alerta})
        politica_entrega = _politica_entrega_parceiro_payload(integracao.filial)
        prontidao = _prontidao_integracao_marketplace(integracao, alerta_integracao, politica_entrega)
        integracao.alertas_operacionais = alerta_integracao
        integracao.prontidao_operacional = prontidao
        integracao.politica_entrega_payload = politica_entrega
        payload_integracoes.append(
            {
                "id": integracao.pk,
                "nome": integracao.nome,
                "provedor": integracao.provedor,
                "filial": str(integracao.filial),
                "ativa": integracao.is_active,
                "token_prefixo": integracao.token_prefixo,
                "total_pedidos": integracao.total_pedidos,
                "pedidos_abertos": integracao.pedidos_abertos,
                "pagamentos_pendentes": integracao.pagamentos_pendentes,
                "ultimo_uso_em": integracao.ultimo_uso_em.isoformat() if integracao.ultimo_uso_em else None,
                "ultimo_pedido_em": integracao.ultimo_pedido_em.isoformat() if integracao.ultimo_pedido_em else None,
                "alertas": alerta_integracao,
                "politica_entrega": politica_entrega,
                "prontidao": prontidao,
            }
        )
    resumo = {
        "integracoes": len(integracoes),
        "ativas": sum(1 for item in integracoes if item.is_active),
        "pedidos_recebidos": sum(item.total_pedidos for item in integracoes),
        "pedidos_abertos": sum(item.pedidos_abertos for item in integracoes),
        "pagamentos_pendentes": sum(item.pagamentos_pendentes for item in integracoes),
        "alertas": len(alertas),
        "prontas_homologacao": sum(1 for item in integracoes if getattr(item, "prontidao_operacional", {}).get("status") == "Pronta para homologação"),
        "com_bloqueio": sum(1 for item in integracoes if getattr(item, "prontidao_operacional", {}).get("status") == "Bloqueada"),
    }
    return {"gerado_em": timezone.now(), "resumo": resumo, "integracoes": integracoes, "payload_integracoes": payload_integracoes, "alertas": alertas}


@role_required(*SISTEMA)
def integracoes_diagnostico(request):
    diagnostico = _diagnostico_integracoes_marketplace(request.user)
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
    form = IntegracaoMarketplaceForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        integracao = form.save(commit=False)
        integracao.usuario = request.user
        integracao.token_prefixo = "temporario"
        integracao.token_hash = "temporario"
        integracao.save()
        request.session["marketplace_novo_token"] = gerar_token_integracao(integracao)
        messages.success(request, "Integração criada. Guarde a chave exibida, pois ela não será mostrada novamente.")
        return redirect("marketplace:integracoes")
    return render(request, "marketplace/integracao_form.html", {"form": form})


@role_required(*SISTEMA)
def renovar_token(request, pk):
    integracao = get_object_or_404(integracoes_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        request.session["marketplace_novo_token"] = gerar_token_integracao(integracao)
        messages.success(request, "Chave renovada. A chave anterior deixou de funcionar.")
    return redirect("marketplace:integracoes")


@role_required(*SISTEMA)
def politicas_entrega(request):
    politicas = politicas_para_usuario(request.user).select_related("filial__empresa").prefetch_related("faixas")
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


def _politicas_entrega_diagnostico(user=None):
    politicas = politicas_para_usuario(user).select_related("filial__empresa").prefetch_related("faixas")
    provider_configurado = bool(getattr(settings, "MARKETPLACE_GEOCODING_PROVIDER_URL", ""))
    itens = []
    resumo = {"politicas": 0, "ativas": 0, "sem_faixas": 0, "com_alerta": 0}
    for politica in politicas:
        faixas = list(politica.faixas.all())
        alertas = []
        if not politica.is_active:
            alertas.append("Política inativa.")
        if not faixas:
            alertas.append("Nenhuma faixa de taxa cadastrada.")
        if faixas and faixas[0].distancia_inicial_km > 0:
            alertas.append("A primeira faixa não comeca em 0 km.")
        for anterior, atual in zip(faixas, faixas[1:]):
            if atual.distancia_inicial_km > anterior.distancia_final_km:
                alertas.append("Existem lacunas entre as faixas de distância.")
                break
            if atual.distancia_inicial_km < anterior.distancia_final_km:
                alertas.append("Existem faixas de distância sobrepostas.")
                break
        if faixas and faixas[-1].distancia_final_km < politica.raio_maximo_km:
            alertas.append("A ultima faixa não cobre todo o raio máximo.")
        if politica.valor_minimo_pedido <= 0:
            alertas.append("Pedido mínimo zerado.")
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
                "prontidao": {
                    "status": (
                        "blocked"
                        if alertas
                        else "ready_for_provider_homologation"
                        if provider_configurado
                        else "ready_with_manual_distance"
                    ),
                    "calculo_manual_disponivel": True,
                    "provider_configurado": provider_configurado,
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
        )
    if not itens:
        prontidao_status = "no_policy_configured"
        prontidao_percentual = 25
        recomendacoes = ["Cadastre ao menos uma política de entrega por filial que realiza entregas."]
    elif resumo["com_alerta"]:
        prontidao_status = "configuration_required"
        prontidao_percentual = 65
        recomendacoes = ["Corrija os alertas de faixa, raio e pedido mínimo antes de liberar pedidos para entrega."]
    elif not provider_configurado:
        prontidao_status = "ready_with_manual_distance"
        prontidao_percentual = 85
        recomendacoes = ["Escolha e homologue um provedor de mapa/rota; o calculo manual permanece disponível."]
    else:
        prontidao_status = "ready_for_provider_homologation"
        prontidao_percentual = 92
        recomendacoes = ["Homologue rotas, timeout e indisponibilidade do provedor com endereços reais das filiais."]
    return {
        "resumo": resumo,
        "prontidao": {
            "contrato": "delivery_policy_readiness_v1",
            "status": prontidao_status,
            "percentual": prontidao_percentual,
            "provider_configurado": provider_configurado,
            "fallback_manual_distancia": True,
            "recomendacoes": recomendacoes,
        },
        "politicas": itens,
        "geocodificacao": {
            "contrato": "delivery_geocode_v1",
            "provider_configurado": provider_configurado,
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
            "alertas": ["Filial sem política de entrega ativa. Envie pedidos como retirada ou configure a política."],
        }
    faixas = list(politica.faixas.all())
    alertas = []
    if not faixas:
        alertas.append("Nenhuma faixa de taxa cadastrada.")
    if faixas and faixas[-1].distancia_final_km < politica.raio_maximo_km:
        alertas.append("A ultima faixa não cobre todo o raio máximo.")
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
        return {"status": "manual_required", "mensagem": "Geocodificação não configurada. Informe a distância manualmente."}
    url = _montar_url_geocoding(provider_url, politica=politica, endereco=endereco)
    timeout = getattr(settings, "MARKETPLACE_GEOCODING_TIMEOUT_SEGUNDOS", 5)
    requisicao = Request(url, headers={"Accept": "application/json", "User-Agent": "DeigoVarejoERP/delivery_geocode_v1"})
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
        return {"status": "provider_error", "mensagem": f"Provedor de geocodificação respondeu HTTP {exc.code}."}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": "provider_error", "mensagem": f"Falha ao consultar geocodificação: {exc}."}
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError:
        return {"status": "provider_error", "mensagem": "Provedor de geocodificação retornou resposta que não é JSON."}
    if status_code >= 400 or not isinstance(dados, dict):
        return {"status": "provider_error", "mensagem": "Provedor de geocodificação retornou formato inesperado."}
    distancia = (
        _decimal_geocoding(dados.get("distancia_km"))
        or _decimal_geocoding(dados.get("distance_km"))
        or _decimal_geocoding(dados.get("distancia"))
        or _decimal_geocoding(dados.get("distance"))
    )
    if distancia is None:
        return {"status": "provider_error", "mensagem": "Provedor de geocodificação não retornou distancia_km."}
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
        return {"erro": "Informe política, subtotal e distância válidos."}
    politica = politicas_para_usuario(request.user).filter(pk=politica_id, is_active=True).prefetch_related("faixas").first()
    if not politica:
        return {"erro": "Política ativa não encontrada."}
    geocodificacao = None
    if distancia is None:
        if not endereco:
            return {"erro": "Informe a distância ou o endereço para calcular a entrega."}
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
    return JsonResponse(_politicas_entrega_diagnostico(request.user))


@role_required(*SISTEMA)
def politica_entrega_form(request, pk=None):
    politica = get_object_or_404(politicas_para_usuario(request.user), pk=pk) if pk else None
    form = PoliticaEntregaForm(request.POST or None, instance=politica, user=request.user)
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
        messages.success(request, "Política de entrega salva com sucesso.")
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
        return JsonResponse({"erro": "Método não permitido."}, status=405)
    integracao = _autenticar_integracao(request)
    if not integracao:
        return JsonResponse({"erro": "Chave de integração inválida."}, status=401)
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
    prontidao = _prontidao_integracao_marketplace(integracao, alertas, politica_entrega)
    integracao.ultimo_uso_em = timezone.now()
    integracao.save(update_fields=["ultimo_uso_em"])
    return JsonResponse(
        {
            "status": "ok",
            "contrato": "marketplace_partner_v1",
            "integracao": {
                "id": integracao.id,
                "nome": integracao.nome,
                "provedor": integracao.provedor,
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
            "prontidao": prontidao,
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
        return JsonResponse({"erro": "Método não permitido."}, status=405)
    integracao = _autenticar_integracao(request)
    if not integracao:
        return JsonResponse({"erro": "Chave de integração inválida."}, status=401)
    if len(request.body) > 1024 * 1024:
        return JsonResponse({"erro": "Conteudo excede o limite de 1 MB."}, status=413)
    try:
        payload_recebido = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido ou campos obrigatorios ausentes."}, status=400)
    try:
        dados = normalizar_payload_marketplace(integracao, payload_recebido)
    except ImproperlyConfigured as exc:
        return JsonResponse({"erro": str(exc), "contrato": "marketplace_partner_adapter_v1"}, status=503)
    except MarketplaceAdapterError as exc:
        return JsonResponse({"erro": str(exc), "contrato": "marketplace_partner_adapter_v1"}, status=400)
    try:
        referencia = str(dados["referencia_externa"]).strip()
        nome_cliente = str(dados["nome_cliente"]).strip()
        itens = dados["itens"]
        tipo_entrega = dados.get("tipo_entrega", TipoEntrega.RETIRADA)
        taxa_entrega = Decimal(str(dados.get("taxa_entrega", 0)))
        desconto = Decimal(str(dados.get("desconto", 0)))
    except (KeyError, TypeError, InvalidOperation):
        return JsonResponse({"erro": "Pedido normalizado sem os campos obrigatorios."}, status=400)
    if not referencia or not nome_cliente or not isinstance(itens, list) or not itens:
        return JsonResponse({"erro": "Informe referencia_externa, nome_cliente e ao menos um item."}, status=400)
    existente = integracao.pedidos.filter(referencia_externa=referencia).first()
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
                bairro_entrega=str(dados.get("bairro_entrega", "")).strip(),
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
        return JsonResponse({"erro": "Produto inexistente ou indisponível para marketplace."}, status=400)
    except (KeyError, TypeError, InvalidOperation, ValidationError) as exc:
        mensagem = " ".join(exc.messages) if isinstance(exc, ValidationError) else "Item do pedido inválido."
        return JsonResponse({"erro": mensagem}, status=400)
    return JsonResponse({"pedido_id": pedido.pk, "status": pedido.status, "duplicado": False}, status=201)
