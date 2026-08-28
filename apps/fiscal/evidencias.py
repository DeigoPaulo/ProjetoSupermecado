import hashlib
import json

from django.db import transaction
from django.utils import timezone

from .models import DocumentoFiscal, EvidenciaFiscal


def _serializar_conteudo(conteudo):
    if isinstance(conteudo, str):
        return conteudo
    return json.dumps(
        conteudo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def registrar_evidencia_fiscal(
    *,
    documento,
    tipo,
    referencia,
    conteudo,
    usuario=None,
    canal="",
    chave_acesso="",
    protocolo="",
):
    referencia = str(referencia or "").strip()
    if not referencia:
        raise ValueError("A referência idempotente da evidência fiscal é obrigatória.")
    if len(referencia) > 180:
        referencia = hashlib.sha256(referencia.encode("utf-8")).hexdigest()
    conteudo = _serializar_conteudo(conteudo)

    with transaction.atomic():
        documento_bloqueado = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        existente = EvidenciaFiscal.objects.filter(
            documento=documento_bloqueado,
            tipo=tipo,
            referencia=referencia,
        ).first()
        if existente:
            if existente.conteudo_sha256 != hashlib.sha256(conteudo.encode("utf-8")).hexdigest():
                raise ValueError(
                    "A referência da evidência fiscal já existe com conteúdo diferente."
                )
            return existente, False

        anterior = (
            EvidenciaFiscal.objects.filter(documento=documento_bloqueado)
            .order_by("-sequencia", "-id")
            .first()
        )
        evidencia = EvidenciaFiscal.objects.create(
            documento=documento_bloqueado,
            sequencia=(anterior.sequencia + 1) if anterior else 1,
            tipo=tipo,
            canal=str(canal or "")[:40],
            referencia=referencia,
            chave_acesso=str(chave_acesso or documento_bloqueado.chave_acesso or "")[:44],
            protocolo=str(protocolo or "")[:80],
            conteudo=conteudo,
            anterior_sha256=anterior.cadeia_sha256 if anterior else "",
            usuario=usuario if getattr(usuario, "pk", None) else None,
        )
        return evidencia, True


def verificar_integridade_evidencias(documento):
    anterior_sha256 = ""
    sequencia_esperada = 1
    total = 0
    for evidencia in documento.evidencias_fiscais.order_by("sequencia", "id"):
        total += 1
        conteudo_sha256 = hashlib.sha256(evidencia.conteudo.encode("utf-8")).hexdigest()
        cadeia_sha256 = EvidenciaFiscal.calcular_cadeia(
            evidencia.documento_id,
            evidencia.sequencia,
            evidencia.tipo,
            evidencia.referencia,
            conteudo_sha256,
            evidencia.anterior_sha256,
        )
        if (
            evidencia.sequencia != sequencia_esperada
            or evidencia.conteudo_sha256 != conteudo_sha256
            or evidencia.anterior_sha256 != anterior_sha256
            or evidencia.cadeia_sha256 != cadeia_sha256
        ):
            return {
                "integra": False,
                "total": total,
                "sequencia_invalida": evidencia.sequencia,
                "cadeia_sha256": anterior_sha256,
            }
        anterior_sha256 = evidencia.cadeia_sha256
        sequencia_esperada += 1
    return {
        "integra": True,
        "total": total,
        "sequencia_invalida": None,
        "cadeia_sha256": anterior_sha256,
    }

def gerar_manifesto_integridade_evidencias():
    documentos = []
    documento_id_atual = None
    anterior_sha256 = ""
    sequencia_esperada = 1
    total_documento = 0
    total_evidencias = 0
    documento_integro = True
    sequencia_invalida = None

    def finalizar_documento():
        if documento_id_atual is None:
            return
        documentos.append(
            {
                "documento_id": documento_id_atual,
                "total_evidencias": total_documento,
                "integra": documento_integro,
                "sequencia_invalida": sequencia_invalida,
                "cadeia_sha256": anterior_sha256,
            }
        )

    evidencias = EvidenciaFiscal.objects.order_by(
        "documento_id", "sequencia", "id"
    ).iterator(chunk_size=1000)
    for evidencia in evidencias:
        if evidencia.documento_id != documento_id_atual:
            finalizar_documento()
            documento_id_atual = evidencia.documento_id
            anterior_sha256 = ""
            sequencia_esperada = 1
            total_documento = 0
            documento_integro = True
            sequencia_invalida = None

        total_documento += 1
        total_evidencias += 1
        conteudo_sha256 = hashlib.sha256(evidencia.conteudo.encode("utf-8")).hexdigest()
        cadeia_sha256 = EvidenciaFiscal.calcular_cadeia(
            evidencia.documento_id,
            evidencia.sequencia,
            evidencia.tipo,
            evidencia.referencia,
            conteudo_sha256,
            evidencia.anterior_sha256,
        )
        valida = (
            evidencia.sequencia == sequencia_esperada
            and evidencia.conteudo_sha256 == conteudo_sha256
            and evidencia.anterior_sha256 == anterior_sha256
            and evidencia.cadeia_sha256 == cadeia_sha256
        )
        if not valida and documento_integro:
            documento_integro = False
            sequencia_invalida = evidencia.sequencia
        anterior_sha256 = evidencia.cadeia_sha256
        sequencia_esperada += 1
    finalizar_documento()

    nucleo = {
        "contrato": "fiscal_evidence_anchor_v1",
        "total_documentos": len(documentos),
        "total_evidencias": total_evidencias,
        "documentos": documentos,
    }
    serializado = json.dumps(
        nucleo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    divergencias = [item for item in documentos if not item["integra"]]
    return {
        **nucleo,
        "gerado_em": timezone.now().isoformat(),
        "integra": not divergencias,
        "total_divergencias": len(divergencias),
        "ancora_global_sha256": hashlib.sha256(serializado.encode("utf-8")).hexdigest(),
        "observacao": (
            "Manifesto local sem XML, chave, protocolo, CNPJ, certificado ou credencial. "
            "Preserve-o em backup protegido para comparação histórica."
        ),
    }

def verificar_continuidade_manifesto_anterior(manifesto_anterior, manifesto_atual):
    if not isinstance(manifesto_anterior, dict):
        return ["O manifesto externo anterior não é um objeto JSON válido."]
    if manifesto_anterior.get("contrato") != "fiscal_evidence_anchor_v1":
        return ["O manifesto externo anterior possui contrato incompatível."]
    anteriores = {
        int(item["documento_id"]): item
        for item in manifesto_anterior.get("documentos", [])
        if isinstance(item, dict) and item.get("documento_id") is not None
    }
    atuais = {
        int(item["documento_id"]): item
        for item in manifesto_atual.get("documentos", [])
        if isinstance(item, dict) and item.get("documento_id") is not None
    }
    divergencias = []
    for documento_id, anterior in anteriores.items():
        atual = atuais.get(documento_id)
        if atual is None:
            divergencias.append(
                f"Documento {documento_id}: cadeia ausente em relação à âncora anterior."
            )
            continue
        total_anterior = int(anterior.get("total_evidencias") or 0)
        total_atual = int(atual.get("total_evidencias") or 0)
        if total_atual < total_anterior:
            divergencias.append(
                f"Documento {documento_id}: quantidade de evidências regrediu."
            )
            continue
        marco = EvidenciaFiscal.objects.filter(
            documento_id=documento_id,
            sequencia=total_anterior,
        ).values_list("cadeia_sha256", flat=True).first()
        if total_anterior and marco != anterior.get("cadeia_sha256"):
            divergencias.append(
                f"Documento {documento_id}: prefixo histórico diverge da âncora anterior."
            )
    return divergencias