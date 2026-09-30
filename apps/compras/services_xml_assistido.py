import hashlib
import hmac
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.permissions import CADASTROS, has_role
from apps.auditoria.models import LogAuditoria
from apps.core_money import quantizar_custo
from apps.produtos.forms import ProdutoForm
from apps.produtos.models import (
    CodigoBarrasProduto,
    Produto,
    ProdutoFornecedor,
    TipoCodigoBarrasProduto,
    UnidadeMedida,
)

from .services_xml import (
    ErroAnaliseItem,
    STATUS_CONVERSAO_NAO_CONFIGURADA,
    STATUS_PRODUTO_NAO_ENCONTRADO,
    STATUS_RESOLVIDO,
    STATUS_UNIDADE_INVALIDA,
    _converter_item_para_unidade_base,
    _gtin_canonico,
    _localizar_produto,
    _resolver_contexto_importacao,
    importar_xml_entrada,
    ler_xml_nfe,
)


UNIDADES_DOCUMENTAIS = {valor for valor, _ in UnidadeMedida.choices} | {"PAC"}
TIPOS_EMBALAGEM = {
    "CX": TipoCodigoBarrasProduto.CAIXA,
    "FD": TipoCodigoBarrasProduto.FARDO,
    "PCT": TipoCodigoBarrasProduto.PACOTE,
    "PAC": TipoCodigoBarrasProduto.PACOTE,
    "UN": TipoCodigoBarrasProduto.UNIDADE,
}


def hash_xml(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _item_documental(item):
    item_documental = item.copy()
    item_documental["quantidade"] = item["quantidade_documental"]
    item_documental["total"] = item["valor_produto_documental"]
    item_documental["custo_unitario"] = quantizar_custo(
        item["valor_produto_documental"] / item["quantidade_documental"]
    )
    return item_documental


def _itens_unicos(dados):
    unicos = {}
    for item in dados["itens"]:
        unicos.setdefault(item["numero"], _item_documental(item))
    return list(unicos.values())


def _decimal_texto(valor):
    return format(valor, "f") if valor is not None else None


def _serializar_item(item, produto, codigo, status, motivo, conversao=None):
    quantidade_base = conversao["quantidade"] if conversao else None
    custo_base = conversao["custo_unitario"] if conversao else None
    return {
        "numero": item["numero"],
        "descricao": item["descricao"],
        "codigo_fornecedor": item["codigo"],
        "ean_comercial": item["ean"],
        "ean_tributavel": item["ean_tributavel"],
        "unidade_documental": item["unidade_comercial"],
        "quantidade_documental": _decimal_texto(item["quantidade_documental"]),
        "valor_total": _decimal_texto(item["valor_produto_documental"]),
        "ncm_fornecedor": item.get("ncm_fornecedor", ""),
        "cest_fornecedor": item.get("cest_fornecedor", ""),
        "status": status,
        "motivo": motivo,
        "produto": (
            {
                "id": produto.pk,
                "nome": produto.nome,
                "unidade_base": produto.unidade,
                "unidade_compra": produto.unidade_compra,
                "fator_compra": _decimal_texto(produto.fator_conversao_compra),
            }
            if produto
            else None
        ),
        "codigo_embalagem_id": codigo.pk if codigo else None,
        "quantidade_base": _decimal_texto(quantidade_base),
        "custo_unitario_base": _decimal_texto(custo_base),
    }


def analisar_xml_entrada(conteudo, *, usuario):
    dados = ler_xml_nfe(conteudo)
    filial, fornecedor = _resolver_contexto_importacao(dados, usuario)
    itens = []
    for item in _itens_unicos(dados):
        produto = codigo = conversao = None
        if item["unidade_comercial"] not in UNIDADES_DOCUMENTAIS:
            itens.append(_serializar_item(
                item,
                None,
                None,
                STATUS_UNIDADE_INVALIDA,
                f"A unidade {item['unidade_comercial'] or '-'} não é aceita pelo cadastro de produtos.",
            ))
            continue
        try:
            produto, codigo = _localizar_produto(item, fornecedor)
            if produto is None:
                status = STATUS_PRODUTO_NAO_ENCONTRADO
                motivo = "Produto ainda não identificado. Vincule um cadastro existente ou crie um novo produto."
            else:
                conversao = _converter_item_para_unidade_base(item, produto, codigo)
                status = STATUS_RESOLVIDO
                motivo = "Produto e embalagem reconhecidos automaticamente."
        except ErroAnaliseItem as exc:
            status = exc.status
            motivo = " ".join(exc.messages)
        itens.append(_serializar_item(item, produto, codigo, status, motivo, conversao))

    return {
        "hash_sha256": hash_xml(conteudo),
        "chave_final": dados["chave"][-8:],
        "numero_documento": dados["numero_documento"],
        "filial": {"id": filial.pk, "nome": filial.nome},
        "fornecedor": {"id": fornecedor.pk, "nome": fornecedor.razao_social},
        "pode_configurar": has_role(usuario, CADASTROS),
        "todos_resolvidos": all(item["status"] == STATUS_RESOLVIDO for item in itens),
        "itens": itens,
    }


def _fator(valor):
    try:
        informado = Decimal(str(valor))
        if not informado.is_finite():
            raise InvalidOperation
        fator = informado.quantize(Decimal("0.001"))
    except (InvalidOperation, TypeError):
        raise ValidationError("Informe um fator de conversão válido.") from None
    if fator <= 0 or informado != fator:
        raise ValidationError("O fator deve ser positivo e possuir no máximo 3 casas decimais.")
    return fator


def _unidade(valor, *, rotulo="unidade"):
    valor = (valor or "").strip().upper()
    valor = "PCT" if valor == "PAC" else valor
    if valor not in UnidadeMedida.values:
        raise ValidationError(f"Informe uma {rotulo} válida.")
    return valor


def _produto_escolhido(produto_id):
    try:
        return Produto.objects.select_for_update().get(pk=produto_id, is_active=True)
    except (Produto.DoesNotExist, TypeError, ValueError):
        raise ValidationError("O produto escolhido não está disponível.") from None


def _validar_vinculo_fornecedor(produto, fornecedor, codigo):
    conflito = ProdutoFornecedor.objects.select_for_update().filter(
        fornecedor=fornecedor,
        codigo_no_fornecedor=codigo,
        is_active=True,
    ).exclude(produto=produto).exists()
    if conflito:
        raise ValidationError("O código do fornecedor já está vinculado a outro produto.")
    vinculo, criado = ProdutoFornecedor.objects.select_for_update().get_or_create(
        produto=produto,
        fornecedor=fornecedor,
        defaults={"codigo_no_fornecedor": codigo, "is_active": True},
    )
    if not criado and vinculo.codigo_no_fornecedor not in {"", codigo}:
        raise ValidationError("O produto já possui outro código para este fornecedor.")
    if not criado and (vinculo.codigo_no_fornecedor != codigo or not vinculo.is_active):
        vinculo.codigo_no_fornecedor = codigo
        vinculo.is_active = True
        vinculo.save(update_fields=["codigo_no_fornecedor", "is_active", "updated_at"])
    return criado


def _salvar_codigo_embalagem(produto, item, fator):
    codigo = _gtin_canonico(item["ean"])
    if not codigo or codigo == _gtin_canonico(produto.codigo_barras):
        return None, False
    existente = CodigoBarrasProduto.objects.select_for_update().filter(codigo=codigo).first()
    if existente:
        if existente.produto_id != produto.pk or existente.fator_conversao != fator:
            raise ValidationError("O código comercial já possui produto ou fator diferente; conflito bloqueado.")
        return existente, False
    try:
        return CodigoBarrasProduto.objects.create(
            produto=produto,
            codigo=codigo,
            tipo=TIPOS_EMBALAGEM.get(item["unidade_comercial"], TipoCodigoBarrasProduto.OUTRO),
            fator_conversao=fator,
            permite_venda=False,
        ), True
    except IntegrityError:
        raise ValidationError("O código comercial foi alterado concorrentemente; analise o XML novamente.") from None


def _configurar_embalagem(produto, item, decisao):
    unidade_base = _unidade(decisao.get("unidade_base") or produto.unidade, rotulo="unidade-base")
    unidade_compra = _unidade(decisao.get("unidade_compra") or item["unidade_comercial"], rotulo="unidade de compra")
    fator = _fator(decisao.get("fator"))
    if unidade_base != produto.unidade:
        raise ValidationError("A unidade-base informada difere do cadastro do produto.")
    codigo, codigo_criado = _salvar_codigo_embalagem(produto, item, fator)
    padrao_alterado = False
    if decisao.get("definir_como_padrao") is True:
        if produto.unidade_compra != unidade_compra or produto.fator_conversao_compra != fator:
            produto.unidade_compra = unidade_compra
            produto.fator_conversao_compra = fator
            produto.save(update_fields=["unidade_compra", "fator_conversao_compra", "updated_at"])
            padrao_alterado = True
    if codigo is None and not padrao_alterado and unidade_compra != produto.unidade:
        raise ValidationError(
            "Confirme a embalagem padrão ou informe um código comercial válido para registrar a conversão."
        )
    return fator, codigo, codigo_criado, padrao_alterado


def _criar_produto(item, decisao):
    unidade_base = _unidade(decisao.get("unidade_base"), rotulo="unidade-base")
    unidade_compra = _unidade(decisao.get("unidade_compra") or item["unidade_comercial"], rotulo="unidade de compra")
    fator = _fator(decisao.get("fator"))
    quantidade_base = item["quantidade_documental"] * fator
    custo_base = quantizar_custo(item["valor_produto_documental"] / quantidade_base)
    codigo_principal = (decisao.get("codigo_principal") or "").strip()
    if decisao.get("usar_cean_como_principal") is True:
        codigo_principal = _gtin_canonico(item["ean"])
    if not codigo_principal:
        raise ValidationError("Confirme ou informe o código principal do novo produto.")
    dados_form = {
        "codigo_barras": codigo_principal,
        "codigo_interno": "",
        "nome": (decisao.get("nome") or item["descricao"]).strip(),
        "descricao": "",
        "tipo_produto": "MERCADORIA",
        "categoria": decisao.get("categoria_id"),
        "marca": "",
        "unidade": unidade_base,
        "unidade_compra": unidade_compra,
        "fator_conversao_compra": str(fator),
        "peso_liquido": "",
        "peso_bruto": "",
        "preco_custo": str(custo_base),
        "margem_desejada_percentual": "",
        "preco_venda": decisao.get("preco_venda"),
        "preco_promocional": "",
        "estoque_minimo": "0",
        "exige_lote": "",
        "vendido_no_pdv": "on",
        "vendido_no_marketplace": "",
        "produtos_similares": [],
        "ncm": "",
        "cest": "",
        "origem_mercadoria": "",
        "cst_icms": "",
        "csosn": "",
        "aliquota_icms": "",
        "reducao_base_icms": "",
        "aliquota_fcp": "",
        "cst_pis": "",
        "aliquota_pis": "",
        "cst_cofins": "",
        "aliquota_cofins": "",
        "cst_ipi": "",
        "codigo_enquadramento_ipi": "",
        "aliquota_ipi": "",
        "cst_ibs_cbs": "",
        "classificacao_tributaria_ibs_cbs": "",
        "is_active": "on",
    }
    form = ProdutoForm(data=dados_form)
    if not form.is_valid():
        mensagens = [mensagem for erros in form.errors.values() for mensagem in erros]
        raise ValidationError(mensagens)
    return form.save(), fator


def _auditar(usuario, acao, produto, fornecedor, item, descricao, ip):
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="compras",
        acao=acao,
        descricao=(
            f"{descricao} Origem: importação NF-e assistida; item {item['numero'] or '?'}; "
            f"fornecedor {fornecedor.pk}; produto {produto.pk}; unidade documental "
            f"{item['unidade_comercial']}. Nenhum XML foi armazenado."
        ),
        objeto_tipo="Produto",
        objeto_id=str(produto.pk),
        ip=ip,
    )


@transaction.atomic
def aplicar_resolucoes_e_importar_xml(
    conteudo,
    *,
    hash_analisado,
    decisoes,
    usuario,
    gerar_conta_financeira=True,
    ip=None,
):
    if not hmac.compare_digest(hash_xml(conteudo), (hash_analisado or "").strip().lower()):
        raise ValidationError("O arquivo XML mudou desde a análise. Analise novamente antes de confirmar.")
    dados = ler_xml_nfe(conteudo)
    _, fornecedor = _resolver_contexto_importacao(dados, usuario)
    decisoes_por_item = {str(decisao.get("numero", "")): decisao for decisao in decisoes}

    for item in _itens_unicos(dados):
        if item["unidade_comercial"] not in UNIDADES_DOCUMENTAIS:
            raise ValidationError(
                f"A unidade {item['unidade_comercial'] or '-'} do item {item['numero'] or '?'} é inválida."
            )
        try:
            produto, codigo = _localizar_produto(item, fornecedor)
            if produto is not None:
                _converter_item_para_unidade_base(item, produto, codigo)
                continue
            status = STATUS_PRODUTO_NAO_ENCONTRADO
        except ErroAnaliseItem as exc:
            status = exc.status
        if status not in {STATUS_PRODUTO_NAO_ENCONTRADO, STATUS_CONVERSAO_NAO_CONFIGURADA}:
            raise ValidationError("O item possui conflito ou dado inválido e não pode ser resolvido pelo assistente.")
        if not has_role(usuario, CADASTROS):
            raise PermissionDenied("Seu perfil pode analisar, mas não pode alterar o cadastro de produtos.")
        decisao = decisoes_por_item.get(str(item["numero"]))
        if not decisao:
            raise ValidationError(f"Informe uma decisão para o item {item['numero'] or '?'}.")

        acao = decisao.get("acao")
        produto_criado = False
        if status == STATUS_PRODUTO_NAO_ENCONTRADO and acao == "vincular":
            produto = _produto_escolhido(decisao.get("produto_id"))
        elif status == STATUS_PRODUTO_NAO_ENCONTRADO and acao == "cadastrar":
            produto, fator_novo = _criar_produto(item, decisao)
            produto_criado = True
            codigo_novo, codigo_criado = _salvar_codigo_embalagem(produto, item, fator_novo)
            _auditar(
                usuario,
                "CADASTRO_PRODUTO_ASSISTIDO_XML",
                produto,
                fornecedor,
                item,
                "Produto criado com dados operacionais confirmados; tributação de saída permaneceu vazia.",
                ip,
            )
            _auditar(
                usuario,
                "CONFIGURACAO_EMBALAGEM_XML",
                produto,
                fornecedor,
                item,
                f"Conversão confirmada: 1 {item['unidade_comercial']} = {fator_novo} "
                f"{produto.unidade}; código adicional "
                f"{'criado' if codigo_criado else 'reutilizado/dispensado'}; embalagem padrão definida.",
                ip,
            )
        elif status == STATUS_CONVERSAO_NAO_CONFIGURADA and acao == "configurar":
            produto = Produto.objects.select_for_update().get(pk=produto.pk)
        else:
            raise ValidationError("A decisão não é compatível com a pendência encontrada.")

        vinculo_criado = _validar_vinculo_fornecedor(produto, fornecedor, item["codigo"])
        if vinculo_criado:
            _auditar(
                usuario,
                "VINCULO_PRODUTO_FORNECEDOR_XML",
                produto,
                fornecedor,
                item,
                f"Código do fornecedor {item['codigo']} vinculado ao produto.",
                ip,
            )

        precisa_configurar = (
            status == STATUS_CONVERSAO_NAO_CONFIGURADA
            or item["unidade_comercial"] not in {produto.unidade, "PAC" if produto.unidade == "PCT" else produto.unidade}
        )
        if precisa_configurar and not produto_criado:
            fator, codigo_embalagem, codigo_criado, padrao_alterado = _configurar_embalagem(produto, item, decisao)
            _auditar(
                usuario,
                "CONFIGURACAO_EMBALAGEM_XML",
                produto,
                fornecedor,
                item,
                f"Conversão confirmada: 1 {item['unidade_comercial']} = {fator} {produto.unidade}; "
                f"código adicional {'criado' if codigo_criado else 'reutilizado/dispensado'}; "
                f"embalagem padrão {'alterada' if padrao_alterado else 'preservada'}.",
                ip,
            )

    return importar_xml_entrada(
        conteudo,
        usuario=usuario,
        gerar_conta_financeira=gerar_conta_financeira,
        ip=ip,
    )
