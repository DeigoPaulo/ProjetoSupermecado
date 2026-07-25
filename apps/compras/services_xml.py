from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Filial
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Produto

from .models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra


LIMITE_XML_BYTES = 5 * 1024 * 1024
CENTAVOS = Decimal("0.01")


def _digitos(valor):
    return "".join(caractere for caractere in (valor or "") if caractere.isdigit())


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
            raise ValidationError("Data de emissao invalida no XML.") from None


def _sem_namespace(tag):
    return tag.rsplit("}", 1)[-1]


def ler_xml_nfe(conteudo):
    if not conteudo:
        raise ValidationError("O arquivo XML esta vazio.")
    if len(conteudo) > LIMITE_XML_BYTES:
        raise ValidationError("O arquivo XML deve ter no maximo 5 MB.")

    conteudo_maiusculo = conteudo.upper()
    if b"<!DOCTYPE" in conteudo_maiusculo or b"<!ENTITY" in conteudo_maiusculo:
        raise ValidationError("XML com DTD ou entidades externas nao e permitido.")

    try:
        raiz = ElementTree.fromstring(conteudo)
    except ElementTree.ParseError:
        raise ValidationError("O arquivo enviado nao e um XML valido.") from None

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
        raise ValidationError("XML sem protocolo de autorizacao da NF-e.")
    cstat = _texto(protocolo, caminho("cStat"))
    if cstat != "100":
        raise ValidationError(f"A NF-e nao esta autorizada (cStat {cstat or 'ausente'}).")

    identificador = (inf_nfe.attrib.get("Id") or "").strip()
    chave = identificador[3:] if identificador.startswith("NFe") else identificador
    chave = _digitos(chave)
    if len(chave) != 44:
        raise ValidationError("Chave de acesso da NF-e ausente ou invalida.")
    chave_protocolada = _digitos(_texto(protocolo, caminho("chNFe"), obrigatorio=True, rotulo="chave protocolada"))
    if chave_protocolada != chave:
        raise ValidationError("A chave da NF-e difere da chave do protocolo de autorizacao.")

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
            "codigo": _texto(produto, caminho("cProd"), obrigatorio=True, rotulo="codigo do produto"),
            "ean": _texto(produto, caminho("cEAN")),
            "ean_tributavel": _texto(produto, caminho("cEANTrib")),
            "descricao": _texto(produto, caminho("xProd"), obrigatorio=True, rotulo="descricao do produto"),
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
                    raise ValidationError("Data de fabricacao ou validade invalida em lote da NF-e.") from None
                if fabricacao and validade and fabricacao > validade:
                    raise ValidationError("A NF-e possui lote com fabricacao posterior a validade.")
                lotes_item.append({
                    "quantidade": quantidade_lote,
                    "codigo_lote": _texto(rastro, caminho("nLote"), obrigatorio=True, rotulo="codigo do lote"),
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
                    total_lote / lote_item["quantidade"]
                ).quantize(CENTAVOS, rounding=ROUND_HALF_UP),
                "total": total_lote,
            })
    if not itens:
        raise ValidationError("A NF-e nao possui itens de produto.")

    vencimentos = []
    for duplicata in inf_nfe.findall(f".//{namespace}dup"):
        valor = _texto(duplicata, caminho("dVenc"))
        if valor:
            try:
                vencimentos.append(date.fromisoformat(valor))
            except ValueError:
                raise ValidationError("Data de vencimento invalida no XML.") from None

    data_valor = _texto(ide, caminho("dhEmi")) or _texto(ide, caminho("dEmi"))
    total_nfe = next((elemento for elemento in inf_nfe.iter() if _sem_namespace(elemento.tag) == "ICMSTot"), None)
    if total_nfe is None:
        raise ValidationError("XML sem os totais da NF-e.")
    total_documento = _decimal(
        _texto(total_nfe, caminho("vNF"), obrigatorio=True, rotulo="total da NF-e"),
        "total da NF-e",
    ).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    if total_documento < 0:
        raise ValidationError("O total da NF-e nao pode ser negativo.")
    emitente_cnpj = _digitos(_texto(emitente, caminho("CNPJ"), obrigatorio=True, rotulo="CNPJ do emitente"))
    destinatario_cnpj = _digitos(_texto(destinatario, caminho("CNPJ"), obrigatorio=True, rotulo="CNPJ do destinatario"))
    if len(emitente_cnpj) != 14 or len(destinatario_cnpj) != 14:
        raise ValidationError("CNPJ do emitente ou destinatario invalido no XML.")

    return {
        "chave": chave,
        "numero_documento": _texto(ide, caminho("nNF"), obrigatorio=True, rotulo="numero da NF-e"),
        "data_emissao": _data_emissao(data_valor),
        "emitente_cnpj": emitente_cnpj,
        "emitente_nome": _texto(emitente, caminho("xNome")),
        "destinatario_cnpj": destinatario_cnpj,
        "vencimento": min(vencimentos) if vencimentos else None,
        "total_documento": total_documento,
        "itens": itens,
    }


def _registro_unico_por_cnpj(queryset, cnpj, rotulo):
    encontrados = [objeto for objeto in queryset if _digitos(objeto.cnpj) == cnpj]
    if not encontrados:
        raise ValidationError(f"Nenhum {rotulo} ativo encontrado para o CNPJ {cnpj}.")
    if len(encontrados) > 1:
        raise ValidationError(f"Ha mais de um {rotulo} ativo com o CNPJ {cnpj}; corrija o cadastro.")
    return encontrados[0]


def _localizar_produto(item):
    eans = {
        codigo.strip()
        for codigo in (item["ean"], item["ean_tributavel"])
        if codigo and codigo.strip().upper() not in {"SEM GTIN", "SEM-GTIN"}
    }
    produto = Produto.all_objects.filter(codigo_barras__in=eans, is_active=True).first() if eans else None
    if produto:
        return produto

    codigo = item["codigo"].strip()
    candidatos = list(
        Produto.all_objects.filter(
            Q(codigo_interno__iexact=codigo) | Q(codigo_barras__iexact=codigo),
            is_active=True,
        )[:2]
    )
    if len(candidatos) == 1:
        return candidatos[0]
    return None


def importar_xml_entrada(conteudo, *, usuario, gerar_conta_financeira=True, ip=None):
    dados = ler_xml_nfe(conteudo)
    fornecedor = _registro_unico_por_cnpj(
        Fornecedor.objects.filter(is_active=True),
        dados["emitente_cnpj"],
        "fornecedor",
    )
    filiais = Filial.objects.filter(is_active=True).select_related("empresa")
    filiais_compativeis = [
        filial
        for filial in filiais
        if _digitos(filial.cnpj or filial.empresa.cnpj) == dados["destinatario_cnpj"]
    ]
    if not filiais_compativeis:
        raise ValidationError(f"Nenhuma filial ativa encontrada para o CNPJ {dados['destinatario_cnpj']}.")
    if len(filiais_compativeis) > 1:
        raise ValidationError("Ha mais de uma filial ativa para o CNPJ destinatario; corrija o cadastro.")
    filial = filiais_compativeis[0]

    itens_resolvidos = []
    nao_encontrados = []
    for item in dados["itens"]:
        produto = _localizar_produto(item)
        if produto is None:
            nao_encontrados.append(
                f"item {item['numero'] or '?'}: {item['descricao']} "
                f"(cProd {item['codigo']}, GTIN {item['ean'] or item['ean_tributavel'] or '-'})"
            )
        else:
            itens_resolvidos.append((item, produto))
    if nao_encontrados:
        raise ValidationError(
            ["Nenhuma entrada foi criada. Cadastre ou corrija os produtos sem correspondencia:"] + nao_encontrados
        )

    with transaction.atomic():
        if EntradaCompra.objects.select_for_update().filter(chave_acesso_xml=dados["chave"]).exists():
            raise ValidationError("Esta NF-e ja foi importada.")

        entrada = EntradaCompra.objects.create(
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
            )
            for item, produto in itens_resolvidos
        ])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="IMPORTACAO_XML_ENTRADA",
            descricao=(
                f"NF-e {dados['chave']} importada na entrada em rascunho {entrada.id}, "
                f"com {len(itens_resolvidos)} item(ns). Nenhum estoque ou financeiro foi movimentado."
            ),
            objeto_tipo="EntradaCompra",
            objeto_id=str(entrada.id),
            ip=ip,
        )
        return entrada
