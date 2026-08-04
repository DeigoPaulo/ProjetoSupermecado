import hmac

from django.conf import settings


def normalizar_cnpj(valor):
    return "".join(filter(str.isdigit, str(valor or "")))


def _tokens_configurados(valor):
    if isinstance(valor, str):
        candidatos = [valor]
    elif isinstance(valor, dict):
        atual = valor.get("atual") or valor.get("current") or ""
        anteriores = valor.get(
            "anteriores",
            valor.get("previous", valor.get("anterior", [])),
        )
        if not isinstance(atual, str) or not atual.strip():
            return ()
        if isinstance(anteriores, str):
            anteriores = [anteriores]
        elif not isinstance(anteriores, (list, tuple)):
            anteriores = []
        candidatos = [atual, *anteriores[:3]]
    else:
        candidatos = []

    tokens = []
    for candidato in candidatos:
        if not isinstance(candidato, str):
            continue
        token = candidato.strip()
        if token and token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def credenciais_sincronizacao_para_cnpj(cnpj):
    alvo = normalizar_cnpj(cnpj)
    if alvo:
        for chave, configuracao in settings.SINCRONIZACAO_TOKENS_EMPRESA.items():
            if normalizar_cnpj(chave) == alvo:
                tokens = _tokens_configurados(configuracao)
                return (tokens, "empresa") if tokens else ((), "ausente")

    token_global = str(settings.SINCRONIZACAO_API_TOKEN or "").strip()
    if settings.SINCRONIZACAO_PERMITE_TOKEN_GLOBAL and token_global:
        return (token_global,), "global_transicao"
    return (), "ausente"


def token_sincronizacao_para_cnpj(cnpj):
    tokens, origem = credenciais_sincronizacao_para_cnpj(cnpj)
    return (tokens[0] if tokens else ""), origem


def credencial_sincronizacao_valida(cnpj, token_recebido):
    tokens, origem = credenciais_sincronizacao_para_cnpj(cnpj)
    recebido = str(token_recebido or "")
    valido = False
    for token in tokens:
        valido = hmac.compare_digest(recebido, token) or valido
    return valido, origem
