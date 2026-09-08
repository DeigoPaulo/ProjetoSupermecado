import hashlib
import json
import zipfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.compras.models import EntradaCompra, ItemEntradaCompra
from apps.compras.services import finalizar_entrada_compra
from apps.empresas.models import Empresa, Filial
from apps.fiscal.models import DocumentoFiscal
from apps.fornecedores.models import Fornecedor
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento
from apps.vendas.services import finalizar_venda

from .evidencia_piloto import gerar_evidencia_fluxo_estoque_piloto
from .fechamento_contabil import capturar_fechamento_estoque_contabil
from .ficha_execucao_piloto import gerar_ficha_execucao_piloto
from .models import (
    Estoque,
    LoteEstoque,
    MovimentacaoLoteEstoque,
    StatusInventario,
    StatusTratamentoValidade,
)
from .previsualizacao_piloto import previsualizar_candidatos_piloto
from .verificador_artefatos_piloto import verificar_integridade_artefatos_piloto
from .services import (
    aplicar_inventario,
    criar_inventario_divergencias_validade,
    planejar_tratamento_validade_lote,
    registrar_conferencia_fisica_validade_lote,
    registrar_contagem_lote_inventario_validade,
    registrar_perda_lote_validade,
)


class FluxoEstoquePilotoPontaAPontaTests(TestCase):
    def test_compra_venda_perda_inventario_e_fechamento_geram_evidencia_valida(self):
        usuario = get_user_model().objects.create_superuser(
            "master-piloto-estoque", "piloto@example.com", "senha"
        )
        empresa = Empresa.objects.create(
            razao_social="Mercado Piloto Sintético Ltda",
            nome_fantasia="Mercado Piloto Sintético",
            cnpj="91.111.111/0001-91",
        )
        filial = Filial.objects.create(
            empresa=empresa, nome="Filial Ensaio", cnpj=empresa.cnpj
        )
        fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor Sintético Ltda",
            nome_fantasia="Fornecedor Sintético",
        )
        categoria = Categoria.all_objects.create(nome="Categoria Ensaio Ponta a Ponta")
        produto = Produto.objects.create(
            codigo_barras="7899911111111",
            nome="Produto Sintético Rastreado",
            categoria=categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("10.00"),
            exige_lote=True,
        )
        entrada = EntradaCompra.objects.create(
            fornecedor=fornecedor,
            filial=filial,
            usuario=usuario,
            numero_documento="ENSAIO-SEM-VALOR-FISCAL",
            gerar_conta_financeira=False,
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=produto,
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("12.00"),
            codigo_lote="LOTE-VENCIDO-ENSAIO",
            validade=timezone.localdate() - timedelta(days=1),
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=produto,
            quantidade=Decimal("7.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("28.00"),
            codigo_lote="LOTE-VALIDO-ENSAIO",
            validade=timezone.localdate() + timedelta(days=10),
        )
        finalizar_entrada_compra(entrada, supervisor=usuario)

        lote_vencido = LoteEstoque.objects.get(codigo="LOTE-VENCIDO-ENSAIO")
        lote_valido = LoteEstoque.objects.get(codigo="LOTE-VALIDO-ENSAIO")
        caixa = Caixa.objects.create(
            filial=filial, usuario_abertura=usuario, valor_inicial=Decimal("0.00")
        )
        dinheiro = FormaPagamento.objects.create(
            nome="Dinheiro Ensaio", tipo="DINHEIRO", permite_troco=True
        )
        venda = finalizar_venda(
            caixa=caixa,
            usuario=usuario,
            itens=[{"produto": produto, "quantidade": Decimal("2.000")}],
            pagamentos=[{"forma_pagamento": dinheiro, "valor": Decimal("20.00")}],
            preparar_fiscal=False,
        )
        lote_vencido.refresh_from_db()
        lote_valido.refresh_from_db()
        self.assertEqual(lote_vencido.quantidade_atual, Decimal("3.000"))
        self.assertEqual(lote_valido.quantidade_atual, Decimal("5.000"))
        alocacao_venda = MovimentacaoLoteEstoque.objects.get(
            movimentacao__referencia=f"venda:{venda.pk}", lote=lote_valido
        )
        self.assertEqual(alocacao_venda.lote_codigo_snapshot, "LOTE-VALIDO-ENSAIO")
        self.assertEqual(alocacao_venda.lote_validade_snapshot, lote_valido.validade)
        self.assertEqual(
            alocacao_venda.tratamento_status_snapshot,
            StatusTratamentoValidade.NAO_INICIADO,
        )
        self.assertTrue(alocacao_venda.snapshot_integro)

        planejar_tratamento_validade_lote(
            lote=lote_vencido,
            status=StatusTratamentoValidade.DESCARTE_PLANEJADO,
            observacao="Separado para o ensaio de descarte controlado.",
            usuario=usuario,
        )
        registrar_conferencia_fisica_validade_lote(
            lote=lote_vencido,
            quantidade_observada=Decimal("3.000"),
            observacao="Conferência sintética antes da perda.",
            confirmar_dados=True,
            usuario=usuario,
        )
        perda = registrar_perda_lote_validade(
            lote=lote_vencido,
            quantidade=Decimal("1.000"),
            motivo="Unidade sintética vencida",
            usuario=usuario,
            supervisor=usuario,
        )
        lote_vencido.refresh_from_db()
        registrar_conferencia_fisica_validade_lote(
            lote=lote_vencido,
            quantidade_observada=Decimal("1.000"),
            observacao="Divergência sintética restante para inventário.",
            confirmar_dados=True,
            usuario=usuario,
        )
        inventario, criado = criar_inventario_divergencias_validade(
            filial=filial,
            lotes=[lote_vencido],
            usuario=usuario,
            descricao="Ensaio integrado de validade",
        )
        self.assertTrue(criado)
        item = inventario.itens.get(produto=produto)
        item.quantidade_contada = Decimal("6.000")
        item.save(update_fields=["quantidade_contada"])
        for escopo in item.escopos_validade.select_related("lote"):
            registrar_contagem_lote_inventario_validade(
                escopo=escopo,
                quantidade_contada=(
                    Decimal("1.000") if escopo.lote_id == lote_vencido.pk
                    else escopo.lote.quantidade_atual
                ),
                usuario=usuario,
                observacao="Contagem do ensaio ponta a ponta.",
                confirmar_dados=True,
            )
        aplicar_inventario(
            inventario=inventario, usuario=usuario, supervisor=usuario
        )
        inventario.refresh_from_db()
        self.assertEqual(inventario.status, StatusInventario.APLICADO)
        self.assertEqual(
            Estoque.objects.get(produto=produto, filial=filial).quantidade_atual,
            Decimal("6.000"),
        )

        lote_valido.validade = timezone.localdate() - timedelta(days=2)
        lote_valido.tratamento_validade_status = StatusTratamentoValidade.SEPARADO
        lote_valido.save(update_fields=[
            "validade", "tratamento_validade_status", "atualizado_em"
        ])
        alocacao_venda.refresh_from_db()
        self.assertEqual(alocacao_venda.lote_codigo_snapshot, "LOTE-VALIDO-ENSAIO")
        self.assertEqual(
            alocacao_venda.tratamento_status_snapshot,
            StatusTratamentoValidade.NAO_INICIADO,
        )
        self.assertTrue(alocacao_venda.snapshot_integro)

        fechamento, criado_fechamento = capturar_fechamento_estoque_contabil(
            filial=filial, usuario=usuario
        )
        self.assertTrue(criado_fechamento)
        ficha = gerar_ficha_execucao_piloto(
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
            responsavel_execucao="Operador Piloto",
            responsavel_conferencia="Conferente Piloto",
            observacoes_operacionais="Turno acompanhado pelo Master.",
        )
        self.assertEqual(ficha["contrato"], "inventory_pilot_execution_sheet_v2")
        self.assertTrue(ficha["apta_para_verificacao_final"])
        self.assertFalse(ficha["aprovacao_automatica"])
        self.assertEqual(ficha["impedimentos"], [])
        self.assertEqual(len(ficha["conteudo_sha256"]), 64)
        self.assertIn(f"--entrada-id {entrada.pk}", ficha["comando_verificacao_final"])
        self.assertEqual(ficha["responsaveis"]["execucao"], "Operador Piloto")
        self.assertTrue(ficha["responsaveis"]["responsaveis_distintos"])
        self.assertFalse(ficha["responsaveis"]["persistidos_no_banco"])
        self.assertFalse(ficha["dados_pessoais_sensiveis_solicitados"])
        self.assertGreaterEqual(len(ficha["orientacoes_operacionais"]), 5)

        saida_ficha = StringIO()
        call_command(
            "gerar_ficha_execucao_piloto",
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
            responsavel_execucao="Operador Piloto",
            responsavel_conferencia="Conferente Piloto",
            observacoes="Turno acompanhado pelo Master.",
            estrito=True,
            stdout=saida_ficha,
        )
        self.assertTrue(
            json.loads(saida_ficha.getvalue())["apta_para_verificacao_final"]
        )
        self.client.force_login(usuario)
        resposta_previa = self.client.post(
            "/configuracoes/servidor-local/piloto/previa.json",
            {"filial_id": filial.pk, "limite": 20},
        )
        self.assertEqual(resposta_previa.status_code, 200)
        self.assertIn("attachment", resposta_previa["Content-Disposition"])
        self.assertEqual(
            json.loads(resposta_previa.content)["filial"]["id"], filial.pk
        )
        resposta_ficha = self.client.post(
            "/configuracoes/servidor-local/piloto/ficha.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
                "responsavel_execucao": "Operador Piloto",
                "responsavel_conferencia": "Conferente Piloto",
                "observacoes_operacionais": "Turno acompanhado pelo Master.",
                "confirmar_selecao": "sim",
            },
        )
        self.assertEqual(resposta_ficha.status_code, 200)
        self.assertTrue(
            json.loads(resposta_ficha.content)["apta_para_verificacao_final"]
        )
        resposta_relatorio = self.client.post(
            "/configuracoes/servidor-local/piloto/relatorio.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
                "tipo_dados": "sinteticos",
                "confirmar_relatorio": "sim",
            },
        )
        self.assertEqual(resposta_relatorio.status_code, 200)
        self.assertIn("attachment", resposta_relatorio["Content-Disposition"])
        relatorio_visual = json.loads(resposta_relatorio.content)
        self.assertEqual(
            relatorio_visual["contrato"], "inventory_pilot_end_to_end_evidence_v3"
        )
        self.assertTrue(relatorio_visual["valida"])
        self.assertTrue(relatorio_visual["dados_sinteticos"])
        self.assertFalse(relatorio_visual["comunicacao_externa"])
        resposta_integridade_visual = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-arquivos.json",
            {
                "ficha_json": SimpleUploadedFile(
                    "ficha.json",
                    resposta_ficha.content,
                    content_type="application/json",
                ),
                "relatorio_json": SimpleUploadedFile(
                    "relatorio.json",
                    resposta_relatorio.content,
                    content_type="application/json",
                ),
                "confirmar_verificacao": "sim",
            },
        )
        self.assertEqual(resposta_integridade_visual.status_code, 200)
        integridade_visual = json.loads(resposta_integridade_visual.content)
        self.assertTrue(integridade_visual["integridade_confirmada"])
        self.assertFalse(integridade_visual["consulta_banco"])
        self.assertFalse(integridade_visual["persiste_resultado"])
        self.assertNotIn("Operador Piloto", resposta_integridade_visual.content.decode())
        resposta_dossie = self.client.post(
            "/configuracoes/servidor-local/piloto/dossie.zip",
            {
                "ficha_json": SimpleUploadedFile(
                    "ficha.json", resposta_ficha.content, content_type="application/json"
                ),
                "relatorio_json": SimpleUploadedFile(
                    "relatorio.json",
                    resposta_relatorio.content,
                    content_type="application/json",
                ),
                "verificacao_json": SimpleUploadedFile(
                    "verificacao.json",
                    resposta_integridade_visual.content,
                    content_type="application/json",
                ),
                "confirmar_dossie": "sim",
            },
        )
        self.assertEqual(resposta_dossie.status_code, 200)
        self.assertEqual(resposta_dossie["Content-Type"], "application/zip")
        self.assertIn("attachment", resposta_dossie["Content-Disposition"])
        sha256_dossie = hashlib.sha256(resposta_dossie.content).hexdigest()
        self.assertIn(
            sha256_dossie[:12], resposta_dossie["Content-Disposition"]
        )
        with zipfile.ZipFile(BytesIO(resposta_dossie.content)) as pacote:
            manifesto_dossie = json.loads(pacote.read("manifesto.json"))
            self.assertEqual(
                manifesto_dossie["contrato"], "inventory_pilot_dossier_v1"
            )
            self.assertTrue(manifesto_dossie["integridade_confirmada"])
            self.assertFalse(manifesto_dossie["persiste_dossie"])
        resposta_verificacao_dossie = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-dossie.json",
            {
                "dossie_zip": SimpleUploadedFile(
                    "dossie.zip",
                    resposta_dossie.content,
                    content_type="application/zip",
                ),
                "confirmar_verificacao_dossie": "sim",
            },
        )
        self.assertEqual(resposta_verificacao_dossie.status_code, 200)
        integridade_dossie = json.loads(resposta_verificacao_dossie.content)
        self.assertTrue(integridade_dossie["integridade_confirmada"])
        self.assertEqual(
            integridade_dossie["dossie"]["sha256_arquivo"], sha256_dossie
        )
        self.assertFalse(integridade_dossie["extrai_arquivos"])
        self.assertFalse(integridade_dossie["persiste_resultado"])
        self.assertFalse(integridade_dossie["consulta_banco"])
        self.assertNotIn(
            "Operador Piloto", resposta_verificacao_dossie.content.decode()
        )
        resposta_verificacao_dossie_invalido = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-dossie.json",
            {
                "dossie_zip": SimpleUploadedFile(
                    "dossie.zip", b"nao e zip", content_type="application/zip"
                ),
                "confirmar_verificacao_dossie": "sim",
            },
        )
        self.assertEqual(resposta_verificacao_dossie_invalido.status_code, 200)
        self.assertFalse(
            json.loads(resposta_verificacao_dossie_invalido.content)[
                "integridade_confirmada"
            ]
        )
        resposta_verificacao_dossie_sem_confirmacao = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-dossie.json",
            {
                "dossie_zip": SimpleUploadedFile(
                    "dossie.zip",
                    resposta_dossie.content,
                    content_type="application/zip",
                )
            },
        )
        self.assertEqual(
            resposta_verificacao_dossie_sem_confirmacao.status_code, 400
        )
        resposta_dossie_sem_confirmacao = self.client.post(
            "/configuracoes/servidor-local/piloto/dossie.zip",
            {
                "ficha_json": SimpleUploadedFile(
                    "ficha.json", resposta_ficha.content, content_type="application/json"
                ),
                "relatorio_json": SimpleUploadedFile(
                    "relatorio.json",
                    resposta_relatorio.content,
                    content_type="application/json",
                ),
                "verificacao_json": SimpleUploadedFile(
                    "verificacao.json",
                    resposta_integridade_visual.content,
                    content_type="application/json",
                ),
            },
        )
        self.assertEqual(resposta_dossie_sem_confirmacao.status_code, 400)
        resposta_integridade_sem_confirmacao = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-arquivos.json",
            {
                "ficha_json": SimpleUploadedFile(
                    "ficha.json", resposta_ficha.content, content_type="application/json"
                ),
                "relatorio_json": SimpleUploadedFile(
                    "relatorio.json",
                    resposta_relatorio.content,
                    content_type="application/json",
                ),
            },
        )
        self.assertEqual(resposta_integridade_sem_confirmacao.status_code, 400)
        resposta_integridade_grande = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-arquivos.json",
            {
                "ficha_json": SimpleUploadedFile(
                    "ficha.json",
                    b"x" * ((5 * 1024 * 1024) + 1),
                    content_type="application/json",
                ),
                "relatorio_json": SimpleUploadedFile(
                    "relatorio.json",
                    resposta_relatorio.content,
                    content_type="application/json",
                ),
                "confirmar_verificacao": "sim",
            },
        )
        self.assertEqual(resposta_integridade_grande.status_code, 400)
        ficha_adulterada = json.loads(resposta_ficha.content)
        ficha_adulterada["produto_id"] = produto.pk + 999
        resposta_integridade_adulterada = self.client.post(
            "/configuracoes/servidor-local/piloto/verificar-arquivos.json",
            {
                "ficha_json": SimpleUploadedFile(
                    "ficha.json",
                    json.dumps(ficha_adulterada).encode(),
                    content_type="application/json",
                ),
                "relatorio_json": SimpleUploadedFile(
                    "relatorio.json",
                    resposta_relatorio.content,
                    content_type="application/json",
                ),
                "confirmar_verificacao": "sim",
            },
        )
        self.assertEqual(resposta_integridade_adulterada.status_code, 200)
        self.assertFalse(
            json.loads(resposta_integridade_adulterada.content)[
                "integridade_confirmada"
            ]
        )
        resposta_relatorio_real = self.client.post(
            "/configuracoes/servidor-local/piloto/relatorio.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
                "tipo_dados": "reais",
                "confirmar_relatorio": "sim",
            },
        )
        self.assertEqual(resposta_relatorio_real.status_code, 200)
        relatorio_visual_real = json.loads(resposta_relatorio_real.content)
        self.assertFalse(relatorio_visual_real["dados_sinteticos"])
        self.assertTrue(
            relatorio_visual_real["prontidao_piloto_real"]["aplicada_ao_aceite"]
        )
        self.assertTrue(
            relatorio_visual_real["verificacoes"][
                "filial_pronta_para_piloto_real"
            ]
        )
        resposta_relatorio_sem_confirmacao = self.client.post(
            "/configuracoes/servidor-local/piloto/relatorio.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
                "tipo_dados": "sinteticos",
            },
        )
        self.assertEqual(resposta_relatorio_sem_confirmacao.status_code, 400)
        resposta_relatorio_sem_tipo = self.client.post(
            "/configuracoes/servidor-local/piloto/relatorio.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
                "confirmar_relatorio": "sim",
            },
        )
        self.assertEqual(resposta_relatorio_sem_tipo.status_code, 400)
        resposta_sem_confirmacao = self.client.post(
            "/configuracoes/servidor-local/piloto/ficha.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
            },
        )
        self.assertEqual(resposta_sem_confirmacao.status_code, 400)
        resposta_sem_responsaveis = self.client.post(
            "/configuracoes/servidor-local/piloto/ficha.json",
            {
                "entrada_id": entrada.pk,
                "venda_id": venda.pk,
                "perda_id": perda.pk,
                "inventario_id": inventario.pk,
                "fechamento_id": fechamento.pk,
                "confirmar_selecao": "sim",
            },
        )
        self.assertEqual(resposta_sem_responsaveis.status_code, 400)
        with self.assertRaisesMessage(ValueError, "não deve conter"):
            gerar_ficha_execucao_piloto(
                entrada_id=entrada.pk,
                venda_id=venda.pk,
                perda_id=perda.pk,
                inventario_id=inventario.pk,
                fechamento_id=fechamento.pk,
                responsavel_execucao="operador@example.com",
                responsavel_conferencia="Conferente Piloto",
            )
        previa = previsualizar_candidatos_piloto(filial_id=filial.pk)
        self.assertEqual(previa["contrato"], "inventory_pilot_candidate_preview_v1")
        self.assertEqual(previa["produtos_com_fluxo_completo"], [produto.pk])
        self.assertTrue(previa["possui_candidatos_compativeis"])
        self.assertFalse(previa["seleciona_automaticamente"])
        self.assertEqual(previa["impedimentos"], [])
        self.assertEqual(previa["candidatos"]["entradas"][0]["id"], entrada.pk)

        saida_previa = StringIO()
        call_command(
            "previsualizar_fluxo_estoque_piloto",
            filial_id=filial.pk,
            limite=20,
            estrito=True,
            stdout=saida_previa,
        )
        self.assertEqual(
            json.loads(saida_previa.getvalue())["filial"]["id"], filial.pk
        )
        saida = StringIO()
        call_command(
            "verificar_fluxo_estoque_piloto",
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
            estrito=True,
            dados_sinteticos=True,
            stdout=saida,
        )
        evidencia = json.loads(saida.getvalue())
        self.assertEqual(evidencia["contrato"], "inventory_pilot_end_to_end_evidence_v3")
        self.assertTrue(evidencia["valida"])
        self.assertEqual(
            evidencia["prontidao_piloto_real"]["contrato"],
            "inventory_real_pilot_readiness_v1",
        )
        self.assertFalse(
            evidencia["prontidao_piloto_real"]["aplicada_ao_aceite"]
        )
        self.assertTrue(evidencia["verificacoes"]["venda_snapshot_lote_preservado"])
        self.assertTrue(evidencia["verificacoes"]["venda_consumiu_somente_tratamento_liberado"])
        self.assertEqual(
            evidencia["alocacoes_venda_snapshot"][0]["tratamento_status"],
            StatusTratamentoValidade.NAO_INICIADO,
        )
        self.assertTrue(all(evidencia["verificacoes"].values()))
        self.assertEqual(len(evidencia["conteudo_sha256"]), 64)
        self.assertTrue(evidencia["somente_leitura"])
        self.assertFalse(evidencia["comunicacao_externa"])
        self.assertTrue(evidencia["dados_sinteticos"])
        self.assertFalse(DocumentoFiscal.objects.exists())

        integridade_artefatos = verificar_integridade_artefatos_piloto(
            ficha=ficha,
            relatorio=evidencia,
        )
        self.assertEqual(
            integridade_artefatos["contrato"],
            "inventory_pilot_artifact_integrity_v1",
        )
        self.assertTrue(integridade_artefatos["integridade_confirmada"])
        self.assertTrue(integridade_artefatos["vinculo"]["confirmado"])
        self.assertEqual(integridade_artefatos["impedimentos"], [])
        self.assertFalse(integridade_artefatos["consulta_banco"])
        self.assertFalse(integridade_artefatos["persiste_resultado"])
        self.assertNotIn("Operador Piloto", json.dumps(integridade_artefatos))

        evidencia_real = gerar_evidencia_fluxo_estoque_piloto(
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
        )
        self.assertTrue(evidencia_real["valida"])
        self.assertTrue(
            evidencia_real["prontidao_piloto_real"]["aplicada_ao_aceite"]
        )
        self.assertTrue(
            evidencia_real["verificacoes"]["filial_pronta_para_piloto_real"]
        )

        MovimentacaoLoteEstoque.objects.filter(pk=alocacao_venda.pk).update(
            lote_codigo_snapshot="",
            tratamento_status_snapshot="",
            snapshot_sha256="",
        )
        evidencia_legada = gerar_evidencia_fluxo_estoque_piloto(
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
            dados_sinteticos=True,
        )
        self.assertFalse(evidencia_legada["valida"])
        self.assertFalse(
            evidencia_legada["verificacoes"]["venda_snapshot_lote_preservado"]
        )

        outra_filial = Filial.objects.create(
            empresa=empresa, nome="Filial fora do ensaio", cnpj="91.111.111/0002-72"
        )
        outro_fechamento, _ = capturar_fechamento_estoque_contabil(
            filial=outra_filial, usuario=usuario
        )
        ficha_incompativel = gerar_ficha_execucao_piloto(
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=outro_fechamento.pk,
            responsavel_execucao="Operador Piloto",
            responsavel_conferencia="Conferente Piloto",
        )
        self.assertFalse(ficha_incompativel["apta_para_verificacao_final"])
        self.assertIsNone(ficha_incompativel["filial_id"])
        self.assertIn(
            "MESMA_FILIAL",
            {item["codigo"] for item in ficha_incompativel["impedimentos"]},
        )
        with self.assertRaisesMessage(CommandError, "ainda possui impedimentos"):
            call_command(
                "gerar_ficha_execucao_piloto",
                entrada_id=entrada.pk,
                venda_id=venda.pk,
                perda_id=perda.pk,
                inventario_id=inventario.pk,
                fechamento_id=outro_fechamento.pk,
                responsavel_execucao="Operador Piloto",
                responsavel_conferencia="Conferente Piloto",
                estrito=True,
                stdout=StringIO(),
            )
        with self.assertRaisesMessage(ValidationError, "mesma filial"):
            gerar_evidencia_fluxo_estoque_piloto(
                entrada_id=entrada.pk,
                venda_id=venda.pk,
                perda_id=perda.pk,
                inventario_id=inventario.pk,
                fechamento_id=outro_fechamento.pk,
            )
