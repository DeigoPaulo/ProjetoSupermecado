"""Extrai somente referências autorizadas. Não produz conteúdo fiscal ou XML."""
import hashlib
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.clientes.escopo import empresa_id_do_usuario
from .contrato_devolucao import CONTRATO, GRUPOS, validar_contrato_devolucao
from .devolucao_fornecedor import _hash_conteudo_revisao
from .dossie_devolucao import diagnosticar_dossie
from .identidade_partes_devolucao import (
    CONTRATO_IDENTIDADE_PARTES,
    validar_identidade_partes_devolucao,
)
from .models import ConfiguracaoFiscal, DocumentoDFeRecebido, RascunhoDevolucaoFornecedor
from .pacote_contabil import analisar_xml_nfe
from .referencias_item_devolucao import (
    CONTRATO_REFERENCIAS_ITEM,
    POLITICA_REFERENCIAS_ITEM,
    validar_referencias_item_devolucao,
)


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
        grupo("transporte", [("transporte", rascunho.transportes.order_by("-versao").first())], ["transporte"])
        grupo("observacoes", [("parecer", parecer)], ["parecer"])
        contrato = {"contrato": CONTRATO, "rascunho_id": rascunho.pk,
                    "empresa_id": rascunho.entrada_compra.filial.empresa_id, "modelo": "55",
                    "operacao": "DEVOLUCAO_COMPRA", "permite_emissao": False, "grupos": grupos}
        return {"conteudo": contrato, "validacao": validar_contrato_devolucao(contrato),
                "referencias_itens": _extrair_referencias_itens(rascunho, dfe, xml),
                "identidade_partes": _extrair_identidade_partes(rascunho, xml, parecer),
                "pendencias_dossie": [e for e in dossie["etapas"] if e["estado"] in ("Pendente", "Desatualizado", "Inconsistente", "Bloqueado")]}
