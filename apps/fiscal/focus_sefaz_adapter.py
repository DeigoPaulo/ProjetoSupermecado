"""Adaptador de emissão fiscal pela API oficial da Focus NFe."""

import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, build_opener
from xml.etree import ElementTree as ET

from django.conf import settings

from .adapters import SefazAdapterError

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
HOSTS = {"homologacao.focusnfe.com.br", "api.focusnfe.com.br"}


class FocusNFeSefazAdapter:
    """Converte o XML validado pelo ERP para o JSON da Focus NFe."""

    assina_xml = True
    valida_schema = True
    preserva_chave_local = False
    nome = "Focus NFe"

    def __init__(self, opener=None):
        self.base_url = (
            getattr(settings, "FOCUS_NFE_FISCAL_BASE_URL", "")
            or "https://homologacao.focusnfe.com.br"
        ).rstrip("/")
        self.timeout = max(
            1, int(getattr(settings, "FOCUS_NFE_FISCAL_TIMEOUT_SECONDS", 30))
        )
        self.allow_production = bool(
            getattr(settings, "FOCUS_NFE_FISCAL_ALLOW_PRODUCTION", False)
        )
        self.opener = opener or build_opener()

    def transmitir(self, *, documento, xml, idempotency_key, ambiente):
        del idempotency_key
        self._validar_ambiente(ambiente)
        token = self._token(documento)
        payload, modelo = self._payload_xml(xml)
        recurso = "nfce" if modelo == "65" else "nfe"
        params = {"ref": self._referencia(documento)}
        if modelo == "65":
            params["completa"] = "1"
        try:
            resposta = self._json(
                f"/v2/{recurso}?{urlencode(params)}",
                token=token,
                method="POST",
                payload=payload,
            )
        except FocusNFeFiscalHTTPError as exc:
            if exc.status_code != 422 or not self._referencia_duplicada(exc.payload):
                raise
            resposta = self._consultar(documento, token, modelo)
        return self._normalizar(resposta, token=token, consulta=False)

    def consultar(self, *, documento, chave_acesso, idempotency_key, ambiente):
        del chave_acesso, idempotency_key
        self._validar_ambiente(ambiente)
        token = self._token(documento)
        try:
            resposta = self._consultar(documento, token, self._modelo(documento))
        except FocusNFeFiscalHTTPError as exc:
            if exc.status_code != 404:
                raise
            return {
                "status": "NAO_LOCALIZADO",
                "mensagem": "Documento não localizado na Focus NFe.",
            }
        return self._normalizar(resposta, token=token, consulta=True)

    def cancelar(
        self,
        *,
        documento,
        chave_acesso,
        protocolo_autorizacao,
        justificativa,
        idempotency_key,
        ambiente,
    ):
        del chave_acesso, protocolo_autorizacao, idempotency_key
        self._validar_ambiente(ambiente)
        token = self._token(documento)
        recurso = "nfce" if self._modelo(documento) == "65" else "nfe"
        resposta = self._json(
            f"/v2/{recurso}/{quote(self._referencia(documento))}",
            token=token,
            method="DELETE",
            payload={"justificativa": justificativa},
        )
        status = self._status(resposta)
        if status in {"cancelado", "autorizado_cancelamento"}:
            return {
                "status": "CANCELADO",
                "protocolo": self._primeiro(
                    resposta, "protocolo_cancelamento", "protocolo"
                ),
                "mensagem": self._mensagem(resposta),
            }
        if status in {"processando_cancelamento", "pendente"}:
            return {"status": "PENDENTE", "mensagem": self._mensagem(resposta)}
        return {
            "status": "REJEITADO",
            "mensagem": self._mensagem(resposta) or "Cancelamento rejeitado.",
        }

    def inutilizar(
        self,
        *,
        inutilizacao,
        cnpj,
        tipo_documento,
        ano,
        serie,
        numero_inicial,
        numero_final,
        justificativa,
        idempotency_key,
        ambiente,
    ):
        del idempotency_key
        self._validar_ambiente(ambiente)
        token = self._token(inutilizacao, cnpj=cnpj)
        recurso = "nfce" if str(tipo_documento).upper() == "NFCE" else "nfe"
        resposta = self._json(
            f"/v2/{recurso}/inutilizacao",
            token=token,
            method="POST",
            payload={
                "cnpj": self._digitos(cnpj),
                "ano": int(ano),
                "serie": int(serie),
                "numero_inicial": int(numero_inicial),
                "numero_final": int(numero_final),
                "justificativa": justificativa,
            },
        )
        status = self._status(resposta)
        if status in {"autorizado", "inutilizado", "inutilizada"}:
            return {
                "status": "INUTILIZADA",
                "protocolo": self._primeiro(
                    resposta, "protocolo", "numero_protocolo"
                ),
                "mensagem": self._mensagem(resposta),
            }
        if status in {"processando", "pendente"}:
            return {"status": "PENDENTE", "mensagem": self._mensagem(resposta)}
        return {
            "status": "REJEITADA",
            "mensagem": self._mensagem(resposta) or "Inutilização rejeitada.",
        }

    def diagnosticar(self):
        try:
            self._validar_url(self.base_url)
            token = bool(
                getattr(settings, "FOCUS_NFE_FISCAL_TOKEN", "")
                or getattr(settings, "FOCUS_NFE_FISCAL_TOKENS", {})
            )
            return {
                "pronto": token,
                "provedor": self.nome,
                "ambiente": "producao" if self._producao() else "homologacao",
                "token_configurado": token,
                "erro": "" if token else "Token fiscal da Focus NFe não configurado.",
            }
        except Exception as exc:
            return {"pronto": False, "provedor": self.nome, "erro": str(exc)}

    def _consultar(self, documento, token, modelo):
        recurso = "nfce" if modelo == "65" else "nfe"
        return self._json(
            f"/v2/{recurso}/{quote(self._referencia(documento))}", token=token
        )

    def _normalizar(self, resposta, *, token, consulta):
        status = self._status(resposta)
        chave = self._digitos(
            self._primeiro(
                resposta, "chave_nfe", "chave_nfce", "chave_acesso", "chave"
            )
        )
        protocolo = str(
            self._primeiro(resposta, "protocolo", "numero_protocolo") or ""
        ).strip()
        mensagem = self._mensagem(resposta)
        if status in {"autorizado", "autorizada", "emitido", "emitida"}:
            xml = self._xml_autorizado(resposta, token)
            if not xml:
                raise FocusNFeFiscalError(
                    "A Focus NFe autorizou o documento, mas não disponibilizou o XML processado."
                )
            chave_xml = self._chave_xml(xml)
            chave = chave or chave_xml
            if chave != chave_xml:
                raise FocusNFeFiscalError(
                    "A chave retornada não corresponde ao XML autorizado."
                )
            return {
                "status": "AUTORIZADO",
                "chave_acesso": chave,
                "protocolo": protocolo,
                "mensagem": mensagem or "Documento autorizado pela Focus NFe.",
                "xml_autorizado": xml,
            }
        if consulta and status in {"cancelado", "cancelada"}:
            return {
                "status": "CANCELADO",
                "chave_acesso": chave,
                "protocolo": protocolo,
                "protocolo_cancelamento": self._primeiro(
                    resposta, "protocolo_cancelamento", "protocolo"
                ),
                "mensagem": mensagem or "Documento cancelado.",
            }
        if consulta and status in {"denegado", "denegada"}:
            return {
                "status": "DENEGADO",
                "chave_acesso": chave,
                "protocolo": protocolo,
                "mensagem": mensagem or "Documento denegado.",
            }
        if status in {
            "processando_autorizacao",
            "processando",
            "pendente",
            "em_processamento",
        }:
            return {
                "status": "PENDENTE",
                "chave_acesso": chave,
                "mensagem": mensagem or "Documento em processamento na Focus NFe.",
            }
        if consulta:
            return {
                "status": "NAO_LOCALIZADO",
                "mensagem": mensagem or "Documento não localizado na Focus NFe.",
            }
        return {
            "status": "REJEITADO",
            "mensagem": mensagem or "Documento rejeitado pela Focus NFe.",
        }

    def _payload_xml(self, xml):
        try:
            raiz = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise FocusNFeFiscalError("O XML fiscal local está inválido.") from exc
        inf = raiz.find(".//nfe:infNFe", NS)
        if inf is None:
            raise FocusNFeFiscalError("O XML fiscal não possui o grupo infNFe.")
        ide = inf.find("nfe:ide", NS)
        emit = inf.find("nfe:emit", NS)
        dest = inf.find("nfe:dest", NS)
        modelo = self._texto(ide, "mod")
        if modelo not in {"55", "65"}:
            raise FocusNFeFiscalError("Modelo fiscal não suportado pela Focus NFe.")
        payload = {
            "natureza_operacao": self._texto(ide, "natOp"),
            "data_emissao": self._texto(ide, "dhEmi"),
            "tipo_documento": self._texto(ide, "tpNF") or "1",
            "local_destino": self._texto(ide, "idDest") or "1",
            "finalidade_emissao": self._texto(ide, "finNFe") or "1",
            "consumidor_final": self._texto(ide, "indFinal") or "1",
            "presenca_comprador": self._texto(ide, "indPres") or "1",
            "cnpj_emitente": self._texto(emit, "CNPJ"),
            "numero": self._texto(ide, "nNF"),
            "serie": self._texto(ide, "serie"),
            "modalidade_frete": self._texto(
                inf.find("nfe:transp", NS), "modFrete"
            ) or "9",
            "items": [self._item(det) for det in inf.findall("nfe:det", NS)],
        }
        self._destinatario(payload, dest, modelo)
        pagamentos = [
            {
                "indicador_pagamento": self._texto(det, "indPag") or "0",
                "forma_pagamento": self._texto(det, "tPag"),
                "valor_pagamento": self._texto(det, "vPag"),
            }
            for det in inf.findall("nfe:pag/nfe:detPag", NS)
        ]
        if pagamentos:
            payload["formas_pagamento"] = pagamentos
        complemento = self._texto(inf.find("nfe:infAdic", NS), "infCpl")
        if complemento:
            payload["informacoes_adicionais_contribuinte"] = complemento
        return payload, modelo

    def _item(self, det):
        prod = det.find("nfe:prod", NS)
        imposto = det.find("nfe:imposto", NS)
        item = {
            "numero_item": det.attrib.get("nItem"),
            "codigo_produto": self._texto(prod, "cProd"),
            "descricao": self._texto(prod, "xProd"),
            "codigo_ncm": self._texto(prod, "NCM"),
            "cfop": self._texto(prod, "CFOP"),
            "unidade_comercial": self._texto(prod, "uCom"),
            "quantidade_comercial": self._texto(prod, "qCom"),
            "valor_unitario_comercial": self._texto(prod, "vUnCom"),
            "valor_bruto": self._texto(prod, "vProd"),
            "unidade_tributavel": self._texto(prod, "uTrib"),
            "quantidade_tributavel": self._texto(prod, "qTrib"),
            "valor_unitario_tributavel": self._texto(prod, "vUnTrib"),
            "inclui_no_total": self._texto(prod, "indTot") or "1",
        }
        self._copiar(
            item,
            prod,
            {
                "codigo_barras_comercial": "cEAN",
                "codigo_barras_tributavel": "cEANTrib",
                "codigo_cest": "CEST",
                "codigo_beneficio_fiscal": "cBenef",
                "valor_desconto": "vDesc",
            },
            ignorar={"SEM GTIN"},
        )
        icms = imposto.find("nfe:ICMS", NS) if imposto is not None else None
        grupo_icms = next(iter(icms), None) if icms is not None else None
        if grupo_icms is not None:
            item["icms_origem"] = self._texto(grupo_icms, "orig")
            item["icms_situacao_tributaria"] = (
                self._texto(grupo_icms, "CST")
                or self._texto(grupo_icms, "CSOSN")
            )
            self._copiar(
                item,
                grupo_icms,
                {
                    "icms_modalidade_base_calculo": "modBC",
                    "icms_base_calculo": "vBC",
                    "icms_reducao_base_calculo": "pRedBC",
                    "icms_aliquota": "pICMS",
                    "icms_valor": "vICMS",
                },
            )
        self._contribuicao(item, imposto, "PIS", "pis")
        self._contribuicao(item, imposto, "COFINS", "cofins")
        self._ipi(item, imposto)
        return item

    def _ipi(self, item, imposto):
        grupo = imposto.find("nfe:IPI", NS) if imposto is not None else None
        if grupo is None:
            return
        enquadramento = self._texto(grupo, "cEnq")
        detalhe = next(
            (
                filho
                for filho in grupo
                if filho.tag.rsplit("}", 1)[-1] in {"IPINT", "IPITrib"}
            ),
            None,
        )
        if detalhe is None:
            return
        if enquadramento:
            item["ipi_codigo_enquadramento_legal"] = enquadramento
        item["ipi_situacao_tributaria"] = self._texto(detalhe, "CST")
        self._copiar(
            item,
            detalhe,
            {
                "ipi_base_calculo": "vBC",
                "ipi_aliquota": "pIPI",
                "ipi_valor": "vIPI",
            },
        )

    def _contribuicao(self, item, imposto, tag, prefixo):
        grupo = imposto.find(f"nfe:{tag}", NS) if imposto is not None else None
        detalhe = next(iter(grupo), None) if grupo is not None else None
        if detalhe is None:
            return
        item[f"{prefixo}_situacao_tributaria"] = self._texto(detalhe, "CST")
        self._copiar(
            item,
            detalhe,
            {
                f"{prefixo}_base_calculo": "vBC",
                f"{prefixo}_aliquota_porcentual": f"p{tag}",
                f"{prefixo}_valor": f"v{tag}",
            },
        )

    def _destinatario(self, payload, dest, modelo):
        if dest is None:
            if modelo == "55":
                raise FocusNFeFiscalError("NF-e exige destinatário completo.")
            return
        self._copiar(
            payload,
            dest,
            {
                "cpf_destinatario": "CPF",
                "cnpj_destinatario": "CNPJ",
                "id_estrangeiro_destinatario": "idEstrangeiro",
                "nome_destinatario": "xNome",
                "indicador_inscricao_estadual_destinatario": "indIEDest",
            },
        )
        endereco = dest.find("nfe:enderDest", NS)
        if modelo == "55" and endereco is None:
            raise FocusNFeFiscalError(
                "NF-e ainda não pode ser enviada: cadastre o endereço estruturado do destinatário."
            )
        if endereco is not None:
            self._copiar(
                payload,
                endereco,
                {
                    "logradouro_destinatario": "xLgr",
                    "numero_destinatario": "nro",
                    "complemento_destinatario": "xCpl",
                    "bairro_destinatario": "xBairro",
                    "municipio_destinatario": "xMun",
                    "uf_destinatario": "UF",
                    "cep_destinatario": "CEP",
                    "codigo_municipio_destinatario": "cMun",
                    "telefone_destinatario": "fone",
                },
            )

    def _xml_autorizado(self, resposta, token):
        for campo in ("xml", "xml_nfe", "xml_nfce", "xml_completo"):
            valor = resposta.get(campo)
            if isinstance(valor, str) and "<" in valor:
                return valor
        caminho = self._primeiro(
            resposta, "caminho_xml_nota_fiscal", "url_xml", "caminho_xml"
        )
        if not caminho:
            return ""
        try:
            return self._request(
                str(caminho), token=token, accept="application/xml"
            ).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FocusNFeFiscalError(
                "O XML autorizado possui codificação inválida."
            ) from exc

    def _json(self, path, *, token, method="GET", payload=None):
        conteudo = self._request(
            path, token=token, method=method, payload=payload
        )
        try:
            resposta = json.loads(conteudo.decode("utf-8-sig") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FocusNFeFiscalError(
                "A Focus NFe retornou uma resposta inválida."
            ) from exc
        if not isinstance(resposta, dict):
            raise FocusNFeFiscalError("Resposta inesperada da Focus NFe.")
        return resposta

    def _request(
        self, path, *, token, method="GET", payload=None, accept="application/json"
    ):
        url = (
            path
            if urlparse(path).scheme
            else urljoin(f"{self.base_url}/", path.lstrip("/"))
        )
        self._validar_url(url)
        dados = None
        headers = {
            "Accept": accept,
            "Authorization": "Basic "
            + base64.b64encode(f"{token}:".encode()).decode("ascii"),
            "User-Agent": "Deigo-Varejo-ERP/1.0",
        }
        if payload is not None:
            dados = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            with self.opener.open(
                Request(url, data=dados, headers=headers, method=method),
                timeout=self.timeout,
            ) as resposta:
                return resposta.read()
        except HTTPError as exc:
            corpo = exc.read()
            try:
                erro = json.loads(corpo.decode("utf-8-sig") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                erro = {}
            mensagem = self._mensagem(erro) or {
                401: "Token da Focus NFe inválido ou sem permissão.",
                403: "A Focus NFe recusou o acesso desta empresa.",
                404: "Documento não localizado na Focus NFe.",
                422: "A Focus NFe rejeitou os dados fiscais enviados.",
                429: "Limite temporário de requisições da Focus NFe atingido.",
            }.get(exc.code, "Falha HTTP na comunicação com a Focus NFe.")
            raise FocusNFeFiscalHTTPError(exc.code, mensagem, erro) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(
                "Não foi possível conectar à Focus NFe. Verifique internet, DNS e TLS."
            ) from exc

    def _token(self, objeto, cnpj=""):
        if not cnpj:
            filial = getattr(objeto, "filial", None)
            empresa = getattr(filial, "empresa", None)
            cnpj = getattr(filial, "cnpj", "") or getattr(empresa, "cnpj", "")
        cnpj = self._digitos(cnpj)
        tokens = getattr(settings, "FOCUS_NFE_FISCAL_TOKENS", {}) or {}
        token = str(
            tokens.get(cnpj)
            or getattr(settings, "FOCUS_NFE_FISCAL_TOKEN", "")
            or ""
        ).strip()
        if not token:
            raise FocusNFeFiscalError(
                f"Token fiscal da Focus NFe não configurado para o CNPJ {cnpj or 'da filial'}."
            )
        return token

    def _validar_ambiente(self, ambiente):
        self._validar_url(self.base_url)
        producao = str(ambiente).upper() == "PRODUCAO"
        if producao != self._producao():
            raise FocusNFeFiscalError(
                "O ambiente do documento não corresponde ao endpoint da Focus NFe."
            )
        if producao and not self.allow_production:
            raise FocusNFeFiscalError(
                "Produção Focus NFe bloqueada. Homologue e habilite "
                "FOCUS_NFE_FISCAL_ALLOW_PRODUCTION."
            )

    @staticmethod
    def _validar_url(url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS:
            raise FocusNFeFiscalError(
                "A URL fiscal deve usar HTTPS em um domínio oficial da Focus NFe."
            )
        if parsed.username or parsed.password:
            raise FocusNFeFiscalError("Não informe credenciais na URL da Focus NFe.")

    def _producao(self):
        return urlparse(self.base_url).hostname == "api.focusnfe.com.br"

    @staticmethod
    def _modelo(documento):
        return "65" if str(documento.tipo_documento).upper() == "NFCE" else "55"

    @staticmethod
    def _referencia(documento):
        return f"detec-{str(documento.tipo_documento).lower()}-{documento.pk}"

    @staticmethod
    def _status(resposta):
        return str(
            resposta.get("status") or resposta.get("situacao") or ""
        ).strip().lower()

    @classmethod
    def _mensagem(cls, resposta):
        if not isinstance(resposta, dict):
            return ""
        valor = cls._primeiro(
            resposta, "mensagem", "mensagem_sefaz", "erro", "message"
        )
        if isinstance(valor, (dict, list)):
            return json.dumps(valor, ensure_ascii=False)[:2000]
        return str(valor or "").strip()[:2000]

    @staticmethod
    def _referencia_duplicada(payload):
        texto = json.dumps(payload or {}, ensure_ascii=False).lower()
        return "refer" in texto and any(
            termo in texto for termo in ("existe", "utilizada", "duplic")
        )

    @staticmethod
    def _chave_xml(xml):
        try:
            raiz = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise FocusNFeFiscalError("O XML autorizado está inválido.") from exc
        inf = raiz.find(".//nfe:infNFe", NS)
        chave = re.sub(
            r"\D", "", inf.attrib.get("Id", "") if inf is not None else ""
        )
        if len(chave) != 44:
            raise FocusNFeFiscalError(
                "O XML autorizado não contém uma chave válida."
            )
        return chave

    @staticmethod
    def _texto(elemento, tag):
        if elemento is None:
            return ""
        filho = elemento.find(f"nfe:{tag}", NS)
        return (filho.text or "").strip() if filho is not None else ""

    @classmethod
    def _copiar(cls, destino, origem, campos, ignorar=None):
        ignorar = ignorar or set()
        for destino_nome, origem_nome in campos.items():
            valor = cls._texto(origem, origem_nome)
            if valor and valor not in ignorar:
                destino[destino_nome] = valor

    @staticmethod
    def _primeiro(dados, *campos):
        for campo in campos:
            valor = dados.get(campo) if isinstance(dados, dict) else None
            if valor not in (None, ""):
                return valor
        return ""

    @staticmethod
    def _digitos(valor):
        return re.sub(r"\D", "", str(valor or ""))


class FocusNFeFiscalError(SefazAdapterError):
    pass


class FocusNFeFiscalHTTPError(FocusNFeFiscalError):
    def __init__(self, status_code, mensagem, payload=None):
        self.status_code = status_code
        self.payload = payload or {}
        super().__init__(mensagem)
