import csv
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import DetailView, ListView
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.edit import ModelFormMixin, ProcessFormView

from apps.accounts.permissions import COMPRAS, RoleRequiredMixin, role_required, supervisor_from_request
from apps.auditoria.models import LogAuditoria
from apps.estoque.models import Estoque, MovimentacaoEstoque
from apps.empresas.models import AcaoPinSupervisor
from apps.financeiro.models import ContaFinanceira, StatusContaFinanceira
from apps.fiscal.devolucao_fornecedor import (
    cancelar_rascunho_devolucao_fornecedor,
    preparar_devolucao_fornecedor,
    rascunho_ativo_da_entrada,
    salvar_rascunho_devolucao_fornecedor,
)

from .escopo import (
    cotacoes_para_usuario,
    entradas_para_usuario,
    pedidos_para_usuario,
    respostas_para_usuario,
)
from .forms import (
    CotacaoCompraForm,
    EntradaCompraForm,
    ImportarXMLEntradaForm,
    ItemCotacaoCompraFormSet,
    ItemEntradaCompraFormSet,
    ItemPedidoCompraFormSet,
    PedidoCompraForm,
    PrecoRespostaCotacaoFormSet,
    RespostaCotacaoFornecedorForm,
)
from .models import (
    CotacaoCompra,
    EntradaCompra,
    PedidoCompra,
    PrecoRespostaCotacao,
    RespostaCotacaoFornecedor,
    StatusCotacaoCompra,
    StatusEntradaCompra,
    StatusPedidoCompra,
)
from .services import (
    abrir_cotacao_compra,
    avaliar_conferencia_entrada,
    cancelar_entrada_compra,
    cancelar_pedido_compra,
    confirmar_conferencia_fisica,
    converter_pedido_em_entrada,
    enviar_pedido_compra,
    itens_conferencia_entrada,
    finalizar_entrada_compra,
    gerar_pedido_da_resposta,
    vincular_xml_a_pedido_manual,
)
from .services_xml import importar_xml_entrada


FINANCEIRO_CHOICES = [
    ("ABERTA", "Conta aberta"),
    ("PAGA", "Conta paga"),
    ("CANCELADA", "Conta cancelada"),
    ("VENCIDA", "Conta vencida"),
    ("SEM_CONTA", "Sem conta financeira"),
]


@login_required
@role_required(*COMPRAS)
def importar_xml(request):
    form = ImportarXMLEntradaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            entrada = importar_xml_entrada(
                form.cleaned_data["arquivo_xml"].read(),
                usuario=request.user,
                gerar_conta_financeira=form.cleaned_data["gerar_conta_financeira"],
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            for mensagem in exc.messages:
                form.add_error("arquivo_xml", mensagem)
        else:
            messages.success(
                request,
                "NF-e importada como rascunho. Revise todos os dados antes de finalizar.",
            )
            return redirect("compras:editar", pk=entrada.pk)
    return render(request, "compras/entrada_importar_xml.html", {"form": form})


@login_required
@role_required(*COMPRAS)
def cotacoes_compra_lista(request):
    cotacoes = cotacoes_para_usuario(request.user).select_related("filial", "usuario").prefetch_related("itens", "respostas")
    termo = (request.GET.get("q") or "").strip()
    if termo:
        cotacoes = cotacoes.filter(Q(referencia__icontains=termo) | Q(filial__nome__icontains=termo))
    status = (request.GET.get("status") or "").strip()
    if status in dict(StatusCotacaoCompra.choices):
        cotacoes = cotacoes.filter(status=status)
    por_status = {
        item["status"]: item["quantidade"]
        for item in cotacoes_para_usuario(request.user).values("status").annotate(quantidade=Count("id"))
    }
    return render(request, "compras/cotacao_list.html", {
        "cotacoes": cotacoes,
        "status_choices": StatusCotacaoCompra.choices,
        "resumo": {
            "total": sum(por_status.values()),
            "rascunhos": por_status.get(StatusCotacaoCompra.RASCUNHO, 0),
            "abertas": por_status.get(StatusCotacaoCompra.ABERTA, 0),
            "encerradas": por_status.get(StatusCotacaoCompra.ENCERRADA, 0),
        },
    })


@login_required
@role_required(*COMPRAS)
def cotacao_compra_form(request, pk=None):
    cotacao = get_object_or_404(cotacoes_para_usuario(request.user), pk=pk) if pk else None
    if cotacao and cotacao.status != StatusCotacaoCompra.RASCUNHO:
        messages.error(request, "Somente cotacoes em rascunho podem ser editadas.")
        return redirect("compras:cotacao_detalhe", pk=cotacao.pk)

    form = CotacaoCompraForm(request.POST or None, instance=cotacao, user=request.user)
    formset = ItemCotacaoCompraFormSet(request.POST or None, instance=cotacao, prefix="itens")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        nova = cotacao is None
        with transaction.atomic():
            cotacao = form.save(commit=False)
            if nova:
                cotacao.usuario = request.user
            cotacao.save()
            formset.instance = cotacao
            formset.save()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="compras",
                acao="CRIACAO_COTACAO_COMPRA" if nova else "EDICAO_COTACAO_COMPRA",
                descricao=f"Cotacao de compra {cotacao.id} {'criada' if nova else 'editada'} em rascunho.",
                objeto_tipo="CotacaoCompra",
                objeto_id=str(cotacao.id),
                ip=request.META.get("REMOTE_ADDR"),
            )
        messages.success(request, "Cotacao salva como rascunho. Nenhum estoque ou financeiro foi alterado.")
        return redirect("compras:cotacao_detalhe", pk=cotacao.pk)
    return render(request, "compras/cotacao_form.html", {"form": form, "formset": formset, "cotacao": cotacao})


@login_required
@role_required(*COMPRAS)
def cotacao_compra_detalhe(request, pk):
    cotacao = get_object_or_404(
        cotacoes_para_usuario(request.user).select_related("filial", "usuario")
        .prefetch_related(
            "itens__produto",
            "respostas__fornecedor",
            "respostas__precos__item__produto",
        ),
        pk=pk,
    )
    return render(request, "compras/cotacao_detalhe.html", {"cotacao": cotacao})


@login_required
@role_required(*COMPRAS)
def cotacao_compra_abrir(request, pk):
    cotacao = get_object_or_404(cotacoes_para_usuario(request.user).prefetch_related("itens"), pk=pk)
    if request.method == "POST":
        try:
            abrir_cotacao_compra(cotacao, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Cotacao aberta para registrar propostas de fornecedores.")
    return redirect("compras:cotacao_detalhe", pk=cotacao.pk)


@login_required
@role_required(*COMPRAS)
def cotacao_resposta_form(request, pk):
    cotacao = get_object_or_404(cotacoes_para_usuario(request.user).prefetch_related("itens__produto"), pk=pk)
    if cotacao.status != StatusCotacaoCompra.ABERTA:
        messages.error(request, "Propostas so podem ser registradas em cotacoes abertas.")
        return redirect("compras:cotacao_detalhe", pk=cotacao.pk)
    itens = list(cotacao.itens.all())
    item_queryset = cotacao.itens.select_related("produto")
    form = RespostaCotacaoFornecedorForm(request.POST or None, user=request.user, empresa_id=cotacao.filial.empresa_id)
    initial = [{"item": item.pk, "disponivel": True} for item in itens]
    formset = PrecoRespostaCotacaoFormSet(
        request.POST or None,
        prefix="precos",
        initial=None if request.method == "POST" else initial,
        form_kwargs={"item_queryset": item_queryset},
    )
    itens_por_id = {str(item.pk): item for item in itens}
    for indice, preco_form in enumerate(formset.forms):
        item_id = (
            preco_form.data.get(f"{preco_form.prefix}-item")
            if preco_form.is_bound
            else str(initial[indice]["item"])
        )
        preco_form.item_obj = itens_por_id.get(str(item_id))

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        linhas = [linha.cleaned_data for linha in formset.forms]
        ids_recebidos = [linha["item"].pk for linha in linhas]
        fornecedor = form.cleaned_data["fornecedor"]
        if cotacao.respostas.filter(fornecedor=fornecedor).exists():
            form.add_error("fornecedor", "Este fornecedor ja possui proposta nesta cotacao.")
        elif len(ids_recebidos) != len(set(ids_recebidos)) or set(ids_recebidos) != {item.pk for item in itens}:
            messages.error(request, "A proposta deve informar exatamente todos os itens da cotacao.")
        else:
            try:
                with transaction.atomic():
                    resposta = form.save(commit=False)
                    resposta.cotacao = cotacao
                    resposta.usuario = request.user
                    resposta.save()
                    PrecoRespostaCotacao.objects.bulk_create(
                        [
                            PrecoRespostaCotacao(
                                resposta=resposta,
                                item=linha["item"],
                                disponivel=linha["disponivel"],
                                custo_unitario=linha["custo_unitario"],
                            )
                            for linha in linhas
                        ]
                    )
                    LogAuditoria.objects.create(
                        usuario=request.user,
                        modulo="compras",
                        acao="REGISTRO_PROPOSTA_COTACAO",
                        descricao=f"Proposta de {resposta.fornecedor} registrada na cotacao {cotacao.id}.",
                        objeto_tipo="CotacaoCompra",
                        objeto_id=str(cotacao.id),
                        ip=request.META.get("REMOTE_ADDR"),
                    )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Proposta registrada para comparacao.")
                return redirect("compras:cotacao_detalhe", pk=cotacao.pk)
    return render(request, "compras/cotacao_resposta_form.html", {
        "cotacao": cotacao,
        "form": form,
        "formset": formset,
    })


@login_required
@role_required(*COMPRAS)
def cotacao_selecionar_resposta(request, pk, resposta_pk):
    cotacao = get_object_or_404(cotacoes_para_usuario(request.user), pk=pk)
    resposta = get_object_or_404(respostas_para_usuario(request.user), pk=resposta_pk, cotacao=cotacao)
    if request.method == "POST":
        try:
            pedido = gerar_pedido_da_resposta(
                resposta,
                usuario=request.user,
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Proposta selecionada e pedido criado como rascunho.")
            return redirect("compras:pedido_detalhe", pk=pedido.pk)
    return redirect("compras:cotacao_detalhe", pk=cotacao.pk)


@login_required
@role_required(*COMPRAS)
def pedidos_compra_lista(request):
    pedidos = pedidos_para_usuario(request.user).select_related("fornecedor", "filial", "usuario").prefetch_related("itens")
    termo = (request.GET.get("q") or "").strip()
    if termo:
        pedidos = pedidos.filter(
            Q(referencia__icontains=termo)
            | Q(fornecedor__razao_social__icontains=termo)
            | Q(fornecedor__nome_fantasia__icontains=termo)
        )
    status = (request.GET.get("status") or "").strip()
    if status in dict(StatusPedidoCompra.choices):
        pedidos = pedidos.filter(status=status)
    por_status = {
        item["status"]: item["quantidade"]
        for item in pedidos_para_usuario(request.user).values("status").annotate(quantidade=Count("id"))
    }
    return render(request, "compras/pedido_list.html", {
        "pedidos": pedidos,
        "status_choices": StatusPedidoCompra.choices,
        "resumo": {
            "total": sum(por_status.values()),
            "rascunhos": por_status.get(StatusPedidoCompra.RASCUNHO, 0),
            "enviados": por_status.get(StatusPedidoCompra.ENVIADO, 0),
            "convertidos": por_status.get(StatusPedidoCompra.CONVERTIDO, 0),
            "cancelados": por_status.get(StatusPedidoCompra.CANCELADO, 0),
        },
    })


@login_required
@role_required(*COMPRAS)
def pedido_compra_form(request, pk=None):
    pedido = get_object_or_404(pedidos_para_usuario(request.user), pk=pk) if pk else None
    if pedido and pedido.status != StatusPedidoCompra.RASCUNHO:
        messages.error(request, "Somente pedidos em rascunho podem ser editados.")
        return redirect("compras:pedido_detalhe", pk=pedido.pk)

    form = PedidoCompraForm(request.POST or None, instance=pedido, user=request.user)
    formset = ItemPedidoCompraFormSet(request.POST or None, instance=pedido, prefix="itens")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        novo = pedido is None
        with transaction.atomic():
            pedido = form.save(commit=False)
            if novo:
                pedido.usuario = request.user
            pedido.save()
            formset.instance = pedido
            itens = formset.save(commit=False)
            for item in itens:
                item.total_previsto = item.quantidade * item.custo_unitario_previsto
                item.save()
            for removido in formset.deleted_objects:
                removido.delete()
            formset.save_m2m()
            total = sum((item.total_previsto for item in pedido.itens.all()), 0)
            pedido.total_previsto = total
            pedido.save(update_fields=["total_previsto", "updated_at"])
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="compras",
                acao="CRIACAO_PEDIDO_COMPRA" if novo else "EDICAO_PEDIDO_COMPRA",
                descricao=f"Pedido de compra {pedido.id} {'criado' if novo else 'editado'} em rascunho com total previsto R$ {total}.",
                objeto_tipo="PedidoCompra",
                objeto_id=str(pedido.id),
                ip=request.META.get("REMOTE_ADDR"),
            )
        messages.success(request, "Pedido de compra salvo como rascunho. Estoque e financeiro não foram alterados.")
        return redirect("compras:pedido_detalhe", pk=pedido.pk)

    return render(request, "compras/pedido_form.html", {
        "form": form,
        "formset": formset,
        "pedido": pedido,
    })


@login_required
@role_required(*COMPRAS)
def pedido_compra_detalhe(request, pk):
    pedido = get_object_or_404(
        pedidos_para_usuario(request.user).select_related("fornecedor", "filial", "usuario").prefetch_related("itens__produto"),
        pk=pk,
    )
    return render(request, "compras/pedido_detalhe.html", {"pedido": pedido})


@login_required
@role_required(*COMPRAS)
def pedido_compra_enviar(request, pk):
    pedido = get_object_or_404(pedidos_para_usuario(request.user).prefetch_related("itens"), pk=pk)
    if request.method == "POST":
        try:
            enviar_pedido_compra(pedido, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Pedido marcado como enviado. Nenhum estoque ou financeiro foi movimentado.")
    return redirect("compras:pedido_detalhe", pk=pedido.pk)


@login_required
@role_required(*COMPRAS)
def pedido_compra_cancelar(request, pk):
    pedido = get_object_or_404(pedidos_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        try:
            cancelar_pedido_compra(
                pedido,
                usuario=request.user,
                motivo=request.POST.get("motivo", ""),
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Pedido de compra cancelado sem alterar estoque ou financeiro.")
    return redirect("compras:pedido_detalhe", pk=pedido.pk)


@login_required
@role_required(*COMPRAS)
def pedido_compra_gerar_entrada(request, pk):
    pedido = get_object_or_404(pedidos_para_usuario(request.user).prefetch_related("itens"), pk=pk)
    if request.method == "POST":
        try:
            entrada = converter_pedido_em_entrada(
                pedido,
                usuario=request.user,
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                "Entrada criada como rascunho. Confira os itens antes de finalizar; estoque e financeiro ainda não foram alterados.",
            )
            return redirect("compras:detalhe", pk=entrada.pk)
    return redirect("compras:pedido_detalhe", pk=pedido.pk)


def entradas_filtradas(params, user=None):
    queryset = entradas_para_usuario(
        user,
        EntradaCompra.objects.select_related("fornecedor", "filial", "usuario")
        .prefetch_related("contas_financeiras")
        .order_by("-data_recebimento"),
    )
    termo = (params.get("q") or "").strip()
    if termo:
        queryset = queryset.filter(Q(numero_documento__icontains=termo) | Q(fornecedor__razao_social__icontains=termo) | Q(fornecedor__nome_fantasia__icontains=termo))
    status = (params.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    financeiro = (params.get("financeiro") or "").strip()
    if financeiro == "SEM_CONTA":
        queryset = queryset.filter(contas_financeiras__isnull=True)
    elif financeiro == "VENCIDA":
        queryset = queryset.filter(contas_financeiras__status=StatusContaFinanceira.ABERTA, contas_financeiras__vencimento__lt=timezone.localdate())
    elif financeiro in dict(FINANCEIRO_CHOICES):
        queryset = queryset.filter(contas_financeiras__status=financeiro)
    return queryset.distinct()


class EntradaCompraListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = COMPRAS
    model = EntradaCompra
    template_name = "compras/entrada_list.html"
    context_object_name = "entradas"
    paginate_by = 25
    financeiro_choices = FINANCEIRO_CHOICES

    def _url_financeiro(self, financeiro):
        params = self.request.GET.copy()
        params["financeiro"] = financeiro
        return f"?{params.urlencode()}"

    def get_queryset(self):
        return entradas_filtradas(self.request.GET, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = entradas_para_usuario(self.request.user)
        por_status = {
            item["status"]: item
            for item in base_queryset.values("status").annotate(quantidade=Count("id"), total=Sum("total_produtos"))
        }
        context["resumo_compras"] = {
            "total": sum(item["quantidade"] for item in por_status.values()),
            "rascunhos": por_status.get(StatusEntradaCompra.RASCUNHO, {}).get("quantidade", 0),
            "finalizadas": por_status.get(StatusEntradaCompra.FINALIZADA, {}).get("quantidade", 0),
            "total_finalizado": por_status.get(StatusEntradaCompra.FINALIZADA, {}).get("total") or 0,
        }
        hoje = timezone.localdate()
        contas_compra = ContaFinanceira.objects.filter(entrada_compra__isnull=False)
        contas_abertas = contas_compra.filter(status=StatusContaFinanceira.ABERTA)
        context["resumo_financeiro_compras"] = {
            "abertas": contas_abertas.count(),
            "total_aberto": contas_abertas.aggregate(total=Sum("valor"))["total"] or 0,
            "url_abertas": self._url_financeiro("ABERTA"),
            "vencidas": contas_abertas.filter(vencimento__lt=hoje).count(),
            "total_vencido": contas_abertas.filter(vencimento__lt=hoje).aggregate(total=Sum("valor"))["total"] or 0,
            "url_vencidas": self._url_financeiro("VENCIDA"),
            "pagas": contas_compra.filter(status=StatusContaFinanceira.PAGA).count(),
            "total_pago": contas_compra.filter(status=StatusContaFinanceira.PAGA).aggregate(total=Sum("valor_pago"))["total"] or 0,
            "url_pagas": self._url_financeiro("PAGA"),
        }
        context["status_choices"] = StatusEntradaCompra.choices
        context["financeiro_choices"] = self.financeiro_choices
        context["filtros_ativos"] = any((self.request.GET.get("q"), self.request.GET.get("status"), self.request.GET.get("financeiro")))
        status_labels = dict(StatusEntradaCompra.choices)
        financeiro_labels = dict(self.financeiro_choices)
        filtros_aplicados = []
        if self.request.GET.get("q"):
            filtros_aplicados.append(("Busca", self.request.GET.get("q")))
        if self.request.GET.get("status"):
            filtros_aplicados.append(("Status", status_labels.get(self.request.GET.get("status"), self.request.GET.get("status"))))
        if self.request.GET.get("financeiro"):
            filtros_aplicados.append(("Financeiro", financeiro_labels.get(self.request.GET.get("financeiro"), self.request.GET.get("financeiro"))))
        context["filtros_aplicados"] = filtros_aplicados
        return context


@login_required
@role_required(*COMPRAS)
def entradas_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="compras_operacionais.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "ID",
        "Recebimento",
        "Fornecedor",
        "Filial",
        "Documento",
        "Total",
        "Status entrada",
        "Status financeiro",
        "Vencimento financeiro",
        "Data pagamento",
        "Valor financeiro",
        "Valor pago",
    ])
    for entrada in entradas_filtradas(request.GET, request.user):
        contas = list(entrada.contas_financeiras.all())
        status_financeiro = ", ".join(conta.get_status_display() for conta in contas) or "Sem conta"
        vencimentos = ", ".join(conta.vencimento.strftime("%d/%m/%Y") for conta in contas if conta.vencimento)
        pagamentos = ", ".join(conta.data_pagamento.strftime("%d/%m/%Y") for conta in contas if conta.data_pagamento)
        valor_financeiro = sum((conta.valor for conta in contas), 0)
        valor_pago = sum((conta.valor_pago or 0 for conta in contas), 0)
        writer.writerow([
            entrada.id,
            timezone.localtime(entrada.data_recebimento).strftime("%d/%m/%Y %H:%M"),
            entrada.fornecedor,
            entrada.filial,
            entrada.numero_documento,
            str(entrada.total_produtos).replace(".", ","),
            entrada.get_status_display(),
            status_financeiro,
            vencimentos,
            pagamentos,
            str(valor_financeiro).replace(".", ","),
            str(valor_pago).replace(".", ","),
        ])
    return response


@login_required
@role_required(*COMPRAS)
def entradas_imprimir(request):
    entradas = list(entradas_filtradas(request.GET, request.user))
    total_entradas = len(entradas)
    total_compras = sum((entrada.total_produtos for entrada in entradas), 0)
    total_financeiro = sum((conta.valor for entrada in entradas for conta in entrada.contas_financeiras.all()), 0)
    total_pago = sum((conta.valor_pago or 0 for entrada in entradas for conta in entrada.contas_financeiras.all()), 0)
    return render(request, "compras/entrada_imprimir.html", {
        "entradas": entradas,
        "total_entradas": total_entradas,
        "total_compras": total_compras,
        "total_financeiro": total_financeiro,
        "total_pago": total_pago,
        "gerado_em": timezone.localtime(),
        "filtros": {
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
            "financeiro": request.GET.get("financeiro", ""),
        },
    })


@login_required
@role_required(*COMPRAS)
def entrada_imprimir(request, pk):
    entrada = get_object_or_404(
        entradas_para_usuario(request.user).select_related("fornecedor", "filial", "usuario").prefetch_related(
            "itens__produto",
            "contas_financeiras__lancamentos__conta",
            "contas_financeiras__lancamentos__usuario",
        ),
        pk=pk,
    )
    movimentacoes = MovimentacaoEstoque.objects.select_related("produto", "usuario").filter(
        filial=entrada.filial,
        referencia__in=[f"entrada_compra:{entrada.id}", f"entrada_compra_cancelamento:{entrada.id}"],
    ).order_by("data", "id")
    return render(request, "compras/entrada_detalhe_imprimir.html", {
        "entrada": entrada,
        "movimentacoes_estoque": movimentacoes,
        "gerado_em": timezone.localtime(),
    })


class EntradaCompraDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    required_roles = COMPRAS
    model = EntradaCompra
    template_name = "compras/entrada_detalhe.html"
    context_object_name = "entrada"

    def get_queryset(self):
        return entradas_para_usuario(self.request.user).select_related("fornecedor", "filial", "usuario", "pedido_origem").prefetch_related(
            "itens__produto",
            "contas_financeiras__lancamentos__conta",
            "contas_financeiras__lancamentos__usuario",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entrada = self.object
        retorno_lista = self.request.GET.get("next") or reverse("compras:lista")
        if not url_has_allowed_host_and_scheme(retorno_lista, allowed_hosts={self.request.get_host()}):
            retorno_lista = reverse("compras:lista")
        context["retorno_lista_url"] = retorno_lista
        context["itens_conferencia"] = itens_conferencia_entrada(entrada)
        rascunho_devolucao = (
            rascunho_ativo_da_entrada(entrada)
            if entrada.status == StatusEntradaCompra.FINALIZADA
            else None
        )
        bloqueios_cancelamento = []
        if entrada.status == StatusEntradaCompra.FINALIZADA:
            if rascunho_devolucao:
                bloqueios_cancelamento.append(
                    "Existe uma preparação fiscal de devolução ativa para esta entrada."
                )
            if entrada.contas_financeiras.filter(status=StatusContaFinanceira.PAGA).exists():
                bloqueios_cancelamento.append("A conta financeira vinculada ja foi paga.")
            for item in entrada.itens.all():
                estoque = Estoque.objects.filter(produto=item.produto, filial=entrada.filial).first()
                saldo = estoque.quantidade_disponivel if estoque else 0
                if saldo < item.quantidade:
                    bloqueios_cancelamento.append(
                        f"Saldo insuficiente para reverter {item.produto}: disponivel {saldo}, necessario {item.quantidade}."
                    )
        context["bloqueios_cancelamento"] = bloqueios_cancelamento
        context["pode_cancelar_entrada"] = entrada.status == StatusEntradaCompra.FINALIZADA and not bloqueios_cancelamento
        context["preparacao_devolucao_fornecedor"] = (
            preparar_devolucao_fornecedor(entrada)
            if entrada.status == StatusEntradaCompra.FINALIZADA
            else None
        )
        selecoes_devolucao = {
            item.item_entrada_id: item.quantidade
            for item in (rascunho_devolucao.itens.all() if rascunho_devolucao else [])
        }
        context["rascunho_devolucao_fornecedor"] = rascunho_devolucao
        context["itens_rascunho_devolucao"] = [
            {
                "item": item,
                "quantidade_selecionada": selecoes_devolucao.get(item.pk),
                "quantidade_selecionada_html": (
                    format(selecoes_devolucao[item.pk], "f")
                    if item.pk in selecoes_devolucao
                    else ""
                ),
                "quantidade_maxima_html": format(item.quantidade, "f"),
            }
            for item in entrada.itens.all()
        ]
        context["pedidos_vinculaveis"] = PedidoCompra.objects.none()
        if entrada.status == StatusEntradaCompra.RASCUNHO and entrada.chave_acesso_xml and not entrada.pedido_origem_id:
            context["pedidos_vinculaveis"] = pedidos_para_usuario(self.request.user).filter(
                fornecedor=entrada.fornecedor,
                filial=entrada.filial,
                status=StatusPedidoCompra.ENVIADO,
                entrada_gerada__isnull=True,
            ).order_by("-enviado_em", "-id")
        context["movimentacoes_estoque"] = MovimentacaoEstoque.objects.select_related("produto", "usuario").filter(
            filial=entrada.filial,
            referencia__in=[f"entrada_compra:{entrada.id}", f"entrada_compra_cancelamento:{entrada.id}"],
        ).order_by("data", "id")
        return context


class EntradaCompraFormMixin(LoginRequiredMixin, RoleRequiredMixin, TemplateResponseMixin, ModelFormMixin, ProcessFormView):
    required_roles = COMPRAS
    model = EntradaCompra
    form_class = EntradaCompraForm
    template_name = "compras/entrada_form.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object() if self.kwargs.get("pk") else None
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if self.kwargs.get("pk") else None
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_retorno_lista_url(self):
        retorno = self.request.POST.get("next") or self.request.GET.get("next") or ""
        if retorno and url_has_allowed_host_and_scheme(retorno, allowed_hosts={self.request.get_host()}):
            return retorno
        return ""

    def get_success_url(self):
        url = reverse("compras:detalhe", args=[self.object.pk])
        retorno = self.get_retorno_lista_url()
        if retorno:
            url = f"{url}?{urlencode({'next': retorno})}"
        return url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["formset"] = ItemEntradaCompraFormSet(self.request.POST, instance=self.object)
        else:
            context["formset"] = ItemEntradaCompraFormSet(instance=self.object)
        context["retorno_lista_url"] = self.get_retorno_lista_url()
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        formset = context["formset"]
        if not formset.is_valid():
            return self.form_invalid(form)
        finalizar_agora = self.request.POST.get("acao") == "finalizar"

        with transaction.atomic():
            self.object = form.save(commit=False)
            if not self.object.pk:
                self.object.usuario = self.request.user
            self.object.save()
            formset.instance = self.object
            itens = formset.save(commit=False)
            for item in itens:
                item.total = item.quantidade * item.custo_unitario
                item.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            formset.save_m2m()
            avaliar_conferencia_entrada(self.object)
            self.object.save(update_fields=["conferencia_status", "conferencia_resumo", "updated_at"])

        if finalizar_agora:
            try:
                supervisor = supervisor_from_request(self.request, acao=AcaoPinSupervisor.COMPRA_FINALIZAR)
                finalizar_entrada_compra(self.object, supervisor=supervisor, ip=self.request.META.get("REMOTE_ADDR"))
            except ValidationError as exc:
                messages.error(self.request, "Entrada salva como rascunho. " + " ".join(exc.messages))
                return redirect(self.get_success_url())
            messages.success(self.request, "Entrada finalizada e estoque atualizado.")
            return redirect(self.get_success_url())

        messages.success(self.request, "Entrada de compra salva com sucesso.")
        return redirect(self.get_success_url())


class EntradaCompraCreateView(EntradaCompraFormMixin):
    pass


class EntradaCompraUpdateView(EntradaCompraFormMixin):
    def get_queryset(self):
        return entradas_para_usuario(self.request.user).filter(status=StatusEntradaCompra.RASCUNHO)


@login_required
@role_required(*COMPRAS)
def finalizar_entrada(request, pk):
    entrada = get_object_or_404(entradas_para_usuario(request.user).prefetch_related("itens__produto"), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)

    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.COMPRA_FINALIZAR)
        finalizar_entrada_compra(entrada, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Entrada finalizada e estoque atualizado.")

    return redirect("compras:detalhe", pk=entrada.pk)


@login_required
@role_required(*COMPRAS)
def vincular_xml_pedido_manual(request, pk):
    entrada = get_object_or_404(entradas_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)
    pedido = get_object_or_404(
        pedidos_para_usuario(request.user),
        pk=request.POST.get("pedido_id"),
        fornecedor=entrada.fornecedor,
        filial=entrada.filial,
        status=StatusPedidoCompra.ENVIADO,
        entrada_gerada__isnull=True,
    )
    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.COMPRA_VINCULAR_XML)
        vincular_xml_a_pedido_manual(
            entrada,
            pedido,
            usuario=request.user,
            supervisor=supervisor,
            justificativa=request.POST.get("justificativa", ""),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "XML vinculado ao pedido. Revise as divergências antes de finalizar a entrada.")
    return redirect("compras:detalhe", pk=entrada.pk)

@login_required
@role_required(*COMPRAS)
def confirmar_conferencia_fisica_entrada(request, pk):
    entrada = get_object_or_404(entradas_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)
    try:
        confirmar_conferencia_fisica(
            entrada,
            usuario=request.user,
            observacoes=request.POST.get("observacoes", ""),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Conferência física registrada e auditada.")
    return redirect("compras:detalhe", pk=entrada.pk)

@login_required
@role_required(*COMPRAS)
def cancelar_entrada(request, pk):
    entrada = get_object_or_404(entradas_para_usuario(request.user).prefetch_related("itens__produto", "contas_financeiras"), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)

    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.COMPRA_CANCELAR)
        cancelar_entrada_compra(
            entrada,
            usuario=request.user,
            motivo=request.POST.get("motivo", ""),
            supervisor=supervisor,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Entrada cancelada, estoque revertido e financeiro ajustado.")

    return redirect("compras:detalhe", pk=entrada.pk)


@login_required
@role_required(*COMPRAS)
def salvar_rascunho_devolucao(request, pk):
    entrada = get_object_or_404(
        entradas_para_usuario(request.user).prefetch_related("itens__produto"),
        pk=pk,
    )
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)
    selecoes = {
        item.pk: request.POST.get(f"quantidade_{item.pk}", "")
        for item in entrada.itens.all()
    }
    try:
        _, criado = salvar_rascunho_devolucao_fornecedor(
            entrada,
            selecoes=selecoes,
            motivo_operacional=request.POST.get("motivo_operacional", ""),
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        acao = "criado" if criado else "atualizado"
        messages.success(
            request,
            f"Rascunho de devolução {acao}. Nenhuma nota, estoque ou transmissão foi gerada.",
        )
    return redirect("compras:detalhe", pk=entrada.pk)


@login_required
@role_required(*COMPRAS)
def cancelar_rascunho_devolucao(request, pk):
    entrada = get_object_or_404(entradas_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)
    try:
        cancelar_rascunho_devolucao_fornecedor(
            entrada,
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            "Preparação fiscal cancelada. As quantidades foram liberadas sem alterar o estoque.",
        )
    return redirect("compras:detalhe", pk=entrada.pk)


@login_required
@role_required(*COMPRAS)
def excluir_rascunho(request, pk):
    entrada = get_object_or_404(entradas_para_usuario(request.user).select_related("pedido_origem").prefetch_related("itens"), pk=pk)
    retorno = request.POST.get("next") or reverse("compras:lista")
    if not url_has_allowed_host_and_scheme(retorno, allowed_hosts={request.get_host()}):
        retorno = reverse("compras:lista")
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)
    if entrada.status != StatusEntradaCompra.RASCUNHO:
        messages.error(request, "Somente entradas em rascunho podem ser excluídas. Entradas finalizadas devem ser canceladas com reversão.")
        return redirect("compras:detalhe", pk=entrada.pk)

    entrada_id = entrada.id
    fornecedor = str(entrada.fornecedor)
    total_itens = entrada.itens.count()
    numero_documento = entrada.numero_documento or "-"
    pedido_origem = entrada.pedido_origem
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="compras",
        acao="ENTRADA_COMPRA_RASCUNHO_EXCLUIDA",
        descricao=f"Rascunho de compra {entrada_id} excluído. Fornecedor: {fornecedor}. Documento: {numero_documento}. Itens: {total_itens}.",
        objeto_tipo="EntradaCompra",
        objeto_id=str(entrada_id),
        ip=request.META.get("REMOTE_ADDR"),
    )
    entrada.delete()
    if pedido_origem and pedido_origem.status == StatusPedidoCompra.CONVERTIDO:
        pedido_origem.status = StatusPedidoCompra.ENVIADO
        pedido_origem.save(update_fields=["status", "updated_at"])
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="compras",
            acao="REABERTURA_PEDIDO_APOS_EXCLUSAO_ENTRADA",
            descricao=(
                f"Pedido de compra {pedido_origem.id} voltou para enviado apos exclusao "
                f"da entrada em rascunho {entrada_id}."
            ),
            objeto_tipo="PedidoCompra",
            objeto_id=str(pedido_origem.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
    messages.success(request, "Rascunho de compra excluído com sucesso. Nenhum estoque ou financeiro foi movimentado.")
    return redirect(retorno)

# Create your views here.
