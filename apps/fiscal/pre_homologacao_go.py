"""Diagnostico offline do XSD e das capacidades internas do piloto GO."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from .auditoria_pacote_xsd import auditar_pacote_xsd


CONTRATO = "fiscal_go_pre_homologation_matrix_v1"

SUPORTADO = "SUPORTADO"
BLOQUEADO = "BLOQUEADO"
DEPENDE_DE_HOMOLOGACAO = "DEPENDE_DE_HOMOLOGACAO"
DEPENDE_DE_PARAMETRIZACAO = "DEPENDE_DE_PARAMETRIZACAO"
NAO_IMPLEMENTADO = "NAO_IMPLEMENTADO"
STATUS_VALIDOS = {
    SUPORTADO,
    BLOQUEADO,
    DEPENDE_DE_HOMOLOGACAO,
    DEPENDE_DE_PARAMETRIZACAO,
    NAO_IMPLEMENTADO,
}

PACOTE_XSD = {
    "versao": "PL_010f_v1.04",
    "publicado_em": "2026-08-31",
    "fonte_oficial": (
        "https://www.nfe.fazenda.gov.br/portal/"
        "exibirArquivo.aspx?conteudo=8ITFuBLltXs%3D"
    ),
    "listagem_oficial": (
        "https://www.nfe.fazenda.gov.br/portal/"
        "listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D"
    ),
    "arquivo_relativo": "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
    "sha256": "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998",
    "arquivo_raiz": "PL_010f_v1.04/nfe_v4.00.xsd",
    "arquivo_raiz_sha256": (
        "adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df"
    ),
}


def _capacidade(codigo, area, cenario, status, escopo, evidencias):
    return {
        "codigo": codigo,
        "area": area,
        "cenario": cenario,
        "status": status,
        "escopo": escopo,
        "evidencias": tuple(evidencias),
    }


CAPACIDADES = (
    _capacidade(
        "modelo_65_nfce", "documento", "NFC-e modelo 65", DEPENDE_DE_HOMOLOGACAO,
        "Gerador e preflight cobrem venda interna a consumidor final; autorizacao real continua pendente.",
        ("services.gerar_xml_nfce", "cenarios_tributarios.avaliar_cenario_fiscal_go"),
    ),
    _capacidade(
        "modelo_55_nfe", "documento", "NF-e modelo 55", DEPENDE_DE_HOMOLOGACAO,
        "Gerador atual cobre pedido online interno dentro do recorte fail-closed do piloto.",
        ("services.gerar_xml_nfe_pedido_online", "marketplace.tests"),
    ),
    _capacidade(
        "crt_1_simples", "tributacao", "CRT 1 - Simples Nacional", DEPENDE_DE_PARAMETRIZACAO,
        "Exige CSOSN suportado e cadastro fiscal completo por produto e operacao.",
        ("services.CSOSN_ICMS_SUPORTADOS",),
    ),
    _capacidade(
        "crt_2_excesso", "tributacao", "CRT 2 - excesso de sublimite", DEPENDE_DE_PARAMETRIZACAO,
        "Usa a matriz de CST do regime normal e decisao explicita de cBenef em GO.",
        ("services.CST_ICMS_SUPORTADOS", "diagnostico_cbenef"),
    ),
    _capacidade(
        "crt_3_normal", "tributacao", "CRT 3 - regime normal", DEPENDE_DE_PARAMETRIZACAO,
        "Exige CST suportado, aliquotas e decisao explicita de cBenef em GO.",
        ("services.CST_ICMS_SUPORTADOS", "diagnostico_cbenef"),
    ),
    _capacidade(
        "crt_4_mei", "tributacao", "CRT 4 - MEI", DEPENDE_DE_PARAMETRIZACAO,
        "Compartilha o ramo CSOSN; enquadramento real depende de revisao fiscal.",
        ("services._usa_csosn",),
    ),
    _capacidade(
        "icms_cst_suportados", "tributacao", "CST ICMS 00, 20, 40, 41 e 50", SUPORTADO,
        "Serializacao interna explicita em ICMS00, ICMS20 ou ICMS40; nao libera producao.",
        ("services._icms_produto", "test_cenarios_tributarios"),
    ),
    _capacidade(
        "icms_cst_desconhecido", "tributacao", "CST ICMS fora da matriz", BLOQUEADO,
        "O preflight e o gerador recusam CST nao catalogado.",
        ("services._icms_produto", "services.pendencias_produto_fiscal"),
    ),
    _capacidade(
        "icms_csosn_suportados", "tributacao", "CSOSN 102, 103, 300 e 400", SUPORTADO,
        "Serializacao interna explicita no grupo ICMSSN102; nao libera producao.",
        ("services._icms_produto", "test_cenarios_tributarios"),
    ),
    _capacidade(
        "icms_csosn_desconhecido", "tributacao", "CSOSN fora da matriz", BLOQUEADO,
        "O preflight e o gerador recusam CSOSN nao catalogado.",
        ("services._icms_produto", "services.pendencias_produto_fiscal"),
    ),
    _capacidade(
        "pis", "tributacao", "PIS", DEPENDE_DE_PARAMETRIZACAO,
        "CST 01/02, 04-09, 49 e 99 possuem ramos explicitos; aliquota e aplicabilidade dependem do produto.",
        ("services._contribuicao_produto", "diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "cofins", "tributacao", "COFINS", DEPENDE_DE_PARAMETRIZACAO,
        "CST 01/02, 04-09, 49 e 99 possuem ramos explicitos; aliquota e aplicabilidade dependem do produto.",
        ("services._contribuicao_produto", "diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "ipi", "tributacao", "IPI", DEPENDE_DE_PARAMETRIZACAO,
        "Grupos tributado e nao tributado existem, mas exigem CST, cEnq e politica da natureza.",
        ("services._ipi_produto", "services._composicao_item_ipi"),
    ),
    _capacidade(
        "cbenef", "tributacao", "cBenef GO", DEPENDE_DE_PARAMETRIZACAO,
        "Decisao por produto e natureza existe; validade e divergencias exigem responsavel fiscal.",
        ("diagnostico_cbenef", "INVENTARIO_CBENEF_LEGADO.md"),
    ),
    _capacidade(
        "ibs_cbs", "tributacao", "IBS/CBS no XML", NAO_IMPLEMENTADO,
        "Cadastro preparatorio existe, mas calculo e grupos XML emissivos permanecem desabilitados.",
        ("services.capacidade_tributaria_fiscal",),
    ),
    _capacidade(
        "pagamento_dinheiro", "pagamento", "Dinheiro", SUPORTADO,
        "Mapeamento tPag 01 e multiplas parcelas sao serializados offline.",
        ("services._codigo_pagamento", "test_diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "pagamento_credito", "pagamento", "Cartao de credito", DEPENDE_DE_HOMOLOGACAO,
        "tPag 03 e vinculo fiscal sao cobertos offline; driver e adquirente reais estao ausentes.",
        ("services._adicionar_integracao_pagamento_nfce", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_debito", "pagamento", "Cartao de debito", DEPENDE_DE_HOMOLOGACAO,
        "tPag 04 e vinculo fiscal sao cobertos offline; driver e adquirente reais estao ausentes.",
        ("services._adicionar_integracao_pagamento_nfce", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_pix", "pagamento", "PIX", DEPENDE_DE_HOMOLOGACAO,
        "tPag 17 e vinculo sem bandeira inventada sao cobertos offline; provedor real esta ausente.",
        ("diagnostico_pagamentos_xsd", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_vale_alimentacao", "pagamento", "Vale-alimentacao", DEPENDE_DE_HOMOLOGACAO,
        "tPag 10 passa offline, mas nao existe operadora/verificador real conectado.",
        ("services._codigo_pagamento", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_vale_refeicao", "pagamento", "Vale-refeicao", DEPENDE_DE_HOMOLOGACAO,
        "tPag 11 passa offline, mas nao existe operadora/verificador real conectado.",
        ("services._codigo_pagamento", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_dividido", "pagamento", "Pagamento dividido", DEPENDE_DE_HOMOLOGACAO,
        "Parcelas e paridade XML/banco sao cobertas offline; ponta a ponta real permanece pendente.",
        ("services.validar_vinculos_pagamentos_xml", "diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "destinatario_nao_identificado", "destinatario", "Consumidor nao identificado", SUPORTADO,
        "A NFC-e omite dest de forma explicita quando essa opcao e selecionada.",
        ("services._documento_consumidor_nfce",),
    ),
    _capacidade(
        "destinatario_cpf", "destinatario", "CPF informado na NFC-e", SUPORTADO,
        "Documento e canonicalizado e serializado em dest/CPF.",
        ("services._documento_consumidor_nfce", "pdv.forms"),
    ),
    _capacidade(
        "destinatario_cnpj", "destinatario", "CNPJ quando aplicavel", DEPENDE_DE_HOMOLOGACAO,
        "Serializacao interna existe; consumidor contribuinte/B2B e aceite externo nao estao cobertos.",
        ("services._documento_consumidor_nfce", "services._dados_destinatario_nfe_pedido"),
    ),
    _capacidade(
        "endereco_emitente", "emitente", "Endereco fiscal do emitente", DEPENDE_DE_PARAMETRIZACAO,
        "Preflight GO exige endereco estruturado e CEP; nenhum valor ausente e inventado.",
        ("services.pendencias_endereco_emitente_nfce",),
    ),
    _capacidade(
        "qrcode_nfce", "documento", "QR Code NFC-e", DEPENDE_DE_HOMOLOGACAO,
        "Geracao offline existe; versao, URLs e CSC quando aplicavel exigem configuracao e homologacao.",
        ("qrcode_nfce", "AUDITORIA_PRE_HOMOLOGACAO_SEFAZ_GO.md"),
    ),
    _capacidade(
        "contingencia_nfce", "canal", "Contingencia NFC-e tpEmis 9", DEPENDE_DE_HOMOLOGACAO,
        "Fluxo offline, prazo e reconciliacao existem; comportamento real depende da SEFAZ-GO.",
        ("services.ativar_contingencia_offline", "sefaz_direta.capacidades"),
    ),
    _capacidade(
        "sefaz_direta_go", "canal", "SEFAZ direta GO", DEPENDE_DE_HOMOLOGACAO,
        "Sete capacidades estruturais estao offline; rede e producao permanecem bloqueadas.",
        ("roteamento_operacoes_fiscais", "MATRIZ_QUALIFICACAO_CANAIS_FISCAIS.md"),
    ),
    _capacidade(
        "focus", "canal", "Focus NFe", DEPENDE_DE_HOMOLOGACAO,
        "Cinco capacidades estruturais existem; CC-e e manifestacao falham fechado neste canal.",
        ("roteamento_operacoes_fiscais", "MATRIZ_QUALIFICACAO_CANAIS_FISCAIS.md"),
    ),
    _capacidade(
        "xsd_operacional", "schema", "XSD operacional do piloto", BLOQUEADO,
        "O 010f esta arquivado e integro, mas nao foi promovido, aprovado nem instalado.",
        ("auditoria_pacote_xsd", "fiscal_schemas/README.md"),
    ),
    _capacidade(
        "venda_interestadual", "operacao", "Venda interestadual", NAO_IMPLEMENTADO,
        "O gerador atual declara idDest interno e o avaliador GO recusa o cenario.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go",),
    ),
    _capacidade(
        "destinatario_contribuinte", "operacao", "Venda para contribuinte", NAO_IMPLEMENTADO,
        "A matriz GO bloqueia B2B contribuinte por exigir regras proprias.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go",),
    ),
    _capacidade(
        "frete", "operacao", "Venda com frete", NAO_IMPLEMENTADO,
        "O XML atual fixa modFrete sem frete e o avaliador recusa o cenario.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go",),
    ),
    _capacidade(
        "producao", "seguranca", "Emissao em producao", BLOQUEADO,
        "Nenhum resultado offline, XSD compilado ou adaptador estrutural libera producao.",
        ("sefaz_direta.adapter", "services_evidencias_homologacao"),
    ),
)


def matriz_capacidades_piloto_go():
    itens = []
    for capacidade in CAPACIDADES:
        item = dict(capacidade)
        item["evidencias"] = list(item["evidencias"])
        item["autoriza_producao"] = False
        itens.append(item)
    return itens


def consultar_capacidade_piloto_go(codigo):
    codigo = str(codigo or "").strip()
    for item in matriz_capacidades_piloto_go():
        if item["codigo"] == codigo:
            return item
    return {
        "codigo": codigo,
        "area": "desconhecida",
        "cenario": "Cenario nao catalogado",
        "status": BLOQUEADO,
        "escopo": "Combinacao desconhecida nao pode gerar XML transmissivel.",
        "evidencias": [],
        "autoriza_producao": False,
        "motivo": "CENARIO_NAO_CATALOGADO",
    }


def _sha256_json(conteudo):
    serializado = json.dumps(
        conteudo, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def diagnostico_pre_homologacao_go(base_dir):
    base = Path(base_dir).resolve()
    arquivo = base / PACOTE_XSD["arquivo_relativo"]
    auditoria = auditar_pacote_xsd(
        arquivo=arquivo,
        sha256_esperado=PACOTE_XSD["sha256"],
        versao=PACOTE_XSD["versao"],
    )
    xsd_operacionais = sorted(
        str(item.relative_to(base)).replace("\\", "/")
        for item in (base / "fiscal_schemas").glob("**/*.xsd")
    )
    itens = matriz_capacidades_piloto_go()
    contagem = Counter(item["status"] for item in itens)
    resultado = {
        "contrato": CONTRATO,
        "escopo": "DIAGNOSTICO_INTERNO_OFFLINE_SEM_HOMOLOGACAO",
        "xsd": {
            "pacote_atual": {
                "papel": "ARQUIVADO_PARA_TESTES_E_AUDITORIA",
                "versao": PACOTE_XSD["versao"],
                "arquivo": PACOTE_XSD["arquivo_relativo"],
                "sha256": auditoria["pacote"]["sha256"],
                "arquivo_raiz": auditoria["schema"]["arquivo_raiz"],
                "arquivo_raiz_sha256": auditoria["schema"]["arquivo_raiz_sha256"],
                "arquivos_xsd": auditoria["schema"]["arquivos_xsd"],
            },
            "pacote_oficial_identificado": {
                "versao": PACOTE_XSD["versao"],
                "publicado_em": PACOTE_XSD["publicado_em"],
                "fonte": PACOTE_XSD["fonte_oficial"],
                "listagem": PACOTE_XSD["listagem_oficial"],
                "sha256": PACOTE_XSD["sha256"],
            },
            "comparacao": "IGUAIS_POR_SHA256",
            "impacto": "SEM_SUBSTITUICAO; PROMOCAO E APROVACAO CONTINUAM PENDENTES",
            "arquivos_afetados": [],
            "operacional_no_repositorio": {
                "estado": "NAO_INSTALADO" if not xsd_operacionais else "XSD_PRESENTE_NAO_AVALIADO",
                "arquivos_xsd": xsd_operacionais,
            },
            "modelos_estruturais": ["55", "65"],
            "compilacao_offline": auditoria["schema"]["compilacao_offline"],
        },
        "capacidades": {
            "status_validos": sorted(STATUS_VALIDOS),
            "total": len(itens),
            "contagem": {status: contagem.get(status, 0) for status in sorted(STATUS_VALIDOS)},
            "itens": itens,
        },
        "politica": {
            "acessou_rede": False,
            "alterou_configuracao": False,
            "instalou_schema": False,
            "gerou_xml": False,
            "transmitiu": False,
            "homologacao_real": False,
            "producao_liberada": False,
        },
    }
    resultado["manifesto_sha256"] = _sha256_json(resultado)
    return resultado
