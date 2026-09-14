"""Catalogo exclusivo para identidades fiscais usadas por testes novos.

O prefixo ``test_`` e intencional: este arquivo e excluido de artefatos gerados
por ``git archive`` pelas regras de ``.gitattributes``. Mesmo em um checkout
completo, toda obtencao le o ambiente configurado e recusa homologacao,
producao e finalidades operacionais.
"""

from dataclasses import dataclass
from types import MappingProxyType

from django.conf import settings

from .estrategia_normalizacao_cnpj import (
    calcular_dv_cnpj,
    canonicalizar_cnpj,
    validar_dv_cnpj,
)
from .politica_identidades_fiscais import avaliar_uso_identidade_fiscal


CONTRATO_CATALOGO_IDENTIDADES_TESTE = "fiscal_test_identity_catalog_v1"
FINALIDADES_CATALOGO = frozenset({"TESTE_UNITARIO", "TESTE_INTEGRACAO_LOCAL"})


class UsoIdentidadeTesteNegado(ValueError):
    """Impede que uma identidade do catalogo atravesse a fronteira de testes."""


@dataclass(frozen=True)
class _DefinicaoIdentidadeTeste:
    codigo: str
    base: str
    categoria: str = "FICTICIO_DESENVOLVIMENTO"


_DEFINICOES = MappingProxyType({
    item.codigo: item
    for item in (
        _DefinicaoIdentidadeTeste("EMPRESA_MATRIZ", "TSTEMPRESA01"),
        _DefinicaoIdentidadeTeste("FILIAL", "TSTFILIAL001"),
        _DefinicaoIdentidadeTeste("FORNECEDOR", "TSTFORNEC001"),
        _DefinicaoIdentidadeTeste("CLIENTE_PJ", "TSTCLI000001"),
    )
})


def _formatar_cnpj(canonico):
    return (
        f"{canonico[:2]}.{canonico[2:5]}.{canonico[5:8]}/"
        f"{canonico[8:12]}-{canonico[12:]}"
    )


def _construir_cnpj(definicao):
    return definicao.base + calcular_dv_cnpj(definicao.base)


def descrever_catalogo_identidades_teste():
    """Lista papeis disponiveis sem expor os documentos completos."""
    return {
        "contrato": CONTRATO_CATALOGO_IDENTIDADES_TESTE,
        "codigos": sorted(_DEFINICOES),
        "quantidade": len(_DEFINICOES),
        "finalidades_permitidas": sorted(FINALIDADES_CATALOGO),
        "valores_expostos": False,
        "distribuicao_producao": False,
        "adocao": "SOMENTE_TESTES_NOVOS_OU_MODIFICADOS",
        "garantias": {
            "prova_titularidade": False,
            "pode_receber_credencial": False,
            "pode_vincular_certificado": False,
            "pode_vincular_licenca": False,
            "pode_emitir": False,
            "libera_focus": False,
            "libera_sefaz_direta": False,
        },
    }


def obter_identidade_fiscal_teste(codigo, *, finalidade, mascarado=False):
    """Entrega uma identidade deterministica apenas em contexto local de teste."""
    definicao = _DEFINICOES.get(str(codigo or "").strip().upper())
    if definicao is None:
        raise UsoIdentidadeTesteNegado("IDENTIDADE_TESTE_DESCONHECIDA")

    finalidade_normalizada = str(finalidade or "").strip().upper()
    avaliacao = avaliar_uso_identidade_fiscal(
        definicao.categoria,
        ambiente=getattr(settings, "ENVIRONMENT", ""),
        finalidade=finalidade_normalizada,
    )
    if finalidade_normalizada not in FINALIDADES_CATALOGO:
        raise UsoIdentidadeTesteNegado("FINALIDADE_FORA_DO_CATALOGO_DE_TESTES")
    if not avaliacao["uso_cadastral_permitido"]:
        raise UsoIdentidadeTesteNegado(avaliacao["motivo"])

    canonico = _construir_cnpj(definicao)
    if canonicalizar_cnpj(canonico) != canonico or not validar_dv_cnpj(canonico):
        raise RuntimeError("DEFINICAO_INTERNA_DE_IDENTIDADE_TESTE_INVALIDA")
    return _formatar_cnpj(canonico) if mascarado else canonico
