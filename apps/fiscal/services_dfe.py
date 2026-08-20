from datetime import date
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.clientes.escopo import empresa_id_do_usuario

from .dfe_adapters import carregar_adaptador_dfe, normalizar_lote_dfe
from .models import (
    ConfiguracaoDistribuicaoDFe,
    ControleDistribuicaoDFeFilial,
    DocumentoDFeRecebido,
    EventoDFeRecebido,
    StatusDFeRecebido,
)


def _digitos(valor):
    return "".join(caractere for caractere in (valor or "") if caractere.isdigit())


def _filial_por_destinatario(destinatario_cnpj, *, usuario=None, empresa=None):
    cnpj = _digitos(destinatario_cnpj)
    filiais = Filial.objects.filter(is_active=True).select_related("empresa")
    if empresa is not None:
        filiais = filiais.filter(empresa=empresa)
    elif usuario is not None:
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None:
            filiais = filiais.filter(empresa_id=empresa_id)
    candidatas = [
        filial
        for filial in filiais
        if _digitos(filial.cnpj or filial.empresa.cnpj) == cnpj
    ]
    empresas = {filial.empresa_id: filial.empresa for filial in candidatas}
    if not empresas:
        raise ValidationError("Nenhuma empresa ativa encontrada para o CNPJ destinatário da NF-e.")
    if len(empresas) > 1:
        raise ValidationError(
            "Há mais de uma empresa compatível com o CNPJ destinatário; corrija os cadastros antes de importar."
        )
    empresa_encontrada = next(iter(empresas.values()))
    filial_direta = next(
        (filial for filial in candidatas if _digitos(filial.cnpj) == cnpj),
        candidatas[0],
    )
    return empresa_encontrada, filial_direta


def registrar_xml_dfe_recebido(
    conteudo,
    *,
    usuario,
    ip=None,
    nsu="",
    origem="MANUAL",
    filial_esperada=None,
):
    """Armazena NF-e recebida sem gerar entrada, manifestação, estoque ou financeiro."""
    from apps.compras.services_xml import ler_xml_nfe

    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    dados = ler_xml_nfe(conteudo)
    empresa, filial_direta = _filial_por_destinatario(
        dados["destinatario_cnpj"], usuario=usuario
    )
    if filial_esperada is not None and filial_direta.pk != filial_esperada.pk:
        raise ValidationError(
            "O XML retornado não pertence ao CNPJ da filial consultada."
        )

    with transaction.atomic():
        ConfiguracaoDistribuicaoDFe.objects.get_or_create(empresa=empresa)
        documento, criado = DocumentoDFeRecebido.objects.get_or_create(
            empresa=empresa,
            chave_acesso=dados["chave"],
            defaults={
                "filial_destino": filial_direta,
                "nsu": str(nsu or ""),
                "schema": "procNFe",
                "emitente_cnpj": dados["emitente_cnpj"],
                "emitente_nome": dados["emitente_nome"],
                "numero_documento": dados["numero_documento"],
                "data_emissao": dados["data_emissao"],
                "valor_total": dados["total_documento"],
                "status": StatusDFeRecebido.XML_DISPONIVEL,
                "origem": origem,
                "xml_conteudo": conteudo.decode("utf-8", errors="strict"),
            },
        )
        if not criado and not documento.xml_conteudo:
            documento.filial_destino = filial_direta
            documento.nsu = documento.nsu or str(nsu or "")
            documento.schema = "procNFe"
            documento.emitente_cnpj = dados["emitente_cnpj"]
            documento.emitente_nome = dados["emitente_nome"]
            documento.numero_documento = dados["numero_documento"]
            documento.data_emissao = dados["data_emissao"]
            documento.valor_total = dados["total_documento"]
            documento.origem = origem
            documento.xml_conteudo = conteudo.decode("utf-8", errors="strict")
            if documento.status == StatusDFeRecebido.NOVO:
                documento.status = StatusDFeRecebido.XML_DISPONIVEL
            documento.save()
        if not criado and documento.xml_conteudo and nsu and documento.nsu != str(nsu):
            documento.nsu = str(nsu)
            documento.save(update_fields=["nsu", "atualizado_em"])
        if criado:
            LogAuditoria.objects.create(
                usuario=usuario,
                modulo="fiscal",
                acao="IMPORTACAO_DFE_RECEBIDO",
                descricao=(
                    f"NF-e recebida {documento.chave_acesso} armazenada na caixa DF-e da empresa {empresa}. "
                    "Nenhuma entrada, manifestação ou lançamento financeiro foi criado."
                ),
                objeto_tipo="DocumentoDFeRecebido",
                objeto_id=str(documento.pk),
                ip=ip,
            )
    return documento, criado


def _decimal_seguro(valor):
    try:
        return Decimal(str(valor or "0"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("O valor total de um documento DF-e é inválido.") from exc


def _data_segura(valor):
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    resultado = parse_date(str(valor)[:10])
    if not resultado:
        raise ValidationError("A data de emissão de um documento DF-e é inválida.")
    return resultado


def registrar_evento_dfe_recebido(item, *, filial, usuario, ip=None):
    """Preserva eventos distribuídos pela SEFAZ sem executar efeitos operacionais."""
    chave = _digitos(item.get("chave_acesso"))
    nsu = str(item.get("nsu") or "").strip()
    xml = item.get("xml")
    if len(chave) != 44 or not nsu.isdigit() or not xml:
        raise ValidationError("Evento DF-e inválido: informe chave, NSU e XML.")
    destinatario = _digitos(item.get("destinatario_cnpj") or filial.cnpj or filial.empresa.cnpj)
    if destinatario != _digitos(filial.cnpj or filial.empresa.cnpj):
        raise ValidationError("O evento retornado não pertence ao CNPJ da filial consultada.")
    data_evento = item.get("data_evento")
    if data_evento and not hasattr(data_evento, "tzinfo"):
        data_evento = parse_datetime(str(data_evento))
    try:
        sequencia = max(1, int(item.get("sequencia") or 1))
    except (TypeError, ValueError) as exc:
        raise ValidationError("A sequência do evento DF-e é inválida.") from exc

    evento, criado = EventoDFeRecebido.objects.get_or_create(
        empresa=filial.empresa,
        nsu=nsu,
        defaults={
            "filial_destino": filial,
            "schema": str(item.get("schema") or "")[:80],
            "chave_acesso": chave,
            "tipo_evento": str(item.get("tipo_evento") or "")[:20],
            "sequencia": sequencia,
            "data_evento": data_evento,
            "descricao": str(item.get("descricao") or "")[:255],
            "xml_conteudo": str(xml),
        },
    )
    if not criado and (evento.chave_acesso != chave or evento.xml_conteudo != str(xml)):
        raise ValidationError("O NSU do evento já existe com conteúdo divergente.")
    if criado:
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="EVENTO_DFE_RECEBIDO",
            descricao=(
                f"Evento fiscal {evento.tipo_evento or '-'} da NF-e {chave} armazenado para {filial}. "
                "Nenhuma movimentação operacional foi criada."
            ),
            objeto_tipo="EventoDFeRecebido",
            objeto_id=str(evento.pk),
            ip=ip,
        )
    return evento, criado

def registrar_resumo_dfe_recebido(item, *, filial, usuario, ip=None):
    chave = _digitos(item.get("chave_acesso"))
    if len(chave) != 44:
        raise ValidationError("A chave de acesso resumida deve possuir 44 dígitos.")
    destinatario = _digitos(item.get("destinatario_cnpj") or filial.cnpj or filial.empresa.cnpj)
    if destinatario != _digitos(filial.cnpj or filial.empresa.cnpj):
        raise ValidationError("O resumo retornado não pertence ao CNPJ da filial consultada.")

    documento, criado = DocumentoDFeRecebido.objects.get_or_create(
        empresa=filial.empresa,
        chave_acesso=chave,
        defaults={
            "filial_destino": filial,
            "nsu": str(item.get("nsu") or ""),
            "schema": str(item.get("schema") or "resNFe")[:80],
            "emitente_cnpj": _digitos(item.get("emitente_cnpj"))[:14],
            "emitente_nome": str(item.get("emitente_nome") or "")[:255],
            "numero_documento": str(item.get("numero_documento") or "")[:30],
            "data_emissao": _data_segura(item.get("data_emissao")),
            "valor_total": _decimal_seguro(item.get("valor_total")),
            "status": StatusDFeRecebido.NOVO,
            "origem": "DISTRIBUICAO",
        },
    )
    if not criado:
        campos_atualizados = []
        novos_valores = {
            "filial_destino": filial,
            "nsu": str(item.get("nsu") or documento.nsu),
            "emitente_cnpj": _digitos(item.get("emitente_cnpj"))[:14] or documento.emitente_cnpj,
            "emitente_nome": str(item.get("emitente_nome") or documento.emitente_nome)[:255],
            "numero_documento": str(item.get("numero_documento") or documento.numero_documento)[:30],
            "data_emissao": _data_segura(item.get("data_emissao")) or documento.data_emissao,
        }
        if item.get("valor_total") not in (None, ""):
            novos_valores["valor_total"] = _decimal_seguro(item.get("valor_total"))
        for campo, valor in novos_valores.items():
            if getattr(documento, campo) != valor:
                setattr(documento, campo, valor)
                campos_atualizados.append(campo)
        if campos_atualizados:
            documento.save(update_fields=[*campos_atualizados, "atualizado_em"])
    if criado:
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="RESUMO_DFE_RECEBIDO",
            descricao=(
                f"Resumo da NF-e {chave} armazenado para {filial}. "
                "O XML completo ainda não está disponível e nenhuma operação foi criada."
            ),
            objeto_tipo="DocumentoDFeRecebido",
            objeto_id=str(documento.pk),
            ip=ip,
        )
    return documento, criado


def consultar_distribuicao_dfe(*, filial, usuario, ip=None, limite=50):
    empresa_id = empresa_id_do_usuario(usuario)
    if empresa_id is not None and filial.empresa_id != empresa_id:
        raise ValidationError("A filial selecionada não pertence à empresa do usuário.")
    cnpj = _digitos(filial.cnpj or filial.empresa.cnpj)
    if len(cnpj) != 14:
        raise ValidationError("Cadastre um CNPJ válido na filial antes de consultar DF-e.")

    configuracao, _ = ConfiguracaoDistribuicaoDFe.objects.get_or_create(
        empresa=filial.empresa
    )
    if not configuracao.ativo:
        raise ValidationError("A caixa de entrada de DF-e está desativada para esta empresa.")
    controle, _ = ControleDistribuicaoDFeFilial.objects.get_or_create(
        configuracao=configuracao,
        filial=filial,
    )
    agora = timezone.now()
    if controle.proxima_consulta_em and controle.proxima_consulta_em > agora:
        horario = timezone.localtime(controle.proxima_consulta_em).strftime("%d/%m/%Y às %H:%M")
        raise ValidationError(
            f"A SEFAZ solicitou intervalo entre consultas. Tente novamente em {horario}."
        )
    cursor_inicial = controle.ultimo_nsu
    try:
        adaptador = carregar_adaptador_dfe()
    except ImproperlyConfigured as exc:
        raise ValidationError(str(exc)) from exc
    if adaptador is None:
        raise ValidationError(
            "A distribuição automática ainda não possui adaptador fiscal configurado."
        )

    try:
        retorno = adaptador.consultar(
            cnpj=cnpj,
            ultimo_nsu=cursor_inicial,
            limite=max(1, min(int(limite), 100)),
        )
    except Exception as exc:
        mensagem = f"Falha ao consultar o provedor DF-e: {exc}"
        ControleDistribuicaoDFeFilial.objects.filter(pk=controle.pk).update(
            ultima_consulta_em=timezone.now(),
            ultima_mensagem=mensagem[:2000],
        )
        raise ValidationError(mensagem) from exc

    lote = normalizar_lote_dfe(retorno)
    if cursor_inicial and lote["ultimo_nsu"] and int(lote["ultimo_nsu"]) < int(cursor_inicial):
        raise ValidationError("O adaptador tentou regredir o cursor NSU da filial.")

    with transaction.atomic():
        controle = ControleDistribuicaoDFeFilial.objects.select_for_update().get(
            pk=controle.pk
        )
        if controle.ultimo_nsu != cursor_inicial:
            raise ValidationError(
                "Outra consulta atualizou esta filial. Recarregue a página antes de tentar novamente."
            )
        criados = 0
        atualizados = 0
        eventos = 0
        for item in lote["documentos"]:
            xml = item.get("xml")
            if item.get("tipo_documento") == "EVENTO":
                _, criado = registrar_evento_dfe_recebido(
                    item, filial=filial, usuario=usuario, ip=ip
                )
                eventos += 1
            elif xml:
                _, criado = registrar_xml_dfe_recebido(
                    xml,
                    usuario=usuario,
                    ip=ip,
                    nsu=item.get("nsu"),
                    origem="DISTRIBUICAO",
                    filial_esperada=filial,
                )
            else:
                _, criado = registrar_resumo_dfe_recebido(
                    item, filial=filial, usuario=usuario, ip=ip
                )
            criados += int(criado)
            atualizados += int(not criado)

        agora = timezone.now()
        controle.ultimo_nsu = lote["ultimo_nsu"] or cursor_inicial
        controle.max_nsu = lote["max_nsu"]
        controle.ultima_consulta_em = agora
        controle.proxima_consulta_em = (
            agora + timedelta(seconds=lote["aguardar_segundos"])
            if lote["aguardar_segundos"]
            else None
        )
        controle.ultima_mensagem = lote["mensagem"] or (
            f"{len(lote['documentos'])} documento(s) processado(s)."
        )
        controle.save()
        configuracao.ultimo_nsu = controle.ultimo_nsu
        configuracao.ultima_consulta_em = agora
        configuracao.ultima_mensagem = (
            f"{filial}: {controle.ultima_mensagem}"
        )
        configuracao.save(
            update_fields=[
                "ultimo_nsu",
                "ultima_consulta_em",
                "ultima_mensagem",
                "atualizado_em",
            ]
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="CONSULTA_DISTRIBUICAO_DFE",
            descricao=(
                f"Consulta DF-e da filial {filial}: cursor {cursor_inicial or 'inicial'} "
                f"para {controle.ultimo_nsu or 'sem avanço'}; {criados} novo(s), "
                f"{atualizados} já conhecido(s). Nenhuma movimentação operacional foi criada."
            ),
            objeto_tipo="ControleDistribuicaoDFeFilial",
            objeto_id=str(controle.pk),
            ip=ip,
        )
    return {
        "controle": controle,
        "recebidos": len(lote["documentos"]),
        "criados": criados,
        "ja_conhecidos": atualizados,
        "eventos": eventos,
    }


def criar_entrada_rascunho_a_partir_dfe(documento, *, usuario, ip=None):
    """Encaminha manualmente um DF-e recebido para uma entrada em rascunho."""
    from apps.compras.services_xml import importar_xml_entrada

    with transaction.atomic():
        documento = DocumentoDFeRecebido.objects.select_for_update().select_related("empresa").get(pk=documento.pk)
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None and documento.empresa_id != empresa_id:
            raise ValidationError("Este documento DF-e não pertence à empresa do usuário.")
        if documento.entrada_compra_id or documento.status == StatusDFeRecebido.VINCULADO:
            raise ValidationError("Este DF-e já foi encaminhado para uma entrada de compra.")
        if not documento.xml_conteudo:
            raise ValidationError("O documento DF-e não possui XML disponível para importação.")

        entrada = importar_xml_entrada(documento.xml_conteudo.encode("utf-8"), usuario=usuario, ip=ip)
        documento.entrada_compra = entrada
        documento.status = StatusDFeRecebido.VINCULADO
        documento.save(update_fields=["entrada_compra", "status", "atualizado_em"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="DFE_ENCAMINHADO_PARA_ENTRADA",
            descricao=(
                f"DF-e {documento.chave_acesso} encaminhado manualmente para a entrada em rascunho {entrada.id}. "
                "Nenhum estoque ou financeiro foi movimentado nesta ação."
            ),
            objeto_tipo="DocumentoDFeRecebido",
            objeto_id=str(documento.pk),
            ip=ip,
        )
    return entrada


def ignorar_dfe_recebido(documento, *, usuario, motivo, ip=None):
    """Registra que um DF-e foi revisado e não seguirá para compras."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo para desconsiderar o DF-e.")

    with transaction.atomic():
        documento = DocumentoDFeRecebido.objects.select_for_update().get(pk=documento.pk)
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None and documento.empresa_id != empresa_id:
            raise ValidationError("Este documento DF-e não pertence à empresa do usuário.")
        if documento.entrada_compra_id or documento.status == StatusDFeRecebido.VINCULADO:
            raise ValidationError("Um DF-e já vinculado a uma entrada não pode ser desconsiderado.")
        if documento.status == StatusDFeRecebido.IGNORADO:
            raise ValidationError("Este DF-e já foi desconsiderado.")

        documento.status = StatusDFeRecebido.IGNORADO
        documento.save(update_fields=["status", "atualizado_em"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="DFE_DESCONSIDERADO",
            descricao=f"DF-e {documento.chave_acesso} desconsiderado. Motivo: {motivo}",
            objeto_tipo="DocumentoDFeRecebido",
            objeto_id=str(documento.pk),
            ip=ip,
        )
    return documento