from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class TipoMovimentacaoEstoque(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saida"
    AJUSTE = "AJUSTE", "Ajuste"
    VENDA = "VENDA", "Venda"
    DEVOLUCAO = "DEVOLUCAO", "Devolucao"
    PERDA = "PERDA", "Perda"
    RESERVA = "RESERVA", "Reserva"
    LIBERACAO_RESERVA = "LIBERACAO_RESERVA", "Liberacao de reserva"
    DESMEMBRAMENTO = "DESMEMBRAMENTO", "Desmembramento"


class Estoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="estoques")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="estoques")
    quantidade_atual = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_reservada = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["produto", "filial"]
        ordering = ["produto__nome", "filial__nome"]

    @property
    def quantidade_disponivel(self):
        return self.quantidade_atual - self.quantidade_reservada

    def clean(self):
        if self.quantidade_atual < 0:
            raise ValidationError("Quantidade atual nao pode ser negativa.")
        if self.quantidade_reservada < 0:
            raise ValidationError("Quantidade reservada nao pode ser negativa.")
        if self.quantidade_reservada > self.quantidade_atual:
            raise ValidationError("Quantidade reservada nao pode superar o estoque fisico.")

    def __str__(self):
        return f"{self.produto} / {self.filial}: {self.quantidade_disponivel}"


class MovimentacaoEstoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="movimentacoes")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="movimentacoes_estoque")
    tipo = models.CharField(max_length=30, choices=TipoMovimentacaoEstoque.choices)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=255, blank=True)
    referencia = models.CharField(max_length=120, blank=True)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    custo_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"{self.tipo} {self.quantidade} - {self.produto}"


class LoteEstoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="lotes_estoque")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="lotes_estoque")
    codigo = models.CharField(max_length=60)
    fabricacao = models.DateField(null=True, blank=True)
    validade = models.DateField(null=True, blank=True)
    quantidade_inicial = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_atual = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    origem_referencia = models.CharField(max_length=120, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [models.F("validade").asc(nulls_last=True), "criado_em", "id"]
        indexes = [
            models.Index(fields=["produto", "filial", "codigo"], name="est_lote_prod_fil_cod_idx"),
            models.Index(fields=["validade", "quantidade_atual"], name="est_lote_val_saldo_idx"),
        ]

    def clean(self):
        if not self.codigo.strip():
            raise ValidationError("Informe o codigo do lote.")
        if self.quantidade_inicial <= 0:
            raise ValidationError("Quantidade inicial do lote deve ser maior que zero.")
        if self.quantidade_atual < 0:
            raise ValidationError("Quantidade atual do lote nao pode ser negativa.")
        if self.quantidade_atual > self.quantidade_inicial:
            raise ValidationError("Quantidade atual nao pode superar a quantidade inicial do lote.")
        if self.fabricacao and self.validade and self.fabricacao > self.validade:
            raise ValidationError("A fabricacao do lote nao pode ser posterior a validade.")

    def __str__(self):
        return f"{self.produto} - lote {self.codigo}"

    @property
    def dias_para_vencer(self):
        if not self.validade:
            return None
        return (self.validade - timezone.localdate()).days

    @property
    def situacao_validade(self):
        dias = self.dias_para_vencer
        if dias is None:
            return "SEM_VALIDADE"
        if dias < 0:
            return "VENCIDO"
        if dias <= 30:
            return "PROXIMO"
        return "VALIDO"


class MovimentacaoLoteEstoque(models.Model):
    movimentacao = models.ForeignKey(MovimentacaoEstoque, on_delete=models.CASCADE, related_name="alocacoes_lote")
    lote = models.ForeignKey(LoteEstoque, on_delete=models.PROTECT, related_name="movimentacoes_lote")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.movimentacao} / {self.lote.codigo}: {self.quantidade}"


class StatusInventario(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    APLICADO = "APLICADO", "Aplicado"
    CANCELADO = "CANCELADO", "Cancelado"


class InventarioEstoque(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="inventarios")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="inventarios")
    descricao = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=StatusInventario.choices, default=StatusInventario.ABERTO)
    criado_em = models.DateTimeField(auto_now_add=True)
    aplicado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Inventario {self.id} - {self.filial}"


class ItemInventarioEstoque(models.Model):
    inventario = models.ForeignKey(InventarioEstoque, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_inventario")
    quantidade_sistema = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_contada = models.DecimalField(max_digits=12, decimal_places=3)
    diferenca = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    observacao = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ["inventario", "produto"]
        ordering = ["produto__nome"]

    def __str__(self):
        return f"{self.produto}: {self.diferenca}"


class TipoPerdaEstoque(models.TextChoices):
    VENCIMENTO = "VENCIMENTO", "Vencimento"
    AVARIA = "AVARIA", "Avaria"
    QUEBRA = "QUEBRA", "Quebra"
    EXTRAVIO_FURTO = "EXTRAVIO_FURTO", "Extravio/furto"
    CONSUMO_INTERNO = "CONSUMO_INTERNO", "Consumo interno"
    DEVOLUCAO_NAO_REAPROVEITAVEL = "DEVOLUCAO_NAO_REAPROVEITAVEL", "Devolucao nao reaproveitavel"
    OUTROS = "OUTROS", "Outros"


class PerdaEstoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="perdas")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="perdas_estoque")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="perdas_estoque")
    desmembramento_item = models.ForeignKey(
        "estoque.ItemDesmembramentoProduto",
        on_delete=models.CASCADE,
        related_name="perdas_geradas",
        null=True,
        blank=True,
    )
    tipo = models.CharField(max_length=40, choices=TipoPerdaEstoque.choices)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=255)
    custo_unitario_no_momento = models.DecimalField(max_digits=10, decimal_places=2)
    preco_venda_no_momento = models.DecimalField(max_digits=10, decimal_places=2)
    valor_custo_estimado = models.DecimalField(max_digits=12, decimal_places=2)
    valor_venda_estimado = models.DecimalField(max_digits=12, decimal_places=2)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"{self.tipo} - {self.produto} ({self.quantidade})"


class TipoDesmembramentoProduto(models.TextChoices):
    SIMPLES = "SIMPLES", "Simples / unitizacao"
    CAIXA_FARDO = "CAIXA_FARDO", "Caixa / fardo"
    HORTIFRUTI = "HORTIFRUTI", "Hortifruti reembalado"
    ACOUGUE = "ACOUGUE", "Acougue por rendimento"
    PRODUCAO = "PRODUCAO", "Producao interna"
    KIT = "KIT", "Kit / composicao"


class StatusDesmembramentoProduto(models.TextChoices):
    CONFIRMADO = "CONFIRMADO", "Confirmado"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusProducaoComposicao(models.TextChoices):
    CONFIRMADO = "CONFIRMADO", "Confirmado"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusOrdemProducaoComposicao(models.TextChoices):
    PLANEJADA = "PLANEJADA", "Planejada"
    PRODUZIDA = "PRODUZIDA", "Produzida"
    CANCELADA = "CANCELADA", "Cancelada"


class PrioridadeOrdemProducaoComposicao(models.TextChoices):
    BAIXA = "BAIXA", "Baixa"
    NORMAL = "NORMAL", "Normal"
    ALTA = "ALTA", "Alta"
    URGENTE = "URGENTE", "Urgente"


class EtapaOrdemProducaoComposicao(models.TextChoices):
    AGUARDANDO = "AGUARDANDO", "Aguardando"
    SEPARACAO = "SEPARACAO", "Separação"
    PRODUCAO = "PRODUCAO", "Produção"
    CONFERENCIA = "CONFERENCIA", "Conferência"


class MetodoCustoDesmembramento(models.TextChoices):
    QUANTIDADE = "QUANTIDADE", "Proporcional por quantidade"
    PESO = "PESO", "Proporcional por peso"
    MANUAL = "MANUAL", "Custo manual autorizado"


class TipoSaidaDesmembramento(models.TextChoices):
    VENDAVEL = "VENDAVEL", "Produto vendavel"
    PERDA = "PERDA", "Perda / descarte"
    SUBPRODUTO = "SUBPRODUTO", "Subproduto"


class ReceitaDesmembramento(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="receitas_desmembramento")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="receitas_desmembramento", null=True, blank=True)
    produto_origem = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="receitas_desmembramento_origem")
    produto_destino = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="receitas_desmembramento_destino")
    quantidade_origem = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    quantidade_destino = models.DecimalField(max_digits=12, decimal_places=3)
    tipo = models.CharField(max_length=30, choices=TipoDesmembramentoProduto.choices, default=TipoDesmembramentoProduto.SIMPLES)
    tipo_saida = models.CharField(max_length=20, choices=TipoSaidaDesmembramento.choices, default=TipoSaidaDesmembramento.VENDAVEL)
    observacao = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["produto_origem__nome", "produto_destino__nome"]

    def clean(self):
        if self.filial_id and self.empresa_id and self.filial.empresa_id != self.empresa_id:
            raise ValidationError("A filial deve pertencer a empresa da receita.")
        if self.produto_origem_id and self.produto_destino_id and self.produto_origem_id == self.produto_destino_id:
            raise ValidationError("Produto origem e produto destino devem ser diferentes.")
        if self.quantidade_origem <= 0 or self.quantidade_destino <= 0:
            raise ValidationError("Quantidades da receita devem ser maiores que zero.")

    def __str__(self):
        return f"{self.quantidade_origem} {self.produto_origem} -> {self.quantidade_destino} {self.produto_destino}"


class ComposicaoProduto(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="composicoes_produto")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="composicoes_produto", null=True, blank=True)
    produto_final = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="composicoes_final")
    quantidade_final = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    tipo = models.CharField(max_length=30, choices=TipoDesmembramentoProduto.choices, default=TipoDesmembramentoProduto.KIT)
    observacao = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["produto_final__nome"]

    def clean(self):
        if self.quantidade_final <= 0:
            raise ValidationError("Quantidade final da composicao deve ser maior que zero.")
        if self.filial_id and self.empresa_id and self.filial.empresa_id != self.empresa_id:
            raise ValidationError("A filial deve pertencer à empresa da composição.")

    def __str__(self):
        return f"{self.produto_final} ({self.quantidade_final})"


class ItemComposicaoProduto(models.Model):
    composicao = models.ForeignKey(ComposicaoProduto, on_delete=models.CASCADE, related_name="itens")
    produto_componente = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="composicoes_componente")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        unique_together = ["composicao", "produto_componente"]
        ordering = ["produto_componente__nome"]

    def clean(self):
        if self.quantidade <= 0:
            raise ValidationError("Quantidade do componente deve ser maior que zero.")
        if self.composicao_id and self.produto_componente_id == self.composicao.produto_final_id:
            raise ValidationError("Produto final nao pode ser componente da propria composicao.")

    def __str__(self):
        return f"{self.produto_componente}: {self.quantidade}"


class ProducaoComposicaoProduto(models.Model):
    composicao = models.ForeignKey(ComposicaoProduto, on_delete=models.PROTECT, related_name="producoes")
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="producoes_composicao")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="producoes_composicao")
    produto_final = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="producoes_composicao")
    quantidade_final = models.DecimalField(max_digits=12, decimal_places=3)
    custo_total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=StatusProducaoComposicao.choices, default=StatusProducaoComposicao.CONFIRMADO)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="producoes_composicao")
    motivo = models.CharField(max_length=255)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def clean(self):
        if self.filial_id and self.empresa_id and self.filial.empresa_id != self.empresa_id:
            raise ValidationError("A filial deve pertencer à empresa da produção.")
        if self.composicao_id and self.empresa_id and self.composicao.empresa_id != self.empresa_id:
            raise ValidationError("A composição deve pertencer à empresa da produção.")
        if self.composicao_id and self.composicao.filial_id and self.composicao.filial_id != self.filial_id:
            raise ValidationError("A produção deve usar a filial da composição.")

    def __str__(self):
        return f"Producao {self.id} - {self.produto_final}"


class ItemProducaoComposicaoProduto(models.Model):
    producao = models.ForeignKey(ProducaoComposicaoProduto, on_delete=models.CASCADE, related_name="itens")
    produto_componente = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_producao_composicao")
    quantidade_consumida = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    custo_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["produto_componente__nome"]

    def __str__(self):
        return f"{self.produto_componente}: {self.quantidade_consumida}"


class OrdemProducaoComposicao(models.Model):
    composicao = models.ForeignKey(ComposicaoProduto, on_delete=models.PROTECT, related_name="ordens_producao")
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="ordens_producao_composicao")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="ordens_producao_composicao")
    produto_final = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="ordens_producao_composicao")
    quantidade_planejada = models.DecimalField(max_digits=12, decimal_places=3)
    data_programada = models.DateField()
    prioridade = models.CharField(
        max_length=20,
        choices=PrioridadeOrdemProducaoComposicao.choices,
        default=PrioridadeOrdemProducaoComposicao.NORMAL,
    )
    setor_responsavel = models.CharField(max_length=80, blank=True)
    etapa_operacional = models.CharField(
        max_length=20,
        choices=EtapaOrdemProducaoComposicao.choices,
        default=EtapaOrdemProducaoComposicao.AGUARDANDO,
    )
    status = models.CharField(max_length=20, choices=StatusOrdemProducaoComposicao.choices, default=StatusOrdemProducaoComposicao.PLANEJADA)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ordens_producao_composicao")
    responsavel_operacional = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ordens_producao_operacionais",
        null=True,
        blank=True,
    )
    motivo = models.CharField(max_length=255)
    observacao = models.TextField(blank=True)
    producao_gerada = models.ForeignKey(
        ProducaoComposicaoProduto,
        on_delete=models.PROTECT,
        related_name="ordens_origem",
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["data_programada", "produto_final__nome"]

    def clean(self):
        if self.quantidade_planejada <= 0:
            raise ValidationError("Quantidade planejada deve ser maior que zero.")
        if self.filial_id and self.empresa_id and self.filial.empresa_id != self.empresa_id:
            raise ValidationError("A filial deve pertencer à empresa da ordem.")
        if self.composicao_id and self.empresa_id and self.composicao.empresa_id != self.empresa_id:
            raise ValidationError("A composição deve pertencer à empresa da ordem.")
        if self.composicao_id and self.composicao.filial_id and self.composicao.filial_id != self.filial_id:
            raise ValidationError("Ordem de produção deve usar a filial da composição.")
        if self.responsavel_operacional_id and self.empresa_id:
            perfil = getattr(self.responsavel_operacional, "perfil_supermercado", None)
            if perfil and perfil.is_active and perfil.filial_id and perfil.filial.empresa_id != self.empresa_id:
                raise ValidationError("O responsável operacional deve pertencer à empresa da ordem.")

    def __str__(self):
        return f"Ordem {self.id} - {self.produto_final}"


class HistoricoEtapaOrdemProducaoComposicao(models.Model):
    ordem = models.ForeignKey(OrdemProducaoComposicao, on_delete=models.CASCADE, related_name="historico_etapas")
    etapa_anterior = models.CharField(max_length=20, choices=EtapaOrdemProducaoComposicao.choices, blank=True)
    etapa_nova = models.CharField(max_length=20, choices=EtapaOrdemProducaoComposicao.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="historicos_etapa_ordem_producao")
    observacao = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return f"Ordem {self.ordem_id}: {self.etapa_anterior or '-'} -> {self.etapa_nova}"


class ConfiguracaoSLASetorProducao(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="slas_setor_producao")
    filial = models.ForeignKey(
        "empresas.Filial",
        on_delete=models.PROTECT,
        related_name="slas_setor_producao",
        null=True,
        blank=True,
    )
    setor = models.CharField(max_length=80)
    meta_minutos = models.PositiveIntegerField(default=240)
    observacao = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empresa__nome_fantasia", "filial__nome", "setor"]
        unique_together = ["empresa", "filial", "setor"]

    def clean(self):
        if self.filial_id and self.empresa_id and self.filial.empresa_id != self.empresa_id:
            raise ValidationError("A filial deve pertencer a empresa informada.")
        if not self.setor.strip():
            raise ValidationError("Setor e obrigatorio.")

    def __str__(self):
        filial = self.filial.nome if self.filial_id else "Todas as filiais"
        return f"{self.setor} - {filial}: {self.meta_minutos} min"


class AlertaSLAOrdemProducao(models.Model):
    ordem = models.ForeignKey(OrdemProducaoComposicao, on_delete=models.CASCADE, related_name="alertas_sla")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alertas_sla_producao",
    )
    papel = models.CharField(max_length=30)
    mensagem = models.CharField(max_length=255)
    criado_em = models.DateTimeField(auto_now_add=True)
    visualizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        unique_together = ["ordem", "usuario", "papel"]

    def __str__(self):
        return f"SLA ordem {self.ordem_id} para {self.usuario}"


class DesmembramentoProduto(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="desmembramentos_produto")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="desmembramentos_produto")
    produto_origem = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="desmembramentos_origem")
    quantidade_origem = models.DecimalField(max_digits=12, decimal_places=3)
    custo_total_origem = models.DecimalField(max_digits=12, decimal_places=2)
    tipo = models.CharField(max_length=30, choices=TipoDesmembramentoProduto.choices, default=TipoDesmembramentoProduto.SIMPLES)
    metodo_custo = models.CharField(max_length=20, choices=MetodoCustoDesmembramento.choices, default=MetodoCustoDesmembramento.QUANTIDADE)
    status = models.CharField(max_length=20, choices=StatusDesmembramentoProduto.choices, default=StatusDesmembramentoProduto.CONFIRMADO)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="desmembramentos_produto")
    motivo = models.CharField(max_length=255)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Desmembramento {self.id} - {self.produto_origem}"


class ItemDesmembramentoProduto(models.Model):
    desmembramento = models.ForeignKey(DesmembramentoProduto, on_delete=models.CASCADE, related_name="itens")
    produto_destino = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="desmembramentos_destino")
    quantidade_gerada = models.DecimalField(max_digits=12, decimal_places=3)
    unidade = models.CharField(max_length=3)
    custo_unitario_calculado = models.DecimalField(max_digits=10, decimal_places=2)
    custo_total = models.DecimalField(max_digits=12, decimal_places=2)
    percentual_rendimento = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    percentual_rendimento_esperado = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    lote = models.CharField(max_length=60, blank=True)
    validade = models.DateField(null=True, blank=True)
    tipo_saida = models.CharField(max_length=20, choices=TipoSaidaDesmembramento.choices, default=TipoSaidaDesmembramento.VENDAVEL)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.produto_destino} ({self.quantidade_gerada})"

    @property
    def rendimento_abaixo_esperado(self):
        if self.percentual_rendimento_esperado is None:
            return False
        return self.percentual_rendimento < self.percentual_rendimento_esperado

    @property
    def diferenca_rendimento(self):
        if self.percentual_rendimento_esperado is None:
            return None
        return self.percentual_rendimento - self.percentual_rendimento_esperado


def consumir_lotes_movimentacao(
    *,
    movimentacao,
    quantidade,
    codigo_lote="",
    lote_id=None,
    exigir_lote=False,
):
    restante = quantidade
    codigo_lote = (codigo_lote or "").strip()
    lotes = LoteEstoque.objects.select_for_update().filter(
        produto=movimentacao.produto,
        filial=movimentacao.filial,
        quantidade_atual__gt=0,
    )
    if codigo_lote:
        lotes = lotes.filter(codigo=codigo_lote)
    if lote_id:
        lotes = lotes.filter(pk=lote_id)
    lotes = lotes.order_by(models.F("validade").asc(nulls_last=True), "criado_em", "id")
    consumido = 0
    for lote in lotes:
        quantidade_lote = min(lote.quantidade_atual, restante)
        if quantidade_lote <= 0:
            continue
        lote.quantidade_atual -= quantidade_lote
        lote.save(update_fields=["quantidade_atual", "atualizado_em"])
        MovimentacaoLoteEstoque.objects.create(
            movimentacao=movimentacao,
            lote=lote,
            quantidade=quantidade_lote,
            custo_unitario=lote.custo_unitario,
        )
        restante -= quantidade_lote
        consumido += quantidade_lote
        if restante <= 0:
            break
    if (codigo_lote or exigir_lote) and restante > 0:
        identificacao = f" {codigo_lote}" if codigo_lote else ""
        raise ValidationError(f"Saldo insuficiente no lote{identificacao}.")
    return consumido


def criar_lote_movimentacao(
    *,
    movimentacao,
    codigo_lote,
    quantidade,
    custo_unitario,
    fabricacao=None,
    validade=None,
):
    codigo_lote = (codigo_lote or "").strip()
    if not codigo_lote:
        return None
    if custo_unitario is None:
        raise ValidationError("Informe o custo unitario para uma entrada com lote.")
    custo_unitario = Decimal(custo_unitario).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    lote = LoteEstoque(
        produto=movimentacao.produto,
        filial=movimentacao.filial,
        codigo=codigo_lote,
        fabricacao=fabricacao,
        validade=validade,
        quantidade_inicial=quantidade,
        quantidade_atual=quantidade,
        custo_unitario=custo_unitario,
        origem_referencia=movimentacao.referencia,
    )
    lote.full_clean()
    lote.save()
    MovimentacaoLoteEstoque.objects.create(
        movimentacao=movimentacao,
        lote=lote,
        quantidade=quantidade,
        custo_unitario=custo_unitario,
    )
    return lote


def restaurar_lotes_movimentacao(*, movimentacao_origem, movimentacao_reversao):
    restaurado = 0
    for alocacao in movimentacao_origem.alocacoes_lote.select_related("lote").all():
        lote = LoteEstoque.objects.select_for_update().get(pk=alocacao.lote_id)
        lote.quantidade_atual += alocacao.quantidade
        lote.full_clean()
        lote.save(update_fields=["quantidade_atual", "atualizado_em"])
        MovimentacaoLoteEstoque.objects.create(
            movimentacao=movimentacao_reversao,
            lote=lote,
            quantidade=alocacao.quantidade,
            custo_unitario=alocacao.custo_unitario,
        )
        restaurado += alocacao.quantidade
    return restaurado


def movimentar_estoque(
    *,
    produto,
    filial,
    tipo,
    quantidade,
    usuario=None,
    motivo="",
    referencia="",
    custo_unitario=None,
    codigo_lote="",
    fabricacao=None,
    validade=None,
):
    with transaction.atomic():
        if quantidade <= 0:
            raise ValidationError("Quantidade deve ser maior que zero.")
        estoque, _ = Estoque.objects.select_for_update().get_or_create(produto=produto, filial=filial)

        if tipo in [TipoMovimentacaoEstoque.SAIDA, TipoMovimentacaoEstoque.VENDA, TipoMovimentacaoEstoque.PERDA]:
            if estoque.quantidade_disponivel < quantidade:
                raise ValidationError("Estoque insuficiente.")
            estoque.quantidade_atual -= quantidade
        elif tipo == TipoMovimentacaoEstoque.RESERVA:
            if estoque.quantidade_disponivel < quantidade:
                raise ValidationError("Estoque insuficiente para reserva.")
            estoque.quantidade_reservada += quantidade
        elif tipo == TipoMovimentacaoEstoque.LIBERACAO_RESERVA:
            if estoque.quantidade_reservada < quantidade:
                raise ValidationError("Reserva insuficiente para liberacao.")
            estoque.quantidade_reservada -= quantidade
        else:
            estoque.quantidade_atual += quantidade

        estoque.full_clean()
        estoque.save()

        custo_total = None
        if custo_unitario is not None:
            custo_total = custo_unitario * quantidade

        movimentacao = MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=filial,
            tipo=tipo,
            quantidade=quantidade,
            motivo=motivo,
            referencia=referencia,
            custo_unitario=custo_unitario,
            custo_total=custo_total,
            usuario=usuario,
        )
        codigo_lote = (codigo_lote or "").strip()
        if produto.exige_lote and tipo == TipoMovimentacaoEstoque.ENTRADA and not codigo_lote:
            raise ValidationError("Este produto exige lote nas novas entradas.")
        if tipo in [TipoMovimentacaoEstoque.SAIDA, TipoMovimentacaoEstoque.VENDA, TipoMovimentacaoEstoque.PERDA]:
            consumir_lotes_movimentacao(
                movimentacao=movimentacao,
                quantidade=quantidade,
                codigo_lote=codigo_lote,
            )
        elif codigo_lote and tipo not in [TipoMovimentacaoEstoque.RESERVA, TipoMovimentacaoEstoque.LIBERACAO_RESERVA]:
            criar_lote_movimentacao(
                movimentacao=movimentacao,
                codigo_lote=codigo_lote,
                quantidade=quantidade,
                custo_unitario=custo_unitario,
                fabricacao=fabricacao,
                validade=validade,
            )
        return movimentacao

# Create your models here.
