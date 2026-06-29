from django.conf import settings
from django.db import models


class PromocaoProduto(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="promocoes")
    nome = models.CharField(max_length=255)
    preco_promocional = models.DecimalField(max_digits=10, decimal_places=2)
    inicio = models.DateTimeField()
    fim = models.DateTimeField()
    ativa = models.BooleanField(default=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="promocoes_criadas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inicio", "produto__nome"]

    def __str__(self):
        return f"{self.produto} - {self.preco_promocional}"

# Create your models here.
