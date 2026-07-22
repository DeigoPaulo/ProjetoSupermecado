from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import CADASTROS, RoleRequiredMixin, role_required, supervisor_from_request
from apps.configuracoes.models import ConfiguracaoImpressao, TipoDocumentoImpressao
from apps.configuracoes.services import configuracao_impressao_para
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.promocoes.services import preco_atual_produto

from .forms import CategoriaForm, EtiquetaProdutoForm, MarcaForm, ProdutoForm, ProdutoImagemFormSet, ProdutoImportCSVForm, ReajustePrecoForm
from .models import Categoria, Marca, Produto
from .services import aplicar_reajuste_precos, importar_produtos_csv, simular_reajuste_precos


def _select2_payload(objeto, texto, **extra):
    return {"id": objeto.pk, "text": texto, **extra}


class ProdutoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = CADASTROS
    model = Produto
    template_name = "produtos/produto_list.html"
    context_object_name = "produtos"
    paginate_by = 25

    def get_queryset(self):
        queryset = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(Q(nome__icontains=termo) | Q(codigo_barras__icontains=termo))
        return queryset


class ProdutoGaleriaMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["galeria_formset"] = ProdutoImagemFormSet(
                self.request.POST, self.request.FILES, instance=self.object, prefix="galeria"
            )
        else:
            context["galeria_formset"] = ProdutoImagemFormSet(instance=self.object, prefix="galeria")
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        galeria_formset = context["galeria_formset"]
        if not galeria_formset.is_valid():
            return self.form_invalid(form)
        with transaction.atomic():
            self.object = form.save()
            galeria_formset.instance = self.object
            galeria_formset.save()
        messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())


class ProdutoCreateView(ProdutoGaleriaMixin, LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista")
    success_message = "Produto cadastrado com sucesso."


class ProdutoUpdateView(ProdutoGaleriaMixin, LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = CADASTROS
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista")
    success_message = "Produto atualizado com sucesso."

    def get_queryset(self):
        return Produto.all_objects.all()

class CategoriaCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = Categoria
    form_class = CategoriaForm
    template_name = "produtos/categoria_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Categoria cadastrada com sucesso.")
        return super().form_valid(form)


class MarcaCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = Marca
    form_class = MarcaForm
    template_name = "produtos/marca_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Marca cadastrada com sucesso.")
        return super().form_valid(form)


@login_required
@role_required(*CADASTROS)
@require_GET
def categorias_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    if not termo:
        return JsonResponse({"results": []})
    categorias = Categoria.objects.filter(Q(nome__icontains=termo) | Q(descricao__icontains=termo)).order_by("nome")[:20]
    return JsonResponse(
        {
            "results": [
                _select2_payload(categoria, categoria.nome, descricao=categoria.descricao, ativa=categoria.is_active)
                for categoria in categorias
            ]
        }
    )


@login_required
@role_required(*CADASTROS)
@require_GET
def marcas_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    if not termo:
        return JsonResponse({"results": []})
    marcas = Marca.objects.filter(nome__icontains=termo).order_by("nome")[:20]
    return JsonResponse(
        {
            "results": [
                _select2_payload(marca, marca.nome, ativa=marca.is_active)
                for marca in marcas
            ]
        }
    )


@login_required
@role_required(*CADASTROS)
def importar_csv(request):
    resultado = None
    if request.method == "POST":
        form = ProdutoImportCSVForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                resultado = importar_produtos_csv(
                    form.cleaned_data["arquivo"],
                    atualizar_existentes=form.cleaned_data["atualizar_existentes"],
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Importacao concluida: {resultado['criados']} criados, {resultado['atualizados']} atualizados, {resultado['ignorados']} ignorados.",
                )
                if not resultado["erros"]:
                    return redirect("produtos:lista")
    else:
        form = ProdutoImportCSVForm()

    return render(request, "produtos/importar_csv.html", {"form": form, "resultado": resultado})


@login_required
@role_required(*CADASTROS)
def reajustar_precos(request):
    preview = []
    total_afetado = 0
    form = ReajustePrecoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        if request.POST.get("confirmar") == "1":
            try:
                supervisor = supervisor_from_request(request)
                total = aplicar_reajuste_precos(
                    usuario=request.user,
                    categoria=dados["categoria"],
                    marca=dados["marca"],
                    percentual=dados["percentual"],
                    motivo=dados["motivo"],
                    aplicar_em_promocional=dados["aplicar_em_promocional"],
                    supervisor=supervisor,
                    ip=request.META.get("REMOTE_ADDR"),
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, f"Reajuste aplicado em {total} produto(s).")
                return redirect("produtos:lista")

        preview, total_afetado = simular_reajuste_precos(
            categoria=dados["categoria"],
            marca=dados["marca"],
            percentual=dados["percentual"],
            aplicar_em_promocional=dados["aplicar_em_promocional"],
        )

    return render(
        request,
        "produtos/reajuste_precos.html",
        {
            "form": form,
            "preview": preview,
            "total_afetado": total_afetado,
        },
    )


@login_required
@role_required(*CADASTROS)
def etiquetas(request):
    perfil = getattr(request.user, "perfil_supermercado", None)
    filial = perfil.filial if perfil else None
    form = EtiquetaProdutoForm(request.GET or None, filial=filial)
    produtos = []
    etiquetas_lista = []
    quantidade_copias = 1
    configuracao_etiqueta = configuracao_impressao_para(filial, TipoDocumentoImpressao.ETIQUETA)
    if not configuracao_etiqueta:
        configuracao_etiqueta = ConfiguracaoImpressao.objects.filter(
            filial__isnull=True,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            is_active=True,
        ).order_by("empresa_id").first()
    if form.is_valid() and request.GET:
        dados = form.cleaned_data
        quantidade_copias = dados["quantidade_copias"]
        queryset = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
        if not dados["incluir_inativos"]:
            queryset = queryset.filter(is_active=True)
        if dados["busca"]:
            busca = dados["busca"].strip()
            queryset = queryset.filter(
                Q(codigo_barras__iexact=busca)
                | Q(codigo_interno__iexact=busca)
                | Q(codigo_barras__icontains=busca)
                | Q(codigo_interno__icontains=busca)
                | Q(nome__icontains=busca)
            )
        if dados["categoria"]:
            queryset = queryset.filter(categoria=dados["categoria"])
        if dados["marca"]:
            queryset = queryset.filter(marca=dados["marca"])
        produtos = list(queryset[:200])
        for produto in produtos:
            produto.preco_etiqueta = preco_atual_produto(produto)
            for _ in range(dados["quantidade_copias"]):
                etiquetas_lista.append(produto)

    modelo_salvo = form.cleaned_data.get("modelo_salvo") if form.is_valid() else None
    if form.is_valid() and form.cleaned_data.get("modelo") == EtiquetaProdutoForm.MODELO_CONFIGURADO and not modelo_salvo:
        modelo_salvo = form.fields["modelo_salvo"].queryset.filter(padrao=True).first()
    if modelo_salvo:
        configuracao_etiqueta = modelo_salvo.configuracao

    modelo_etiqueta = form.cleaned_data.get("modelo", EtiquetaProdutoForm.MODELO_COMPACTO) if form.is_valid() else EtiquetaProdutoForm.MODELO_COMPACTO
    dimensoes_modelo = {
        EtiquetaProdutoForm.MODELO_COMPACTO: {"largura_mm": 110, "altura_mm": 30, "gap_horizontal_mm": 2, "gap_vertical_mm": 2, "colunas": 1},
        EtiquetaProdutoForm.MODELO_COMPLETO: {"largura_mm": 100, "altura_mm": 50, "gap_horizontal_mm": 2, "gap_vertical_mm": 2, "colunas": 1},
    }.get(modelo_etiqueta)
    if modelo_etiqueta == EtiquetaProdutoForm.MODELO_CONFIGURADO and modelo_salvo:
        dimensoes_modelo = {
            "id": modelo_salvo.id,
            "nome": modelo_salvo.nome,
            "largura_mm": float(modelo_salvo.largura_mm),
            "altura_mm": float(modelo_salvo.altura_mm),
            "gap_horizontal_mm": float(modelo_salvo.gap_horizontal_mm),
            "gap_vertical_mm": float(modelo_salvo.gap_vertical_mm),
            "colunas": modelo_salvo.colunas,
            "orientacao": modelo_salvo.orientacao,
        }
    elif modelo_etiqueta == EtiquetaProdutoForm.MODELO_CONFIGURADO and configuracao_etiqueta:
        dimensoes_modelo = {
            "largura_mm": float(configuracao_etiqueta.largura_etiqueta_mm),
            "altura_mm": float(configuracao_etiqueta.altura_etiqueta_mm),
            "gap_horizontal_mm": float(configuracao_etiqueta.gap_horizontal_mm),
            "gap_vertical_mm": float(configuracao_etiqueta.gap_vertical_mm),
            "colunas": configuracao_etiqueta.colunas_etiqueta,
        }
    linguagens_nativas = {"ZPL", "EPL", "PPLA", "PPLB"}
    impressao_nativa_disponivel = bool(
        produtos
        and dimensoes_modelo
        and configuracao_etiqueta
        and configuracao_etiqueta.impressora_padrao
        and configuracao_etiqueta.linguagem_impressora in linguagens_nativas
    )
    payload_etiquetas = None
    if impressao_nativa_disponivel:
        payload_etiquetas = {
            "impressora_padrao": configuracao_etiqueta.impressora_padrao,
            "linguagem": configuracao_etiqueta.linguagem_impressora,
            "dpi": configuracao_etiqueta.dpi_impressora,
            "densidade": configuracao_etiqueta.densidade_impressao,
            "velocidade": configuracao_etiqueta.velocidade_impressao,
            "tipo_midia": configuracao_etiqueta.tipo_midia_etiqueta,
            "modelo": dimensoes_modelo,
            "itens": [
                {
                    "produto_id": produto.id,
                    "nome": produto.nome,
                    "codigo": produto.codigo_barras or produto.codigo_interno,
                    "preco": str(produto.preco_etiqueta),
                    "unidade": produto.unidade,
                    "copias": quantidade_copias,
                }
                for produto in produtos
            ],
        }

    return render(
        request,
        "produtos/etiquetas.html",
        {
            "form": form,
            "produtos": produtos,
            "etiquetas": etiquetas_lista,
            "modelo_etiqueta": modelo_etiqueta,
            "configuracao_etiqueta": configuracao_etiqueta,
            "modelo_salvo": modelo_salvo,
            "impressao_nativa_disponivel": impressao_nativa_disponivel,
            "payload_etiquetas": payload_etiquetas,
        },
    )


@login_required
@role_required(*CADASTROS)
def kardex(request, pk):
    produto = get_object_or_404(Produto.all_objects.select_related("categoria", "marca"), pk=pk)
    movimentacoes = MovimentacaoEstoque.objects.filter(produto=produto).select_related("filial", "usuario").order_by("-data")
    estoques = Estoque.objects.filter(produto=produto).select_related("filial").order_by("filial__nome")
    entradas = movimentacoes.filter(tipo__in=[TipoMovimentacaoEstoque.ENTRADA, TipoMovimentacaoEstoque.DEVOLUCAO, TipoMovimentacaoEstoque.AJUSTE]).aggregate(total=Sum("quantidade"))["total"] or 0
    saidas = movimentacoes.filter(tipo__in=[TipoMovimentacaoEstoque.SAIDA, TipoMovimentacaoEstoque.VENDA, TipoMovimentacaoEstoque.PERDA]).aggregate(total=Sum("quantidade"))["total"] or 0

    return render(
        request,
        "produtos/kardex.html",
        {
            "produto": produto,
            "movimentacoes": movimentacoes[:200],
            "estoques": estoques,
            "entradas": entradas,
            "saidas": saidas,
            "saldo_total": estoques.aggregate(total=Sum("quantidade_atual"))["total"] or 0,
            "reservado_total": estoques.aggregate(total=Sum("quantidade_reservada"))["total"] or 0,
        },
    )

# Create your views here.
