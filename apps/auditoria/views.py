import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.permissions import SISTEMA, role_required

from .models import LogAuditoria


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


def _logs_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    modulo = request.GET.get("modulo", "").strip()
    acao = request.GET.get("acao", "").strip()
    usuario = request.GET.get("usuario", "").strip()
    q = request.GET.get("q", "").strip()

    logs = LogAuditoria.objects.select_related("usuario").filter(
        criado_em__date__gte=data_inicio,
        criado_em__date__lte=data_fim,
    )
    if modulo:
        logs = logs.filter(modulo=modulo)
    if acao:
        logs = logs.filter(acao=acao)
    if usuario:
        logs = logs.filter(usuario__username__icontains=usuario)
    if q:
        logs = logs.filter(
            Q(descricao__icontains=q)
            | Q(objeto_tipo__icontains=q)
            | Q(objeto_id__icontains=q)
            | Q(ip__icontains=q)
        )
    return logs, {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "modulo": modulo,
        "acao": acao,
        "usuario": usuario,
        "q": q,
    }


@login_required
@role_required(*SISTEMA)
def logs(request):
    logs_qs, filtros = _logs_filtrados(request)
    modulos = LogAuditoria.objects.order_by("modulo").values_list("modulo", flat=True).distinct()
    acoes = LogAuditoria.objects.order_by("acao").values_list("acao", flat=True).distinct()
    context = {
        **filtros,
        "logs": logs_qs[:300],
        "total_logs": logs_qs.count(),
        "modulos": modulos,
        "acoes": acoes,
        "csv_url": f"{reverse('auditoria:logs_csv')}?{request.GET.urlencode()}",
    }
    return render(request, "auditoria/logs.html", context)


@login_required
@role_required(*SISTEMA)
def logs_csv(request):
    logs_qs, filtros = _logs_filtrados(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="auditoria_{filtros["data_inicio"]}_{filtros["data_fim"]}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Modulo", "Acao", "Usuario", "Objeto", "ID", "IP", "Descricao"])
    for log in logs_qs.iterator():
        writer.writerow([
            timezone.localtime(log.criado_em).strftime("%d/%m/%Y %H:%M:%S"),
            log.modulo,
            log.acao,
            log.usuario.username if log.usuario else "",
            log.objeto_tipo,
            log.objeto_id,
            log.ip or "",
            log.descricao,
        ])
    return response
