import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string


CONTRATO_ADAPTADOR_EXTRATO = "financial_statement_adapter_v1"


@dataclass(frozen=True)
class ExtratoAdapterInfo:
    codigo: str
    nome: str
    extensoes: tuple[str, ...]
    contrato: str = CONTRATO_ADAPTADOR_EXTRATO


class CSVGenericoExtratoAdapter:
    codigo = "CSV_GENERICO"
    nome = "CSV genérico do ERP"
    extensoes = (".csv",)

    def ler(self, *, conteudo, arquivo_nome):
        from .services_conciliacao import ler_extrato_csv

        return ler_extrato_csv(conteudo)


class OFXExtratoAdapter:
    codigo = "OFX"
    nome = "OFX bancário"
    extensoes = (".ofx",)

    @staticmethod
    def _decodificar(conteudo):
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return conteudo.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValidationError("Não foi possível identificar a codificação do arquivo OFX.")

    @staticmethod
    def _campo(bloco, nome):
        correspondencia = re.search(
            rf"<{nome}>\s*([^<\r\n]+)",
            bloco,
            flags=re.IGNORECASE,
        )
        return correspondencia.group(1).strip() if correspondencia else ""

    def ler(self, *, conteudo, arquivo_nome):
        texto = self._decodificar(conteudo)
        blocos = re.findall(
            r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))",
            texto,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not blocos:
            raise ValidationError("O arquivo OFX não contém movimentações STMTTRN.")

        itens = []
        referencias = set()
        for indice, bloco in enumerate(blocos, start=1):
            data_bruta = self._campo(bloco, "DTPOSTED")
            valor_bruto = self._campo(bloco, "TRNAMT").replace(",", ".")
            referencia = self._campo(bloco, "FITID")
            tipo_ofx = self._campo(bloco, "TRNTYPE")
            descricao = (
                self._campo(bloco, "MEMO")
                or self._campo(bloco, "NAME")
                or tipo_ofx
                or "Movimentação OFX"
            )
            if len(data_bruta) < 8 or not data_bruta[:8].isdigit():
                raise ValidationError(f"Movimentação OFX {indice}: DTPOSTED inválido.")
            if not referencia:
                raise ValidationError(f"Movimentação OFX {indice}: FITID ausente.")
            if referencia in referencias:
                raise ValidationError(f"Movimentação OFX {indice}: FITID duplicado ({referencia}).")
            referencias.add(referencia)
            try:
                valor = Decimal(valor_bruto).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                raise ValidationError(f"Movimentação OFX {indice}: TRNAMT inválido.")
            if valor == 0:
                raise ValidationError(f"Movimentação OFX {indice}: o valor não pode ser zero.")
            itens.append(
                {
                    "numero_linha": indice,
                    "data": f"{data_bruta[:4]}-{data_bruta[4:6]}-{data_bruta[6:8]}",
                    "tipo": "entrada" if valor > 0 else "saida",
                    "valor": abs(valor),
                    "descricao": descricao,
                    "referencia_externa": referencia,
                }
            )
        return itens


_ADAPTADORES_NATIVOS = {
    "CSV_GENERICO": CSVGenericoExtratoAdapter,
    "OFX": OFXExtratoAdapter,
}


def _codigo_normalizado(codigo):
    codigo = str(codigo or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_]{2,40}", codigo):
        raise ImproperlyConfigured("Código de adaptador de extrato inválido.")
    return codigo


def _registro_adaptadores():
    registro = dict(_ADAPTADORES_NATIVOS)
    configurados = getattr(settings, "FINANCEIRO_EXTRATO_ADAPTERS", {}) or {}
    if not isinstance(configurados, dict):
        raise ImproperlyConfigured("FINANCEIRO_EXTRATO_ADAPTERS deve ser um objeto JSON.")
    for codigo, caminho in configurados.items():
        codigo = _codigo_normalizado(codigo)
        if codigo in _ADAPTADORES_NATIVOS:
            raise ImproperlyConfigured(f"O adaptador nativo {codigo} não pode ser sobrescrito.")
        if not isinstance(caminho, str) or not caminho.strip():
            raise ImproperlyConfigured(f"Informe a classe do adaptador {codigo}.")
        registro[codigo] = caminho.strip()
    return registro


def carregar_adaptador_extrato(codigo):
    codigo = _codigo_normalizado(codigo)
    registro = _registro_adaptadores()
    referencia = registro.get(codigo)
    if not referencia:
        raise ImproperlyConfigured(f"Adaptador de extrato não registrado: {codigo}.")
    try:
        classe = import_string(referencia) if isinstance(referencia, str) else referencia
        adaptador = classe()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ImproperlyConfigured(f"Não foi possível carregar o adaptador de extrato {codigo}.") from exc
    if not callable(getattr(adaptador, "ler", None)):
        raise ImproperlyConfigured(f"O adaptador {codigo} deve implementar o método ler.")
    extensoes = tuple(str(item).lower() for item in getattr(adaptador, "extensoes", ()) if str(item).startswith("."))
    if not extensoes:
        raise ImproperlyConfigured(f"O adaptador {codigo} deve declarar extensões aceitas.")
    return adaptador


def info_adaptador_extrato(codigo):
    codigo = _codigo_normalizado(codigo)
    adaptador = carregar_adaptador_extrato(codigo)
    return ExtratoAdapterInfo(
        codigo=codigo,
        nome=str(getattr(adaptador, "nome", codigo)).strip()[:120] or codigo,
        extensoes=tuple(str(item).lower() for item in adaptador.extensoes),
    )


def listar_adaptadores_extrato():
    infos = []
    erros = []
    try:
        codigos = sorted(_registro_adaptadores())
    except ImproperlyConfigured as exc:
        return infos, [{"codigo": "", "erro": str(exc)}]
    for codigo in codigos:
        try:
            infos.append(info_adaptador_extrato(codigo))
        except ImproperlyConfigured as exc:
            erros.append({"codigo": codigo, "erro": str(exc)})
    return infos, erros


def validar_arquivo_adaptador(*, codigo, arquivo_nome):
    info = info_adaptador_extrato(codigo)
    nome = str(arquivo_nome or "").lower()
    if not any(nome.endswith(extensao) for extensao in info.extensoes):
        aceitas = ", ".join(info.extensoes)
        raise ValidationError(f"O layout {info.nome} aceita somente: {aceitas}.")
    return info
