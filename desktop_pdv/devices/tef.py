from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from copy import deepcopy
from uuid import uuid4


class ErroTef(RuntimeError):
    pass


class AdaptadorTefIndisponivel(ErroTef):
    pass


class RespostaTefInvalida(ErroTef):
    pass


class AdaptadorTef(ABC):
    @abstractmethod
    def processar(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def consultar(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def estornar(self, payload: dict) -> dict:
        raise NotImplementedError

    def capturar_documento(self, payload: dict) -> dict:
        raise AdaptadorTefIndisponivel(
            "O driver TEF instalado nao permite capturar CPF/CNPJ pelo pinpad."
        )


class SimuladorTef(AdaptadorTef):
    def __init__(self, provedor: str, modo: str):
        self.provedor = provedor
        self.modo = modo
        self._pendentes: dict[str, dict] = {}

    def processar(self, payload: dict) -> dict:
        referencia = uuid4().hex.upper()
        tipo = payload["tipo"]
        valor = payload["valor"]
        transacao = f"TEF-SIM-{referencia[:16]}"
        aprovado = {
            "status": "ok",
            "aprovado": True,
            "tipo": tipo,
            "valor": valor,
            "provedor": self.provedor,
            "modo": self.modo,
            "transacao_externa_id": transacao,
            "nsu": referencia[16:28],
            "codigo_autorizacao": referencia[28:34],
            "mensagem_processadora": "Pagamento aprovado pelo simulador TEF do app desktop.",
        }
        if tipo != "PIX":
            return aprovado

        pix = f"DEIGO-PDV-SIMULACAO|TXID={referencia[:25]}|VALOR={valor}"
        pendente = {
            "status": "pending",
            "aprovado": False,
            "tipo": tipo,
            "valor": valor,
            "provedor": self.provedor,
            "modo": self.modo,
            "transacao_externa_id": transacao,
            "pix_qr_code": pix,
            "pix_simulado": True,
            "mensagem_processadora": "QR Code PIX gerado. Aguardando confirmacao do pagamento.",
        }
        self._pendentes[transacao] = {
            "consultas": 0,
            "pendente": pendente,
            "aprovado": aprovado,
        }
        return deepcopy(pendente)

    def consultar(self, payload: dict) -> dict:
        transacao = str(payload.get("transacao_externa_id") or "").strip()
        registro = self._pendentes.get(transacao)
        if not registro:
            raise ErroTef("Transacao PIX nao encontrada neste terminal.")
        registro["consultas"] += 1
        if registro["consultas"] < 2:
            return deepcopy(registro["pendente"])
        return deepcopy(registro["aprovado"])

    def estornar(self, payload: dict) -> dict:
        referencia = uuid4().hex.upper()
        return {
            "status": "ok",
            "estornado": True,
            "tipo": payload.get("tipo", ""),
            "valor": payload["valor"],
            "provedor": self.provedor,
            "modo": self.modo,
            "transacao_externa_id": payload["transacao_externa_id"],
            "estorno_transacao_id": f"TEF-SIM-REF-{referencia[:16]}",
            "nsu": referencia[16:28],
            "codigo_autorizacao": referencia[28:34],
            "mensagem_processadora": "Estorno aprovado pelo simulador TEF do app desktop.",
        }

    def capturar_documento(self, payload: dict) -> dict:
        tipo_solicitado = str(payload.get("tipo") or "AUTO").strip().upper()
        tipo = "CNPJ" if tipo_solicitado == "CNPJ" else "CPF"
        documento = "11222333000181" if tipo == "CNPJ" else "52998224725"
        return {
            "status": "ok",
            "tipo": tipo,
            "documento": documento,
            "origem": "pinpad",
            "simulado": True,
            "mensagem": "Documento recebido pelo simulador do pinpad.",
        }


def _carregar_fabrica(caminho: str):
    modulo_nome, separador, atributo = caminho.partition(":")
    if not separador or not modulo_nome or not atributo:
        raise AdaptadorTefIndisponivel(
            "Adaptador TEF local invalido. Use o formato pacote.modulo:fabrica."
        )
    try:
        modulo = importlib.import_module(modulo_nome)
        fabrica = getattr(modulo, atributo)
    except (ImportError, AttributeError) as exc:
        raise AdaptadorTefIndisponivel(
            "O driver TEF configurado nao esta instalado nesta maquina."
        ) from exc
    if not callable(fabrica):
        raise AdaptadorTefIndisponivel("A fabrica do adaptador TEF nao e executavel.")
    return fabrica


def criar_adaptador_tef(config_local: dict, configuracao_servidor: dict) -> AdaptadorTef:
    provedor = str(configuracao_servidor.get("provedor") or "NAO_CONFIGURADO").upper()
    modo = str(configuracao_servidor.get("modo_integracao") or "DESKTOP_BRIDGE").upper()
    local = dict((config_local or {}).get("tef") or {})
    adaptador = str(local.get("adaptador") or ("SIMULADOR" if configuracao_servidor.get("simulador_permitido") else "")).strip()

    if provedor == "NAO_CONFIGURADO":
        raise AdaptadorTefIndisponivel("TEF/maquininha nao configurado para este terminal.")

    if adaptador.upper() == "SIMULADOR":
        if not configuracao_servidor.get("simulador_permitido"):
            raise AdaptadorTefIndisponivel(
                "O simulador TEF nao foi autorizado pelo servidor para este ambiente."
            )
        return SimuladorTef(provedor, "SIMULADOR")

    if not adaptador:
        raise AdaptadorTefIndisponivel(
            f"Driver TEF do provedor {provedor} nao instalado nesta maquina."
        )

    fabrica = _carregar_fabrica(adaptador)
    try:
        instancia = fabrica(
            provedor=provedor,
            modo=modo,
            configuracao=dict(local.get("configuracao") or {}),
        )
    except Exception as exc:
        raise AdaptadorTefIndisponivel(
            f"O driver TEF do provedor {provedor} falhou ao inicializar."
        ) from exc
    for metodo in ("processar", "consultar", "estornar"):
        if not callable(getattr(instancia, metodo, None)):
            raise AdaptadorTefIndisponivel(
                f"O adaptador TEF local nao implementa o metodo obrigatorio {metodo}."
            )
    return instancia


def validar_resposta_tef(resultado: dict, operacao: str) -> dict:
    if not isinstance(resultado, dict):
        raise RespostaTefInvalida("O driver TEF devolveu uma resposta invalida.")
    status = str(resultado.get("status") or "").lower()
    if status not in {"ok", "pending", "erro", "recusado", "cancelado"}:
        raise RespostaTefInvalida("O driver TEF devolveu um status desconhecido.")

    if operacao == "estorno":
        if status == "ok" and not resultado.get("estornado"):
            raise RespostaTefInvalida("O driver TEF nao confirmou o estorno.")
    elif status == "ok":
        obrigatorios = ("transacao_externa_id", "nsu", "codigo_autorizacao")
        if not resultado.get("aprovado") or any(not resultado.get(campo) for campo in obrigatorios):
            raise RespostaTefInvalida("O driver TEF nao devolveu a autorizacao completa.")
    elif status == "pending" and not resultado.get("transacao_externa_id"):
        raise RespostaTefInvalida("O driver TEF nao identificou a transacao pendente.")
    normalizado = dict(resultado)
    if status not in {"ok", "pending"}:
        normalizado.setdefault("aprovado", False)
        normalizado.setdefault("estornado", False)
    return normalizado

def capacidades_adaptador_tef(adaptador) -> dict:
    metodo = getattr(adaptador, "capturar_documento", None)
    implementado = callable(metodo)
    if isinstance(adaptador, AdaptadorTef):
        implementado = implementado and type(adaptador).capturar_documento is not AdaptadorTef.capturar_documento
    return {
        "contrato": "pdv_tef_capabilities_v1",
        "captura_documento_consumidor": bool(implementado),
    }


def _documento_valido(documento: str) -> bool:
    tamanho = len(documento)
    if tamanho not in {11, 14} or documento == documento[0] * tamanho:
        return False
    base = documento[:-2]
    digitos = documento[-2:]
    if tamanho == 11:
        pesos = list(range(10, 1, -1))
        calculados = []
        numeros = [int(valor) for valor in base]
        for _ in range(2):
            soma = sum(valor * peso for valor, peso in zip(numeros, pesos))
            resto = (soma * 10) % 11
            calculado = 0 if resto == 10 else resto
            calculados.append(calculado)
            numeros.append(calculado)
            pesos = list(range(11, 1, -1))
    else:
        calculados = []
        numeros = [int(valor) for valor in base]
        for pesos in (
            [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
            [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
        ):
            soma = sum(valor * peso for valor, peso in zip(numeros, pesos))
            resto = soma % 11
            calculado = 0 if resto < 2 else 11 - resto
            calculados.append(calculado)
            numeros.append(calculado)
    return digitos == "".join(str(valor) for valor in calculados)


def validar_resposta_documento_pinpad(resultado: dict) -> dict:
    if not isinstance(resultado, dict):
        raise RespostaTefInvalida("O driver do pinpad devolveu uma resposta invalida.")
    status = str(resultado.get("status") or "").strip().lower()
    if status not in {"ok", "erro", "cancelado"}:
        raise RespostaTefInvalida("O driver do pinpad devolveu um status desconhecido.")
    normalizado = dict(resultado)
    normalizado["status"] = status
    if status != "ok":
        normalizado.pop("documento", None)
        return normalizado
    documento = "".join(valor for valor in str(resultado.get("documento") or "") if valor.isdigit())
    if not _documento_valido(documento):
        raise RespostaTefInvalida("O pinpad devolveu um CPF/CNPJ invalido.")
    tipo = str(resultado.get("tipo") or "").strip().upper()
    tipo_esperado = "CPF" if len(documento) == 11 else "CNPJ"
    if tipo and tipo != tipo_esperado:
        raise RespostaTefInvalida("O tipo do documento devolvido pelo pinpad e inconsistente.")
    normalizado["tipo"] = tipo_esperado
    normalizado["documento"] = documento
    normalizado.setdefault("origem", "pinpad")
    return normalizado
