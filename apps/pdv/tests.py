import hashlib
import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.accounts.models import CredencialAutorizacao, PerfilUsuario, TipoCredencialAutorizacao, TipoPerfil, UsoCredencialAutorizacao
from apps.auditoria.models import LogAuditoria
from apps.configuracoes.models import ConfiguracaoImpressao, TipoDocumentoImpressao
from apps.clientes.models import Cliente
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.financeiro.models import ContaMovimentoFinanceiro, LancamentoFinanceiro, TipoContaMovimento, TipoLancamentoFinanceiro
from apps.marketplace.models import CanalPedido, FaixaTaxaEntrega, FormaPagamentoPedido, ItemPedidoOnline, PedidoOnline, PoliticaEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega
from apps.fiscal.models import AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.produtos.models import Categoria, CodigoBarrasProduto, Produto
from apps.vendas.models import EstornoParcialPagamento, FormaPagamento, PreVenda, StatusEstornoParcial, StatusPagamento, StatusVenda, Venda
from apps.vendas.services import cancelar_venda, finalizar_venda, registrar_devolucao_venda

from .models import AcessoPdvNuvem, Caixa, CanalAtualizacaoPdv, EventoDispositivoTerminal, ModoIntegracaoTef, ProtocoloBalanca, ProvedorTef, Sangria, StatusAcessoPdvNuvem, StatusCaixa, StatusLicencaTerminal, Suprimento, TerminalPdv
from .services_acesso import acesso_pdv_nuvem_aprovado, decidir_acesso_pdv_nuvem, solicitar_acesso_pdv_nuvem

def criar_artefato_pdv_teste(caminho, conteudo, versao="0.1.0", assinado=False):
    caminho.write_bytes(conteudo)
    assinatura = "Valid" if assinado else "NotSigned"
    metadados = {
        "version": versao,
        "filename": caminho.name,
        "size_bytes": len(conteudo),
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "executable_signature": assinatura,
        "msi_signature": assinatura if caminho.suffix.lower() == ".msi" else "",
    }
    caminho.with_name(caminho.name + ".version.json").write_text(json.dumps(metadados), encoding="utf-8")


class AcessoPdvNuvemTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(razao_social="Mercado Nuvem", nome_fantasia="Mercado Nuvem", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")
        self.operador = User.objects.create_user(username="operador", password="senha")
        PerfilUsuario.objects.create(usuario=self.operador, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        self.admin = User.objects.create_user(username="admin", password="senha")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)

    def test_pdv_exibe_identidade_deigo_sem_substituir_logo_da_loja(self):
        self.client.force_login(self.admin)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Deigo Tecnologia")
        self.assertContains(resposta, "DeTec PDV")
        self.assertContains(resposta, "img/brand/deigo-tecnologia.png")
        self.assertContains(resposta, self.filial.empresa.nome_fantasia)
    def test_supervisor_ve_menu_no_pdv(self):
        self.client.force_login(self.admin)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'id="pdv-menu-link"')
        self.assertNotContains(resposta, 'id="pdv-exit-button"')

    @override_settings(PDV_NUVEM_REQUER_APROVACAO=False)
    def test_operador_ve_saida_em_vez_do_menu(self):
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'id="pdv-exit-button"')
        self.assertContains(resposta, "Shift+S")
        self.assertContains(resposta, 'action="/logout/"')
        self.assertNotContains(resposta, 'id="pdv-menu-link"')
    @override_settings(PDV_TEF_SIMULATOR_ENABLED=True)
    def test_terminal_autenticado_inicializa_e_registra_conexao(self):
        terminal = TerminalPdv(
            filial=self.filial,
            nome="Caixa 01",
            emite_documento_fiscal=False,
            provedor_tef=ProvedorTef.PAGBANK,
            modo_integracao_tef=ModoIntegracaoTef.DESKTOP_BRIDGE,
            status_licenca=StatusLicencaTerminal.LIBERADA,
            usa_balanca=True,
            protocolo_balanca=ProtocoloBalanca.SERIAL,
            porta_balanca="COM3",
            modelo_balanca="Toledo Prix",
        )
        chave = terminal.gerar_chave_api()
        terminal.save()
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
            abrir_gaveta_em_movimento_caixa=True,
        )

        resposta = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            REMOTE_ADDR="192.168.1.25",
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["terminal"]["nome"], "Caixa 01")
        self.assertTrue(resposta.json()["recursos"]["venda_local"])
        self.assertFalse(resposta.json()["terminal"]["emite_documento_fiscal"])
        self.assertFalse(resposta.json()["recursos"]["emissao_fiscal_automatica"])
        self.assertTrue(resposta.json()["recursos"]["tef_integrado"])
        self.assertTrue(resposta.json()["recursos"]["modo_offline_permitido"])
        self.assertTrue(resposta.json()["terminal"]["permite_modo_offline"])
        self.assertEqual(resposta.json()["terminal"]["provedor_tef"], ProvedorTef.PAGBANK)
        self.assertEqual(resposta.json()["terminal"]["licenca"]["status"], StatusLicencaTerminal.LIBERADA)
        self.assertTrue(resposta.json()["terminal"]["licenca"]["liberada"])
        self.assertEqual(resposta.json()["licenciamento"]["modelo"], "por_terminal")
        self.assertTrue(resposta.json()["licenciamento"]["terminal_autorizado"])
        self.assertTrue(resposta.json()["recursos"]["balanca_local"])
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["contrato"], "pdv_scale_v1")
        self.assertTrue(resposta.json()["dispositivos"]["balanca"]["habilitada"])
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["protocolo"], ProtocoloBalanca.SERIAL)
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["porta"], "COM3")
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["modelo"], "Toledo Prix")
        self.assertTrue(resposta.json()["dispositivos"]["balanca"]["leitura_automatica"])
        self.assertTrue(resposta.json()["dispositivos"]["balanca"]["fallback_manual"])
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["unidade_padrao"], "KG")
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["precisao_decimal"], 3)
        self.assertEqual(resposta.json()["dispositivos"]["gaveta"]["contrato"], "pdv_cash_drawer_v1")
        self.assertTrue(resposta.json()["dispositivos"]["gaveta"]["habilitada"])
        self.assertEqual(resposta.json()["dispositivos"]["gaveta"]["impressora_padrao"], "EPSON TM-T20")
        self.assertTrue(resposta.json()["dispositivos"]["gaveta"]["abrir_em_movimento_caixa"])
        self.assertEqual(resposta.json()["tef"]["contrato"], "pdv_tef_v1")
        self.assertTrue(resposta.json()["tef"]["simulador_permitido"])
        self.assertIn("PIX", resposta.json()["tef"]["tipos_pagamento"])
        self.assertIn("captura_documento_consumidor", resposta.json()["tef"]["recursos_opcionais"])
        self.assertEqual(resposta.json()["tef"]["captura_documento_consumidor"], "NEGOCIADA_NO_DESKTOP")
        self.assertIsNone(resposta.json()["aplicativo"]["versao_cliente"])
        self.assertFalse(resposta.json()["aplicativo"]["atualizacao_disponivel"])
        self.assertTrue(resposta.json()["aplicativo"]["atualizacao_requer_admin_master"])
        terminal.refresh_from_db()
        self.assertIsNotNone(terminal.ultima_conexao)
        self.assertEqual(terminal.ultimo_ip, "192.168.1.25")

    @override_settings(PDV_TEF_SIMULATOR_ENABLED=False)
    def test_bootstrap_bloqueia_simulador_tef_em_producao(self):
        terminal = TerminalPdv(
            filial=self.filial,
            nome="Caixa produção",
            provedor_tef=ProvedorTef.STONE,
            status_licenca=StatusLicencaTerminal.LIBERADA,
        )
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.json()["tef"]["simulador_permitido"])


    @override_settings(PDV_DESKTOP_VERSION="0.3.0", PDV_DESKTOP_MIN_VERSION="0.2.0")
    def test_bootstrap_controla_versao_instalada_sem_atualizacao_automatica(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa versão", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()

        opcional = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            HTTP_X_PDV_VERSION="0.2.5",
        )
        obrigatoria = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            HTTP_X_PDV_VERSION="0.1.9",
        )

        self.assertEqual(opcional.status_code, 200)
        self.assertTrue(opcional.json()["aplicativo"]["atualizacao_disponivel"])
        self.assertFalse(opcional.json()["aplicativo"]["atualizacao_obrigatoria"])
        self.assertEqual(opcional.json()["aplicativo"]["versao_vigente"], "0.3.0")
        self.assertTrue(obrigatoria.json()["aplicativo"]["atualizacao_obrigatoria"])
        self.assertTrue(obrigatoria.json()["aplicativo"]["atualizacao_requer_admin_master"])

    @override_settings(
        PDV_DESKTOP_VERSION="0.3.0",
        PDV_DESKTOP_MIN_VERSION="0.1.0",
        PDV_DESKTOP_RELEASE_CHANNEL=CanalAtualizacaoPdv.PILOTO,
    )
    def test_rollout_piloto_e_congelamento_controlam_atualizacao_por_terminal(self):
        estavel = TerminalPdv.objects.create(
            filial=self.filial,
            nome="Caixa estavel",
            status_licenca=StatusLicencaTerminal.LIBERADA,
            canal_atualizacao=CanalAtualizacaoPdv.ESTAVEL,
        )
        piloto = TerminalPdv.objects.create(
            filial=self.filial,
            nome="Caixa piloto",
            status_licenca=StatusLicencaTerminal.LIBERADA,
            canal_atualizacao=CanalAtualizacaoPdv.PILOTO,
        )
        congelado = TerminalPdv.objects.create(
            filial=self.filial,
            nome="Caixa congelado",
            status_licenca=StatusLicencaTerminal.LIBERADA,
            canal_atualizacao=CanalAtualizacaoPdv.PILOTO,
            bloquear_atualizacoes=True,
        )
        respostas = {}
        for nome, terminal in [("estavel", estavel), ("piloto", piloto), ("congelado", congelado)]:
            chave = terminal.gerar_chave_api()
            terminal.save(update_fields=["chave_api_hash", "chave_api_prefixo"])
            respostas[nome] = self.client.get(
                "/pdv/api/terminal/bootstrap/",
                HTTP_X_TERMINAL_ID=str(terminal.identificador),
                HTTP_X_TERMINAL_KEY=chave,
                HTTP_X_PDV_VERSION="0.2.0",
            ).json()["aplicativo"]

        self.assertFalse(respostas["estavel"]["atualizacao_disponivel"])
        self.assertEqual(respostas["estavel"]["politica_atualizacao"]["motivo"], "aguardando_canal_estavel")
        self.assertTrue(respostas["piloto"]["atualizacao_disponivel"])
        self.assertEqual(respostas["piloto"]["politica_atualizacao"]["motivo"], "atualizacao_liberada")
        self.assertFalse(respostas["congelado"]["atualizacao_disponivel"])
        self.assertEqual(respostas["congelado"]["politica_atualizacao"]["motivo"], "terminal_congelado")

    @override_settings(
        PDV_DESKTOP_VERSION="0.3.0",
        PDV_DESKTOP_MIN_VERSION="0.2.0",
        PDV_DESKTOP_RELEASE_CHANNEL=CanalAtualizacaoPdv.PILOTO,
    )
    def test_versao_insegura_ignora_congelamento_e_permanece_obrigatoria(self):
        terminal = TerminalPdv(
            filial=self.filial,
            nome="Caixa inseguro",
            status_licenca=StatusLicencaTerminal.LIBERADA,
            bloquear_atualizacoes=True,
        )
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            HTTP_X_PDV_VERSION="0.1.0",
        ).json()["aplicativo"]

        self.assertTrue(resposta["atualizacao_disponivel"])
        self.assertTrue(resposta["atualizacao_obrigatoria"])
        self.assertEqual(resposta["politica_atualizacao"]["motivo"], "versao_abaixo_do_minimo")

    def test_terminal_licenciado_baixa_atualizacao_publicada_com_hash_e_auditoria(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa update", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()
        conteudo = b"instalador-pdv-controlado"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "SupermercadoPDV.exe"
            criar_artefato_pdv_teste(caminho, conteudo, versao="0.4.0")
            with override_settings(PDV_DESKTOP_INSTALLER_PATH=caminho, PDV_DESKTOP_VERSION="0.4.0", PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER=False):
                bootstrap = self.client.get(
                    "/pdv/api/terminal/bootstrap/",
                    HTTP_X_TERMINAL_ID=str(terminal.identificador),
                    HTTP_X_TERMINAL_KEY=chave,
                    HTTP_X_PDV_VERSION="0.3.0",
                )
                resposta = self.client.get(
                    "/pdv/api/terminal/update/",
                    HTTP_X_TERMINAL_ID=str(terminal.identificador),
                    HTTP_X_TERMINAL_KEY=chave,
                    HTTP_X_PDV_VERSION="0.3.0",
                    REMOTE_ADDR="192.168.1.31",
                )
                recebido = b"".join(resposta.streaming_content)

        pacote = bootstrap.json()["aplicativo"]["pacote"]
        self.assertEqual(bootstrap.status_code, 200)
        self.assertTrue(pacote["disponivel"])
        self.assertEqual(pacote["nome"], "SupermercadoPDV.exe")
        self.assertEqual(pacote["sha256"], hashlib.sha256(conteudo).hexdigest())
        self.assertIn("/pdv/api/terminal/update/", pacote["url"])
        self.assertFalse(pacote["instalacao_automatica"])
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(recebido, conteudo)
        self.assertEqual(resposta["X-PDV-Version"], "0.4.0")
        self.assertEqual(resposta["X-PDV-SHA256"], hashlib.sha256(conteudo).hexdigest())
        log = LogAuditoria.objects.get(acao="DOWNLOAD_ATUALIZACAO_PDV_DESKTOP", objeto_id=str(terminal.id))
        self.assertEqual(log.ip, "192.168.1.31")

    @override_settings(
        PDV_DESKTOP_VERSION="0.4.0",
        PDV_DESKTOP_MIN_VERSION="0.1.0",
        PDV_DESKTOP_RELEASE_CHANNEL=CanalAtualizacaoPdv.PILOTO,
    )
    def test_download_rejeita_terminal_fora_do_rollout_e_audita(self):
        terminal = TerminalPdv(
            filial=self.filial,
            nome="Caixa fora rollout",
            status_licenca=StatusLicencaTerminal.LIBERADA,
            canal_atualizacao=CanalAtualizacaoPdv.ESTAVEL,
        )
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.get(
            "/pdv/api/terminal/update/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            HTTP_X_PDV_VERSION="0.3.0",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["status"], "atualizacao_nao_liberada")
        self.assertEqual(resposta.json()["politica_atualizacao"]["motivo"], "aguardando_canal_estavel")
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="DOWNLOAD_ATUALIZACAO_NAO_LIBERADA",
                objeto_id=str(terminal.pk),
            ).exists()
        )

    def test_terminal_sem_licenca_nao_baixa_atualizacao(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa update pendente", status_licenca=StatusLicencaTerminal.PENDENTE)
        chave = terminal.gerar_chave_api()
        terminal.save()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "SupermercadoPDV.exe"
            caminho.write_bytes(b"instalador")
            with override_settings(PDV_DESKTOP_INSTALLER_PATH=caminho):
                resposta = self.client.get(
                    "/pdv/api/terminal/update/",
                    HTTP_X_TERMINAL_ID=str(terminal.identificador),
                    HTTP_X_TERMINAL_KEY=chave,
                )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["status"], "licenca_terminal_bloqueada")
        self.assertTrue(LogAuditoria.objects.filter(acao="DOWNLOAD_ATUALIZACAO_SEM_LICENCA", objeto_id=str(terminal.id)).exists())
    def test_terminal_rejeita_chave_invalida_e_terminal_inativo(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa 02", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()

        invalida = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY="chave-errada",
        )
        self.assertEqual(invalida.status_code, 401)

        terminal.ativo = False
        terminal.save(update_fields=["ativo"])
        inativo = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
        )
        self.assertEqual(inativo.status_code, 403)

    def test_terminal_com_licenca_pendente_nao_inicializa(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa pendente", status_licenca=StatusLicencaTerminal.PENDENTE)
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            REMOTE_ADDR="10.0.0.55",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["status"], "licenca_terminal_bloqueada")
        self.assertEqual(resposta.json()["licenca"]["status"], StatusLicencaTerminal.PENDENTE)
        terminal.refresh_from_db()
        self.assertIsNone(terminal.ultima_conexao)
        log = LogAuditoria.objects.get(acao="BOOTSTRAP_TERMINAL_SEM_LICENCA", objeto_id=str(terminal.id))
        self.assertEqual(log.modulo, "pdv")
        self.assertEqual(log.ip, "10.0.0.55")
        self.assertIn("Pendente", log.descricao)

    def test_terminal_licenciado_sincroniza_eventos_de_dispositivo(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa eventos", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.post(
            "/pdv/api/terminal/device-events/",
            data=json.dumps(
                {
                    "eventos": [
                        {
                            "em": "2026-07-13T08:40:00-03:00",
                            "tipo": "balanca",
                            "payload": {
                                "status": "erro",
                                "mensagem": "Driver físico indisponivel",
                                "porta": "COM3",
                                "fallback_manual": True,
                            },
                        },
                        "linha quebrada",
                    ]
                }
            ),
            content_type="application/json",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["recebidos"], 1)
        self.assertEqual(resposta.json()["ignorados"], 1)
        evento = EventoDispositivoTerminal.objects.get(terminal=terminal)
        self.assertEqual(evento.tipo, "balanca")
        self.assertEqual(evento.status, "erro")
        self.assertEqual(evento.mensagem, "Driver físico indisponivel")
        self.assertEqual(evento.payload["porta"], "COM3")
        self.assertIsNotNone(evento.ocorrido_em)

    def test_evento_de_dispositivo_reenviado_nao_e_duplicado(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa idempotente", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()
        corpo = {
            "eventos": [
                {
                    "id": "evento-local-001",
                    "em": "2026-07-27T18:00:00+00:00",
                    "tipo": "tef",
                    "payload": {"status": "ok", "mensagem": "Aprovado"},
                }
            ]
        }

        primeira = self.client.post(
            "/pdv/api/terminal/device-events/",
            data=json.dumps(corpo),
            content_type="application/json",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
        )
        segunda = self.client.post(
            "/pdv/api/terminal/device-events/",
            data=json.dumps(corpo),
            content_type="application/json",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
        )

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(primeira.json()["processados"], 1)
        self.assertEqual(primeira.json()["recebidos"], 1)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(segunda.json()["processados"], 1)
        self.assertEqual(segunda.json()["recebidos"], 0)
        self.assertEqual(segunda.json()["duplicados"], 1)
        self.assertEqual(
            EventoDispositivoTerminal.objects.filter(terminal=terminal, evento_id="evento-local-001").count(),
            1,
        )


    def test_terminal_sem_licenca_nao_sincroniza_eventos_de_dispositivo(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa eventos bloqueado", status_licenca=StatusLicencaTerminal.PENDENTE)
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.post(
            "/pdv/api/terminal/device-events/",
            data=json.dumps({"eventos": [{"tipo": "balanca", "payload": {"status": "erro"}}]}),
            content_type="application/json",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            REMOTE_ADDR="10.0.0.60",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(EventoDispositivoTerminal.objects.exists())
        log = LogAuditoria.objects.get(acao="EVENTOS_DISPOSITIVO_TERMINAL_SEM_LICENCA", objeto_id=str(terminal.id))
        self.assertEqual(log.ip, "10.0.0.60")

    def test_solicitacao_pendente_nao_duplica(self):
        primeira, criada = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial, ip="127.0.0.1")
        segunda, criada_novamente = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial, ip="127.0.0.1")

        self.assertTrue(criada)
        self.assertFalse(criada_novamente)
        self.assertEqual(primeira, segunda)
        self.assertEqual(primeira.status, StatusAcessoPdvNuvem.PENDENTE)

    def test_admin_aprova_acesso_do_operador(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)

        decidir_acesso_pdv_nuvem(solicitacao=solicitacao, admin=self.admin, aprovar=True)

        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusAcessoPdvNuvem.APROVADO)
        self.assertEqual(solicitacao.decidido_por, self.admin)
        self.assertTrue(acesso_pdv_nuvem_aprovado(self.operador, self.filial))

    def test_operador_nao_decide_solicitacao(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)

        with self.assertRaises(ValidationError):
            decidir_acesso_pdv_nuvem(solicitacao=solicitacao, admin=self.operador, aprovar=False)

    def test_painel_de_acessos_exige_supervisao(self):
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/acessos-nuvem/")

        self.assertEqual(resposta.status_code, 403)

    def test_admin_aprova_pelo_painel_de_acessos(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)
        self.client.force_login(self.admin)

        resposta = self.client.post(
            f"/pdv/acessos-nuvem/{solicitacao.id}/decidir/",
            {"acao": "aprovar", "justificativa": "Caixa autorizado"},
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/acessos-nuvem/")
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusAcessoPdvNuvem.APROVADO)
        self.assertEqual(solicitacao.decidido_por, self.admin)
        self.assertContains(resposta, "Caixa autorizado")

    def test_alerta_visual_de_acesso_pendente_aparece_para_admin(self):
        solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)
        self.client.force_login(self.admin)

        resposta = self.client.get("/pdv/acessos-nuvem/")

        self.assertContains(resposta, "1 acesso pendente")
        self.assertContains(resposta, "Há operador aguardando liberação")

    @override_settings(PDV_NUVEM_REQUER_APROVACAO=True)
    def test_pdv_nuvem_bloqueia_operador_sem_aprovacao(self):
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, "Acesso ao PDV em nuvem pendente", status_code=403)
        self.assertContains(resposta, "O admin ou gerente já pode aprovar ou recusar", status_code=403)
        self.assertEqual(AcessoPdvNuvem.objects.filter(usuario=self.operador, status=StatusAcessoPdvNuvem.PENDENTE).count(), 1)

    @override_settings(PDV_NUVEM_REQUER_APROVACAO=True)
    def test_pdv_nuvem_libera_operador_aprovado(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)
        decidir_acesso_pdv_nuvem(solicitacao=solicitacao, admin=self.admin, aprovar=True)
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'id="pdv-capture-document"')
        self.assertContains(resposta, "Shift+F4")

    def test_finalizar_venda_volta_ao_pdv_limpa_carrinho_e_mostra_popup(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000001", nome="Arroz", categoria=categoria, preco_custo=Decimal("10"), preco_venda=Decimal("15"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "2"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["30.00"],
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertContains(resposta, "CAIXA LIVRE")
        self.assertContains(resposta, "Nenhum item no carrinho.")
        self.assertContains(resposta, "pdv-cash-drawer-action")
        self.assertContains(resposta, "pagamento_em_dinheiro")
        venda = Venda.objects.get()
        self.assertContains(resposta, f'data-print-url="/pdv/vendas/{venda.id}/recibo/"')
        self.assertContains(resposta, f'data-desktop-print-url="/pdv/vendas/{venda.id}/impressao-desktop.json"')
        self.assertEqual(self.client.session["pdv_cart"], {})
        self.assertEqual(Venda.objects.count(), 1)

    def test_desconto_exige_supervisor_e_registra_autorizacao_no_log(self):
        categoria = Categoria.objects.create(nome="Mercearia desconto")
        produto = Produto.objects.create(
            codigo_barras="789100000090",
            nome="Produto com desconto",
            categoria=categoria,
            preco_custo=Decimal("10"),
            preco_venda=Decimal("15"),
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro desconto", tipo="DINHEIRO", permite_troco=True)
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "2"}
        session.save()
        self.client.force_login(self.operador)
        dados = {
            "action": "finish",
            "caixa": caixa.id,
            "cliente": "",
            "desconto": "5.00",
            "vencimento_financeiro": "",
            "pagamento_forma": [forma.id],
            "pagamento_valor": ["25.00"],
        }

        sem_autorizacao = self.client.post("/pdv/", dados, follow=True)

        self.assertContains(sem_autorizacao, "Informe usuário e senha ou leia a credencial do supervisor.")
        self.assertEqual(Venda.objects.count(), 0)
        self.assertEqual(self.client.session["pdv_cart"], {str(produto.id): "2"})

        credencial = CredencialAutorizacao(
            usuario=self.admin,
            tipo=TipoCredencialAutorizacao.NFC,
            nome="Cartão do administrador",
            criada_por=self.admin,
        )
        credencial.definir_identificador("CARTAO-ADMIN-PDV")
        credencial.save()
        autorizado = self.client.post(
            "/pdv/",
            {**dados, "supervisor_credencial": "CARTAO-ADMIN-PDV"},
            follow=True,
        )

        venda = Venda.objects.get()
        self.assertContains(autorizado, "CAIXA LIVRE")
        self.assertEqual(venda.desconto, Decimal("5.00"))
        log = LogAuditoria.objects.get(acao="AUTORIZACAO_DESCONTO_PDV", objeto_id=str(venda.id))
        self.assertEqual(log.usuario, self.admin)
        self.assertIn(self.operador.username, log.descricao)
        self.assertIn(self.admin.username, log.descricao)
        uso = UsoCredencialAutorizacao.objects.get(credencial=credencial)
        self.assertEqual(uso.supervisor, self.admin)
        self.assertEqual(uso.operador, self.operador)
    def test_impressao_desktop_avisa_quando_cupom_nao_tem_impressora_padrao(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000002", nome="Feijao", categoria=categoria, preco_custo=Decimal("7"), preco_venda=Decimal("12"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="",
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["12.00"],
            },
        )
        venda = Venda.objects.get()

        resposta = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json")

        self.assertEqual(resposta.status_code, 200)
        payload = resposta.json()
        self.assertTrue(payload["impressao"]["configurada"])
        self.assertFalse(payload["impressao"]["impressora_configurada"])
        self.assertEqual(payload["impressao"]["impressora_padrao"], "")
        self.assertIn("sem impressora padrão definida", payload["impressao"]["mensagem"])

    def test_remover_item_do_pdv_reduz_uma_unidade_por_vez(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000099", nome="Feijao", categoria=categoria, preco_custo=Decimal("7"), preco_venda=Decimal("12"))
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "3.000"}
        session.save()
        self.client.force_login(self.operador)

        primeira = self.client.get(f"/pdv/item/remover/{produto.id}/", follow=True)
        self.assertRedirects(primeira, "/pdv/")
        self.assertEqual(Decimal(self.client.session["pdv_cart"][str(produto.id)]), Decimal("2.000"))
        self.assertContains(primeira, "Quantidade do item reduzida.")

        segunda = self.client.get(f"/pdv/item/remover/{produto.id}/", follow=True)
        self.assertEqual(Decimal(self.client.session["pdv_cart"][str(produto.id)]), Decimal("1.000"))

        terceira = self.client.get(f"/pdv/item/remover/{produto.id}/", follow=True)
        self.assertNotIn(str(produto.id), self.client.session["pdv_cart"])
        self.assertContains(terceira, "Item removido.")

    def test_pdv_bloqueia_pagamento_eletronico_sem_retorno_da_maquininha(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000021", nome="Cafe", categoria=categoria, preco_custo=Decimal("8"), preco_venda=Decimal("20"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="PIX", tipo="PIX")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["20.00"],
            },
            follow=True,
        )

        self.assertContains(resposta, "Pagamento eletrônico exige aprovação da maquininha")
        self.assertEqual(Venda.objects.count(), 0)

    def test_pdv_bloqueia_pagamento_eletronico_aprovado_sem_nsu(self):
        categoria = Categoria.objects.create(nome="Bebidas")
        produto = Produto.objects.create(codigo_barras="789100000024", nome="Suco", categoria=categoria, preco_custo=Decimal("4"), preco_venda=Decimal("9"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Cartão crédito", tipo="CREDITO")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish", "caixa": caixa.id, "cliente": "", "desconto": "0", "vencimento_financeiro": "",
                "pagamento_forma": [forma.id], "pagamento_valor": ["9.00"],
                "pagamento_status": ["CONFIRMADO"], "pagamento_transacao_externa_id": ["TEF-123"],
                "pagamento_nsu": [""], "pagamento_codigo_autorizacao": ["AUT123"],
            },
            follow=True,
        )

        self.assertContains(resposta, "NSU")
        self.assertEqual(Venda.objects.count(), 0)

    def test_pdv_finaliza_pagamento_eletronico_com_retorno_da_maquininha(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000022", nome="Leite", categoria=categoria, preco_custo=Decimal("4"), preco_venda=Decimal("7.50"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Cartão débito", tipo="DEBITO")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "2"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["15.00"],
                "pagamento_status": ["CONFIRMADO"],
                "pagamento_transacao_externa_id": ["TEF-SIM-123"],
                "pagamento_nsu": ["123456"],
                "pagamento_codigo_autorizacao": ["ABC123"],
                "pagamento_mensagem_processadora": ["Aprovado"],
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        venda = Venda.objects.get()
        pagamento = venda.pagamentos.get()
        self.assertEqual(pagamento.transacao_externa_id, "TEF-SIM-123")
        self.assertEqual(pagamento.codigo_autorizacao, "ABC123")

    def test_supervisor_confirma_estorno_eletronico_pendente(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000023", nome="Feijao", categoria=categoria, preco_custo=Decimal("6"), preco_venda=Decimal("12"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="PIX", tipo="PIX")
        venda = finalizar_venda(
            caixa=caixa,
            usuario=self.operador,
            itens=[{"produto": produto, "quantidade": Decimal("1.000")}],
            pagamentos=[
                {
                    "forma_pagamento": forma,
                    "valor": Decimal("12.00"),
                    "transacao_externa_id": "TEF-SIM-ESTORNO",
                    "nsu": "123456",
                    "codigo_autorizacao": "AUT123",
                }
            ],
        )
        cancelar_venda(venda=venda, usuario=self.admin, motivo="Cancelamento teste")
        pagamento = venda.pagamentos.get()
        self.client.force_login(self.operador)
        sem_permissao = self.client.get("/pdv/pagamentos/estornos-pendentes/diagnostico.json")
        self.assertEqual(sem_permissao.status_code, 403)
        tela_sem_permissao = self.client.get("/pdv/pagamentos/estornos-pendentes/")
        self.assertEqual(tela_sem_permissao.status_code, 403)

        self.client.force_login(self.admin)
        diagnostico_pendente = self.client.get("/pdv/pagamentos/estornos-pendentes/diagnostico.json")
        self.assertEqual(diagnostico_pendente.status_code, 200)
        payload_pendente = diagnostico_pendente.json()
        self.assertEqual(payload_pendente["contrato"], "payment_refund_readiness_v1")
        self.assertEqual(payload_pendente["status"], "attention_required")
        self.assertEqual(payload_pendente["resumo"]["pendentes"], 1)
        self.assertEqual(payload_pendente["resumo"]["valor_pendente"], "12.00")
        self.assertEqual(payload_pendente["estornos"][0]["pagamento_id"], pagamento.id)
        self.assertTrue(payload_pendente["estornos"][0]["confirmar_url"])

        tela_pendente = self.client.get("/pdv/pagamentos/estornos-pendentes/")
        self.assertEqual(tela_pendente.status_code, 200)
        self.assertContains(tela_pendente, "Estornos eletrônicos")
        self.assertContains(tela_pendente, "R$ 12.00")
        self.assertContains(tela_pendente, "TEF-SIM-ESTORNO")
        self.assertContains(tela_pendente, "Abrir venda")
        self.assertContains(tela_pendente, "keyboard-row")
        self.assertContains(tela_pendente, "data-open-url")
        self.assertContains(tela_pendente, 'event.key === "ArrowDown"')
        self.assertContains(tela_pendente, 'event.key === "Enter"')
        self.assertContains(tela_pendente, "refund-selected-form")
        self.assertContains(tela_pendente, "data-tef-refund-form")
        self.assertContains(tela_pendente, 'event.key === "F10"')
        self.assertContains(tela_pendente, 'event.ctrlKey && event.key === "Enter"')

        sem_evidencia = self.client.post(
            f"/pdv/pagamentos/{pagamento.id}/confirmar-estorno/",
            {
                "supervisor_usuario": self.admin.username,
                "supervisor_senha": "senha",
            },
            follow=True,
        )
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, StatusPagamento.ESTORNO_PENDENTE)
        self.assertContains(sem_evidencia, "Informe a autorização ou o retorno da adquirente")
        self.assertFalse(LancamentoFinanceiro.objects.filter(pagamento_venda=pagamento, origem="ESTORNO").exists())
        resposta = self.client.post(
            f"/pdv/pagamentos/{pagamento.id}/confirmar-estorno/",
            {
                "autorizacao": "EST987",
                "motivo": "Confirmado na operadora",
                "mensagem_processadora": "Estorno aprovado pelo simulador TEF do app desktop.",
                "supervisor_usuario": self.admin.username,
                "supervisor_senha": "senha",
                "next": "estornos_eletronicos",
            },
            follow=True,
        )

        pagamento.refresh_from_db()
        self.assertRedirects(resposta, "/pdv/pagamentos/estornos-pendentes/")
        self.assertEqual(pagamento.status, StatusPagamento.ESTORNADO)
        diagnostico_limpo = self.client.get("/pdv/pagamentos/estornos-pendentes/diagnostico.json").json()
        self.assertEqual(diagnostico_limpo["status"], "clear")
        self.assertEqual(diagnostico_limpo["resumo"]["pendentes"], 0)
        self.assertIn("EST987", pagamento.mensagem_processadora)
        self.assertIn("simulador TEF", pagamento.mensagem_processadora)
        self.assertTrue(LancamentoFinanceiro.objects.filter(pagamento_venda=pagamento, origem="ESTORNO").exists())
        self.assertContains(resposta, "Estorno eletrônico confirmado")

    def test_fila_confirma_estorno_eletronico_parcial_da_devolucao(self):
        categoria = Categoria.objects.create(nome="Bebidas estorno parcial")
        produto = Produto.objects.create(
            codigo_barras="789100009901",
            nome="Suco",
            categoria=categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("10.00"),
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10.000"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100.00"))
        dinheiro = FormaPagamento.objects.create(nome="Dinheiro parcial", tipo="DINHEIRO")
        pix = FormaPagamento.objects.create(nome="PIX parcial", tipo="PIX")
        venda = finalizar_venda(
            caixa=caixa,
            usuario=self.operador,
            itens=[{"produto": produto, "quantidade": Decimal("2.000")}],
            pagamentos=[
                {"forma_pagamento": dinheiro, "valor": Decimal("8.00")},
                {
                    "forma_pagamento": pix,
                    "valor": Decimal("12.00"),
                    "transacao_externa_id": "PIX-PARCIAL-ORIGINAL",
                    "nsu": "NSU-PARCIAL",
                },
            ],
        )
        devolucao = registrar_devolucao_venda(
            venda=venda,
            usuario=self.admin,
            itens=[{"item_venda": venda.itens.get(), "quantidade": Decimal("1.000")}],
            motivo="Devolução parcial teste",
            supervisor=self.admin,
        )
        estorno = EstornoParcialPagamento.objects.get(devolucao=devolucao)

        self.client.force_login(self.admin)
        diagnostico = self.client.get("/pdv/pagamentos/estornos-pendentes/diagnostico.json").json()
        self.assertEqual(diagnostico["resumo"]["pendentes"], 1)
        self.assertEqual(diagnostico["resumo"]["valor_pendente"], "6.00")
        self.assertEqual(diagnostico["estornos"][0]["tipo_estorno"], "PARCIAL")
        self.assertEqual(diagnostico["estornos"][0]["chave"], f"estorno-parcial-{estorno.id}")

        resposta = self.client.post(
            f"/pdv/pagamentos/estornos-parciais/{estorno.id}/confirmar/",
            {
                "autorizacao": "AUT-PARCIAL",
                "transacao_estorno_id": "REFUND-PARCIAL-1",
                "mensagem_processadora": "Aprovado pelo TEF.",
                "supervisor_usuario": self.admin.username,
                "supervisor_senha": "senha",
                "next": "estornos_eletronicos",
            },
            follow=True,
        )
        estorno.refresh_from_db()
        self.assertRedirects(resposta, "/pdv/pagamentos/estornos-pendentes/")
        self.assertEqual(estorno.status, StatusEstornoParcial.CONFIRMADO)
        self.assertEqual(estorno.transacao_estorno_id, "REFUND-PARCIAL-1")
        self.assertTrue(
            LancamentoFinanceiro.objects.filter(
                pagamento_venda=estorno.pagamento,
                origem="ESTORNO",
                valor=Decimal("6.00"),
            ).exists()
        )
    def test_terminal_sem_fiscal_automatico_finaliza_venda_sem_preparar_nfce(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(
            codigo_barras="789100000006",
            nome="Macarrao",
            categoria=categoria,
            preco_custo=Decimal("4"),
            preco_venda=Decimal("9"),
            ncm="19021900",
            origem_mercadoria="0",
            cst_icms="00",
            aliquota_icms=Decimal("18.00"),
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            inscricao_estadual="123456789",
            csc_id="1",
            csc_token="token",
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=1)
        NaturezaOperacao.objects.create(empresa=self.filial.empresa, descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa sem fiscal", emite_documento_fiscal=False)
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["9.00"],
            },
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertEqual(Venda.objects.count(), 1)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_pdv_exibe_fechamento_e_conferencia_no_modal_de_caixas(self):
        Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.operador,
            usuario_fechamento=self.operador,
            valor_inicial=Decimal("50"),
            valor_final=Decimal("80"),
            status=StatusCaixa.FECHADO,
        )
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Fechar caixa")
        self.assertContains(resposta, "<kbd>F5</kbd>", html=True)
        self.assertContains(resposta, "Suprimento")
        self.assertContains(resposta, "<kbd>F2</kbd>", html=True)
        self.assertContains(resposta, "Sangria")
        self.assertContains(resposta, "<kbd>F3</kbd>", html=True)
        self.assertContains(resposta, "Ctrl+Enter")
        self.assertContains(resposta, "Aguardando conferência")
        self.assertContains(resposta, "Conferir")

    def test_pdv_exibe_pagamento_eletronico_e_saida_superior_sem_menu_inferior_duplicado(self):
        FormaPagamento.objects.create(nome="Pix", tipo="PIX")
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<kbd>F3</kbd> Eletrônico", html=True)
        self.assertContains(resposta, "<kbd>F3</kbd> PIX", html=True)
        self.assertContains(resposta, "Adicionar forma")
        self.assertContains(resposta, "Shift +")
        self.assertContains(resposta, "Remover forma de pagamento (Del)")
        self.assertContains(resposta, "Remover item (Del)")
        self.assertContains(resposta, "Ctrl+Del")
        self.assertContains(resposta, "data-remove-url")
        self.assertContains(resposta, 'name="pagamento_transacao_externa_id"')
        self.assertContains(resposta, 'name="pagamento_codigo_autorizacao"')
        self.assertContains(resposta, "data-pdv-read-scale")
        self.assertContains(resposta, "<kbd>F12</kbd>", html=True)
        self.assertContains(resposta, "<kbd>Shift+S</kbd> Sair", count=1, html=True)
        self.assertNotContains(resposta, "<kbd>Shift+M</kbd> Menu", html=True)
        self.assertContains(resposta, "Navegador")

    def test_pdv_exibe_status_fiscal_do_terminal_identificado(self):
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa sem fiscal", emite_documento_fiscal=False)
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/", HTTP_X_TERMINAL_ID=str(terminal.identificador))

        self.assertContains(resposta, "Fiscal")
        self.assertContains(resposta, "Desligado")

    def test_sangria_registrada_pelo_pdv_retorna_ao_pdv(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            gaveta_automatica=True,
            abrir_gaveta_em_movimento_caixa=True,
        )
        self.client.force_login(self.operador)

        resposta = self.client.post(
            f"/pdv/caixas/{caixa.id}/sangria/",
            {
                "next": "pdv",
                "valor": "10.00",
                "motivo": "Retirada parcial",
                "supervisor_usuario": "admin",
                "supervisor_senha": "senha",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertContains(resposta, "pdv-cash-drawer-action")
        self.assertContains(resposta, "sangria")
        self.assertEqual(Sangria.objects.filter(caixa=caixa, valor=Decimal("10.00")).count(), 1)
        sangria = Sangria.objects.get(caixa=caixa)
        conta = ContaMovimentoFinanceiro.objects.get(filial=self.filial, nome="Caixa PDV", tipo=TipoContaMovimento.CAIXA)
        lancamento = LancamentoFinanceiro.objects.get(sangria=sangria)
        self.assertEqual(lancamento.conta, conta)
        self.assertEqual(lancamento.tipo, TipoLancamentoFinanceiro.SAIDA)
        self.assertEqual(lancamento.valor, Decimal("10.00"))

    def test_suprimento_registrado_pelo_pdv_entra_no_livro_financeiro(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            gaveta_automatica=True,
            abrir_gaveta_em_movimento_caixa=True,
        )
        self.client.force_login(self.operador)

        resposta = self.client.post(
            f"/pdv/caixas/{caixa.id}/suprimento/",
            {
                "next": "pdv",
                "valor": "25.00",
                "motivo": "Troco inicial extra",
                "supervisor_usuario": "admin",
                "supervisor_senha": "senha",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertContains(resposta, "pdv-cash-drawer-action")
        self.assertContains(resposta, "suprimento")
        suprimento = Suprimento.objects.get(caixa=caixa)
        conta = ContaMovimentoFinanceiro.objects.get(filial=self.filial, nome="Caixa PDV", tipo=TipoContaMovimento.CAIXA)
        lancamento = LancamentoFinanceiro.objects.get(suprimento=suprimento)
        self.assertEqual(lancamento.conta, conta)
        self.assertEqual(lancamento.tipo, TipoLancamentoFinanceiro.ENTRADA)
        self.assertEqual(lancamento.valor, Decimal("25.00"))

    def test_pdv_exibe_estorno_e_cancela_venda_com_supervisor(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000002", nome="Feijao", categoria=categoria, preco_custo=Decimal("7"), preco_venda=Decimal("12"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["12.00"],
            },
        )
        venda = Venda.objects.get()

        tela = self.client.get("/pdv/")
        self.assertContains(tela, "Estorno")
        self.assertContains(tela, f"Venda #{venda.id}")
        self.assertContains(tela, "Reimprimir")
        self.assertContains(tela, 'data-pdv-modal-paginated')
        self.assertContains(tela, 'data-page-size="4"')
        self.assertContains(tela, 'data-refund-command-panel')
        self.assertContains(tela, 'data-refund-open')
        self.assertContains(tela, 'data-refund-print')
        self.assertContains(tela, "Estornar venda")
        self.assertContains(tela, "F6")
        self.assertContains(tela, "Ctrl+Enter")
        self.assertContains(tela, f"/pdv/vendas/{venda.id}/impressao-desktop.json?reimpressao=1")

        resposta = self.client.post(
            f"/pdv/vendas/{venda.id}/cancelar/",
            {
                "next": "pdv",
                "motivo": "Cupom emitido incorreto",
                "supervisor_usuario": "admin",
                "supervisor_senha": "senha",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        venda.refresh_from_db()
        self.assertEqual(venda.status, StatusVenda.CANCELADA)

    def test_payload_de_impressao_desktop_da_venda_inclui_gaveta_opcional(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000003", nome="Cafe", categoria=categoria, preco_custo=Decimal("8"), preco_venda=Decimal("14.50"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            impressao_automatica=True,
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
        )
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "2"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["29.00"],
            },
        )
        venda = Venda.objects.get()

        response = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["venda"]["cliente"], "Cliente avulso")
        self.assertEqual(payload["venda"]["total_liquido"], "29.00")
        self.assertEqual(payload["itens"][0]["quantidade"], "2")
        self.assertEqual(payload["pagamentos"][0]["tipo"], "DINHEIRO")
        self.assertEqual(payload["impressao"]["impressora_padrao"], "EPSON TM-T20")
        self.assertTrue(payload["impressao"]["impressao_automatica"])
        self.assertTrue(payload["gaveta"]["abrir"])
        self.assertFalse(payload["gaveta"]["bloqueia_venda_se_indisponivel"])

        detalhe = self.client.get(f"/pdv/vendas/{venda.id}/")
        self.assertContains(detalhe, "Reimprimir cupom")
        self.assertContains(detalhe, f"/pdv/vendas/{venda.id}/impressao-desktop.json?reimpressao=1")

        reimpressao = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json?reimpressao=1").json()
        self.assertTrue(reimpressao["reimpressao"])
        self.assertEqual(reimpressao["operacao"], "reimpressao_cupom")
        self.assertFalse(reimpressao["gaveta"]["abrir"])
        self.assertTrue(LogAuditoria.objects.filter(acao="REIMPRESSAO_CUPOM", objeto_tipo="Venda", objeto_id=str(venda.id), usuario=self.operador).exists())

        self.client.get(f"/pdv/vendas/{venda.id}/recibo/?reimpressao=1")
        self.assertEqual(LogAuditoria.objects.filter(acao="REIMPRESSAO_CUPOM", objeto_id=str(venda.id)).count(), 2)

    def test_payload_desktop_prioriza_danfe_nfce_emitida_com_qrcode(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa,
            usuario=self.operador,
            status=StatusVenda.FINALIZADA,
            total_bruto=Decimal("25.90"),
            total_liquido=Decimal("25.90"),
        )
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_FISCAL,
            impressora_padrao="EPSON TM-T20",
        )
        chave = "35260712345678000190650010000001001123456780"
        qrcode_url = f"https://nfce.example.com/qrcode?p={chave}|3|2"
        xml = (
            '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<infNFe versao="4.00" Id="NFe{chave}" />'
            f'<infNFeSupl><qrCode>{qrcode_url}</qrCode></infNFeSupl>'
            '</NFe>'
        )
        documento = DocumentoFiscal.objects.create(
            filial=self.filial,
            venda=venda,
            usuario=self.operador,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            status=StatusDocumentoFiscal.EMITIDO,
            serie=1,
            numero=100,
            chave_acesso=chave,
            protocolo="135260000000001",
            valor_total=venda.total_liquido,
            xml_conteudo=xml,
        )
        self.client.force_login(self.operador)

        response = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json")
        fallback = self.client.get(f"/pdv/vendas/{venda.id}/recibo/")
        reimpressao = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json?reimpressao=1")

        payload = response.json()
        self.assertEqual(payload["tipo"], "danfe_nfce")
        self.assertEqual(payload["operacao"], "impressao_danfe_nfce")
        self.assertEqual(payload["impressao"]["impressora_padrao"], "EPSON TM-T20")
        self.assertEqual(payload["fiscal"]["documento_id"], documento.id)
        self.assertEqual(payload["fiscal"]["chave_acesso"], chave)
        self.assertEqual(payload["fiscal"]["qrcode_url"], qrcode_url)
        self.assertTrue(payload["impressao"]["documento_pronto"])
        self.assertEqual(fallback.status_code, 200)
        self.assertContains(fallback, "DOCUMENTO AUXILIAR DA NOTA FISCAL")
        self.assertContains(fallback, "data:image/png;base64,")
        self.assertEqual(reimpressao.json()["operacao"], "reimpressao_danfe_nfce")
        self.assertTrue(LogAuditoria.objects.filter(acao="REIMPRESSAO_DANFE_NFCE", objeto_id=str(venda.id)).exists())

    def test_recibo_e_payload_desktop_exibem_autorizacao_eletronica(self):
        categoria = Categoria.objects.create(nome="Bebidas")
        produto = Produto.objects.create(codigo_barras="789100000004", nome="Suco", categoria=categoria, preco_custo=Decimal("3"), preco_venda=Decimal("8.50"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="PIX dinamico", tipo="PIX")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["8.50"],
                "pagamento_status": ["CONFIRMADO"],
                "pagamento_transacao_externa_id": ["TEF-SIM-PIX-001"],
                "pagamento_nsu": ["998877"],
                "pagamento_codigo_autorizacao": ["PX1234"],
                "pagamento_mensagem_processadora": ["Pagamento aprovado pelo simulador TEF do app desktop."],
            },
        )
        venda = Venda.objects.get()
        pagamento = venda.pagamentos.get()

        recibo = self.client.get(f"/pdv/vendas/{venda.id}/recibo/")
        payload = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json").json()

        self.assertContains(recibo, f"NSU {pagamento.nsu}")
        self.assertContains(recibo, f"Aut. {pagamento.codigo_autorizacao}")
        self.assertContains(recibo, pagamento.transacao_externa_id)
        self.assertEqual(payload["pagamentos"][0]["tipo"], "PIX")
        self.assertEqual(payload["pagamentos"][0]["transacao_externa_id"], pagamento.transacao_externa_id)
        self.assertEqual(payload["pagamentos"][0]["nsu"], pagamento.nsu)
        self.assertEqual(payload["pagamentos"][0]["codigo_autorizacao"], pagamento.codigo_autorizacao)
        self.assertIn("simulador TEF do app desktop", payload["pagamentos"][0]["mensagem_processadora"])

class AcessoPdvNuvemEscopoEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(razao_social="Empresa PDV Um", nome_fantasia="Empresa PDV Um", cnpj="70123456000110")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz PDV Um")
        outra = Empresa.objects.create(razao_social="Empresa PDV Dois", nome_fantasia="Empresa PDV Dois", cnpj="80123456000110")
        outra_filial = Filial.objects.create(empresa=outra, nome="Matriz PDV Dois")
        self.admin = User.objects.create_user("admin_pdv_um", password="123")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        self.outro_operador = User.objects.create_user("operador_pdv_dois", password="123")
        PerfilUsuario.objects.create(usuario=self.outro_operador, filial=outra_filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        self.acesso_estrangeiro = AcessoPdvNuvem.objects.create(usuario=self.outro_operador, filial=outra_filial)
        for indice in range(51):
            operador = User.objects.create_user(f"operador_pdv_um_{indice}", password="123")
            PerfilUsuario.objects.create(usuario=operador, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
            AcessoPdvNuvem.objects.create(usuario=operador, filial=self.filial)

    def test_admin_ve_apenas_sua_empresa_com_cinquenta_por_pagina(self):
        self.client.force_login(self.admin)
        response = self.client.get("/pdv/acessos-nuvem/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pendentes"].paginator.count, 51)
        self.assertEqual(len(response.context["pendentes"]), 50)
        self.assertNotContains(response, "operador_pdv_dois")

    def test_admin_nao_decide_solicitacao_de_outra_empresa(self):
        self.client.force_login(self.admin)
        response = self.client.post(f"/pdv/acessos-nuvem/{self.acesso_estrangeiro.pk}/decidir/", {"acao": "aprovar"})
        self.assertEqual(response.status_code, 404)
        self.acesso_estrangeiro.refresh_from_db()
        self.assertEqual(self.acesso_estrangeiro.status, StatusAcessoPdvNuvem.PENDENTE)
@override_settings(PDV_NUVEM_REQUER_APROVACAO=False)
class PdvTelaEscopoEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(
            razao_social="Empresa Caixa Um",
            nome_fantasia="Empresa Caixa Um",
            cnpj="91123456000110",
        )
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz Caixa Um")
        outra_empresa = Empresa.objects.create(
            razao_social="Empresa Caixa Dois",
            nome_fantasia="Empresa Caixa Dois",
            cnpj="92123456000110",
        )
        self.outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Matriz Caixa Dois")
        self.operador = User.objects.create_user("operador_escopo_um", password="123")
        PerfilUsuario.objects.create(usuario=self.operador, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        self.colega = User.objects.create_user("colega_escopo_um", password="123")
        PerfilUsuario.objects.create(usuario=self.colega, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        self.estrangeiro = User.objects.create_user("operador_escopo_dois", password="123")
        PerfilUsuario.objects.create(usuario=self.estrangeiro, filial=self.outra_filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        self.caixa = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.operador,
            valor_inicial=Decimal("100"),
        )
        self.caixa_colega = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.colega,
            valor_inicial=Decimal("100"),
        )
        self.caixa_estrangeiro = Caixa.objects.create(
            filial=self.outra_filial,
            usuario_abertura=self.estrangeiro,
            valor_inicial=Decimal("100"),
        )
        self.venda = Venda.objects.create(
            filial=self.filial,
            caixa=self.caixa,
            usuario=self.operador,
            total_bruto=Decimal("10"),
            total_liquido=Decimal("10"),
            status=StatusVenda.FINALIZADA,
        )
        self.venda_estrangeira = Venda.objects.create(
            filial=self.outra_filial,
            caixa=self.caixa_estrangeiro,
            usuario=self.estrangeiro,
            total_bruto=Decimal("20"),
            total_liquido=Decimal("20"),
            status=StatusVenda.FINALIZADA,
        )
        self.terminal_estrangeiro = TerminalPdv.objects.create(
            filial=self.outra_filial,
            nome="Terminal estrangeiro",
            status_licenca=StatusLicencaTerminal.LIBERADA,
        )
        self.pre_venda = PreVenda.objects.create(
            filial=self.filial,
            usuario=self.operador,
            total_bruto=Decimal("10"),
            total_liquido=Decimal("10"),
        )
        self.pre_venda_estrangeira = PreVenda.objects.create(
            filial=self.outra_filial,
            usuario=self.estrangeiro,
            total_bruto=Decimal("20"),
            total_liquido=Decimal("20"),
        )

    def test_tela_pdv_isola_caixas_vendas_terminal_e_filial_por_empresa(self):
        self.client.force_login(self.operador)
        response = self.client.get(
            "/pdv/",
            HTTP_X_TERMINAL_ID=str(self.terminal_estrangeiro.identificador),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["caixa_aberto"], self.caixa)
        self.assertEqual(response.context["filial_visual"], self.filial)
        self.assertIsNone(response.context["terminal_requisicao"])
        self.assertIn(self.caixa, response.context["caixas_recentes"])
        self.assertIn(self.caixa_colega, response.context["caixas_recentes"])
        self.assertNotIn(self.caixa_estrangeiro, response.context["caixas_recentes"])
        self.assertIn(self.venda, response.context["vendas_recentes"])
        self.assertNotIn(self.venda_estrangeira, response.context["vendas_recentes"])

    def test_operador_nao_acessa_recibo_ou_payload_de_venda_de_outra_empresa(self):
        self.client.force_login(self.operador)

        recibo = self.client.get(f"/pdv/vendas/{self.venda_estrangeira.id}/recibo/")
        payload = self.client.get(f"/pdv/vendas/{self.venda_estrangeira.id}/impressao-desktop.json")

        self.assertEqual(recibo.status_code, 404)
        self.assertEqual(payload.status_code, 404)
    def test_listagens_nao_exibem_dav_ou_caixa_de_outra_empresa(self):
        self.client.force_login(self.operador)

        davs = self.client.get("/pdv/pre-vendas/")
        caixas = self.client.get("/pdv/caixas/")

        self.assertEqual(davs.status_code, 200)
        self.assertIn(self.pre_venda, davs.context["pre_vendas"])
        self.assertNotIn(self.pre_venda_estrangeira, davs.context["pre_vendas"])
        self.assertEqual(caixas.status_code, 200)
        self.assertIn(self.caixa, caixas.context["caixas"])
        self.assertNotIn(self.caixa_estrangeiro, caixas.context["caixas"])

    def test_operador_nao_acessa_objetos_de_outra_empresa_por_id(self):
        self.client.force_login(self.operador)
        urls = [
            f"/pdv/pre-vendas/{self.pre_venda_estrangeira.id}/",
            f"/pdv/pre-vendas/{self.pre_venda_estrangeira.id}/recibo/",
            f"/pdv/pre-vendas/{self.pre_venda_estrangeira.id}/carregar/",
            f"/pdv/pre-vendas/{self.pre_venda_estrangeira.id}/cancelar/",
            f"/pdv/vendas/{self.venda_estrangeira.id}/",
            f"/pdv/vendas/{self.venda_estrangeira.id}/devolver/",
            f"/pdv/vendas/{self.venda_estrangeira.id}/cancelar/",
            f"/pdv/caixas/{self.caixa_estrangeiro.id}/",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_operador_nao_movimenta_caixa_de_outra_empresa(self):
        self.client.force_login(self.operador)
        urls = [
            f"/pdv/caixas/{self.caixa_estrangeiro.id}/sangria/",
            f"/pdv/caixas/{self.caixa_estrangeiro.id}/suprimento/",
            f"/pdv/caixas/{self.caixa_estrangeiro.id}/fechar/",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_operador_finaliza_somente_no_proprio_caixa_aberto(self):
        self.client.force_login(self.operador)
        response = self.client.get("/pdv/")

        caixas = response.context["finish_form"].fields["caixa"].queryset
        self.assertIn(self.caixa, caixas)
        self.assertNotIn(self.caixa_colega, caixas)
        self.assertNotIn(self.caixa_estrangeiro, caixas)


    def test_pdv_converte_ean_de_caixa_em_unidades_base_no_carrinho(self):
        categoria = Categoria.objects.create(nome="Embalagens PDV")
        produto = Produto.objects.create(
            codigo_barras="7891234500001",
            nome="Leite em unidade",
            categoria=categoria,
            preco_venda=Decimal("5.00"),
        )
        CodigoBarrasProduto.objects.create(
            produto=produto,
            codigo="17891234500008",
            tipo="CAIXA",
            fator_conversao=Decimal("12.000"),
            permite_venda=True,
        )
        self.client.force_login(self.operador)

        response = self.client.post(
            "/pdv/",
            {"action": "add", "busca": "17891234500008", "quantidade": "2.000"},
        )

        self.assertRedirects(response, "/pdv/")
        self.assertEqual(self.client.session["pdv_cart"][str(produto.pk)], "24.000000")

    def test_consulta_preco_calcula_valor_da_apresentacao_adicional(self):
        categoria = Categoria.objects.create(nome="Consulta de embalagens")
        produto = Produto.objects.create(
            codigo_barras="7891234500002",
            nome="Cafe em unidade",
            categoria=categoria,
            preco_venda=Decimal("4.50"),
        )
        codigo = CodigoBarrasProduto.objects.create(
            produto=produto,
            codigo="17891234500015",
            tipo="FARDO",
            fator_conversao=Decimal("6.000"),
            permite_venda=True,
        )
        self.client.force_login(self.operador)

        response = self.client.get("/pdv/consulta-preco/", {"q": codigo.codigo})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["produto"], produto)
        self.assertEqual(response.context["apresentacao"], codigo)
        self.assertEqual(response.context["preco_atual"], Decimal("27.00000"))
        self.assertContains(response, "Fardo com")

@override_settings(PDV_NUVEM_REQUER_APROVACAO=False)
class PdvEntregaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(razao_social="Mercado Entrega", nome_fantasia="Mercado Entrega", cnpj="98765432000190")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")
        self.operador = User.objects.create_user(username="operador_entrega", password="senha")
        PerfilUsuario.objects.create(usuario=self.operador, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        categoria = Categoria.objects.create(nome="Mercearia entrega")
        self.produto = Produto.objects.create(
            codigo_barras="789100000999",
            nome="Arroz entrega",
            categoria=categoria,
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("15.00"),
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10"))

    def test_carrinho_pode_virar_pedido_para_entrega_sem_finalizar_venda(self):
        self.client.force_login(self.operador)
        session = self.client.session
        session["pdv_cart"] = {str(self.produto.id): "2"}
        session.save()

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "create_delivery",
                "cliente": "",
                "nome_cliente": "Ana da Entrega",
                "telefone": "(11) 99999-9999",
                "endereco_entrega": "Rua das Flores, 100",
                "observacoes": "Interfone 12",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/?delivery=1")
        self.assertContains(resposta, "Pedido de entrega #1 criado")
        pedido = PedidoOnline.objects.get()
        self.assertEqual(pedido.filial, self.filial)
        self.assertEqual(pedido.canal, CanalPedido.TELEFONE)
        self.assertEqual(pedido.tipo_entrega, TipoEntrega.ENTREGA)
        self.assertEqual(pedido.total, Decimal("30.00"))
        item = ItemPedidoOnline.objects.get(pedido=pedido)
        self.assertEqual(item.produto, self.produto)
        self.assertEqual(item.quantidade, Decimal("2"))
        self.assertEqual(item.quantidade_separada, Decimal("2"))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StatusPedido.PRONTO)
        self.assertTrue(pedido.estoque_reservado)
        self.assertEqual(self.client.session["pdv_cart"], {})
        self.assertEqual(Venda.objects.count(), 0)

    def test_entrega_reaproveita_cliente_salvo_e_preenche_dados_ausentes(self):
        cliente = Cliente.objects.create(
            empresa=self.filial.empresa,
            nome="Cliente cadastrado",
            telefone="62999991111",
            endereco="Rua Cadastrada, 20",
        )
        self.client.force_login(self.operador)
        session = self.client.session
        session["pdv_cart"] = {str(self.produto.id): "1"}
        session.save()

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "create_delivery",
                "cliente": cliente.pk,
                "nome_cliente": "Texto ignorado",
                "telefone": "",
                "endereco_entrega": "",
                "bairro_entrega": "",
                "observacoes": "",
            },
        )

        self.assertRedirects(resposta, "/pdv/?delivery=1")
        pedido = PedidoOnline.objects.get()
        self.assertEqual(pedido.cliente, cliente)
        self.assertEqual(pedido.nome_cliente, cliente.nome)
        self.assertEqual(pedido.telefone, cliente.telefone)
        self.assertEqual(pedido.endereco_entrega, cliente.endereco)

    def test_entrega_avulsa_pode_salvar_cliente_opcionalmente(self):
        self.client.force_login(self.operador)
        session = self.client.session
        session["pdv_cart"] = {str(self.produto.id): "1"}
        session.save()

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "create_delivery",
                "cliente": "",
                "nome_cliente": "Novo cliente da entrega",
                "telefone": "62988887777",
                "endereco_entrega": "Avenida Nova, 30",
                "bairro_entrega": "",
                "observacoes": "",
                "salvar_cliente": "on",
            },
        )

        self.assertRedirects(resposta, "/pdv/?delivery=1")
        cliente = Cliente.objects.get(nome="Novo cliente da entrega")
        pedido = PedidoOnline.objects.get()
        self.assertEqual(cliente.empresa, self.filial.empresa)
        self.assertEqual(pedido.cliente, cliente)

    def test_modal_de_entrega_oferece_busca_e_operacao_por_teclado(self):
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertContains(resposta, 'data-client-search-url="/clientes/busca.json"')
        self.assertContains(resposta, 'aria-autocomplete="list"')
        self.assertContains(resposta, "Salvar cliente para pr")
        self.assertContains(resposta, "Alt+S")
        self.assertContains(resposta, "Espaço")

    def test_entrega_do_pdv_calcula_frete_com_politica_da_filial(self):
        politica = PoliticaEntrega.objects.create(
            filial=self.filial,
            raio_maximo_km=Decimal("10.00"),
            valor_minimo_pedido=Decimal("0.00"),
            bairros_atendidos="Centro",
        )
        FaixaTaxaEntrega.objects.create(
            politica=politica,
            distancia_inicial_km=Decimal("0.00"),
            distancia_final_km=Decimal("10.00"),
            taxa=Decimal("6.50"),
        )
        self.client.force_login(self.operador)
        session = self.client.session
        session["pdv_cart"] = {str(self.produto.id): "2"}
        session.save()

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "create_delivery",
                "cliente": "",
                "nome_cliente": "Ana da Entrega",
                "telefone": "11999999999",
                "endereco_entrega": "Rua das Flores, 100",
                "bairro_entrega": "Centro",
                "distancia_entrega_km": "4.20",
                "observacoes": "",
            },
        )

        self.assertRedirects(resposta, "/pdv/?delivery=1")
        pedido = PedidoOnline.objects.get()
        self.assertEqual(pedido.bairro_entrega, "Centro")
        self.assertEqual(pedido.taxa_entrega, Decimal("6.50"))
        self.assertEqual(pedido.total, Decimal("36.50"))
        self.assertEqual(pedido.regra_entrega_aplicada, "Faixa de 0.00 a 10.00 km")

    def test_operador_abre_conferencia_da_entrega_pelo_pdv(self):
        pedido = PedidoOnline.objects.create(
            filial=self.filial,
            nome_cliente="Cliente entrega",
            telefone="11999999999",
            tipo_entrega=TipoEntrega.ENTREGA,
            canal=CanalPedido.TELEFONE,
            endereco_entrega="Rua das Flores, 100",
            usuario=self.operador,
        )
        ItemPedidoOnline.objects.create(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal("1"),
            preco_unitario=Decimal("15.00"),
        )
        pedido.recalcular()
        self.client.force_login(self.operador)

        resposta = self.client.get(f"/pedidos-online/{pedido.id}/?origem=pdv")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Voltar ao PDV")
        self.assertContains(resposta, "Cliente entrega")
        impressao = self.client.get(f"/pedidos-online/{pedido.id}/separacao/imprimir/")
        self.assertEqual(impressao.status_code, 200)
        self.assertContains(impressao, "Cliente entrega")

    def test_operador_confere_entrega_no_modal_do_pdv_sem_ir_ao_marketplace(self):
        pedido = PedidoOnline.objects.create(
            filial=self.filial,
            nome_cliente="Cliente do modal",
            telefone="11999999999",
            tipo_entrega=TipoEntrega.ENTREGA,
            canal=CanalPedido.TELEFONE,
            endereco_entrega="Rua do Modal, 10",
            usuario=self.operador,
        )
        ItemPedidoOnline.objects.create(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal("1"),
            preco_unitario=Decimal("15.00"),
        )
        pedido.recalcular()
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'id="pdv-modal-delivery-detail"')
        self.assertContains(resposta, f'data-delivery-id="{pedido.pk}"')
        self.assertContains(resposta, 'data-delivery-action="reserve"')
        self.assertContains(resposta, "/static/js/app.js")

        resposta = self.client.post(
            f"/pedidos-online/{pedido.pk}/acao/",
            {"origem_pdv": "1", "acao": "reservar"},
        )

        self.assertRedirects(resposta, f"/pdv/?delivery={pedido.pk}")
        pedido.refresh_from_db()

    def test_modal_entrega_indica_pagamento_ja_confirmado(self):
        pedido = PedidoOnline.objects.create(
            filial=self.filial, nome_cliente="Cliente pago", telefone="11999999999",
            tipo_entrega=TipoEntrega.ENTREGA, canal=CanalPedido.TELEFONE,
            endereco_entrega="Rua do Pagamento, 10", status=StatusPedido.SAIU_ENTREGA,
            status_pagamento=StatusPagamentoPedido.PAGO,
            forma_pagamento=FormaPagamentoPedido.PIX, valor_pago=Decimal("15.00"), usuario=self.operador,
        )
        ItemPedidoOnline.objects.create(pedido=pedido, produto=self.produto, quantidade=Decimal("1"), preco_unitario=Decimal("15.00"))
        pedido.recalcular()
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertContains(resposta, "Pagamento confirmado: PIX")
        self.assertContains(resposta, 'data-delivery-action="complete"')

    def test_pdv_exibe_atalho_de_entrega_quando_ha_itens_no_carrinho(self):
        self.client.force_login(self.operador)
        session = self.client.session
        session["pdv_cart"] = {str(self.produto.id): "1"}
        session.save()

        resposta = self.client.get("/pdv/")

        self.assertContains(resposta, 'data-pdv-modal-open="delivery"')
        self.assertContains(resposta, 'data-pdv-modal-open="deliveries"')
        self.assertContains(resposta, 'id="pdv-payment-delivery"')
        self.assertContains(resposta, "Entrega: pagar depois")
        self.assertContains(resposta, "Ctrl+E")
        self.assertContains(resposta, "Shift+E")
        self.assertContains(resposta, 'id="pdv-delivery-question"')

    def test_entrega_paga_no_caixa_fica_confirmada_no_pedido(self):
        caixa = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.operador,
            valor_inicial=Decimal("100.00"),
        )
        dinheiro = FormaPagamento.objects.create(nome="Dinheiro entrega", tipo="DINHEIRO", permite_troco=True)
        self.client.force_login(self.operador)
        session = self.client.session
        session["pdv_cart"] = {str(self.produto.id): "1"}
        session.save()

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "create_delivery",
                "pagamento_no_caixa": "1",
                "caixa": str(caixa.id),
                "pagamento_forma": str(dinheiro.id),
                "pagamento_valor": "15.00",
                "pagamento_status": "CONFIRMADO",
                "pagamento_transacao_externa_id": "",
                "pagamento_nsu": "",
                "pagamento_codigo_autorizacao": "",
                "pagamento_mensagem_processadora": "",
                "cliente": "",
                "nome_cliente": "Ana paga no caixa",
                "telefone": "11999999999",
                "endereco_entrega": "Rua das Flores, 100",
                "bairro_entrega": "",
                "observacoes": "",
            },
        )

        self.assertRedirects(resposta, "/pdv/?delivery=1")
        pedido = PedidoOnline.objects.get()
        self.assertEqual(pedido.status_pagamento, StatusPagamentoPedido.PAGO)
        self.assertEqual(pedido.forma_pagamento, FormaPagamentoPedido.DINHEIRO)
        self.assertEqual(pedido.valor_pago, Decimal("15.00"))
        self.assertIn("Caixa PDV", pedido.referencia_pagamento)
    def test_comanda_desktop_usa_impressora_de_pedido_separacao(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.PEDIDO_SEPARACAO,
            impressora_padrao="EPSON COMANDA",
            numero_vias=2,
            impressao_automatica=True,
        )
        pedido = PedidoOnline.objects.create(
            filial=self.filial,
            nome_cliente="Cliente da comanda",
            telefone="62999990000",
            tipo_entrega=TipoEntrega.ENTREGA,
            canal=CanalPedido.TELEFONE,
            endereco_entrega="Rua da Entrega, 10",
            status=StatusPedido.PRONTO,
            status_pagamento=StatusPagamentoPedido.PAGO,
            forma_pagamento=FormaPagamentoPedido.PIX,
            valor_pago=Decimal("15.00"),
            usuario=self.operador,
        )
        ItemPedidoOnline.objects.create(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal("1"),
            preco_unitario=Decimal("15.00"),
        )
        pedido.recalcular()
        self.client.force_login(self.operador)

        resposta = self.client.get(f"/pedidos-online/{pedido.id}/separacao/impressao-desktop.json")

        self.assertEqual(resposta.status_code, 200)
        payload = resposta.json()
        self.assertEqual(payload["tipo"], "comanda_entrega")
        self.assertEqual(payload["impressao"]["impressora_padrao"], "EPSON COMANDA")
        self.assertEqual(payload["impressao"]["numero_vias"], 2)
        self.assertEqual(payload["pedido"]["cliente"], "Cliente da comanda")
        self.assertEqual(payload["pedido"]["pagamento"], "Pago")
        self.assertEqual(payload["itens"][0]["produto"], self.produto.nome)
