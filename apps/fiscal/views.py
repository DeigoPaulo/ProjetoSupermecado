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

from apps.accounts.permissions import (
    ADMINISTRACAO,
    RELATORIOS,
    REVISAO_FISCAL,
    SISTEMA,
    role_required,
)
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Filial
from apps.produtos.models import Produto
from apps.vendas.models import StatusVenda, Venda

from .adapters import diagnosticar_adaptador_sefaz
from .dfe_adapters import diagnostico_adaptador_dfe
from .manifestacao_adapters import diagnostico_adaptador_manifestacao
from .cce_adapters import diagnostico_adaptador_cce
from .cadastro_adapters import diagnostico_adaptador_consulta_cadastro
from .assinaturas import assinatura_local_disponivel
from .certificados import salvar_certificado_a1
from .evidencias import verificar_integridade_evidencias
from .escopo import (
    configuracoes_para_usuario,
    documentos_dfe_recebidos_para_usuario,
    documentos_para_usuario,
    filiais_para_usuario,
    inutilizacoes_para_usuario,
    naturezas_para_usuario,
    rascunhos_devolucao_para_usuario,
    series_para_usuario,
    vendas_para_usuario,
)
from .forms import (
    ConfiguracaoFiscalForm,
    ImportarDFeRecebidoForm,
    HomologacaoFiscalForm,
    InutilizacaoNumeracaoFiscalForm,
    NaturezaOperacaoForm,
    SerieFiscalForm,
)
from .fila import (
    configuracao_fila_fiscal,
    diagnostico_fila_fiscal,
    reagendar_documento_fiscal,
    retomar_consultas_documento_fiscal,
)
from .models import (
    AlertaAtualizacaoFiscal,
    AmbienteFiscal,
    CartaCorrecaoFiscal,
    ConsultaCadastroContribuinte,
    ConfiguracaoFiscal,
    ControleDistribuicaoDFeFilial,
    DocumentoDFeRecebido,
    EventoDFeRecebido,
    DocumentoFiscal,
    DecisaoRevisaoDevolucaoFornecedor,
    DecisaoRevisaoMemoriaCalculoFornecedor,
    FonteAtualizacaoFiscal,
    HomologacaoFiscal,
    InutilizacaoNumeracaoFiscal,
    ManifestacaoDestinatario,
    NaturezaOperacao,
    ProvedorEmissaoFiscal,
    RascunhoDevolucaoFornecedor,
    SerieFiscal,
    StatusDFeRecebido,
    StatusDocumentoFiscal,
    StatusAlertaAtualizacaoFiscal,
    StatusFonteAtualizacaoFiscal,
    StatusHomologacaoFiscal,
    StatusInutilizacaoFiscal,
    StatusManifestacaoDestinatario,
    StatusRascunhoDevolucaoFornecedor,
    TipoDocumentoFiscal,
    TipoDocumentoConsultaCadastro,
    TipoManifestacaoDestinatario,
)
from .devolucao_fornecedor import (
    TRIBUTOS_MEMORIA_CALCULO,
    registrar_memoria_calculo_devolucao_fornecedor,
    registrar_parametrizacao_itens_devolucao_fornecedor,
    registrar_parecer_tributario_devolucao_fornecedor,
    revisar_memoria_calculo_devolucao_fornecedor,
    revisar_rascunho_devolucao_fornecedor,
)
from .monitor_atualizacoes import resumo_monitor_atualizacoes
from .services_cce import registrar_carta_correcao
from .services_cadastro import consultar_cadastro_contribuinte
from .validacoes import diagnosticar_schemas_fiscais
from .qrcode_nfce import gerar_qrcode_data_uri, obter_url_qrcode_nfce
from .readiness import diagnostico_prontidao_homologacao_goias
from .perfis_uf import pendencias_endpoints_nfce
from .services import (
    CSOSN_ICMS_SUPORTADOS,
    CST_ICMS_SUPORTADOS,
    ativar_contingencia_offline,
    ativar_contingencia_svc,
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


from .transporte_devolucao import TransporteDevolucaoForm, registrar_transporte
from .composicao_devolucao import ComposicaoDevolucaoForm, registrar_composicao
from .composicao_devolucao import RevisaoComposicaoForm, revisar_composicao
from .rateio_devolucao import RateioDevolucaoForm, registrar_rateio


def _rascunhos_revisao_queryset(user):
    return rascunhos_devolucao_para_usuario(
        user,
        RascunhoDevolucaoFornecedor.objects.select_related(
            "entrada_compra__fornecedor",
            "entrada_compra__filial",
            "submetido_por",
        ).prefetch_related(
            "itens__item_entrada__produto",
            "revisoes__revisor",
            "pareceres_tributarios__responsavel",
            "parametrizacoes_fiscais__responsavel",
            "parametrizacoes_fiscais__parecer",
            "parametrizacoes_fiscais__itens__item_rascunho__item_entrada__produto",
            "memorias_calculo__responsavel",
            "memorias_calculo__parametrizacao",
            "memorias_calculo__itens",
            "memorias_calculo__revisao_fiscal__revisor",
            "transportes__responsavel",
            "composicoes__responsavel",
            "composicoes__revisao__revisor",
            "composicoes__rateios__responsavel",
        ),
    )


@login_required
@role_required(*REVISAO_FISCAL)
def revisoes_devolucao_fornecedor(request):
    status = request.GET.get(
        "status", StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO
    )
    queryset = _rascunhos_revisao_queryset(request.user)
    if status != "TODOS":
        if status not in StatusRascunhoDevolucaoFornecedor.values:
            status = StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO
        queryset = queryset.filter(status=status)
    pagina = Paginator(queryset.order_by("submetido_em", "id"), 25).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "fiscal/revisoes_devolucao_fornecedor.html",
        {
            "pagina": pagina,
            "status_selecionado": status,
            "status_opcoes": StatusRascunhoDevolucaoFornecedor.choices,
        },
    )


@login_required
@role_required(*REVISAO_FISCAL)
def revisao_devolucao_fornecedor_detalhe(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    composicao_rateio = rascunho.composicoes.order_by("-versao").select_related("memoria", "revisao").first()
    rateio_form = None
    if (rascunho.status == "APROVADO" and composicao_rateio
        and getattr(composicao_rateio, "revisao", None)
        and composicao_rateio.revisao.decisao == "APROVAR"
        and not rascunho.memorias_calculo.filter(versao__gt=composicao_rateio.memoria.versao).exists()):
        rateio_form = RateioDevolucaoForm(itens=composicao_rateio.memoria.itens.order_by("item_rascunho_id"), totais=composicao_rateio.conteudo_snapshot["dados"])
    return render(
        request,
        "fiscal/revisao_devolucao_fornecedor_detalhe.html",
        {
            "rascunho": rascunho,
            "rateio_form": rateio_form,
            "composicao_rateio": composicao_rateio,
            "transporte_form": TransporteDevolucaoForm(),
            "composicao_form": ComposicaoDevolucaoForm(),
            "revisao_composicao_form": RevisaoComposicaoForm(),
            "ultima_composicao_id": rascunho.composicoes.order_by("-versao").values_list("pk", flat=True).first(),
            "decisao_aprovar": DecisaoRevisaoDevolucaoFornecedor.APROVAR,
            "decisao_corrigir": DecisaoRevisaoDevolucaoFornecedor.DEVOLVER_CORRECAO,
            "decisao_memoria_aprovar": DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
            "decisao_memoria_corrigir": DecisaoRevisaoMemoriaCalculoFornecedor.DEVOLVER_CORRECAO,
            "tributos_memoria": [
                {"chave": chave, "rotulo": rotulo}
                for chave, rotulo in TRIBUTOS_MEMORIA_CALCULO
            ],
            "ultima_memoria_id": rascunho.memorias_calculo.order_by("-versao")
            .values_list("pk", flat=True)
            .first(),
        },
    )


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def decidir_revisao_devolucao_fornecedor(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        revisao, rascunho = revisar_rascunho_devolucao_fornecedor(
            rascunho,
            decisao=request.POST.get("decisao"),
            justificativa=request.POST.get("justificativa"),
            revisor=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("fiscal:revisao_devolucao_detalhe", pk=rascunho.pk)

    if rascunho.status == StatusRascunhoDevolucaoFornecedor.APROVADO:
        messages.success(
            request,
            f"Revisão {revisao.sequencia} aprovada. A preparação continua sem autorização para emitir.",
        )
    else:
        messages.success(
            request,
            f"Revisão {revisao.sequencia} devolvida para correção em Compras.",
        )
    return redirect("fiscal:revisoes_devolucao")


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def registrar_parecer_devolucao_fornecedor(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        parecer, criado = registrar_parecer_tributario_devolucao_fornecedor(
            rascunho,
            dados=request.POST,
            responsavel=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if criado:
            messages.success(
                request,
                f"Parecer tributário versão {parecer.versao} registrado sem liberar emissão.",
            )
        else:
            messages.info(
                request,
                f"O mesmo conteúdo já está preservado na versão {parecer.versao}.",
            )
    return redirect("fiscal:revisao_devolucao_detalhe", pk=rascunho.pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def registrar_parametrizacao_devolucao_fornecedor(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        parametrizacao, criado = registrar_parametrizacao_itens_devolucao_fornecedor(
            rascunho,
            parecer_id=request.POST.get("parecer_id"),
            dados=request.POST,
            responsavel=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if criado:
            messages.success(
                request,
                f"Parâmetros por item versão {parametrizacao.versao} registrados sem calcular ou emitir.",
            )
        else:
            messages.info(
                request,
                f"O mesmo conteúdo já está preservado na versão {parametrizacao.versao}.",
            )
    return redirect("fiscal:revisao_devolucao_detalhe", pk=rascunho.pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def registrar_memoria_calculo_devolucao(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        memoria, criado = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=request.POST.get("parametrizacao_id"),
            dados=request.POST,
            responsavel=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if criado:
            messages.success(
                request,
                f"Memória de cálculo versão {memoria.versao} registrada com totais conferidos, sem emitir.",
            )
        else:
            messages.info(
                request,
                f"O mesmo conteúdo já está preservado na versão {memoria.versao}.",
            )
    return redirect("fiscal:revisao_devolucao_detalhe", pk=rascunho.pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def revisar_memoria_calculo_devolucao(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        revisao = revisar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            memoria_id=request.POST.get("memoria_id"),
            decisao=request.POST.get("decisao"),
            justificativa=request.POST.get("justificativa"),
            revisor=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if revisao.decisao == DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR:
            messages.success(
                request,
                f"Memória versão {revisao.memoria.versao} aprovada sem liberar XML ou emissão.",
            )
        else:
            messages.success(
                request,
                f"Memória versão {revisao.memoria.versao} devolvida; registre uma nova versão corrigida.",
            )
    return redirect("fiscal:revisao_devolucao_detalhe", pk=rascunho.pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def registrar_transporte_devolucao(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        ficha, criado = registrar_transporte(rascunho, dados=request.POST, responsavel=request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Transporte versão {ficha.versao}: " + ("registrado." if criado else "conteúdo já registrado."))
    return redirect("fiscal:revisao_devolucao_detalhe", pk=pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def registrar_composicao_devolucao(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        ficha, criado = registrar_composicao(rascunho, dados=request.POST, responsavel=request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Composição versão {ficha.versao}: " + ("registrada para conferência contábil." if criado else "conteúdo já registrado."))
    return redirect("fiscal:revisao_devolucao_detalhe", pk=pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def revisar_composicao_devolucao(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        revisao = revisar_composicao(rascunho, composicao_id=request.POST.get("composicao_id"), dados=request.POST, revisor=request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"{revisao.get_decisao_display()}. Decisão registrada; emissão continua bloqueada.")
    return redirect("fiscal:revisao_devolucao_detalhe", pk=pk)


@login_required
@role_required(*REVISAO_FISCAL)
@require_POST
def registrar_rateio_devolucao(request, pk):
    rascunho = get_object_or_404(_rascunhos_revisao_queryset(request.user), pk=pk)
    try:
        rateio, criado = registrar_rateio(rascunho, composicao_id=request.POST.get("composicao_id"), dados=request.POST, responsavel=request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Rateio versão {rateio.versao}: " + ("registrado; emissão continua bloqueada." if criado else "conteúdo já registrado."))
    return redirect("fiscal:revisao_devolucao_detalhe", pk=pk)


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
    exigir_ibs_cbs = any(config.ibs_cbs_exigido_em() for config in configuracoes.values())
    filtro_produtos_pendentes = filtro_pendencias_produto_fiscal(regimes, ufs, crts, exigir_ibs_cbs)
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
    producao_configs = [
        config
        for config in configuracoes.values()
        if config.ambiente == AmbienteFiscal.PRODUCAO
    ]
    diagnosticos_producao = [
        (config, diagnosticar_adaptador_sefaz(filial=config.filial))
        for config in producao_configs
    ]
    diagnosticos_adapter = [item[1] for item in diagnosticos_producao]
    if not diagnosticos_adapter:
        diagnosticos_adapter = [diagnosticar_adaptador_sefaz()]
    operacionais = [
        diagnostico["configuracao_operacional"]
        for diagnostico in diagnosticos_adapter
    ]
    adapters_configurados = all(
        diagnostico["configurado"] for diagnostico in diagnosticos_adapter
    )
    adapters_carregaveis = all(
        diagnostico["carregavel"] for diagnostico in diagnosticos_adapter
    )
    adapters_assinam_xml = all(
        diagnostico["assina_xml"] for diagnostico in diagnosticos_adapter
    )
    adapters_validam_schema = all(
        diagnostico["valida_schema"] for diagnostico in diagnosticos_adapter
    )
    adapters_consultam_documento = all(
        diagnostico["consulta_documento"] for diagnostico in diagnosticos_adapter
    )
    diagnostico_operacional_disponivel = all(
        operacional["diagnostico_disponivel"] for operacional in operacionais
    )
    configuracao_operacional_pronta = bool(
        diagnostico_operacional_disponivel
        and all(operacional["pronto"] for operacional in operacionais)
    )
    configuracao_operacional_bloqueada = any(
        operacional["diagnostico_disponivel"] and not operacional["pronto"]
        for operacional in operacionais
    )
    producao_operacional_bloqueada = any(
        operacional["diagnostico_disponivel"]
        and operacional["producao_habilitada"] is False
        for operacional in operacionais
    )
    if all(operacional["producao_habilitada"] is True for operacional in operacionais):
        producao_habilitada_adapter = True
    elif any(
        operacional["producao_habilitada"] is False
        for operacional in operacionais
    ):
        producao_habilitada_adapter = False
    else:
        producao_habilitada_adapter = None

    diagnostico_schema = diagnosticar_schemas_fiscais()
    schema_disponivel = all(
        diagnostico["valida_schema"] or diagnostico_schema["pronto"]
        for diagnostico in diagnosticos_adapter
    )
    assinatura_local_pronta = bool(
        settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED
        and producao_configs
        and all(config.certificado_status == "valido" for config in producao_configs)
    )
    assinatura_disponivel = bool(
        producao_configs
        and all(
            diagnostico["assina_xml"]
            or (
                settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED
                and config.certificado_status == "valido"
            )
            for config, diagnostico in diagnosticos_producao
        )
    )
    alertas_producao = []
    if producao_configs and not adapters_configurados:
        alertas_producao.append(
            "Existe filial em produção fiscal, mas nenhum adaptador SEFAZ oficial foi configurado."
        )
    elif producao_configs and not adapters_carregaveis:
        alertas_producao.append(
            "O adaptador SEFAZ configurado para uma ou mais filiais não pôde ser carregado."
        )
    elif producao_configs and configuracao_operacional_bloqueada:
        mensagens = {
            operacional["mensagem"]
            for operacional in operacionais
            if operacional["diagnostico_disponivel"] and not operacional["pronto"]
        }
        alertas_producao.extend(sorted(mensagens))
    elif producao_configs and producao_operacional_bloqueada:
        alertas_producao.append(
            "Produção fiscal permanece bloqueada na configuração do adaptador."
        )
    elif producao_configs and not assinatura_disponivel:
        alertas_producao.append(
            "Não há assinatura XML disponível pelo adaptador nem por certificado A1 local válido."
        )
    elif producao_configs and not schema_disponivel:
        alertas_producao.append(
            "Nenhum schema fiscal local válido ou validação XSD pelo adaptador está disponível."
        )
    if not producao_configs:
        alertas_producao.append(
            "Nenhuma filial em produção fiscal; transmissão real permanece fora de uso."
        )

    producao = {
        "contrato": "fiscal_production_readiness_v1",
        "filiais_em_producao": len(producao_configs),
        "sefaz_adapter_configurado": adapters_configurados,
        "sefaz_adapter_carregavel": adapters_carregaveis,
        "sefaz_adapter_assina_xml": adapters_assinam_xml,
        "sefaz_adapter_diagnostico_operacional": diagnostico_operacional_disponivel,
        "sefaz_adapter_configuracao_pronta": configuracao_operacional_pronta,
        "sefaz_adapter_producao_habilitada": producao_habilitada_adapter,
        "assinatura_local_habilitada": settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED,
        "assinatura_local_pronta": assinatura_local_pronta,
        "assinatura_xml_disponivel": assinatura_disponivel,
        "sefaz_adapter_valida_schema": adapters_validam_schema,
        "sefaz_adapter_consulta_documento": adapters_consultam_documento,
        "schema_local_configurado": diagnostico_schema["configurado"],
        "schema_local_pronto": diagnostico_schema["pronto"],
        "schema_local_sha256": diagnostico_schema["sha256"],
        "transmissao_real_disponivel": bool(
            producao_configs
            and adapters_carregaveis
            and not configuracao_operacional_bloqueada
            and not producao_operacional_bloqueada
            and assinatura_disponivel
            and schema_disponivel
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
        "capacidade_tributaria": capacidade_tributaria_fiscal(configuracoes.values()),
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
        "monitor_atualizacoes": resumo_monitor_atualizacoes(),
    }
    return render(request, "fiscal/documentos.html", context)


@login_required
@role_required(*ADMINISTRACAO)
def atualizacoes_fiscais(request):
    status = request.GET.get("status", StatusAlertaAtualizacaoFiscal.NOVO)
    fonte_id = request.GET.get("fonte", "")
    q = request.GET.get("q", "").strip()
    alertas = AlertaAtualizacaoFiscal.objects.select_related("fonte", "revisado_por")
    if status:
        alertas = alertas.filter(status=status)
    if fonte_id.isdigit():
        alertas = alertas.filter(fonte_id=fonte_id)
    if q:
        alertas = alertas.filter(Q(titulo__icontains=q) | Q(fonte__nome__icontains=q))
    pagina = Paginator(alertas, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "fiscal/atualizacoes.html",
        {
            "alertas": pagina,
            "page_obj": pagina,
            "fontes": FonteAtualizacaoFiscal.objects.all(),
            "status": status,
            "fonte_id": fonte_id,
            "q": q,
            "status_choices": StatusAlertaAtualizacaoFiscal.choices,
            "resumo_monitor": resumo_monitor_atualizacoes(),
        },
    )


@login_required
@role_required(*ADMINISTRACAO)
@require_POST
def revisar_atualizacao_fiscal(request, pk):
    alerta = get_object_or_404(AlertaAtualizacaoFiscal, pk=pk)
    novo_status = request.POST.get("status", "")
    permitidos = {
        StatusAlertaAtualizacaoFiscal.REVISADO,
        StatusAlertaAtualizacaoFiscal.IGNORADO,
    }
    if novo_status not in permitidos:
        messages.error(request, "Situação de revisão inválida.")
        return redirect("fiscal:atualizacoes")
    alerta.status = novo_status
    alerta.revisado_em = timezone.now()
    alerta.revisado_por = request.user
    alerta.save(update_fields=["status", "revisado_em", "revisado_por"])
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="fiscal",
        acao="REVISA_ATUALIZACAO_FISCAL",
        descricao=f"Alerta fiscal marcado como {alerta.get_status_display()}.",
        objeto_tipo="AlertaAtualizacaoFiscal",
        objeto_id=str(alerta.pk),
    )
    messages.success(request, "Alerta fiscal revisado com sucesso.")
    return redirect("fiscal:atualizacoes")


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
                    "prazo_vencido": documento.contingencia_prazo_vencido,
                    "aguardando_consulta_sefaz": documento.aguardando_consulta_sefaz,
                    "tentativas_consulta_sefaz": documento.tentativas_consulta_sefaz,
                    "confirmacoes_nao_localizado": documento.confirmacoes_nao_localizado,
                    "confirmacoes_exigidas": max(
                        2,
                        int(
                            getattr(
                                settings,
                                "FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS",
                                2,
                            )
                        ),
                    ),
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
    exigir_ibs_cbs = any(config.ibs_cbs_exigido_em() for config in configuracoes_qs)
    pendente_q = filtro_pendencias_produto_fiscal(regimes, ufs, crts, exigir_ibs_cbs)
    return regimes, ufs, crts, exigir_ibs_cbs, pendente_q


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
    _regimes, _ufs, _crts, _exigir_ibs_cbs, pendente_q = _parametros_validacao_produtos_fiscais(
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
    regimes, ufs, crts, exigir_ibs_cbs, pendente_q = _parametros_validacao_produtos_fiscais(
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
        produto.pendencias_fiscais = pendencias_produto_fiscal(produto, regimes, ufs, crts, exigir_ibs_cbs)
        produto.pronto_fiscal = not produto.pendencias_fiscais
    context = {
        "produtos": produtos,
        "page_obj": pagina,
        "q": q,
        "filtro": filtro,
        "total_analisados": total_analisados,
        "total_pendentes": total_pendentes,
        "total_prontos": total_analisados - total_pendentes,
        "capacidade_tributaria": capacidade_tributaria_fiscal(
            configuracoes_para_usuario(request.user, ConfiguracaoFiscal.objects.all())
        ),
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
    diagnostico_adapter = diagnosticar_adaptador_sefaz(filial=documento.filial)
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
    cartas_correcao = documento.cartas_correcao.select_related("usuario").all()
    diagnostico_cce = diagnostico_adaptador_cce()
    integridade_evidencias = (
        verificar_integridade_evidencias(documento)
        if request.user.is_superuser
        else None
    )
    svc_visivel_master = bool(
        request.user.is_superuser
        and documento.tipo_documento == TipoDocumentoFiscal.NFE
        and documento.filial.uf == "GO"
        and documento.status == StatusDocumentoFiscal.PRONTO
        and configuracao_fiscal
        and configuracao_fiscal.provedor_emissao
        == ProvedorEmissaoFiscal.SEFAZ_DIRETA_GO
    )
    svc_documento_ativo = bool(
        documento.tipo_documento == TipoDocumentoFiscal.NFE
        and documento.contingencia_iniciada_em
        and len(documento.chave_acesso) == 44
        and documento.chave_acesso[34] == "7"
    )
    svc_transmissao_disponivel = bool(
        request.user.is_superuser
        and svc_documento_ativo
        and getattr(settings, "SEFAZ_DIRETA_SVC_ENABLED", False)
        and diagnostico_adapter["configuracao_operacional"].get("rede_habilitada")
        is True
        and sefaz_pronta
    )
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
            "cartas_correcao": cartas_correcao,
            "cce_disponivel": diagnostico_cce["disponivel"],
            "cce_diagnostico": diagnostico_cce,
            "integridade_evidencias": integridade_evidencias,
            "svc_visivel_master": svc_visivel_master,
            "svc_documento_ativo": svc_documento_ativo,
            "svc_transmissao_disponivel": svc_transmissao_disponivel,
            "svc_habilitada": bool(
                getattr(settings, "SEFAZ_DIRETA_SVC_ENABLED", False)
            ),
            "cce_pode_registrar": (
                documento.tipo_documento == TipoDocumentoFiscal.NFE
                and documento.status == StatusDocumentoFiscal.EMITIDO
                and cartas_correcao.count() < 20
            ),
        },
    )

@login_required
@role_required(*SISTEMA)
def consulta_cadastro(request):
    filiais = filiais_para_usuario(
        request.user,
        Filial.objects.select_related("empresa").order_by(
            "empresa__nome_fantasia", "nome"
        ),
    )
    consultas = ConsultaCadastroContribuinte.objects.select_related(
        "filial__empresa", "usuario"
    ).filter(filial__in=filiais)
    q = request.GET.get("q", "").strip()
    if q:
        consultas = consultas.filter(
            Q(documento__icontains=q)
            | Q(filial__nome__icontains=q)
            | Q(filial__empresa__nome_fantasia__icontains=q)
        )

    if request.method == "POST":
        filial = get_object_or_404(filiais, pk=request.POST.get("filial"))
        try:
            consulta = consultar_cadastro_contribuinte(
                filial=filial,
                uf=request.POST.get("uf") or filial.uf,
                tipo_documento=request.POST.get("tipo_documento"),
                documento=request.POST.get("documento"),
                usuario=request.user,
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"Consulta cadastral concluída: {consulta.get_status_display()}.",
            )
            return redirect(f"{request.path}?resultado={consulta.pk}")

    pagina = Paginator(consultas, 50).get_page(request.GET.get("page"))
    selecionada = None
    resultado_id = request.GET.get("resultado")
    if resultado_id:
        selecionada = consultas.filter(pk=resultado_id).first()
    return render(
        request,
        "fiscal/consulta_cadastro.html",
        {
            "filiais": filiais,
            "pagina": pagina,
            "page_obj": pagina,
            "selecionada": selecionada,
            "q": q,
            "tipos_documento": TipoDocumentoConsultaCadastro.choices,
            "diagnostico": diagnostico_adaptador_consulta_cadastro(),
        },
    )


@login_required
@role_required(*SISTEMA)
def baixar_xml_consulta_cadastro(request, pk, direcao):
    filiais = filiais_para_usuario(request.user)
    consulta = get_object_or_404(
        ConsultaCadastroContribuinte.objects.filter(filial__in=filiais), pk=pk
    )
    if direcao not in {"envio", "retorno"}:
        return HttpResponse(status=404)
    conteudo = consulta.xml_envio if direcao == "envio" else consulta.xml_retorno
    if not conteudo:
        messages.error(request, "O XML solicitado ainda não está disponível.")
        return redirect("fiscal:consulta_cadastro")
    resposta = HttpResponse(conteudo, content_type="application/xml; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="consulta-cadastro-{consulta.pk}-{direcao}.xml"'
    )
    return resposta

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


def _checklist_homologacao_goias(configuracao):
    return diagnostico_prontidao_homologacao_goias(configuracao)["checklist"]


@login_required
@role_required(*SISTEMA)
def homologacao_goias(request, pk):
    configuracao = get_object_or_404(
        configuracoes_para_usuario(request.user, ConfiguracaoFiscal.objects.select_related("filial__empresa")),
        pk=pk,
    )
    if configuracao.filial.uf != "GO":
        messages.error(request, "O roteiro técnico atual está disponível somente para filiais de Goiás.")
        return redirect("fiscal:documentos")

    homologacao, _ = HomologacaoFiscal.objects.get_or_create(configuracao=configuracao)
    checklist = _checklist_homologacao_goias(configuracao)
    itens_automaticos_prontos = all(item["pronto"] for item in checklist)
    if request.method == "POST":
        form = HomologacaoFiscalForm(request.POST, instance=homologacao)
        if form.is_valid():
            if form.cleaned_data["status"] == StatusHomologacaoFiscal.CONCLUIDA and not itens_automaticos_prontos:
                form.add_error("status", "Conclua os itens técnicos automáticos antes de encerrar a homologação.")
            else:
                homologacao = form.save(commit=False)
                if homologacao.status == StatusHomologacaoFiscal.CONCLUIDA:
                    homologacao.concluida_em = timezone.now()
                    homologacao.concluida_por = request.user
                else:
                    homologacao.concluida_em = None
                    homologacao.concluida_por = None
                homologacao.save()
                LogAuditoria.objects.create(
                    usuario=request.user,
                    modulo="fiscal",
                    acao="ATUALIZA_HOMOLOGACAO_GOIAS",
                    descricao=f"Homologação técnica de Goiás da filial {configuracao.filial} atualizada para {homologacao.get_status_display()}.",
                    objeto_tipo="HomologacaoFiscal",
                    objeto_id=str(homologacao.pk),
                    ip=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, "Roteiro de homologação técnica atualizado.")
                return redirect("fiscal:homologacao_goias", pk=configuracao.pk)
    else:
        form = HomologacaoFiscalForm(instance=homologacao)
    return render(request, "fiscal/homologacao_goias.html", {
        "configuracao": configuracao,
        "homologacao": homologacao,
        "form": form,
        "checklist": checklist,
        "itens_automaticos_prontos": itens_automaticos_prontos,
    })

@login_required
@role_required(*SISTEMA)
def dfe_recebidos(request):
    form = ImportarDFeRecebidoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        from .services_dfe import registrar_xml_dfe_recebido
        try:
            documento, criado = registrar_xml_dfe_recebido(
                form.cleaned_data["arquivo_xml"].read(), usuario=request.user, ip=request.META.get("REMOTE_ADDR")
            )
        except ValidationError as exc:
            form.add_error("arquivo_xml", exc)
        else:
            messages.success(
                request,
                "NF-e recebida armazenada na caixa DF-e." if criado else "Esta NF-e já estava armazenada na caixa DF-e.",
            )
            return redirect("fiscal:dfe_recebidos")

    documentos = documentos_dfe_recebidos_para_usuario(
        request.user, DocumentoDFeRecebido.objects.select_related("empresa", "filial_destino")
    )
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    if status:
        documentos = documentos.filter(status=status)
    if q:
        documentos = documentos.filter(
            Q(chave_acesso__icontains=q) | Q(numero_documento__icontains=q)
            | Q(emitente_nome__icontains=q) | Q(emitente_cnpj__icontains=q)
        )
    pagina = Paginator(documentos, 50).get_page(request.GET.get("page"))
    filiais = list(
        filiais_para_usuario(
            request.user,
            Filial.objects.filter(is_active=True).select_related("empresa"),
        ).order_by("empresa__nome_fantasia", "nome")
    )
    controles = {
        controle.filial_id: controle
        for controle in ControleDistribuicaoDFeFilial.objects.filter(
            filial_id__in=[filial.pk for filial in filiais]
        ).select_related("filial")
    }
    agora = timezone.now()
    linhas_distribuicao = [
        {
            "filial": filial,
            "controle": controles.get(filial.pk),
            "em_espera": bool(
                controles.get(filial.pk)
                and controles[filial.pk].proxima_consulta_em
                and controles[filial.pk].proxima_consulta_em > agora
            ),
        }
        for filial in filiais
    ]
    eventos = EventoDFeRecebido.objects.filter(
        filial_destino_id__in=[filial.pk for filial in filiais]
    ).select_related("filial_destino").order_by("-recebido_em")
    diagnostico_dfe = diagnostico_adaptador_dfe()
    return render(request, "fiscal/dfe_recebidos.html", {
        "form": form, "documentos": pagina, "page_obj": pagina, "status": status, "q": q,
        "status_choices": StatusDFeRecebido.choices, "total": documentos.count(),
        "com_xml": documentos.filter(status=StatusDFeRecebido.XML_DISPONIVEL).count(),
        "linhas_distribuicao": linhas_distribuicao,
        "diagnostico_dfe": diagnostico_dfe,
        "eventos_dfe": eventos[:20],
        "total_eventos": eventos.count(),
    })


@login_required
@role_required(*SISTEMA)
@require_POST
def dfe_consultar_distribuicao(request):
    filial = get_object_or_404(
        filiais_para_usuario(
            request.user,
            Filial.objects.filter(is_active=True).select_related("empresa"),
        ),
        pk=request.POST.get("filial"),
    )
    from .services_dfe import consultar_distribuicao_dfe

    try:
        resultado = consultar_distribuicao_dfe(
            filial=filial,
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request,
            (
                f"Consulta de {filial} concluída: {resultado['recebidos']} registro(s), "
                f"{resultado['criados']} novo(s), {resultado['ja_conhecidos']} já conhecido(s) "
                f"e {resultado['eventos']} evento(s) fiscal(is)."
            ),
        )
    return redirect("fiscal:dfe_recebidos")


@login_required
@role_required(*SISTEMA)
def dfe_evento_baixar_xml(request, pk):
    filiais = filiais_para_usuario(request.user, Filial.objects.filter(is_active=True))
    evento = get_object_or_404(
        EventoDFeRecebido.objects.filter(filial_destino_id__in=filiais.values("pk")),
        pk=pk,
    )
    resposta = HttpResponse(evento.xml_conteudo, content_type="application/xml; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="evento-dfe-{evento.nsu}.xml"'
    return resposta


@login_required
@role_required(*SISTEMA)
def dfe_detalhe(request, pk):
    documento = get_object_or_404(
        documentos_dfe_recebidos_para_usuario(request.user).select_related("empresa", "filial_destino", "entrada_compra"),
        pk=pk,
    )
    manifestacoes = documento.manifestacoes_destinatario.select_related("usuario")
    conclusiva = manifestacoes.filter(
        status=StatusManifestacaoDestinatario.AUTORIZADA,
        tipo__in=[
            TipoManifestacaoDestinatario.CONFIRMACAO,
            TipoManifestacaoDestinatario.DESCONHECIMENTO,
            TipoManifestacaoDestinatario.OPERACAO_NAO_REALIZADA,
        ],
    ).first()
    return render(request, "fiscal/dfe_detalhe.html", {
        "documento": documento,
        "manifestacoes": manifestacoes,
        "manifestacao_conclusiva": conclusiva,
        "tipos_manifestacao": TipoManifestacaoDestinatario.choices,
        "diagnostico_manifestacao": diagnostico_adaptador_manifestacao(),
    })


@login_required
@role_required(*SISTEMA)
@require_POST
def dfe_manifestar(request, pk):
    documento = get_object_or_404(
        documentos_dfe_recebidos_para_usuario(request.user).select_related(
            "empresa", "filial_destino"
        ),
        pk=pk,
    )
    from .services_manifestacao import registrar_manifestacao_destinatario

    try:
        manifestacao = registrar_manifestacao_destinatario(
            documento,
            tipo=request.POST.get("tipo"),
            justificativa=request.POST.get("justificativa"),
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request,
            f"{manifestacao.get_tipo_display()}: {manifestacao.get_status_display()}. "
            f"{manifestacao.mensagem}",
        )
    return redirect("fiscal:dfe_detalhe", pk=documento.pk)


@login_required
@role_required(*SISTEMA)
def dfe_manifestacao_baixar_xml(request, pk, direcao):
    filiais = filiais_para_usuario(request.user, Filial.objects.filter(is_active=True))
    manifestacao = get_object_or_404(
        ManifestacaoDestinatario.objects.filter(filial_id__in=filiais.values("pk")), pk=pk
    )
    if direcao not in {"envio", "retorno"}:
        return HttpResponse("Direção inválida.", status=404, content_type="text/plain; charset=utf-8")
    conteudo = manifestacao.xml_envio if direcao == "envio" else manifestacao.xml_retorno
    if not conteudo:
        return HttpResponse("XML não disponível.", status=404, content_type="text/plain; charset=utf-8")
    resposta = HttpResponse(conteudo, content_type="application/xml; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="manifestacao-{manifestacao.pk}-{direcao}.xml"'
    return resposta


@login_required
@role_required(*SISTEMA)
def dfe_baixar_xml(request, pk):
    documento = get_object_or_404(documentos_dfe_recebidos_para_usuario(request.user), pk=pk)
    if not documento.xml_conteudo:
        return HttpResponse("XML não disponível.", status=404, content_type="text/plain; charset=utf-8")
    resposta = HttpResponse(documento.xml_conteudo, content_type="application/xml; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="dfe-{documento.chave_acesso}.xml"'
    return resposta
@login_required
@role_required(*SISTEMA)
@require_POST
def dfe_ignorar(request, pk):
    documento = get_object_or_404(documentos_dfe_recebidos_para_usuario(request.user), pk=pk)
    from .services_dfe import ignorar_dfe_recebido

    try:
        ignorar_dfe_recebido(
            documento,
            usuario=request.user,
            motivo=request.POST.get("motivo"),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "DF-e desconsiderado e registrado na auditoria.")
    return redirect("fiscal:dfe_detalhe", pk=documento.pk)
@login_required
@role_required(*SISTEMA)
@require_POST
def dfe_criar_entrada(request, pk):
    documento = get_object_or_404(documentos_dfe_recebidos_para_usuario(request.user), pk=pk)
    from .services_dfe import criar_entrada_rascunho_a_partir_dfe

    try:
        entrada = criar_entrada_rascunho_a_partir_dfe(
            documento, usuario=request.user, ip=request.META.get("REMOTE_ADDR")
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("fiscal:dfe_recebidos")
    messages.success(request, f"DF-e encaminhado para a entrada em rascunho #{entrada.id}. Revise antes de finalizar.")
    return redirect("compras:detalhe", pk=entrada.pk)

@login_required
@role_required(*SISTEMA)
def configuracao_form(request, pk=None):
    configuracao = (
        get_object_or_404(configuracoes_para_usuario(request.user), pk=pk)
        if pk
        else None
    )
    provedor_anterior = configuracao.provedor_emissao if configuracao else ""
    if request.method == "POST":
        form = ConfiguracaoFiscalForm(
            request.POST,
            request.FILES,
            instance=configuracao,
            user=request.user,
        )
        if form.is_valid():
            configuracao = form.save()
            arquivo = form.cleaned_data.get("certificado_arquivo")
            senha = form.cleaned_data.get("certificado_senha")
            if (
                request.user.is_superuser
                and provedor_anterior != configuracao.provedor_emissao
            ):
                LogAuditoria.objects.create(
                    usuario=request.user,
                    modulo="fiscal",
                    acao="ALTERA_CANAL_EMISSAO_FISCAL",
                    descricao=(
                        f"Canal técnico de emissão da filial {configuracao.filial} "
                        f"alterado de {provedor_anterior or 'não definido'} para "
                        f"{configuracao.get_provedor_emissao_display()}."
                    ),
                    objeto_tipo="ConfiguracaoFiscal",
                    objeto_id=str(configuracao.pk),
                    ip=request.META.get("REMOTE_ADDR"),
                )
            if arquivo:
                try:
                    salvar_certificado_a1(configuracao, arquivo, senha)
                except ValidationError as exc:
                    form.add_error("certificado_arquivo", exc)
                    return render(
                        request,
                        "fiscal/form.html",
                        {"form": form, "titulo": "Configuração fiscal"},
                    )
            messages.success(request, "Configuração fiscal salva.")
            return redirect("fiscal:documentos")
    else:
        form = ConfiguracaoFiscalForm(
            instance=configuracao,
            user=request.user,
        )
    return render(
        request,
        "fiscal/form.html",
        {"form": form, "titulo": "Configuração fiscal"},
    )

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
@require_POST
def ativar_svc(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    try:
        ativar_contingencia_svc(
            documento,
            request.user,
            request.POST.get("justificativa", ""),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.warning(
            request,
            "NF-e preparada para contingência SVC-RS. Ela ainda precisa ser autorizada pela SEFAZ.",
        )
    return redirect("fiscal:detalhe", pk=pk)


@login_required
@role_required(*SISTEMA)
@require_POST
def registrar_cce(request, pk):
    documento = get_object_or_404(documentos_para_usuario(request.user), pk=pk)
    try:
        carta = registrar_carta_correcao(
            documento,
            correcao=request.POST.get("correcao", ""),
            confirmou_limites=request.POST.get("confirmou_limites") == "on",
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            f"Carta de Correção #{carta.sequencia}: {carta.get_status_display()}.",
        )
    return redirect("fiscal:detalhe", pk=pk)


@login_required
@role_required(*RELATORIOS)
def baixar_xml_cce(request, pk, direcao):
    carta = get_object_or_404(
        CartaCorrecaoFiscal.objects.select_related("documento", "empresa"),
        pk=pk,
        documento__in=documentos_para_usuario(request.user),
    )
    if direcao not in {"envio", "retorno"}:
        return HttpResponse(status=404)
    conteudo = carta.xml_envio if direcao == "envio" else carta.xml_retorno
    if not conteudo:
        messages.error(request, "O XML solicitado ainda não está disponível.")
        return redirect("fiscal:detalhe", pk=carta.documento_id)
    resposta = HttpResponse(conteudo, content_type="application/xml; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="cce-{carta.documento_id}-{carta.sequencia}-{direcao}.xml"'
    )
    return resposta


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
