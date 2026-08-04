from urllib.parse import urlparse

from django.conf import settings

from .models import Empresa, Filial


def _url_https_valida(valor: str) -> bool:
    if not valor:
        return False
    analisada = urlparse(valor)
    return analisada.scheme.lower() == "https" and bool(analisada.netloc)


def diagnostico_prontidao_consulta_cadastro() -> dict:
    provider_cnpj = getattr(settings, "CADASTRO_CNPJ_PROVIDER_URL", "")
    provider_cep = getattr(settings, "CADASTRO_CEP_PROVIDER_URL", "")
    timeout = getattr(settings, "CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS", 5)
    cnpj_configurado = bool(provider_cnpj)
    cep_configurado = bool(provider_cep)
    cnpj_https = _url_https_valida(provider_cnpj)
    cep_https = _url_https_valida(provider_cep)
    alertas = []

    if not cnpj_configurado:
        alertas.append("CNPJ opera em validacao formal e fallback local ate configurar um provedor externo homologado.")
    elif not cnpj_https:
        alertas.append("O provedor de CNPJ deve usar uma URL HTTPS valida.")
    if not cep_configurado:
        alertas.append("CEP opera em fallback local/manual ate configurar um provedor externo homologado.")
    elif not cep_https:
        alertas.append("O provedor de CEP deve usar uma URL HTTPS valida.")

    provedores_configurados = int(cnpj_configurado) + int(cep_configurado)
    provedores_seguros = int(cnpj_https) + int(cep_https)
    pronto_homologacao = provedores_seguros == 2

    if pronto_homologacao:
        prontidao_status = "ready_for_provider_homologation"
        prontidao_resumo = "CNPJ e CEP possuem provedores HTTPS configurados e mantem fallback local."
        recomendacoes = [
            "Homologar disponibilidade, limites, formato das respostas e tratamento de falhas dos provedores configurados.",
        ]
    elif provedores_configurados:
        prontidao_status = "partially_configured"
        prontidao_resumo = "A configuracao externa esta parcial ou possui URL insegura; o fallback local permanece ativo."
        recomendacoes = [
            "Configurar URLs HTTPS validas para os dois provedores.",
            "Manter o fallback local para indisponibilidade do servico externo.",
        ]
    else:
        prontidao_status = "local_fallback_only"
        prontidao_resumo = "As consultas funcionam com validacao e dados locais, sem preenchimento publico externo."
        recomendacoes = [
            "Escolher provedores de producao para CNPJ e CEP.",
            "Homologar disponibilidade, limites, formato das respostas e tratamento de falhas.",
        ]

    return {
        "contrato": "cadastro_lookup_v1",
        "status": "ready_with_external_provider" if pronto_homologacao else "ready_with_local_fallback",
        "prontidao": {
            "contrato": "cadastro_lookup_readiness_v1",
            "status": prontidao_status,
            "provedores_configurados": provedores_configurados,
            "provedores_seguros": provedores_seguros,
            "provedores_necessarios": 2,
            "pronto_homologacao": pronto_homologacao,
            "fallback_local_disponivel": True,
            "resumo": prontidao_resumo,
            "recomendacoes": recomendacoes,
            "bloqueios": [] if pronto_homologacao else list(alertas),
        },
        "provedores": {
            "cnpj_configurado": cnpj_configurado,
            "cep_configurado": cep_configurado,
            "cnpj_https": cnpj_https,
            "cep_https": cep_https,
            "timeout_segundos": timeout,
            "modo_operacao": "externo_com_fallback_local" if cnpj_configurado or cep_configurado else "local_offline",
        },
        "fallback_local": True,
        "consultas": {
            "cnpj": {
                "validacao": "calculo_digitos_verificadores",
                "mascara": "00.000.000/0000-00",
                "provedor_configurado": cnpj_configurado,
            },
            "cep": {
                "validacao": "8_digitos",
                "mascara": "00000-000",
                "provedor_configurado": cep_configurado,
            },
        },
        "base_local": {
            "empresas_com_cnpj": Empresa.objects.exclude(cnpj="").count(),
            "filiais_com_cnpj": Filial.objects.exclude(cnpj="").count(),
            "empresas_com_endereco": Empresa.objects.exclude(endereco="").count(),
            "filiais_com_endereco": Filial.objects.exclude(endereco="").count(),
        },
        "alertas": alertas,
    }
