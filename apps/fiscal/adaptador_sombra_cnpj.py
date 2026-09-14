"""Observador somente leitura do portao de CNPJ, sem efeito no fluxo operacional."""

from .portao_leitura_dupla_cnpj import resolver_cnpj_por_leitura_dupla


CONTRATO_ADAPTADOR_SOMBRA_CNPJ = "alphanumeric_cnpj_company_branch_shadow_adapter_v1"


def _comparar_resultados(fronteira, legado_id, resultado_portao):
    legado_encontrou = legado_id is not None
    portao_encontrou = resultado_portao["status"] == "ENCONTRADO_UNICO"
    mesma_identidade = (
        legado_encontrou
        and portao_encontrou
        and str(legado_id) == resultado_portao["identificador"]
    )
    if resultado_portao["status"] == "AMBIGUO":
        classificacao = "AMBIGUIDADE_CANONICA"
    elif legado_encontrou and portao_encontrou:
        classificacao = "CONCORDAM" if mesma_identidade else "IDENTIDADES_DIVERGENTES"
    elif legado_encontrou:
        classificacao = "LEGADO_SELECIONA_PORTAO_RECUSA"
    elif portao_encontrou:
        classificacao = "CANONICO_ENCONTRA_LEGADO_NAO"
    else:
        classificacao = "AMBOS_NAO_SELECIONAM"
    return {
        "contrato": CONTRATO_ADAPTADOR_SOMBRA_CNPJ,
        "fronteira": fronteira,
        "classificacao": classificacao,
        "legado_encontrou": legado_encontrou,
        "portao_status": resultado_portao["status"],
        "portao_encontrou": portao_encontrou,
        "mesma_identidade": mesma_identidade,
        "consulta": resultado_portao["consulta"],
        "diagnostico": resultado_portao["diagnostico"],
        "seguranca": {
            "somente_select": True,
            "altera_dados": False,
            "identificador_interno_exposto": False,
            "cnpj_completo_exposto": False,
            "substitui_busca_atual": False,
            "resultado_operacional_alterado": False,
            "consulta_credenciais": False,
            "libera_licenca": False,
            "libera_emissao": False,
        },
    }


def observar_busca_empresa_ativa_por_cnpj(valor_consulta):
    """Compara a busca exata atual de Empresa ativa com o portao, sem decidir por ela."""
    from apps.empresas.models import Empresa

    legado_id = (
        Empresa.objects.filter(cnpj=valor_consulta, is_active=True)
        .values_list("pk", flat=True)
        .first()
    )
    registros = [
        {
            "origem": "Empresa",
            "identificador": pk,
            "empresa_id": "",
            "fronteira": "EMPRESA",
            "valor": cnpj,
        }
        for pk, cnpj in (
            Empresa.objects.filter(is_active=True).order_by("pk").values_list("pk", "cnpj")
        )
    ]
    portao = resolver_cnpj_por_leitura_dupla(
        valor_consulta, registros, fronteira="EMPRESA"
    )
    return _comparar_resultados("EMPRESA", legado_id, portao)


def observar_busca_filial_da_empresa_por_cnpj(valor_consulta, *, empresa_id):
    """Compara a busca exata atual de Filial escopada, sem decidir por ela."""
    from apps.empresas.models import Filial

    if not str(empresa_id or ""):
        portao = resolver_cnpj_por_leitura_dupla(
            valor_consulta, [], fronteira="FILIAL", empresa_id=None
        )
        portao["status"] = "ESCOPO_EMPRESA_OBRIGATORIO"
        return _comparar_resultados("FILIAL", None, portao)
    legado_id = (
        Filial.objects.filter(empresa_id=empresa_id, cnpj=valor_consulta)
        .values_list("pk", flat=True)
        .first()
    )
    registros = [
        {
            "origem": "Filial",
            "identificador": pk,
            "empresa_id": empresa_id_registro,
            "fronteira": "FILIAL",
            "valor": cnpj,
        }
        for pk, empresa_id_registro, cnpj in (
            Filial.objects.filter(empresa_id=empresa_id)
            .order_by("pk")
            .values_list("pk", "empresa_id", "cnpj")
        )
    ]
    portao = resolver_cnpj_por_leitura_dupla(
        valor_consulta, registros, fronteira="FILIAL", empresa_id=empresa_id
    )
    return _comparar_resultados("FILIAL", legado_id, portao)


def ensaiar_adaptador_sombra_empresa_filial():
    """Agrega observacoes da base local sem expor documentos ou identidades."""
    from apps.empresas.models import Empresa, Filial

    consultas = [
        observar_busca_empresa_ativa_por_cnpj(cnpj)
        for cnpj in Empresa.objects.filter(is_active=True).order_by("pk").values_list("cnpj", flat=True)
    ]
    consultas.extend(
        observar_busca_filial_da_empresa_por_cnpj(cnpj, empresa_id=empresa_id)
        for empresa_id, cnpj in Filial.objects.order_by("pk").values_list("empresa_id", "cnpj")
    )
    classificacoes = {}
    status_portao = {}
    for item in consultas:
        classificacoes[item["classificacao"]] = classificacoes.get(item["classificacao"], 0) + 1
        status_portao[item["portao_status"]] = status_portao.get(item["portao_status"], 0) + 1
    bloqueios = sum(
        quantidade for codigo, quantidade in classificacoes.items() if codigo != "CONCORDAM"
    )
    return {
        "contrato": CONTRATO_ADAPTADOR_SOMBRA_CNPJ,
        "base": "ENSAIO_LOCAL_NAO_ACEITE_PRODUCAO",
        "resumo": {
            "total_observacoes": len(consultas),
            "por_classificacao": classificacoes,
            "por_status_portao": status_portao,
            "quantidade_bloqueios": bloqueios,
        },
        "seguranca": {
            "somente_select": True,
            "altera_dados": False,
            "detalhes_individuais_expostos": False,
            "substitui_busca_atual": False,
            "aceite_producao": False,
            "libera_licenca": False,
            "libera_emissao": False,
        },
        "proximo_passo": "DEFINIR_CATALOGO_CENTRAL_DE_IDENTIDADES_DE_TESTE_SEM_TROCA_EM_MASSA",
    }
