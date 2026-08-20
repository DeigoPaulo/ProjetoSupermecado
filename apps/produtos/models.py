from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models, transaction


VALIDAR_IMAGEM_PNG_JPEG = FileExtensionValidator(
    allowed_extensions=["png", "jpg", "jpeg"],
    message="Envie uma imagem PNG, JPG ou JPEG.",
)


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class NivelCategoriaProduto(models.TextChoices):
    DEPARTAMENTO = "DEPARTAMENTO", "Departamento"
    SECAO = "SECAO", "Seção"
    GRUPO = "GRUPO", "Grupo"
    SUBGRUPO = "SUBGRUPO", "Subgrupo"


class Categoria(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    nivel = models.CharField(
        "Nível comercial", max_length=20, choices=NivelCategoriaProduto.choices, default=NivelCategoriaProduto.GRUPO
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="Classificação superior",
        on_delete=models.PROTECT,
        related_name="filhas",
        null=True,
        blank=True,
    )
    descricao = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["nome"]

    def clean(self):
        super().clean()
        if not self.parent:
            return
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "A classificação não pode ser superior de si mesma."})
        ordem = list(NivelCategoriaProduto.values)
        if ordem.index(self.parent.nivel) != ordem.index(self.nivel) - 1:
            raise ValidationError({"parent": "Selecione uma classificação de nível superior."})
        atual = self.parent
        visitados = {self.pk} if self.pk else set()
        while atual:
            if atual.pk in visitados:
                raise ValidationError({"parent": "A hierarquia informada forma um ciclo."})
            visitados.add(atual.pk)
            atual = atual.parent

    @property
    def caminho_completo(self):
        nomes = [self.nome]
        atual = self.parent
        visitados = {self.pk} if self.pk else set()
        while atual and atual.pk not in visitados:
            nomes.append(atual.nome)
            visitados.add(atual.pk)
            atual = atual.parent
        return " > ".join(reversed(nomes))

    def __str__(self):
        return self.caminho_completo


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
    CAIXA = "CX", "Caixa"
    FARDO = "FD", "Fardo"
    PACOTE = "PCT", "Pacote"


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


class TipoProduto(models.TextChoices):
    MERCADORIA = "MERCADORIA", "Mercadoria para revenda"
    INSUMO = "INSUMO", "Insumo"
    SERVICO = "SERVICO", "Serviço"
    IMOBILIZADO = "IMOBILIZADO", "Imobilizado"
    MATERIAL_CONSUMO = "MATERIAL_CONSUMO", "Material de consumo"


class BaseCalculoNutricional(models.TextChoices):
    CEM_GRAMAS = "100G", "100 g"
    CEM_MILILITROS = "100ML", "100 ml"


class DeclaracaoComponente(models.TextChoices):
    NAO_INFORMADO = "", "Não informado"
    CONTEM = "CONTEM", "Contém"
    NAO_CONTEM = "NAO_CONTEM", "Não contém"


class Produto(models.Model):
    codigo_barras = models.CharField(max_length=80, unique=True)
    codigo_interno = models.CharField(max_length=80, blank=True)
    nome = models.CharField(max_length=255)
    descricao = models.TextField(blank=True)
    tipo_produto = models.CharField(
        "Tipo comercial", max_length=20, choices=TipoProduto.choices, default=TipoProduto.MERCADORIA
    )
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="produtos")
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="produtos", null=True, blank=True)
    unidade = models.CharField(max_length=3, choices=UnidadeMedida.choices, default=UnidadeMedida.UNIDADE)
    unidade_compra = models.CharField(
        "Unidade de compra", max_length=3, choices=UnidadeMedida.choices, default=UnidadeMedida.UNIDADE
    )
    fator_conversao_compra = models.DecimalField(
        "Quantidade na unidade base",
        max_digits=12,
        decimal_places=3,
        default=1,
        validators=[MinValueValidator(0.001)],
        help_text="Quantidade da unidade base contida em uma unidade de compra.",
    )
    peso_liquido = models.DecimalField("Peso líquido (kg)", max_digits=12, decimal_places=3, null=True, blank=True)
    peso_bruto = models.DecimalField("Peso bruto (kg)", max_digits=12, decimal_places=3, null=True, blank=True)
    produto_pesavel = models.BooleanField(default=False)
    preco_custo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    margem_desejada_percentual = models.DecimalField(
        "Margem desejada (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(99.99)],
    )
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
    produtos_similares = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=True,
        help_text="Alternativas comerciais que podem substituir ou complementar este produto.",
    )
    imagem = models.ImageField(upload_to="produtos/", blank=True, null=True, validators=[VALIDAR_IMAGEM_PNG_JPEG])
    ncm = models.CharField("NCM", max_length=8, blank=True)
    cest = models.CharField("CEST", max_length=7, blank=True)
    origem_mercadoria = models.CharField(max_length=1, choices=OrigemMercadoria.choices, blank=True)
    cst_icms = models.CharField("CST ICMS", max_length=2, blank=True)
    csosn = models.CharField("CSOSN", max_length=3, blank=True)
    aliquota_icms = models.DecimalField("Aliquota ICMS (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    reducao_base_icms = models.DecimalField(
        "Redução da base ICMS (%)", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    aliquota_fcp = models.DecimalField(
        "Alíquota FCP (%)", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    codigo_beneficio_fiscal = models.CharField(
        "Código de benefício fiscal (cBenef)", max_length=10, blank=True
    )
    cst_pis = models.CharField("CST PIS", max_length=2, blank=True)
    aliquota_pis = models.DecimalField(
        "Alíquota PIS (%)", max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    cst_cofins = models.CharField("CST COFINS", max_length=2, blank=True)
    aliquota_cofins = models.DecimalField(
        "Alíquota COFINS (%)", max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    cst_ipi = models.CharField("CST IPI", max_length=2, blank=True)
    codigo_enquadramento_ipi = models.CharField("Código de enquadramento IPI (cEnq)", max_length=3, blank=True)
    aliquota_ipi = models.DecimalField(
        "Alíquota IPI (%)", max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    cst_ibs_cbs = models.CharField("CST IBS/CBS", max_length=3, blank=True)
    classificacao_tributaria_ibs_cbs = models.CharField(
        "Classificação tributária IBS/CBS (cClassTrib)", max_length=6, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["codigo_interno"],
                condition=~models.Q(codigo_interno=""),
                name="produtos_codigo_interno_unico_preenchido",
            )
        ]

    @classmethod
    def codigo_interno_disponivel(cls, referencia):
        numero = max(1, int(referencia or 1))
        while True:
            codigo = f"PRD-{numero:06d}"
            if not cls.all_objects.filter(codigo_interno=codigo).exists():
                return codigo
            numero += 1

    @classmethod
    def proximo_codigo_interno(cls):
        ultimo_id = cls.all_objects.order_by("-id").values_list("id", flat=True).first() or 0
        return cls.codigo_interno_disponivel(ultimo_id + 1)

    def save(self, *args, **kwargs):
        self.codigo_interno = (self.codigo_interno or "").strip().upper()
        novo_sem_codigo = self._state.adding and not self.codigo_interno
        if not novo_sem_codigo and not self.codigo_interno and self.pk:
            self.codigo_interno = self.codigo_interno_disponivel(self.pk)

        if not novo_sem_codigo:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            resultado = super().save(*args, **kwargs)
            self.codigo_interno = self.codigo_interno_disponivel(self.pk)
            type(self).all_objects.filter(pk=self.pk).update(codigo_interno=self.codigo_interno)
            return resultado

    @property
    def margem_atual_percentual(self):
        if not self.preco_venda:
            return None
        return ((self.preco_venda - self.preco_custo) / self.preco_venda * 100).quantize(Decimal("0.01"))

    @property
    def preco_venda_sugerido(self):
        if self.margem_desejada_percentual is None:
            return None
        divisor = Decimal("1") - (self.margem_desejada_percentual / Decimal("100"))
        return (self.preco_custo / divisor).quantize(Decimal("0.01"))

    def __str__(self):
        return self.nome


class InformacaoNutricional(models.Model):
    produto = models.OneToOneField(Produto, on_delete=models.CASCADE, related_name="informacao_nutricional")
    base_calculo = models.CharField(
        "Valores declarados por", max_length=5, choices=BaseCalculoNutricional.choices, default=BaseCalculoNutricional.CEM_GRAMAS
    )
    porcao_quantidade = models.DecimalField("Porção", max_digits=10, decimal_places=2, null=True, blank=True)
    porcao_unidade = models.CharField("Unidade da porção", max_length=10, blank=True, help_text="Ex.: g, ml ou unidade.")
    medida_caseira = models.CharField(max_length=120, blank=True, help_text="Ex.: 1 colher, 2 fatias ou 1 unidade.")
    porcoes_por_embalagem = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor_energetico_kcal = models.DecimalField("Valor energético (kcal)", max_digits=10, decimal_places=2, null=True, blank=True)
    carboidratos_g = models.DecimalField("Carboidratos (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    acucares_totais_g = models.DecimalField("Açúcares totais (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    acucares_adicionados_g = models.DecimalField("Açúcares adicionados (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    proteinas_g = models.DecimalField("Proteínas (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    gorduras_totais_g = models.DecimalField("Gorduras totais (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    gorduras_saturadas_g = models.DecimalField("Gorduras saturadas (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    gorduras_trans_g = models.DecimalField("Gorduras trans (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    fibra_alimentar_g = models.DecimalField("Fibra alimentar (g)", max_digits=10, decimal_places=2, null=True, blank=True)
    sodio_mg = models.DecimalField("Sódio (mg)", max_digits=10, decimal_places=2, null=True, blank=True)
    ingredientes = models.TextField(blank=True)
    alergicos = models.TextField("Alérgicos", blank=True)
    gluten = models.CharField("Glúten", max_length=12, choices=DeclaracaoComponente.choices, blank=True)
    lactose = models.CharField("Lactose", max_length=12, choices=DeclaracaoComponente.choices, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Informação nutricional"
        verbose_name_plural = "Informações nutricionais"

    def __str__(self):
        return f"Informação nutricional de {self.produto}"


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

class TipoCodigoBarrasProduto(models.TextChoices):
    UNIDADE = "UNIDADE", "Unidade"
    PACOTE = "PACOTE", "Pacote"
    FARDO = "FARDO", "Fardo"
    CAIXA = "CAIXA", "Caixa"
    OUTRO = "OUTRO", "Outro"


class CodigoBarrasProduto(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="codigos_adicionais")
    codigo = models.CharField("Código de barras", max_length=80, unique=True)
    tipo = models.CharField(max_length=20, choices=TipoCodigoBarrasProduto.choices, default=TipoCodigoBarrasProduto.UNIDADE)
    fator_conversao = models.DecimalField(
        "Quantidade na unidade base",
        max_digits=12,
        decimal_places=3,
        default=1,
        validators=[MinValueValidator(0.001)],
    )
    permite_venda = models.BooleanField("Pode ser usado no PDV", default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["produto", "tipo", "codigo"]
        verbose_name = "Código de barras do produto"
        verbose_name_plural = "Códigos de barras dos produtos"

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or "").strip()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} - {self.produto} ({self.fator_conversao})"

class SetorBalanca(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="setores_balanca")
    codigo = models.PositiveSmallIntegerField("Código do setor", validators=[MinValueValidator(1), MaxValueValidator(999)])
    nome = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empresa__nome_fantasia", "codigo", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="setor_balanca_codigo_unico_empresa"),
            models.UniqueConstraint(fields=["empresa", "nome"], name="setor_balanca_nome_unico_empresa"),
        ]
        verbose_name = "Setor de balança"
        verbose_name_plural = "Setores de balança"

    def __str__(self):
        return f"{self.codigo:03d} - {self.nome} ({self.empresa.nome_fantasia})"


class ConfiguracaoBalancaProduto(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="produtos_balanca")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="configuracoes_balanca")
    setor = models.ForeignKey(SetorBalanca, on_delete=models.PROTECT, related_name="produtos_configurados")
    plu = models.PositiveIntegerField("PLU", validators=[MinValueValidator(1), MaxValueValidator(999999)])
    tara_kg = models.DecimalField(
        "Tara (kg)", max_digits=8, decimal_places=3, default=0, validators=[MinValueValidator(0)]
    )
    validade_dias = models.PositiveSmallIntegerField("Validade (dias)", default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["setor__empresa__nome_fantasia", "setor__codigo", "plu"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "plu"], name="produto_balanca_plu_unico_empresa"),
            models.UniqueConstraint(fields=["produto", "empresa"], name="produto_balanca_unico_empresa"),
        ]
        verbose_name = "Configuração de balança do produto"
        verbose_name_plural = "Configurações de balança dos produtos"

    def clean(self):
        super().clean()
        if self.setor_id and self.empresa_id and self.setor.empresa_id != self.empresa_id:
            raise ValidationError({"setor": "O setor de balança deve pertencer à mesma empresa da configuração."})
    def __str__(self):
        return f"PLU {self.plu} - {self.produto} / {self.setor.nome}"

class ProdutoFornecedor(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="fornecedores_vinculados")
    fornecedor = models.ForeignKey(
        "fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="produtos_vinculados"
    )
    codigo_no_fornecedor = models.CharField("Código no fornecedor", max_length=80, blank=True)
    ultimo_custo = models.DecimalField("Último custo cotado", max_digits=10, decimal_places=2, null=True, blank=True)
    principal = models.BooleanField("Fornecedor principal", default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-principal", "fornecedor__razao_social"]
        constraints = [
            models.UniqueConstraint(fields=["produto", "fornecedor"], name="produto_fornecedor_unico"),
        ]
        verbose_name = "Fornecedor do produto"
        verbose_name_plural = "Fornecedores do produto"

    def __str__(self):
        return f"{self.produto} - {self.fornecedor}"


class StatusVersaoPreco(models.TextChoices):
    AGENDADA = "AGENDADA", "Agendada"
    CANCELADA = "CANCELADA", "Cancelada"


class VersaoPrecoProduto(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="versoes_preco")
    versao = models.PositiveIntegerField()
    preco_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    preco_novo = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    vigencia_inicio = models.DateTimeField("Início da vigência")
    motivo = models.CharField(max_length=255)
    status = models.CharField(max_length=12, choices=StatusVersaoPreco.choices, default=StatusVersaoPreco.AGENDADA)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="versoes_preco_criadas"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="versoes_preco_canceladas",
        null=True, blank=True,
    )
    cancelado_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-vigencia_inicio", "-versao"]
        constraints = [
            models.UniqueConstraint(fields=["produto", "versao"], name="produto_versao_preco_unica"),
            models.CheckConstraint(condition=models.Q(preco_novo__gt=0), name="produto_versao_preco_positivo"),
        ]
        indexes = [models.Index(fields=["produto", "status", "vigencia_inicio"], name="produto_preco_vigente_idx")]
        verbose_name = "Versão de preço do produto"
        verbose_name_plural = "Versões de preço dos produtos"

    @property
    def esta_vigente(self):
        from django.utils import timezone
        return self.status == StatusVersaoPreco.AGENDADA and self.vigencia_inicio <= timezone.now()

    def __str__(self):
        return f"{self.produto} - versão {self.versao} - R$ {self.preco_novo}"

# Create your models here.
