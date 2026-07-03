import hmac
import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.permissions import SISTEMA, role_required

from .forms import EmpresaForm, FilialForm
from .models import Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, StatusEventoEntrada, StatusSincronizacao, VendaSincronizada


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


@login_required
@role_required(*SISTEMA)
def sincronizacao(request):
    eventos = EventoSincronizacao.objects.select_related("empresa", "filial").order_by("-criado_em")[:200]
    eventos_entrada = EventoEntradaSincronizacao.objects.select_related("empresa").order_by("-recebido_em")[:80]
    vendas_sincronizadas = VendaSincronizada.objects.select_related("empresa", "filial").order_by("-realizada_em", "-recebida_em")[:50]
    contagens = dict(EventoSincronizacao.objects.values_list("status").annotate(total=Count("id")))
    contagens_entrada = dict(EventoEntradaSincronizacao.objects.values_list("status").annotate(total=Count("id")))
    total_vendas_sync = VendaSincronizada.objects.aggregate(total=Sum("total_liquido"))["total"] or 0
    context = {
        "eventos": eventos,
        "eventos_entrada": eventos_entrada,
        "vendas_sincronizadas": vendas_sincronizadas,
        "pendentes": contagens.get(StatusSincronizacao.PENDENTE, 0),
        "processando": contagens.get(StatusSincronizacao.PROCESSANDO, 0),
        "enviados": contagens.get(StatusSincronizacao.ENVIADO, 0),
        "erros": contagens.get(StatusSincronizacao.ERRO, 0),
        "entrada_recebidos": contagens_entrada.get(StatusEventoEntrada.RECEBIDO, 0),
        "entrada_processados": contagens_entrada.get(StatusEventoEntrada.PROCESSADO, 0),
        "entrada_conflitos": contagens_entrada.get(StatusEventoEntrada.CONFLITO, 0),
        "entrada_erros": contagens_entrada.get(StatusEventoEntrada.ERRO, 0),
        "total_vendas_sincronizadas": VendaSincronizada.objects.count(),
        "valor_vendas_sincronizadas": total_vendas_sync,
    }
    return render(request, "empresas/sincronizacao.html", context)


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
