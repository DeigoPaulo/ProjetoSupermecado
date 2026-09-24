from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .diagnostico_cbenef import (
    AUSENTE,
    CONCORDANTE,
    DIVERGENTE,
    INDEFINIDO,
    SEM_BENEFICIO_EXPLICITO,
    SEM_BENEFICIO_EXPLICITO_COM_LEGADO,
    SOMENTE_EXPLICITO,
    SOMENTE_LEGADO,
    classificar_confronto_cbenef,
    iterar_diagnostico_cbenef,
    paginar_diagnostico_cbenef,
)
from .models import (
    CodigoRegimeTributario,
    ConfiguracaoFiscal,
    NaturezaOperacao,
    ParametrizacaoBeneficioFiscalProduto,
    SituacaoBeneficioFiscalICMS,
    TipoDocumentoFiscal,
)


def decisao(situacao, codigo=""):
    return SimpleNamespace(situacao=situacao, codigo_beneficio_fiscal=codigo)


class ClassificacaoDiagnosticoCBenefTests(TestCase):
    def test_legado_igual_explicito(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                "GO123456", decisao(SituacaoBeneficioFiscalICMS.COM_BENEFICIO, "GO123456")
            ),
            CONCORDANTE,
        )

    def test_legado_diferente_explicito(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                "GO123456", decisao(SituacaoBeneficioFiscalICMS.COM_BENEFICIO, "GO654321")
            ),
            DIVERGENTE,
        )

    def test_legado_preenchido_e_decisao_sem_beneficio(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                "GO123456", decisao(SituacaoBeneficioFiscalICMS.SEM_BENEFICIO)
            ),
            SEM_BENEFICIO_EXPLICITO_COM_LEGADO,
        )

    def test_legado_vazio_e_decisao_com_beneficio(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                "", decisao(SituacaoBeneficioFiscalICMS.COM_BENEFICIO, "GO123456")
            ),
            SOMENTE_EXPLICITO,
        )

    def test_parametrizacao_indefinida(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                "GO123456", decisao(SituacaoBeneficioFiscalICMS.INDEFINIDO)
            ),
            INDEFINIDO,
        )

    def test_somente_legado(self):
        self.assertEqual(classificar_confronto_cbenef("GO123456", None), SOMENTE_LEGADO)

    def test_somente_explicito(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                None, decisao(SituacaoBeneficioFiscalICMS.COM_BENEFICIO, "GO123456")
            ),
            SOMENTE_EXPLICITO,
        )

    def test_ambos_ausentes(self):
        self.assertEqual(classificar_confronto_cbenef("", None), AUSENTE)

    def test_sem_beneficio_explicito_sem_legado_tem_estado_proprio(self):
        self.assertEqual(
            classificar_confronto_cbenef(
                "", decisao(SituacaoBeneficioFiscalICMS.SEM_BENEFICIO, "SEM CBENEF")
            ),
            SEM_BENEFICIO_EXPLICITO,
        )


class RelatorioDiagnosticoCBenefTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(
            razao_social="Empresa A Ltda",
            nome_fantasia="Empresa A",
            cnpj="11.111.111/0001-11",
        )
        cls.empresa_b = Empresa.objects.create(
            razao_social="Empresa B Ltda",
            nome_fantasia="Empresa B",
            cnpj="22.222.222/0001-22",
        )
        cls.filial_go_crt2 = Filial.objects.create(
            empresa=cls.empresa_a, nome="GO CRT 2", cnpj="11.111.111/0002-00", uf="GO"
        )
        cls.filial_go_crt3 = Filial.objects.create(
            empresa=cls.empresa_a, nome="GO CRT 3", cnpj="11.111.111/0003-00", uf="GO"
        )
        cls.filial_go_crt1 = Filial.objects.create(
            empresa=cls.empresa_a, nome="GO CRT 1", cnpj="11.111.111/0004-00", uf="GO"
        )
        cls.filial_go_crt4 = Filial.objects.create(
            empresa=cls.empresa_a, nome="GO CRT 4", cnpj="11.111.111/0005-00", uf="GO"
        )
        cls.filial_sp = Filial.objects.create(
            empresa=cls.empresa_a, nome="SP CRT 3", cnpj="11.111.111/0006-00", uf="SP"
        )
        cls.filial_b = Filial.objects.create(
            empresa=cls.empresa_b, nome="Filial B", cnpj="22.222.222/0002-00", uf="GO"
        )
        for filial, crt in [
            (cls.filial_go_crt2, CodigoRegimeTributario.SIMPLES_EXCESSO_SUBLIMITE),
            (cls.filial_go_crt3, CodigoRegimeTributario.REGIME_NORMAL),
            (cls.filial_go_crt1, CodigoRegimeTributario.SIMPLES_NACIONAL),
            (cls.filial_go_crt4, CodigoRegimeTributario.MEI),
            (cls.filial_sp, CodigoRegimeTributario.REGIME_NORMAL),
            (cls.filial_b, CodigoRegimeTributario.REGIME_NORMAL),
        ]:
            ConfiguracaoFiscal.objects.create(filial=filial, crt=crt)

        cls.natureza_a = NaturezaOperacao.objects.create(
            empresa=cls.empresa_a,
            descricao="Venda NFC-e A",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )
        cls.natureza_a_2 = NaturezaOperacao.objects.create(
            empresa=cls.empresa_a,
            descricao="Venda especial A",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )
        cls.natureza_b = NaturezaOperacao.objects.create(
            empresa=cls.empresa_b,
            descricao="Venda NFC-e B",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )
        cls.categoria = Categoria.objects.create(nome="Diagnóstico fiscal")
        cls.produto = Produto.objects.create(
            codigo_barras="7890000000001",
            nome="Produto diagnóstico",
            categoria=cls.categoria,
            preco_venda="10.00",
            codigo_beneficio_fiscal="GO123456",
        )
        User = get_user_model()
        cls.admin_a = User.objects.create_user("admin_cbenef_a", password="123")
        PerfilUsuario.objects.create(
            usuario=cls.admin_a,
            filial=cls.filial_go_crt3,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        cls.operador_a = User.objects.create_user("operador_cbenef_a", password="123")
        PerfilUsuario.objects.create(
            usuario=cls.operador_a,
            filial=cls.filial_go_crt3,
            tipo=TipoPerfil.OPERADOR_CAIXA,
        )
        cls.contador_a = User.objects.create_user("contador_cbenef_a", password="123")
        PerfilUsuario.objects.create(
            usuario=cls.contador_a,
            filial=cls.filial_go_crt3,
            tipo=TipoPerfil.CONTABILIDADE,
        )

    def linhas(self, **filtros):
        filtros.setdefault("q", self.produto.codigo_barras)
        filtros.setdefault("natureza", str(self.natureza_a.pk))
        return list(iterar_diagnostico_cbenef(self.admin_a, filtros))

    def criar_parametrizacao(self, natureza=None, situacao=SituacaoBeneficioFiscalICMS.COM_BENEFICIO, codigo="GO123456"):
        return ParametrizacaoBeneficioFiscalProduto.objects.create(
            produto=self.produto,
            natureza_operacao=natureza or self.natureza_a,
            situacao=situacao,
            codigo_beneficio_fiscal=codigo,
            atualizado_por=self.admin_a,
        )

    def test_multiplas_naturezas_geram_linhas_separadas_sem_duplicacao(self):
        linhas = self.linhas(filial=str(self.filial_go_crt3.pk), natureza="")
        self.assertEqual(len(linhas), 2)
        self.assertEqual(
            {linha.natureza.pk for linha in linhas},
            {self.natureza_a.pk, self.natureza_a_2.pk},
        )

    def test_consulta_em_lote_nao_cria_n_mais_um(self):
        for indice in range(10):
            Produto.objects.create(
                codigo_barras=f"789200000{indice:04d}",
                nome=f"Produto lote {indice:02d}",
                categoria=self.categoria,
                preco_venda="1.00",
            )
        with self.assertNumQueries(4):
            linhas = list(
                iterar_diagnostico_cbenef(
                    self.admin_a,
                    {"filial": self.filial_go_crt3.pk, "natureza": self.natureza_a.pk},
                )
            )
        self.assertEqual(len(linhas), 11)

    def test_go_crt2_caracteriza_fonte_explicita(self):
        linha = self.linhas(filial=str(self.filial_go_crt2.pk))[0]
        self.assertEqual(linha.uf, "GO")
        self.assertEqual(linha.crt, "2")
        self.assertIn("decisão explícita", linha.fonte_emissiva_atual)

    def test_go_crt3_caracteriza_fonte_explicita(self):
        linha = self.linhas(filial=str(self.filial_go_crt3.pk))[0]
        self.assertEqual(linha.crt, "3")
        self.assertIn("decisão explícita", linha.fonte_emissiva_atual)

    def test_go_crt1_e_crt4_caracterizam_fallback_legado(self):
        for filial, crt in [(self.filial_go_crt1, "1"), (self.filial_go_crt4, "4")]:
            with self.subTest(crt=crt):
                linha = self.linhas(filial=str(filial.pk))[0]
                self.assertEqual(linha.crt, crt)
                self.assertIn("campo legado", linha.fonte_emissiva_atual)

    def test_outra_uf_e_apenas_diagnostica(self):
        linha = self.linhas(filial=str(self.filial_sp.pk))[0]
        self.assertEqual(linha.uf, "SP")
        self.assertFalse(linha.perfil_estadual)
        self.assertIn("não valida a aplicabilidade fiscal", linha.observacao)

    def test_ausencia_de_perfil_estadual_e_explicita(self):
        linha = self.linhas(filial=str(self.filial_sp.pk))[0]
        self.assertIn("Recorte sem perfil fiscal estadual homologado", linha.observacao)

    def test_isolamento_entre_empresas(self):
        linhas = self.linhas()
        self.assertTrue(linhas)
        self.assertEqual({linha.empresa.pk for linha in linhas}, {self.empresa_a.pk})
        self.assertNotIn(self.natureza_b.pk, {linha.natureza.pk for linha in linhas})

    def test_usuario_sem_permissao_recebe_403(self):
        self.client.force_login(self.operador_a)
        resposta = self.client.get(reverse("fiscal:diagnostico_cbenef"))
        self.assertEqual(resposta.status_code, 403)

    def test_usuario_de_revisao_fiscal_e_autorizado(self):
        self.client.force_login(self.contador_a)
        resposta = self.client.get(reverse("fiscal:diagnostico_cbenef"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "cBenef legado")

    def test_relatorio_nao_altera_produto(self):
        antes = Produto.all_objects.values().get(pk=self.produto.pk)
        list(iterar_diagnostico_cbenef(self.admin_a, {"filial": self.filial_go_crt3.pk}))
        depois = Produto.all_objects.values().get(pk=self.produto.pk)
        self.assertEqual(depois, antes)

    def test_relatorio_nao_altera_parametrizacao(self):
        parametrizacao = self.criar_parametrizacao()
        antes = ParametrizacaoBeneficioFiscalProduto.objects.values().get(pk=parametrizacao.pk)
        list(iterar_diagnostico_cbenef(self.admin_a, {"filial": self.filial_go_crt3.pk}))
        depois = ParametrizacaoBeneficioFiscalProduto.objects.values().get(pk=parametrizacao.pk)
        self.assertEqual(depois, antes)

    def test_csv_nao_altera_banco_e_nao_parece_importacao(self):
        self.criar_parametrizacao()
        self.client.force_login(self.admin_a)
        antes_produto = Produto.all_objects.values().get(pk=self.produto.pk)
        antes_parametros = list(ParametrizacaoBeneficioFiscalProduto.objects.values())
        resposta = self.client.get(
            reverse("fiscal:diagnostico_cbenef_exportar_csv"),
            {"filial": self.filial_go_crt3.pk, "natureza": self.natureza_a.pk},
        )
        conteudo = b"".join(resposta.streaming_content).decode("utf-8")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("cbenef_legacy_explicit_diagnostic_v1", conteudo)
        self.assertNotIn("_modo_importacao", conteudo)
        self.assertEqual(Produto.all_objects.values().get(pk=self.produto.pk), antes_produto)
        self.assertEqual(list(ParametrizacaoBeneficioFiscalProduto.objects.values()), antes_parametros)

    def test_filtros_nao_misturam_empresas_ou_naturezas(self):
        linhas = list(
            iterar_diagnostico_cbenef(
                self.admin_a,
                {"filial": self.filial_go_crt3.pk, "natureza": self.natureza_b.pk},
            )
        )
        self.assertEqual(linhas, [])

    def test_paginacao_preserva_cardinalidade_sem_duplicacao(self):
        for indice in range(50):
            Produto.objects.create(
                codigo_barras=f"789100000{indice:04d}",
                nome=f"Produto página {indice:02d}",
                categoria=self.categoria,
                preco_venda="1.00",
            )
        pagina, _contagens = paginar_diagnostico_cbenef(
            self.admin_a,
            {"filial": self.filial_go_crt3.pk, "natureza": self.natureza_a.pk},
            2,
            50,
        )
        self.assertEqual(pagina.paginator.count, 51)
        self.assertEqual(len(pagina.object_list), 1)
        chaves = {
            (linha.produto.pk, linha.natureza.pk, linha.filial.pk)
            for linha in pagina.object_list
        }
        self.assertEqual(len(chaves), 1)

    def test_legado_go_em_outra_uf_nao_e_declarado_valido(self):
        linha = self.linhas(filial=str(self.filial_sp.pk))[0]
        self.assertEqual(linha.legado, "GO123456")
        self.assertIn("validade não é afirmada para SP", linha.observacao)

    def test_filtro_de_situacao_retorna_somente_classificacao_pedida(self):
        self.criar_parametrizacao(codigo="GO654321")
        linhas = self.linhas(
            filial=str(self.filial_go_crt3.pk),
            situacao=DIVERGENTE,
        )
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0].situacao, DIVERGENTE)
