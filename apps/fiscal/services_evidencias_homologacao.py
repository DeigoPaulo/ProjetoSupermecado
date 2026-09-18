import re

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import (
    AmbienteFiscal,
    EvidenciaHomologacaoCanal,
    OperacaoHomologacaoFiscal,
    ProvedorEmissaoFiscal,
    StatusEvidenciaHomologacaoCanal,
)
from .roteiros_homologacao_canais import construir_roteiros_homologacao
from .manifesto_qualificacao_fiscal import diagnosticar_qualificacao_instalada
from .politica_canais_fiscais import (
    OPERACOES_FISCAIS_CANONICAS,
    diagnosticar_compatibilidade_canal_uf,
)


CONTRATO_REGISTRO_EVIDENCIA_HOMOLOGACAO = "fiscal_channel_homologation_evidence_v1"
CONTRATO_COBERTURA_EVIDENCIA_HOMOLOGACAO = "fiscal_channel_homologation_coverage_v1"
CONTRATO_PORTAO_CONCLUSAO_HOMOLOGACAO = "fiscal_channel_homologation_completion_gate_v2"
CONTRATO_HISTORICO_CANAIS_HOMOLOGACAO = "fiscal_channel_homologation_history_v1"
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")

ESTADOS_COBERTURA = {
    "APROVADA": "Aprovada",
    "PENDENTE": "Pendente de revisão",
    "REJEITADA": "Rejeitada",
    "AUSENTE": "Sem evidência",
    "BLOQUEADA_LACUNA_INTERNA": "Bloqueada por lacuna interna",
}


def _exigir_master(usuario):
    if not getattr(usuario, "is_authenticated", False) or not usuario.is_superuser:
        raise PermissionDenied("Somente o Master pode registrar ou revisar evidências fiscais.")


def _roteiro(configuracao, operacao):
    operacao = str(operacao or "").strip().upper()
    if operacao not in OperacaoHomologacaoFiscal.values:
        raise ValidationError("Selecione uma operação fiscal válida.")
    roteiros = construir_roteiros_homologacao(settings.BASE_DIR)["roteiros"]
    return next(
        (
            item for item in roteiros
            if item["canal"] == configuracao.provedor_emissao
            and item["operacao"] == operacao
        ),
        None,
    )


def diagnosticar_cobertura_evidencias_homologacao(configuracao):
    """Resume cobertura real sem alterar o status ou liberar a homologação."""
    roteiros = [
        item for item in construir_roteiros_homologacao(settings.BASE_DIR)["roteiros"]
        if item["canal"] == configuracao.provedor_emissao
    ]
    estados_por_operacao = {}
    for operacao, status in configuracao.evidencias_homologacao_canal.filter(
        canal=configuracao.provedor_emissao
    ).values_list("operacao", "status"):
        estados_por_operacao.setdefault(operacao, set()).add(status)

    itens = []
    for roteiro in roteiros:
        estados = estados_por_operacao.get(roteiro["operacao"], set())
        if roteiro["estado_pre_homologacao"] == "BLOQUEADO_LACUNA_INTERNA":
            estado = "BLOQUEADA_LACUNA_INTERNA"
        elif StatusEvidenciaHomologacaoCanal.APROVADA in estados:
            estado = "APROVADA"
        elif StatusEvidenciaHomologacaoCanal.PENDENTE in estados:
            estado = "PENDENTE"
        elif StatusEvidenciaHomologacaoCanal.REJEITADA in estados:
            estado = "REJEITADA"
        else:
            estado = "AUSENTE"
        itens.append({
            "operacao": roteiro["operacao"],
            "titulo": OperacaoHomologacaoFiscal(roteiro["operacao"]).label,
            "estado": estado,
            "estado_display": ESTADOS_COBERTURA[estado],
            "aprovada": estado == "APROVADA",
            "bloqueada": estado == "BLOQUEADA_LACUNA_INTERNA",
        })

    contagens = {
        estado: sum(item["estado"] == estado for item in itens)
        for estado in ESTADOS_COBERTURA
    }
    total = len(itens)
    return {
        "contrato": CONTRATO_COBERTURA_EVIDENCIA_HOMOLOGACAO,
        "canal": configuracao.provedor_emissao,
        "itens": itens,
        "total": total,
        "aprovadas": contagens["APROVADA"],
        "pendentes": contagens["PENDENTE"],
        "rejeitadas": contagens["REJEITADA"],
        "ausentes": contagens["AUSENTE"],
        "bloqueadas": contagens["BLOQUEADA_LACUNA_INTERNA"],
        "cobertura_completa": total > 0 and contagens["APROVADA"] == total,
        "altera_homologacao": False,
        "libera_producao": False,
    }


def avaliar_portao_conclusao_homologacao(configuracao, *, qualificacao_instalada=None):
    cobertura = diagnosticar_cobertura_evidencias_homologacao(configuracao)
    compatibilidade = diagnosticar_compatibilidade_canal_uf(
        configuracao.provedor_emissao, configuracao.filial.uf
    )
    qualificacao = qualificacao_instalada or diagnosticar_qualificacao_instalada(
        canal=configuracao.provedor_emissao,
        operacoes=OPERACOES_FISCAIS_CANONICAS,
    )
    motivos = []
    if cobertura["ausentes"]:
        motivos.append(f'{cobertura["ausentes"]} operação(ões) sem evidência')
    if cobertura["pendentes"]:
        motivos.append(f'{cobertura["pendentes"]} evidência(s) pendente(s) de revisão')
    if cobertura["rejeitadas"]:
        motivos.append(f'{cobertura["rejeitadas"]} operação(ões) somente com evidência rejeitada')
    if cobertura["bloqueadas"]:
        motivos.append(f'{cobertura["bloqueadas"]} operação(ões) com lacuna interna')
    if not compatibilidade["valido"]:
        motivos.append(compatibilidade["motivo"])
    if not qualificacao["valido"]:
        motivos.extend(qualificacao["problemas"])
    return {
        "contrato": CONTRATO_PORTAO_CONCLUSAO_HOMOLOGACAO,
        "permitido": bool(
            cobertura["cobertura_completa"]
            and compatibilidade["valido"]
            and qualificacao["valido"]
        ),
        "motivos": tuple(motivos),
        "cobertura": cobertura,
        "compatibilidade_uf": compatibilidade,
        "qualificacao_instalada": qualificacao,
        "libera_producao": False,
    }


def consultar_historico_canais_homologacao(configuracao, *, usuario):
    """Retorna somente metadados sanitizados para revisão exclusiva do Master."""
    _exigir_master(usuario)
    resumo = {}
    for canal, status in configuracao.evidencias_homologacao_canal.values_list(
        "canal", "status"
    ):
        item = resumo.setdefault(canal, {
            "canal": canal,
            "canal_display": ProvedorEmissaoFiscal(canal).label,
            "total": 0,
            "aprovadas": 0,
            "pendentes": 0,
            "rejeitadas": 0,
        })
        item["total"] += 1
        if status == StatusEvidenciaHomologacaoCanal.APROVADA:
            item["aprovadas"] += 1
        elif status == StatusEvidenciaHomologacaoCanal.PENDENTE:
            item["pendentes"] += 1
        elif status == StatusEvidenciaHomologacaoCanal.REJEITADA:
            item["rejeitadas"] += 1

    transicoes = LogAuditoria.objects.filter(
        modulo="fiscal",
        acao="ALTERA_CANAL_EMISSAO_FISCAL",
        objeto_tipo="ConfiguracaoFiscal",
        objeto_id=str(configuracao.pk),
    ).select_related("usuario").order_by("-criado_em")
    return {
        "contrato": CONTRATO_HISTORICO_CANAIS_HOMOLOGACAO,
        "canais": tuple(sorted(resumo.values(), key=lambda item: item["canal"])),
        "transicoes": tuple({
            "criado_em": log.criado_em,
            "usuario": log.usuario.get_username() if log.usuario else "Sistema",
            "descricao": log.descricao,
        } for log in transicoes),
        "inclui_segredos": False,
        "inclui_referencias": False,
    }


def registrar_evidencia_homologacao(
    configuracao,
    *,
    operacao,
    referencia,
    conteudo_sha256,
    versao_aplicacao,
    resultado_esperado,
    resultado_obtido,
    usuario,
    codigo_status="",
    protocolo="",
    ip=None,
):
    _exigir_master(usuario)
    if configuracao.ambiente != AmbienteFiscal.HOMOLOGACAO:
        raise ValidationError("Evidências deste roteiro só podem ser registradas em homologação.")
    roteiro = _roteiro(configuracao, operacao)
    if roteiro is None:
        raise ValidationError("O canal selecionado não possui roteiro para esta operação.")
    if roteiro["estado_pre_homologacao"] == "BLOQUEADO_LACUNA_INTERNA":
        raise ValidationError("A operação possui lacuna interna e não pode receber evidência real.")

    referencia = str(referencia or "").strip()
    sha256 = str(conteudo_sha256 or "").strip().lower()
    versao = str(versao_aplicacao or "").strip()
    esperado = str(resultado_esperado or "").strip()
    obtido = str(resultado_obtido or "").strip()
    if not referencia:
        raise ValidationError("Informe a referência protegida da evidência.")
    if not SHA256_RE.fullmatch(sha256):
        raise ValidationError("Informe o SHA-256 válido do pacote de evidências.")
    if not versao or not esperado or not obtido:
        raise ValidationError("Informe versão, resultado esperado e resultado obtido.")

    evidencia = EvidenciaHomologacaoCanal.objects.create(
        configuracao=configuracao,
        canal=configuracao.provedor_emissao,
        operacao=roteiro["operacao"],
        ambiente=configuracao.ambiente,
        status=StatusEvidenciaHomologacaoCanal.PENDENTE,
        referencia=referencia[:500],
        conteudo_sha256=sha256,
        codigo_status=str(codigo_status or "").strip()[:20],
        protocolo=str(protocolo or "").strip()[:80],
        versao_aplicacao=versao[:80],
        resultado_esperado=esperado,
        resultado_obtido=obtido,
        registrada_por=usuario,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="REGISTRA_EVIDENCIA_HOMOLOGACAO_CANAL",
        descricao=(
            f"Evidência #{evidencia.pk} registrada como pendente para "
            f"{evidencia.canal}/{evidencia.operacao} na filial {configuracao.filial}."
        ),
        objeto_tipo="EvidenciaHomologacaoCanal",
        objeto_id=str(evidencia.pk),
        ip=ip,
    )
    return evidencia


@transaction.atomic
def revisar_evidencia_homologacao(
    evidencia,
    *,
    decisao,
    observacoes,
    usuario,
    ip=None,
):
    _exigir_master(usuario)
    evidencia = EvidenciaHomologacaoCanal.objects.select_for_update().get(pk=evidencia.pk)
    if evidencia.status != StatusEvidenciaHomologacaoCanal.PENDENTE:
        raise ValidationError("A evidência já foi revisada e seu resultado é imutável.")
    decisao = str(decisao or "").strip().upper()
    if decisao not in {
        StatusEvidenciaHomologacaoCanal.APROVADA,
        StatusEvidenciaHomologacaoCanal.REJEITADA,
    }:
        raise ValidationError("Selecione aprovação ou rejeição da evidência.")
    observacoes = str(observacoes or "").strip()
    if not observacoes:
        raise ValidationError("Registre a justificativa da revisão.")

    evidencia.status = decisao
    evidencia.observacoes_revisao = observacoes
    evidencia.revisada_por = usuario
    evidencia.revisada_em = timezone.now()
    evidencia.save(update_fields=[
        "status", "observacoes_revisao", "revisada_por", "revisada_em"
    ])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="REVISA_EVIDENCIA_HOMOLOGACAO_CANAL",
        descricao=(
            f"Evidência #{evidencia.pk} revisada como {evidencia.get_status_display()} "
            f"para {evidencia.canal}/{evidencia.operacao}."
        ),
        objeto_tipo="EvidenciaHomologacaoCanal",
        objeto_id=str(evidencia.pk),
        ip=ip,
    )
    return evidencia
