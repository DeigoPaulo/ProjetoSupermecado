import csv

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.models import TipoPerfil
from apps.accounts.permissions import role_required

from .models import LogAuditoria


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


def _logs_permitidos(user):
    logs = LogAuditoria.objects.select_related(
        "usuario", "usuario__perfil_supermercado", "usuario__perfil_supermercado__filial"
    )
    if user.is_superuser:
        return logs
    perfil = getattr(user, "perfil_supermercado", None)
    if not perfil or not perfil.is_active or not perfil.filial_id:
        return logs.none()
    return logs.filter(
        usuario__is_superuser=False,
        usuario__perfil_supermercado__is_active=True,
        usuario__perfil_supermercado__filial__empresa_id=perfil.filial.empresa_id,
    )


def _logs_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    modulo = request.GET.get("modulo", "").strip()
    acao = request.GET.get("acao", "").strip()
    usuario = request.GET.get("usuario", "").strip()
    q = request.GET.get("q", "").strip()

    logs = _logs_permitidos(request.user).filter(
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
@role_required(TipoPerfil.ADMINISTRADOR)
def logs(request):
    logs_qs, filtros = _logs_filtrados(request)
    logs_permitidos = _logs_permitidos(request.user)
    pagina = Paginator(logs_qs, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    context = {
        **filtros,
        "logs": pagina,
        "pagina": pagina,
        "total_logs": pagina.paginator.count,
        "modulos": logs_permitidos.order_by("modulo").values_list("modulo", flat=True).distinct(),
        "acoes": logs_permitidos.order_by("acao").values_list("acao", flat=True).distinct(),
        "query_sem_pagina": query.urlencode(),
        "csv_url": f"{reverse('auditoria:logs_csv')}?{query.urlencode()}",
    }
    return render(request, "auditoria/logs.html", context)


@login_required
@role_required(TipoPerfil.ADMINISTRADOR)
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
