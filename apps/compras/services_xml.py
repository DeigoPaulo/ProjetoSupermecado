from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core_money import quantizar_custo

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Filial
from apps.clientes.escopo import empresa_id_do_usuario
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import CodigoBarrasProduto, Produto, ProdutoFornecedor
from apps.fiscal.chave_acesso import canonicalizar_chave_acesso_estrutural
from apps.fiscal.estrategia_normalizacao_cnpj import canonicalizar_cnpj

from .models import (
    DuplicataNFeEntrada,
    EntradaCompra,
    FaturaNFeEntrada,
    ItemEntradaCompra,
    PedidoCompra,
    StatusEntradaCompra,
    StatusPedidoCompra,
)
from .services import avaliar_conferencia_entrada


LIMITE_XML_BYTES = 5 * 1024 * 1024
CENTAVOS = Decimal("0.01")
QUANTIDADE_TRES_CASAS = Decimal("0.001")
COMPRIMENTOS_GTIN = {8, 12, 13, 14}


def _texto(elemento, caminho, *, obrigatorio=False, rotulo=None):
    encontrado = elemento.find(caminho)
    valor = (encontrado.text or "").strip() if encontrado is not None else ""
    if obrigatorio and not valor:
        raise ValidationError(f"XML sem {rotulo or caminho}.")
    return valor


def _decimal(valor, rotulo):
    try:
        return Decimal(valor)
    except (InvalidOperation, TypeError):
        raise ValidationError(f"Valor invalido no XML para {rotulo}.") from None


def _data_emissao(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            raise ValidationError("Data de emissao inválida no XML.") from None


def _sem_namespace(tag):
    return tag.rsplit("}", 1)[-1]


def ler_xml_nfe(conteudo):
    if not conteudo:
        raise ValidationError("O arquivo XML está vazio.")
    if len(conteudo) > LIMITE_XML_BYTES:
        raise ValidationError("O arquivo XML deve ter no máximo 5 MB.")

    conteudo_maiusculo = conteudo.upper()
    if b"<!DOCTYPE" in conteudo_maiusculo or b"<!ENTITY" in conteudo_maiusculo:
        raise ValidationError("XML com DTD ou entidades externas não e permitido.")

    try:
        raiz = ElementTree.fromstring(conteudo)
    except ElementTree.ParseError:
        raise ValidationError("O arquivo enviado não e um XML valido.") from None

    if _sem_namespace(raiz.tag) not in {"nfeProc", "NFe"}:
        raise ValidationError("O XML deve representar uma NF-e.")

    inf_nfe = next((elemento for elemento in raiz.iter() if _sem_namespace(elemento.tag) == "infNFe"), None)
    if inf_nfe is None:
        raise ValidationError("XML sem os dados principais da NF-e.")

    namespace = ""
    if inf_nfe.tag.startswith("{"):
        namespace = inf_nfe.tag.split("}", 1)[0] + "}"
    caminho = lambda valor: "/".join(f"{namespace}{parte}" for parte in valor.split("/"))

    protocolo = next((elemento for elemento in raiz.iter() if _sem_namespace(elemento.tag) == "infProt"), None)
    if protocolo is None:
        raise ValidationError("XML sem protocolo de autorização da NF-e.")
    cstat = _texto(protocolo, caminho("cStat"))
    if cstat != "100":
        raise ValidationError(f"A NF-e não está autorizada (cStat {cstat or 'ausente'}).")

    identificador = (inf_nfe.attrib.get("Id") or "").strip()
    chave = identificador[3:] if identificador.startswith("NFe") else identificador
    chave = canonicalizar_chave_acesso_estrutural(chave)
    if len(chave) != 44:
        raise ValidationError("Chave de acesso da NF-e ausente ou inválida.")
    chave_protocolada = canonicalizar_chave_acesso_estrutural(
        _texto(protocolo, caminho("chNFe"), obrigatorio=True, rotulo="chave protocolada")
    )
    if chave_protocolada != chave:
        raise ValidationError("A chave da NF-e difere da chave do protocolo de autorização.")

    emitente = inf_nfe.find(caminho("emit"))
    destinatario = inf_nfe.find(caminho("dest"))
    ide = inf_nfe.find(caminho("ide"))
    if emitente is None or destinatario is None or ide is None:
        raise ValidationError("XML sem emitente, destinatario ou identificacao da NF-e.")

    itens = []
    for detalhe in inf_nfe.findall(caminho("det")):
        produto = detalhe.find(caminho("prod"))
        if produto is None:
            continue
        quantidade = _decimal(_texto(produto, caminho("qCom"), obrigatorio=True, rotulo="quantidade"), "quantidade")
        valor_total = _decimal(_texto(produto, caminho("vProd"), obrigatorio=True, rotulo="total do item"), "total do item")
        if quantidade <= 0:
            raise ValidationError("A NF-e possui item com quantidade menor ou igual a zero.")
        if valor_total < 0:
            raise ValidationError("A NF-e possui item com valor negativo.")
        dados_base = {
            "numero": detalhe.attrib.get("nItem", ""),
            "codigo": _texto(produto, caminho("cProd"), obrigatorio=True, rotulo="código do produto"),
            "ean": _texto(produto, caminho("cEAN")),
            "ean_tributavel": _texto(produto, caminho("cEANTrib")),
            "descricao": _texto(produto, caminho("xProd"), obrigatorio=True, rotulo="descrição do produto"),
            "unidade_comercial": _texto(
                produto, caminho("uCom"), obrigatorio=True, rotulo="unidade comercial"
            ).upper(),
            "quantidade_documental": quantidade,
            "valor_unitario_comercial": _decimal(
                _texto(produto, caminho("vUnCom"), obrigatorio=True, rotulo="valor unitário comercial"),
                "valor unitário comercial",
            ),
            "valor_produto_documental": valor_total,
        }
        rastros = produto.findall(caminho("rastro"))
        if rastros:
            lotes_item = []
            for rastro in rastros:
                quantidade_lote = _decimal(
                    _texto(rastro, caminho("qLote"), obrigatorio=True, rotulo="quantidade do lote"),
                    "quantidade do lote",
                )
                if quantidade_lote <= 0:
                    raise ValidationError("A NF-e possui lote com quantidade menor ou igual a zero.")
                try:
                    fabricacao = date.fromisoformat(_texto(rastro, caminho("dFab"))) if _texto(rastro, caminho("dFab")) else None
                    validade = date.fromisoformat(_texto(rastro, caminho("dVal"))) if _texto(rastro, caminho("dVal")) else None
                except ValueError:
                    raise ValidationError("Data de fabricação ou validade inválida em lote da NF-e.") from None
                if fabricacao and validade and fabricacao > validade:
                    raise ValidationError("A NF-e possui lote com fabricação posterior a validade.")
                lotes_item.append({
                    "quantidade": quantidade_lote,
                    "codigo_lote": _texto(rastro, caminho("nLote"), obrigatorio=True, rotulo="código do lote"),
                    "fabricacao": fabricacao,
                    "validade": validade,
                })
            if sum((lote["quantidade"] for lote in lotes_item), Decimal("0.000")) != quantidade:
                raise ValidationError("A soma das quantidades dos lotes difere da quantidade do item na NF-e.")
        else:
            lotes_item = [{
                "quantidade": quantidade,
                "codigo_lote": "",
                "fabricacao": None,
                "validade": None,
            }]

        total_distribuido = Decimal("0.00")
        for indice, lote_item in enumerate(lotes_item):
            if indice == len(lotes_item) - 1:
                total_lote = valor_total.quantize(CENTAVOS, rounding=ROUND_HALF_UP) - total_distribuido
            else:
                total_lote = (
                    valor_total * lote_item["quantidade"] / quantidade
                ).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
                total_distribuido += total_lote
            itens.append({
                **dados_base,
                **lote_item,
                "custo_unitario": (
                    quantizar_custo(total_lote / lote_item["quantidade"])
                ),
                "total": total_lote,
            })
    if not itens:
        raise ValidationError("A NF-e não possui itens de produto.")

    cobranca = inf_nfe.find(caminho("cobr"))
    fatura_xml = cobranca.find(caminho("fat")) if cobranca is not None else None
    fatura = None
    if fatura_xml is not None:
        fatura = {
            "numero": _texto(fatura_xml, caminho("nFat")),
            "valor_original": _decimal(_texto(fatura_xml, caminho("vOrig")), "valor original da fatura").quantize(CENTAVOS) if _texto(fatura_xml, caminho("vOrig")) else None,
            "valor_desconto": _decimal(_texto(fatura_xml, caminho("vDesc")), "desconto da fatura").quantize(CENTAVOS) if _texto(fatura_xml, caminho("vDesc")) else None,
            "valor_liquido": _decimal(_texto(fatura_xml, caminho("vLiq")), "valor líquido da fatura").quantize(CENTAVOS) if _texto(fatura_xml, caminho("vLiq")) else None,
        }

    duplicatas = []
    vencimento_anterior = None
    elementos_duplicata = cobranca.findall(caminho("dup")) if cobranca is not None else []
    if len(elementos_duplicata) > 120:
        raise ValidationError("A NF-e excede o limite de 120 parcelas.")
    for sequencia, duplicata in enumerate(elementos_duplicata, start=1):
        numero = _texto(duplicata, caminho("nDup"), obrigatorio=True, rotulo="número da parcela")
        numero_esperado = f"{sequencia:03d}"
        if numero != numero_esperado:
            raise ValidationError(
                f"As parcelas da NF-e devem ser sequenciais; esperado {numero_esperado}."
            )
        vencimento_texto = _texto(
            duplicata, caminho("dVenc"), obrigatorio=True, rotulo="vencimento da parcela"
        )
        try:
            vencimento = date.fromisoformat(vencimento_texto)
        except ValueError:
            raise ValidationError("Data de vencimento inválida no XML.") from None
        if vencimento_anterior and vencimento < vencimento_anterior:
            raise ValidationError("Os vencimentos das parcelas devem estar em ordem crescente.")
        valor = _decimal(
            _texto(duplicata, caminho("vDup"), obrigatorio=True, rotulo="valor da parcela"),
            "valor da parcela",
        ).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        if valor <= 0:
            raise ValidationError("O valor de cada parcela da NF-e deve ser positivo.")
        duplicatas.append({
            "sequencia": sequencia,
            "numero": numero,
            "vencimento": vencimento,
            "valor": valor,
        })
        vencimento_anterior = vencimento

    if duplicatas and fatura and fatura["valor_liquido"] is not None:
        total_duplicatas = sum((item["valor"] for item in duplicatas), Decimal("0.00"))
        if total_duplicatas != fatura["valor_liquido"].quantize(CENTAVOS):
            raise ValidationError("A soma das parcelas difere do valor líquido da fatura.")

    data_valor = _texto(ide, caminho("dhEmi")) or _texto(ide, caminho("dEmi"))
    total_nfe = next((elemento for elemento in inf_nfe.iter() if _sem_namespace(elemento.tag) == "ICMSTot"), None)
    if total_nfe is None:
        raise ValidationError("XML sem os totais da NF-e.")
    total_documento = _decimal(
        _texto(total_nfe, caminho("vNF"), obrigatorio=True, rotulo="total da NF-e"),
        "total da NF-e",
    ).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    if total_documento < 0:
        raise ValidationError("O total da NF-e não pode ser negativo.")
    emitente_cnpj = canonicalizar_cnpj(
        _texto(emitente, caminho("CNPJ"), obrigatorio=True, rotulo="CNPJ do emitente")
    )
    destinatario_cnpj = canonicalizar_cnpj(
        _texto(destinatario, caminho("CNPJ"), obrigatorio=True, rotulo="CNPJ do destinatario")
    )
    if len(emitente_cnpj) != 14 or len(destinatario_cnpj) != 14:
        raise ValidationError("CNPJ do emitente ou destinatario inválido no XML.")

    return {
        "chave": chave,
        "numero_documento": _texto(ide, caminho("nNF"), obrigatorio=True, rotulo="número da NF-e"),
        "data_emissao": _data_emissao(data_valor),
        "emitente_cnpj": emitente_cnpj,
        "emitente_nome": _texto(emitente, caminho("xNome")),
        "destinatario_cnpj": destinatario_cnpj,
        "vencimento": duplicatas[0]["vencimento"] if duplicatas else None,
        "fatura": fatura,
        "duplicatas": duplicatas,
        "total_documento": total_documento,
        "itens": itens,
    }


def _registro_unico_por_cnpj(queryset, cnpj, rotulo):
    encontrados = [
        objeto for objeto in queryset if canonicalizar_cnpj(objeto.cnpj) == cnpj
    ]
    if not encontrados:
        raise ValidationError(f"Nenhum {rotulo} ativo encontrado para o CNPJ {cnpj}.")
    if len(encontrados) > 1:
        raise ValidationError(f"Ha mais de um {rotulo} ativo com o CNPJ {cnpj}; corrija o cadastro.")
    return encontrados[0]


def _gtin_canonico(codigo):
    codigo = (codigo or "").strip()
    if not codigo.isdigit() or len(codigo) not in COMPRIMENTOS_GTIN:
        return None
    soma = sum(
        int(digito) * (3 if indice % 2 == 0 else 1)
        for indice, digito in enumerate(reversed(codigo[:-1]))
    )
    digito_esperado = (10 - (soma % 10)) % 10
    if int(codigo[-1]) != digito_esperado:
        return None
    return codigo.zfill(14)


def _representacoes_equivalentes_gtin(codigo):
    codigo = (codigo or "").strip()
    if not codigo or codigo.upper() in {"SEM GTIN", "SEM-GTIN"}:
        return set()
    canonico = _gtin_canonico(codigo)
    representacoes = {codigo}
    if canonico:
        for comprimento in COMPRIMENTOS_GTIN:
            candidato = canonico[-comprimento:]
            if candidato.zfill(14) == canonico and _gtin_canonico(candidato) == canonico:
                representacoes.add(candidato)
    return representacoes


def _objetos_por_codigo_gtin(queryset, atributo, codigo):
    representacoes = _representacoes_equivalentes_gtin(codigo)
    if not representacoes:
        return []
    return list(queryset.filter(**{f"{atributo}__in": representacoes}))


def _localizar_produto(item, fornecedor):
    produtos = Produto.all_objects.filter(is_active=True)
    codigos_adicionais = (
        CodigoBarrasProduto.objects.filter(is_active=True, produto__is_active=True).select_related("produto")
    )
    evidencias = []
    codigo_comercial = None

    for campo, rotulo in (("ean", "cEAN"), ("ean_tributavel", "cEANTrib")):
        valor = (item[campo] or "").strip()
        for produto in _objetos_por_codigo_gtin(produtos, "codigo_barras", valor):
            evidencias.append((rotulo, valor, produto))
        codigos_encontrados = _objetos_por_codigo_gtin(codigos_adicionais, "codigo", valor)
        for codigo_adicional in codigos_encontrados:
            evidencias.append((f"{rotulo} adicional", valor, codigo_adicional.produto))
        if campo == "ean":
            exatos = [codigo for codigo in codigos_encontrados if codigo.codigo == valor]
            if len(exatos) > 1:
                raise ValidationError(
                    f"Código comercial ambíguo no item {item['numero'] or '?'}: {valor}."
                )
            codigo_comercial = exatos[0] if exatos else None

    codigo_fornecedor = item["codigo"].strip()
    candidatos_codigo = list(
        Produto.all_objects.filter(
            Q(codigo_interno__iexact=codigo_fornecedor) | Q(codigo_barras__iexact=codigo_fornecedor),
            is_active=True,
        )
    )
    evidencias.extend(("cProd", codigo_fornecedor, produto) for produto in candidatos_codigo)
    vinculos_fornecedor = list(
        ProdutoFornecedor.objects.filter(
            fornecedor=fornecedor,
            codigo_no_fornecedor__iexact=codigo_fornecedor,
            is_active=True,
            produto__is_active=True,
        ).select_related("produto")
    )
    evidencias.extend(
        ("cProd do fornecedor", codigo_fornecedor, vinculo.produto)
        for vinculo in vinculos_fornecedor
    )

    produtos_por_id = {produto.pk: produto for _, _, produto in evidencias}
    if len(produtos_por_id) > 1:
        detalhes = ", ".join(
            f"{fonte} {codigo or '-'} -> {produto.nome}"
            for fonte, codigo, produto in evidencias
        )
        raise ValidationError(
            f"Conflito na identificação do produto do item {item['numero'] or '?'}. {detalhes}."
        )
    if not produtos_por_id:
        return None, None
    return next(iter(produtos_por_id.values())), codigo_comercial


def _quantidade_com_tres_casas(valor, *, numero_item, rotulo):
    quantizada = valor.quantize(QUANTIDADE_TRES_CASAS)
    if valor != quantizada:
        raise ValidationError(
            f"Precisão incompatível no item {numero_item or '?'}: {rotulo} {valor} "
            "não pode ser representada exatamente com 3 casas decimais."
        )
    return quantizada


def _converter_item_para_unidade_base(item, produto, codigo_comercial):
    unidade_documental = item["unidade_comercial"]
    evidencias_fator = []
    if codigo_comercial is not None:
        evidencias_fator.append(("CODIGO_BARRAS_ADICIONAL", codigo_comercial.fator_conversao))
    if unidade_documental == produto.unidade:
        evidencias_fator.append(("UNIDADE_BASE", Decimal("1.000")))
    if unidade_documental == produto.unidade_compra:
        evidencias_fator.append(("UNIDADE_COMPRA", produto.fator_conversao_compra))

    invalidas = [(fonte, fator) for fonte, fator in evidencias_fator if fator is None or fator <= 0]
    if invalidas:
        raise ValidationError(
            f"Fator de conversão inválido para o item {item['numero'] or '?'}; corrija o cadastro."
        )
    fatores = {fator for _, fator in evidencias_fator}
    if len(fatores) > 1:
        detalhes = " e ".join(f"{fonte} informa fator {fator}" for fonte, fator in evidencias_fator)
        raise ValidationError(
            f"Conversão de unidade ambígua para o item {item['numero'] or '?'}. {detalhes}."
        )
    if not evidencias_fator:
        raise ValidationError(
            f"Unidade comercial {unidade_documental or '-'} desconhecida no item {item['numero'] or '?'}. "
            "Configure a unidade de compra ou um código de barras adicional com fator de conversão."
        )

    fator = evidencias_fator[0][1]
    quantidade_base = _quantidade_com_tres_casas(
        item["quantidade"] * fator,
        numero_item=item["numero"],
        rotulo="quantidade convertida",
    )
    quantidade_base_item = _quantidade_com_tres_casas(
        item["quantidade_documental"] * fator,
        numero_item=item["numero"],
        rotulo="quantidade total convertida",
    )
    custo_base = quantizar_custo(item["total"] / quantidade_base)
    fontes = [fonte for fonte, valor in evidencias_fator if valor == fator]
    fonte_conversao = "+".join(fontes)
    snapshot = {
        "contrato": "purchase_xml_unit_conversion_v1",
        "nItem": str(item["numero"]),
        "cProd": item["codigo"],
        "cEAN": item["ean"],
        "cEANTrib": item["ean_tributavel"],
        "uCom": unidade_documental,
        "qCom": str(item["quantidade_documental"]),
        "vUnCom": str(item["valor_unitario_comercial"]),
        "vProd": str(item["valor_produto_documental"]),
        "unidade_base": produto.unidade,
        "fator_conversao": str(fator.quantize(QUANTIDADE_TRES_CASAS)),
        "quantidade_base": str(quantidade_base),
        "quantidade_base_item": str(quantidade_base_item),
        "custo_unitario_base": str(custo_base),
        "fonte_conversao": fonte_conversao,
    }
    if item["codigo_lote"]:
        snapshot["qLote"] = str(item["quantidade"])

    return {
        **item,
        "quantidade": quantidade_base,
        "custo_unitario": custo_base,
        "origem_xml_snapshot": snapshot,
    }


def importar_xml_entrada(conteudo, *, usuario, gerar_conta_financeira=True, ip=None):
    dados = ler_xml_nfe(conteudo)
    filiais = Filial.objects.filter(is_active=True).select_related("empresa")
    empresa_id = empresa_id_do_usuario(usuario)
    if empresa_id is not None:
        filiais = filiais.filter(empresa_id=empresa_id)
    filiais_compativeis = [
        filial
        for filial in filiais
        if canonicalizar_cnpj(filial.cnpj or filial.empresa.cnpj) == dados["destinatario_cnpj"]
    ]
    if not filiais_compativeis:
        raise ValidationError(f"Nenhuma filial ativa encontrada para o CNPJ {dados['destinatario_cnpj']}.")
    if len(filiais_compativeis) > 1:
        raise ValidationError("Ha mais de uma filial ativa para o CNPJ destinatario; corrija o cadastro.")
    filial = filiais_compativeis[0]
    fornecedores = Fornecedor.objects.filter(is_active=True, empresa_id=filial.empresa_id)
    if empresa_id is None:
        fornecedores = Fornecedor.objects.filter(
            Q(empresa_id=filial.empresa_id) | Q(empresa__isnull=True),
            is_active=True,
        )
    fornecedor = _registro_unico_por_cnpj(
        fornecedores,
        dados["emitente_cnpj"],
        "fornecedor",
    )

    itens_resolvidos = []
    nao_encontrados = []
    for item in dados["itens"]:
        produto, codigo_comercial = _localizar_produto(item, fornecedor)
        if produto is None:
            nao_encontrados.append(
                f"item {item['numero'] or '?'}: {item['descricao']} "
                f"(cProd {item['codigo']}, GTIN {item['ean'] or item['ean_tributavel'] or '-'})"
            )
        else:
            itens_resolvidos.append(
                (_converter_item_para_unidade_base(item, produto, codigo_comercial), produto)
            )
    if nao_encontrados:
        raise ValidationError(
            ["Nenhuma entrada foi criada. Cadastre ou corrija os produtos sem correspondencia:"] + nao_encontrados
        )
    sem_lote_obrigatorio = [
        f"item {item['numero'] or '?'}: {produto.nome}"
        for item, produto in itens_resolvidos
        if produto.exige_lote and not (item["codigo_lote"] or "").strip()
    ]
    if sem_lote_obrigatorio:
        raise ValidationError(
            ["Nenhuma entrada foi criada. A NF-e não informou rastro para produtos que exigem lote:"]
            + sem_lote_obrigatorio
        )

    with transaction.atomic():
        if EntradaCompra.objects.select_for_update().filter(chave_acesso_xml=dados["chave"]).exists():
            raise ValidationError("Esta NF-e ja foi importada.")

        itens_xml_por_produto = {}
        for item, produto in itens_resolvidos:
            quantidade, total = itens_xml_por_produto.get(produto.pk, (Decimal("0.000"), Decimal("0.00")))
            itens_xml_por_produto[produto.pk] = (quantidade + item["quantidade"], total + item["total"])

        pedidos_exatos = []
        pedidos_compativeis = PedidoCompra.objects.select_for_update().filter(
            fornecedor=fornecedor,
            filial=filial,
            status=StatusPedidoCompra.ENVIADO,
        ).prefetch_related("itens")
        for pedido in pedidos_compativeis:
            itens_pedido_por_produto = {}
            for item in pedido.itens.all():
                quantidade, total = itens_pedido_por_produto.get(item.produto_id, (Decimal("0.000"), Decimal("0.00")))
                itens_pedido_por_produto[item.produto_id] = (
                    quantidade + item.quantidade,
                    total + item.total_previsto,
                )
            if itens_pedido_por_produto == itens_xml_por_produto:
                pedidos_exatos.append(pedido)

        # Somente um pedido inteiramente igual pode ser associado sem intervenção humana.
        pedido_origem = pedidos_exatos[0] if len(pedidos_exatos) == 1 else None

        entrada = EntradaCompra.objects.create(
            pedido_origem=pedido_origem,
            fornecedor=fornecedor,
            filial=filial,
            usuario=usuario,
            numero_documento=dados["numero_documento"],
            chave_acesso_xml=dados["chave"],
            importada_xml_em=timezone.now(),
            data_emissao=dados["data_emissao"],
            vencimento_financeiro=dados["vencimento"],
            gerar_conta_financeira=gerar_conta_financeira,
            observacoes=(
                f"Entrada importada da NF-e {dados['chave']}. "
                "Revise os produtos, quantidades, custos e vencimento antes de finalizar."
            ),
            status=StatusEntradaCompra.RASCUNHO,
            total_produtos=sum((item["total"] for item, _ in itens_resolvidos), Decimal("0.00")),
            total_documento=dados["total_documento"],
        )
        ItemEntradaCompra.objects.bulk_create([
            ItemEntradaCompra(
                entrada=entrada,
                produto=produto,
                quantidade=item["quantidade"],
                custo_unitario=item["custo_unitario"],
                total=item["total"],
                atualizar_preco_custo=True,
                codigo_lote=item["codigo_lote"],
                fabricacao=item["fabricacao"],
                validade=item["validade"],
                numero_item_xml=item["numero"],
                origem_xml_snapshot=item["origem_xml_snapshot"],
            )
            for item, produto in itens_resolvidos
        ])
        if dados["fatura"] is not None or dados["duplicatas"]:
            fatura = FaturaNFeEntrada.objects.create(
                entrada=entrada,
                **(dados["fatura"] or {}),
            )
            DuplicataNFeEntrada.objects.bulk_create([
                DuplicataNFeEntrada(fatura=fatura, **duplicata)
                for duplicata in dados["duplicatas"]
            ])
        if pedido_origem:
            pedido_origem.status = StatusPedidoCompra.CONVERTIDO
            pedido_origem.save(update_fields=["status", "updated_at"])
        avaliar_conferencia_entrada(entrada)
        entrada.save(update_fields=["conferencia_status", "conferencia_resumo", "updated_at"])

        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="IMPORTACAO_XML_ENTRADA",
            descricao=(
                f"NF-e {dados['chave']} importada na entrada em rascunho {entrada.id}, "
                f"com {len(itens_resolvidos)} item(ns). Conferencia: {entrada.get_conferencia_status_display()}. "
                "Nenhum estoque ou financeiro foi movimentado."
            ),
            objeto_tipo="EntradaCompra",
            objeto_id=str(entrada.id),
            ip=ip,
        )
        return entrada
