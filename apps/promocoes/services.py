from django.utils import timezone

from .models import PromocaoProduto


def promocao_ativa_para_produto(produto, momento=None):
    momento = momento or timezone.now()
    return (
        PromocaoProduto.objects.filter(
            produto=produto,
            ativa=True,
            inicio__lte=momento,
            fim__gte=momento,
        )
        .order_by("preco_promocional", "-inicio")
        .first()
    )


def preco_atual_produto(produto, momento=None):
    promocao = promocao_ativa_para_produto(produto, momento)
    if promocao:
        return promocao.preco_promocional
    return produto.preco_promocional or produto.preco_venda
