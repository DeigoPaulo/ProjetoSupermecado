from django.conf import settings
from django.utils import timezone

from apps.auditoria.models import LogAuditoria


ACAO_BACKUP_SUCESSO = "BACKUP_OPERACIONAL_SUCESSO"
ACAO_BACKUP_FALHA = "BACKUP_OPERACIONAL_FALHA"
ACOES_BACKUP = [ACAO_BACKUP_SUCESSO, ACAO_BACKUP_FALHA]
OBJETO_BACKUP_PREFIXO = "backup_operacional_v1"

ETAPAS = {
    "preparacao": "preparação",
    "integridade_fiscal": "integridade fiscal",
    "geracao": "geração do pacote",
    "criptografia": "criptografia",
    "copia_secundaria": "cópia secundária",
    "retencao": "retenção",
    "concluido": "conclusão",
}
CODIGOS_FALHA = {
    "erro_operacional": "Falha operacional durante o backup.",
    "integridade_fiscal": "A verificação da integridade fiscal bloqueou o backup.",
    "geracao_pacote": "O pacote de backup não pôde ser concluído.",
    "criptografia": "O pacote não pôde ser criptografado.",
    "copia_secundaria": "A cópia secundária não pôde ser validada.",
    "retencao": "A política de retenção não pôde ser concluída.",
}


def registrar_resultado_backup(
    *,
    execucao_id,
    status,
    etapa,
    criptografado=False,
    copia_secundaria=False,
    hash_validado=False,
    codigo_falha="erro_operacional",
):
    execucao_id = str(execucao_id or "").strip()
    if not execucao_id:
        raise ValueError("Identificador da execução é obrigatório.")
    acao = ACAO_BACKUP_SUCESSO if status == "sucesso" else ACAO_BACKUP_FALHA
    existente = LogAuditoria.objects.filter(
        modulo="backup",
        acao__in=ACOES_BACKUP,
        objeto_id=execucao_id,
    ).first()
    if existente:
        return existente, False

    etapa_label = ETAPAS.get(etapa, ETAPAS["preparacao"])
    destino_label = "principal e secundário" if copia_secundaria else "principal"
    protecao_label = "criptografado" if criptografado else "não criptografado"
    hash_label = "validado" if hash_validado else "não confirmado"
    if status == "sucesso":
        descricao = (
            f"Backup concluído; destino {destino_label}; pacote {protecao_label}; "
            f"SHA-256 {hash_label}."
        )
    else:
        descricao = (
            f"Backup não concluído na etapa de {etapa_label}. "
            f"{CODIGOS_FALHA.get(codigo_falha, CODIGOS_FALHA['erro_operacional'])}"
        )
    objeto_tipo = ":".join(
        [
            OBJETO_BACKUP_PREFIXO,
            "criptografado" if criptografado else "aberto",
            "secundario" if copia_secundaria else "principal",
            "hash_ok" if hash_validado else "hash_pendente",
            etapa,
        ]
    )
    return (
        LogAuditoria.objects.create(
            usuario=None,
            modulo="backup",
            acao=acao,
            descricao=descricao,
            objeto_tipo=objeto_tipo[:120],
            objeto_id=execucao_id[:80],
        ),
        True,
    )


def historico_backup_operacional(*, limite=20):
    logs = LogAuditoria.objects.filter(
        modulo="backup",
        acao__in=ACOES_BACKUP,
        objeto_tipo__startswith=OBJETO_BACKUP_PREFIXO,
    ).order_by("-criado_em", "-pk")[:limite]
    resultado = []
    for log in logs:
        partes = (log.objeto_tipo or "").split(":")
        momento = timezone.localtime(log.criado_em)
        resultado.append(
            {
                "execucao_id": log.objeto_id,
                "status": "Sucesso" if log.acao == ACAO_BACKUP_SUCESSO else "Falha",
                "sucesso": log.acao == ACAO_BACKUP_SUCESSO,
                "criptografado": len(partes) > 1 and partes[1] == "criptografado",
                "copia_secundaria": len(partes) > 2 and partes[2] == "secundario",
                "hash_validado": len(partes) > 3 and partes[3] == "hash_ok",
                "etapa": ETAPAS.get(partes[4] if len(partes) > 4 else "preparacao", "preparação"),
                "descricao": log.descricao,
                "criado_em": momento.isoformat(),
                "criado_em_label": momento.strftime("%d/%m/%Y %H:%M"),
            }
        )
    return resultado

def politica_periodicidade_backup(*, idade_maxima_horas=None):
    origem = "argumento" if idade_maxima_horas is not None else "ambiente"
    if idade_maxima_horas is None:
        idade_maxima_horas = getattr(settings, "LOCAL_BACKUP_MAX_AGE_HOURS", 0)
    idade_maxima_horas = max(0, int(idade_maxima_horas or 0))
    return {
        "contrato": "backup_age_policy_v1",
        "configuracao": "LOCAL_BACKUP_MAX_AGE_HOURS",
        "origem": origem,
        "configurada": idade_maxima_horas > 0,
        "idade_maxima_horas": idade_maxima_horas,
    }


def diagnostico_periodicidade_backup(*, agora=None, idade_maxima_horas=None):
    politica = politica_periodicidade_backup(idade_maxima_horas=idade_maxima_horas)
    idade_maxima_horas = politica["idade_maxima_horas"]
    ultimo_sucesso = LogAuditoria.objects.filter(
        modulo="backup",
        acao=ACAO_BACKUP_SUCESSO,
        objeto_tipo__startswith=OBJETO_BACKUP_PREFIXO,
    ).order_by("-criado_em", "-pk").first()
    resultado = {
        "contrato": "backup_freshness_v1",
        "politica_contrato": politica["contrato"],
        "politica_origem": politica["origem"],
        "configuracao": "LOCAL_BACKUP_MAX_AGE_HOURS",
        "configurado": idade_maxima_horas > 0,
        "idade_maxima_horas": idade_maxima_horas,
        "status": "Desativado",
        "alerta": False,
        "ultimo_sucesso_em": None,
        "ultimo_sucesso_em_label": "—",
        "idade_horas": None,
        "descricao": "Monitoramento de periodicidade não configurado.",
    }
    if not idade_maxima_horas:
        return resultado
    if not ultimo_sucesso:
        resultado.update(
            status="Sem sucesso",
            alerta=True,
            descricao=(
                "Nenhum backup bem-sucedido foi registrado dentro da política "
                f"de {idade_maxima_horas} hora(s)."
            ),
        )
        return resultado

    agora = agora or timezone.now()
    idade_segundos = max(0, (agora - ultimo_sucesso.criado_em).total_seconds())
    idade_horas = round(idade_segundos / 3600, 1)
    momento = timezone.localtime(ultimo_sucesso.criado_em)
    atrasado = idade_segundos > idade_maxima_horas * 3600
    resultado.update(
        status="Atrasado" if atrasado else "Em dia",
        alerta=atrasado,
        ultimo_sucesso_em=momento.isoformat(),
        ultimo_sucesso_em_label=momento.strftime("%d/%m/%Y %H:%M"),
        idade_horas=idade_horas,
        descricao=(
            f"Último backup bem-sucedido há {idade_horas:g} hora(s); "
            f"limite configurado de {idade_maxima_horas} hora(s)."
        ),
    )
    return resultado
