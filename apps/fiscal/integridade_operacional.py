from django.utils import timezone

from apps.auditoria.models import LogAuditoria


ACAO_INTEGRIDADE_OK = "INTEGRIDADE_EVIDENCIAS_OK"
ACAO_INTEGRIDADE_DIVERGENTE = "INTEGRIDADE_EVIDENCIAS_DIVERGENTE"
OBJETO_INTEGRIDADE_PREFIXO = "integridade_evidencias_fiscais"


def registrar_resultado_integridade(manifesto, *, origem):
    integra = bool(manifesto.get("integra"))
    acao = ACAO_INTEGRIDADE_OK if integra else ACAO_INTEGRIDADE_DIVERGENTE
    ancora = str(manifesto.get("ancora_global_sha256") or "")[:80]
    objeto_tipo = f"{OBJETO_INTEGRIDADE_PREFIXO}:{origem}"
    ultimo = (
        LogAuditoria.objects.filter(
            modulo="fiscal",
            acao__in=[ACAO_INTEGRIDADE_OK, ACAO_INTEGRIDADE_DIVERGENTE],
            objeto_tipo__startswith=OBJETO_INTEGRIDADE_PREFIXO,
        )
        .order_by("-criado_em", "-pk")
        .first()
    )
    if ultimo and ultimo.acao == acao and ultimo.objeto_id == ancora:
        return ultimo, False

    if integra:
        descricao = (
            "Verificação operacional concluída sem divergências: "
            f"{int(manifesto.get('total_documentos') or 0)} documento(s) e "
            f"{int(manifesto.get('total_evidencias') or 0)} evidência(s)."
        )
    else:
        descricao = (
            "Alerta operacional de integridade fiscal: "
            f"{int(manifesto.get('total_divergencias') or 0)} divergência(s) detectada(s). "
            "Revisão técnica do Master obrigatória."
        )
    return (
        LogAuditoria.objects.create(
            usuario=None,
            modulo="fiscal",
            acao=acao,
            descricao=descricao,
            objeto_tipo=objeto_tipo,
            objeto_id=ancora,
        ),
        True,
    )


def diagnostico_integridade_operacional():
    ultimo = (
        LogAuditoria.objects.filter(
            modulo="fiscal",
            acao__in=[ACAO_INTEGRIDADE_OK, ACAO_INTEGRIDADE_DIVERGENTE],
            objeto_tipo__startswith=OBJETO_INTEGRIDADE_PREFIXO,
        )
        .order_by("-criado_em", "-pk")
        .first()
    )
    if not ultimo:
        return {
            "status": "Pendente",
            "integra": None,
            "alerta": True,
            "verificado_em": None,
            "verificado_em_label": "Ainda não executado",
            "origem": "não registrada",
            "descricao": "A verificação operacional das evidências fiscais ainda não foi registrada.",
        }
    integra = ultimo.acao == ACAO_INTEGRIDADE_OK
    origem = ultimo.objeto_tipo.partition(":")[2] or "manual"
    verificado_em = timezone.localtime(ultimo.criado_em)
    return {
        "status": "Íntegra" if integra else "Divergente",
        "integra": integra,
        "alerta": not integra,
        "verificado_em": verificado_em.isoformat(),
        "verificado_em_label": verificado_em.strftime("%d/%m/%Y %H:%M"),
        "origem": origem,
        "descricao": ultimo.descricao,
    }
