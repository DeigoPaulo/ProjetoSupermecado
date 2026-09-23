from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.fiscal.models import TipoDocumentoFiscal
from apps.fiscal.services import NFE_NS, _adicionar_integracao_pagamento_nfce, validar_vinculos_pagamentos_xml
from apps.pdv.models import Caixa
from . import tests as vendas_tests
from .integracao_pagamentos import confirmar_pagamento_no_servidor
from .models import ConfirmacaoPagamentoIntegrado, FormaPagamento, PagamentoVenda, Venda
from .services import finalizar_venda, formas_pagamento_disponiveis
from .test_support_integracao import confirmar_parcela_teste


class ConfirmacaoIntegracaoTests(TestCase):
    setUp = vendas_tests.VendaServiceTests.setUp

    def confirmar(self, valor="25.00", **dados):
        return confirmar_parcela_teste(
            caixa=self.caixa, forma_pagamento=self.pix, valor=Decimal(valor), **dados,
        )

    def vender(self, pagamentos, **kwargs):
        return finalizar_venda(
            caixa=kwargs.pop("caixa", self.caixa), usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=pagamentos, preparar_fiscal=False, **kwargs,
        )

    def parcela(self, confirmacao=None, **dados):
        return {
            "forma_pagamento": self.pix, "valor": Decimal("25.00"),
            "tipo_integracao": "1",
            "confirmacao_integracao_id": str(confirmacao.pk) if confirmacao else "",
            **dados,
        }

    def vales(self):
        return [
            FormaPagamento.objects.create(nome=tipo, tipo=tipo)
            for tipo in ("VALE_ALIMENTACAO", "VALE_REFEICAO")
        ]

    def test_jornada_vales_sozinhos_e_divididos_preserva_confirmacao_por_parcela(self):
        credito = FormaPagamento.objects.create(nome="Crédito", tipo="CREDITO")
        for vale in self.vales():
            for outra in (None, self.pix, self.dinheiro, credito):
                with self.subTest(vale=vale.tipo, outra=getattr(outra, "tipo", None)):
                    parcelas = [(vale, Decimal("25.00"))] if outra is None else [
                        (vale, Decimal("10.00")), (outra, Decimal("15.00")),
                    ]
                    pagamentos = []
                    confirmacoes = []
                    for forma, valor in parcelas:
                        confirmacao = None
                        if forma != self.dinheiro:
                            confirmacao = confirmar_parcela_teste(
                                caixa=self.caixa, forma_pagamento=forma, valor=valor,
                            )
                            confirmacoes.append(confirmacao.pk)
                        pagamentos.append({
                            "forma_pagamento": forma, "valor": valor,
                            "confirmacao_integracao_id": str(confirmacao.pk) if confirmacao else "",
                        })
                    venda = self.vender(pagamentos)
                    gravados = list(venda.pagamentos.order_by("pk"))
                    self.assertEqual([item.valor for item in gravados], [valor for _, valor in parcelas])
                    self.assertEqual(
                        [item.confirmacao_integracao_id for item in gravados if item.confirmacao_integracao_id],
                        confirmacoes,
                    )
                    self.assertEqual(gravados[0].bandeira_cartao, "")
                    self.assertEqual(gravados[0].codigo_autorizacao, "AUT-TESTE")

    def test_vales_rejeitam_confirmacao_duplicada_consumida_ou_divergente(self):
        for vale in self.vales():
            with self.subTest(vale=vale.tipo):
                confirmacao = confirmar_parcela_teste(
                    caixa=self.caixa, forma_pagamento=vale, valor=Decimal("12.50"),
                )
                parcela = {
                    "forma_pagamento": vale, "valor": Decimal("12.50"),
                    "confirmacao_integracao_id": str(confirmacao.pk),
                }
                with self.assertRaisesMessage(ValidationError, "já utilizada"):
                    self.vender([parcela, parcela.copy()])
                with self.assertRaisesMessage(ValidationError, "não corresponde"):
                    self.vender([{"forma_pagamento": vale, "valor": Decimal("25.00"),
                                  "confirmacao_integracao_id": str(confirmacao.pk)}])
                with self.assertRaisesMessage(ValidationError, "não corresponde"):
                    self.vender([{"forma_pagamento": self.pix, "valor": Decimal("25.00"),
                                  "confirmacao_integracao_id": str(confirmacao.pk)}])
                confirmacao_total = confirmar_parcela_teste(
                    caixa=self.caixa, forma_pagamento=vale, valor=Decimal("25.00"),
                )
                self.vender([{"forma_pagamento": vale, "valor": Decimal("25.00"),
                             "confirmacao_integracao_id": str(confirmacao_total.pk)}])
                with self.assertRaisesMessage(ValidationError, "já utilizada"):
                    self.vender([{"forma_pagamento": vale, "valor": Decimal("25.00"),
                                  "confirmacao_integracao_id": str(confirmacao_total.pk)}])
                with self.assertRaises(ValidationError):
                    confirmar_parcela_teste(
                        caixa=self.caixa, forma_pagamento=vale, valor=Decimal("25.00"),
                        transacao_externa_id=confirmacao_total.transacao_externa_id,
                    )

    def test_vales_rejeitam_outro_caixa_filial_e_metadados_adulterados(self):
        from apps.empresas.models import Empresa, Filial

        outra_empresa = Empresa.objects.create(razao_social="Outra", nome_fantasia="Outra", cnpj="22222222000122")
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Outra", cnpj=outra_empresa.cnpj)
        outro_caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario, valor_inicial=0)
        caixa_outra_filial = Caixa.objects.create(filial=outra_filial, usuario_abertura=self.usuario, valor_inicial=0)
        for vale in self.vales():
            with self.subTest(vale=vale.tipo):
                for caixa in (outro_caixa, caixa_outra_filial):
                    confirmacao = confirmar_parcela_teste(
                        caixa=caixa, forma_pagamento=vale, valor=Decimal("25.00"),
                    )
                    with self.assertRaisesMessage(ValidationError, "não corresponde"):
                        self.vender([{"forma_pagamento": vale, "valor": Decimal("25.00"),
                                      "confirmacao_integracao_id": str(confirmacao.pk)}])
                confirmacao = confirmar_parcela_teste(
                    caixa=self.caixa, forma_pagamento=vale, valor=Decimal("25.00"),
                )
                pagamento = self.vender([{
                    "forma_pagamento": vale, "valor": Decimal("25.00"),
                    "confirmacao_integracao_id": str(confirmacao.pk),
                    "codigo_autorizacao": "AUT-DIGITADA", "bandeira_cartao": "01",
                }]).pagamentos.get()
                self.assertEqual(pagamento.codigo_autorizacao, "AUT-TESTE")
                self.assertEqual(pagamento.bandeira_cartao, "")
                for campo, valor in (
                    ("codigo_autorizacao", "AUT-ALTERADA"), ("nsu", "NSU-ALTERADO"),
                    ("cnpj_instituicao_pagamento", "00000000000000"),
                    ("bandeira_cartao", "01"),
                    ("cnpj_beneficiario_pagamento", "00000000000000"),
                    ("identificador_terminal_pagamento", "OUTRO"),
                ):
                    setattr(pagamento, campo, valor)
                    with self.subTest(campo=campo), self.assertRaisesMessage(ValidationError, "divergem"):
                        _adicionar_integracao_pagamento_nfce(
                            ET.Element("detPag"), pagamento, "10" if vale.tipo == "VALE_ALIMENTACAO" else "11",
                            uf_emitente="GO",
                        )
                    pagamento.refresh_from_db()

    def test_vale_sem_confirmacao_nao_aceita_dados_digitados_ou_simulador(self):
        for vale in self.vales():
            with self.subTest(vale=vale.tipo), self.assertRaisesMessage(
                ValidationError, "confirmação confiável",
            ):
                self.vender([{
                    "forma_pagamento": vale, "valor": Decimal("25.00"),
                    "tipo_integracao": "1", "codigo_autorizacao": "AUT-DIGITADA",
                    "nsu": "NSU-DIGITADO", "transacao_externa_id": "E2E-DIGITADO",
                }])
            pagamento = self.vender([{"forma_pagamento": vale, "valor": Decimal("25.00")}]).pagamentos.get()
            pagamento.tipo_integracao = "2"
            with self.assertRaisesMessage(ValidationError, "confirmação confiável"):
                _adicionar_integracao_pagamento_nfce(
                    ET.Element("detPag"), pagamento,
                    "10" if vale.tipo == "VALE_ALIMENTACAO" else "11", uf_emitente="GO",
                )

    def test_vale_preserva_bandeira_somente_quando_confirmada_pelo_verificador(self):
        vale = self.vales()[0]
        confirmacao = confirmar_parcela_teste(
            caixa=self.caixa, forma_pagamento=vale, valor=Decimal("25.00"),
            bandeira_cartao="01",
        )
        pagamento = self.vender([{
            "forma_pagamento": vale, "valor": Decimal("25.00"),
            "confirmacao_integracao_id": str(confirmacao.pk),
        }]).pagamentos.get()
        self.assertEqual(pagamento.bandeira_cartao, "01")
        det = ET.Element("detPag")
        _adicionar_integracao_pagamento_nfce(det, pagamento, "10", uf_emitente="GO")
        self.assertEqual(det.findtext(f"{{{NFE_NS}}}card/{{{NFE_NS}}}tBand"), "01")

    def test_nao_existe_verificador_habilitado_por_padrao(self):
        with self.assertRaisesMessage(ValidationError, "sem verificador"):
            confirmar_pagamento_no_servidor(
                provedor="TESTE", referencia="arbitraria", caixa=self.caixa,
                forma_pagamento=self.pix, valor=Decimal("25"),
            )
        self.assertFalse(ConfirmacaoPagamentoIntegrado.objects.exists())

    def test_campos_forjados_nao_declaram_integracao_e_rollback_preserva_estoque(self):
        with self.assertRaisesMessage(ValidationError, "confirmação confiável"):
            self.vender([self.parcela(
                transacao_externa_id="TX-FORJADA", nsu="123", codigo_autorizacao="FORJADA",
                cnpj_instituicao_pagamento="12ABC34501DE35",
            )])
        self.assertFalse(Venda.objects.exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10"))

    def test_campos_do_servidor_prevalecem_sobre_post(self):
        confirmacao = self.confirmar()
        pagamento = self.vender([self.parcela(
            confirmacao, codigo_autorizacao="FORJADA", nsu="FORJADO",
            tipo_integracao="2", cnpj_instituicao_pagamento="00000000000000",
        )]).pagamentos.get()
        self.assertEqual(pagamento.codigo_autorizacao, "AUT-TESTE")
        self.assertEqual(pagamento.nsu, "NSU-TESTE")
        self.assertEqual(pagamento.tipo_integracao, "1")
        self.assertEqual(pagamento.cnpj_instituicao_pagamento, "12ABC34501DE35")
        self.assertEqual(pagamento.confirmacao_integracao_id, confirmacao.pk)

    def test_referencia_invalida_e_desconhecida_sao_rejeitadas(self):
        for referencia in ("invalida", "00000000-0000-0000-0000-000000000001"):
            with self.subTest(referencia=referencia), self.assertRaisesMessage(ValidationError, "inexistente ou inválida"):
                self.vender([self.parcela(confirmacao_integracao_id=referencia)])

    def test_confirmacao_de_outro_caixa_ou_filial_nao_e_aceita(self):
        from apps.empresas.models import Empresa, Filial

        confirmacao = self.confirmar()
        empresa = Empresa.objects.create(razao_social="Outra", nome_fantasia="Outra", cnpj="22222222000122")
        filial = Filial.objects.create(empresa=empresa, nome="Outra", cnpj=empresa.cnpj)
        for destino in (self.filial, filial):
            outro = Caixa.objects.create(filial=destino, usuario_abertura=self.usuario, valor_inicial=0)
            confirmacao.caixa = outro
            confirmacao.save(update_fields=["caixa"])
            with self.subTest(filial=destino.pk), self.assertRaisesMessage(ValidationError, "não corresponde"):
                self.vender([self.parcela(confirmacao)])
        self.assertFalse(Venda.objects.exists())

    def test_forma_e_valor_da_parcela_precisam_corresponder(self):
        confirmacao = self.confirmar("20.00")
        with self.assertRaisesMessage(ValidationError, "não corresponde"):
            self.vender([self.parcela(confirmacao)])
        confirmacao = self.confirmar()
        with self.assertRaisesMessage(ValidationError, "não corresponde"):
            self.vender([self.parcela(confirmacao, forma_pagamento=self.dinheiro)])

    def test_nao_reutiliza_confirmacao_em_outra_venda(self):
        confirmacao = self.confirmar()
        self.vender([self.parcela(confirmacao)])
        with self.assertRaisesMessage(ValidationError, "já utilizada"):
            self.vender([self.parcela(confirmacao)])
        self.assertEqual(Venda.objects.count(), 1)

    def test_pagamento_dividido_consume_confirmacao_por_parcela(self):
        primeira = self.confirmar("10.00")
        segunda = self.confirmar("15.00")
        venda = self.vender([
            self.parcela(primeira, valor=Decimal("10")),
            self.parcela(segunda, valor=Decimal("15")),
        ])
        self.assertEqual(set(venda.pagamentos.values_list("confirmacao_integracao_id", flat=True)), {primeira.pk, segunda.pk})

    def test_reuso_na_mesma_venda_reverte_consumo_e_estoque(self):
        confirmacao = self.confirmar("12.50")
        parcelas = [self.parcela(confirmacao, valor=Decimal("12.50")) for _ in range(2)]
        with self.assertRaisesMessage(ValidationError, "já utilizada"):
            self.vender(parcelas)
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(PagamentoVenda.objects.filter(confirmacao_integracao=confirmacao).exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10"))

    def test_banco_impede_consumo_duplo_mesmo_fora_do_servico(self):
        confirmacao = self.confirmar()
        venda = self.vender([self.parcela(confirmacao)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            PagamentoVenda.objects.create(
                venda=venda, forma_pagamento=self.pix, valor=Decimal("25"),
                confirmacao_integracao=confirmacao,
            )

    def test_transacao_do_provedor_nao_gera_segunda_confirmacao(self):
        self.confirmar(transacao_externa_id="UNICA")
        with self.assertRaises(ValidationError):
            self.confirmar(transacao_externa_id="UNICA")
        self.assertEqual(ConfirmacaoPagamentoIntegrado.objects.count(), 1)

    def test_resposta_incompleta_simulada_ou_divergente_nao_gera_confirmacao(self):
        for dados in (
            {"status": "PENDENTE"}, {"codigo_autorizacao": ""}, {"nsu": ""},
            {"cnpj_instituicao_pagamento": ""}, {"tipo_integracao": "3"},
            {"transacao_externa_id": "TEF-SIM-123"}, {"bandeira_cartao": "01"},
            {"tipo_forma": "DEBITO"},
        ):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                self.confirmar(**dados)
        for valor in ("NaN", "Infinity", "-1", "0", "25.001"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                self.confirmar(valor)
        self.assertFalse(ConfirmacaoPagamentoIntegrado.objects.exists())

    def test_xml_bloqueia_integracao_legada_sem_origem(self):
        pagamento = self.vender([self.parcela(tipo_integracao="2")]).pagamentos.get()
        pagamento.tipo_integracao = "1"
        pagamento.cnpj_instituicao_pagamento = "12ABC34501DE35"
        with self.assertRaisesMessage(ValidationError, "confirmação confiável"):
            _adicionar_integracao_pagamento_nfce(ET.Element("detPag"), pagamento, "17", uf_emitente="GO")

    def test_autorizacao_sem_origem_confiavel_nao_vira_caut_com_tipo_2(self):
        pagamento = self.vender([self.parcela(tipo_integracao="2")]).pagamentos.get()
        self.assertIn("Autorização eletrônica simulada", pagamento.mensagem_processadora)
        pagamento.tipo_integracao = "2"
        for autorizacao in (
            pagamento.codigo_autorizacao, pagamento.nsu,
            pagamento.transacao_externa_id, "E2E-DIGITADO",
        ):
            pagamento.codigo_autorizacao = autorizacao
            with self.subTest(autorizacao=autorizacao), self.assertRaisesMessage(
                ValidationError, "confirmação confiável"
            ):
                _adicionar_integracao_pagamento_nfce(
                    ET.Element("detPag"), pagamento, "17", uf_emitente="GO",
                )

    def test_tipo_2_com_autorizacao_confirmada_preserva_caut_e_revalida_paridade(self):
        confirmacao = self.confirmar(tipo_integracao="2")
        pagamento = self.vender([self.parcela(confirmacao)]).pagamentos.get()
        self.assertEqual(pagamento.tipo_integracao, "2")
        documento = SimpleNamespace(
            tipo_documento=TipoDocumentoFiscal.NFCE, venda_id=pagamento.venda_id,
            venda=pagamento.venda, filial=self.filial,
        )
        inf = ET.Element(f"{{{NFE_NS}}}infNFe")
        pag = ET.SubElement(inf, f"{{{NFE_NS}}}pag")
        det = ET.SubElement(pag, f"{{{NFE_NS}}}detPag")
        ET.SubElement(det, f"{{{NFE_NS}}}tPag").text = "17"
        ET.SubElement(det, f"{{{NFE_NS}}}vPag").text = "25.00"
        _adicionar_integracao_pagamento_nfce(det, pagamento, "17", uf_emitente="GO")
        self.assertEqual(det.findtext(f"{{{NFE_NS}}}card/{{{NFE_NS}}}tpIntegra"), "2")
        self.assertEqual(det.findtext(f"{{{NFE_NS}}}card/{{{NFE_NS}}}cAut"), "AUT-TESTE")
        validar_vinculos_pagamentos_xml(documento, inf)
        for tag, valor in (("cAut", "ALTERADA"), ("tpIntegra", "1")):
            elemento = det.find(f"{{{NFE_NS}}}card/{{{NFE_NS}}}{tag}")
            original = elemento.text
            elemento.text = valor
            with self.subTest(tag=tag), self.assertRaisesMessage(ValidationError, "diverge"):
                validar_vinculos_pagamentos_xml(documento, inf)
            elemento.text = original
        pagamento.codigo_autorizacao = "OUTRA"
        pagamento.save(update_fields=["codigo_autorizacao"])
        with self.assertRaisesMessage(ValidationError, "divergem"):
            validar_vinculos_pagamentos_xml(documento, inf)

    def test_xml_bloqueia_adulteracao_posterior_inclusive_tentativa_de_downgrade(self):
        pagamento = self.vender([self.parcela(self.confirmar())]).pagamentos.get()
        for campo, valor in (
            ("codigo_autorizacao", "OUTRA"), ("nsu", "OUTRO"),
            ("valor", Decimal("24")), ("tipo_integracao", "2"),
            ("tipo_integracao", ""), ("cnpj_instituicao_pagamento", "00000000000000"),
        ):
            pagamento.refresh_from_db()
            setattr(pagamento, campo, valor)
            with self.subTest(campo=campo, valor=valor), self.assertRaisesMessage(ValidationError, "divergem"):
                _adicionar_integracao_pagamento_nfce(ET.Element("detPag"), pagamento, "17", uf_emitente="SP")

    def test_xml_preparado_e_revalidado_antes_do_envio(self):
        venda = self.vender([self.parcela(self.confirmar())])
        pagamento = venda.pagamentos.get()
        documento = SimpleNamespace(
            tipo_documento=TipoDocumentoFiscal.NFCE, venda_id=venda.pk,
            venda=venda, filial=self.filial,
        )
        inf = ET.Element(f"{{{NFE_NS}}}infNFe")
        pag = ET.SubElement(inf, f"{{{NFE_NS}}}pag")
        det = ET.SubElement(pag, f"{{{NFE_NS}}}detPag")
        ET.SubElement(det, f"{{{NFE_NS}}}tPag").text = "17"
        valor_xml = ET.SubElement(det, f"{{{NFE_NS}}}vPag")
        valor_xml.text = "25.00"
        _adicionar_integracao_pagamento_nfce(det, pagamento, "17", uf_emitente="GO")
        validar_vinculos_pagamentos_xml(documento, inf)
        for tag in ("vPag", "card/cAut", "card/tpIntegra"):
            caminho = "/".join(f"{{{NFE_NS}}}{parte}" for parte in tag.split("/"))
            elemento = det.find(caminho)
            original = elemento.text
            elemento.text = "2"
            with self.subTest(tag=tag), self.assertRaisesMessage(ValidationError, "diverge"):
                validar_vinculos_pagamentos_xml(documento, inf)
            elemento.text = original
        PagamentoVenda.objects.filter(pk=pagamento.pk).update(codigo_autorizacao="ALTERADA")
        with self.assertRaisesMessage(ValidationError, "divergem"):
            validar_vinculos_pagamentos_xml(documento, inf)


@skipUnless(connection.vendor == "postgresql", "Concorrência exige PostgreSQL real.")
class ConfirmacaoConcorrenciaTests(TransactionTestCase):
    setUp = vendas_tests.VendaServiceTests.setUp

    def test_duas_vendas_concorrentes_consumem_confirmacao_uma_unica_vez(self):
        confirmacao = confirmar_parcela_teste(
            caixa=self.caixa, forma_pagamento=self.pix, valor=Decimal("25"),
        )
        list(formas_pagamento_disponiveis(self.filial))
        barreira = Barrier(2)

        def vender():
            try:
                barreira.wait(timeout=15)
                finalizar_venda(
                    caixa=self.caixa, usuario=self.usuario,
                    itens=[{"produto": self.produto, "quantidade": Decimal("1")}],
                    pagamentos=[{
                        "forma_pagamento": self.pix, "valor": Decimal("25"),
                        "confirmacao_integracao_id": str(confirmacao.pk),
                    }], preparar_fiscal=False,
                )
                return "concluida"
            except ValidationError as exc:
                return " ".join(exc.messages)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futuros = [executor.submit(vender) for _ in range(2)]
            resultados = [futuro.result(timeout=40) for futuro in futuros]
        self.assertEqual(resultados.count("concluida"), 1)
        self.assertTrue(any("já utilizada" in resultado for resultado in resultados))
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(PagamentoVenda.objects.filter(confirmacao_integracao=confirmacao).count(), 1)
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("9"))
