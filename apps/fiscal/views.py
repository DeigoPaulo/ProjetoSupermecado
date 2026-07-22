from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import RELATORIOS, SISTEMA, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Filial
from apps.produtos.models import Produto
from apps.vendas.models import StatusVenda, Venda

from .certificados import salvar_certificado_a1
from .forms import ConfiguracaoFiscalForm, NaturezaOperacaoForm, SerieFiscalForm
from .models import ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from .services import (
    cancelar_documento,
    pendencias_preparacao_fiscal,
    pendencias_produto_fiscal,
    preparar_documento_venda,
    salvar_xml_documento,
    transmitir_documento_simulado,
)


def _diagnostico_prontidao_fiscal():
    configuracoes = {config.filial_id: config for config in ConfiguracaoFiscal.objects.select_related("filial")}
    series_nfce = {
        serie.filial_id: serie
        for serie in SerieFiscal.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True).select_related("filial")
    }
    natureza_nfce = NaturezaOperacao.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True).first()
    regimes = list(ConfiguracaoFiscal.objects.exclude(regime_tributario="").values_list("regime_tributario", flat=True))
    produtos_pendentes = 0
    for produto in Produto.all_objects.select_related("categoria", "marca")[:500]:
        if pendencias_produto_fiscal(produto, regimes):
            produtos_pendentes += 1
    vendas_pendentes_qs = Venda.objects.filter(status=StatusVenda.FINALIZADA, documentos_fiscais__isnull=True)
    filiais = []
    alertas = []
    for filial in Filial.objects.select_related("empresa").order_by("empresa__nome_fantasia", "nome"):
        config = configuracoes.get(filial.id)
        serie = series_nfce.get(filial.id)
        pendencias = []
        if not config:
            pendencias.append("Configuração fiscal ausente.")
        else:
            if not config.ativo:
                pendencias.append("Configuração fiscal inativa.")
            if config.certificado_status != "valido":
                pendencias.append(f"Certificado {config.certificado_status.replace('_', ' ')}.")
            if not config.csc_id or not config.csc_token:
                pendencias.append("CSC/Token NFC-e incompleto.")
            if not config.inscricao_estadual:
                pendencias.append("Inscrição estadual ausente.")
        if not filial.uf or not filial.codigo_municipio_ibge:
            pendencias.append("UF ou código IBGE da filial ausente.")
        if not serie:
            pendencias.append("Série NFC-e ativa ausente.")
        if not natureza_nfce:
            pendencias.append("Natureza de operação NFC-e ativa ausente.")
        vendas_pendentes = vendas_pendentes_qs.filter(filial=filial).count()
        if vendas_pendentes:
            pendencias.append(f"{vendas_pendentes} venda(s) aguardando NFC-e.")
        status = "Pronta" if not pendencias else "Atenção"
        for pendencia in pendencias:
            alertas.append({"filial": str(filial), "mensagem": pendencia})
        filiais.append(
            {
                "id": filial.id,
                "filial": str(filial),
                "ambiente": config.get_ambiente_display() if config else "-",
                "certificado": config.certificado_status if config else "nao_configurado",
                "serie_nfce": serie.serie if serie else None,
                "proximo_numero": serie.proximo_numero if serie else None,
                "vendas_pendentes": vendas_pendentes,
                "pendencias": pendencias,
                "status": status,
            }
        )
    resumo = {
        "filiais": len(filiais),
        "filiais_prontas": sum(1 for filial in filiais if filial["status"] == "Pronta"),
        "alertas": len(alertas),
        "produtos_pendentes": produtos_pendentes,
        "vendas_pendentes": vendas_pendentes_qs.count(),
        "documentos_prontos": DocumentoFiscal.objects.filter(status=StatusDocumentoFiscal.PRONTO).count(),
        "documentos_rejeitados": DocumentoFiscal.objects.filter(status=StatusDocumentoFiscal.REJEITADO).count(),
    }
    return {"resumo": resumo, "filiais": filiais, "alertas": alertas}


@login_required
@role_required(*RELATORIOS)
def documentos(request):
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    documentos_qs = DocumentoFiscal.objects.select_related("filial", "venda", "pedido_online", "natureza_operacao", "usuario")
    if status:
        documentos_qs = documentos_qs.filter(status=status)
    if q:
        documentos_qs = documentos_qs.filter(numero__icontains=q)
    vendas_pendentes = list(
        Venda.objects.select_related("filial", "cliente", "usuario")
        .prefetch_related("itens__produto")
        .filter(status=StatusVenda.FINALIZADA, documentos_fiscais__isnull=True)
        .order_by("-data")[:50]
    )
    configuracoes_por_filial = {config.filial_id: config for config in ConfiguracaoFiscal.objects.all()}
    filiais_com_serie = set(
        SerieFiscal.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True).values_list("filial_id", flat=True)
    )
    natureza_padrao = NaturezaOperacao.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True).first()
    for venda in vendas_pendentes:
        configuracao = configuracoes_por_filial.get(venda.filial_id)
        if not configuracao:
            pendencias = ["Configure os dados fiscais da filial."]
        elif not configuracao.ativo:
            pendencias = ["A configuracao fiscal da filial esta inativa."]
        else:
            pendencias = pendencias_preparacao_fiscal(venda, configuracao, natureza_padrao)
        if venda.filial_id not in filiais_com_serie:
            pendencias.append("Cadastre uma serie NFC-e ativa para a filial.")
        venda.pendencias_fiscais = pendencias
        venda.pronta_fiscal = not pendencias
    logs_pendencia = {}
    for log in LogAuditoria.objects.filter(
        modulo="fiscal",
        acao="PREPARA_DOCUMENTO_PENDENTE",
        objeto_tipo="Venda",
        objeto_id__in=[str(venda.id) for venda in vendas_pendentes],
    ).order_by("-criado_em"):
        logs_pendencia.setdefault(log.objeto_id, log)
    for venda in vendas_pendentes:
        venda.ultima_tentativa_fiscal = logs_pendencia.get(str(venda.id))
    context = {
        "diagnostico": _diagnostico_prontidao_fiscal(),
        "documentos": documentos_qs[:200],
        "status": status,
        "q": q,
        "status_choices": StatusDocumentoFiscal.choices,
        "vendas_pendentes": vendas_pendentes,
        "configuracoes": ConfiguracaoFiscal.objects.select_related("filial"),
        "series": SerieFiscal.objects.select_related("filial"),
        "naturezas": NaturezaOperacao.objects.all(),
        "total_documentos": documentos_qs.count(),
        "pendentes": documentos_qs.filter(status="PRONTO").count(),
        "emitidos": documentos_qs.filter(status="EMITIDO").count(),
        "rejeitados": documentos_qs.filter(status="REJEITADO").count(),
        "pendencias_automaticas": len(logs_pendencia),
    }
    return render(request, "fiscal/documentos.html", context)


@login_required
@role_required(*RELATORIOS)
def diagnostico_json(request):
    return JsonResponse(_diagnostico_prontidao_fiscal())


@login_required
@role_required(*RELATORIOS)
def produtos_fiscais(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "pendentes")
    produtos_qs = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
    if q:
        produtos_qs = produtos_qs.filter(nome__icontains=q) | produtos_qs.filter(codigo_barras__icontains=q)
    regimes = list(ConfiguracaoFiscal.objects.exclude(regime_tributario="").values_list("regime_tributario", flat=True))
    produtos = []
    total_pendentes = 0
    for produto in produtos_qs[:500]:
        produto.pendencias_fiscais = pendencias_produto_fiscal(produto, regimes)
        produto.pronto_fiscal = not produto.pendencias_fiscais
        if produto.pendencias_fiscais:
            total_pendentes += 1
        if filtro == "todos" or (filtro == "prontos" and produto.pronto_fiscal) or (filtro == "pendentes" and not produto.pronto_fiscal):
            produtos.append(produto)
    context = {
        "produtos": produtos,
        "q": q,
        "filtro": filtro,
        "total_analisados": min(produtos_qs.count(), 500),
        "total_pendentes": total_pendentes,
        "total_prontos": min(produtos_qs.count(), 500) - total_pendentes,
    }
    return render(request, "fiscal/produtos_fiscais.html", context)


def _documento_com_dados(pk):
    return get_object_or_404(
        DocumentoFiscal.objects.select_related("filial__empresa", "venda__cliente", "venda__caixa", "pedido_online", "natureza_operacao", "usuario")
        .prefetch_related("venda__itens__produto", "venda__pagamentos__forma_pagamento"),
        pk=pk,
    )


@login_required
@role_required(*RELATORIOS)
def detalhe(request, pk):
    documento = _documento_com_dados(pk)
    return render(request, "fiscal/detalhe.html", {"documento": documento, "imprimir": False})


@login_required
@role_required(*RELATORIOS)
def imprimir(request, pk):
    documento = _documento_com_dados(pk)
    return render(request, "fiscal/detalhe.html", {"documento": documento, "imprimir": True})


@login_required
@role_required(*RELATORIOS)
def baixar_xml(request, pk):
    documento = _documento_com_dados(pk)
    if not documento.xml_conteudo:
        salvar_xml_documento(documento)
    nome = f"nfce_{documento.serie}_{documento.numero or documento.pk}.xml"
    response = HttpResponse(documento.xml_conteudo, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    return response


@login_required
@role_required(*SISTEMA)
def configuracao_form(request, pk=None):
    configuracao = get_object_or_404(ConfiguracaoFiscal, pk=pk) if pk else None
    if request.method == "POST":
        form = ConfiguracaoFiscalForm(request.POST, request.FILES, instance=configuracao)
        if form.is_valid():
            configuracao = form.save()
            arquivo = form.cleaned_data.get("certificado_arquivo")
            senha = form.cleaned_data.get("certificado_senha")
            if arquivo:
                try:
                    salvar_certificado_a1(configuracao, arquivo, senha)
                except ValidationError as exc:
                    form.add_error("certificado_arquivo", exc)
                    return render(request, "fiscal/form.html", {"form": form, "titulo": "Configuracao fiscal"})
            messages.success(request, "Configuracao fiscal salva.")
            return redirect("fiscal:documentos")
    else:
        form = ConfiguracaoFiscalForm(instance=configuracao)
    return render(request, "fiscal/form.html", {"form": form, "titulo": "Configuracao fiscal"})


@login_required
@role_required(*SISTEMA)
def serie_form(request, pk=None):
    serie = get_object_or_404(SerieFiscal, pk=pk) if pk else None
    if request.method == "POST":
        form = SerieFiscalForm(request.POST, instance=serie)
        if form.is_valid():
            form.save()
            messages.success(request, "Serie fiscal salva.")
            return redirect("fiscal:documentos")
    else:
        form = SerieFiscalForm(instance=serie)
    return render(request, "fiscal/form.html", {"form": form, "titulo": "Serie fiscal"})


@login_required
@role_required(*SISTEMA)
def natureza_form(request, pk=None):
    natureza = get_object_or_404(NaturezaOperacao, pk=pk) if pk else None
    if request.method == "POST":
        form = NaturezaOperacaoForm(request.POST, instance=natureza)
        if form.is_valid():
            form.save()
            messages.success(request, "Natureza de operacao salva.")
            return redirect("fiscal:documentos")
    else:
        form = NaturezaOperacaoForm(instance=natureza)
    return render(request, "fiscal/form.html", {"form": form, "titulo": "Natureza de operacao"})


@login_required
@role_required(*SISTEMA)
def preparar_venda(request, venda_id):
    venda = get_object_or_404(Venda, pk=venda_id)
    try:
        preparar_documento_venda(venda, request.user, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Documento fiscal preparado para transmissao.")
    return redirect("fiscal:documentos")


@login_required
@role_required(*SISTEMA)
def cancelar(request, pk):
    documento = get_object_or_404(DocumentoFiscal, pk=pk)
    if request.method == "POST":
        try:
            cancelar_documento(documento, request.user, request.POST.get("motivo", ""), ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Documento fiscal cancelado.")
    return redirect("fiscal:documentos")


@login_required
@role_required(*SISTEMA)
def transmitir_simulado(request, pk):
    documento = get_object_or_404(DocumentoFiscal, pk=pk)
    if request.method == "POST":
        try:
            transmitir_documento_simulado(documento, request.user, ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Documento fiscal transmitido em homologacao simulada.")
    return redirect("fiscal:detalhe", pk=pk)
