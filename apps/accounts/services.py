from django.conf import settings


def diagnostico_prontidao_recuperacao_senha() -> dict:
    backend = getattr(settings, "EMAIL_BACKEND", "")
    smtp_backend = backend.endswith("smtp.EmailBackend")
    console_backend = backend.endswith("console.EmailBackend")
    locmem_backend = backend.endswith("locmem.EmailBackend")
    host_configurado = bool(getattr(settings, "EMAIL_HOST", ""))
    usuario_configurado = bool(getattr(settings, "EMAIL_HOST_USER", ""))
    senha_configurada = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))
    remetente = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    remetente_configurado = bool(remetente and "@" in remetente)
    tls = bool(getattr(settings, "EMAIL_USE_TLS", False))
    ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))
    timeout = getattr(settings, "EMAIL_TIMEOUT", None)
    porta = getattr(settings, "EMAIL_PORT", None)
    alertas = []

    if console_backend or locmem_backend:
        alertas.append("Backend de desenvolvimento ativo; os e-mails nao saem para usuarios reais.")
    if smtp_backend and not host_configurado:
        alertas.append("SMTP sem host configurado.")
    if smtp_backend and not remetente_configurado:
        alertas.append("Remetente padrao invalido ou ausente.")
    if smtp_backend and not usuario_configurado:
        alertas.append("Usuario SMTP nao configurado; confirme se o provedor aceita envio sem autenticacao.")
    if smtp_backend and usuario_configurado and not senha_configurada:
        alertas.append("Senha SMTP ausente para o usuario configurado.")
    if tls and ssl:
        alertas.append("TLS e SSL estao ativos ao mesmo tempo; escolha apenas uma opcao conforme o provedor.")

    pronto_configuracao = smtp_backend and host_configurado and remetente_configurado and not (tls and ssl)
    if usuario_configurado:
        pronto_configuracao = pronto_configuracao and senha_configurada

    if console_backend or locmem_backend:
        prontidao_status = "development_only"
        prontidao_percentual = 55
        bloqueios = ["Ative um backend SMTP para enviar mensagens a usuarios reais."]
    elif not smtp_backend:
        prontidao_status = "unsupported_backend"
        prontidao_percentual = 35
        bloqueios = ["Configure um backend SMTP suportado para a recuperacao de senha."]
    elif not pronto_configuracao:
        prontidao_status = "configuration_required"
        prontidao_percentual = 70
        bloqueios = list(alertas)
    else:
        prontidao_status = "ready_for_homologation"
        prontidao_percentual = 90
        bloqueios = []

    recomendacoes = []
    if pronto_configuracao:
        recomendacoes = [
            "Executar envio real de recuperacao para uma caixa de teste.",
            "Validar SPF, DKIM, DMARC, remetente e entrega sem cair em spam.",
        ]

    return {
        "contrato": "password_reset_email_v1",
        "status": "ready_for_production" if pronto_configuracao else "needs_configuration",
        "prontidao": {
            "contrato": "password_reset_readiness_v1",
            "status": prontidao_status,
            "percentual": prontidao_percentual,
            "configuracao_smtp_completa": pronto_configuracao,
            "homologacao_real_pendente": pronto_configuracao,
            "bloqueios": bloqueios,
            "recomendacoes": recomendacoes,
        },
        "backend": {
            "smtp": smtp_backend,
            "console": console_backend,
            "memoria_teste": locmem_backend,
        },
        "smtp": {
            "host_configurado": host_configurado,
            "porta": porta,
            "usuario_configurado": usuario_configurado,
            "senha_configurada": senha_configurada,
            "tls": tls,
            "ssl": ssl,
            "timeout_segundos": timeout,
        },
        "remetente_configurado": remetente_configurado,
        "seguranca": {
            "resposta_publica_neutra": True,
            "token_temporario_uso_unico": True,
            "nao_expoe_credenciais": True,
        },
        "alertas": alertas,
    }
