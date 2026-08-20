import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .dfe_adapters import CONTRATO_DISTRIBUICAO_DFE


class FocusNFeDFeAdapter:
    """Consulta NF-e recebidas na Focus sem manifestar ou criar operações."""

    nome = "Focus NFe"

    def __init__(self, opener=None):
        self.base_url = (getattr(settings, "FOCUS_NFE_DFE_BASE_URL", "") or "").rstrip("/")
        self.timeout = max(1, int(getattr(settings, "FOCUS_NFE_DFE_TIMEOUT_SECONDS", 20)))
        self.fetch_xml = bool(getattr(settings, "FOCUS_NFE_DFE_FETCH_XML", True))
        self.allow_production = bool(
            getattr(settings, "FOCUS_NFE_DFE_ALLOW_PRODUCTION", False)
        )
        self._opener = opener or urlopen

    def diagnosticar(self):
        try:
            self._validar_base_url()
        except ImproperlyConfigured as exc:
            return {
                "disponivel": False,
                "mensagem": str(exc),
                "ambiente": "inválido",
            }
        tokens = getattr(settings, "FOCUS_NFE_DFE_TOKENS", {}) or {}
        token_global = (getattr(settings, "FOCUS_NFE_DFE_TOKEN", "") or "").strip()
        disponivel = bool(token_global or tokens)
        ambiente = "produção" if self._producao else "homologação"
        return {
            "disponivel": disponivel,
            "mensagem": (
                f"Focus NFe pronta em {ambiente}."
                if disponivel
                else "Configure o token Focus NFe no .env para consultar documentos recebidos."
            ),
            "ambiente": ambiente,
        }

    def consultar(self, *, cnpj, ultimo_nsu="", limite=100):
        self._validar_base_url()
        cnpj = self._digitos(cnpj)
        if len(cnpj) != 14:
            raise ValueError("O CNPJ da consulta Focus NFe deve possuir 14 dígitos.")
        token = self._token_para_cnpj(cnpj)
        if not token:
            raise ImproperlyConfigured(
                "Não há token Focus NFe configurado para o CNPJ consultado."
            )

        cursor = str(ultimo_nsu or "").strip()
        if cursor and not cursor.isdigit():
            raise ValueError("O cursor Focus NFe deve ser numérico.")
        parametros = {"cnpj": cnpj}
        if cursor:
            parametros["versao"] = cursor
        dados, headers = self._request_json(
            f"/v2/nfes_recebidas?{urlencode(parametros)}", token=token
        )
        if not isinstance(dados, list):
            raise ValueError("A Focus NFe retornou uma lista de documentos inválida.")

        limite = max(1, min(int(limite), 100))
        documentos = []
        for bruto in dados[:limite]:
            documento = self._normalizar_documento(bruto, cnpj=cnpj)
            if self.fetch_xml and documento["chave_acesso"] and not documento.get("xml"):
                xml = self._consultar_xml_disponivel(
                    chave=documento["chave_acesso"], cnpj=cnpj, token=token
                )
                if xml:
                    documento["xml"] = xml
                    documento["schema"] = "procNFe"
            documentos.append(documento)

        versoes = [int(item["nsu"]) for item in documentos if item.get("nsu")]
        cursor_processado = str(max(versoes)) if versoes else cursor
        max_versao = self._cabecalho(headers, "X-Max-Version")
        if not str(max_versao or "").isdigit():
            max_versao = cursor_processado
        total = self._cabecalho(headers, "X-Total-Count") or len(dados)
        return {
            "contrato": CONTRATO_DISTRIBUICAO_DFE,
            "documentos": documentos,
            "ultimo_nsu": cursor_processado,
            "max_nsu": str(max_versao or cursor_processado),
            "mensagem": (
                f"Focus NFe: {len(documentos)} documento(s) processado(s) "
                f"de {total} registro(s) disponível(is)."
            ),
        }

    @property
    def _producao(self):
        return urlparse(self.base_url).hostname == "api.focusnfe.com.br"

    def _validar_base_url(self):
        url = urlparse(self.base_url)
        if url.scheme != "https" or not url.hostname:
            raise ImproperlyConfigured(
                "FOCUS_NFE_DFE_BASE_URL deve ser uma URL HTTPS válida."
            )
        hosts_oficiais = {
            "homologacao.focusnfe.com.br",
            "api.focusnfe.com.br",
        }
        if url.hostname not in hosts_oficiais:
            raise ImproperlyConfigured(
                "FOCUS_NFE_DFE_BASE_URL deve apontar para um ambiente oficial da Focus NFe."
            )
        if self._producao and not self.allow_production:
            raise ImproperlyConfigured(
                "A integração DF-e Focus em produção está bloqueada. "
                "Homologue primeiro e habilite FOCUS_NFE_DFE_ALLOW_PRODUCTION explicitamente."
            )

    def _token_para_cnpj(self, cnpj):
        tokens = getattr(settings, "FOCUS_NFE_DFE_TOKENS", {}) or {}
        for chave, token in tokens.items():
            if self._digitos(str(chave)) == cnpj and str(token).strip():
                return str(token).strip()
        return (getattr(settings, "FOCUS_NFE_DFE_TOKEN", "") or "").strip()

    def _request_json(self, caminho, *, token):
        resposta = self._request(caminho, token=token, accept="application/json")
        try:
            dados = json.loads(resposta[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("A Focus NFe retornou JSON inválido.") from exc
        return dados, resposta[1]

    def _request(self, caminho, *, token, accept):
        url = urljoin(f"{self.base_url}/", caminho.lstrip("/"))
        credencial = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        requisicao = Request(
            url,
            headers={
                "Accept": accept,
                "Authorization": f"Basic {credencial}",
                "User-Agent": "DeTecServer/FocusDFe",
            },
            method="GET",
        )
        try:
            with self._opener(requisicao, timeout=self.timeout) as resposta:
                return resposta.read(), resposta.headers
        except HTTPError as exc:
            mensagens = {
                400: "A Focus NFe recusou os parâmetros da consulta.",
                401: "O token Focus NFe não foi autorizado.",
                403: "A conta Focus NFe não permite esta consulta.",
                404: "Documento não encontrado na Focus NFe.",
                429: "Limite de consultas da Focus NFe atingido; tente novamente depois.",
            }
            raise FocusNFeDFeHTTPError(
                exc.code, mensagens.get(exc.code, "Falha HTTP ao consultar a Focus NFe.")
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(
                "Não foi possível conectar à Focus NFe. Verifique internet, DNS e TLS."
            ) from exc

    def _consultar_xml_disponivel(self, *, chave, cnpj, token):
        del cnpj  # A chave de acesso identifica a NF-e no endpoint oficial de XML.
        try:
            conteudo, _ = self._request(
                f"/v2/nfes_recebidas/{chave}.xml",
                token=token,
                accept="application/xml",
            )
        except FocusNFeDFeHTTPError as exc:
            if exc.status_code == 404:
                return ""
            raise
        try:
            xml = conteudo.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("A Focus NFe retornou um XML com codificação inválida.") from exc
        return xml if "<" in xml else ""

    def _normalizar_documento(self, bruto, *, cnpj):
        if not isinstance(bruto, dict):
            raise ValueError("A Focus NFe retornou um documento inválido.")
        chave = self._digitos(
            self._primeiro(
                bruto,
                "chave_nfe",
                "chave_acesso",
                "chave",
                "chave_nota_fiscal",
            )
        )
        if len(chave) != 44:
            raise ValueError("A Focus NFe retornou uma chave de acesso inválida.")
        versao = str(self._primeiro(bruto, "versao", "version") or "").strip()
        if not versao.isdigit():
            raise ValueError("A Focus NFe retornou uma versão de documento inválida.")
        xml = self._primeiro(bruto, "xml", "xml_nfe", "xml_completo", "conteudo_xml")
        if not isinstance(xml, str) or "<" not in xml:
            xml = ""
        return {
            "nsu": versao,
            "chave_acesso": chave,
            "destinatario_cnpj": cnpj,
            "emitente_cnpj": self._digitos(
                self._primeiro(bruto, "cnpj_emitente", "emitente_cnpj", "cnpj_emissor")
            ),
            "emitente_nome": self._primeiro(
                bruto, "nome_emitente", "razao_social_emitente", "emitente_nome"
            ),
            "numero_documento": self._primeiro(
                bruto, "numero", "numero_nfe", "numero_documento"
            ),
            "data_emissao": self._primeiro(
                bruto, "data_emissao", "emitida_em", "data_emissao_nfe"
            ),
            "valor_total": self._primeiro(bruto, "valor_total", "valor_nfe", "total"),
            "schema": "procNFe" if xml else "resNFe",
            "xml": xml,
        }

    @staticmethod
    def _primeiro(dados, *campos):
        for campo in campos:
            valor = dados.get(campo)
            if valor not in (None, ""):
                return valor
        return ""

    @staticmethod
    def _cabecalho(headers, nome):
        if hasattr(headers, "get"):
            return headers.get(nome) or headers.get(nome.lower())
        return ""

    @staticmethod
    def _digitos(valor):
        return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


class FocusNFeDFeHTTPError(RuntimeError):
    def __init__(self, status_code, mensagem):
        self.status_code = status_code
        super().__init__(mensagem)