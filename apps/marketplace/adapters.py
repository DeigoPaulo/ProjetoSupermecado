from copy import deepcopy

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class MarketplaceAdapterError(Exception):
    pass


def _registro_adaptadores():
    registro = getattr(settings, "MARKETPLACE_PARTNER_ADAPTERS", {})
    return {str(chave).upper().strip(): str(valor).strip() for chave, valor in registro.items() if valor}


def carregar_adaptador_marketplace(provedor):
    codigo = str(provedor or "").upper().strip()
    caminho = _registro_adaptadores().get(codigo, "")
    if not caminho:
        raise ImproperlyConfigured(f"Nenhum adaptador foi configurado para o provedor {codigo}.")
    try:
        adapter_class = import_string(caminho)
        adapter = adapter_class()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ImproperlyConfigured(f"Nao foi possivel carregar o adaptador do provedor {codigo}.") from exc
    if not callable(getattr(adapter, "normalizar_pedido", None)):
        raise ImproperlyConfigured("O adaptador de marketplace deve implementar normalizar_pedido.")
    return adapter


def diagnosticar_adaptador_marketplace(provedor):
    codigo = str(provedor or "PADRAO").upper().strip()
    base = {"contrato": "marketplace_partner_adapter_v1", "provedor": codigo}
    if codigo == "PADRAO":
        return {
            **base,
            "nativo": True,
            "configurado": True,
            "carregavel": True,
            "nome": "Contrato nativo Deigo Varejo",
            "erro": "",
        }
    caminho = _registro_adaptadores().get(codigo, "")
    if not caminho:
        return {
            **base,
            "nativo": False,
            "configurado": False,
            "carregavel": False,
            "nome": "",
            "erro": f"Nenhum adaptador foi configurado para o provedor {codigo}.",
        }
    try:
        adapter = carregar_adaptador_marketplace(codigo)
    except ImproperlyConfigured as exc:
        return {
            **base,
            "nativo": False,
            "configurado": True,
            "carregavel": False,
            "nome": "",
            "erro": str(exc),
        }
    return {
        **base,
        "nativo": False,
        "configurado": True,
        "carregavel": True,
        "nome": str(getattr(adapter, "nome", adapter.__class__.__name__))[:120],
        "erro": "",
    }


def normalizar_payload_marketplace(integracao, payload):
    if not isinstance(payload, dict):
        raise MarketplaceAdapterError("O pedido do parceiro deve ser um objeto JSON.")
    if integracao.provedor == "PADRAO":
        return deepcopy(payload)
    adapter = carregar_adaptador_marketplace(integracao.provedor)
    try:
        normalizado = adapter.normalizar_pedido(payload=deepcopy(payload), integracao=integracao)
    except MarketplaceAdapterError:
        raise
    except Exception as exc:
        raise MarketplaceAdapterError("O adaptador nao conseguiu normalizar o pedido recebido.") from exc
    if not isinstance(normalizado, dict):
        raise MarketplaceAdapterError("O adaptador retornou um pedido em formato invalido.")
    return normalizado
