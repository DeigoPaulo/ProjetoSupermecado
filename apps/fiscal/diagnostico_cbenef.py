from collections import Counter, defaultdict
from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Prefetch, Q

from apps.produtos.models import Produto

from .escopo import configuracoes_para_usuario, naturezas_para_usuario
from .models import (
    CodigoRegimeTributario,
    ConfiguracaoFiscal,
    NaturezaOperacao,
    ParametrizacaoBeneficioFiscalProduto,
    SituacaoBeneficioFiscalICMS,
)
from .perfis_uf import perfil_fiscal_uf


CONCORDANTE = "CONCORDANTE"
DIVERGENTE = "DIVERGENTE"
SOMENTE_LEGADO = "SOMENTE_LEGADO"
SOMENTE_EXPLICITO = "SOMENTE_EXPLICITO"
SEM_BENEFICIO_EXPLICITO_COM_LEGADO = "SEM_BENEFICIO_EXPLICITO_COM_LEGADO"
SEM_BENEFICIO_EXPLICITO = "SEM_BENEFICIO_EXPLICITO"
INDEFINIDO = "INDEFINIDO"
AUSENTE = "AUSENTE"

CLASSIFICACOES_CBENEF = {
    CONCORDANTE: "Concordante",
    DIVERGENTE: "Divergente",
    SOMENTE_LEGADO: "Somente legado",
    SOMENTE_EXPLICITO: "Somente explícito",
    SEM_BENEFICIO_EXPLICITO_COM_LEGADO: "Sem benefício explícito com legado",
    SEM_BENEFICIO_EXPLICITO: "Sem benefício explícito",
    INDEFINIDO: "Indefinido",
    AUSENTE: "Ausente",
}


@dataclass(frozen=True)
class LinhaDiagnosticoCBenef:
    produto: Produto
    configuracao: ConfiguracaoFiscal
    natureza: NaturezaOperacao
    parametrizacao: ParametrizacaoBeneficioFiscalProduto | None
    legado: str
    decisao_explicita: str
    codigo_explicito: str
    situacao: str
    situacao_label: str
    observacao: str
    perfil_estadual: bool
    fonte_emissiva_atual: str

    @property
    def empresa(self):
        return self.configuracao.filial.empresa

    @property
    def filial(self):
        return self.configuracao.filial

    @property
    def uf(self):
        return (self.configuracao.filial.uf or "").strip().upper()

    @property
    def crt(self):
        return str(self.configuracao.crt or "")


def _normalizar_codigo(valor):
    return (valor or "").strip().upper()


def classificar_confronto_cbenef(legado, parametrizacao):
    legado = _normalizar_codigo(legado)
    if parametrizacao is None:
        return SOMENTE_LEGADO if legado else AUSENTE

    situacao = parametrizacao.situacao
    explicito = _normalizar_codigo(parametrizacao.codigo_beneficio_fiscal)
    if situacao == SituacaoBeneficioFiscalICMS.INDEFINIDO:
        return INDEFINIDO
    if situacao == SituacaoBeneficioFiscalICMS.SEM_BENEFICIO:
        return SEM_BENEFICIO_EXPLICITO_COM_LEGADO if legado else SEM_BENEFICIO_EXPLICITO
    if not legado:
        return SOMENTE_EXPLICITO
    return CONCORDANTE if legado == explicito else DIVERGENTE


def _observacao_linha(*, situacao, legado, uf, perfil_estadual, fonte_emissiva_atual):
    observacoes = []
    if situacao == CONCORDANTE:
        observacoes.append("As duas fontes possuem o mesmo valor cadastrado.")
    elif situacao == DIVERGENTE:
        observacoes.append("As fontes possuem valores diferentes; exige revisão humana.")
    elif situacao == SOMENTE_LEGADO:
        observacoes.append("Há valor no campo legado e nenhuma decisão explícita para esta natureza.")
    elif situacao == SOMENTE_EXPLICITO:
        observacoes.append("Há decisão com código explícito e o campo legado está vazio.")
    elif situacao == SEM_BENEFICIO_EXPLICITO_COM_LEGADO:
        observacoes.append("A decisão humana informa sem benefício, mas o campo legado ainda possui valor.")
    elif situacao == SEM_BENEFICIO_EXPLICITO:
        observacoes.append("A decisão humana informa sem benefício e o campo legado está vazio.")
    elif situacao == INDEFINIDO:
        observacoes.append("A parametrização existe, mas a decisão humana permanece indefinida.")
    else:
        observacoes.append("Não há valor legado nem decisão explícita para esta natureza.")

    if not perfil_estadual:
        observacoes.append("Recorte sem perfil fiscal estadual homologado no Deigo Fiscal.")
    if legado.startswith("GO") and uf != "GO":
        observacoes.append(
            f"O legado com prefixo GO é apenas exibido; sua validade não é afirmada para {uf or 'UF não informada'}."
        )
    observacoes.append(f"Fonte emissiva atual caracterizada: {fonte_emissiva_atual}.")
    observacoes.append("Este diagnóstico não valida a aplicabilidade fiscal dos códigos.")
    return " ".join(observacoes)


def _fonte_emissiva_atual(uf, crt):
    if uf == "GO" and crt in {
        CodigoRegimeTributario.SIMPLES_EXCESSO_SUBLIMITE,
        CodigoRegimeTributario.REGIME_NORMAL,
    }:
        return "decisão explícita por produto e natureza"
    return "campo legado por compatibilidade"


def opcoes_diagnostico_cbenef(user):
    configuracoes = list(
        configuracoes_para_usuario(
            user,
            ConfiguracaoFiscal.objects.select_related("filial__empresa"),
        ).order_by("filial__empresa__nome_fantasia", "filial__nome")
    )
    empresas = {}
    filiais = []
    for configuracao in configuracoes:
        empresas[configuracao.filial.empresa_id] = configuracao.filial.empresa
        filiais.append(configuracao.filial)
    naturezas = list(
        naturezas_para_usuario(
            user,
            NaturezaOperacao.objects.select_related("empresa"),
        ).order_by("empresa__nome_fantasia", "descricao")
    )
    return {
        "empresas": list(empresas.values()),
        "filiais": filiais,
        "naturezas": naturezas,
        "ufs": sorted({config.filial.uf for config in configuracoes if config.filial.uf}),
        "crts": CodigoRegimeTributario.choices,
        "classificacoes": CLASSIFICACOES_CBENEF,
    }


def _inteiro_positivo(valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def iterar_diagnostico_cbenef(user, filtros=None):
    filtros = filtros or {}
    empresa_id = _inteiro_positivo(filtros.get("empresa"))
    filial_id = _inteiro_positivo(filtros.get("filial"))
    natureza_id = _inteiro_positivo(filtros.get("natureza"))
    uf = (filtros.get("uf") or "").strip().upper()
    crt = (filtros.get("crt") or "").strip()
    q = (filtros.get("q") or "").strip()
    situacao_filtro = (filtros.get("situacao") or "").strip().upper()

    configuracoes_qs = configuracoes_para_usuario(
        user,
        ConfiguracaoFiscal.objects.select_related("filial__empresa"),
    )
    if empresa_id:
        configuracoes_qs = configuracoes_qs.filter(filial__empresa_id=empresa_id)
    if filial_id:
        configuracoes_qs = configuracoes_qs.filter(filial_id=filial_id)
    if uf:
        configuracoes_qs = configuracoes_qs.filter(filial__uf=uf)
    if crt:
        configuracoes_qs = configuracoes_qs.filter(crt=crt)
    configuracoes = list(
        configuracoes_qs.order_by("filial__empresa__nome_fantasia", "filial__nome")
    )
    if not configuracoes:
        return

    empresa_ids = {config.filial.empresa_id for config in configuracoes}
    naturezas_qs = naturezas_para_usuario(
        user,
        NaturezaOperacao.objects.select_related("empresa").filter(empresa_id__in=empresa_ids),
    )
    if natureza_id:
        naturezas_qs = naturezas_qs.filter(pk=natureza_id)
    naturezas = list(naturezas_qs.order_by("empresa__nome_fantasia", "descricao"))
    naturezas_por_empresa = defaultdict(list)
    for natureza in naturezas:
        naturezas_por_empresa[natureza.empresa_id].append(natureza)
    if not naturezas_por_empresa:
        return

    parametrizacoes_qs = ParametrizacaoBeneficioFiscalProduto.objects.filter(
        natureza_operacao_id__in=[natureza.pk for natureza in naturezas]
    ).select_related("natureza_operacao")
    produtos_qs = Produto.all_objects.select_related("categoria").prefetch_related(
        Prefetch(
            "parametrizacoes_beneficio_fiscal",
            queryset=parametrizacoes_qs,
            to_attr="diagnostico_cbenef_parametrizacoes",
        )
    ).order_by("nome", "pk")
    if q:
        produtos_qs = produtos_qs.filter(
            Q(nome__icontains=q)
            | Q(codigo_barras__icontains=q)
            | Q(codigo_interno__icontains=q)
        )

    for produto in produtos_qs.iterator(chunk_size=250):
        parametrizacoes = {
            item.natureza_operacao_id: item
            for item in produto.diagnostico_cbenef_parametrizacoes
        }
        legado = _normalizar_codigo(produto.codigo_beneficio_fiscal)
        for configuracao in configuracoes:
            recorte_uf = (configuracao.filial.uf or "").strip().upper()
            recorte_crt = str(configuracao.crt or "")
            perfil_estadual = bool(perfil_fiscal_uf(recorte_uf))
            fonte_emissiva = _fonte_emissiva_atual(recorte_uf, recorte_crt)
            for natureza in naturezas_por_empresa[configuracao.filial.empresa_id]:
                parametrizacao = parametrizacoes.get(natureza.pk)
                situacao = classificar_confronto_cbenef(legado, parametrizacao)
                if situacao_filtro and situacao_filtro in CLASSIFICACOES_CBENEF and situacao != situacao_filtro:
                    continue
                codigo_explicito = _normalizar_codigo(
                    parametrizacao.codigo_beneficio_fiscal if parametrizacao else ""
                )
                decisao = (
                    parametrizacao.get_situacao_display() if parametrizacao else "Sem parametrização"
                )
                yield LinhaDiagnosticoCBenef(
                    produto=produto,
                    configuracao=configuracao,
                    natureza=natureza,
                    parametrizacao=parametrizacao,
                    legado=legado,
                    decisao_explicita=decisao,
                    codigo_explicito=codigo_explicito,
                    situacao=situacao,
                    situacao_label=CLASSIFICACOES_CBENEF[situacao],
                    observacao=_observacao_linha(
                        situacao=situacao,
                        legado=legado,
                        uf=recorte_uf,
                        perfil_estadual=perfil_estadual,
                        fonte_emissiva_atual=fonte_emissiva,
                    ),
                    perfil_estadual=perfil_estadual,
                    fonte_emissiva_atual=fonte_emissiva,
                )


def paginar_diagnostico_cbenef(user, filtros=None, numero_pagina=1, por_pagina=50):
    try:
        numero_pagina = max(1, int(numero_pagina))
    except (TypeError, ValueError):
        numero_pagina = 1
    inicio = (numero_pagina - 1) * por_pagina
    fim = inicio + por_pagina
    linhas = []
    contagens = Counter()
    total = 0
    for linha in iterar_diagnostico_cbenef(user, filtros):
        contagens[linha.situacao] += 1
        if inicio <= total < fim:
            linhas.append(linha)
        total += 1

    paginador = Paginator(range(total), por_pagina)
    pagina = paginador.get_page(numero_pagina)
    if pagina.number != numero_pagina:
        inicio = (pagina.number - 1) * por_pagina
        fim = inicio + por_pagina
        linhas = [
            linha
            for indice, linha in enumerate(iterar_diagnostico_cbenef(user, filtros))
            if inicio <= indice < fim
        ]
    pagina.object_list = linhas
    return pagina, contagens
