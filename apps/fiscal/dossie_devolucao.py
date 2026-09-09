"""Resumo de consulta da preparação; não é autorização nem validação normativa."""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.clientes.escopo import empresa_id_do_usuario
from .devolucao_fornecedor import _hash_conteudo_revisao, _validar_integridade_memoria_calculo
from .reflexos_devolucao import validar_aprovacao_reflexos
from .models import RascunhoDevolucaoFornecedor


def _integro(objeto):
    return objeto is not None and _hash_conteudo_revisao(objeto.conteudo_snapshot) == objeto.conteudo_sha256


def diagnosticar_dossie(rascunho, usuario):
    if not has_role(usuario, REVISAO_FISCAL):
        raise ValidationError("Sem permissão para consultar o dossiê fiscal.")
    # Não reutilizar relações em cache: o XML pode ter mudado desde a leitura anterior.
    rascunho = RascunhoDevolucaoFornecedor.objects.select_related("entrada_compra__filial").get(pk=rascunho.pk)
    empresa_id = empresa_id_do_usuario(usuario)
    if empresa_id is not None and empresa_id != rascunho.entrada_compra.filial.empresa_id:
        raise ValidationError("Preparação de outra empresa.")
    etapas = []

    def incluir(chave, titulo, estado, detalhe, objeto=None):
        etapas.append({"chave": chave, "titulo": titulo, "estado": estado, "detalhe": detalhe,
                       "registro_id": objeto.pk if objeto else None})

    incluir("preparacao", "Preparação", "Conferida" if rascunho.status == "APROVADO" else "Pendente",
            "Preparação aprovada; isso não autoriza emissão." if rascunho.status == "APROVADO" else "Submeter e obter aprovação da preparação.")
    memoria = rascunho.memorias_calculo.order_by("-versao").select_related("parametrizacao__parecer", "reflexos_origem__rateio__composicao").first()
    parecer = rascunho.pareceres_tributarios.order_by("-versao").first()
    parametros = rascunho.parametrizacoes_fiscais.order_by("-versao").first()
    for chave, titulo, objeto in (("parecer", "Parecer tributário", parecer), ("parametros", "Parâmetros por item", parametros)):
        incluir(chave, titulo, "Registrado" if _integro(objeto) else ("Inconsistente" if objeto else "Pendente"),
                "Conteúdo registrado com hash conferido; não equivale a aceite real do contador." if _integro(objeto) else "Registrar ou conferir a integridade do conteúdo.", objeto)
    if parametros and parecer and parametros.parecer_id != parecer.pk:
        incluir("parecer_atual", "Vínculo do parecer", "Desatualizado", "A parametrização não usa o parecer mais recente.")
    if memoria:
        try:
            # O validador existente usa bloqueios de leitura; exige transação.
            with transaction.atomic():
                _validar_integridade_memoria_calculo(rascunho, memoria)
        except ValidationError as exc:
            incluir("memoria", "Memória atual", "Inconsistente", " ".join(exc.messages), memoria)
        else:
            incluir("memoria", "Memória atual", "Conferida", f"Versão {memoria.versao}: itens, totais e XML de origem conferidos.", memoria)
        if parametros and memoria.parametrizacao_id != parametros.pk:
            incluir("parametros_atuais", "Vínculo dos parâmetros", "Desatualizado", "A memória não usa os parâmetros mais recentes.")
        revisao = getattr(memoria, "revisao_fiscal", None)
        if revisao and (not _integro(revisao) or revisao.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256
                        or revisao.conteudo_snapshot.get("decisao") != revisao.decisao):
            incluir("revisao_memoria", "Revisão da memória", "Inconsistente", "Conferir a integridade da decisão.")
        elif revisao and revisao.decisao == "APROVAR":
            incluir("revisao_memoria", "Revisão da memória", "Conferida", "Versão atual aprovada; não autoriza XML.", revisao)
        else:
            incluir("revisao_memoria", "Revisão da memória", "Pendente", "Corrigir a memória devolvida." if revisao else "Obter revisão independente da memória atual.")
    else:
        incluir("memoria", "Memória atual", "Pendente", "Registrar valores e totais para conferência.")

    composicao = rascunho.composicoes.order_by("-versao").first()
    registro = memoria.reflexos_origem if memoria and memoria.reflexos_origem_id else None
    if registro:
        rateio = registro.rateio
        origem = rateio.composicao
        incluir("origem_revisada", "Origem da memória revisada", "Referência", f"Reflexos {registro.pk}, rateio {rateio.pk} e composição {origem.pk} preservados como origem; os impactos não devem ser reaplicados.")
        if not composicao or composicao.pk != origem.pk or origem.rateios.order_by("-versao").first().pk != rateio.pk or rateio.reflexos.order_by("-versao").first().pk != registro.pk:
            incluir("origem_atual", "Atualidade da origem", "Desatualizado", "Há uma versão posterior à origem da memória revisada; conferir a cadeia antes de avançar.")
        composicao = origem
    else:
        rateio = composicao.rateios.order_by("-versao").first() if composicao else None
        registro = rateio.reflexos.order_by("-versao").first() if rateio else None
        if composicao and memoria and composicao.memoria_id != memoria.pk:
            incluir("composicao_atual", "Vínculo da composição", "Desatualizado", "A composição não está ligada à memória atual.")
    for chave, titulo, objeto in (("composicao", "Composição comercial", composicao), ("rateio", "Rateio por item", rateio), ("reflexos", "Reflexos nas bases", registro)):
        incluir(chave, titulo, "Registrado" if _integro(objeto) else ("Inconsistente" if objeto else "Pendente"),
                "Conteúdo registrado com hash conferido." if _integro(objeto) else "Registrar ou conferir a integridade do conteúdo.", objeto)
    if composicao:
        revisao = getattr(composicao, "revisao", None)
        aprovado = revisao and revisao.decisao == "APROVAR" and _integro(revisao) and revisao.conteudo_snapshot.get("composicao_sha256") == composicao.conteudo_sha256
        incluir("revisao_composicao", "Revisão da composição", "Conferida" if aprovado else "Pendente", "Aprovação registrada." if aprovado else "Obter aprovação independente da composição.")
    if registro:
        try:
            validar_aprovacao_reflexos(registro)
        except ValidationError as exc:
            incluir("revisao_reflexos", "Revisão dos reflexos", "Pendente", " ".join(exc.messages))
        else:
            incluir("revisao_reflexos", "Revisão dos reflexos", "Conferida", "Aprovação registrada; valores dos impostos ainda dependem da memória revisada.")
        if not memoria or memoria.reflexos_origem_id != registro.pk:
            incluir("vinculo_reflexos", "Memória revisada", "Pendente", "Vincular as bases finais aprovadas a uma memória revisada, sem reaplicar impactos.")
    transporte = rascunho.transportes.order_by("-versao").first()
    if not transporte:
        incluir("transporte", "Transporte", "Pendente", "Registrar a ficha logística sobre a memória aprovada atual.")
    elif not _integro(transporte):
        incluir("transporte", "Transporte", "Inconsistente", "Conferir integridade da ficha logística.", transporte)
    elif not memoria or transporte.memoria_id != memoria.pk or transporte.conteudo_snapshot.get("memoria_sha256") != memoria.conteudo_sha256:
        incluir("transporte", "Transporte", "Desatualizado", "Atualizar a ficha logística para a memória aprovada atual.", transporte)
    else:
        incluir("transporte", "Transporte", "Registrado", "Ficha vinculada à memória atual; não equivale a homologação.", transporte)
    incluir("xml", "XML e transmissão", "Bloqueado", "Geração do XML de devolução, validações oficiais, aceite contábil real e homologação por canal permanecem pendentes.")
    return {"contrato": "supplier_return_dossier_status_v1", "etapas": etapas,
            "pendencias": sum(e["estado"] in ("Pendente", "Desatualizado", "Inconsistente", "Bloqueado") for e in etapas),
            "permite_emissao": False}
