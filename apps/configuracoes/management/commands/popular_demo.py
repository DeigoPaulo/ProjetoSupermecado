from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.clientes.models import Cliente
from apps.configuracoes.services import criar_configuracoes_padrao
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque, movimentar_estoque
from apps.fornecedores.models import Fornecedor
from apps.marketplace.models import (
    CanalPedido,
    FormaPagamentoPedido,
    ItemPedidoOnline,
    PedidoOnline,
    StatusPedido,
    StatusPagamentoPedido,
    TipoEntrega,
)
from apps.pdv.models import Caixa, StatusCaixa
from apps.produtos.models import Categoria, Marca, Produto, UnidadeMedida
from apps.vendas.models import FormaPagamento, FormaPagamentoFilial, ItemVenda, PagamentoVenda, StatusPagamento, StatusVenda, Venda


DEMO_CNPJ = "99.999.999/0001-99"
DEMO_PASSWORD = "Demo@2026"


class Command(BaseCommand):
    help = "Cria uma base demonstrativa isolada para testar o ERP sem dados reais."

    def add_arguments(self, parser):
        parser.add_argument(
            "--redefinir-senhas",
            action="store_true",
            help="Redefine a senha dos usuários demonstrativos para Demo@2026.",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Valida a carga dentro de uma transacao e desfaz todas as alteracoes ao final.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            resumo = self._popular(redefinir_senhas=options["redefinir_senhas"])
            if options["simular"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Simulacao concluida. Nenhum dado foi gravado."))
            else:
                self.stdout.write(self.style.SUCCESS("Base demonstrativa criada ou atualizada."))

        for chave, valor in resumo.items():
            self.stdout.write(f"- {chave}: {valor}")
        self.stdout.write("Usuários demo: demo.admin, demo.supervisor, demo.caixa e demo.estoque")
        self.stdout.write("Senha inicial dos novos usuários: Demo@2026")
        self.stdout.write("Use apenas para demonstração e testes; não utilize esses usuários em produção.")

    def _popular(self, *, redefinir_senhas):
        empresa, _ = Empresa.objects.update_or_create(
            cnpj=DEMO_CNPJ,
            defaults={
                "razao_social": "Deigo Varejo Demonstração Ltda",
                "nome_fantasia": "Deigo Varejo Demo",
                "telefone": "(62) 99999-0000",
                "email": "demo@deigovarejo.local",
                "endereco": "Rua de Demonstração, 100 - Goiânia/GO",
                "regime_tributario": "Simples Nacional",
                "is_active": True,
            },
        )
        matriz, _ = Filial.objects.update_or_create(
            empresa=empresa,
            nome="DEMO - Loja Matriz",
            defaults={
                "cnpj": DEMO_CNPJ,
                "telefone": "(62) 99999-0000",
                "endereco": "Rua de Demonstração, 100 - Setor Central",
                "municipio": "Goiânia",
                "uf": "GO",
                "codigo_municipio_ibge": "5208707",
                "is_active": True,
            },
        )
        filial, _ = Filial.objects.update_or_create(
            empresa=empresa,
            nome="DEMO - Loja Bairro",
            defaults={
                "cnpj": "99.999.999/0002-70",
                "telefone": "(62) 99999-0001",
                "endereco": "Avenida Demonstração, 200 - Setor Oeste",
                "municipio": "Goiânia",
                "uf": "GO",
                "codigo_municipio_ibge": "5208707",
                "is_active": True,
            },
        )
        usuarios = self._usuarios(matriz, redefinir_senhas)
        categorias = self._categorias()
        produtos = self._produtos(categorias)
        fornecedor, _ = Fornecedor.objects.update_or_create(
            empresa=empresa,
            razao_social="DEMO - Distribuidora Goias Ltda",
            defaults={
                "nome_fantasia": "DEMO Distribuidora",
                "cnpj": "99.999.999/0003-51",
                "telefone": "(62) 98888-0000",
                "email": "fornecedor.demo@deigovarejo.local",
                "endereco": "Rodovia de Demonstração, KM 10 - Goiânia/GO",
                "condicao_pagamento": "28 dias",
                "prazo_entrega_dias": 2,
                "is_active": True,
            },
        )
        cliente, _ = Cliente.objects.update_or_create(
            empresa=empresa,
            nome="DEMO - Ana Cliente",
            defaults={
                "cpf_cnpj": "000.000.000-00",
                "telefone": "(62) 99513-4774",
                "email": "ana.demo@deigovarejo.local",
                "endereco": "Rua 18, QD 81, LT 12 - Santos Dumont - Goiânia/GO",
                "is_active": True,
            },
        )
        formas = self._formas(matriz, filial)
        self._estoque(matriz, produtos, usuarios["estoque"])
        self._estoque(filial, produtos, usuarios["estoque"])
        caixa = self._caixa(matriz, usuarios["caixa"])
        self._vendas(matriz, caixa, produtos, formas, cliente, usuarios["caixa"])
        self._entrega(matriz, produtos, cliente, usuarios["caixa"])
        criar_configuracoes_padrao(empresa)
        return {
            "empresa": empresa.nome_fantasia,
            "filiais": 2,
            "usuarios": len(usuarios),
            "produtos": len(produtos),
            "fornecedor": fornecedor.nome_fantasia,
            "cliente": cliente.nome,
            "caixa_aberto": caixa.pk,
            "vendas_demo": Venda.objects.filter(filial=matriz, observacao_fiscal_consumidor__startswith="DEMO-").count(),
            "entregas_pendentes": PedidoOnline.objects.filter(filial=matriz, referencia_externa__startswith="DEMO-").exclude(status=StatusPedido.CONCLUIDO).count(),
        }

    def _usuarios(self, filial, redefinir_senhas):
        User = get_user_model()
        definicoes = {
            "admin": ("demo.admin", "Administrador", TipoPerfil.ADMINISTRADOR),
            "supervisor": ("demo.supervisor", "Supervisor", TipoPerfil.GERENTE),
            "caixa": ("demo.caixa", "Operador", TipoPerfil.OPERADOR_CAIXA),
            "estoque": ("demo.estoque", "Estoquista", TipoPerfil.ESTOQUISTA),
        }
        usuarios = {}
        for chave, (username, first_name, perfil) in definicoes.items():
            usuario, criado = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "email": f"{username}@deigovarejo.local", "is_active": True},
            )
            if criado or redefinir_senhas:
                usuario.set_password(DEMO_PASSWORD)
                usuario.save(update_fields=["password"])
            PerfilUsuario.objects.update_or_create(
                usuario=usuario,
                defaults={"filial": filial, "tipo": perfil, "telefone": "(62) 99999-0000", "is_active": True},
            )
            usuarios[chave] = usuario
        return usuarios

    def _categorias(self):
        dados = {
            "hortifruti": ("DEMO - Hortifruti", "Grupo"),
            "mercearia": ("DEMO - Mercearia", "Grupo"),
            "bebidas": ("DEMO - Bebidas", "Grupo"),
            "limpeza": ("DEMO - Limpeza", "Grupo"),
        }
        categorias = {}
        for chave, (nome, descricao) in dados.items():
            categorias[chave], _ = Categoria.all_objects.get_or_create(
                nome=nome,
                defaults={"descricao": descricao, "is_active": True},
            )
        return categorias

    def _produtos(self, categorias):
        marca, _ = Marca.all_objects.get_or_create(nome="DEMO - Marca Deigo Varejo", defaults={"is_active": True})
        dados = [
            ("7890000001001", "DEMO-1001", "Arroz Tipo 1 5kg", "mercearia", "UN", "18.90", "24.99", "45"),
            ("7890000001002", "DEMO-1002", "Leite Integral 1L", "mercearia", "UN", "3.95", "5.49", "80"),
            ("7890000001003", "DEMO-1003", "Coca-Cola Original 2L", "bebidas", "UN", "6.20", "9.49", "60"),
            ("7890000001004", "DEMO-1004", "Banana Prata", "hortifruti", "KG", "3.10", "6.99", "72.5"),
            ("7890000001005", "DEMO-1005", "Maçã Gala", "hortifruti", "KG", "4.20", "8.99", "55"),
            ("7890000001006", "DEMO-1006", "Detergente Neutro 500ml", "limpeza", "UN", "1.80", "3.49", "70"),
        ]
        produtos = {}
        for codigo, interno, nome, categoria, unidade, custo, venda, saldo in dados:
            produto, _ = Produto.all_objects.update_or_create(
                codigo_barras=codigo,
                defaults={
                    "codigo_interno": interno,
                    "nome": nome,
                    "descricao": "Produto fictício para demonstração e testes.",
                    "categoria": categorias[categoria],
                    "marca": marca,
                    "unidade": unidade,
                    "unidade_compra": unidade,
                    "produto_pesavel": unidade == UnidadeMedida.QUILO,
                    "preco_custo": Decimal(custo),
                    "preco_venda": Decimal(venda),
                    "estoque_minimo": Decimal("10.000"),
                    "vendido_no_pdv": True,
                    "vendido_no_marketplace": True,
                    "is_active": True,
                },
            )
            produtos[interno] = (produto, Decimal(saldo), Decimal(custo))
        return produtos

    def _formas(self, matriz, filial):
        definicoes = [
            ("DEMO - Dinheiro", "DINHEIRO", True),
            ("DEMO - PIX", "PIX", False),
            ("DEMO - Cartão de débito", "DEBITO", False),
            ("DEMO - Cartão de crédito", "CREDITO", False),
            ("DEMO - Vale refeicao", "VALE_REFEICAO", False),
        ]
        formas = {}
        for nome, tipo, troco in definicoes:
            forma, _ = FormaPagamento.objects.get_or_create(
                nome=nome,
                defaults={"tipo": tipo, "permite_troco": troco, "exige_autorizacao": tipo != "DINHEIRO", "ativo": True},
            )
            for filial_atual in (matriz, filial):
                FormaPagamentoFilial.objects.get_or_create(filial=filial_atual, forma_pagamento=forma, defaults={"ativo": True})
            formas[tipo] = forma
        return formas

    def _estoque(self, filial, produtos, usuario):
        for codigo, (produto, saldo, custo) in produtos.items():
            referencia = f"DEMO-ENTRADA-{codigo}"
            if not MovimentacaoEstoque.objects.filter(produto=produto, filial=filial, referencia=referencia).exists():
                movimentar_estoque(
                    produto=produto,
                    filial=filial,
                    tipo=TipoMovimentacaoEstoque.ENTRADA,
                    quantidade=saldo,
                    custo_unitario=custo,
                    usuario=usuario,
                    motivo="Carga inicial demonstrativa",
                    referencia=referencia,
                )

    def _caixa(self, filial, usuario):
        caixa = Caixa.objects.filter(filial=filial, usuario_abertura=usuario, status=StatusCaixa.ABERTO).first()
        if caixa:
            return caixa
        return Caixa.objects.create(filial=filial, usuario_abertura=usuario, valor_inicial=Decimal("200.00"), status=StatusCaixa.ABERTO)

    def _vendas(self, filial, caixa, produtos, formas, cliente, usuario):
        dados = [
            ("DEMO-VENDA-DINHEIRO", [("DEMO-1001", "1.000"), ("DEMO-1002", "2.000")], "DINHEIRO"),
            ("DEMO-VENDA-PIX", [("DEMO-1003", "1.000"), ("DEMO-1004", "1.250")], "PIX"),
            ("DEMO-VENDA-VALE", [("DEMO-1005", "1.000"), ("DEMO-1006", "2.000")], "VALE_REFEICAO"),
        ]
        for marcador, itens, tipo_pagamento in dados:
            if Venda.objects.filter(filial=filial, observacao_fiscal_consumidor=marcador).exists():
                continue
            venda = Venda.objects.create(filial=filial, caixa=caixa, cliente=cliente, usuario=usuario, status=StatusVenda.FINALIZADA, observacao_fiscal_consumidor=marcador)
            total = Decimal("0.00")
            for codigo, quantidade in itens:
                produto = produtos[codigo][0]
                qtd = Decimal(quantidade)
                item_total = (qtd * produto.preco_venda).quantize(Decimal("0.01"))
                ItemVenda.objects.create(venda=venda, produto=produto, quantidade=qtd, preco_unitario_venda=produto.preco_venda, total=item_total, custo_unitario_no_momento=produto.preco_custo)
                total += item_total
                referencia = f"{marcador}-{codigo}"
                if not MovimentacaoEstoque.objects.filter(produto=produto, filial=filial, referencia=referencia).exists():
                    movimentar_estoque(produto=produto, filial=filial, tipo=TipoMovimentacaoEstoque.VENDA, quantidade=qtd, usuario=usuario, motivo="Venda demonstrativa", referencia=referencia)
            venda.total_bruto = total
            venda.total_liquido = total
            venda.save(update_fields=["total_bruto", "total_liquido"])
            dados_tef = {}
            if tipo_pagamento != "DINHEIRO":
                dados_tef = {"transacao_externa_id": f"DEMO-{tipo_pagamento}-{venda.pk}", "nsu": f"DEMO{venda.pk:06d}", "codigo_autorizacao": f"AUT{venda.pk:06d}", "mensagem_processadora": "Pagamento demonstrativo"}
            PagamentoVenda.objects.create(venda=venda, forma_pagamento=formas[tipo_pagamento], valor=total, status=StatusPagamento.CONFIRMADO, **dados_tef)

    def _entrega(self, filial, produtos, cliente, usuario):
        pedido, _ = PedidoOnline.objects.get_or_create(
            filial=filial,
            referencia_externa="DEMO-ENTREGA-001",
            defaults={
                "cliente": cliente,
                "nome_cliente": cliente.nome,
                "telefone": cliente.telefone,
                "canal": CanalPedido.TELEFONE,
                "tipo_entrega": TipoEntrega.ENTREGA,
                "endereco_entrega": cliente.endereco,
                "bairro_entrega": "Santos Dumont",
                "distancia_entrega_km": Decimal("4.50"),
                "status": StatusPedido.PRONTO,
                "status_pagamento": StatusPagamentoPedido.PENDENTE,
                "taxa_entrega": Decimal("5.00"),
                "observacoes": "Pedido demonstrativo para testar separacao, entrega e pagamento na maquininha.",
                "usuario": usuario,
            },
        )
        if not pedido.itens.exists():
            for codigo, quantidade in (("DEMO-1004", Decimal("1.500")), ("DEMO-1002", Decimal("2.000"))):
                produto = produtos[codigo][0]
                ItemPedidoOnline.objects.create(pedido=pedido, produto=produto, quantidade=quantidade, preco_unitario=produto.preco_venda)
            pedido.recalcular()