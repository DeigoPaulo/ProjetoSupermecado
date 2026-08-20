from datetime import datetime, timedelta

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from lxml import etree

from apps.auditoria.models import LogAuditoria

from .cce_adapters import carregar_adaptador_cce, normalizar_retorno_cce
from .models import (
    CartaCorrecaoFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    StatusCartaCorrecao,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)


def _data_autorizacao(documento):
    if documento.xml_conteudo:
        try:
            raiz = etree.fromstring(documento.xml_conteudo.encode("utf-8"))
            valores = raiz.xpath("//*[local-name()='dhRecbto']/text()")
            if valores:
                return datetime.fromisoformat(str(valores[-1]).replace("Z", "+00:00"))
        except (ValueError, TypeError, etree.XMLSyntaxError):
            pass
    return documento.criado_em


def registrar_carta_correcao(
    documento, *, correcao, confirmou_limites=False, usuario, ip=None
):
    correcao = " ".join(str(correcao or "").split())
    if not 15 <= len(correcao) <= 1000:
        raise ValidationError("A correção deve ter entre 15 e 1.000 caracteres.")
    if not confirmou_limites:
        raise ValidationError(
            "Confirme que a correção respeita os limites legais da CC-e."
        )

    try:
        adaptador = carregar_adaptador_cce()
    except ImproperlyConfigured as exc:
        raise ValidationError(str(exc)) from exc
    if adaptador is None:
        raise ValidationError(
            "A Carta de Correção ainda não possui adaptador fiscal configurado."
        )

    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().select_related(
            "filial__empresa"
        ).get(pk=documento.pk)
        if documento.tipo_documento != TipoDocumentoFiscal.NFE:
            raise ValidationError("A CC-e está disponível somente para NF-e modelo 55.")
        if documento.status != StatusDocumentoFiscal.EMITIDO:
            raise ValidationError("A CC-e exige uma NF-e autorizada e não cancelada.")
        if not documento.chave_acesso or not documento.protocolo:
            raise ValidationError("A NF-e não possui chave e protocolo de autorização.")

        autorizada_em = _data_autorizacao(documento)
        if autorizada_em:
            if timezone.is_naive(autorizada_em):
                autorizada_em = timezone.make_aware(autorizada_em)
            if timezone.now() - autorizada_em > timedelta(hours=720):
                raise ValidationError(
                    "O prazo oficial de 720 horas para registrar a CC-e foi ultrapassado."
                )

        if documento.cartas_correcao.filter(
            status=StatusCartaCorrecao.PENDENTE
        ).exists():
            raise ValidationError(
                "Já existe uma Carta de Correção aguardando processamento para esta NF-e."
            )
        maior = documento.cartas_correcao.aggregate(valor=Max("sequencia"))["valor"] or 0
        sequencia = maior + 1
        if sequencia > 20:
            raise ValidationError("A NF-e atingiu o limite oficial de 20 Cartas de Correção.")

        configuracao = ConfiguracaoFiscal.objects.filter(
            filial=documento.filial,
            ativo=True,
        ).first()
        if configuracao is None:
            raise ValidationError("A filial não possui configuração fiscal ativa.")

        tentativa = CartaCorrecaoFiscal.objects.create(
            empresa=documento.filial.empresa,
            filial=documento.filial,
            documento=documento,
            sequencia=sequencia,
            correcao=correcao,
            ambiente=configuracao.ambiente,
            usuario=usuario,
        )

    try:
        retorno = adaptador.corrigir(
            documento=documento,
            sequencia=tentativa.sequencia,
            correcao=tentativa.correcao,
            idempotency_key=f"cce:{tentativa.pk}",
        )
        resultado = normalizar_retorno_cce(retorno)
    except Exception as exc:
        tentativa.status = StatusCartaCorrecao.ERRO
        tentativa.mensagem = str(exc)[:2000]
        tentativa.processado_em = timezone.now()
        tentativa.save(update_fields=["status", "mensagem", "processado_em", "atualizado_em"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="CARTA_CORRECAO_ERRO",
            descricao=(
                f"Falha na CC-e #{tentativa.sequencia} da NF-e "
                f"{documento.chave_acesso}: {tentativa.mensagem}"
            ),
            objeto_tipo="CartaCorrecaoFiscal",
            objeto_id=str(tentativa.pk),
            ip=ip,
        )
        raise ValidationError(f"Falha ao transmitir a Carta de Correção: {exc}") from exc

    tentativa.status = resultado["status"]
    tentativa.codigo_status = resultado["codigo_status"]
    tentativa.protocolo = resultado["protocolo"]
    tentativa.mensagem = resultado["mensagem"]
    tentativa.xml_envio = resultado["xml_envio"]
    tentativa.xml_retorno = resultado["xml_retorno"]
    tentativa.processado_em = timezone.now()
    tentativa.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="CARTA_CORRECAO",
        descricao=(
            f"CC-e #{tentativa.sequencia} da NF-e {documento.chave_acesso}: "
            f"{tentativa.get_status_display()} ({tentativa.codigo_status or '-'})."
        ),
        objeto_tipo="CartaCorrecaoFiscal",
        objeto_id=str(tentativa.pk),
        ip=ip,
    )
    return tentativa
