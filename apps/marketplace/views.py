from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, InvalidOperation
import json

from apps.accounts.permissions import CADASTROS, SISTEMA, role_required
from apps.configuracoes.models import TipoDocumentoImpressao
from apps.configuracoes.services import configuracao_impressao_para, estilos_impressao

from .forms import CalcularEntregaForm, FaixaTaxaEntregaFormSet, IntegracaoMarketplaceForm, ItemPedidoOnlineForm, PagamentoPedidoForm, PedidoOnlineForm, PoliticaEntregaForm
from .models import CanalPedido, IntegracaoMarketplace, ItemPedidoOnline, PedidoOnline, PoliticaEntrega, StatusPedido, TipoEntrega
from .services import alterar_status_pedido, calcular_entrega_pedido, cancelar_pedido, gerar_token_integracao, registrar_pagamento, reservar_pedido
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
    return render(request, "marketplace/pedidos.html", {"pedidos": queryset[:100], "status_opcoes": StatusPedido.choices, "valor_total": resumo["valor"] or 0, "painel": painel})


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
    return render(request, "marketplace/integracoes.html", {"integracoes": IntegracaoMarketplace.objects.select_related("filial__empresa", "usuario"), "novo_token": request.session.pop("marketplace_novo_token", None)})


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
    return render(request, "marketplace/politicas_entrega.html", {"politicas": politicas})


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
                calcular_entrega_pedido(pedido=pedido, distancia_km=Decimal(str(dados["distancia_entrega_km"])))
            integracao.ultimo_uso_em = timezone.now()
            integracao.save(update_fields=["ultimo_uso_em"])
    except Produto.DoesNotExist:
        return JsonResponse({"erro": "Produto inexistente ou indisponivel para marketplace."}, status=400)
    except (KeyError, TypeError, InvalidOperation, ValidationError) as exc:
        mensagem = " ".join(exc.messages) if isinstance(exc, ValidationError) else "Item do pedido invalido."
        return JsonResponse({"erro": mensagem}, status=400)
    return JsonResponse({"pedido_id": pedido.pk, "status": pedido.status, "duplicado": False}, status=201)
