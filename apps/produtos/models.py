from django.core.validators import FileExtensionValidator
from django.db import models


VALIDAR_IMAGEM_PNG_JPEG = FileExtensionValidator(
    allowed_extensions=["png", "jpg", "jpeg"],
    message="Envie uma imagem PNG, JPG ou JPEG.",
)


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Categoria(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Marca(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class UnidadeMedida(models.TextChoices):
    UNIDADE = "UN", "Unidade"
    QUILO = "KG", "Quilo"
    GRAMA = "G", "Grama"
    LITRO = "L", "Litro"
    METRO = "M", "Metro"


class OrigemMercadoria(models.TextChoices):
    NACIONAL = "0", "0 - Nacional"
    ESTRANGEIRA_IMPORTACAO_DIRETA = "1", "1 - Estrangeira, importacao direta"
    ESTRANGEIRA_MERCADO_INTERNO = "2", "2 - Estrangeira, adquirida no mercado interno"
    NACIONAL_CONTEUDO_IMPORTACAO_SUPERIOR_40 = "3", "3 - Nacional, conteudo importado superior a 40%"
    NACIONAL_PROCESSOS_BASICOS = "4", "4 - Nacional, processos produtivos basicos"
    NACIONAL_CONTEUDO_IMPORTACAO_INFERIOR_40 = "5", "5 - Nacional, conteudo importado ate 40%"
    ESTRANGEIRA_SEM_SIMILAR = "6", "6 - Estrangeira, sem similar nacional"
    ESTRANGEIRA_MERCADO_INTERNO_SEM_SIMILAR = "7", "7 - Estrangeira interna, sem similar nacional"
    NACIONAL_CONTEUDO_IMPORTACAO_SUPERIOR_70 = "8", "8 - Nacional, conteudo importado superior a 70%"


class Produto(models.Model):
    codigo_barras = models.CharField(max_length=80, unique=True)
    codigo_interno = models.CharField(max_length=80, blank=True)
    nome = models.CharField(max_length=255)
    descricao = models.TextField(blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="produtos")
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="produtos", null=True, blank=True)
    unidade = models.CharField(max_length=3, choices=UnidadeMedida.choices, default=UnidadeMedida.UNIDADE)
    produto_pesavel = models.BooleanField(default=False)
    preco_custo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preco_venda = models.DecimalField(max_digits=10, decimal_places=2)
    preco_promocional = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estoque_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    exige_lote = models.BooleanField(
        "Exigir lote nas novas entradas",
        default=False,
        help_text="Quando ativo, novas entradas deste produto devem informar um lote. O saldo legado continua utilizavel.",
    )
    vendido_no_pdv = models.BooleanField(default=True)
    vendido_no_marketplace = models.BooleanField(default=False)
    imagem = models.ImageField(upload_to="produtos/", blank=True, null=True, validators=[VALIDAR_IMAGEM_PNG_JPEG])
    ncm = models.CharField("NCM", max_length=8, blank=True)
    cest = models.CharField("CEST", max_length=7, blank=True)
    origem_mercadoria = models.CharField(max_length=1, choices=OrigemMercadoria.choices, blank=True)
    cst_icms = models.CharField("CST ICMS", max_length=2, blank=True)
    csosn = models.CharField("CSOSN", max_length=3, blank=True)
    aliquota_icms = models.DecimalField("Aliquota ICMS (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class ProdutoImagem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="galeria")
    imagem = models.ImageField(upload_to="produtos/galeria/", validators=[VALIDAR_IMAGEM_PNG_JPEG])
    legenda = models.CharField(max_length=120, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self):
        return self.legenda or f"Imagem de {self.produto}"

# Create your models here.
