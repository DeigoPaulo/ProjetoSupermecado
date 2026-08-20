import re

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .cadastro_adapters import (
    carregar_adaptador_consulta_cadastro,
    normalizar_retorno_consulta_cadastro,
)
from .models import (
    ConsultaCadastroContribuinte,
    StatusConsultaCadastro,
    TipoDocumentoConsultaCadastro,
)


def consultar_cadastro_contribuinte(
    *, filial, uf, tipo_documento, documento, usuario, ip=None
):
    tipo = str(tipo_documento or "").strip().upper()
    if tipo not in TipoDocumentoConsultaCadastro.values:
        raise ValidationError("Escolha CNPJ, CPF ou inscrição estadual.")
    valor = re.sub(r"\D", "", str(documento or ""))
    if tipo == TipoDocumentoConsultaCadastro.CNPJ and len(valor) != 14:
        raise ValidationError("Informe um CNPJ válido com 14 dígitos.")
    if tipo == TipoDocumentoConsultaCadastro.CPF and len(valor) != 11:
        raise ValidationError("Informe um CPF válido com 11 dígitos.")
    if tipo == TipoDocumentoConsultaCadastro.IE and not 2 <= len(valor) <= 14:
        raise ValidationError("Informe uma inscrição estadual válida.")
    uf = str(uf or filial.uf or "").strip().upper()
    if len(uf) != 2:
        raise ValidationError("Informe a UF da consulta cadastral.")
    if not hasattr(filial, "configuracao_fiscal") or not filial.configuracao_fiscal.ativo:
        raise ValidationError("A filial não possui configuração fiscal ativa.")

    try:
        adaptador = carregar_adaptador_consulta_cadastro()
    except ImproperlyConfigured as exc:
        raise ValidationError(str(exc)) from exc
    if adaptador is None:
        raise ValidationError("A consulta cadastral ainda não possui adaptador configurado.")

    consulta = ConsultaCadastroContribuinte.objects.create(
        empresa=filial.empresa,
        filial=filial,
        uf=uf,
        tipo_documento=tipo,
        documento=valor,
        usuario=usuario,
    )
    try:
        retorno = adaptador.consultar(
            filial=filial,
            uf=uf,
            tipo_documento=tipo,
            documento=valor,
        )
        resultado = normalizar_retorno_consulta_cadastro(retorno)
    except Exception as exc:
        consulta.status = StatusConsultaCadastro.ERRO
        consulta.mensagem = str(exc)[:2000]
        consulta.processado_em = timezone.now()
        consulta.save(
            update_fields=["status", "mensagem", "processado_em", "atualizado_em"]
        )
        _auditar(consulta, usuario, "CONSULTA_CADASTRO_ERRO", ip)
        raise ValidationError(f"Falha na consulta cadastral: {exc}") from exc

    consulta.status = resultado["status"]
    consulta.codigo_status = resultado["codigo_status"]
    consulta.mensagem = resultado["mensagem"]
    consulta.ocorrencias = resultado["ocorrencias"]
    consulta.xml_envio = resultado["xml_envio"]
    consulta.xml_retorno = resultado["xml_retorno"]
    consulta.processado_em = timezone.now()
    consulta.save()
    _auditar(consulta, usuario, "CONSULTA_CADASTRO", ip)
    return consulta


def _auditar(consulta, usuario, acao, ip):
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao=acao,
        descricao=(
            f"Consulta {consulta.tipo_documento} {consulta.documento} em "
            f"{consulta.uf}: {consulta.get_status_display()} "
            f"({consulta.codigo_status or '-'})."
        ),
        objeto_tipo="ConsultaCadastroContribuinte",
        objeto_id=str(consulta.pk),
        ip=ip,
    )
