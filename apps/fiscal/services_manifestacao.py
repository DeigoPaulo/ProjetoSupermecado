from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .manifestacao_adapters import (
    carregar_adaptador_manifestacao,
    normalizar_retorno_manifestacao,
)
from .models import (
    ConfiguracaoFiscal,
    DocumentoDFeRecebido,
    ManifestacaoDestinatario,
    StatusManifestacaoDestinatario,
    TipoManifestacaoDestinatario,
)


TIPOS_CONCLUSIVOS = {
    TipoManifestacaoDestinatario.CONFIRMACAO,
    TipoManifestacaoDestinatario.DESCONHECIMENTO,
    TipoManifestacaoDestinatario.OPERACAO_NAO_REALIZADA,
}


def registrar_manifestacao_destinatario(
    documento, *, tipo, justificativa="", usuario, ip=None
):
    tipo = str(tipo or "").strip()
    justificativa = str(justificativa or "").strip()
    if tipo not in TipoManifestacaoDestinatario.values:
        raise ValidationError("Selecione um tipo válido de manifestação do destinatário.")
    if not documento.filial_destino_id:
        raise ValidationError("Identifique a filial destinatária antes de manifestar a NF-e.")
    if documento.filial_destino.empresa_id != documento.empresa_id:
        raise ValidationError(
            "A filial destinatária não pertence à empresa do documento fiscal."
        )
    if tipo == TipoManifestacaoDestinatario.OPERACAO_NAO_REALIZADA:
        if not 15 <= len(justificativa) <= 255:
            raise ValidationError(
                "A operação não realizada exige justificativa entre 15 e 255 caracteres."
            )
    elif justificativa:
        raise ValidationError(
            "A justificativa deve ser informada somente para operação não realizada."
        )

    try:
        adaptador = carregar_adaptador_manifestacao()
    except ImproperlyConfigured as exc:
        raise ValidationError(str(exc)) from exc
    if adaptador is None:
        raise ValidationError(
            "A manifestação do destinatário ainda não possui adaptador fiscal configurado."
        )

    with transaction.atomic():
        documento = DocumentoDFeRecebido.objects.select_for_update().select_related(
            "empresa", "filial_destino"
        ).get(pk=documento.pk)
        ativas = documento.manifestacoes_destinatario.filter(
            status__in=[
                StatusManifestacaoDestinatario.PENDENTE,
                StatusManifestacaoDestinatario.AUTORIZADA,
            ]
        )
        if ativas.filter(tipo=tipo).exists():
            raise ValidationError(
                "Esta manifestação já está em andamento ou foi autorizada para a NF-e."
            )
        conclusiva = ativas.filter(tipo__in=TIPOS_CONCLUSIVOS).first()
        if conclusiva:
            raise ValidationError(
                "A NF-e já possui manifestação conclusiva em andamento ou autorizada: "
                f"{conclusiva.get_tipo_display()}."
            )
        if tipo in TIPOS_CONCLUSIVOS and documento.data_emissao:
            limite = timezone.localdate() - timedelta(days=90)
            if documento.data_emissao < limite:
                raise ValidationError(
                    "O prazo oficial estimado de 90 dias para manifestação conclusiva foi ultrapassado. "
                    "Confirme a data de autorização com o responsável fiscal."
                )

        configuracao = ConfiguracaoFiscal.objects.filter(
            filial=documento.filial_destino,
            ativo=True,
        ).first()
        if configuracao is None:
            raise ValidationError(
                "A filial destinatária não possui configuração fiscal ativa."
            )
        tentativa = ManifestacaoDestinatario.objects.create(
            empresa=documento.empresa,
            filial=documento.filial_destino,
            documento=documento,
            tipo=tipo,
            justificativa=justificativa,
            ambiente=configuracao.ambiente,
            usuario=usuario,
        )
    try:
        retorno = adaptador.manifestar(
            documento=documento,
            tipo=tipo,
            justificativa=justificativa,
            idempotency_key=f"manifestacao:{tentativa.pk}",
        )
        resultado = normalizar_retorno_manifestacao(retorno)
    except Exception as exc:
        tentativa.status = StatusManifestacaoDestinatario.ERRO
        tentativa.mensagem = str(exc)[:2000]
        tentativa.processado_em = timezone.now()
        tentativa.save(update_fields=["status", "mensagem", "processado_em", "atualizado_em"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="MANIFESTACAO_DESTINATARIO_ERRO",
            descricao=f"Falha ao transmitir {tentativa.get_tipo_display()} para a NF-e {documento.chave_acesso}: {tentativa.mensagem}",
            objeto_tipo="ManifestacaoDestinatario",
            objeto_id=str(tentativa.pk),
            ip=ip,
        )
        raise ValidationError(f"Falha ao transmitir a manifestação: {exc}") from exc

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
        acao="MANIFESTACAO_DESTINATARIO",
        descricao=(
            f"{tentativa.get_tipo_display()} da NF-e {documento.chave_acesso}: "
            f"{tentativa.get_status_display()} ({tentativa.codigo_status or '-'})."
        ),
        objeto_tipo="ManifestacaoDestinatario",
        objeto_id=str(tentativa.pk),
        ip=ip,
    )
    return tentativa
