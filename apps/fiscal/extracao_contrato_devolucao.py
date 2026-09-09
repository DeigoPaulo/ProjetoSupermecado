"""Extrai somente referências autorizadas. Não produz conteúdo fiscal ou XML."""
import hashlib

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.clientes.escopo import empresa_id_do_usuario
from .contrato_devolucao import CONTRATO, GRUPOS, validar_contrato_devolucao
from .devolucao_fornecedor import _hash_conteudo_revisao
from .dossie_devolucao import diagnosticar_dossie
from .models import DocumentoDFeRecebido, RascunhoDevolucaoFornecedor


def extrair_contrato_devolucao(rascunho_id, usuario):
    if not has_role(usuario, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para consultar o contrato fiscal.")
    try:
        rascunho_id = int(rascunho_id)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Preparação inválida.") from exc
    with transaction.atomic():
        qs = RascunhoDevolucaoFornecedor.objects.select_for_update().select_related("entrada_compra__filial")
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
                "pendencias_dossie": [e for e in dossie["etapas"] if e["estado"] in ("Pendente", "Desatualizado", "Inconsistente", "Bloqueado")]}
