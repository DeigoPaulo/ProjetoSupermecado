"""Extrai somente referências autorizadas. Não produz conteúdo fiscal ou XML."""
import hashlib
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.clientes.escopo import empresa_id_do_usuario
from .ajustes_comerciais_devolucao import (
    CONTRATO_AJUSTES_COMERCIAIS,
    validar_ajustes_comerciais_devolucao,
)
from .contrato_devolucao import CONTRATO, GRUPOS, validar_contrato_devolucao
from .devolucao_fornecedor import _hash_conteudo_revisao
from .dossie_devolucao import diagnosticar_dossie
from .identidade_partes_devolucao import (
    CONTRATO_IDENTIDADE_PARTES,
    validar_identidade_partes_devolucao,
)
from .icms_st_fcp_contrato import construir_icms_st_fcp
from .ipi_devolvido_contrato import construir_ipi_devolvido
from .models import ConfiguracaoFiscal, DocumentoDFeRecebido, RascunhoDevolucaoFornecedor
from .pacote_contabil import analisar_xml_nfe
from .produtos_devolucao import CONTRATO_PRODUTOS, validar_produtos_devolucao
from .pagamento_fiscal_devolucao import construir_politica_pagamento_devolucao
from .portao_prontidao_devolucao import construir_portao_prontidao
from .observacoes_fiscais_devolucao import (
    CONTRATO_OBSERVACOES,
    validar_observacoes_fiscais_devolucao,
)
from .obrigatoriedade_campos_devolucao import construir_obrigatoriedade_campos_devolucao
from .referencias_item_devolucao import (
    CONTRATO_REFERENCIAS_ITEM,
    POLITICA_REFERENCIAS_ITEM,
    validar_referencias_item_devolucao,
)
from .rtc_devolucao_contrato import construir_rtc_devolucao
from .rastreabilidade_leiaute_devolucao import construir_rastreabilidade_leiaute_devolucao
from .tributos_itens_devolucao import (
    CONTRATO_TRIBUTOS_ITENS,
    ESTADOS_GRUPOS,
    validar_tributos_itens_devolucao,
)
from .transporte_contrato_devolucao import (
    CONTRATO_TRANSPORTE,
    validar_transporte_devolucao,
)
from .totalizacao_diagnostica_devolucao import construir_totalizacao_diagnostica


LIMITE_XML_ORIGEM_BYTES = 5 * 1024 * 1024


def _digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _nome_local(elemento):
    return elemento.tag.rsplit("}", 1)[-1]


def _primeiro(elemento, nome):
    return next((item for item in elemento.iter() if _nome_local(item) == nome), None)


def _texto(elemento, nome):
    filho = _primeiro(elemento, nome) if elemento is not None else None
    return (filho.text or "").strip() if filho is not None else ""


def _ler_identidade_xml_autorizado(xml):
    """Lê apenas identidade/protocolo do XML, sem validar tributos ou gerar saída."""
    emitente_vazio = {
        "cnpj": "", "razao_social": "", "nome_fantasia": "",
        "inscricao_estadual": "", "logradouro": "", "numero": "",
        "complemento": "", "bairro": "", "codigo_municipio": "",
        "municipio": "", "uf": "", "cep": "",
    }
    vazio = {
        "chave": "", "modelo": "", "emitente_cnpj": "", "destinatario_cnpj": "",
        "emitente": emitente_vazio, "nitens": [],
    }
    if not isinstance(xml, str) or not xml.strip():
        return vazio, "XML_AUSENTE"
    conteudo = xml.encode("utf-8")
    if len(conteudo) > LIMITE_XML_ORIGEM_BYTES:
        return vazio, "XML_EXCEDE_LIMITE"
    maiusculo = conteudo.upper()
    if b"<!DOCTYPE" in maiusculo or b"<!ENTITY" in maiusculo:
        return vazio, "XML_COM_DTD_OU_ENTIDADE"
    try:
        raiz = ElementTree.fromstring(conteudo)
    except (ElementTree.ParseError, ValueError):
        return vazio, "XML_MALFORMADO"
    if _nome_local(raiz) not in {"nfeProc", "NFe"}:
        return vazio, "DOCUMENTO_NAO_E_NFE"
    inf_nfe = _primeiro(raiz, "infNFe")
    protocolo = _primeiro(raiz, "infProt")
    if inf_nfe is None or protocolo is None:
        return vazio, "PROTOCOLO_AUTORIZACAO_AUSENTE"
    if _texto(protocolo, "cStat") != "100":
        return vazio, "NFE_NAO_AUTORIZADA"
    identificador = (inf_nfe.attrib.get("Id") or "").strip()
    chave = identificador[3:] if identificador.startswith("NFe") else identificador
    chave = _digitos(chave)
    if len(chave) != 44 or _digitos(_texto(protocolo, "chNFe")) != chave:
        return vazio, "CHAVE_DIFERE_DO_PROTOCOLO"
    ide = _primeiro(inf_nfe, "ide")
    emitente = _primeiro(inf_nfe, "emit")
    destinatario = _primeiro(inf_nfe, "dest")
    if ide is None or emitente is None or destinatario is None:
        return vazio, "PARTES_OU_IDENTIFICACAO_AUSENTES"
    endereco_emitente = _primeiro(emitente, "enderEmit")
    return {
        "chave": chave,
        "modelo": _texto(ide, "mod"),
        "emitente_cnpj": _digitos(_texto(emitente, "CNPJ")),
        "destinatario_cnpj": _digitos(_texto(destinatario, "CNPJ")),
        "emitente": {
            "cnpj": _digitos(_texto(emitente, "CNPJ")),
            "razao_social": _texto(emitente, "xNome"),
            "nome_fantasia": _texto(emitente, "xFant"),
            "inscricao_estadual": _texto(emitente, "IE"),
            "logradouro": _texto(endereco_emitente, "xLgr"),
            "numero": _texto(endereco_emitente, "nro"),
            "complemento": _texto(endereco_emitente, "xCpl"),
            "bairro": _texto(endereco_emitente, "xBairro"),
            "codigo_municipio": _texto(endereco_emitente, "cMun"),
            "municipio": _texto(endereco_emitente, "xMun"),
            "uf": _texto(endereco_emitente, "UF"),
            "cep": _digitos(_texto(endereco_emitente, "CEP")),
        },
        "nitens": [(item.attrib.get("nItem") or "").strip() for item in inf_nfe if _nome_local(item) == "det"],
    }, ""


def _extrair_referencias_itens(rascunho, dfe, xml):
    entrada = rascunho.entrada_compra
    filial = entrada.filial
    itens_rascunho = list(rascunho.itens.select_related("item_entrada").order_by("item_entrada_id"))
    identidade, erro_xml = _ler_identidade_xml_autorizado(xml)
    analise = analisar_xml_nfe(xml) if not erro_xml else {"itens": []}
    itens_xml = analise.get("itens", [])
    atuais_por_nitem = {item.get("numero_item"): item for item in itens_xml}
    nitens_xml = identidade["nitens"]
    chave = _digitos(rascunho.chave_referenciada)
    conteudo = {
        "contrato": CONTRATO_REFERENCIAS_ITEM,
        "politica": POLITICA_REFERENCIAS_ITEM,
        "modelo": "55",
        "operacao": "DEVOLUCAO_COMPRA",
        "possui_nfref_cabecalho": False,
        "permite_emissao": False,
        "itens": [
            {
                "nitem_novo": indice,
                "chave_acesso": chave,
                "nitem_original": int(item.numero_item_xml) if str(item.numero_item_xml).isdigit() else item.numero_item_xml,
            }
            for indice, item in enumerate(itens_rascunho, 1)
        ],
    }
    validacao_estrutural = validar_referencias_item_devolucao(conteudo)
    hash_atual = hashlib.sha256(xml.encode("utf-8")).hexdigest() if xml else ""
    cnpj_filial = _digitos(filial.cnpj or filial.empresa.cnpj)
    chaves_esperadas = {
        chave,
        _digitos(entrada.chave_acesso_xml),
        _digitos(dfe.chave_acesso) if dfe else "",
        identidade["chave"],
    }
    nitem_integro = bool(itens_rascunho) and all(
        item.item_entrada.entrada_id == entrada.pk
        and item.numero_item_xml in nitens_xml
        and item.item_xml_snapshot
        and atuais_por_nitem.get(item.numero_item_xml) == item.item_xml_snapshot
        for item in itens_rascunho
    )
    verificacoes = [
        {"codigo": "ESCOPO_DFE", "rotulo": "DF-e pertence à empresa e à filial da preparação", "ok": bool(dfe) and dfe.empresa_id == filial.empresa_id and dfe.filial_destino_id == filial.pk},
        {"codigo": "HASH_XML", "rotulo": "XML integral mantém o hash congelado na submissão", "ok": bool(xml) and hash_atual == rascunho.xml_origem_sha256},
        {"codigo": "PROTOCOLO_AUTORIZADO", "rotulo": "XML contém protocolo de autorização cStat 100", "ok": not erro_xml, "detalhe": erro_xml},
        {"codigo": "MODELO_55", "rotulo": "Documento original é NF-e modelo 55", "ok": identidade["modelo"] == "55"},
        {"codigo": "CHAVE_UNICA", "rotulo": "Chave coincide no XML, protocolo, DF-e, compra e preparação", "ok": len(chaves_esperadas) == 1 and "" not in chaves_esperadas},
        {"codigo": "EMITENTE_FORNECEDOR", "rotulo": "Emitente do XML corresponde ao fornecedor", "ok": identidade["emitente_cnpj"] == _digitos(entrada.fornecedor.cnpj) and len(identidade["emitente_cnpj"]) == 14},
        {"codigo": "DESTINATARIO_FILIAL", "rotulo": "Destinatário do XML corresponde à filial", "ok": identidade["destinatario_cnpj"] == cnpj_filial and len(cnpj_filial) == 14},
        {"codigo": "NITEM_E_SNAPSHOT", "rotulo": "Cada item referencia um nItem original íntegro", "ok": nitem_integro},
    ]
    origem_conferida = validacao_estrutural["estrutura_valida"] and all(item["ok"] for item in verificacoes)
    bloqueios = [
        item for item in validacao_estrutural["bloqueios"]
        if item["codigo"] not in {"PARTES_E_XML_ORIGINAL_NAO_CONFERIDOS", "INTEGRACAO_AUTENTICADA_PENDENTE"}
    ]
    if not origem_conferida:
        bloqueios.extend(
            {"grupo": "origem", "codigo": item["codigo"]}
            for item in verificacoes if not item["ok"]
        )
    return {
        "conteudo": conteudo,
        "validacao_estrutural": validacao_estrutural,
        "verificacoes": verificacoes,
        "origem_conferida": origem_conferida,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }


def _extrair_identidade_partes(rascunho, xml, parecer):
    entrada = rascunho.entrada_compra
    filial = entrada.filial
    empresa = filial.empresa
    identidade_xml, erro_xml = _ler_identidade_xml_autorizado(xml)
    emitente_original = identidade_xml["emitente"]
    configuracao = ConfiguracaoFiscal.objects.filter(filial=filial, ativo=True).first()
    uf_destino = emitente_original.get("uf", "")
    destino_operacao = "1" if filial.uf and filial.uf == uf_destino else "2" if filial.uf and uf_destino else ""
    conteudo = {
        "contrato": CONTRATO_IDENTIDADE_PARTES,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "identificacao": {
            "modelo": "55",
            "finalidade": "4",
            "tipo_operacao": "1",
            "natureza_operacao": parecer.natureza_operacao if parecer else "",
            "codigo_municipio_fato_gerador": filial.codigo_municipio_ibge,
            "destino_operacao": destino_operacao,
            "consumidor_final": "",
            "presenca_comprador": "",
        },
        "emitente": {
            "fonte": "FILIAL_E_CONFIGURACAO_FISCAL",
            "filial_id": filial.pk,
            "cnpj": _digitos(filial.cnpj or empresa.cnpj),
            "razao_social": empresa.razao_social,
            "nome_fantasia": filial.nome,
            "inscricao_estadual": configuracao.inscricao_estadual if configuracao else "",
            "crt": configuracao.crt if configuracao else "",
            "logradouro": filial.logradouro,
            "numero": filial.numero,
            "complemento": filial.complemento,
            "bairro": filial.bairro,
            "codigo_municipio": filial.codigo_municipio_ibge,
            "municipio": filial.municipio,
            "uf": filial.uf,
            "cep": _digitos(filial.cep),
        },
        "destinatario": {
            "fonte": "XML_ORIGINAL_E_CADASTRO_FORNECEDOR",
            "fornecedor_id": entrada.fornecedor_id,
            **emitente_original,
        },
    }
    validacao = validar_identidade_partes_devolucao(conteudo)
    if erro_xml:
        validacao["dados_completos"] = False
        validacao["pendencias"].append({"caminho": "destinatario", "codigo": erro_xml})
        validacao["bloqueios"].append({"grupo": "destinatario", "codigo": erro_xml})
    return {"conteudo": conteudo, "validacao": validacao}


def _memoria_aprovada_e_integra(memoria, parametros):
    revisao = getattr(memoria, "revisao_fiscal", None) if memoria else None
    aprovada = bool(
        memoria and revisao and revisao.decisao == "APROVAR"
        and _hash_conteudo_revisao(memoria.conteudo_snapshot) == memoria.conteudo_sha256
        and _hash_conteudo_revisao(revisao.conteudo_snapshot) == revisao.conteudo_sha256
        and revisao.conteudo_snapshot.get("memoria_sha256") == memoria.conteudo_sha256
        and parametros and _hash_conteudo_revisao(parametros.conteudo_snapshot) == parametros.conteudo_sha256
    )
    return aprovada, revisao


def _extrair_produtos(rascunho, memoria, parametros):
    itens_rascunho = list(
        rascunho.itens.select_related("item_entrada__produto").order_by("item_entrada_id")
    )
    itens_parametros = {
        item.item_rascunho_id: item
        for item in parametros.itens.all()
    } if parametros else {}
    itens_memoria = {
        item.item_rascunho_id: item
        for item in memoria.itens.all()
    } if memoria else {}
    memoria_aprovada, _revisao = _memoria_aprovada_e_integra(memoria, parametros)
    itens = []
    for indice, item in enumerate(itens_rascunho, 1):
        snapshot = item.item_xml_snapshot or {}
        parametro = itens_parametros.get(item.pk)
        item_memoria = itens_memoria.get(item.pk)
        origem_aprovada = bool(
            memoria_aprovada and parametro and item_memoria
            and item_memoria.item_parametrizacao_id == parametro.pk
            and parametro.numero_item_xml == item.numero_item_xml
            and item_memoria.numero_item_xml == item.numero_item_xml
        )
        itens.append({
            "nitem_novo": indice,
            "nitem_original": int(item.numero_item_xml) if str(item.numero_item_xml).isdigit() else item.numero_item_xml,
            "item_rascunho_id": item.pk,
            "produto_id": item.item_entrada.produto_id,
            "xml_origem_sha256": rascunho.xml_origem_sha256,
            "parametrizacao_id": parametros.pk if parametros else 0,
            "parametrizacao_sha256": parametros.conteudo_sha256 if parametros else "",
            "memoria_id": memoria.pk if memoria else 0,
            "memoria_sha256": memoria.conteudo_sha256 if memoria else "",
            "memoria_aprovada": origem_aprovada,
            "codigo_produto": snapshot.get("codigo_produto", ""),
            "ean": snapshot.get("ean", ""),
            "ean_tributavel": snapshot.get("ean_tributavel", ""),
            "descricao": snapshot.get("descricao", ""),
            "ncm": snapshot.get("ncm", ""),
            "cest": snapshot.get("cest", ""),
            "cfop": parametros.parecer.cfop if origem_aprovada else "",
            "unidade_comercial": snapshot.get("unidade", ""),
            "quantidade_comercial": format(item.quantidade, ".3f"),
            "valor_unitario_comercial": snapshot.get("valor_unitario", "") if origem_aprovada else "",
            "valor_produtos": format(item_memoria.valor_operacao, ".2f") if origem_aprovada else "",
            "unidade_tributavel": snapshot.get("unidade_tributavel", "") if origem_aprovada else "",
            "quantidade_tributavel": snapshot.get("quantidade_tributavel", "") if origem_aprovada else "",
            "valor_unitario_tributavel": snapshot.get("valor_unitario_tributavel", "") if origem_aprovada else "",
            "tipo_codigo_icms": parametro.tipo_codigo_icms if origem_aprovada else "",
            "origem_icms": parametro.origem_icms if origem_aprovada else "",
            "codigo_icms": parametro.codigo_icms if origem_aprovada else "",
            "codigo_ipi": parametro.codigo_ipi if origem_aprovada else "",
            "codigo_pis": parametro.codigo_pis if origem_aprovada else "",
            "codigo_cofins": parametro.codigo_cofins if origem_aprovada else "",
            "codigo_cbenef": parametro.codigo_cbenef if origem_aprovada else "",
        })
    conteudo = {
        "contrato": CONTRATO_PRODUTOS,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "itens": itens,
    }
    return {"conteudo": conteudo, "validacao": validar_produtos_devolucao(conteudo)}


def _extrair_tributos_itens(rascunho, memoria, parametros):
    memoria_aprovada, revisao = _memoria_aprovada_e_integra(memoria, parametros)
    itens_memoria = {
        item.item_rascunho_id: item for item in memoria.itens.select_related("item_parametrizacao")
    } if memoria else {}
    itens = []
    for indice, item_rascunho in enumerate(rascunho.itens.order_by("item_entrada_id"), 1):
        item = itens_memoria.get(item_rascunho.pk)
        origem_aprovada = bool(
            memoria_aprovada and item and parametros
            and item.item_parametrizacao.parametrizacao_id == parametros.pk
            and item.item_parametrizacao.item_rascunho_id == item_rascunho.pk
            and item.item_parametrizacao.numero_item_xml == item_rascunho.numero_item_xml
            and item.numero_item_xml == item_rascunho.numero_item_xml
        )
        parametro = item.item_parametrizacao if origem_aprovada else None
        grupos = {}
        codigos = {
            "icms": parametro.codigo_icms if parametro else "",
            "pis": parametro.codigo_pis if parametro else "",
            "cofins": parametro.codigo_cofins if parametro else "",
            "icms_st": parametro.codigo_icms if parametro else "",
            "fcp": parametro.codigo_icms if parametro else "",
            "ipi_memoria": parametro.codigo_ipi if parametro else "",
            "ibs": "",
            "cbs": "",
        }
        for nome, estado in ESTADOS_GRUPOS.items():
            origem = "ipi" if nome == "ipi_memoria" else nome
            grupos[nome] = {
                "estado": estado,
                "codigo": codigos[nome],
                "base": format(getattr(item, f"base_{origem}"), ".2f") if origem_aprovada else "",
                "aliquota": format(getattr(item, f"aliquota_{origem}"), ".4f") if origem_aprovada else "",
                "valor": format(getattr(item, f"valor_{origem}"), ".2f") if origem_aprovada else "",
            }
        itens.append({
            "nitem_novo": indice,
            "nitem_original": int(item_rascunho.numero_item_xml) if str(item_rascunho.numero_item_xml).isdigit() else item_rascunho.numero_item_xml,
            "item_rascunho_id": item_rascunho.pk,
            "memoria_id": memoria.pk if memoria else 0,
            "memoria_sha256": memoria.conteudo_sha256 if memoria else "",
            "revisao_sha256": revisao.conteudo_sha256 if revisao else "",
            "origem_aprovada": origem_aprovada,
            "grupos": grupos,
        })
    conteudo = {
        "contrato": CONTRATO_TRIBUTOS_ITENS,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "itens": itens,
    }
    return {"conteudo": conteudo, "validacao": validar_tributos_itens_devolucao(conteudo)}


def _extrair_ajustes_comerciais(rascunho, memoria, parametros, rateio, reflexos):
    memoria_aprovada, revisao_memoria = _memoria_aprovada_e_integra(memoria, parametros)
    revisao_reflexos = getattr(reflexos, "revisao", None) if reflexos else None
    origem_aprovada = bool(
        memoria_aprovada and rateio and reflexos and revisao_reflexos
        and memoria.reflexos_origem_id == reflexos.pk
        and reflexos.rateio_id == rateio.pk
        and revisao_reflexos.decisao == "APROVAR"
        and _hash_conteudo_revisao(rateio.conteudo_snapshot) == rateio.conteudo_sha256
        and _hash_conteudo_revisao(reflexos.conteudo_snapshot) == reflexos.conteudo_sha256
        and _hash_conteudo_revisao(revisao_reflexos.conteudo_snapshot) == revisao_reflexos.conteudo_sha256
        and revisao_reflexos.conteudo_snapshot.get("reflexos_sha256") == reflexos.conteudo_sha256
    )
    linhas_rateio = {
        linha.get("item_rascunho_id"): linha
        for linha in (rateio.conteudo_snapshot.get("itens", []) if origem_aprovada else [])
    }
    itens_memoria_rateio = {
        item.item_rascunho_id: item for item in rateio.composicao.memoria.itens.all()
    } if origem_aprovada else {}
    itens = []
    for indice, item_rascunho in enumerate(rascunho.itens.order_by("item_entrada_id"), 1):
        linha = linhas_rateio.get(item_rascunho.pk, {})
        item_memoria = itens_memoria_rateio.get(item_rascunho.pk)
        itens.append({
            "nitem_novo": indice,
            "nitem_original": int(item_rascunho.numero_item_xml) if str(item_rascunho.numero_item_xml).isdigit() else item_rascunho.numero_item_xml,
            "item_rascunho_id": item_rascunho.pk,
            "item_memoria_id": item_memoria.pk if item_memoria and linha.get("item_memoria_id") == item_memoria.pk else 0,
            "valor_base": linha.get("base", ""),
            "frete": linha.get("frete", ""),
            "seguro": linha.get("seguro", ""),
            "outras_despesas": linha.get("despesas", ""),
            "desconto": linha.get("desconto", ""),
            "total_informado": linha.get("total", ""),
        })
    dados_totais = rateio.composicao.conteudo_snapshot.get("dados", {}) if origem_aprovada else {}
    totais = {
        "valor_base": dados_totais.get("valor_base", ""),
        "frete": dados_totais.get("frete", ""),
        "seguro": dados_totais.get("seguro", ""),
        "outras_despesas": dados_totais.get("despesas", ""),
        "desconto": dados_totais.get("desconto", ""),
        "total_informado": dados_totais.get("total", ""),
    }
    conteudo = {
        "contrato": CONTRATO_AJUSTES_COMERCIAIS,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "origem_aprovada": origem_aprovada,
        "rateio_id": rateio.pk if rateio else 0,
        "rateio_sha256": rateio.conteudo_sha256 if rateio else "",
        "reflexos_id": reflexos.pk if reflexos else 0,
        "reflexos_sha256": reflexos.conteudo_sha256 if reflexos else "",
        "memoria_id": memoria.pk if memoria else 0,
        "memoria_sha256": memoria.conteudo_sha256 if memoria else "",
        "revisao_memoria_sha256": revisao_memoria.conteudo_sha256 if revisao_memoria else "",
        "itens": itens,
        "totais": totais,
    }
    return {"conteudo": conteudo, "validacao": validar_ajustes_comerciais_devolucao(conteudo)}


def _extrair_transporte(rascunho, memoria, parametros, ficha):
    memoria_aprovada, revisao = _memoria_aprovada_e_integra(memoria, parametros)
    origem_atual = bool(
        memoria_aprovada and ficha and ficha.memoria_id == memoria.pk
        and _hash_conteudo_revisao(ficha.conteudo_snapshot) == ficha.conteudo_sha256
        and ficha.conteudo_snapshot.get("rascunho_id") == rascunho.pk
        and ficha.conteudo_snapshot.get("memoria_id") == memoria.pk
        and ficha.conteudo_snapshot.get("memoria_sha256") == memoria.conteudo_sha256
        and ficha.conteudo_snapshot.get("revisao_sha256") == revisao.conteudo_sha256
    )
    dados_vazios = {
        "modalidade": "", "nome": "", "documento": "", "inscricao_estadual": "",
        "endereco": "", "municipio": "", "uf": "", "quantidade_volumes": None,
        "especie": "", "marca": "", "numeracao": "", "peso_liquido": "",
        "peso_bruto": "", "observacao": "",
    }
    dados = {**dados_vazios, **(ficha.conteudo_snapshot.get("dados", {}) if origem_atual else {})}
    conteudo = {
        "contrato": CONTRATO_TRANSPORTE,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "origem_atual": origem_atual,
        "ficha_id": ficha.pk if ficha else 0,
        "ficha_sha256": ficha.conteudo_sha256 if ficha else "",
        "memoria_id": memoria.pk if memoria else 0,
        "memoria_sha256": memoria.conteudo_sha256 if memoria else "",
        "revisao_memoria_sha256": revisao.conteudo_sha256 if revisao else "",
        "dados": dados,
    }
    return {"conteudo": conteudo, "validacao": validar_transporte_devolucao(conteudo)}


def _extrair_observacoes_fiscais(rascunho, memoria, parametros, parecer, transporte):
    memoria_aprovada, revisao = _memoria_aprovada_e_integra(memoria, parametros)
    origem_aprovada = bool(
        memoria_aprovada and parametros and parecer
        and parametros.parecer_id == parecer.pk
        and memoria.parametrizacao_id == parametros.pk
        and _hash_conteudo_revisao(parecer.conteudo_snapshot) == parecer.conteudo_sha256
        and parametros.conteudo_snapshot.get("parecer_id") == parecer.pk
        and parametros.conteudo_snapshot.get("parecer_sha256") == parecer.conteudo_sha256
        and memoria.conteudo_snapshot.get("parametrizacao_id") == parametros.pk
        and memoria.conteudo_snapshot.get("parametrizacao_sha256") == parametros.conteudo_sha256
    )
    itens_parametros = parametros.conteudo_snapshot.get("itens", []) if origem_aprovada else []
    itens_memoria = memoria.conteudo_snapshot.get("itens", []) if origem_aprovada else []
    transporte_atual = bool(transporte["validacao"].get("origem_completa"))
    conteudo = {
        "contrato": CONTRATO_OBSERVACOES,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "origem_aprovada": origem_aprovada,
        "fontes": {
            "parecer_id": parecer.pk if parecer else 0,
            "parecer_sha256": parecer.conteudo_sha256 if parecer else "",
            "parametrizacao_id": parametros.pk if parametros else 0,
            "parametrizacao_sha256": parametros.conteudo_sha256 if parametros else "",
            "memoria_id": memoria.pk if memoria else 0,
            "memoria_sha256": memoria.conteudo_sha256 if memoria else "",
            "revisao_memoria_sha256": revisao.conteudo_sha256 if revisao else "",
        },
        "inventario_interno": {
            "motivo_operacional_presente": bool(rascunho.motivo_operacional) if origem_aprovada else False,
            "fundamentacao_parecer_presente": bool(parecer.fundamentacao) if origem_aprovada else False,
            "observacoes_parametros": sum(bool(item.get("observacao")) for item in itens_parametros),
            "observacoes_memoria": sum(bool(item.get("observacao")) for item in itens_memoria),
            "observacao_transporte_presente": bool(
                transporte["conteudo"]["dados"].get("observacao")
            ) if transporte_atual else False,
        },
        "textos_fiscais": {
            "infadic": "",
            "itens": [
                {
                    "nitem_novo": indice,
                    "nitem_original": int(item.numero_item_xml) if str(item.numero_item_xml).isdigit() else item.numero_item_xml,
                    "item_rascunho_id": item.pk,
                    "infadprod": "",
                }
                for indice, item in enumerate(rascunho.itens.order_by("item_entrada_id"), 1)
            ],
        },
        "politica": {
            "classificacao_interna_obrigatoria": True,
            "exportacao_automatica": False,
            "exige_texto_fiscal_aprovado": True,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_observacoes_fiscais_devolucao(conteudo)}


def extrair_contrato_devolucao(rascunho_id, usuario):
    if not has_role(usuario, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para consultar o contrato fiscal.")
    try:
        rascunho_id = int(rascunho_id)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Preparação inválida.") from exc
    with transaction.atomic():
        qs = RascunhoDevolucaoFornecedor.objects.select_for_update().select_related(
            "entrada_compra__filial__empresa", "entrada_compra__fornecedor"
        )
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None:
            qs = qs.filter(entrada_compra__filial__empresa_id=empresa_id)
        rascunho = qs.filter(pk=rascunho_id).first()
        if not rascunho:
            raise ValidationError("Preparação indisponível para este usuário.")
        dossie = diagnosticar_dossie(rascunho, usuario)
        etapas = {e["chave"]: e["estado"] for e in dossie["etapas"]}
        grupos = {g: {"estado": "NAO_SUPORTADO", "referencias": []} for g in GRUPOS}

        def grupo(nome, objetos, chaves):
            referencias = []
            divergente = False
            for tipo, objeto in objetos:
                if objeto is None:
                    continue
                if _hash_conteudo_revisao(objeto.conteudo_snapshot) != objeto.conteudo_sha256:
                    divergente = True
                    continue
                referencias.append({"tipo": tipo, "id": objeto.pk, "sha256": objeto.conteudo_sha256})
            estados = [etapas.get(c) for c in chaves]
            estado = "REFERENCIADO" if referencias else "AUSENTE"
            if divergente or "Inconsistente" in estados:
                estado = "DIVERGENTE"
            elif "Desatualizado" in estados:
                estado = "SUPERADO"
            grupos[nome] = {"estado": estado, "referencias": referencias}

        dfe = DocumentoDFeRecebido.objects.filter(entrada_compra=rascunho.entrada_compra).first()
        xml = dfe.xml_conteudo if dfe else ""
        if xml and hashlib.sha256(xml.encode("utf-8")).hexdigest() == rascunho.xml_origem_sha256:
            grupos["origem"] = {"estado": "REFERENCIADO", "referencias": [{"tipo": "xml_origem", "id": dfe.pk, "sha256": rascunho.xml_origem_sha256}]}
        else:
            grupos["origem"] = {"estado": "DIVERGENTE" if xml else "AUSENTE", "referencias": []}
        memoria = rascunho.memorias_calculo.order_by("-versao").first()
        parametros = memoria.parametrizacao if memoria else rascunho.parametrizacoes_fiscais.order_by("-versao").first()
        parecer = parametros.parecer if parametros else rascunho.pareceres_tributarios.order_by("-versao").first()
        reflexos = memoria.reflexos_origem if memoria and memoria.reflexos_origem_id else None
        composicao = reflexos.rateio.composicao if reflexos else rascunho.composicoes.order_by("-versao").first()
        rateio = reflexos.rateio if reflexos else composicao.rateios.order_by("-versao").first() if composicao else None
        reflexos = reflexos or (rateio.reflexos.order_by("-versao").first() if rateio else None)
        bases = [("memoria", memoria), ("revisao_memoria", getattr(memoria, "revisao_fiscal", None)),
                 ("reflexos", reflexos), ("revisao_reflexos", getattr(reflexos, "revisao", None))]
        # Inclui predecessoras e decisões de correção, sem expor o conteúdo pessoal.
        anterior = memoria.correcao_de if memoria else None
        vistos = {memoria.pk} if memoria else set()
        while anterior and anterior.pk not in vistos:
            vistos.add(anterior.pk)
            bases.extend([("memoria", anterior), ("revisao_memoria", getattr(anterior, "revisao_fiscal", None))])
            anterior = anterior.correcao_de
        if reflexos:
            origem = reflexos.rateio.composicao.memoria
            if origem.pk not in vistos:
                bases.extend([("memoria", origem), ("revisao_memoria", getattr(origem, "revisao_fiscal", None))])
        grupo("classificacao", [("parametros", parametros), ("parecer", parecer)], ["parametros", "parecer", "parametros_atuais", "parecer_atual"])
        grupo("bases_valores", bases, ["memoria", "revisao_memoria", "reflexos", "origem_atual"])
        grupo("ajustes_comerciais", [("composicao", composicao), ("revisao_composicao", getattr(composicao, "revisao", None)), ("rateio", rateio)], ["composicao", "rateio", "composicao_atual", "origem_atual"])
        transporte = rascunho.transportes.order_by("-versao").first()
        grupo("transporte", [("transporte", transporte)], ["transporte"])
        grupo("observacoes", [("parecer", parecer)], ["parecer"])
        contrato = {"contrato": CONTRATO, "rascunho_id": rascunho.pk,
                    "empresa_id": rascunho.entrada_compra.filial.empresa_id, "modelo": "55",
                    "operacao": "DEVOLUCAO_COMPRA", "permite_emissao": False, "grupos": grupos}
        produtos_extraidos = _extrair_produtos(rascunho, memoria, parametros)
        tributos_extraidos = _extrair_tributos_itens(rascunho, memoria, parametros)
        ajustes_extraidos = _extrair_ajustes_comerciais(
            rascunho, memoria, parametros, rateio, reflexos
        )
        transporte_extraido = _extrair_transporte(rascunho, memoria, parametros, transporte)
        resultado = {"conteudo": contrato, "validacao": validar_contrato_devolucao(contrato),
                "referencias_itens": _extrair_referencias_itens(rascunho, dfe, xml),
                "identidade_partes": _extrair_identidade_partes(rascunho, xml, parecer),
                "produtos": produtos_extraidos,
                "tributos_itens": tributos_extraidos,
                "ajustes_comerciais": ajustes_extraidos,
                "transporte": transporte_extraido,
                "totalizacao": construir_totalizacao_diagnostica(
                    produtos_extraidos, tributos_extraidos, ajustes_extraidos
                ),
                "pagamento_fiscal": construir_politica_pagamento_devolucao(),
                "observacoes_fiscais": _extrair_observacoes_fiscais(
                    rascunho, memoria, parametros, parecer, transporte_extraido
                ),
                "ipi_devolvido": construir_ipi_devolvido(tributos_extraidos),
                "icms_st_fcp": construir_icms_st_fcp(tributos_extraidos),
                "rtc": construir_rtc_devolucao(tributos_extraidos),
                "pendencias_dossie": [e for e in dossie["etapas"] if e["estado"] in ("Pendente", "Desatualizado", "Inconsistente", "Bloqueado")]}
        resultado["portao_prontidao"] = construir_portao_prontidao(resultado)
        resultado["rastreabilidade_leiaute"] = construir_rastreabilidade_leiaute_devolucao()
        resultado["obrigatoriedade_campos"] = construir_obrigatoriedade_campos_devolucao()
        return resultado
