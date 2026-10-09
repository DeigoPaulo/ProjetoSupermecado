from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password

from apps.core_money import quantizar_moeda
from apps.vendas.models import StatusPagamento, TipoDocumentoConsumidor
from apps.clientes.models import IndicadorInscricaoEstadual

from .documentos_destinatario import normalizar_documento_cliente


class CanalPedido(models.TextChoices):
    PDV = "PDV", "PDV"
    LOJA_ONLINE = "LOJA_ONLINE", "Loja online"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    TELEFONE = "TELEFONE", "Telefone"
    MARKETPLACE = "MARKETPLACE", "Marketplace parceiro"


class TipoEntrega(models.TextChoices):
    RETIRADA = "RETIRADA", "Retirada na loja"
    ENTREGA = "ENTREGA", "Entrega"


class StatusPedido(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_SEPARACAO = "EM_SEPARACAO", "Em separação"
    PRONTO = "PRONTO", "Pronto"
    SAIU_ENTREGA = "SAIU_ENTREGA", "Saiu para entrega"
    CONCLUIDO = "CONCLUIDO", "Concluído"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusPagamentoPedido(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    PAGO = "PAGO", "Pago"
    ESTORNADO = "ESTORNADO", "Estornado"


class OrigemRecebimentoPedido(models.TextChoices):
    CAIXA_PDV = "CAIXA_PDV", "Caixa PDV"
    ENTREGA = "ENTREGA", "Entrega"


class StatusAcertoEntrega(models.TextChoices):
    NAO_APLICA = "NAO_APLICA", "Não se aplica"
    PENDENTE = "PENDENTE", "Pendente"
    ACERTADO = "ACERTADO", "Acertado"


class FormaPagamentoPedido(models.TextChoices):
    PIX = "PIX", "PIX"
    CARTAO = "CARTAO", "Cartão"
    CARTAO_CREDITO_ENTREGA = "CARTAO_CREDITO_ENTREGA", "Cartão de crédito na entrega"
    CARTAO_DEBITO_ENTREGA = "CARTAO_DEBITO_ENTREGA", "Cartão de débito na entrega"
    DINHEIRO = "DINHEIRO", "Dinheiro"
    GATEWAY = "GATEWAY", "Gateway/marketplace"
    OUTRO = "OUTRO", "Outro"


class ProvedorIntegracaoMarketplace(models.TextChoices):
    PADRAO = "PADRAO", "Contrato padrão"
    IFOOD = "IFOOD", "iFood"
    RAPPI = "RAPPI", "Rappi"
    MERCADO_LIVRE = "MERCADO_LIVRE", "Mercado Livre"
    SITE_PROPRIO = "SITE_PROPRIO", "Site próprio"
    OUTRO = "OUTRO", "Outro parceiro"


class IntegracaoMarketplace(models.Model):
    nome = models.CharField(max_length=120)
    provedor = models.CharField(
        max_length=30,
        choices=ProvedorIntegracaoMarketplace.choices,
        default=ProvedorIntegracaoMarketplace.PADRAO,
    )
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="integracoes_marketplace")
    token_prefixo = models.CharField(max_length=12, db_index=True)
    token_hash = models.CharField(max_length=255)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="integracoes_marketplace")
    is_active = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    ultimo_uso_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nome"]

    def definir_token(self, token):
        self.token_prefixo = token[:12]
        self.token_hash = make_password(token)

    def token_valido(self, token):
        return bool(token and token.startswith(self.token_prefixo) and check_password(token, self.token_hash))

    def __str__(self):
        return f"{self.nome} - {self.filial}"


class PoliticaEntrega(models.Model):
    filial = models.OneToOneField("empresas.Filial", on_delete=models.PROTECT, related_name="politica_entrega")
    raio_maximo_km = models.DecimalField(max_digits=7, decimal_places=2)
    valor_minimo_pedido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frete_gratis_acima = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bairros_atendidos = models.TextField(blank=True, help_text="Separe bairros ou setores por vírgula.")
    bairros_bloqueados = models.TextField(blank=True, help_text="Separe bairros ou setores por vírgula.")
    horarios_entrega = models.TextField(blank=True)
    permite_retirada = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["filial__empresa__nome_fantasia", "filial__nome"]

    def clean(self):
        if self.raio_maximo_km <= 0:
            raise ValidationError({"raio_maximo_km": "O raio máximo deve ser maior que zero."})
        if self.valor_minimo_pedido < 0 or (self.frete_gratis_acima is not None and self.frete_gratis_acima < 0):
            raise ValidationError("Os valores da política não podem ser negativos.")

    def __str__(self):
        return f"Política de entrega - {self.filial}"


class FaixaTaxaEntrega(models.Model):
    politica = models.ForeignKey(PoliticaEntrega, on_delete=models.CASCADE, related_name="faixas")
    distancia_inicial_km = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    distancia_final_km = models.DecimalField(max_digits=7, decimal_places=2)
    taxa = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["distancia_inicial_km"]

    def clean(self):
        if self.distancia_inicial_km < 0 or self.distancia_final_km <= self.distancia_inicial_km:
            raise ValidationError("A distância final deve ser maior que a inicial.")
        if self.taxa < 0:
            raise ValidationError({"taxa": "A taxa não pode ser negativa."})

    def __str__(self):
        return f"{self.distancia_inicial_km} a {self.distancia_final_km} km - R$ {self.taxa}"


class PedidoOnline(models.Model):
    integracao = models.ForeignKey(IntegracaoMarketplace, on_delete=models.PROTECT, null=True, blank=True, related_name="pedidos")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="pedidos_online")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, null=True, blank=True, related_name="pedidos_online")
    nome_cliente = models.CharField(max_length=150)
    documento_cliente_tipo = models.CharField(max_length=20, choices=TipoDocumentoConsumidor.choices, default=TipoDocumentoConsumidor.NAO_IDENTIFICADO)
    documento_cliente = models.CharField(max_length=32, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    canal = models.CharField(max_length=20, choices=CanalPedido.choices, default=CanalPedido.LOJA_ONLINE)
    tipo_entrega = models.CharField(max_length=20, choices=TipoEntrega.choices, default=TipoEntrega.RETIRADA)
    endereco_entrega = models.TextField(blank=True)
    destinatario_indicador_ie = models.CharField(
        "Indicador de IE",
        max_length=1,
        choices=IndicadorInscricaoEstadual.choices,
        blank=True,
        default="",
    )
    destinatario_inscricao_estadual = models.CharField("Inscrição estadual", max_length=20, blank=True)
    destinatario_logradouro = models.CharField("Logradouro fiscal", max_length=120, blank=True)
    destinatario_numero = models.CharField("Número fiscal", max_length=60, blank=True)
    destinatario_complemento = models.CharField("Complemento fiscal", max_length=60, blank=True)
    destinatario_bairro = models.CharField("Bairro fiscal", max_length=60, blank=True)
    destinatario_codigo_municipio_ibge = models.CharField("Código IBGE do município", max_length=7, blank=True)
    destinatario_municipio = models.CharField("Município fiscal", max_length=60, blank=True)
    destinatario_uf = models.CharField("UF fiscal", max_length=2, blank=True)
    destinatario_cep = models.CharField("CEP fiscal", max_length=9, blank=True)
    bairro_entrega = models.CharField(max_length=120, blank=True)
    distancia_entrega_km = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    regra_entrega_aplicada = models.CharField(max_length=180, blank=True)
    referencia_externa = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=StatusPedido.choices, default=StatusPedido.RASCUNHO)
    estoque_reservado = models.BooleanField(default=False)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxa_entrega = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status_pagamento = models.CharField(max_length=20, choices=StatusPagamentoPedido.choices, default=StatusPagamentoPedido.PENDENTE)
    forma_pagamento = models.CharField(max_length=40, choices=FormaPagamentoPedido.choices, blank=True)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    referencia_pagamento = models.CharField(max_length=120, blank=True)
    pago_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos_online_criados")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=80, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(fields=["integracao", "referencia_externa"], condition=models.Q(integracao__isnull=False), name="pedido_referencia_unica_por_integracao"),
        ]

    def clean(self):
        if self.integracao_id and self.filial_id and self.integracao.filial_id != self.filial_id:
            raise ValidationError({"integracao": "Integração informada pertence a outra filial."})
        if self.cliente_id and self.filial_id and self.cliente.empresa_id != self.filial.empresa_id:
            raise ValidationError({"cliente": "Cliente informado pertence a outra empresa."})
        if self.tipo_entrega == TipoEntrega.ENTREGA and not self.endereco_entrega.strip():
            raise ValidationError({"endereco_entrega": "Informe o endereço para pedidos com entrega."})
        if (
            self.destinatario_indicador_ie == IndicadorInscricaoEstadual.CONTRIBUINTE
            and not self.destinatario_inscricao_estadual.strip()
        ):
            raise ValidationError(
                {"destinatario_inscricao_estadual": "Informe a inscrição estadual do contribuinte."}
            )
        if (
            self.destinatario_indicador_ie != IndicadorInscricaoEstadual.CONTRIBUINTE
            and self.destinatario_inscricao_estadual.strip()
        ):
            raise ValidationError(
                {"destinatario_inscricao_estadual": "A IE só deve ser informada para contribuinte."}
            )
        if (
            self.destinatario_codigo_municipio_ibge
            and not self.destinatario_codigo_municipio_ibge.isdigit()
        ) or (
            self.destinatario_codigo_municipio_ibge
            and len(self.destinatario_codigo_municipio_ibge) != 7
        ):
            raise ValidationError(
                {"destinatario_codigo_municipio_ibge": "Informe o código IBGE com 7 dígitos."}
            )
        if self.destinatario_uf and len(self.destinatario_uf.strip()) != 2:
            raise ValidationError({"destinatario_uf": "Informe a UF com 2 letras."})
        cep = "".join(caractere for caractere in self.destinatario_cep if caractere.isdigit())
        if self.destinatario_cep and len(cep) != 8:
            raise ValidationError({"destinatario_cep": "Informe o CEP com 8 dígitos."})
        if self.desconto < 0 or self.taxa_entrega < 0:
            raise ValidationError("Desconto e taxa de entrega não podem ser negativos.")
        if self.documento_cliente:
            normalizar_documento_cliente(
                self.documento_cliente_tipo,
                self.documento_cliente,
                inferir=(
                    self.documento_cliente_tipo
                    == TipoDocumentoConsumidor.NAO_IDENTIFICADO
                ),
            )

    def preencher_destinatario_do_cliente(self):
        if not self.cliente_id:
            return
        cliente = self.cliente
        campos = {
            "nome_cliente": "nome",
            "documento_cliente": "cpf_cnpj",
            "destinatario_indicador_ie": "indicador_ie",
            "destinatario_inscricao_estadual": "inscricao_estadual",
            "destinatario_logradouro": "logradouro",
            "destinatario_numero": "numero",
            "destinatario_complemento": "complemento",
            "destinatario_bairro": "bairro",
            "destinatario_codigo_municipio_ibge": "codigo_municipio_ibge",
            "destinatario_municipio": "municipio",
            "destinatario_uf": "uf",
            "destinatario_cep": "cep",
        }
        for destino, origem in campos.items():
            if not str(getattr(self, destino, "") or "").strip():
                setattr(self, destino, getattr(cliente, origem, "") or "")
        tipo, documento = normalizar_documento_cliente(
            self.documento_cliente_tipo,
            self.documento_cliente,
            inferir=(
                self.documento_cliente_tipo
                == TipoDocumentoConsumidor.NAO_IDENTIFICADO
            ),
        )
        self.documento_cliente_tipo = tipo
        self.documento_cliente = documento

    def recalcular(self):
        self.subtotal = sum((item.total for item in self.itens.all()), Decimal("0.00"))
        self.total = max(self.subtotal + self.taxa_entrega - self.desconto, Decimal("0.00"))
        self.save(update_fields=["subtotal", "total", "atualizado_em"])

    def __str__(self):
        return f"Pedido {self.pk} - {self.nome_cliente}"


class ItemPedidoOnline(models.Model):
    pedido = models.ForeignKey(PedidoOnline, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_pedido_online")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_separada = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    custo_unitario_no_momento = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)

    class Meta:
        unique_together = ["pedido", "produto"]
        ordering = ["id"]

    def clean(self):
        if self.quantidade <= 0:
            raise ValidationError({"quantidade": "A quantidade deve ser maior que zero."})
        if self.preco_unitario < 0:
            raise ValidationError({"preco_unitario": "O preço não pode ser negativo."})
        if self.quantidade_separada < 0 or self.quantidade_separada > self.quantidade:
            raise ValidationError({"quantidade_separada": "A quantidade separada deve ficar entre zero e a quantidade pedida."})

    def save(self, *args, **kwargs):
        self.total = quantizar_moeda(self.quantidade * self.preco_unitario)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.produto} x {self.quantidade}"


class DevolucaoPedido(models.Model):
    pedido = models.OneToOneField(PedidoOnline, on_delete=models.PROTECT, related_name="devolucao")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    motivo = models.CharField(max_length=255)
    valor_devolvido = models.DecimalField(max_digits=12, decimal_places=2)
    produto_apto_venda = models.BooleanField(default=False)
    devolvido_em = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Devolução do pedido #{self.pedido_id}"


class PagamentoPedido(models.Model):
    pedido = models.ForeignKey(PedidoOnline, on_delete=models.PROTECT, related_name="pagamentos")
    forma_pagamento = models.ForeignKey("vendas.FormaPagamento", on_delete=models.PROTECT)
    confirmacao_integracao = models.OneToOneField(
        "vendas.ConfirmacaoPagamentoIntegrado", on_delete=models.PROTECT,
        null=True, blank=True, related_name="pagamento_pedido",
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    valor_informado = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, choices=StatusPagamento.choices, default=StatusPagamento.CONFIRMADO)
    origem_recebimento = models.CharField(max_length=20, choices=OrigemRecebimentoPedido.choices)
    caixa_recebimento = models.ForeignKey(
        "pdv.Caixa", on_delete=models.PROTECT, null=True, blank=True, related_name="pagamentos_pedido"
    )
    usuario_recebimento = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagamentos_pedido_recebidos"
    )
    recebido_em = models.DateTimeField(auto_now_add=True)
    transacao_externa_id = models.CharField(max_length=120, blank=True)
    nsu = models.CharField(max_length=60, blank=True)
    codigo_autorizacao = models.CharField(max_length=128, blank=True)
    tipo_integracao = models.CharField(max_length=1, blank=True)
    cnpj_instituicao_pagamento = models.CharField(max_length=14, blank=True)
    bandeira_cartao = models.CharField(max_length=2, blank=True)
    cnpj_beneficiario_pagamento = models.CharField(max_length=14, blank=True)
    identificador_terminal_pagamento = models.CharField(max_length=40, blank=True)
    mensagem_processadora = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=80, unique=True, default=uuid.uuid4)
    status_acerto = models.CharField(
        max_length=12, choices=StatusAcertoEntrega.choices, default=StatusAcertoEntrega.NAO_APLICA
    )
    caixa_acerto = models.ForeignKey(
        "pdv.Caixa", on_delete=models.PROTECT, null=True, blank=True, related_name="acertos_entrega"
    )
    usuario_acerto = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="acertos_entrega_registrados",
    )
    acertado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["recebido_em", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(valor__gt=0), name="pedido_pagamento_valor_positivo"),
            models.CheckConstraint(
                condition=models.Q(valor_informado__gte=models.F("valor")),
                name="pedido_pagamento_informado_gte_aplicado",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(origem_recebimento=OrigemRecebimentoPedido.CAIXA_PDV, caixa_recebimento__isnull=False)
                    | models.Q(origem_recebimento=OrigemRecebimentoPedido.ENTREGA, caixa_recebimento__isnull=True)
                ),
                name="pedido_pagamento_caixa_por_origem",
            ),
        ]

    def clean(self):
        tipo = (self.forma_pagamento.tipo or "").upper() if self.forma_pagamento_id else ""
        if self.origem_recebimento == OrigemRecebimentoPedido.CAIXA_PDV:
            if not self.caixa_recebimento_id or self.status_acerto != StatusAcertoEntrega.NAO_APLICA:
                raise ValidationError("Pagamento no PDV exige caixa e não pode ter acerto de entrega.")
        elif self.origem_recebimento == OrigemRecebimentoPedido.ENTREGA:
            if self.caixa_recebimento_id:
                raise ValidationError("Pagamento na entrega não pertence a caixa PDV.")
            if tipo == "DINHEIRO" and self.status_acerto not in {
                StatusAcertoEntrega.PENDENTE, StatusAcertoEntrega.ACERTADO
            }:
                raise ValidationError("Dinheiro recebido na entrega exige acerto.")
            if tipo != "DINHEIRO" and self.status_acerto != StatusAcertoEntrega.NAO_APLICA:
                raise ValidationError("Pagamento eletrônico na entrega não possui acerto de dinheiro.")
        if self.caixa_recebimento_id and self.caixa_recebimento.filial_id != self.pedido.filial_id:
            raise ValidationError({"caixa_recebimento": "O caixa pertence a outra filial."})
        if self.caixa_acerto_id and self.caixa_acerto.filial_id != self.pedido.filial_id:
            raise ValidationError({"caixa_acerto": "O caixa do acerto pertence a outra filial."})
        if self.status_acerto == StatusAcertoEntrega.ACERTADO:
            if not all((self.caixa_acerto_id, self.usuario_acerto_id, self.acertado_em)):
                raise ValidationError("Acerto exige caixa, usuário e data.")
        elif any((self.caixa_acerto_id, self.usuario_acerto_id, self.acertado_em)):
            raise ValidationError("Dados de acerto só podem existir após a prestação de contas.")
        if self.status_acerto == StatusAcertoEntrega.PENDENTE and (
            self.origem_recebimento != OrigemRecebimentoPedido.ENTREGA
            or self.forma_pagamento.tipo != "DINHEIRO"
        ):
            raise ValidationError("Somente dinheiro recebido na entrega pode ter acerto pendente.")
