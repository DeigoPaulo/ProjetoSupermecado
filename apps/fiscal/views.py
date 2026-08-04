import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import RELATORIOS, SISTEMA, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Filial
from apps.produtos.models import Produto
from apps.vendas.models import StatusVenda, Venda

from .adapters import diagnosticar_adaptador_sefaz
from .assinaturas import assinatura_local_disponivel
from .certificados import salvar_certificado_a1
from .escopo import (
    configuracoes_para_usuario,
    documentos_para_usuario,
    filiais_para_usuario,
    inutilizacoes_para_usuario,
    naturezas_para_usuario,
    series_para_usuario,
    vendas_para_usuario,
)
from .forms import ConfiguracaoFiscalForm, InutilizacaoNumeracaoFiscalForm, NaturezaOperacaoForm, SerieFiscalForm
from .fila import (
    configuracao_fila_fiscal,
    diagnostico_fila_fiscal,
    reagendar_documento_fiscal,
    retomar_consultas_documento_fiscal,
)
from .models import AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, InutilizacaoNumeracaoFiscal, NaturezaOperacao, SerieFiscal, StatusDocumentoFiscal, StatusInutilizacaoFiscal, TipoDocumentoFiscal
from .validacoes import diagnosticar_schemas_fiscais
from .qrcode_nfce import gerar_qrcode_data_uri, obter_url_qrcode_nfce
from .perfis_uf import pendencias_endpoints_nfce
from .services import (
    CSOSN_ICMS_SUPORTADOS,
    CST_ICMS_SUPORTADOS,
    ativar_contingencia_offline,
    cancelar_documento,
    capacidade_tributaria_fiscal,
    consultar_situacao_documento,
    filtro_pendencias_produto_fiscal,
    pendencias_preparacao_fiscal,
    pendencias_produto_fiscal,
    preparar_documento_venda,
    salvar_xml_documento,
    solicitar_inutilizacao_numeracao,
    transmitir_documento_simulado,
    transmitir_documento_sefaz,
)


def _diagnostico_prontidao_fiscal(user):
    configuracoes_qs = configuracoes_para_usuario(user, ConfiguracaoFiscal.objects.select_related("filial"))
    configuracoes = {config.filial_id: config for config in configuracoes_qs}
    series_nfce = {
        serie.filial_id: serie
        for serie in series_para_usuario(
            user,
            SerieFiscal.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True).select_related("filial"),
        )
    }
    naturezas_nfce = {}
    for natureza in naturezas_para_usuario(
        user,
        NaturezaOperacao.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True, padrao=True),
    ):
        naturezas_nfce.setdefault(natureza.empresa_id, natureza)
    regimes = list(configuracoes_qs.exclude(regime_tributario="").values_list("regime_tributario", flat=True))
    ufs = list(configuracoes_qs.exclude(filial__uf="").values_list("filial__uf", flat=True))
    crts = list(configuracoes_qs.values_list("crt", flat=True))
    filtro_produtos_pendentes = filtro_pendencias_produto_fiscal(regimes, ufs, crts)
    produtos_pendentes = Produto.all_objects.filter(filtro_produtos_pendentes).count()
    vendas_pendentes_qs = vendas_para_usuario(
        user, Venda.objects.filter(status=StatusVenda.FINALIZADA, documentos_fiscais__isnull=True)
    )
    documentos_base_qs = documentos_para_usuario(user)
    documentos_contingencia_qs = documentos_base_qs.filter(status=StatusDocumentoFiscal.CONTINGENCIA)
    contingencias_vencidas = documentos_contingencia_qs.filter(transmissao_limite_em__lt=timezone.now()).count()
    filiais = []
    alertas = []
    for filial in filiais_para_usuario(
        user, Filial.objects.select_related("empresa").order_by("empresa__nome_fantasia", "nome")
    ):
        config = configuracoes.get(filial.id)
        serie = series_nfce.get(filial.id)
        pendencias = []
        if not config:
            pendencias.append("Configuração fiscal ausente.")
        else:
            if not config.ativo:
                pendencias.append("Configuração fiscal inativa.")
            if config.certificado_status != "valido":
                pendencias.append(f"Certificado {config.certificado_status.replace('_', ' ')}.")
            if not config.csc_id or not config.csc_token:
                pendencias.append("CSC/Token NFC-e incompleto.")
            if not config.inscricao_estadual:
                pendencias.append("Inscrição estadual ausente.")
            pendencias.extend(pendencias_endpoints_nfce(filial, config))
        if not filial.uf or not filial.codigo_municipio_ibge:
            pendencias.append("UF ou código IBGE da filial ausente.")
        if not serie:
            pendencias.append("Série NFC-e ativa ausente.")
        if filial.empresa_id not in naturezas_nfce:
            pendencias.append("Natureza de operação NFC-e ativa ausente.")
        vendas_pendentes = vendas_pendentes_qs.filter(filial=filial).count()
        if vendas_pendentes:
            pendencias.append(f"{vendas_pendentes} venda(s) aguardando NFC-e.")
        status = "Pronta" if not pendencias else "Atenção"
        for pendencia in pendencias:
            alertas.append({"filial": str(filial), "mensagem": pendencia})
        filiais.append(
            {
                "id": filial.id,
                "filial": str(filial),
                "ambiente": config.get_ambiente_display() if config else "-",
                "certificado": config.certificado_status if config else "nao_configurado",
                "serie_nfce": serie.serie if serie else None,
                "proximo_numero": serie.proximo_numero if serie else None,
                "vendas_pendentes": vendas_pendentes,
                "contingencia_offline_permitida": bool(config and config.permite_contingencia_offline),
                "pendencias": pendencias,
                "status": status,
            }
        )
    producao_configs = [config for config in configuracoes.values() if config.ambiente == AmbienteFiscal.PRODUCAO]
    diagnostico_adapter = diagnosticar_adaptador_sefaz()
    diagnostico_schema = diagnosticar_schemas_fiscais()
    schema_disponivel = diagnostico_adapter["valida_schema"] or diagnostico_schema["pronto"]
    assinatura_local_pronta = bool(
        settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED
        and producao_configs
        and all(config.certificado_status == "valido" for config in producao_configs)
    )
    assinatura_disponivel = diagnostico_adapter["assina_xml"] or assinatura_local_pronta
    alertas_producao = []
    if producao_configs and not diagnostico_adapter["configurado"]:
        alertas_producao.append("Existe filial em produção fiscal, mas nenhum adaptador SEFAZ oficial foi configurado.")
    elif producao_configs and not diagnostico_adapter["carregavel"]:
        alertas_producao.append("O adaptador SEFAZ configurado não pôde ser carregado.")
    elif producao_configs and not assinatura_disponivel:
        alertas_producao.append("Não há assinatura XML disponível pelo adaptador nem por certificado A1 local válido.")
    elif producao_configs and not schema_disponivel:
        alertas_producao.append("Nenhum schema fiscal local válido ou validação XSD pelo adaptador está disponível.")
    if not producao_configs:
        alertas_producao.append("Nenhuma filial em produção fiscal; transmissão real permanece fora de uso.")

    producao = {
        "contrato": "fiscal_production_readiness_v1",
        "filiais_em_producao": len(producao_configs),
        "sefaz_adapter_configurado": diagnostico_adapter["configurado"],
        "sefaz_adapter_carregavel": diagnostico_adapter["carregavel"],
        "sefaz_adapter_assina_xml": diagnostico_adapter["assina_xml"],
        "assinatura_local_habilitada": settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED,
        "assinatura_local_pronta": assinatura_local_pronta,
        "assinatura_xml_disponivel": assinatura_disponivel,
        "sefaz_adapter_valida_schema": diagnostico_adapter["valida_schema"],
        "sefaz_adapter_consulta_documento": diagnostico_adapter["consulta_documento"],
        "schema_local_configurado": diagnostico_schema["configurado"],
        "schema_local_pronto": diagnostico_schema["pronto"],
        "schema_local_sha256": diagnostico_schema["sha256"],
        "transmissao_real_disponivel": bool(
            producao_configs and diagnostico_adapter["carregavel"] and assinatura_disponivel and schema_disponivel
        ),
        "homologacao_simulada_disponivel": True,
        "alertas": alertas_producao,
    }
    resumo = {
        "filiais": len(filiais),
        "filiais_prontas": sum(1 for filial in filiais if filial["status"] == "Pronta"),
        "alertas": len(alertas),
        "produtos_pendentes": produtos_pendentes,
        "vendas_pendentes": vendas_pendentes_qs.count(),
        "documentos_prontos": documentos_base_qs.filter(status=StatusDocumentoFiscal.PRONTO).count(),
        "documentos_rejeitados": documentos_base_qs.filter(status=StatusDocumentoFiscal.REJEITADO).count(),
        "documentos_em_contingencia": documentos_contingencia_qs.count(),
        "contingencias_com_prazo_vencido": contingencias_vencidas,
    }
    return {
        "contrato": "fiscal_readiness_v1",
        "resumo": resumo,
        "filiais": filiais,
        "alertas": alertas,
        "producao": producao,
        "capacidade_tributaria": capacidade_tributaria_fiscal(),
        "fila_transmissao": diagnostico_fila_fiscal(documentos_para_usuario(user)),
    }


@login_required
@role_required(*RELATORIOS)
def documentos(request):
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    documentos_qs = documentos_para_usuario(
        request.user,
        DocumentoFiscal.objects.select_related("filial", "venda", "pedido_online", "natureza_operacao", "usuario"),
    )
    if status:
        documentos_qs = documentos_qs.filter(status=status)
    if q:
        documentos_qs = documentos_qs.filter(numero__icontains=q)
    vendas_pendentes = list(
        vendas_para_usuario(
            request.user,
            Venda.objects.select_related("filial", "cliente", "usuario")
            .prefetch_related("itens__produto")
            .filter(status=StatusVenda.FINALIZADA, documentos_fiscais__isnull=True),
        ).order_by("-data")[:50]
    )
    configuracoes_qs = configuracoes_para_usuario(request.user)
    configuracoes_por_filial = {config.filial_id: config for config in configuracoes_qs}
    filiais_com_serie = set(
        series_para_usuario(
            request.user, SerieFiscal.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True)
        ).values_list("filial_id", flat=True)
    )
    naturezas_padrao = {}
    for natureza in naturezas_para_usuario(
        request.user,
        NaturezaOperacao.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True, padrao=True),
    ):
        naturezas_padrao.setdefault(natureza.empresa_id, natureza)
    for venda in vendas_pendentes:
        configuracao = configuracoes_por_filial.get(venda.filial_id)
        if not configuracao:
            pendencias = ["Configure os dados fiscais da filial."]
        elif not configuracao.ativo:
            pendencias = ["A configuração fiscal da filial está inativa."]
        else:
            pendencias = pendencias_preparacao_fiscal(
                venda,
                configuracao,
                naturezas_padrao.get(venda.filial.empresa_id),
            )
        if venda.filial_id not in filiais_com_serie:
            pendencias.append("Cadastre uma serie NFC-e ativa para a filial.")
        venda.pendencias_fiscais = pendencias
        venda.pronta_fiscal = not pendencias
    logs_pendencia = {}
    for log in LogAuditoria.objects.filter(
        modulo="fiscal",
        acao="PREPARA_DOCUMENTO_PENDENTE",
        objeto_tipo="Venda",
        objeto_id__in=[str(venda.id) for venda in vendas_pendentes],
    ).order_by("-criado_em"):
        logs_pendencia.setdefault(log.objeto_id, log)
    for venda in vendas_pendentes:
        venda.ultima_tentativa_fiscal = logs_pendencia.get(str(venda.id))
    pagina = Paginator(documentos_qs, 50).get_page(request.GET.get("page"))
    context = {
        "diagnostico": _diagnostico_prontidao_fiscal(request.user),
        "documentos": pagina,
        "page_obj": pagina,
        "status": status,
        "q": q,
        "status_choices": StatusDocumentoFiscal.choices,
        "vendas_pendentes": vendas_pendentes,
        "configuracoes": configuracoes_para_usuario(request.user, ConfiguracaoFiscal.objects.select_related("filial")),
        "series": series_para_usuario(request.user, SerieFiscal.objects.select_related("filial")),
        "naturezas": naturezas_para_usuario(
            request.user,
            NaturezaOperacao.objects.select_related("empresa"),
        ),
        "total_documentos": documentos_qs.count(),
        "pendentes": documentos_qs.filter(status="PRONTO").count(),
        "emitidos": documentos_qs.filter(status="EMITIDO").count(),
        "rejeitados": documentos_qs.filter(status="REJEITADO").count(),
        "em_contingencia": documentos_qs.filter(status=StatusDocumentoFiscal.CONTINGENCIA).count(),
        "pendencias_automaticas": len(logs_pendencia),
    }
    return render(request, "fiscal/documentos.html", context)


@login_required
@role_required(*SISTEMA)
def inutilizacoes(request):
    if request.method == "POST":
        form = InutilizacaoNumeracaoFiscalForm(request.POST, user=request.user)
        if form.is_valid():
            dados = form.cleaned_data
            try:
                solicitar_inutilizacao_numeracao(
                    filial=dados["filial"],
                    tipo_documento=dados["tipo_documento"],
                    ano=dados["ano"],
                    serie=dados["serie"],
                    numero_inicial=dados["numero_inicial"],
                    numero_final=dados["numero_final"],
                    justificativa=dados["justificativa"],
                    usuario=request.user,
                    ip=request.META.get("REMOTE_ADDR"),
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Faixa inutilizada e protocolada com sucesso.")
                return redirect("fiscal:inutilizacoes")
    else:
        form = InutilizacaoNumeracaoFiscalForm(
            user=request.user,
            initial={"ano": timezone.localdate().year},
        )

    status = request.GET.get("status", "")
    registros = inutilizacoes_para_usuario(
        request.user,
        InutilizacaoNumeracaoFiscal.objects.select_related("filial", "usuario"),
    )
    if status in StatusInutilizacaoFiscal.values:
        registros = registros.filter(status=status)
    pagina = Paginator(registros, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "fiscal/inutilizacoes.html",
        {
            "form": form,
            "inutilizacoes": pagina,
            "page_obj": pagina,
            "status": status,
            "status_choices": StatusInutilizacaoFiscal.choices,
            "diagnostico_adapter": diagnosticar_adaptador_sefaz(),
        },
    )


@login_required
@role_required(*RELATORIOS)
def diagnostico_json(request):
    return JsonResponse(_diagnostico_prontidao_fiscal(request.user))


@login_required
@role_required(*RELATORIOS)
def contingencia_json(request):
    status = request.GET.get("status", StatusDocumentoFiscal.PRONTO)
    filial_id = request.GET.get("filial")
    status_permitidos = {
        StatusDocumentoFiscal.PRONTO,
        StatusDocumentoFiscal.CONTINGENCIA,
        StatusDocumentoFiscal.REJEITADO,
        StatusDocumentoFiscal.CANCELADO,
    }
    if status not in status_permitidos:
        status = StatusDocumentoFiscal.PRONTO
    documentos_qs = documentos_para_usuario(
        request.user,
        DocumentoFiscal.objects.select_related(
            "filial",
            "filial__empresa",
            "venda",
            "pedido_online",
            "natureza_operacao",
        ),
    ).filter(status=status).order_by("criado_em")
    if filial_id:
        documentos_qs = documentos_qs.filter(filial_id=filial_id)
    documentos = list(documentos_qs[:200])
    itens = []
    for documento in documentos:
        if not documento.xml_conteudo and documento.status in {StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA}:
            salvar_xml_documento(documento)
        itens.append(
            {
                "id": documento.id,
                "tipo_documento": documento.tipo_documento,
                "ambiente": documento.ambiente,
                "filial": {
                    "id": documento.filial_id,
                    "nome": documento.filial.nome,
                    "cnpj": documento.filial.cnpj or documento.filial.empresa.cnpj,
                    "uf": documento.filial.uf,
                    "codigo_municipio_ibge": documento.filial.codigo_municipio_ibge,
                },
                "origem": {
                    "tipo": "venda" if documento.venda_id else "pedido_online" if documento.pedido_online_id else "manual",
                    "id": documento.venda_id or documento.pedido_online_id,
                },
                "serie": documento.serie,
                "numero": documento.numero,
                "status": documento.status,
                "valor_total": str(documento.valor_total),
                "chave_acesso": documento.chave_acesso,
                "protocolo": documento.protocolo,
                "natureza_operacao": documento.natureza_operacao.descricao if documento.natureza_operacao else "",
                "mensagem_retorno": documento.mensagem_retorno,
                "contingencia": {
                    "iniciada_em": timezone.localtime(documento.contingencia_iniciada_em).isoformat() if documento.contingencia_iniciada_em else None,
                    "justificativa": documento.contingencia_justificativa,
                    "transmissao_limite_em": timezone.localtime(documento.transmissao_limite_em).isoformat() if documento.transmissao_limite_em else None,
                    "tentativas_transmissao": documento.tentativas_transmissao,
                    "ultima_tentativa_em": timezone.localtime(documento.ultima_tentativa_em).isoformat() if documento.ultima_tentativa_em else None,
                },
                "xml": documento.xml_conteudo,
                "criado_em": timezone.localtime(documento.criado_em).isoformat(),
                "atualizado_em": timezone.localtime(documento.atualizado_em).isoformat(),
            }
        )
    payload = {
        "contrato": "fiscal_contingencia_v1",
        "gerado_em": timezone.localtime().isoformat(),
        "status": status,
        "filial_id": int(filial_id) if filial_id and filial_id.isdigit() else None,
        "total": len(itens),
        "limite": 200,
        "observacao": (
            "Exportacao operacional para contingência/suporte. "
            "Não substitui assinatura, autorização ou transmissao oficial pela SEFAZ."
        ),
        "documentos": itens,
    }
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="fiscal",
        acao="EXPORTA_CONTINGENCIA_FISCAL",
        descricao=f"Exportacao de contingencia fiscal gerada com {len(itens)} documento(s), status {status}.",
        objeto_tipo="DocumentoFiscal",
        objeto_id="contingencia",
        ip=request.META.get("REMOTE_ADDR"),
    )
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False, "indent": 2})


def _parametros_validacao_produtos_fiscais(user):
    configuracoes_qs = configuracoes_para_usuario(user)
    regimes = list(
        configuracoes_qs.exclude(regime_tributario="").values_list(
            "regime_tributario", flat=True
        )
    )
    crts = list(configuracoes_qs.values_list("crt", flat=True))
    ufs = list(
        configuracoes_qs.exclude(filial__uf="").values_list("filial__uf", flat=True)
    )
    pendente_q = filtro_pendencias_produto_fiscal(regimes, ufs, crts)
    return regimes, ufs, crts, pendente_q


def _filtrar_catalogo_fiscal(queryset, pendente_q, filtro):
    if filtro == "prontos":
        return queryset.exclude(pendente_q), "prontos"
    if filtro == "todos":
        return queryset, "todos"
    return queryset.filter(pendente_q), "pendentes"


def _decimal_csv(valor):
    return "" if valor is None else str(valor).replace(".", ",")


class _CSVBuffer:
    def write(self, valor):
        return valor


@login_required
@role_required(*RELATORIOS)
def produtos_fiscais_exportar_csv(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "pendentes")
    produtos_qs = Produto.all_objects.select_related("categoria").order_by("nome")
    if q:
        produtos_qs = produtos_qs.filter(
            Q(nome__icontains=q) | Q(codigo_barras__icontains=q)
        )
    _regimes, _ufs, _crts, pendente_q = _parametros_validacao_produtos_fiscais(
        request.user
    )
    produtos_qs, filtro = _filtrar_catalogo_fiscal(produtos_qs, pendente_q, filtro)
    total = produtos_qs.count()
    cabecalhos = [
        "codigo_barras",
        "codigo_interno",
        "nome",
        "categoria",
        "preco_venda",
        "ncm",
        "cest",
        "origem_mercadoria",
        "cst_icms",
        "csosn",
        "aliquota_icms",
        "reducao_base_icms",
        "aliquota_fcp",
        "codigo_beneficio_fiscal",
        "cst_pis",
        "aliquota_pis",
        "cst_cofins",
        "aliquota_cofins",
        "cst_ipi",
        "codigo_enquadramento_ipi",
        "aliquota_ipi",
        "cst_ibs_cbs",
        "classificacao_tributaria_ibs_cbs",
        "_modo_importacao",
    ]
    escritor = csv.writer(_CSVBuffer(), delimiter=";", lineterminator="\r\n")

    def linhas():
        yield "﻿"
        yield escritor.writerow(cabecalhos)
        for produto in produtos_qs.iterator(chunk_size=1000):
            yield escritor.writerow(
                [
                    produto.codigo_barras,
                    produto.codigo_interno,
                    produto.nome,
                    produto.categoria.nome,
                    _decimal_csv(produto.preco_venda),
                    produto.ncm,
                    produto.cest,
                    produto.origem_mercadoria,
                    produto.cst_icms,
                    produto.csosn,
                    _decimal_csv(produto.aliquota_icms),
                    _decimal_csv(produto.reducao_base_icms),
                    _decimal_csv(produto.aliquota_fcp),
                    produto.codigo_beneficio_fiscal,
                    produto.cst_pis,
                    _decimal_csv(produto.aliquota_pis),
                    produto.cst_cofins,
                    _decimal_csv(produto.aliquota_cofins),
                    produto.cst_ipi,
                    produto.codigo_enquadramento_ipi,
                    _decimal_csv(produto.aliquota_ipi),
                    produto.cst_ibs_cbs,
                    produto.classificacao_tributaria_ibs_cbs,
                    "fiscal",
                ]
            )

    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="fiscal",
        acao="EXPORTA_PRODUTOS_FISCAIS_CSV",
        descricao=(
            f"Exportacao fiscal de produtos: {total} registro(s), "
            f"filtro={filtro}, busca={q or '-'}."
        ),
        objeto_tipo="Produto",
        objeto_id="lote",
        ip=request.META.get("REMOTE_ADDR"),
    )
    response = StreamingHttpResponse(
        linhas(),
        content_type="text/csv; charset=utf-8",
    )
    data = timezone.localdate().strftime("%Y%m%d")
    response["Content-Disposition"] = (
        f'attachment; filename="produtos-fiscais-{filtro}-{data}.csv"'
    )
    return response


@login_required
@role_required(*RELATORIOS)
def produtos_fiscais(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "pendentes")
    produtos_qs = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
    if q:
        produtos_qs = produtos_qs.filter(Q(nome__icontains=q) | Q(codigo_barras__icontains=q))
    regimes, ufs, crts, pendente_q = _parametros_validacao_produtos_fiscais(
        request.user
    )
    total_analisados = produtos_qs.count()
    total_pendentes = produtos_qs.filter(pendente_q).count()
    produtos_qs, filtro = _filtrar_catalogo_fiscal(
        produtos_qs, pendente_q, filtro
    )
    pagina = Paginator(produtos_qs, 50).get_page(request.GET.get("page"))
    produtos = list(pagina.object_list)
    for produto in produtos:
        produto.pendencias_fiscais = pendencias_produto_fiscal(produto, regimes, ufs, crts)
        produto.pronto_fiscal = not produto.pendencias_fiscais
    context = {
        "produtos": produtos,
        "page_obj": pagina,
        "q": q,
        "filtro": filtro,
        "total_analisados": total_analisados,
        "total_pendentes": total_pendentes,
        "total_prontos": total_analisados - total_pendentes,
        "capacidade_tributaria": capacidade_tributaria_fiscal(),
    }
    return render(request, "fiscal/produtos_fiscais.html", context)


def _documento_com_dados(user, pk):
    queryset = DocumentoFiscal.objects.select_related(
        "filial__empresa",
        "venda__cliente",
        "venda__caixa",
        "pedido_online",
        "natureza_operacao",
        "usuario",
    ).prefetch_related("venda__itens__produto", "venda__pagamentos__forma_pagamento")
    return get_object_or_404(documentos_para_usuario(user, queryset), pk=pk)


@login_required
@role_required(*RELATORIOS)
def detalhe(request, pk):
    documento = _documento_com_dados(request.user, pk)
    diagnostico_adapter = diagnosticar_adaptador_sefaz()
    diagnostico_schema = diagnosticar_schemas_fiscais()
    try:
        configuracao_fiscal = documento.filial.configuracao_fiscal
    except ConfiguracaoFiscal.DoesNotExist:
        configuracao_fiscal = None
    assinatura_disponivel = diagnostico_adapter["assina_xml"] or assinatura_local_disponivel(configuracao_fiscal)
    sefaz_pronta = (
        diagnostico_adapter["carregavel"]
        and assinatura_disponivel
        and (diagnostico_adapter["valida_schema"] or diagnostico_schema["pronto"])
    )
    fila_configuracao = configuracao_fila_fiscal()
    return render(
        request,
        "fiscal/detalhe.html",
        {
            "documento": documento,
            "imprimir": False,
            "sefaz_adapter_configurado": sefaz_pronta,
            "sefaz_consulta_disponivel": diagnostico_adapter["consulta_documento"],
            "consulta_sefaz_esgotada": (
                documento.aguardando_consulta_sefaz
                and documento.tentativas_consulta_sefaz >= fila_configuracao["max_consultas"]
            ),
            "max_consultas_sefaz": fila_configuracao["max_consultas"],
            "sefaz_cancelamento_disponivel": (
                diagnostico_adapter["cancela_documento"]
                or (
                    documento.ambiente == AmbienteFiscal.HOMOLOGACAO
                    and documento.protocolo.startswith("HOM")
                )
            ),
        },
    )

def _contexto_danfe_nfce(documento):
    contexto = {"documento": documento, "qrcode_data_uri": "", "qrcode_erro": ""}
    if documento.status not in {StatusDocumentoFiscal.EMITIDO, StatusDocumentoFiscal.CONTINGENCIA}:
        contexto["qrcode_erro"] = "QR Code disponível somente apos autorização ou emissao em contingência."
        return contexto
    try:
        contexto["qrcode_url"] = obter_url_qrcode_nfce(documento)
        contexto["qrcode_data_uri"] = gerar_qrcode_data_uri(contexto["qrcode_url"])
    except (ValidationError, ConfiguracaoFiscal.DoesNotExist) as exc:
        contexto["qrcode_erro"] = "; ".join(getattr(exc, "messages", [str(exc)]))
    return contexto


@login_required
@role_required(*RELATORIOS)
def imprimir(request, pk):
    documento = _documento_com_dados(request.user, pk)
    if documento.tipo_documento == TipoDocumentoFiscal.NFCE:
        return render(request, "fiscal/danfe_nfce.html", _contexto_danfe_nfce(documento))
    return render(request, "fiscal/detalhe.html", {"documento": documento, "imprimir": True})


@login_required
@role_required(*RELATORIOS)
def baixar_xml(request, pk):
    documento = _documento_com_dados(request.user, pk)
    if not documento.xml_conteudo:
        salvar_xml_documento(documento)
    nome = f"nfce_{documento.serie}_{documento.numero or documento.pk}.xml"
    response = HttpResponse(documento.xml_conteudo, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    return response


@login_required
@role_required(*SISTEMA)
def configuracao_form(request, pk=None):
    configuracao = get_object_or_404(configuracoes_para_usuario(request.user), pk=pk) if pk else None
    if request.method == "POST":
        form = ConfiguracaoFiscalForm(request.POST, request.FILES, instance=configuracao, user=request.user)
        if form.is_valid():
            configuracao = form.save()
            arquivo = form.cleaned_data.get("certificado_arquivo")
            senha = form.cleaned_data.get("certificado_senha")
            if arquivo:
                try:
                    salvar_certificado_a1(configuracao, arquivo, senha)
                except ValidationError as exc:
                    form.add_error("certificado_arquivo", exc)
                    return render(request, "fiscal/form.html", {"form": form, "titulo": "Configuração fiscal"})
            messages.success(request, "Configuração fiscal salva.")
            return redirect("fiscal:documentos")
    else:
        form = ConfiguracaoFiscalForm(instance=configuracao, user=request.user)
    return render(request, "fiscal/form.html", {"form": form, "titulo": "Configuração fiscal"})


@login_required
@role_required(*SISTEMA)
def serie_form(request, pk=None):
    serie = get_object_or_404(series_para_usuario(request.user), pk=pk) if pk else None
    if request.method == "POST":
        form = SerieFiscalForm(request.POST, instance=serie, user=request.user)
        if form.is_valid():
            criando = serie is None
            serie = form.save()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="fiscal",
                acao="CRIA_SERIE_FISCAL" if criando else "ATUALIZA_SERIE_FISCAL",
                descricao=(
                    f"Serie fiscal {serie.serie} ({serie.get_tipo_documento_display()}) "
                    f"da filial {serie.filial} {'criada' if criando else 'atualizada'}."
                ),
                objeto_tipo="SerieFiscal",
                objeto_id=str(serie.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Serie fiscal salva.")
            return redirect("fiscal:documentos")
    else:
        form = SerieFiscalForm(instance=serie, user=request.user)
    return render(request, "fiscal/form.html", {"form": form, "titulo": "Serie fiscal"})


@login_required
@role_required(*SISTEMA)
def natureza_form(request, pk=None):
    natureza = get_object_or_404(naturezas_para_usuario(request.user), pk=pk) if pk else None
    if request.method == "POST":
        form = NaturezaOperacaoForm(request.POST, instance=natureza, user=request.user)
        if form.is_valid():
            criando = natureza is None
            natureza = form.save()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="fiscal",
                acao="CRIA_NATUREZA_OPERACAO" if criando else "ATUALIZA_NATUREZA_OPERACAO",
                descricao=(
                    f"Natureza de operacao {natureza.descricao} (CFOP {natureza.cfop}) "
                    f"{'criada' if criando else 'atualizada'}."
                ),
                objeto_tipo="NaturezaOperacao",
                objeto_id=str(natureza.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Natureza de operação salva.")
            return redirect("fiscal:documentos")
    else:
        form = NaturezaOperacaoForm(instance=natureza, user=request.user)
    return render(request, "fiscal/form.html", {"form": form, "titulo": "Natureza de operação"})


@login_required
@role_required(*SISTEMA)
@require_POST
def definir_natureza_padrao(request, pk):
    natureza = get_object_or_404(naturezas_para_usuario(request.user), pk=pk, ativo=True)
    if not natureza.padrao:
        natureza.padrao = True
        natureza.save(update_fields=["padrao"])
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="fiscal",
            acao="DEFINE_NATUREZA_PADRAO",
            descricao=(
                f"Natureza de operacao {natureza.descricao} definida como padrao "
                f"para {natureza.get_tipo_documento_display()} na empresa {natureza.empresa}."
            ),
            objeto_tipo="NaturezaOperacao",
            objeto_id=str(natureza.pk),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Natureza de operação definida como padrão.")
    return redirect("fiscal:documentos")


@login_required
@role_required(*SISTEMA)
def preparar_venda(request, venda_id):
    venda = get_object_or_404(vendas_para_usuario(request.user), pk=venda_id)
    try:
        preparar_documento_venda(venda, request.user, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Documento fiscal preparado para transmissao.")
    return redirect("fiscal:documentos")


@login_required
@role_required(*SISTEMA)
def ativar_contingencia(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        try:
            ativar_contingencia_offline(
                documento, request.user, request.POST.get("justificativa", ""), ip=request.META.get("REMOTE_ADDR")
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.warning(
                request,
                "NFC-e registrada em contingência offline. Transmita para a SEFAZ assim que a comunicacao voltar.",
            )
    return redirect("fiscal:detalhe", pk=pk)




@login_required
@role_required(*SISTEMA)
def cancelar(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        try:
            cancelar_documento(documento, request.user, request.POST.get("motivo", ""), ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Documento fiscal cancelado.")
    return redirect("fiscal:documentos")


@login_required
@role_required(*SISTEMA)
def reagendar_transmissao(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        try:
            reagendar_documento_fiscal(
                documento,
                request.user,
                request.POST.get("motivo", ""),
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Documento corrigido e recolocado na fila fiscal.")
    return redirect("fiscal:detalhe", pk=pk)


@login_required
@role_required(*SISTEMA)
@require_POST
def retomar_consultas_sefaz(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    try:
        retomar_consultas_documento_fiscal(
            documento,
            request.user,
            request.POST.get("motivo", ""),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Consultas automáticas à SEFAZ retomadas com segurança.")
    return redirect("fiscal:detalhe", pk=pk)


@login_required
@role_required(*SISTEMA)
def transmitir_simulado(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        try:
            transmitir_documento_simulado(documento, request.user, ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Documento fiscal transmitido em homologação simulada.")
    return redirect("fiscal:detalhe", pk=pk)



@login_required
@role_required(*SISTEMA)
@require_POST
def consultar_sefaz(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    try:
        documento, resultado = consultar_situacao_documento(
            documento,
            request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if resultado.status == "AUTORIZADO":
            messages.success(request, "A SEFAZ confirmou a autorização do documento.")
        elif resultado.status == "CANCELADO":
            messages.success(request, "A SEFAZ confirmou o cancelamento do documento.")
        elif resultado.status == "DENEGADO":
            messages.warning(request, "A SEFAZ informou uso denegado para este documento.")
        else:
            messages.warning(request, resultado.mensagem)
    return redirect("fiscal:detalhe", pk=pk)


@login_required
@role_required(*SISTEMA)
def transmitir_sefaz(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    if request.method == "POST":
        try:
            transmitir_documento_sefaz(documento, request.user, ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            documento.refresh_from_db()
            if documento.status == StatusDocumentoFiscal.EMITIDO:
                messages.success(request, "Documento autorizado pela SEFAZ.")
            elif documento.status == StatusDocumentoFiscal.REJEITADO:
                messages.error(request, f"Documento rejeitado pela SEFAZ: {documento.mensagem_retorno}")
            else:
                messages.warning(request, "Transmissao recebida pela SEFAZ e ainda pendente de retorno.")
    return redirect("fiscal:detalhe", pk=pk)
