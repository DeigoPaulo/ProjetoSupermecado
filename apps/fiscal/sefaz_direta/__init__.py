"""Núcleo isolável da integração direta com a SEFAZ."""

from .adapter import (
    HOSTS_OFICIAIS_GO,
    NFE_NS,
    SERVICOS_GO,
    SOAP_ACTION,
    SOAP_NS,
    WSDL_NS,
    SefazDiretaAdapter,
    SefazDiretaConnectionError,
    SefazDiretaError,
    SefazDiretaHTTPError,
)
from .capacidades import matriz_capacidades, resumo_capacidades
from .manifestacao import (
    ENDPOINTS_MANIFESTACAO,
    SefazDiretaManifestacaoAdapter,
    SefazDiretaManifestacaoError,
)
from .cadastro import (
    SefazDiretaConsultaCadastroAdapter,
    SefazDiretaConsultaCadastroError,
)
from .cce import (
    CONDICAO_USO_CCE,
    SefazDiretaCartaCorrecaoAdapter,
    SefazDiretaCartaCorrecaoError,
)
from .dfe import (
    ENDPOINTS_DFE,
    SefazDiretaDFeAdapter,
    SefazDiretaDFeConnectionError,
    SefazDiretaDFeError,
    SefazDiretaDFeHTTPError,
)

__all__ = [
    "HOSTS_OFICIAIS_GO", "NFE_NS", "SERVICOS_GO", "SOAP_ACTION", "SOAP_NS", "WSDL_NS",
    "SefazDiretaAdapter", "SefazDiretaConnectionError", "SefazDiretaError",
    "SefazDiretaHTTPError", "ENDPOINTS_DFE", "SefazDiretaDFeAdapter",
    "SefazDiretaDFeConnectionError", "SefazDiretaDFeError",
    "SefazDiretaDFeHTTPError", "matriz_capacidades", "resumo_capacidades",
    "ENDPOINTS_MANIFESTACAO", "SefazDiretaManifestacaoAdapter",
    "SefazDiretaManifestacaoError", "CONDICAO_USO_CCE",
    "SefazDiretaCartaCorrecaoAdapter", "SefazDiretaCartaCorrecaoError",
    "SefazDiretaConsultaCadastroAdapter", "SefazDiretaConsultaCadastroError",
]
