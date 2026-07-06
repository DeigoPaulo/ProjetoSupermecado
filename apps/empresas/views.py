import csv
import hmac
import json
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.permissions import SISTEMA, role_required

from .forms import EmpresaForm, FilialForm
from .models import DocumentoFiscalSincronizado, Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, StatusEventoEntrada, StatusSincronizacao, VendaSincronizada


def _erro_api(mensagem, status):
    return JsonResponse({"status": "erro", "mensagem": mensagem}, status=status)


@csrf_exempt
@require_POST
def receber_evento_sincronizacao(request):
    token_configurado = settings.SINCRONIZACAO_API_TOKEN
    token_recebido = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token_configurado or not hmac.compare_digest(token_recebido, token_configurado):
        return _erro_api("Credencial de sincronizacao invalida.", 401)
    try:
        dados = json.loads(request.body)
        identificador = uuid.UUID(str(dados["id"]))
        tipo = str(dados["tipo"]).strip()
        empresa_cnpj = str(dados["empresa_cnpj"]).strip()
        payload = dados["payload"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _erro_api("Evento de sincronizacao malformado.", 400)
    chave = request.headers.get("Idempotency-Key", "").strip()
    if not chave or len(chave) > 180 or not tipo or not isinstance(payload, dict):
        return _erro_api("Tipo, payload e chave idempotente sao obrigatorios.", 400)
    empresa = Empresa.objects.filter(cnpj=empresa_cnpj, is_active=True).first()
    if not empresa:
        return _erro_api("Empresa do evento nao encontrada ou inativa.", 422)

    existente = EventoEntradaSincronizacao.objects.filter(identificador=identificador).first()
    if not existente:
        existente = EventoEntradaSincronizacao.objects.filter(chave_idempotencia=chave).first()
    if existente:
        if existente.identificador == identificador and existente.chave_idempotencia == chave:
            return JsonResponse({"status": "duplicado", "id": str(existente.identificador)}, status=200)
        return _erro_api("Conflito entre identificador e chave idempotente.", 409)
    try:
        with transaction.atomic():
            evento = EventoEntradaSincronizacao.objects.create(
                identificador=identificador,
                chave_idempotencia=chave,
                empresa=empresa,
                tipo=tipo,
                payload=dados,
            )
    except IntegrityError:
        return JsonResponse({"status": "duplicado", "id": str(identificador)}, status=200)
    return JsonResponse({"status": "recebido", "id": str(evento.identificador)}, status=202)


@login_required
@role_required(*SISTEMA)
def empresas(request):
    empresas_lista = Empresa.objects.prefetch_related("filiais").order_by("nome_fantasia")
    filiais = Filial.objects.select_related("empresa").order_by("empresa__nome_fantasia", "nome")
    context = {
        "empresas": empresas_lista,
        "filiais": filiais,
        "total_empresas": empresas_lista.count(),
        "total_filiais": filiais.count(),
        "filiais_ativas": filiais.filter(is_active=True).count(),
        "filiais_sem_ibge": filiais.filter(codigo_municipio_ibge="").count(),
    }
    return render(request, "empresas/lista.html", context)


@login_required
@role_required(*SISTEMA)
def empresa_form(request, pk=None):
    empresa = get_object_or_404(Empresa, pk=pk) if pk else None
    form = EmpresaForm(request.POST or None, request.FILES or None, instance=empresa)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Empresa salva com sucesso.")
        return redirect("empresas:lista")
    return render(request, "empresas/empresa_form.html", {"form": form, "empresa": empresa})


@login_required
@role_required(*SISTEMA)
def filial_form(request, pk=None):
    filial = get_object_or_404(Filial, pk=pk) if pk else None
    form = FilialForm(request.POST or None, instance=filial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Filial salva com sucesso.")
        return redirect("empresas:lista")
    return render(request, "empresas/filial_form.html", {"form": form, "filial": filial})


@login_required
@role_required(*SISTEMA)
def consulta_cadastro_placeholder(request):
    return JsonResponse(
        {
            "status": "integration_pending",
            "mensagem": "Consulta automatica de CNPJ/CEP sera conectada a uma API externa em etapa futura.",
            "campos_previstos": [
                "cnpj",
                "razao_social",
                "nome_fantasia",
                "telefone",
                "email",
                "endereco",
                "municipio",
                "uf",
                "codigo_municipio_ibge",
            ],
        }
    )


def _sincronizacao_querysets(request):
    q = request.GET.get("q", "").strip()
    empresa_id = request.GET.get("empresa", "").strip()
    filial_id = request.GET.get("filial", "").strip()
    status_entrada = request.GET.get("status_entrada", "").strip()

    eventos_qs = EventoSincronizacao.objects.select_related("empresa", "filial")
    eventos_entrada_qs = EventoEntradaSincronizacao.objects.select_related("empresa")
    vendas_qs = VendaSincronizada.objects.select_related("empresa", "filial")
    documentos_fiscais_qs = DocumentoFiscalSincronizado.objects.select_related("empresa", "filial")

    if empresa_id.isdigit():
        eventos_qs = eventos_qs.filter(empresa_id=empresa_id)
        eventos_entrada_qs = eventos_entrada_qs.filter(empresa_id=empresa_id)
        vendas_qs = vendas_qs.filter(empresa_id=empresa_id)
        documentos_fiscais_qs = documentos_fiscais_qs.filter(empresa_id=empresa_id)
    if filial_id.isdigit():
        eventos_qs = eventos_qs.filter(filial_id=filial_id)
        vendas_qs = vendas_qs.filter(filial_id=filial_id)
        documentos_fiscais_qs = documentos_fiscais_qs.filter(filial_id=filial_id)
    if status_entrada:
        eventos_entrada_qs = eventos_entrada_qs.filter(status=status_entrada)
    if q:
        eventos_qs = eventos_qs.filter(
            Q(tipo__icontains=q)
            | Q(identificador__icontains=q)
            | Q(objeto_tipo__icontains=q)
            | Q(objeto_id__icontains=q)
            | Q(chave_idempotencia__icontains=q)
            | Q(ultimo_erro__icontains=q)
        )
        eventos_entrada_qs = eventos_entrada_qs.filter(
            Q(tipo__icontains=q)
            | Q(identificador__icontains=q)
            | Q(chave_idempotencia__icontains=q)
            | Q(ultimo_erro__icontains=q)
            | Q(resolucao_conflito__icontains=q)
        )
        vendas_qs = vendas_qs.filter(
            Q(venda_externa_id__icontains=q)
            | Q(caixa_externo__icontains=q)
            | Q(operador__icontains=q)
            | Q(cliente__icontains=q)
        )
        documentos_fiscais_qs = documentos_fiscais_qs.filter(
            Q(documento_externo_id__icontains=q)
            | Q(venda_externa_id__icontains=q)
            | Q(chave_acesso__icontains=q)
            | Q(protocolo__icontains=q)
            | Q(status__icontains=q)
        )
    return {
        "eventos_qs": eventos_qs,
        "eventos_entrada_qs": eventos_entrada_qs,
        "vendas_qs": vendas_qs,
        "documentos_fiscais_qs": documentos_fiscais_qs,
        "filtros": {"q": q, "empresa": empresa_id, "filial": filial_id, "status_entrada": status_entrada},
    }


@login_required
@role_required(*SISTEMA)
def sincronizacao(request):
    dados = _sincronizacao_querysets(request)
    eventos_qs = dados["eventos_qs"]
    eventos_entrada_qs = dados["eventos_entrada_qs"]
    vendas_qs = dados["vendas_qs"]
    documentos_fiscais_qs = dados["documentos_fiscais_qs"]
    eventos = eventos_qs.order_by("-criado_em")[:200]
    eventos_entrada = eventos_entrada_qs.order_by("-recebido_em")[:80]
    vendas_sincronizadas = vendas_qs.order_by("-realizada_em", "-recebida_em")[:50]
    documentos_fiscais = documentos_fiscais_qs.order_by("-emitido_em", "-recebido_em")[:50]
    contagens = dict(eventos_qs.values_list("status").annotate(total=Count("id")))
    contagens_entrada = dict(eventos_entrada_qs.values_list("status").annotate(total=Count("id")))
    total_vendas_sync = vendas_qs.aggregate(total=Sum("total_liquido"))["total"] or 0
    base_dir = Path(settings.BASE_DIR)
    python_exe = base_dir / ".venv" / "Scripts" / "python.exe"
    comando_sincronizacao = f'"{python_exe}" manage.py processar_sincronizacao_completa --limite-saida 50 --limite-entrada 50'
    comando_agendador = (
        'schtasks /Create /TN "Supermercado Sincronizacao" /SC MINUTE /MO 1 '
        f'/TR "cmd /c cd /d {base_dir} && {comando_sincronizacao}" /F'
    )
    context = {
        "eventos": eventos,
        "eventos_entrada": eventos_entrada,
        "vendas_sincronizadas": vendas_sincronizadas,
        "documentos_fiscais_sincronizados": documentos_fiscais,
        "empresas_opcoes": Empresa.objects.filter(is_active=True).order_by("nome_fantasia"),
        "filiais_opcoes": Filial.objects.filter(is_active=True).select_related("empresa").order_by("empresa__nome_fantasia", "nome"),
        "status_entrada_opcoes": StatusEventoEntrada.choices,
        "filtros": dados["filtros"],
        "pendentes": contagens.get(StatusSincronizacao.PENDENTE, 0),
        "processando": contagens.get(StatusSincronizacao.PROCESSANDO, 0),
        "enviados": contagens.get(StatusSincronizacao.ENVIADO, 0),
        "erros": contagens.get(StatusSincronizacao.ERRO, 0),
        "entrada_recebidos": contagens_entrada.get(StatusEventoEntrada.RECEBIDO, 0),
        "entrada_processados": contagens_entrada.get(StatusEventoEntrada.PROCESSADO, 0),
        "entrada_conflitos": contagens_entrada.get(StatusEventoEntrada.CONFLITO, 0),
        "entrada_erros": contagens_entrada.get(StatusEventoEntrada.ERRO, 0),
        "entrada_resolvidos": contagens_entrada.get(StatusEventoEntrada.RESOLVIDO, 0),
        "total_vendas_sincronizadas": vendas_qs.count(),
        "valor_vendas_sincronizadas": total_vendas_sync,
        "total_documentos_fiscais_sincronizados": documentos_fiscais_qs.count(),
        "comando_sincronizacao": comando_sincronizacao,
        "comando_agendador": comando_agendador,
    }
    return render(request, "empresas/sincronizacao.html", context)


@login_required
@role_required(*SISTEMA)
def vendas_sincronizadas_csv(request):
    vendas_qs = _sincronizacao_querysets(request)["vendas_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="vendas_sincronizadas.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Venda externa", "Empresa", "Filial", "Caixa", "Operador", "Cliente", "Total bruto", "Desconto", "Total liquido", "Pagamentos", "Realizada", "Recebida"])
    for venda in vendas_qs.order_by("-realizada_em", "-recebida_em"):
        writer.writerow([
            venda.venda_externa_id,
            venda.empresa.nome_fantasia,
            venda.filial.nome if venda.filial else "",
            venda.caixa_externo,
            venda.operador,
            venda.cliente,
            str(venda.total_bruto).replace(".", ","),
            str(venda.desconto).replace(".", ","),
            str(venda.total_liquido).replace(".", ","),
            len(venda.pagamentos),
            venda.realizada_em.strftime("%d/%m/%Y %H:%M:%S") if venda.realizada_em else "",
            venda.recebida_em.strftime("%d/%m/%Y %H:%M:%S") if venda.recebida_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def documentos_fiscais_sincronizados_csv(request):
    documentos_qs = _sincronizacao_querysets(request)["documentos_fiscais_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="documentos_fiscais_sincronizados.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Documento externo",
        "Venda externa",
        "Empresa",
        "Filial",
        "Tipo",
        "Ambiente",
        "Serie",
        "Numero",
        "Status",
        "Valor total",
        "Chave de acesso",
        "Protocolo",
        "Emitido em",
        "Recebido em",
    ])
    for documento in documentos_qs.order_by("-emitido_em", "-recebido_em"):
        writer.writerow([
            documento.documento_externo_id,
            documento.venda_externa_id,
            documento.empresa.nome_fantasia,
            documento.filial.nome if documento.filial else "",
            documento.tipo_documento,
            documento.ambiente,
            documento.serie,
            documento.numero,
            documento.status,
            str(documento.valor_total).replace(".", ","),
            documento.chave_acesso,
            documento.protocolo,
            documento.emitido_em.strftime("%d/%m/%Y %H:%M:%S") if documento.emitido_em else "",
            documento.recebido_em.strftime("%d/%m/%Y %H:%M:%S") if documento.recebido_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def eventos_sincronizacao_csv(request):
    eventos_qs = _sincronizacao_querysets(request)["eventos_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="eventos_sincronizacao_saida.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Identificador", "Tipo", "Empresa", "Filial", "Objeto", "Chave idempotente", "Status", "Tentativas", "Ultimo erro", "Criado em", "Processado em"])
    for evento in eventos_qs.order_by("-criado_em"):
        writer.writerow([
            evento.identificador,
            evento.tipo,
            evento.empresa.nome_fantasia,
            evento.filial.nome if evento.filial else "",
            f"{evento.objeto_tipo} #{evento.objeto_id}",
            evento.chave_idempotencia,
            evento.get_status_display(),
            evento.tentativas,
            evento.ultimo_erro,
            evento.criado_em.strftime("%d/%m/%Y %H:%M:%S"),
            evento.processado_em.strftime("%d/%m/%Y %H:%M:%S") if evento.processado_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def eventos_entrada_sincronizacao_csv(request):
    eventos_qs = _sincronizacao_querysets(request)["eventos_entrada_qs"].select_related("empresa", "resolvido_por")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="eventos_sincronizacao_entrada.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Identificador", "Tipo", "Empresa", "Chave idempotente", "Status", "Ultimo erro", "Resolucao", "Resolvido por", "Recebido em", "Processado em", "Resolvido em"])
    for evento in eventos_qs.order_by("-recebido_em"):
        writer.writerow([
            evento.identificador,
            evento.tipo,
            evento.empresa.nome_fantasia,
            evento.chave_idempotencia,
            evento.get_status_display(),
            evento.ultimo_erro,
            evento.resolucao_conflito,
            evento.resolvido_por.get_username() if evento.resolvido_por else "",
            evento.recebido_em.strftime("%d/%m/%Y %H:%M:%S"),
            evento.processado_em.strftime("%d/%m/%Y %H:%M:%S") if evento.processado_em else "",
            evento.resolvido_em.strftime("%d/%m/%Y %H:%M:%S") if evento.resolvido_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def venda_sincronizada_detalhe(request, pk):
    venda = get_object_or_404(
        VendaSincronizada.objects.select_related("empresa", "filial", "evento"),
        pk=pk,
    )
    itens = [
        {
            "produto": item.get("nome") or item.get("produto") or "Produto sincronizado",
            "codigo_barras": item.get("codigo_barras") or "-",
            "quantidade": item.get("quantidade") or "-",
            "preco_unitario": item.get("preco_unitario") or "0,00",
            "total": item.get("total") or "0,00",
        }
        for item in venda.itens
        if isinstance(item, dict)
    ]
    pagamentos = [
        {
            "tipo": pagamento.get("tipo") or "-",
            "valor": pagamento.get("valor") or "0,00",
            "status": pagamento.get("status") or "Confirmado",
        }
        for pagamento in venda.pagamentos
        if isinstance(pagamento, dict)
    ]
    return render(
        request,
        "empresas/venda_sincronizada_detalhe.html",
        {"venda": venda, "itens": itens, "pagamentos": pagamentos},
    )


@login_required
@role_required(*SISTEMA)
def documento_fiscal_sincronizado_detalhe(request, pk):
    documento = get_object_or_404(
        DocumentoFiscalSincronizado.objects.select_related("empresa", "filial", "evento"),
        pk=pk,
    )
    payload_formatado = json.dumps(documento.payload, ensure_ascii=False, indent=2)
    return render(
        request,
        "empresas/documento_fiscal_sincronizado_detalhe.html",
        {"documento": documento, "payload_formatado": payload_formatado},
    )


@login_required
@role_required(*SISTEMA)
def evento_sincronizacao_detalhe(request, pk):
    evento = get_object_or_404(
        EventoSincronizacao.objects.select_related("empresa", "filial"),
        pk=pk,
    )
    payload_formatado = json.dumps(evento.payload, ensure_ascii=False, indent=2)
    return render(
        request,
        "empresas/evento_sincronizacao_detalhe.html",
        {"evento": evento, "payload_formatado": payload_formatado},
    )


@login_required
@role_required(*SISTEMA)
def evento_entrada_sincronizacao_detalhe(request, pk):
    evento = get_object_or_404(
        EventoEntradaSincronizacao.objects.select_related("empresa"),
        pk=pk,
    )
    payload_formatado = json.dumps(evento.payload, ensure_ascii=False, indent=2)
    return render(
        request,
        "empresas/evento_entrada_sincronizacao_detalhe.html",
        {"evento": evento, "payload_formatado": payload_formatado},
    )


@login_required
@role_required(*SISTEMA)
def sincronizacao_entrada_resolver_conflito(request, pk):
    if request.method == "POST":
        evento = get_object_or_404(EventoEntradaSincronizacao, pk=pk)
        resolucao = request.POST.get("resolucao_conflito", "").strip()
        if evento.status != StatusEventoEntrada.CONFLITO:
            messages.warning(request, "Apenas eventos em conflito podem ser resolvidos manualmente.")
        elif not resolucao:
            messages.warning(request, "Informe a decisao tomada para resolver o conflito.")
            return redirect("empresas:evento_entrada_sincronizacao_detalhe", pk=evento.pk)
        else:
            evento.status = StatusEventoEntrada.RESOLVIDO
            evento.resolucao_conflito = resolucao
            evento.resolvido_por = request.user
            evento.resolvido_em = timezone.now()
            evento.save(update_fields=["status", "resolucao_conflito", "resolvido_por", "resolvido_em", "atualizado_em"])
            messages.success(request, "Conflito marcado como resolvido manualmente.")
    return redirect("empresas:evento_entrada_sincronizacao_detalhe", pk=pk)


@login_required
@role_required(*SISTEMA)
def sincronizacao_reprocessar(request, pk):
    if request.method == "POST":
        evento = get_object_or_404(EventoSincronizacao, pk=pk)
        evento.status = StatusSincronizacao.PENDENTE
        evento.tentativas = 0
        evento.proxima_tentativa_em = None
        evento.ultimo_erro = ""
        evento.save(update_fields=["status", "tentativas", "proxima_tentativa_em", "ultimo_erro", "atualizado_em"])
        messages.success(request, "Evento devolvido para a fila de sincronizacao.")
    return redirect("empresas:sincronizacao")


@login_required
@role_required(*SISTEMA)
def sincronizacao_entrada_reprocessar(request, pk):
    if request.method == "POST":
        evento = get_object_or_404(EventoEntradaSincronizacao, pk=pk)
        if evento.status in {StatusEventoEntrada.ERRO, StatusEventoEntrada.CONFLITO}:
            evento.status = StatusEventoEntrada.RECEBIDO
            evento.ultimo_erro = ""
            evento.processado_em = None
            evento.save(update_fields=["status", "ultimo_erro", "processado_em", "atualizado_em"])
            messages.success(request, "Evento de entrada devolvido para processamento.")
        else:
            messages.warning(request, "Apenas eventos de entrada com erro ou conflito podem ser reprocessados.")
    return redirect("empresas:sincronizacao")
