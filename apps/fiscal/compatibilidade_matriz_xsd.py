"""Compatibilidade estrutural entre a matriz atômica e um pacote XSD auditado."""

import hashlib
import io
import itertools
import re
import zipfile
from pathlib import Path, PurePosixPath

from lxml import etree

from .auditoria_pacote_xsd import CONTRATO_AUDITORIA_XSD, auditar_pacote_xsd
from .inventario_dados_devolucao import CAMPOS_ATOMICOS
from .matriz_atomica_devolucao import (
    CONTRATO_MATRIZ_ATOMICA, _destino_xml, validar_matriz_atomica_devolucao,
)


CONTRATO_COMPATIBILIDADE_XSD = "supplier_return_atomic_xsd_compatibility_v1"
XSD_NS = "http://www.w3.org/2001/XMLSchema"
NS = {"xs": XSD_NS}
ESTADOS = {
    "CONFIRMADO_NO_XSD_AUDITADO",
    "SEM_TAG_TOTAL_DOCUMENTADA",
    "PENDENTE_DE_LEIAUTE_APROVADO",
    "DIVERGENTE_DO_XSD_AUDITADO",
}


def _local(qname):
    return (qname or "").split(":")[-1]


def _carregar_documentos(arquivo, sha256_esperado):
    caminho = Path(arquivo).expanduser().resolve()
    conteudo = caminho.read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != sha256_esperado:
        raise ValueError("O pacote mudou depois da auditoria.")
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        return {
            PurePosixPath(info.filename): etree.fromstring(
                pacote.read(info),
                etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False),
            )
            for info in pacote.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".xsd")
        }


class _ModeloXSD:
    def __init__(self, documentos):
        self.tipos = {}
        self.elementos = {}
        self.grupos = {}
        for raiz in documentos.values():
            for no in raiz.xpath("./xs:complexType[@name]", namespaces=NS):
                self.tipos[no.get("name")] = no
            for no in raiz.xpath("./xs:element[@name]", namespaces=NS):
                self.elementos[no.get("name")] = no
            for no in raiz.xpath("./xs:group[@name]", namespaces=NS):
                self.grupos[no.get("name")] = no

    def _declaracao(self, elemento):
        referencia = _local(elemento.get("ref"))
        return self.elementos.get(referencia, elemento) if referencia else elemento

    def _tipo_complexo(self, elemento):
        elemento = self._declaracao(elemento)
        interno = elemento.find("xs:complexType", namespaces=NS)
        if interno is not None:
            return interno
        return self.tipos.get(_local(elemento.get("type")))

    def _elementos_compositor(self, no):
        saida = []
        if no is None:
            return saida
        for filho in no:
            if filho.tag == f"{{{XSD_NS}}}element":
                saida.append(self._declaracao(filho))
            elif filho.tag in {
                f"{{{XSD_NS}}}sequence", f"{{{XSD_NS}}}choice", f"{{{XSD_NS}}}all",
            }:
                saida.extend(self._elementos_compositor(filho))
            elif filho.tag == f"{{{XSD_NS}}}group":
                grupo = self.grupos.get(_local(filho.get("ref")))
                saida.extend(self._elementos_compositor(grupo))
        return saida

    def filhos(self, elemento):
        tipo = self._tipo_complexo(elemento)
        if tipo is None:
            return []
        saida = []
        extensoes = tipo.xpath("./xs:complexContent/xs:extension | ./xs:simpleContent/xs:extension", namespaces=NS)
        for extensao in extensoes:
            base = self.tipos.get(_local(extensao.get("base")))
            saida.extend(self._elementos_compositor(base))
            saida.extend(self._elementos_compositor(extensao))
        if not extensoes:
            saida.extend(self._elementos_compositor(tipo))
        unicos = {}
        for item in saida:
            nome = item.get("name") or _local(item.get("ref"))
            if nome:
                unicos[(nome, id(item))] = item
        return list(unicos.values())

    def caminho_existe(self, segmentos):
        atuais = [self.elementos[segmentos[0]]] if segmentos and segmentos[0] in self.elementos else []
        for segmento in segmentos[1:]:
            proximos = []
            for atual in atuais:
                for filho in self.filhos(atual):
                    nome = filho.get("name") or _local(filho.get("ref"))
                    if segmento == "*" or nome == segmento:
                        proximos.append(filho)
            atuais = proximos
            if not atuais:
                return False
        return bool(atuais)


def _opcoes_segmento(segmento):
    if segmento == "*":
        return ["*"]
    if segmento.startswith("(") and segmento.endswith(")"):
        segmento = segmento[1:-1]
    return segmento.split("|")


def _caminhos_concretos(expressao):
    return [list(combinacao) for combinacao in itertools.product(*(
        _opcoes_segmento(segmento) for segmento in expressao.split("/")
    ))]


def construir_compatibilidade_matriz_xsd(*, matriz, arquivo, sha256_esperado, versao):
    conteudo_matriz = matriz.get("conteudo", {}) if isinstance(matriz, dict) else {}
    validacao_matriz = validar_matriz_atomica_devolucao(conteudo_matriz)
    if not validacao_matriz["estrutura_valida"]:
        raise ValueError("A matriz atômica deve estar íntegra antes do confronto XSD.")
    auditoria = auditar_pacote_xsd(
        arquivo=arquivo,
        sha256_esperado=sha256_esperado,
        versao=versao,
    )
    documentos = _carregar_documentos(arquivo, auditoria["pacote"]["sha256"])
    modelo = _ModeloXSD(documentos)
    itens = []
    for item in conteudo_matriz["itens"]:
        destino = item["destino_xml_futuro"]
        caminhos = []
        if "[" in destino:
            estado = "PENDENTE_DE_LEIAUTE_APROVADO"
        elif destino.endswith("/SEM_CAMPO_TOTAL_ESPECIFICO"):
            estado = "SEM_TAG_TOTAL_DOCUMENTADA"
        else:
            caminhos = _caminhos_concretos(destino)
            estado = (
                "CONFIRMADO_NO_XSD_AUDITADO"
                if caminhos and all(modelo.caminho_existe(caminho) for caminho in caminhos)
                else "DIVERGENTE_DO_XSD_AUDITADO"
            )
        itens.append({
            "grupo": item["grupo"],
            "campo": item["campo"],
            "destino_xml_futuro": destino,
            "estado": estado,
            "alternativas_exigidas": len(caminhos),
            "serializacao_liberada": False,
        })
    resumo = {estado: sum(item["estado"] == estado for item in itens) for estado in sorted(ESTADOS)}
    conteudo = {
        "contrato": CONTRATO_COMPATIBILIDADE_XSD,
        "operacao": "DEVOLUCAO_COMPRA",
        "matriz_contrato": conteudo_matriz["contrato"],
        "auditoria_contrato": auditoria["contrato"],
        "pacote_sha256": auditoria["pacote"]["sha256"],
        "arquivo_raiz_sha256": auditoria["schema"]["arquivo_raiz_sha256"],
        "itens": itens,
        "resumo": resumo,
        "compativel_sem_divergencias": resumo["DIVERGENTE_DO_XSD_AUDITADO"] == 0,
        "politica": {
            "aprovar_aplicabilidade": False,
            "promover_schema": False,
            "gerar_xml": False,
            "assinar": False,
            "transmitir": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_compatibilidade_matriz_xsd(conteudo)}


def validar_compatibilidade_matriz_xsd(conteudo):
    erros = []
    if not isinstance(conteudo, dict):
        conteudo = {}
        erros.append({"caminho": "$", "codigo": "OBJETO_OBRIGATORIO"})
    campos = {
        "contrato", "operacao", "matriz_contrato", "auditoria_contrato",
        "pacote_sha256", "arquivo_raiz_sha256", "itens", "resumo",
        "compativel_sem_divergencias", "politica",
    }
    if set(conteudo) != campos:
        erros.append({"caminho": "$", "codigo": "CAMPOS_INVALIDOS"})
    if conteudo.get("contrato") != CONTRATO_COMPATIBILIDADE_XSD:
        erros.append({"caminho": "contrato", "codigo": "CONTRATO_INVALIDO"})
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erros.append({"caminho": "operacao", "codigo": "OPERACAO_INVALIDA"})
    if conteudo.get("matriz_contrato") != CONTRATO_MATRIZ_ATOMICA:
        erros.append({"caminho": "matriz_contrato", "codigo": "MATRIZ_INVALIDA"})
    if conteudo.get("auditoria_contrato") != CONTRATO_AUDITORIA_XSD:
        erros.append({"caminho": "auditoria_contrato", "codigo": "AUDITORIA_INVALIDA"})
    for campo_hash in ("pacote_sha256", "arquivo_raiz_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", conteudo.get(campo_hash, "")):
            erros.append({"caminho": campo_hash, "codigo": "HASH_INVALIDO"})
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or len(itens) != len(CAMPOS_ATOMICOS):
        erros.append({"caminho": "itens", "codigo": "ITENS_INCOMPLETOS"})
        itens = []
    vistos = set()
    for indice, item in enumerate(itens):
        if not isinstance(item, dict) or set(item) != {
            "grupo", "campo", "destino_xml_futuro", "estado",
            "alternativas_exigidas", "serializacao_liberada",
        }:
            erros.append({"caminho": f"itens.{indice}", "codigo": "ITEM_INVALIDO"})
            continue
        grupo, campo = CAMPOS_ATOMICOS[indice][:2]
        destino = _destino_xml(grupo, campo)
        if (item["grupo"], item["campo"], item["destino_xml_futuro"]) != (grupo, campo, destino):
            erros.append({"caminho": f"itens.{indice}", "codigo": "DESTINO_DIVERGENTE"})
        identidade = (item["grupo"], item["campo"])
        if identidade in vistos:
            erros.append({"caminho": f"itens.{indice}", "codigo": "ITEM_DUPLICADO"})
        vistos.add(identidade)
        if item["estado"] not in ESTADOS or item["serializacao_liberada"] is not False:
            erros.append({"caminho": f"itens.{indice}", "codigo": "ESTADO_INVALIDO"})
        if type(item["alternativas_exigidas"]) is not int or item["alternativas_exigidas"] < 0:
            erros.append({"caminho": f"itens.{indice}", "codigo": "ALTERNATIVAS_INVALIDAS"})
        estado_sintatico = (
            "PENDENTE_DE_LEIAUTE_APROVADO" if "[" in destino
            else "SEM_TAG_TOTAL_DOCUMENTADA" if destino.endswith("/SEM_CAMPO_TOTAL_ESPECIFICO")
            else None
        )
        if estado_sintatico and item["estado"] != estado_sintatico:
            erros.append({"caminho": f"itens.{indice}", "codigo": "CLASSIFICACAO_DIVERGENTE"})
    resumo_esperado = {estado: sum(item.get("estado") == estado for item in itens) for estado in sorted(ESTADOS)}
    if conteudo.get("resumo") != resumo_esperado:
        erros.append({"caminho": "resumo", "codigo": "RESUMO_DIVERGENTE"})
    if conteudo.get("compativel_sem_divergencias") != (resumo_esperado["DIVERGENTE_DO_XSD_AUDITADO"] == 0):
        erros.append({"caminho": "compativel_sem_divergencias", "codigo": "COMPATIBILIDADE_DIVERGENTE"})
    politica = {
        "aprovar_aplicabilidade": False, "promover_schema": False,
        "gerar_xml": False, "assinar": False, "transmitir": False,
    }
    if conteudo.get("politica") != politica:
        erros.append({"caminho": "politica", "codigo": "POLITICA_INVALIDA"})
    return {
        "estrutura_valida": not erros,
        "quantidade_itens": len(itens),
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }