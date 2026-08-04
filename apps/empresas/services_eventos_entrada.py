from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone

from .models import EventoEntradaSincronizacao, ModoImplantacao, PoliticaConflitoSincronizacao, StatusEventoEntrada


class ManipuladorEventoNaoEncontrado(Exception):
    pass


class ConflitoSincronizacao(Exception):
    pass


def _ping(_evento):
    return None


def _valor_texto(dados, chave, padrao=""):
    valor = dados.get(chave, padrao)
    return str(valor).strip() if valor is not None else padrao


def _valor_decimal(dados, chave, padrao="0"):
    try:
        return Decimal(str(dados.get(chave, padrao)).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Valor invalido para {chave}.") from exc


def _valor_decimal_opcional(dados, chave):
    valor = dados.get(chave)
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Valor invalido para {chave}.") from exc


def _valor_booleano(dados, chave, padrao=False):
    valor = dados.get(chave, padrao)
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in {"1", "true", "sim", "s", "on"}


def _nome_relacionado(valor):
    if isinstance(valor, dict):
        return str(valor.get("nome", "")).strip()
    return str(valor or "").strip()


def _dados_evento(evento):
    payload = evento.payload.get("payload", evento.payload)
    if not isinstance(payload, dict):
        raise ValueError("Payload de evento deve ser um objeto JSON.")
    return payload


def _forcar_remoto(evento):
    return bool(evento.payload.get("_sync_force_remote"))


def _evento_remoto_em(evento):
    bruto = evento.payload.get("criado_em") or evento.payload.get("atualizado_em")
    if not bruto:
        return None
    data = parse_datetime(str(bruto))
    if data and timezone.is_naive(data):
        data = timezone.make_aware(data)
    return data


def _categoria_do_produto(dados):
    from apps.produtos.models import Categoria, NivelCategoriaProduto

    hierarquia = dados.get("categoria_hierarquia")
    if isinstance(hierarquia, list) and hierarquia:
        superior = None
        categoria = None
        niveis_validos = set(NivelCategoriaProduto.values)
        ordem_niveis = list(NivelCategoriaProduto.values)
        for item in hierarquia:
            if not isinstance(item, dict):
                raise ValueError("Cada nível da categoria_hierarquia deve ser um objeto.")
            nome = _valor_texto(item, "nome")
            nivel = _valor_texto(item, "nivel", NivelCategoriaProduto.GRUPO)
            if not nome or nivel not in niveis_validos:
                raise ValueError("Nome e nível válido são obrigatórios na categoria_hierarquia.")
            if superior and ordem_niveis.index(nivel) != ordem_niveis.index(superior.nivel) + 1:
                raise ValueError("A categoria_hierarquia deve seguir departamento, seção, grupo e subgrupo.")
            categoria = Categoria.all_objects.filter(nome=nome).first()
            if not categoria:
                categoria = Categoria.all_objects.create(nome=nome, nivel=nivel, parent=superior, is_active=True)
            else:
                alterados = []
                if categoria.nivel != nivel:
                    categoria.nivel = nivel
                    alterados.append("nivel")
                if categoria.parent_id != (superior.pk if superior else None):
                    categoria.parent = superior
                    alterados.append("parent")
                if not categoria.is_active:
                    categoria.is_active = True
                    alterados.append("is_active")
                if alterados:
                    categoria.save(update_fields=[*alterados, "updated_at"])
            superior = categoria
        return categoria

    categoria_nome = _nome_relacionado(dados.get("categoria"))
    if not categoria_nome:
        return None
    categoria, _ = Categoria.all_objects.get_or_create(nome=categoria_nome, defaults={"is_active": True})
    return categoria


def _produto_salvar(evento):
    from apps.produtos.models import (
        CodigoBarrasProduto, ConfiguracaoBalancaProduto, InformacaoNutricional, Marca, Produto,
        SetorBalanca, TipoProduto, UnidadeMedida,
    )

    dados = _dados_evento(evento)
    codigo_barras = _valor_texto(dados, "codigo_barras")
    nome = _valor_texto(dados, "nome")
    categoria = _categoria_do_produto(dados)
    if not codigo_barras or not nome or not categoria:
        raise ValueError("codigo_barras, nome e categoria são obrigatórios para sincronizar produto.")
    marca = None
    marca_nome = _nome_relacionado(dados.get("marca"))
    if marca_nome:
        marca, _ = Marca.all_objects.get_or_create(nome=marca_nome, defaults={"is_active": True})

    produto = Produto.all_objects.filter(codigo_barras=codigo_barras).first()
    remoto_em = _evento_remoto_em(evento)
    if produto and remoto_em and produto.updated_at and produto.updated_at > remoto_em and not _forcar_remoto(evento):
        raise ConflitoSincronizacao("Produto local foi alterado depois do evento remoto.")

    valores = {
        "codigo_interno": _valor_texto(dados, "codigo_interno"),
        "nome": nome,
        "descricao": _valor_texto(dados, "descricao"),
        "tipo_produto": _valor_texto(dados, "tipo_produto", TipoProduto.MERCADORIA) or TipoProduto.MERCADORIA,
        "categoria": categoria,
        "marca": marca,
        "unidade": _valor_texto(dados, "unidade", UnidadeMedida.UNIDADE)[:3] or UnidadeMedida.UNIDADE,
        "unidade_compra": _valor_texto(dados, "unidade_compra", UnidadeMedida.UNIDADE)[:3] or UnidadeMedida.UNIDADE,
        "fator_conversao_compra": _valor_decimal(dados, "fator_conversao_compra", "1"),
        "peso_liquido": _valor_decimal_opcional(dados, "peso_liquido"),
        "peso_bruto": _valor_decimal_opcional(dados, "peso_bruto"),
        "produto_pesavel": _valor_booleano(dados, "produto_pesavel"),
        "preco_custo": _valor_decimal(dados, "preco_custo"),
        "margem_desejada_percentual": _valor_decimal_opcional(dados, "margem_desejada_percentual"),
        "preco_venda": _valor_decimal(dados, "preco_venda"),
        "preco_promocional": _valor_decimal_opcional(dados, "preco_promocional"),
        "estoque_minimo": _valor_decimal(dados, "estoque_minimo"),
        "exige_lote": _valor_booleano(dados, "exige_lote"),
        "vendido_no_pdv": _valor_booleano(dados, "vendido_no_pdv", True),
        "vendido_no_marketplace": _valor_booleano(dados, "vendido_no_marketplace"),
        "ncm": _valor_texto(dados, "ncm"),
        "cest": _valor_texto(dados, "cest"),
        "origem_mercadoria": _valor_texto(dados, "origem_mercadoria"),
        "cst_icms": _valor_texto(dados, "cst_icms"),
        "csosn": _valor_texto(dados, "csosn"),
        "aliquota_icms": _valor_decimal(dados, "aliquota_icms", "0"),
        "reducao_base_icms": _valor_decimal_opcional(dados, "reducao_base_icms"),
        "aliquota_fcp": _valor_decimal_opcional(dados, "aliquota_fcp"),
        "codigo_beneficio_fiscal": _valor_texto(dados, "codigo_beneficio_fiscal"),
        "cst_pis": _valor_texto(dados, "cst_pis"),
        "aliquota_pis": _valor_decimal_opcional(dados, "aliquota_pis"),
        "cst_cofins": _valor_texto(dados, "cst_cofins"),
        "aliquota_cofins": _valor_decimal_opcional(dados, "aliquota_cofins"),
        "cst_ipi": _valor_texto(dados, "cst_ipi"),
        "codigo_enquadramento_ipi": _valor_texto(dados, "codigo_enquadramento_ipi"),
        "aliquota_ipi": _valor_decimal_opcional(dados, "aliquota_ipi"),
        "cst_ibs_cbs": _valor_texto(dados, "cst_ibs_cbs"),
        "classificacao_tributaria_ibs_cbs": _valor_texto(dados, "classificacao_tributaria_ibs_cbs"),
        "is_active": _valor_booleano(dados, "is_active", True),
    }
    if produto:
        for campo, valor in valores.items():
            setattr(produto, campo, valor)
        produto._sincronizacao_entrada = True
        produto.save()
    else:
        produto = Produto.all_objects.create(codigo_barras=codigo_barras, **valores)

    if "codigos_adicionais" in dados:
        codigos = dados["codigos_adicionais"]
        if not isinstance(codigos, list):
            raise ValueError("codigos_adicionais deve ser uma lista.")
        codigos_recebidos = set()
        for item in codigos:
            if not isinstance(item, dict):
                raise ValueError("Cada codigo adicional deve ser um objeto.")
            codigo = _valor_texto(item, "codigo")
            if not codigo:
                continue
            if codigo == produto.codigo_barras:
                raise ConflitoSincronizacao("EAN adicional repete o codigo principal do produto.")
            existente = CodigoBarrasProduto.objects.filter(codigo=codigo).exclude(produto=produto).first()
            if existente:
                raise ConflitoSincronizacao("EAN adicional pertence a outro produto.")
            CodigoBarrasProduto.objects.update_or_create(
                produto=produto,
                codigo=codigo,
                defaults={
                    "tipo": _valor_texto(item, "tipo", "UNIDADE"),
                    "fator_conversao": _valor_decimal(item, "fator_conversao", "1"),
                    "permite_venda": _valor_booleano(item, "permite_venda", True),
                    "is_active": _valor_booleano(item, "is_active", True),
                },
            )
            codigos_recebidos.add(codigo)
        produto.codigos_adicionais.exclude(codigo__in=codigos_recebidos).delete()

    if "configuracoes_balanca" in dados:
        configuracoes = dados["configuracoes_balanca"]
        if not isinstance(configuracoes, list):
            raise ValueError("configuracoes_balanca deve ser uma lista.")
        recebidas = set()
        for item in configuracoes:
            if not isinstance(item, dict):
                raise ValueError("Cada configuração de balança deve ser um objeto.")
            setor_codigo = int(item.get("setor_codigo") or 0)
            setor_nome = _valor_texto(item, "setor_nome")
            plu = int(item.get("plu") or 0)
            if setor_codigo <= 0 or not setor_nome or plu <= 0:
                raise ValueError("Setor, nome do setor e PLU são obrigatórios na configuração de balança.")
            setor, _ = SetorBalanca.objects.update_or_create(
                empresa=evento.empresa,
                codigo=setor_codigo,
                defaults={"nome": setor_nome, "is_active": True},
            )
            conflito = ConfiguracaoBalancaProduto.objects.filter(
                empresa=evento.empresa, plu=plu
            ).exclude(produto=produto).first()
            if conflito:
                raise ConflitoSincronizacao("PLU recebido já pertence a outro produto na empresa.")
            ConfiguracaoBalancaProduto.objects.update_or_create(
                empresa=evento.empresa,
                produto=produto,
                defaults={
                    "setor": setor,
                    "plu": plu,
                    "tara_kg": _valor_decimal(item, "tara_kg", "0"),
                    "validade_dias": int(item.get("validade_dias") or 0),
                    "is_active": _valor_booleano(item, "is_active", True),
                },
            )
            recebidas.add(plu)
        produto.configuracoes_balanca.filter(empresa=evento.empresa).exclude(plu__in=recebidas).delete()

    if "informacao_nutricional" in dados:
        nutricao = dados.get("informacao_nutricional")
        if nutricao is None:
            InformacaoNutricional.objects.filter(produto=produto).delete()
        elif not isinstance(nutricao, dict):
            raise ValueError("informacao_nutricional deve ser um objeto ou nulo.")
        else:
            campos_decimais = (
                "porcao_quantidade", "porcoes_por_embalagem", "valor_energetico_kcal",
                "carboidratos_g", "acucares_totais_g", "acucares_adicionados_g",
                "proteinas_g", "gorduras_totais_g", "gorduras_saturadas_g",
                "gorduras_trans_g", "fibra_alimentar_g", "sodio_mg",
            )
            valores_nutricao = {
                "base_calculo": _valor_texto(nutricao, "base_calculo", "100G") or "100G",
                "porcao_unidade": _valor_texto(nutricao, "porcao_unidade"),
                "medida_caseira": _valor_texto(nutricao, "medida_caseira"),
                "ingredientes": _valor_texto(nutricao, "ingredientes"),
                "alergicos": _valor_texto(nutricao, "alergicos"),
                "gluten": _valor_texto(nutricao, "gluten"),
                "lactose": _valor_texto(nutricao, "lactose"),
            }
            valores_nutricao.update({
                campo: _valor_decimal_opcional(nutricao, campo)
                for campo in campos_decimais
            })
            informacao, _ = InformacaoNutricional.objects.update_or_create(
                produto=produto,
                defaults=valores_nutricao,
            )
            informacao.full_clean()
            informacao.save()

    if "produtos_similares" in dados:
        similares_recebidos = dados.get("produtos_similares")
        if not isinstance(similares_recebidos, list):
            raise ValueError("produtos_similares deve ser uma lista.")
        similares = []
        pendentes = []
        for item in similares_recebidos:
            if not isinstance(item, dict):
                raise ValueError("Cada produto similar deve ser um objeto.")
            codigo_similar = _valor_texto(item, "codigo_barras")
            codigo_interno_similar = _valor_texto(item, "codigo_interno")
            similar = None
            if codigo_similar:
                similar = Produto.all_objects.filter(codigo_barras=codigo_similar).first()
            if not similar and codigo_interno_similar:
                similar = Produto.all_objects.filter(codigo_interno=codigo_interno_similar).first()
            if not similar:
                pendentes.append(codigo_similar or codigo_interno_similar or _valor_texto(item, "nome") or "sem identificador")
            elif similar.pk != produto.pk:
                similares.append(similar)
        if pendentes:
            raise ConflitoSincronizacao(
                "Produtos similares ainda nao encontrados na loja: " + ", ".join(pendentes[:5])
            )
        produto.produtos_similares.set(similares)

def _estoque_saldo_atualizar(evento):
    from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
    from apps.produtos.models import Produto

    dados = _dados_evento(evento)
    codigo_barras = _valor_texto(dados, "codigo_barras")
    filial_cnpj = _valor_texto(dados, "filial_cnpj")
    filial_nome = _valor_texto(dados, "filial_nome")
    if not codigo_barras or not (filial_cnpj or filial_nome):
        raise ValueError("codigo_barras e filial_cnpj ou filial_nome são obrigatorios para sincronizar estoque.")

    produto = Produto.all_objects.filter(codigo_barras=codigo_barras).first()
    if not produto:
        raise ConflitoSincronizacao("Produto do saldo de estoque não encontrado na loja.")

    filiais = evento.empresa.filiais.all()
    filial = filiais.filter(cnpj=filial_cnpj).first() if filial_cnpj else None
    if not filial and filial_nome:
        filial = filiais.filter(nome=filial_nome).first()
    if not filial:
        raise ConflitoSincronizacao("Filial do saldo de estoque não encontrada para a empresa.")

    estoque, _ = Estoque.objects.get_or_create(produto=produto, filial=filial)
    remoto_em = _evento_remoto_em(evento)
    if remoto_em and estoque.atualizado_em and estoque.atualizado_em > remoto_em and not _forcar_remoto(evento):
        raise ConflitoSincronizacao("Estoque local foi alterado depois do evento remoto.")

    quantidade_atual = _valor_decimal(dados, "quantidade_atual")
    quantidade_reservada = _valor_decimal(dados, "quantidade_reservada", "0")
    custo_medio = _valor_decimal(dados, "custo_medio", str(produto.preco_custo or 0))
    anterior = estoque.quantidade_atual
    diferenca = quantidade_atual - anterior
    estoque.quantidade_atual = quantidade_atual
    estoque.quantidade_reservada = quantidade_reservada
    estoque.custo_medio = custo_medio
    estoque.full_clean()
    estoque.save()

    if diferenca:
        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=filial,
            tipo=TipoMovimentacaoEstoque.AJUSTE,
            quantidade=diferenca,
            motivo="Sincronizacao de saldo de estoque",
            referencia=f"sync:{evento.identificador}",
        )


def _filial_do_evento(evento, dados):
    filial_cnpj = _valor_texto(dados, "filial_cnpj") or _valor_texto(evento.payload, "filial_cnpj")
    filial_nome = _valor_texto(dados, "filial_nome")
    filiais = evento.empresa.filiais.all()
    filial = filiais.filter(cnpj=filial_cnpj).first() if filial_cnpj else None
    if not filial and filial_nome:
        filial = filiais.filter(nome=filial_nome).first()
    return filial


def _venda_finalizada(evento):
    from .models import VendaSincronizada

    dados = _dados_evento(evento)
    venda_externa_id = _valor_texto(dados, "venda_id") or _valor_texto(dados, "id")
    if not venda_externa_id:
        raise ValueError("venda_id e obrigatório para sincronizar venda finalizada.")
    total_liquido = _valor_decimal(dados, "total_liquido")
    existente = VendaSincronizada.objects.filter(empresa=evento.empresa, venda_externa_id=venda_externa_id).first()
    if existente and existente.total_liquido != total_liquido:
        raise ConflitoSincronizacao("Venda externa ja existe com total diferente.")

    filial = _filial_do_evento(evento, dados)
    if not filial:
        raise ConflitoSincronizacao("Filial da venda sincronizada não encontrada para a empresa.")
    realizada_em = parse_datetime(_valor_texto(dados, "realizada_em")) if _valor_texto(dados, "realizada_em") else None
    if realizada_em and timezone.is_naive(realizada_em):
        realizada_em = timezone.make_aware(realizada_em)
    itens = dados.get("itens", [])
    pagamentos = dados.get("pagamentos", [])
    if not isinstance(itens, list) or not isinstance(pagamentos, list):
        raise ValueError("Itens e pagamentos da venda devem ser listas.")

    valores = {
        "filial": filial,
        "evento": evento,
        "caixa_externo": _valor_texto(dados, "caixa"),
        "operador": _valor_texto(dados, "operador"),
        "cliente": _valor_texto(dados, "cliente", "Cliente avulso"),
        "total_bruto": _valor_decimal(dados, "total_bruto"),
        "desconto": _valor_decimal(dados, "desconto"),
        "total_liquido": total_liquido,
        "itens": itens,
        "pagamentos": pagamentos,
        "realizada_em": realizada_em,
    }
    if existente:
        for campo, valor in valores.items():
            setattr(existente, campo, valor)
        existente.save()
    else:
        VendaSincronizada.objects.create(empresa=evento.empresa, venda_externa_id=venda_externa_id, **valores)


def _documento_fiscal_salvar(evento):
    from .models import DocumentoFiscalSincronizado

    dados = _dados_evento(evento)
    documento_externo_id = _valor_texto(dados, "documento_id") or _valor_texto(dados, "id")
    if not documento_externo_id:
        raise ValueError("documento_id e obrigatório para sincronizar documento fiscal.")

    valor_total = _valor_decimal(dados, "valor_total")
    chave_acesso = _valor_texto(dados, "chave_acesso")
    existente = DocumentoFiscalSincronizado.objects.filter(
        empresa=evento.empresa,
        documento_externo_id=documento_externo_id,
    ).first()
    if existente:
        if existente.valor_total != valor_total:
            raise ConflitoSincronizacao("Documento fiscal externo ja existe com valor diferente.")
        if existente.chave_acesso and chave_acesso and existente.chave_acesso != chave_acesso:
            raise ConflitoSincronizacao("Documento fiscal externo ja existe com chave de acesso diferente.")

    filial = _filial_do_evento(evento, dados)
    if not filial:
        raise ConflitoSincronizacao("Filial do documento fiscal sincronizado não encontrada para a empresa.")
    emitido_em = parse_datetime(_valor_texto(dados, "emitido_em")) if _valor_texto(dados, "emitido_em") else None
    if emitido_em and timezone.is_naive(emitido_em):
        emitido_em = timezone.make_aware(emitido_em)

    valores = {
        "filial": filial,
        "evento": evento,
        "venda_externa_id": _valor_texto(dados, "venda_id"),
        "tipo_documento": _valor_texto(dados, "tipo_documento", "NFCE"),
        "ambiente": _valor_texto(dados, "ambiente"),
        "serie": _valor_texto(dados, "serie"),
        "numero": _valor_texto(dados, "numero"),
        "chave_acesso": chave_acesso,
        "protocolo": _valor_texto(dados, "protocolo"),
        "status": _valor_texto(dados, "status", "EMITIDO"),
        "valor_total": valor_total,
        "emitido_em": emitido_em,
        "payload": dados,
    }
    if existente:
        for campo, valor in valores.items():
            setattr(existente, campo, valor)
        existente.save()
    else:
        DocumentoFiscalSincronizado.objects.create(
            empresa=evento.empresa,
            documento_externo_id=documento_externo_id,
            **valores,
        )


def _rotulo_referencia(valor):
    if not isinstance(valor, dict):
        return str(valor or "").strip()
    codigo = str(valor.get("codigo") or "").strip()
    nome = str(valor.get("nome") or "").strip()
    return " - ".join(parte for parte in (codigo, nome) if parte)


def _lancamento_financeiro_salvar(evento):
    from .models import LancamentoFinanceiroSincronizado

    dados = _dados_evento(evento)
    if _valor_texto(dados, "contrato") != "financeiro_lancamento_v1":
        raise ValueError("Contrato financeiro ausente ou incompativel; esperado financeiro_lancamento_v1.")
    lancamento_externo_id = _valor_texto(dados, "lancamento_id") or _valor_texto(dados, "id")
    if not lancamento_externo_id:
        raise ValueError("lancamento_id e obrigatorio para sincronizar lancamento financeiro.")
    tipo = _valor_texto(dados, "tipo")
    if tipo not in {"ENTRADA", "SAIDA"}:
        raise ValueError("Tipo do lancamento financeiro deve ser ENTRADA ou SAIDA.")
    valor = _valor_decimal(dados, "valor")
    if valor <= 0:
        raise ValueError("Valor do lancamento financeiro deve ser maior que zero.")
    data = parse_date(_valor_texto(dados, "data"))
    if not data:
        raise ValueError("Data valida e obrigatoria no lancamento financeiro.")

    existente = LancamentoFinanceiroSincronizado.objects.filter(
        empresa=evento.empresa,
        lancamento_externo_id=lancamento_externo_id,
    ).first()
    if existente and (existente.tipo != tipo or existente.valor != valor):
        raise ConflitoSincronizacao("Lancamento financeiro externo ja existe com tipo ou valor diferente.")

    filial = _filial_do_evento(evento, dados)
    if not filial:
        raise ConflitoSincronizacao("Filial do lancamento financeiro sincronizado nao encontrada para a empresa.")
    valores = {
        "filial": filial,
        "evento": evento,
        "tipo": tipo,
        "origem": _valor_texto(dados, "origem"),
        "descricao": _valor_texto(dados, "descricao"),
        "valor": valor,
        "data": data,
        "conta_movimento": _rotulo_referencia(dados.get("conta_movimento")),
        "centro_custo": _rotulo_referencia(dados.get("centro_custo")),
        "conta_contabil": _rotulo_referencia(dados.get("conta_contabil")),
        "usuario": _valor_texto(dados, "usuario"),
        "estorno_de_externo_id": _valor_texto(dados, "estorno_de_id"),
        "payload": dados,
    }
    if existente:
        for campo, conteudo in valores.items():
            setattr(existente, campo, conteudo)
        existente.save()
    else:
        LancamentoFinanceiroSincronizado.objects.create(
            empresa=evento.empresa,
            lancamento_externo_id=lancamento_externo_id,
            **valores,
        )


MANIPULADORES = {
    "sistema.ping": _ping,
    "produto.criado": _produto_salvar,
    "produto.atualizado": _produto_salvar,
    "estoque.saldo_atualizado": _estoque_saldo_atualizar,
    "venda.finalizada": _venda_finalizada,
    "financeiro.lancamento_registrado": _lancamento_financeiro_salvar,
    "fiscal.documento_emitido": _documento_fiscal_salvar,
    "fiscal.documento_cancelado": _documento_fiscal_salvar,
}


def processar_evento_entrada(evento):
    manipulador = MANIPULADORES.get(evento.tipo)
    if not manipulador:
        raise ManipuladorEventoNaoEncontrado(f"Evento sem manipulador de dominio: {evento.tipo}")
    manipulador(evento)


def _pode_resolver_conflito_com_remoto(evento, erro):
    if evento.empresa.politica_conflito_sincronizacao != PoliticaConflitoSincronizacao.REMOTO_PRODUTOS_ESTOQUE:
        return False
    if evento.tipo not in {"produto.criado", "produto.atualizado", "estoque.saldo_atualizado"}:
        return False
    return "foi alterado depois do evento remoto" in str(erro)


def _resolver_conflito_com_remoto(evento):
    evento.payload = {**evento.payload, "_sync_force_remote": True}
    processar_evento_entrada(evento)
    evento.payload.pop("_sync_force_remote", None)
    evento.resolucao_conflito = "Resolvido automaticamente pela política da empresa: nuvem prevalece para produtos e estoque."
    evento.resolvido_em = timezone.now()


def _pode_resolver_conflito_com_local(evento, erro):
    if evento.empresa.politica_conflito_sincronizacao != PoliticaConflitoSincronizacao.LOCAL_PRODUTOS_ESTOQUE:
        return False
    if evento.tipo not in {"produto.criado", "produto.atualizado", "estoque.saldo_atualizado"}:
        return False
    return "foi alterado depois do evento remoto" in str(erro)


def _resolver_conflito_com_local(evento):
    evento.resolucao_conflito = (
        "Resolvido automaticamente pela política da empresa: loja prevalece para produtos e estoque; "
        "evento remoto descartado sem alterar o dado local."
    )
    evento.resolvido_em = timezone.now()


def processar_entrada_sincronizacao(*, limite=50):
    candidatos = list(
        EventoEntradaSincronizacao.objects.filter(
            status=StatusEventoEntrada.RECEBIDO,
            empresa__is_active=True,
            empresa__sincronizacao_automatica=True,
        )
        .exclude(empresa__modo_implantacao=ModoImplantacao.LOCAL)
        .exclude(empresa__url_sincronizacao="")
        .order_by("recebido_em")
        .values_list("pk", flat=True)[:limite]
    )
    resultado = {"processados": 0, "erros": 0}
    for pk in candidatos:
        with transaction.atomic():
            evento = EventoEntradaSincronizacao.objects.select_for_update().get(pk=pk)
            if evento.status != StatusEventoEntrada.RECEBIDO:
                continue
            if not evento.empresa.sincronizacao_operacional_habilitada:
                evento.status = StatusEventoEntrada.PAUSADO
                evento.ultimo_erro = "Pausado pela política de implantação."
                evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
                continue
            try:
                processar_evento_entrada(evento)
            except ConflitoSincronizacao as exc:
                if _pode_resolver_conflito_com_remoto(evento, exc):
                    try:
                        _resolver_conflito_com_remoto(evento)
                    except Exception as novo_exc:
                        evento.status = StatusEventoEntrada.CONFLITO
                        evento.ultimo_erro = str(novo_exc)[:2000]
                        evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
                        resultado["erros"] += 1
                    else:
                        evento.status = StatusEventoEntrada.PROCESSADO
                        evento.ultimo_erro = ""
                        evento.processado_em = timezone.now()
                        evento.save(update_fields=["payload", "status", "ultimo_erro", "resolucao_conflito", "resolvido_em", "processado_em", "atualizado_em"])
                        resultado["processados"] += 1
                elif _pode_resolver_conflito_com_local(evento, exc):
                    _resolver_conflito_com_local(evento)
                    evento.status = StatusEventoEntrada.PROCESSADO
                    evento.ultimo_erro = ""
                    evento.processado_em = timezone.now()
                    evento.save(
                        update_fields=[
                            "status",
                            "ultimo_erro",
                            "resolucao_conflito",
                            "resolvido_em",
                            "processado_em",
                            "atualizado_em",
                        ]
                    )
                    resultado["processados"] += 1
                else:
                    evento.status = StatusEventoEntrada.CONFLITO
                    evento.ultimo_erro = str(exc)[:2000]
                    evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
                    resultado["erros"] += 1
            except Exception as exc:
                evento.status = StatusEventoEntrada.ERRO
                evento.ultimo_erro = str(exc)[:2000]
                evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
                resultado["erros"] += 1
            else:
                evento.status = StatusEventoEntrada.PROCESSADO
                evento.ultimo_erro = ""
                evento.processado_em = timezone.now()
                evento.save(update_fields=["status", "ultimo_erro", "processado_em", "atualizado_em"])
                resultado["processados"] += 1
    return resultado
