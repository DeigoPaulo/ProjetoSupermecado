import hashlib
import io
import json
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial, ModoImplantacao
from apps.financeiro.models import ContaMovimentoFinanceiro, TipoContaMovimento
from apps.pdv.models import Caixa, CanalAtualizacaoPdv, EventoDispositivoTerminal, ModoIntegracaoTef, ProtocoloBalanca, ProvedorTef, StatusLicencaTerminal, TerminalPdv
from apps.vendas.models import FormaPagamento, FormaPagamentoFilial, PagamentoVenda, StatusPagamento, Venda

from .models import ConfiguracaoImpressao, ModeloEtiqueta, ModeloPapel, TipoDocumentoImpressao
from .services import configuracao_impressao_para, criar_configuracoes_padrao, estilos_impressao
from .templatetags.formatadores import quantidade_br
from .views import _classificar_dependencia_roadmap, _classificar_etapa_roadmap

def criar_artefato_pdv_teste(caminho, conteudo, versao=None, assinado=False):
    versao = versao or settings.PDV_DESKTOP_VERSION
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


def criar_pacote_servidor_teste(
    caminho,
    conteudo,
    versao=None,
    commit_assinado=True,
    contem_dados_cliente=False,
    arquivos_extras=None,
):
    versao = versao or settings.LOCAL_SERVER_VERSION
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("manage.py", "# pacote de teste")
        pacote.writestr("requirements.txt", "Django")
        pacote.writestr("config/settings.py", "SECRET_KEY = 'runtime'")
        pacote.writestr("apps/core.py", conteudo)
        for nome, dados in (arquivos_extras or {}).items():
            pacote.writestr(nome, dados)
    conteudo_pacote = buffer.getvalue()
    caminho.write_bytes(conteudo_pacote)
    metadados = {
        "contrato": "local_server_package_v1",
        "versao": versao,
        "commit": "a" * 40,
        "commit_assinado_exigido": commit_assinado,
        "arquivo": caminho.name,
        "tamanho_bytes": len(conteudo_pacote),
        "sha256": hashlib.sha256(conteudo_pacote).hexdigest(),
        "contem_dados_cliente": contem_dados_cliente,
    }
    caminho.with_suffix(".manifest.json").write_text(json.dumps(metadados), encoding="utf-8")
    return conteudo_pacote

class FormatadoresTemplateTests(SimpleTestCase):
    def test_quantidade_br_remove_zeros_de_unidade_e_mantem_fracao_brasileira(self):
        self.assertEqual(quantidade_br("20.000"), "20")
        self.assertEqual(quantidade_br("1.000"), "1")
        self.assertEqual(quantidade_br("1.250"), "1,250")

class ClassificadorRoadmapTests(SimpleTestCase):
    def test_credenciais_smtp_nao_sao_confundidas_com_adquirente_rede(self):
        resultado = _classificar_etapa_roadmap(
            "Escopo original",
            "Recuperação de senha",
            "Credenciais SMTP, SPF, DKIM e DMARC pendentes de homologação.",
        )

        self.assertEqual(resultado["trilha"], "Integrações")

    def test_rede_como_marca_de_pagamento_permanece_na_trilha_tef(self):
        resultado = _classificar_etapa_roadmap(
            "Pagamentos",
            "Integração de cartões",
            "Conectar a Rede para processar cartões.",
        )

        self.assertEqual(resultado["trilha"], "Hardware/TEF")

    def test_titulo_financeiro_tem_precedencia_sobre_citacao_fiscal(self):
        resultado = _classificar_etapa_roadmap(
            "Próximas fases",
            "Financeiro completo",
            "Falta integração final com fiscal e contabilidade.",
        )

        self.assertEqual(resultado["trilha"], "Financeiro")

    def test_titulo_marketplace_tem_precedencia_sobre_nota_fiscal(self):
        resultado = _classificar_etapa_roadmap(
            "Próximas fases",
            "Marketplace / pedido online",
            "O pedido permite preparar NF-e modelo 55.",
        )

        self.assertEqual(resultado["trilha"], "Integrações")


    def test_hardware_real_fica_como_homologacao_externa(self):
        resultado = _classificar_dependencia_roadmap(
            "Balança integrada no PDV",
            "Falta conectar a balança física e homologar precisão no equipamento real.",
        )

        self.assertEqual(resultado["codigo"], "externo")
        self.assertEqual(resultado["dependencia"], "Homologação externa")

    def test_homologacao_de_parceiro_marketplace_fica_como_externa(self):
        resultado = _classificar_dependencia_roadmap(
            "Homologação de parceiros marketplace",
            "Falta escolher parceiros, obter credenciais de sandbox e homologar os drivers reais.",
        )

        self.assertEqual(resultado["codigo"], "externo")
        self.assertEqual(resultado["dependencia"], "Homologação externa")

    def test_relatorio_oficial_fica_como_desenvolvimento_interno(self):
        resultado = _classificar_dependencia_roadmap(
            "Financeiro completo",
            "A próxima evolução inclui implementar relatórios oficiais como SPED, ECD e ECF.",
        )

        self.assertEqual(resultado["codigo"], "interno")
        self.assertEqual(resultado["dependencia"], "Desenvolvimento interno")

class ConfiguracoesOperacionaisTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Supermercado Modelo Ltda",
            nome_fantasia="Supermercado Modelo",
            cnpj="22.222.222/0001-22",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)

    def test_cria_configuracoes_padrao_e_resolve_por_filial(self):
        criadas = criar_configuracoes_padrao()

        self.assertGreater(criadas, 0)
        config = configuracao_impressao_para(self.filial, TipoDocumentoImpressao.CUPOM_NAO_FISCAL)
        self.assertIsNotNone(config)
        self.assertEqual(config.modelo_papel, ModeloPapel.BOBINA_80)
        self.assertIsNotNone(configuracao_impressao_para(self.filial, TipoDocumentoImpressao.CUPOM_FISCAL))
        estilo = estilos_impressao(config)
        self.assertEqual(estilo["largura"], "80mm")
        self.assertIn("mm", estilo["margem_css"])

    def test_tela_impressoes_e_backup_operacional(self):
        criar_configuracoes_padrao()

        impressoes = self.client.get("/configuracoes/impressoes/")
        backup_pagina = self.client.get("/configuracoes/backup/")
        backup = self.client.get("/configuracoes/backup/download/")
        checklist = self.client.get("/configuracoes/checklist/")

        self.assertEqual(impressoes.status_code, 200)
        self.assertContains(impressoes, "Central de impressão")
        self.assertContains(impressoes, "Cupom fiscal")
        self.assertContains(impressoes, "Com gaveta")
        self.assertContains(impressoes, "Sem impressora")
        self.assertContains(impressoes, "Descoberta local preparada para o app desktop")
        self.assertContains(impressoes, "Ver ponto de integração")
        self.assertContains(impressoes, "Configurações do desktop")
        self.assertContains(backup_pagina, "BACKUP_ENCRYPTION_PASSPHRASE")
        self.assertContains(backup_pagina, "-ValidarSomente")
        self.assertContains(backup_pagina, "LOCAL_BACKUP_DIR")
        self.assertContains(backup_pagina, "SYSTEM")
        self.assertContains(backup_pagina, ".zip.aes")
        self.assertContains(backup_pagina, "-RemoverOriginalCriptografado")
        self.assertEqual(backup.status_code, 200)
        self.assertEqual(backup["Content-Type"], "application/json; charset=utf-8")
        self.assertTrue(backup.content.startswith(b"["))
        self.assertContains(checklist, "Testes automatizados")
        self.assertContains(checklist, "verificar_prontidao_licenciamento")
        self.assertContains(checklist, "Avan")
        self.assertContains(checklist, "ponderado")
        self.assertRegex(checklist.content.decode("utf-8"), r"[0-9]+%</strong>\s*<span>[^<]*ponderado")
        self.assertContains(checklist, "O percentual conclu")
        self.assertContains(checklist, "Próximas etapas")
        self.assertContains(checklist, "Recorte automático dos itens em andamento")
        self.assertContains(checklist, "Mapa do roadmap")
        self.assertContains(checklist, "Concentração dos itens em andamento")
        self.assertContains(checklist, "Implantação")
        self.assertContains(checklist, "Hardware/TEF")
        self.assertContains(checklist, "Dispositivos")
        self.assertContains(checklist, "alta prioridade")
        self.assertContains(checklist, "Alta")
        self.assertContains(checklist, "M" + "\u00e9" + "dia")
        self.assertContains(checklist, "Fechar pacote instalável")
        self.assertContains(checklist, "Buscar no checklist")
        self.assertContains(checklist, "Todos os status")
        self.assertContains(checklist, "Todos os grupos")
        self.assertContains(checklist, "Todas as trilhas")
        self.assertContains(checklist, "Todas as prioridades")
        self.assertContains(checklist, "Todas as dependências")
        self.assertContains(checklist, "Trabalho interno")
        self.assertContains(checklist, "Homologações externas")
        self.assertContains(checklist, "Desenvolvimento interno")
        self.assertContains(checklist, "Documentos de referência")
        self.assertNotContains(checklist, "documenta" + "\u00c3")
        self.assertContains(checklist, "Excel/CSV")
        self.assertContains(checklist, "Arquitetura PDV desktop local")
        self.assertContains(checklist, "Padrão R$ em todos os formulários")
        self.assertContains(checklist, "Campos numéricos de preço")
        self.assertContains(checklist, "Entradas, saídas e livro contábil")
        self.assertContains(checklist, "livro financeiro imutável")
        self.assertContains(checklist, "Contas de movimento por filial")
        self.assertContains(checklist, "vendas à vista do PDV geram entradas automáticas")
        self.assertContains(checklist, "sangria e suprimento geram saída/entrada automática")
        self.assertContains(checklist, "transferências entre contas")
        self.assertContains(checklist, "estornos por lançamento inverso")
        self.assertContains(checklist, "relatório de receitas, despesas e resultado")
        self.assertContains(checklist, "Gaveta de dinheiro opcional")
        self.assertContains(checklist, "Balança integrada no PDV")
        self.assertContains(checklist, "produto pesável")
        self.assertContains(checklist, "configurar balança por caixa")
        self.assertContains(checklist, "bootstrap do app desktop entregam essa configuração")
        self.assertContains(checklist, "contrato pdv_scale_v1")
        self.assertContains(checklist, "driver genérico real")
        self.assertContains(checklist, "Serial RS-232/USB via pyserial")
        self.assertContains(checklist, "rejeição de peso instável")
        self.assertContains(checklist, "validar parâmetros e comandos do fabricante escolhido")
        self.assertContains(checklist, "fallback manual")
        self.assertContains(checklist, "ponte local para expor a configuração da balanca")
        self.assertContains(checklist, "peso simulado para homologação")
        self.assertContains(checklist, "botão Peso e atalho F12")
        self.assertContains(checklist, "devices.log.jsonl")
        self.assertContains(checklist, "pdv_device_event_queue_v1")
        self.assertContains(checklist, "lotes são enviados do mais antigo ao mais novo")
        self.assertContains(checklist, "compactação atômica remove somente registros já confirmados")
        self.assertContains(checklist, "thread exclusiva sincroniza periodicamente")
        self.assertContains(checklist, "sem depender de reiniciar o caixa")
        self.assertContains(checklist, "ponte deviceLogs")
        self.assertContains(checklist, "leitura visual desse diagnóstico")
        self.assertContains(checklist, "endpoint autenticado por terminal")
        self.assertContains(checklist, "EventoDispositivoTerminal")
        self.assertContains(checklist, "eventos ainda não sincronizados")
        self.assertContains(checklist, "ler peso automaticamente no PDV")
        self.assertContains(checklist, "Central de impressão permite")
        self.assertContains(checklist, "consulta as impressoras instaladas no Windows")
        self.assertContains(checklist, "nome, porta, driver, estado e impressora padrão")
        self.assertContains(checklist, "envia diretamente ao spooler Windows em RAW/ESC-POS")
        self.assertContains(checklist, "sem abrir pré-visualização")
        self.assertContains(checklist, "PIX dinâmico")
        self.assertContains(checklist, "Desconto supervisionado no PDV")
        self.assertContains(checklist, "log de auditoria")
        self.assertContains(checklist, "camada de tela cheia informa CAIXA LIVRE")
        self.assertContains(checklist, "checkPayment")
        self.assertContains(checklist, "mera geração do QR como pagamento")
        self.assertContains(checklist, "somente após pagamento confirmado")
        self.assertContains(checklist, "tenta preparar a NFC-e automaticamente")
        self.assertContains(checklist, "desativar essa tentativa por terminal PDV")
        self.assertContains(checklist, "PDV exibe no topo")
        self.assertContains(checklist, "ultima tentativa automática auditada")
        self.assertContains(checklist, "retomada explícita somente das consultas")
        self.assertContains(checklist, "Núcleo fiscal NFC-e e NF-e")
        self.assertContains(checklist, "Homologação fiscal em produção")
        self.assertContains(checklist, "Aplicativo desktop/PDF")
        self.assertContains(checklist, "Marketplace / pedido online")
        self.assertContains(checklist, "Homologação de parceiros marketplace")
        self.assertContains(checklist, "77% finalizado")
        self.assertEqual(checklist.context["resumo"]["concluidos"], 77)
        self.assertEqual(checklist.context["resumo"]["total"], 100)
        self.assertEqual(checklist.context["resumo"]["percentual"], 77)
        self.assertContains(checklist, "pendencia fica auditada")
        self.assertContains(checklist, "Transmissao simulada em homologação")
        self.assertContains(checklist, "fiscal_production_readiness_v1")
        self.assertContains(checklist, "transmissão SEFAZ real")
        self.assertContains(checklist, "simulador TEF rastreável")
        self.assertContains(checklist, "contrato único de adaptadores")
        self.assertContains(checklist, "simulador deixou de ser implícito")
        self.assertContains(checklist, "sem driver instalado falha de forma segura")
        self.assertContains(checklist, "provedor TEF e modo de integração por adaptador")
        self.assertContains(checklist, "pdv_tef_v1")
        self.assertContains(checklist, "bootstrap local autorizado com validade padrão de 24 horas")
        self.assertContains(checklist, "pdv_local_secret_v1")
        self.assertContains(checklist, "DPAPI vinculado ao usuário do Windows")
        self.assertContains(checklist, "parâmetros sensíveis do adaptador TEF")
        self.assertContains(checklist, "restaura os valores somente em memória")
        self.assertContains(checklist, "migra automaticamente instalações legadas")
        self.assertContains(checklist, "pdv_single_instance_v1")
        self.assertContains(checklist, "impedir duas janelas do mesmo caixa")
        self.assertContains(checklist, "reconfiguração também reserva primeiro a identidade atual")
        self.assertContains(checklist, "bloqueia venda, pagamento e estoque")
        self.assertContains(checklist, "F5/Enter")
        self.assertContains(checklist, "cache vencido ou terminal recusado permanece bloqueado")
        self.assertContains(checklist, "ponte processPayment")
        self.assertContains(checklist, "aguarda resposta da maquininha")
        self.assertContains(checklist, "terminal sem TEF configurado retorna aviso")
        self.assertContains(checklist, "eventos locais tef em devices.log.jsonl")
        self.assertContains(checklist, "chave idempotente por tentativa")
        self.assertContains(checklist, "reutiliza a autorização ou estorno já aprovado")
        self.assertContains(checklist, "confirmar o estorno eletrônico aprovado pela operadora")
        self.assertContains(checklist, "processa diretamente a parcela selecionada")
        self.assertContains(checklist, "aguarda a resposta da maquininha")
        self.assertContains(checklist, "exige evidência informada da adquirente")
        self.assertContains(checklist, "pdv_cash_drawer_v1")
        self.assertContains(checklist, "ponte openCashDrawer")
        self.assertContains(checklist, "registra diagnóstico local da gaveta")
        self.assertContains(checklist, "somente depois da operação ser aceita pelo servidor")
        self.assertContains(checklist, "Arquitetura PDV desktop local")
        self.assertContains(checklist, "fiel ao layout, atalhos e fluxo de venda do PDV web")
        self.assertContains(checklist, "bootstrap diário devolve a configuração vigente")
        self.assertContains(checklist, "autorização do admin master")
        self.assertContains(checklist, "licenca comercial cobrada por terminal")
        self.assertContains(checklist, "sem telas administrativas completas")
        self.assertContains(checklist, "Sincronização loja-nuvem")
        self.assertContains(checklist, "Empresa escolhe entre servidor local")
        self.assertContains(checklist, "Modo local administrativo")
        self.assertContains(checklist, "instalação local do servidor administrativo")
        self.assertContains(checklist, "PDV desktop continua separado e restrito ao operador")
        self.assertContains(checklist, "scripts/register_sync_task.ps1")
        self.assertContains(checklist, "BACKUP_ENCRYPTION_PASSPHRASE")
        self.assertContains(checklist, "-RemoverOriginalCriptografado")
        self.assertContains(checklist, "dados de pagamento eletrônico")
        self.assertContains(checklist, "nem conseguem inicializar o bootstrap")
        self.assertContains(checklist, "Eventos recebidos ficam armazenados")
        self.assertContains(checklist, "Caixa de saída, processador HTTP")
        self.assertContains(checklist, "retentativa exponencial")
        self.assertContains(checklist, "caixa de entrada autenticada")
        self.assertContains(checklist, "processador interno com handlers por tipo")
        self.assertContains(checklist, "handler inicial de produtos")
        self.assertContains(checklist, "handler de saldo de estoque por filial")
        self.assertContains(checklist, "rascunho sem movimentar estoque")
        self.assertContains(checklist, "baixa direta da conta vinculada")
        self.assertContains(checklist, "rastreio financeiro da baixa")
        self.assertContains(checklist, "impressão/PDF individual auditável")
        self.assertContains(checklist, "rastreio financeiro do livro")
        self.assertContains(checklist, "situação financeira da entrada")
        self.assertContains(checklist, "retorno seguro do detalhe e da edição de rascunho")
        self.assertContains(checklist, "situação financeira aberta, paga, cancelada, vencida ou sem conta")
        self.assertContains(checklist, "exportacao Excel/CSV e impressão/PDF da visão operacional filtrada")
        self.assertContains(checklist, "limpeza rapida de filtros ativos")
        self.assertContains(checklist, "chips visuais dos filtros aplicados")
        self.assertContains(checklist, "cards de resumo financeiro")
        self.assertContains(checklist, "atalho para filtro")
        self.assertContains(checklist, "preservando busca e status atuais")
        self.assertContains(checklist, "rastreio no estoque da entrada")
        self.assertContains(checklist, "movimentações de entrada e cancelamento")
        self.assertContains(checklist, "cancelamento protegido de compra finalizada")
        self.assertContains(checklist, "bloqueio quando a conta já foi paga")
        self.assertContains(checklist, "não existir saldo para reverter")
        self.assertContains(checklist, "aviso antecipado desses bloqueios")
        self.assertContains(checklist, "espelho de venda finalizada com painel")
        self.assertContains(checklist, "espelho fiscal sincronizado")
        self.assertContains(checklist, "detalhe auditável de eventos")
        self.assertContains(checklist, "resolução manual de conflitos")
        self.assertContains(checklist, "exportação CSV das filas")
        self.assertContains(checklist, "diagnóstico JSON operacional")
        self.assertContains(checklist, "próximos eventos")
        self.assertContains(checklist, "empresas por modo")
        self.assertContains(checklist, "comando único agendável")
        self.assertContains(checklist, "roteiro do Agendador de Tarefas")
        self.assertContains(checklist, "scripts/register_sync_task.ps1")
        self.assertContains(checklist, "Super admin personalizado")
        self.assertContains(checklist, "saúde da sincronização")
        self.assertContains(checklist, "Etiquetas de gôndola profissionais")
        self.assertContains(checklist, "documento complementar de etiquetas")
        self.assertContains(checklist, "compacto 110x30 mm")
        self.assertContains(checklist, "completo 100x50 mm")
        self.assertContains(checklist, "sem fundo colorido forçado")
        self.assertContains(checklist, "Etiquetas e impressoras profissionais")
        self.assertContains(checklist, "Modelo compacto 110x30")
        self.assertContains(checklist, "Busca por código de barras nas etiquetas")
        self.assertContains(checklist, "Impressão em medidas reais")
        self.assertContains(checklist, "ZPL, EPL, PPLA e PPLB")
        self.assertContains(checklist, "ZPL, EPL, PPLA ou PPLB")
        self.assertContains(checklist, "homologação por modelo")
        self.assertContains(checklist, "etiqueta de teste por modelo")
        self.assertContains(checklist, "limita 500 produtos, 100 cópias por produto e 2.000 etiquetas por lote")
        self.assertContains(checklist, "diagnóstico local de sucesso ou falha")
        self.assertContains(checklist, "quantidade de produtos e cópias efetivamente enviada")
        self.assertContains(checklist, "teste de modelo usa a mesma ponte local")
        self.assertContains(checklist, "Complementar desmembramento e fracionamento de produtos")
        self.assertContains(checklist, "Desmembramento e fracionamento de produtos")
        self.assertContains(checklist, "models DesmembramentoProduto, ItemDesmembramentoProduto e ReceitaDesmembramento")
        self.assertContains(checklist, "receitas/conversões por empresa/filial")
        self.assertContains(checklist, "simulação antes de confirmar")
        self.assertContains(checklist, "O serviço transacional faz baixa da origem")
        self.assertContains(checklist, "As telas de lista, detalhe e receitas exibem quantidades no padrão brasileiro")
        self.assertContains(checklist, "quantidade_br")
        self.assertContains(checklist, "busca remota por código de barras")
        self.assertContains(checklist, "SKU e nome")
        self.assertContains(checklist, "custo proporcional")
        self.assertContains(checklist, "cancelamento seguro com movimentos inversos")
        self.assertContains(checklist, "relatórios/CSV gerenciais")
        self.assertContains(checklist, "fluxos reais de açougue")
        self.assertContains(checklist, "Consulta de CNPJ e CEP")
        self.assertContains(checklist, "CADASTRO_CNPJ_PROVIDER_URL")
        self.assertContains(checklist, "CADASTRO_CEP_PROVIDER_URL")
        self.assertContains(checklist, "verificar_prontidao_consulta_cadastro")
        self.assertContains(checklist, "docs/CONSULTA_CNPJ_CEP.md")
        self.assertContains(checklist, "fallback local/offline")
        self.assertContains(checklist, "diagnóstico JSON")
        self.assertContains(checklist, "Pol" + "\u00ed" + "ticas de entrega por filial")
        self.assertContains(checklist, "delivery_geocode_v1")
        self.assertContains(checklist, "MARKETPLACE_GEOCODING_PROVIDER_URL")
        self.assertContains(checklist, "fallback manual de distancia")
        self.assertContains(checklist, "delivery_policy_v1")
        self.assertContains(checklist, "marketplace_partner_v1")
        self.assertContains(checklist, "Escopo original a decidir")
        self.assertContains(checklist, "Recuperação de senha")
        self.assertContains(checklist, "Cotação e pedido de compra")
        self.assertContains(checklist, "Importação de XML de entrada")
        self.assertContains(checklist, "Estoque geral por lote, validade e custo histórico")
        self.assertContains(checklist, "link temporário de uso único")
        self.assertContains(checklist, "password_reset_readiness_v1")
        self.assertContains(checklist, "verificar_prontidao_recuperacao_senha")
        self.assertContains(checklist, "docs/RECUPERACAO_SENHA_SMTP.md")
        self.assertContains(checklist, "homologar entrega e recuperação ponta a ponta")
        self.assertContains(checklist, "gera pedido em rascunho")
        self.assertContains(checklist, "conversão única em entrada vinculada")
        self.assertContains(checklist, "sem estoque ou financeiro")
        self.assertContains(checklist, "reabre o pedido")
        self.assertContains(checklist, "propostas únicas por fornecedor")
        self.assertContains(checklist, "comparação de totais e prazos")
        self.assertContains(checklist, "seleção auditada da proposta")
        self.assertContains(checklist, "NF-e autorizada")
        self.assertContains(checklist, "bloqueio de DTD/entidades")
        self.assertContains(checklist, "associa todos os produtos por GTIN")
        self.assertContains(checklist, "entrada em rascunho auditada")
        self.assertContains(checklist, "separa total dos produtos do total fiscal")
        self.assertContains(checklist, "saldo agregado")
        self.assertContains(checklist, "consomem as camadas por FEFO")
        self.assertContains(checklist, "itens a vencer em 30 dias")
        self.assertContains(checklist, "estoque legado sem lote continua utilizável")
        self.assertContains(checklist, "atribuir saldo histórico a lotes")
        self.assertContains(checklist, "reduções de inventário ajustam camadas")
        self.assertContains(checklist, "aumentos permanecem sem lote")
        self.assertContains(checklist, "Produção e desmembramento consomem lotes")
        self.assertContains(checklist, "cancelamentos restauram as alocações originais")
        self.assertContains(checklist, "política de lote obrigatório por produto")
        self.assertContains(checklist, "vem desativada")
        self.assertContains(checklist, "NF-e sem rastro")
        self.assertContains(checklist, "Progresso finalizado")
        self.assertContains(checklist, "Diferença em andamento")
        self.assertContains(checklist, "Impacto estimado")
        self.assertIn("diferenca_ponderada", checklist.context["resumo"])
        self.assertEqual(checklist.context["resumo"]["pendentes"], 0)

    def test_checklist_filtra_por_status_grupo_e_busca(self):
        response = self.client.get(
            "/configuracoes/checklist/",
            {"status": "partial", "grupo": "PDV e caixa", "q": "balanca", "trilha": "Dispositivos", "prioridade": "Média", "dependencia": "externo"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "item(ns) encontrado(s)")
        self.assertContains(response, "Balança integrada no PDV")
        self.assertContains(response, "ler peso automaticamente no PDV")
        self.assertContains(response, "Dispositivos")
        self.assertContains(response, "Média")
        self.assertNotContains(response, "Tela PDV em layout de operador")
        self.assertNotContains(response, "TEF/API de maquininha")

        csv_response = self.client.get(
            "/configuracoes/checklist/exportar.csv",
            {"status": "partial", "grupo": "PDV e caixa", "q": "balanca", "trilha": "Dispositivos", "prioridade": "Média", "dependencia": "externo"},
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv; charset=utf-8")
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Grupo;Item;Status;Dependência;Trilha;Prioridade;Próxima ação;Descrição", conteudo)
        self.assertIn("Balança integrada no PDV", conteudo)
        self.assertIn("Em andamento", conteudo)
        self.assertIn("Dispositivos", conteudo)
        self.assertIn("Planejar teste em equipamento real", conteudo)
        self.assertNotIn("Tela PDV em layout de operador", conteudo)
        self.assertNotIn("TEF/API de maquininha", conteudo)

    def test_painel_sistema_centraliza_admin_proprio(self):
        response = self.client.get("/configuracoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Painel do sistema")
        self.assertContains(response, "Empresas e filiais")
        self.assertContains(response, "Usuarios")
        self.assertContains(response, "Fiscal")
        self.assertContains(response, "Formas de pagamento")
        self.assertContains(response, "Terminais PDV")
        self.assertNotContains(response, "Admin Django")
        self.assertContains(response, "Checklist")
        self.assertContains(response, "App PDV desktop")
        self.assertContains(response, "Servidor local/admin")
        self.assertContains(response, "Super admin")
        self.assertNotContains(response, "Admin Django")

    def test_super_admin_proprio_substitui_admin_django_para_admin_master(self):
        PerfilUsuario.objects.create(usuario=self.user, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        LogAuditoria.objects.create(
            usuario=self.user,
            modulo="configuracoes",
            acao="TESTE_SUPER_ADMIN",
            descricao="Evento visivel no painel master.",
        )

        response = self.client.get("/configuracoes/super-admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Super admin")
        self.assertContains(response, "Área restrita ao admin master")
        self.assertContains(response, "Fila avançada concluída")
        self.assertContains(response, "Prontidão operacional")
        self.assertContains(response, "Empresas e filiais")
        self.assertContains(response, "Terminais PDV")
        self.assertContains(response, "Servidor local/admin")
        self.assertContains(response, "Inventário técnico")
        self.assertContains(response, "Inspecionar")
        self.assertContains(response, "Diagnóstico JSON")
        self.assertContains(response, "Excel/CSV")
        self.assertContains(response, "Pendências acionáveis")
        self.assertContains(response, "Usuários sem perfil")
        self.assertContains(response, "Filiais sem IBGE")
        self.assertContains(response, "Cobertura de telas próprias")
        self.assertContains(response, "ConfiguracaoFiscal, SerieFiscal, NaturezaOperacao, DocumentoFiscal")
        self.assertContains(response, "EventoSincronizacao, EventoEntradaSincronizacao")
        self.assertContains(response, "Atividade recente")
        self.assertContains(response, "TESTE_SUPER_ADMIN")
        self.assertContains(response, "Investigações rápidas")
        self.assertContains(response, "Auditoria de configurações")
        self.assertContains(response, "Checklist em andamento")
        self.assertContains(response, "Alertas de sincronização")
        self.assertContains(response, "Sincronização com alerta")
        self.assertContains(response, "Diagnóstico da sincronização")
        self.assertContains(response, "Estornos eletrônicos pendentes")
        self.assertContains(response, "Ambiente e segurança")
        self.assertContains(response, "Banco padrão")
        self.assertContains(response, "Pasta media")
        self.assertContains(response, "Perfis ativos")
        self.assertContains(response, "Administrador")
        self.assertNotContains(response, "Admin Django")

    def test_super_admin_diagnostico_json_para_suporte_restrito(self):
        PerfilUsuario.objects.create(usuario=self.user, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)

        response = self.client.get("/configuracoes/super-admin/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["usuario"], "admin")
        self.assertIn("diagnosticos", payload)
        self.assertIn("modelos", payload)
        self.assertIn("inspecao_url", payload["modelos"][0])
        self.assertIn("perfis_por_tipo", payload)
        self.assertIn("resumo_checklist", payload)
        self.assertIn("pendencias_acionaveis", payload)
        self.assertIn("cobertura_telas", payload)
        self.assertIn("modelos_avancados_pendentes", payload)
        self.assertIn("atividade_recente", payload)
        self.assertIn("investigacoes", payload)
        self.assertIn("ambiente_operacional", payload)
        self.assertIn("prontidao_operacional", payload)
        self.assertIn("links", payload)
        self.assertEqual(payload["links"]["diagnostico_json"], "http://localhost/configuracoes/super-admin/diagnostico.json")
        self.assertEqual(payload["links"]["diagnostico_csv"], "http://localhost/configuracoes/super-admin/diagnostico.csv")
        self.assertEqual(payload["links"]["sincronizacao_diagnostico_json"], "http://localhost/empresas/sincronizacao/diagnostico.json")
        self.assertIn("Usuários sem perfil", [item["titulo"] for item in payload["pendencias_acionaveis"]])
        self.assertIn("Sincronização com alerta", [item["titulo"] for item in payload["pendencias_acionaveis"]])
        self.assertIn("Estornos eletrônicos pendentes", [item["titulo"] for item in payload["pendencias_acionaveis"]])
        self.assertIn("Fiscal", [item["area"] for item in payload["cobertura_telas"]])
        self.assertTrue(all(item["status"] == "Completa" for item in payload["cobertura_telas"]))
        fiscal = next(item for item in payload["cobertura_telas"] if item["area"] == "Fiscal")
        self.assertEqual(fiscal["status"], "Completa")
        self.assertNotIn("Séries fiscais e naturezas", [item["area"] for item in payload["modelos_avancados_pendentes"]])
        self.assertEqual(payload["modelos_avancados_pendentes"], [])
        self.assertIn("Auditoria do PDV", [item["titulo"] for item in payload["investigacoes"]])
        self.assertIn("Diagnóstico da sincronização", [item["titulo"] for item in payload["investigacoes"]])
        self.assertIn("DEBUG", [item["item"] for item in payload["ambiente_operacional"]])
        self.assertIn(payload["prontidao_operacional"]["status"], {"Pronta", "Atenção", "Crítica"})
        self.assertGreaterEqual(payload["total_modelos"], 1)

    def test_super_admin_destaca_valor_de_estorno_eletronico_pendente(self):
        PerfilUsuario.objects.create(usuario=self.user, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.user)
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa,
            usuario=self.user,
            total_liquido=Decimal("42.50"),
        )
        forma = FormaPagamento.objects.create(nome="PIX", tipo="PIX")
        PagamentoVenda.objects.create(
            venda=venda,
            forma_pagamento=forma,
            valor=Decimal("42.50"),
            status=StatusPagamento.ESTORNO_PENDENTE,
            transacao_externa_id="PIX-ESTORNO-001",
        )

        response = self.client.get("/configuracoes/super-admin/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        diagnostico = next(item for item in payload["diagnosticos"] if item["titulo"] == "Estornos eletrônicos pendentes")
        pendencia = next(item for item in payload["pendencias_acionaveis"] if item["titulo"] == "Estornos eletrônicos pendentes")
        self.assertEqual(diagnostico["valor"], 1)
        self.assertIn("R$ 42.50", diagnostico["descricao"])
        self.assertEqual(pendencia["prioridade"], "Alta")
        self.assertEqual(pendencia["total"], 1)
        self.assertEqual(pendencia["url_name"], "pdv:estornos_eletronicos")
        self.assertEqual(payload["prontidao_operacional"]["status"], "Crítica")
    def test_super_admin_diagnostico_csv_para_suporte_restrito(self):
        PerfilUsuario.objects.create(usuario=self.user, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        LogAuditoria.objects.create(
            usuario=self.user,
            modulo="configuracoes",
            acao="EXPORTACAO_TESTE",
            descricao="Evento para CSV do super admin.",
        )

        response = self.client.get("/configuracoes/super-admin/diagnostico.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        conteudo = response.content.decode("utf-8-sig")
        self.assertIn("Seção;Item;Status/Prioridade;Total/Valor;Descrição/Ação", conteudo)
        self.assertIn("Diagnostico;Admin masters;Acesso", conteudo)
        self.assertIn("Pendencia;Usuários sem perfil;Alta", conteudo)
        self.assertIn("Cobertura;Fiscal;Completa", conteudo)
        self.assertNotIn("Modelo avancado;Séries fiscais e naturezas;Alta", conteudo)
        self.assertNotIn("Modelo avancado;", conteudo)
        self.assertIn("Atividade;EXPORTACAO_TESTE;configuracoes", conteudo)
        self.assertIn("Investigacao;Auditoria de configurações;Link", conteudo)
        self.assertIn("Ambiente;DEBUG;", conteudo)
        self.assertIn("Prontidao;", conteudo)
        self.assertIn("Perfil;Administrador;Ativo", conteudo)

    def test_super_admin_modelo_inspecao_protegida_paginada_e_sem_admin_django(self):
        PerfilUsuario.objects.create(usuario=self.user, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        get_user_model().objects.create_user("operador_visivel", "operador_visivel@example.com", "123")

        response = self.client.get("/configuracoes/super-admin/modelos/auth/user/", {"q": "operador"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inspeção de modelo")
        self.assertContains(response, "Consulta protegida, sem edição direta")
        self.assertContains(response, "operador_visivel")
        self.assertContains(response, "Página")
        self.assertContains(response, "••••")
        self.assertNotContains(response, "Admin Django")

    def test_super_admin_modelo_inspecao_exige_admin_master(self):
        gerente = get_user_model().objects.create_user("gerente_modelo", "gerente_modelo@example.com", "123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.client.force_login(gerente)

        response = self.client.get("/configuracoes/super-admin/modelos/auth/user/")

        self.assertEqual(response.status_code, 403)

    def test_super_admin_exige_admin_master(self):
        gerente = get_user_model().objects.create_user("gerente_super_admin", "gerente_super_admin@example.com", "123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.client.force_login(gerente)

        response = self.client.get("/configuracoes/super-admin/")
        diagnostico = self.client.get("/configuracoes/super-admin/diagnostico.json")
        csv_response = self.client.get("/configuracoes/super-admin/diagnostico.csv")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(diagnostico.status_code, 403)
        self.assertEqual(csv_response.status_code, 403)

    def test_administrador_da_empresa_nao_acessa_nem_visualiza_super_admin(self):
        administrador = get_user_model().objects.create_user(
            "admin_empresa_sem_master", "admin_empresa_sem_master@example.com", "123"
        )
        PerfilUsuario.objects.create(
            usuario=administrador,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.client.force_login(administrador)

        painel = self.client.get("/configuracoes/")
        pagina = self.client.get("/configuracoes/super-admin/")
        diagnostico = self.client.get("/configuracoes/super-admin/diagnostico.json")
        csv_response = self.client.get("/configuracoes/super-admin/diagnostico.csv")
        inspecao = self.client.get("/configuracoes/super-admin/modelos/auth/user/")

        self.assertEqual(painel.status_code, 200)
        self.assertNotContains(painel, "Super admin")
        self.assertEqual(pagina.status_code, 403)
        self.assertEqual(diagnostico.status_code, 403)
        self.assertEqual(csv_response.status_code, 403)
        self.assertEqual(inspecao.status_code, 403)
    def test_servidor_local_admin_prepara_manifesto_de_implantacao(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.save(update_fields=["modo_implantacao", "sincronizacao_automatica"])

        response = self.client.get("/configuracoes/servidor-local/")
        manifest = self.client.get("/configuracoes/servidor-local/manifest.json")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Servidor local administrativo")
        self.assertContains(response, "não um segundo sistema")
        self.assertContains(response, "PDV desktop segue separado e restrito ao operador")
        self.assertContains(response, "Serviço Windows/Linux")
        self.assertContains(response, "Backup local automático")
        self.assertContains(response, "scripts/run_local_server.ps1")
        self.assertContains(response, "scripts/register_local_server_task.ps1")
        self.assertContains(response, "scripts/install_local_server_service.ps1")
        self.assertContains(response, "scripts/package_local_server.ps1")
        self.assertContains(response, "scripts/publish_local_server.ps1")
        self.assertContains(response, "scripts/update_local_server.ps1")
        self.assertContains(response, "Atualização controlada")
        self.assertContains(response, "scripts/test_local_server_service.ps1")
        self.assertContains(response, "scripts/uninstall_local_server_service.ps1")
        self.assertContains(response, "server_local/windows/DeigoVarejoServidorLocal.xml.template")
        self.assertContains(response, "scripts/backup_local.ps1")
        self.assertContains(response, "scripts/restore_local_backup.ps1")
        self.assertContains(response, "scripts/register_backup_task.ps1")
        self.assertContains(response, "BACKUP_ENCRYPTION_PASSPHRASE")
        self.assertContains(response, "-RemoverOriginalCriptografado")
        self.assertContains(response, "-ValidarSomente")
        self.assertContains(response, "LOCAL_BACKUP_DIR")
        self.assertContains(response, "Backup local protegido")
        self.assertContains(response, "Restauração operacional")
        self.assertContains(response, "scripts/register_sync_task.ps1")
        self.assertContains(response, "docs/IMPLANTACAO_SERVIDOR_LOCAL.md")
        self.assertContains(response, "docs/MANUAL_INSTALACAO_SUPERMERCADO.md")
        self.assertContains(response, "Supermercado Modelo")
        self.assertContains(response, "Servidor local com sincronização em nuvem")
        self.assertContains(response, "Prontidão do servidor local")
        self.assertContains(response, "local_admin_readiness_v1")
        self.assertEqual(manifest.status_code, 200)
        payload = manifest.json()
        self.assertEqual(payload["contrato"], "erp_local_admin_v1")
        self.assertEqual(payload["prontidao"]["contrato"], "local_admin_readiness_v1")
        self.assertIn(payload["prontidao"]["status"], ["Homologacao parcial", "Pronta com ressalvas", "Pronta"])
        self.assertTrue(payload["prontidao"]["arquivos"]["backup_local"]["existe"])
        self.assertTrue(payload["prontidao"]["arquivos"]["restaurar_backup"]["existe"])
        self.assertTrue(payload["prontidao"]["arquivos"]["manual_instalacao"]["existe"])
        self.assertTrue(payload["acesso"]["usa_navegador"])
        self.assertTrue(payload["acesso"]["pdv_desktop_separado"])
        self.assertEqual(payload["servico_windows"]["nome"], "DeigoVarejoServidorLocal")
        self.assertEqual(payload["servico_windows"]["status"], "instalador_preparado")
        self.assertEqual(payload["servico_windows"]["banco_recomendado"], "PostgreSQL")
        self.assertIn("pg_restore", payload["servico_windows"]["ferramentas_banco"])
        self.assertIn("waitress", payload["servico_windows"]["comando_producao"])
        self.assertEqual(payload["servico_windows"]["healthcheck"], "/login/")
        self.assertEqual(payload["scripts"]["subir_servidor"], "scripts/run_local_server.ps1")
        self.assertEqual(payload["scripts"]["registrar_servidor"], "scripts/register_local_server_task.ps1")
        self.assertEqual(payload["scripts"]["instalar_servico"], "scripts/install_local_server_service.ps1")
        self.assertEqual(payload["scripts"]["empacotar_servidor"], "scripts/package_local_server.ps1")
        self.assertEqual(payload["scripts"]["publicar_servidor"], "scripts/publish_local_server.ps1")
        self.assertEqual(payload["scripts"]["atualizar_servidor"], "scripts/update_local_server.ps1")
        self.assertEqual(payload["scripts"]["diagnosticar_servico"], "scripts/test_local_server_service.ps1")
        self.assertEqual(payload["scripts"]["remover_servico"], "scripts/uninstall_local_server_service.ps1")
        self.assertEqual(payload["scripts"]["template_servico"], "server_local/windows/DeigoVarejoServidorLocal.xml.template")
        self.assertTrue(payload["prontidao"]["arquivos"]["instalar_servico"]["existe"])
        self.assertTrue(payload["prontidao"]["arquivos"]["empacotar_servidor"]["existe"])
        self.assertTrue(payload["prontidao"]["arquivos"]["publicar_servidor"]["existe"])
        self.assertTrue(payload["prontidao"]["arquivos"]["atualizar_servidor"]["existe"])
        self.assertEqual(payload["atualizacao_local"]["contrato_validacao"], "local_server_update_validation_v1")
        self.assertEqual(payload["atualizacao_local"]["contrato_rollback"], "local_server_rollback_v1")
        self.assertTrue(payload["atualizacao_local"]["healthcheck_obrigatorio"])
        self.assertTrue(payload["atualizacao_local"]["preserva_env_dados"])
        self.assertIn("NT SERVICE", payload["servico_windows"]["usuario_recomendado"])
        self.assertEqual(payload["servico_windows"]["diretorio_dados"], r"%ProgramData%\DeigoVarejo\Dados")
        self.assertEqual(payload["servico_windows"]["contrato"], "local_windows_service_v1")
        self.assertIn("SHA-256", payload["servico_windows"]["wrapper"])
        self.assertEqual(payload["scripts"]["backup_local"], "scripts/backup_local.ps1")
        self.assertEqual(payload["scripts"]["restaurar_backup"], "scripts/restore_local_backup.ps1")
        self.assertEqual(payload["scripts"]["registrar_backup"], "scripts/register_backup_task.ps1")
        self.assertEqual(payload["scripts"]["backup_criptografia_env"], "BACKUP_ENCRYPTION_PASSPHRASE")
        self.assertEqual(payload["scripts"]["backup_criptografia_flag"], "-RemoverOriginalCriptografado")
        self.assertEqual(payload["scripts"]["backup_validacao_flag"], "-ValidarSomente")
        self.assertEqual(payload["scripts"]["backup_destino_env"], "LOCAL_BACKUP_DIR")
        self.assertEqual(payload["scripts"]["backup_conta_tarefa"], "SYSTEM")
        self.assertEqual(payload["backup_local"]["contrato"], "erp_local_backup_v2")
        self.assertEqual(payload["backup_local"]["fontes_contrato"], "local_backup_sources_v1")
        self.assertTrue(payload["backup_local"]["sqlite_snapshot_consistente"])
        self.assertTrue(payload["backup_local"]["postgresql_dump_custom"])
        self.assertEqual(payload["backup_local"]["postgresql_ferramenta"], "pg_dump")
        self.assertFalse(payload["backup_local"]["depende_usuario_conectado"])
        self.assertEqual(payload["restauracao_local"]["contrato_validacao"], "local_restore_validation_v1")
        self.assertEqual(payload["restauracao_local"]["contrato_historico"], "local_restore_history_v1")
        self.assertTrue(payload["restauracao_local"]["confirmacao_explicita"])
        self.assertTrue(payload["restauracao_local"]["rollback_sqlite_media"])
        self.assertIn("postgresql", payload["restauracao_local"]["motores"])
        self.assertTrue(payload["restauracao_local"]["postgresql_transacao_unica"])
        self.assertEqual(payload["scripts"]["registrar_sincronizacao"], "scripts/register_sync_task.ps1")
        self.assertEqual(payload["scripts"]["manual_instalacao"], "docs/MANUAL_INSTALACAO_SUPERMERCADO.md")
        self.assertEqual(payload["modos_implantacao"]["hibrido"]["empresas"], 1)
        self.assertEqual(payload["empresas"][0]["modo_implantacao"], ModoImplantacao.HIBRIDO)
        self.assertTrue(payload["empresas"][0]["sincronizacao_automatica"])
        instalador_texto = (Path(settings.BASE_DIR) / payload["scripts"]["instalar_servico"]).read_text(encoding="utf-8")
        empacotador_texto = (Path(settings.BASE_DIR) / payload["scripts"]["empacotar_servidor"]).read_text(encoding="utf-8")
        publicador_texto = (Path(settings.BASE_DIR) / payload["scripts"]["publicar_servidor"]).read_text(encoding="utf-8")
        atualizador_texto = (Path(settings.BASE_DIR) / payload["scripts"]["atualizar_servidor"]).read_text(encoding="utf-8")
        diagnostico_texto = (Path(settings.BASE_DIR) / payload["scripts"]["diagnosticar_servico"]).read_text(encoding="utf-8")
        backup_texto = (Path(settings.BASE_DIR) / payload["scripts"]["backup_local"]).read_text(encoding="utf-8")
        restaurador_texto = (Path(settings.BASE_DIR) / payload["scripts"]["restaurar_backup"]).read_text(encoding="utf-8")
        agendador_backup_texto = (Path(settings.BASE_DIR) / payload["scripts"]["registrar_backup"]).read_text(encoding="utf-8")
        self.assertIn(r"NT SERVICE\DeigoVarejoServidorLocal", instalador_texto)
        self.assertIn("SQLITE_PATH", instalador_texto)
        self.assertIn("icacls.exe", instalador_texto)
        self.assertIn('[string]$DatabaseEngine = "PostgreSQL"', instalador_texto)
        self.assertIn("POSTGRES_PG_DUMP_PATH", instalador_texto)
        self.assertIn("POSTGRES_PG_RESTORE_PATH", instalador_texto)
        self.assertIn("git status --porcelain", empacotador_texto)
        self.assertIn("local_server_package_v1", empacotador_texto)
        self.assertIn("contem_dados_cliente = $false", empacotador_texto)
        self.assertIn("local_server_package_content_v1", empacotador_texto)
        self.assertIn("validar_conteudo_pacote_servidor", empacotador_texto)
        self.assertIn("validar_conteudo_pacote_servidor", publicador_texto)
        self.assertIn("local_server_package_v1", publicador_texto)
        self.assertIn(".uploading", publicador_texto)
        self.assertIn("Get-FileHash", publicador_texto)
        self.assertIn("local_server_update_validation_v1", atualizador_texto)
        self.assertIn("local_server_rollback_v1", atualizador_texto)
        self.assertIn("source.backup(target)", atualizador_texto)
        self.assertIn("Wait-Health", atualizador_texto)
        self.assertIn("Replace-CodeLayout", atualizador_texto)
        self.assertIn("Atualizacao cancelada e rollback concluido", atualizador_texto)
        self.assertIn("identidade_dedicada", diagnostico_texto)
        self.assertIn("local_backup_sources_v1", backup_texto)
        self.assertIn("erp_local_backup_v2", backup_texto)
        self.assertIn("source.backup(target)", backup_texto)
        self.assertIn("pg_dump", backup_texto)
        self.assertIn("--format=custom", backup_texto)
        self.assertIn("PGPASSWORD", backup_texto)
        self.assertIn("DeigoVarejoServidorLocal.xml", backup_texto)
        self.assertIn("local_restore_validation_v1", restaurador_texto)
        self.assertIn("pg_restore", restaurador_texto)
        self.assertIn("--single-transaction", restaurador_texto)
        self.assertIn("Restauracao cruzada foi recusada", restaurador_texto)
        self.assertIn("erp_local_backup_v2", restaurador_texto)
        self.assertIn("ConfirmarRestauracao", restaurador_texto)
        self.assertIn("backup_local.ps1", restaurador_texto)
        self.assertIn("Wait-Health", restaurador_texto)
        self.assertIn("Restauracao cancelada e dados anteriores recuperados", restaurador_texto)
        self.assertIn("-LogonType ServiceAccount", agendador_backup_texto)
        self.assertIn('"SYSTEM"', agendador_backup_texto)

    def test_manifesto_servidor_local_exige_admin_master(self):
        gerente = get_user_model().objects.create_user("gerente_local", "gerente_local@example.com", "123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.client.force_login(gerente)

        response = self.client.get("/configuracoes/servidor-local/manifest.json")

        self.assertEqual(response.status_code, 403)

    def test_admin_master_baixa_pacote_servidor_local_validado_com_auditoria(self):
        conteudo = b"pacote-servidor-local-teste"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeigoVarejoServidorLocal.zip"
            with override_settings(
                LOCAL_SERVER_PACKAGE_PATH=caminho,
                LOCAL_SERVER_VERSION="1.2.3",
                LOCAL_SERVER_REQUIRE_SIGNED_COMMIT=True,
            ):
                conteudo_pacote = criar_pacote_servidor_teste(
                    caminho, conteudo, versao="1.2.3", commit_assinado=True
                )
                central = self.client.get("/configuracoes/servidor-local/")
                manifest = self.client.get("/configuracoes/servidor-local/manifest.json")
                download = self.client.get("/configuracoes/servidor-local/download/")
                baixado = b"".join(download.streaming_content)

        distribuicao = manifest.json()["distribuicao"]
        self.assertContains(central, "Baixar pacote")
        self.assertEqual(distribuicao["contrato"], "local_server_distribution_v1")
        self.assertEqual(distribuicao["status"], "disponivel")
        self.assertEqual(distribuicao["tamanho_bytes"], len(conteudo_pacote))
        self.assertEqual(distribuicao["sha256"], hashlib.sha256(conteudo_pacote).hexdigest())
        self.assertTrue(distribuicao["integridade_valida"])
        self.assertTrue(distribuicao["tamanho_valido"])
        self.assertTrue(distribuicao["origem_rastreavel"])
        self.assertTrue(distribuicao["sem_dados_cliente"])
        self.assertTrue(distribuicao["conteudo_valido"])
        self.assertTrue(distribuicao["commit_assinado_confirmado"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(baixado, conteudo_pacote)
        self.assertTrue(LogAuditoria.objects.filter(acao="DOWNLOAD_SERVIDOR_LOCAL", usuario=self.user).exists())

    def test_pacote_servidor_local_adulterado_e_bloqueado(self):
        conteudo = b"pacote-original"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeigoVarejoServidorLocal.zip"
            with override_settings(
                LOCAL_SERVER_PACKAGE_PATH=caminho,
                LOCAL_SERVER_VERSION="1.2.3",
                LOCAL_SERVER_REQUIRE_SIGNED_COMMIT=False,
            ):
                conteudo_pacote = criar_pacote_servidor_teste(caminho, conteudo, versao="1.2.3")
                caminho.write_bytes(conteudo_pacote + b"-alterado")
                manifest = self.client.get("/configuracoes/servidor-local/manifest.json")
                download = self.client.get("/configuracoes/servidor-local/download/")

        distribuicao = manifest.json()["distribuicao"]
        self.assertEqual(distribuicao["status"], "indisponivel")
        self.assertFalse(distribuicao["integridade_valida"])
        self.assertIn("SHA-256", distribuicao["problemas"][0])
        self.assertEqual(download.status_code, 404)
        self.assertFalse(LogAuditoria.objects.filter(acao="DOWNLOAD_SERVIDOR_LOCAL").exists())

    def test_pacote_servidor_local_com_dados_de_cliente_e_bloqueado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeigoVarejoServidorLocal.zip"
            with override_settings(
                LOCAL_SERVER_PACKAGE_PATH=caminho,
                LOCAL_SERVER_VERSION="1.2.3",
                LOCAL_SERVER_REQUIRE_SIGNED_COMMIT=False,
            ):
                criar_pacote_servidor_teste(
                    caminho,
                    b"pacote-com-dados",
                    versao="1.2.3",
                    contem_dados_cliente=True,
                )
                manifest = self.client.get("/configuracoes/servidor-local/manifest.json")
                download = self.client.get("/configuracoes/servidor-local/download/")

        distribuicao = manifest.json()["distribuicao"]
        self.assertFalse(distribuicao["sem_dados_cliente"])
        self.assertIn("ausencia de dados do cliente", " ".join(distribuicao["problemas"]))
        self.assertEqual(download.status_code, 404)

    def test_pacote_servidor_local_com_testes_e_prototipos_e_bloqueado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeigoVarejoServidorLocal.zip"
            with override_settings(
                LOCAL_SERVER_PACKAGE_PATH=caminho,
                LOCAL_SERVER_VERSION="1.2.3",
                LOCAL_SERVER_REQUIRE_SIGNED_COMMIT=False,
            ):
                criar_pacote_servidor_teste(
                    caminho,
                    b"codigo",
                    versao="1.2.3",
                    arquivos_extras={
                        "apps/licenciamento/tests.py": b"assert True",
                        "docs/protótipos/requisitos-internos.docx": b"interno",
                    },
                )
                manifest = self.client.get("/configuracoes/servidor-local/manifest.json")
                download = self.client.get("/configuracoes/servidor-local/download/")

        distribuicao = manifest.json()["distribuicao"]
        problemas = " ".join(distribuicao["problemas"]).casefold()
        self.assertFalse(distribuicao["conteudo_valido"])
        self.assertIn("teste interno", problemas)
        self.assertIn("documentação interna", problemas)
        self.assertEqual(download.status_code, 404)

    def test_pacote_servidor_local_com_segredos_reais_e_bloqueado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeigoVarejoServidorLocal.zip"
            with override_settings(
                LOCAL_SERVER_PACKAGE_PATH=caminho,
                LOCAL_SERVER_VERSION="1.2.3",
                LOCAL_SERVER_REQUIRE_SIGNED_COMMIT=False,
            ):
                criar_pacote_servidor_teste(
                    caminho,
                    b"codigo",
                    versao="1.2.3",
                    contem_dados_cliente=False,
                    arquivos_extras={
                        ".env": "SECRET_KEY=segredo-real",
                        "media/clientes/documento.jpg": b"dados",
                        "../escape.py": b"nao pode sair do destino",
                    },
                )
                manifest = self.client.get("/configuracoes/servidor-local/manifest.json")
                download = self.client.get("/configuracoes/servidor-local/download/")

        distribuicao = manifest.json()["distribuicao"]
        self.assertFalse(distribuicao["conteudo_valido"])
        self.assertIn("proibido", " ".join(distribuicao["problemas"]).casefold())
        self.assertIn("caminho inseguro", " ".join(distribuicao["problemas"]).casefold())
        self.assertEqual(download.status_code, 404)
    def test_gerente_nao_baixa_pacote_servidor_local(self):
        gerente = get_user_model().objects.create_user("gerente_download_local", password="123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.client.force_login(gerente)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeigoVarejoServidorLocal.zip"
            with override_settings(
                LOCAL_SERVER_PACKAGE_PATH=caminho,
                LOCAL_SERVER_VERSION="1.2.3",
                LOCAL_SERVER_REQUIRE_SIGNED_COMMIT=False,
            ):
                criar_pacote_servidor_teste(caminho, b"pacote-valido", versao="1.2.3")
                response = self.client.get("/configuracoes/servidor-local/download/")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(LogAuditoria.objects.filter(acao="DOWNLOAD_SERVIDOR_LOCAL", usuario=gerente).exists())
    def test_cadastra_e_edita_forma_pagamento_no_painel_próprio(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX Caixa 01",
            tipo=TipoContaMovimento.PIX,
        )
        form_response = self.client.get("/configuracoes/formas-pagamento/nova/")
        response = self.client.post(
            "/configuracoes/formas-pagamento/nova/",
            {"nome": "PIX integrado", "tipo": "PIX", "conta_movimento_padrao": conta_pix.pk, "exige_autorizacao": "on", "ativo": "on"},
        )

        self.assertContains(form_response, "Conta movimento padrão")
        self.assertContains(form_response, "select2-field")
        self.assertRedirects(response, "/configuracoes/formas-pagamento/")
        forma = FormaPagamento.objects.get(nome="PIX integrado")
        self.assertTrue(forma.exige_autorizacao)
        self.assertEqual(forma.conta_movimento_padrao, conta_pix)
        lista = self.client.get("/configuracoes/formas-pagamento/")
        self.assertContains(lista, "PIX integrado")
        self.assertContains(lista, "PIX Caixa 01")

        invalida = self.client.post(
            f"/configuracoes/formas-pagamento/{forma.pk}/editar/",
            {"nome": forma.nome, "tipo": "PIX", "permite_troco": "on", "ativo": "on"},
        )
        self.assertContains(invalida, "Troco deve ser habilitado somente")

    def test_cadastra_terminal_pdv_no_painel_próprio(self):
        response = self.client.post(
            "/configuracoes/terminais-pdv/novo/",
            {
                "filial": self.filial.id,
                "nome": "Caixa 01",
                "descricao": "Frente de loja",
                "provedor_tef": ProvedorTef.PAGBANK,
                "modo_integracao_tef": ModoIntegracaoTef.DESKTOP_BRIDGE,
                "status_licenca": StatusLicencaTerminal.LIBERADA,
                "observacao_licenca": "Caixa contratado",
                "canal_atualizacao": CanalAtualizacaoPdv.PILOTO,
                "bloquear_atualizacoes": "on",
                "permite_modo_offline": "on",
                "emite_documento_fiscal": "on",
                "ativo": "on",
            },
            follow=True,
        )

        self.assertRedirects(response, "/configuracoes/terminais-pdv/")
        terminal = TerminalPdv.objects.get(nome="Caixa 01")
        self.assertEqual(terminal.filial, self.filial)
        self.assertTrue(terminal.permite_modo_offline)
        self.assertTrue(terminal.emite_documento_fiscal)
        self.assertEqual(terminal.provedor_tef, ProvedorTef.PAGBANK)
        self.assertEqual(terminal.modo_integracao_tef, ModoIntegracaoTef.DESKTOP_BRIDGE)
        self.assertEqual(terminal.status_licenca, StatusLicencaTerminal.LIBERADA)
        self.assertEqual(terminal.canal_atualizacao, CanalAtualizacaoPdv.PILOTO)
        self.assertTrue(terminal.bloquear_atualizacoes)
        self.assertEqual(terminal.licenca_liberada_por, self.user)
        self.assertIsNotNone(terminal.licenca_liberada_em)
        self.assertTrue(terminal.chave_api_hash)
        self.assertTrue(terminal.chave_api_prefixo)
        self.assertContains(response, "Caixa 01")
        self.assertContains(response, "servidor local da loja")
        self.assertContains(response, str(terminal.identificador))
        self.assertContains(response, "será mostrada somente agora")
        self.assertContains(response, terminal.chave_api_prefixo)
        self.assertContains(response, "Emite NFC-e")
        self.assertContains(response, "PagBank")
        self.assertContains(response, "Liberada")
        self.assertContains(response, "Piloto")
        self.assertContains(response, "Congelada")
        self.assertTrue(LogAuditoria.objects.filter(acao="POLITICA_ATUALIZACAO_TERMINAL_PDV", objeto_id=str(terminal.pk)).exists())

        segunda_visualizacao = self.client.get("/configuracoes/terminais-pdv/")
        self.assertNotContains(segunda_visualizacao, "será mostrada somente agora")

        form_response = self.client.get(f"/configuracoes/terminais-pdv/{terminal.pk}/editar/")
        self.assertContains(form_response, "select2-field")
        self.assertContains(form_response, str(terminal.identificador))
        self.assertContains(form_response, "Fiscal por terminal")
        self.assertContains(form_response, "TEF por adaptador")
        self.assertContains(form_response, "Balanca local")
        self.assertContains(form_response, "driver genérico")
        self.assertContains(form_response, "endereço:porta")
        self.assertContains(form_response, "Licenciamento do app desktop")
        self.assertContains(form_response, "Atualização controlada")

    def test_terminal_valida_endereco_tcp_e_adaptador_especifico_da_balanca(self):
        base = {
            "filial": self.filial.id,
            "nome": "Caixa balanca",
            "provedor_tef": ProvedorTef.NAO_CONFIGURADO,
            "modo_integracao_tef": ModoIntegracaoTef.DESKTOP_BRIDGE,
            "usa_balanca": "on",
            "protocolo_balanca": ProtocoloBalanca.TCP_IP,
            "porta_balanca": "192.168.1.50",
            "status_licenca": StatusLicencaTerminal.PENDENTE,
            "permite_modo_offline": "on",
            "ativo": "on",
        }
        tcp_invalido = self.client.post("/configuracoes/terminais-pdv/novo/", base)
        outro_sem_modelo = self.client.post(
            "/configuracoes/terminais-pdv/novo/",
            {**base, "protocolo_balanca": ProtocoloBalanca.OUTRO, "porta_balanca": "adaptador-local"},
        )

        self.assertContains(tcp_invalido, "formato endereço:porta")
        self.assertContains(outro_sem_modelo, "Informe o modelo para desenvolver")
        self.assertFalse(TerminalPdv.objects.filter(nome="Caixa balanca").exists())

    def test_lista_terminais_pdv_filtra_por_licenca_e_status(self):
        TerminalPdv.objects.create(filial=self.filial, nome="Caixa Liberado", status_licenca=StatusLicencaTerminal.LIBERADA)
        TerminalPdv.objects.create(filial=self.filial, nome="Caixa Pendente", descricao="Entrada principal", status_licenca=StatusLicencaTerminal.PENDENTE)
        TerminalPdv.objects.create(filial=self.filial, nome="Caixa Bloqueado", status_licenca=StatusLicencaTerminal.BLOQUEADA, ativo=False)

        liberados = self.client.get(f"/configuracoes/terminais-pdv/?licenca={StatusLicencaTerminal.LIBERADA}")
        inativos = self.client.get("/configuracoes/terminais-pdv/?status=inativo")
        bloqueados_inativos = self.client.get(f"/configuracoes/terminais-pdv/?licenca={StatusLicencaTerminal.BLOQUEADA}&status=inativo")
        busca = self.client.get("/configuracoes/terminais-pdv/?q=entrada")
        busca_com_filtro = self.client.get(f"/configuracoes/terminais-pdv/?q=caixa&licenca={StatusLicencaTerminal.PENDENTE}")

        self.assertContains(liberados, "Licença")
        self.assertContains(liberados, "Caixa Liberado")
        self.assertNotContains(liberados, "Caixa Pendente")
        self.assertContains(inativos, "Caixa Bloqueado")
        self.assertNotContains(inativos, "Caixa Liberado")
        self.assertContains(bloqueados_inativos, "Caixa Bloqueado")
        self.assertNotContains(bloqueados_inativos, "Caixa Pendente")
        self.assertContains(busca, "Entrada principal")
        self.assertNotContains(busca, "Caixa Liberado")
        self.assertContains(busca_com_filtro, "Caixa Pendente")
        self.assertNotContains(busca_com_filtro, "Caixa Liberado")
        self.assertContains(liberados, "Diagnósticos")

    def test_diagnosticos_dos_terminais_filtram_paginam_e_exportam_csv(self):
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa Diagnostico")
        outro = TerminalPdv.objects.create(filial=self.filial, nome="Caixa Outro")
        EventoDispositivoTerminal.objects.create(
            terminal=terminal,
            tipo="balanca",
            status="erro",
            mensagem="Driver da balanca indisponivel",
        )
        EventoDispositivoTerminal.objects.create(
            terminal=terminal,
            tipo="tef",
            status="ok",
            mensagem="Pagamento aprovado",
        )
        EventoDispositivoTerminal.objects.create(
            terminal=outro,
            tipo="balanca",
            status="erro",
            mensagem="Falha de outro terminal",
        )
        EventoDispositivoTerminal.objects.bulk_create(
            [
                EventoDispositivoTerminal(
                    terminal=terminal,
                    tipo="impressora",
                    status="ok",
                    mensagem=f"Teste de pagina {indice}",
                )
                for indice in range(51)
            ]
        )

        filtrada = self.client.get(
            "/configuracoes/terminais-pdv/diagnosticos/",
            {"terminal": terminal.pk, "tipo": "balanca", "status": "erro"},
        )
        paginada = self.client.get(
            "/configuracoes/terminais-pdv/diagnosticos/",
            {"terminal": terminal.pk, "page": 2},
        )
        csv_response = self.client.get(
            "/configuracoes/terminais-pdv/diagnosticos/exportar.csv",
            {"terminal": terminal.pk, "status": "erro"},
        )
        csv_texto = csv_response.content.decode("utf-8-sig")

        self.assertEqual(filtrada.status_code, 200)
        self.assertContains(filtrada, "Diagnósticos dos terminais PDV")
        self.assertContains(filtrada, "Driver da balanca indisponivel")
        self.assertNotContains(filtrada, "Pagamento aprovado")
        self.assertNotContains(filtrada, "Falha de outro terminal")
        self.assertEqual(paginada.context["pagina"].number, 2)
        self.assertEqual(paginada.context["pagina"].paginator.num_pages, 2)
        self.assertEqual(csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Caixa Diagnostico", csv_texto)
        self.assertIn("Driver da balanca indisponivel", csv_texto)
        self.assertNotIn("Falha de outro terminal", csv_texto)

    @override_settings(PDV_DESKTOP_INSTALLER_PATH=Path("__teste_instalador_inexistente__.msi"))
    def test_central_app_pdv_desktop_mostra_arquitetura_e_terminais(self):
        terminal = TerminalPdv.objects.create(
            filial=self.filial,
            nome="Caixa 02",
            provedor_tef=ProvedorTef.STONE,
            modo_integracao_tef=ModoIntegracaoTef.POS_INTEGRADO,
            usa_balanca=True,
            protocolo_balanca=ProtocoloBalanca.SERIAL,
            porta_balanca="COM3",
            modelo_balanca="Toledo Prix",
            status_licenca=StatusLicencaTerminal.LIBERADA,
            licenca_liberada_por=self.user,
            emite_documento_fiscal=False,
            canal_atualizacao=CanalAtualizacaoPdv.PILOTO,
            bloquear_atualizacoes=True,
        )
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
            abrir_gaveta_em_movimento_caixa=True,
        )
        TerminalPdv.objects.create(filial=self.filial, nome="Caixa Pendente", status_licenca=StatusLicencaTerminal.PENDENTE)
        TerminalPdv.objects.create(filial=self.filial, nome="Caixa Bloqueado", status_licenca=StatusLicencaTerminal.BLOQUEADA)
        EventoDispositivoTerminal.objects.create(
            terminal=terminal,
            tipo="balanca",
            status="erro",
            mensagem="Driver físico indisponivel",
            payload={"porta": "COM3"},
        )

        response = self.client.get("/configuracoes/pdv-desktop/")
        checklist = self.client.get("/configuracoes/checklist/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "App PDV desktop")
        self.assertContains(response, "artefato separado")
        self.assertContains(response, "admin master")
        self.assertContains(response, "Terminais cadastrados")
        self.assertContains(response, "Licenças liberadas")
        self.assertContains(response, "Pendentes")
        self.assertContains(response, "Bloqueadas/canceladas")
        self.assertContains(response, "Prontidão do App PDV desktop")
        self.assertContains(response, "pdv_desktop_readiness_v1")
        self.assertContains(response, "pdv_tef_v1")
        self.assertContains(response, "Manifesto JSON")
        self.assertContains(response, "Diagnóstico local deste terminal")
        self.assertContains(response, "Ler diagnóstico local")
        self.assertContains(response, "desktop-device-logs")
        self.assertContains(response, "Pré-homologação deste terminal")
        self.assertContains(response, "pdv_device_homologation_v1")
        self.assertContains(response, "Executar pré-homologação")
        self.assertContains(response, "Ler a balança agora")
        self.assertContains(response, "Enviar pulso de teste para a gaveta")
        self.assertContains(response, "não imprime e não cria cobrança TEF")
        self.assertContains(response, "Diagnóstico consolidado dos terminais")
        self.assertContains(response, "1 evento(s) recebidos")
        self.assertContains(response, "Driver físico indisponivel")
        self.assertContains(response, "Caixa 02")
        self.assertContains(response, "Stone")
        self.assertContains(response, "Configurada")
        self.assertContains(response, "Serial RS-232/USB")
        self.assertContains(response, "Sem fiscal automático")
        self.assertContains(response, "Pacote JSON")
        self.assertContains(response, "Atualização controlada")
        self.assertContains(response, "Canal pronto")
        self.assertContains(response, "Empacotamento pronto")
        self.assertContains(response, "WiX v4")
        self.assertContains(checklist, "Central do App PDV desktop")
        self.assertContains(checklist, "pdv_device_homologation_v1")
        self.assertContains(checklist, "não imprime nem cria cobrança")
        self.assertContains(checklist, "grava a evidência em devices.log.jsonl")
        self.assertContains(checklist, "manifesto JSON do app desktop")
        self.assertContains(checklist, "Pacote JSON por terminal")
        self.assertContains(checklist, "mesmo design, componentes, atalhos e regras do PDV web")
        self.assertContains(checklist, "shell WebView separado")
        self.assertContains(checklist, "valida o bootstrap licenciado")
        self.assertContains(checklist, "abrir /pdv/")
        self.assertContains(checklist, "ativação guiada na primeira execução")
        self.assertContains(checklist, "build reproduzível do executável Windows")
        self.assertContains(checklist, "apresenta tamanho e SHA-256")
        self.assertContains(checklist, "registra a entrega na auditoria")
        self.assertContains(checklist, "script de publicação atômica")
        self.assertContains(checklist, "configuráveis por ambiente")
        self.assertContains(checklist, "informa sua versão no bootstrap")
        self.assertContains(checklist, "bloqueia versão insegura")
        self.assertContains(checklist, "sem atualização automática fora do licenciamento")
        self.assertContains(checklist, "canal de atualização autenticado")
        self.assertContains(checklist, "pdv_update_rollout_v1")
        self.assertContains(checklist, "caixas piloto")
        self.assertContains(checklist, "valida SHA-256")
        self.assertContains(checklist, "sem atualização silenciosa")
        self.assertContains(checklist, "pdv_windows_installer_v1")
        self.assertContains(checklist, "PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER")
        self.assertContains(checklist, "exigem manifesto .version.json")
        self.assertContains(checklist, "assinatura comercial, homologação em Windows limpo")
        self.assertContains(checklist, "salva cache local do bootstrap autorizado")
        self.assertContains(checklist, "recusa de licença, chave ou terminal bloqueado nunca usa o cache")
        self.assertContains(checklist, "licença por máquina")
        self.assertContains(checklist, "licença liberada")
        self.assertContains(checklist, "não recebem pacote de ativação")
        self.assertContains(checklist, "projeto/artefato separado")
        self.assertContains(checklist, "baixado por dentro do sistema somente com autorização do admin master")
        self.assertContains(checklist, "filtros por máquina/tipo/status/período")

        manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
        self.assertEqual(manifest.status_code, 200)
        payload = manifest.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["licenciamento"]["modelo"], "por_terminal")
        self.assertTrue(payload["licenciamento"]["download_requer_admin_master"])
        self.assertEqual(payload["prontidao"]["contrato"], "pdv_desktop_readiness_v1")
        self.assertEqual(payload["prontidao"]["status"], "Bloqueada")
        self.assertEqual(payload["prontidao"]["terminais"]["licencas_liberadas"], 1)
        self.assertTrue(payload["prontidao"]["instalador"]["build_msi_preparado"])
        self.assertTrue(payload["prontidao"]["instalador"]["assinatura_obrigatoria_producao"])
        self.assertEqual(payload["contratos"]["tef"], "pdv_tef_v1")
        self.assertEqual(payload["contratos"]["fila_eventos_dispositivo"], "pdv_device_event_queue_v1")
        self.assertEqual(payload["contratos"]["instalador_windows"], "pdv_windows_installer_v1")
        self.assertEqual(payload["contratos"]["credencial_local"], "pdv_local_secret_v1")
        self.assertEqual(payload["contratos"]["instancia_local"], "pdv_single_instance_v1")
        self.assertTrue(payload["recursos"]["credencial_terminal_dpapi"])
        self.assertTrue(payload["recursos"]["configuracao_tef_dpapi"])
        self.assertTrue(payload["recursos"]["instancia_unica_por_terminal"])
        self.assertTrue(payload["recursos"]["eventos_dispositivo_idempotentes"])
        self.assertTrue(payload["recursos"]["compactacao_preserva_pendentes"])
        self.assertTrue(payload["recursos"]["sincronizacao_periodica_eventos"])
        self.assertEqual(payload["politica_atualizacao"]["contrato"], "pdv_update_rollout_v1")
        self.assertTrue(payload["politica_atualizacao"]["versao_minima_sobrepoe_congelamento"])
        self.assertEqual(payload["prontidao"]["terminais"]["canal_piloto"], 1)
        self.assertEqual(payload["prontidao"]["terminais"]["atualizacoes_congeladas"], 1)
        self.assertTrue(payload["recursos"]["fiscal_por_terminal"])
        terminal_payload = next(item for item in payload["terminais"] if item["nome"] == "Caixa 02")
        self.assertEqual(terminal_payload["provedor_tef"], ProvedorTef.STONE)
        self.assertEqual(terminal_payload["balanca"]["contrato"], "pdv_scale_v1")
        self.assertTrue(terminal_payload["balanca"]["habilitada"])
        self.assertEqual(terminal_payload["balanca"]["porta"], "COM3")
        self.assertTrue(terminal_payload["balanca"]["leitura_automatica"])
        self.assertEqual(terminal_payload["licenca"]["status"], StatusLicencaTerminal.LIBERADA)
        self.assertTrue(terminal_payload["licenca"]["liberada"])
        self.assertEqual(terminal_payload["atualizacao"]["canal"], CanalAtualizacaoPdv.PILOTO)
        self.assertTrue(terminal_payload["atualizacao"]["bloqueada_pelo_admin"])
        self.assertIn("/pdv/api/terminal/bootstrap/", terminal_payload["bootstrap_url"])

        pacote = self.client.get(f"/configuracoes/pdv-desktop/terminais/{terminal.pk}/pacote.json")
        self.assertEqual(pacote.status_code, 200)
        pacote_payload = pacote.json()
        self.assertEqual(pacote_payload["terminal"]["nome"], "Caixa 02")
        self.assertEqual(pacote_payload["interface"]["modo"], "webview_compartilhada")
        self.assertEqual(pacote_payload["atualizacao"]["contrato"], "pdv_update_rollout_v1")
        self.assertEqual(pacote_payload["atualizacao"]["canal_terminal"], CanalAtualizacaoPdv.PILOTO)
        self.assertTrue(pacote_payload["atualizacao"]["bloqueada_pelo_admin"])
        self.assertTrue(pacote_payload["interface"]["mesmo_layout_do_pdv_web"])
        self.assertIn("/pdv/", pacote_payload["interface"]["pdv_url"])
        self.assertEqual(pacote_payload["licenciamento"]["modelo"], "por_terminal")
        self.assertTrue(pacote_payload["licenciamento"]["download_requer_admin_master"])
        self.assertTrue(pacote_payload["licenciamento"]["terminal_autorizado"])
        self.assertEqual(pacote_payload["licenciamento"]["status"], StatusLicencaTerminal.LIBERADA)
        self.assertEqual(pacote_payload["tef"]["provedor"], ProvedorTef.STONE)
        self.assertFalse(pacote_payload["fiscal"]["emissao_automatica"])
        self.assertTrue(pacote_payload["sincronizacao"]["modo_offline_permitido"])
        self.assertEqual(pacote_payload["dispositivos"]["balanca"]["contrato"], "pdv_scale_v1")
        self.assertTrue(pacote_payload["dispositivos"]["balanca"]["habilitada"])
        self.assertEqual(pacote_payload["dispositivos"]["balanca"]["protocolo"], ProtocoloBalanca.SERIAL)
        self.assertEqual(pacote_payload["dispositivos"]["balanca"]["modelo"], "Toledo Prix")
        self.assertTrue(pacote_payload["dispositivos"]["balanca"]["fallback_manual"])
        self.assertEqual(pacote_payload["dispositivos"]["gaveta"]["contrato"], "pdv_cash_drawer_v1")
        self.assertTrue(pacote_payload["dispositivos"]["gaveta"]["habilitada"])
        self.assertEqual(pacote_payload["dispositivos"]["gaveta"]["impressora_padrao"], "EPSON TM-T20")
        self.assertTrue(pacote_payload["dispositivos"]["gaveta"]["abrir_em_movimento_caixa"])
        self.assertIn("/configuracoes/impressoes/desktop.json", pacote_payload["dispositivos"]["impressora"]["config_url"])

    def test_pacote_do_app_desktop_so_sai_com_licenca_liberada(self):
        terminal = TerminalPdv.objects.create(
            filial=self.filial,
            nome="Caixa Pendente",
            status_licenca=StatusLicencaTerminal.PENDENTE,
        )

        response = self.client.get("/configuracoes/pdv-desktop/")
        manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
        pacote = self.client.get(f"/configuracoes/pdv-desktop/terminais/{terminal.pk}/pacote.json")

        self.assertContains(response, "Caixa Pendente")
        self.assertContains(response, "Libere licença")
        self.assertEqual(manifest.status_code, 200)
        payload = manifest.json()
        self.assertEqual(payload["terminais"][0]["licenca"]["status"], StatusLicencaTerminal.PENDENTE)
        self.assertFalse(payload["terminais"][0]["licenca"]["liberada"])
        self.assertEqual(pacote.status_code, 403)

    def test_central_informa_quando_instalador_ainda_nao_foi_publicado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeTecPDV.exe"
            with override_settings(PDV_DESKTOP_INSTALLER_PATH=caminho):
                central = self.client.get("/configuracoes/pdv-desktop/")
                manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
                download = self.client.get("/configuracoes/pdv-desktop/download/windows/")

        self.assertContains(central, "Aguardando build assinado")
        self.assertEqual(manifest.json()["artefatos"]["windows_x64"]["status"], "aguardando_build")
        self.assertEqual(download.status_code, 404)

    def test_admin_master_baixa_instalador_publicado_com_integridade_e_auditoria(self):
        conteudo = b"executavel-pdv-teste"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeTecPDV.exe"
            criar_artefato_pdv_teste(caminho, conteudo)
            with override_settings(PDV_DESKTOP_INSTALLER_PATH=caminho, PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER=False):
                central = self.client.get("/configuracoes/pdv-desktop/")
                manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
                download = self.client.get("/configuracoes/pdv-desktop/download/windows/")
                baixado = b"".join(download.streaming_content)

        artefato = manifest.json()["artefatos"]["windows_x64"]
        self.assertContains(central, "Baixar instalador Windows")
        self.assertEqual(artefato["status"], "disponivel")
        self.assertEqual(artefato["tamanho_bytes"], len(conteudo))
        self.assertEqual(artefato["sha256"], hashlib.sha256(conteudo).hexdigest())
        self.assertTrue(artefato["integridade_valida"])
        self.assertTrue(artefato["versao_valida"])
        self.assertFalse(artefato["assinatura_exigida"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(baixado, conteudo)
        self.assertTrue(LogAuditoria.objects.filter(acao="DOWNLOAD_PDV_DESKTOP", usuario=self.user).exists())

    def test_instalador_alterado_apos_publicacao_e_bloqueado(self):
        conteudo = b"msi-original"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeTecPDV.msi"
            criar_artefato_pdv_teste(caminho, conteudo)
            caminho.write_bytes(conteudo + b"-alterado")
            with override_settings(
                PDV_DESKTOP_INSTALLER_PATH=caminho,
                PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER=False,
            ):
                central = self.client.get("/configuracoes/pdv-desktop/")
                manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
                download = self.client.get("/configuracoes/pdv-desktop/download/windows/")

        artefato = manifest.json()["artefatos"]["windows_x64"]
        self.assertContains(central, "Artefato encontrado, mas bloqueado para distribuição")
        self.assertContains(central, "SHA-256 do instalador diverge do manifesto")
        self.assertEqual(artefato["status"], "aguardando_build")
        self.assertFalse(artefato["integridade_valida"])
        self.assertEqual(download.status_code, 404)
        self.assertFalse(LogAuditoria.objects.filter(acao="DOWNLOAD_PDV_DESKTOP", usuario=self.user).exists())

    def test_producao_exige_assinaturas_validas_do_executavel_e_msi(self):
        conteudo = b"msi-sem-assinatura"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeTecPDV.msi"
            criar_artefato_pdv_teste(caminho, conteudo, assinado=False)
            with override_settings(
                PDV_DESKTOP_INSTALLER_PATH=caminho,
                PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER=True,
            ):
                manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
                download = self.client.get("/configuracoes/pdv-desktop/download/windows/")

        artefato = manifest.json()["artefatos"]["windows_x64"]
        self.assertFalse(artefato["assinatura_valida"])
        self.assertTrue(artefato["assinatura_exigida"])
        self.assertIn("Assinatura digital valida", artefato["problemas"][0])
        self.assertEqual(download.status_code, 404)
    def test_gerente_nao_baixa_instalador_desktop(self):
        gerente = get_user_model().objects.create_user("gerente_download", password="123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.client.force_login(gerente)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DeTecPDV.exe"
            caminho.write_bytes(b"arquivo")
            with override_settings(PDV_DESKTOP_INSTALLER_PATH=caminho):
                response = self.client.get("/configuracoes/pdv-desktop/download/windows/")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(LogAuditoria.objects.filter(acao="DOWNLOAD_PDV_DESKTOP", usuario=gerente).exists())

    def test_app_pdv_desktop_exige_admin_master_para_distribuicao(self):
        gerente = get_user_model().objects.create_user("gerente", "gerente@example.com", "123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa Licenca")

        self.client.force_login(gerente)

        response = self.client.get("/configuracoes/pdv-desktop/")
        manifest = self.client.get("/configuracoes/pdv-desktop/manifest.json")
        pacote = self.client.get(f"/configuracoes/pdv-desktop/terminais/{terminal.pk}/pacote.json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(manifest.status_code, 403)
        self.assertEqual(pacote.status_code, 403)

    def test_gerente_nao_libera_licenca_do_terminal_pdv(self):
        gerente = get_user_model().objects.create_user("gerente2", "gerente2@example.com", "123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.client.force_login(gerente)

        response = self.client.post(
            "/configuracoes/terminais-pdv/novo/",
            {
                "filial": self.filial.id,
                "nome": "Caixa sem licenca",
                "descricao": "Criado pelo gerente",
                "provedor_tef": ProvedorTef.NAO_CONFIGURADO,
                "modo_integracao_tef": ModoIntegracaoTef.DESKTOP_BRIDGE,
                "status_licenca": StatusLicencaTerminal.LIBERADA,
                "observacao_licenca": "Tentativa de liberar",
                "canal_atualizacao": CanalAtualizacaoPdv.PILOTO,
                "bloquear_atualizacoes": "on",
                "permite_modo_offline": "on",
                "emite_documento_fiscal": "on",
                "ativo": "on",
            },
            follow=True,
        )

        self.assertRedirects(response, "/configuracoes/terminais-pdv/")
        terminal = TerminalPdv.objects.get(nome="Caixa sem licenca")
        self.assertEqual(terminal.status_licenca, StatusLicencaTerminal.PENDENTE)
        self.assertIsNone(terminal.licenca_liberada_por)
        self.assertEqual(terminal.observacao_licenca, "Aguardando liberação do admin master.")
        self.assertEqual(terminal.canal_atualizacao, CanalAtualizacaoPdv.ESTAVEL)
        self.assertFalse(terminal.bloquear_atualizacoes)
        self.assertFalse(LogAuditoria.objects.filter(acao="POLITICA_ATUALIZACAO_TERMINAL_PDV", objeto_id=str(terminal.pk)).exists())

    def test_admin_master_altera_licenca_do_terminal_por_acao_rapida(self):
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa Licenca Rapida")

        liberar = self.client.post(
            f"/configuracoes/terminais-pdv/{terminal.pk}/licenca/liberar/",
            {"observacao_licenca": "Liberado no contrato mensal"},
            follow=True,
        )
        terminal.refresh_from_db()
        self.assertRedirects(liberar, "/configuracoes/terminais-pdv/")
        self.assertEqual(terminal.status_licenca, StatusLicencaTerminal.LIBERADA)
        self.assertEqual(terminal.licenca_liberada_por, self.user)
        self.assertIsNotNone(terminal.licenca_liberada_em)
        self.assertEqual(terminal.observacao_licenca, "Liberado no contrato mensal")
        self.assertContains(liberar, "Liberada")
        log_liberacao = LogAuditoria.objects.get(acao="LICENCA_TERMINAL_PDV", objeto_id=str(terminal.id))
        self.assertEqual(log_liberacao.usuario, self.user)
        self.assertEqual(log_liberacao.modulo, "configuracoes")
        self.assertIn("Liberada", log_liberacao.descricao)
        self.assertIn("Liberado no contrato mensal", log_liberacao.descricao)

        bloquear = self.client.post(f"/configuracoes/terminais-pdv/{terminal.pk}/licenca/bloquear/", follow=True)
        terminal.refresh_from_db()
        self.assertRedirects(bloquear, "/configuracoes/terminais-pdv/")
        self.assertEqual(terminal.status_licenca, StatusLicencaTerminal.BLOQUEADA)
        self.assertEqual(LogAuditoria.objects.filter(acao="LICENCA_TERMINAL_PDV", objeto_id=str(terminal.id)).count(), 2)
        pacote_bloqueado = self.client.get(f"/configuracoes/pdv-desktop/terminais/{terminal.pk}/pacote.json")
        self.assertEqual(pacote_bloqueado.status_code, 403)

        cancelar = self.client.post(f"/configuracoes/terminais-pdv/{terminal.pk}/licenca/cancelar/", follow=True)
        terminal.refresh_from_db()
        self.assertRedirects(cancelar, "/configuracoes/terminais-pdv/")
        self.assertEqual(terminal.status_licenca, StatusLicencaTerminal.CANCELADA)
        self.assertEqual(LogAuditoria.objects.filter(acao="LICENCA_TERMINAL_PDV", objeto_id=str(terminal.id)).count(), 3)

    def test_gerente_nao_altera_licenca_por_acao_rapida(self):
        gerente = get_user_model().objects.create_user("gerente3", "gerente3@example.com", "123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa Protegido")
        self.client.force_login(gerente)

        response = self.client.post(f"/configuracoes/terminais-pdv/{terminal.pk}/licenca/liberar/")

        terminal.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(terminal.status_licenca, StatusLicencaTerminal.PENDENTE)
        self.assertIsNone(terminal.licenca_liberada_por)

    def test_renova_chave_do_terminal_e_invalida_a_anterior(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa 03")
        chave_anterior = terminal.gerar_chave_api()
        terminal.save()

        response = self.client.post(
            f"/configuracoes/terminais-pdv/{terminal.pk}/regenerar-chave/",
            follow=True,
        )

        terminal.refresh_from_db()
        self.assertRedirects(response, "/configuracoes/terminais-pdv/")
        self.assertFalse(terminal.validar_chave_api(chave_anterior))
        self.assertContains(response, "Chave do terminal renovada")
        self.assertContains(response, "será mostrada somente agora")

    def test_edita_configuracao_impressao(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            modelo_papel=ModeloPapel.BOBINA_58,
        )
        config = ConfiguracaoImpressao.objects.get()

        response = self.client.post(
            f"/configuracoes/impressoes/{config.id}/editar/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "tipo_documento": TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
                "modelo_papel": ModeloPapel.BOBINA_80,
                "exibir_logo": "on",
                "tamanho_fonte": 12,
                "margem_superior_mm": 4,
                "margem_inferior_mm": 4,
                "margem_esquerda_mm": 4,
                "margem_direita_mm": 4,
                "mensagem_rodapé": "Obrigado pela preferência.",
                "impressora_padrao": "Caixa 01",
                "gaveta_automatica": "on",
                "abrir_gaveta_em_dinheiro": "on",
                "abrir_gaveta_em_movimento_caixa": "on",
                "numero_vias": 2,
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertEqual(config.modelo_papel, ModeloPapel.BOBINA_80)
        self.assertEqual(config.numero_vias, 2)
        self.assertEqual(config.impressora_padrao, "Caixa 01")
        self.assertTrue(config.gaveta_automatica)
        self.assertTrue(config.abrir_gaveta_em_dinheiro)
        self.assertTrue(config.abrir_gaveta_em_movimento_caixa)

        form_response = self.client.get(f"/configuracoes/impressoes/{config.id}/editar/")
        self.assertContains(form_response, "printer-suggestions")
        self.assertContains(form_response, "select2-field")
        self.assertContains(form_response, "impressoras detectadas na máquina")
        self.assertContains(form_response, "local-printer-select")
        self.assertContains(form_response, "Atualizar lista")
        self.assertContains(form_response, "Gaveta de dinheiro")
        self.assertContains(form_response, "sem tentar acionar gaveta física")

        list_response = self.client.get("/configuracoes/impressoes/")
        self.assertContains(list_response, "Com gaveta")
        self.assertContains(list_response, "Dinheiro")

    def test_central_de_impressao_alerta_configuracao_sem_impressora(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            modelo_papel=ModeloPapel.BOBINA_80,
            impressora_padrao="",
        )

        response = self.client.get("/configuracoes/impressoes/")

        self.assertContains(response, "Sem impressora")
        self.assertContains(response, "Existem configurações ativas sem impressora padrão")
        self.assertContains(response, "Não definida")

    def test_gaveta_automatica_nao_e_obrigatoria_e_so_serve_para_caixa(self):
        response = self.client.post(
            "/configuracoes/impressoes/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "tipo_documento": TipoDocumentoImpressao.RELATORIO,
                "modelo_papel": ModeloPapel.A4,
                "tamanho_fonte": 10,
                "margem_superior_mm": 5,
                "margem_inferior_mm": 5,
                "margem_esquerda_mm": 5,
                "margem_direita_mm": 5,
                "impressora_padrao": "PDF",
                "gaveta_automatica": "on",
                "abrir_gaveta_em_dinheiro": "on",
                "numero_vias": 1,
                "is_active": "on",
            },
        )
        self.assertContains(response, "Gaveta automática deve ser configurada apenas")

        response = self.client.post(
            "/configuracoes/impressoes/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "tipo_documento": TipoDocumentoImpressao.RELATORIO,
                "modelo_papel": ModeloPapel.A4,
                "tamanho_fonte": 10,
                "margem_superior_mm": 5,
                "margem_inferior_mm": 5,
                "margem_esquerda_mm": 5,
                "margem_direita_mm": 5,
                "impressora_padrao": "PDF",
                "numero_vias": 1,
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        config = ConfiguracaoImpressao.objects.get(tipo_documento=TipoDocumentoImpressao.RELATORIO)
        self.assertFalse(config.gaveta_automatica)
        self.assertFalse(config.abrir_gaveta_em_dinheiro)

    def test_endpoint_impressoras_locais_prepara_app_desktop(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="Caixa 01",
        )

        response = self.client.get("/configuracoes/impressoes/impressoras-locais.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "desktop_bridge_required")
        self.assertIn("Caixa 01", payload["impressoras_cadastradas"])

    def test_endpoint_impressoes_desktop_expõe_regras_de_gaveta(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            impressao_automatica=True,
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
            abrir_gaveta_em_movimento_caixa=False,
        )

        response = self.client.get("/configuracoes/impressoes/desktop.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["prontidao"]["contrato"], "print_readiness_v1")
        self.assertEqual(payload["prontidao"]["resumo"]["com_impressora"], 1)
        config = payload["configuracoes"][0]
        self.assertEqual(config["impressora_padrao"], "EPSON TM-T20")
        self.assertTrue(config["impressora_configurada"])
        self.assertEqual(config["mensagem"], "")
        self.assertTrue(config["impressao_automatica"])
        self.assertTrue(config["gaveta"]["automatica"])
        self.assertTrue(config["gaveta"]["abrir_em_dinheiro"])
        self.assertFalse(config["gaveta"]["abrir_em_movimento_caixa"])
        self.assertFalse(config["gaveta"]["bloqueia_venda_se_indisponivel"])

    def test_configuracao_profissional_etiqueta_e_sincronizada_com_desktop(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            largura_etiqueta_mm="100.00",
            altura_etiqueta_mm="50.00",
            gap_horizontal_mm="2.50",
            gap_vertical_mm="3.00",
            colunas_etiqueta=2,
            dpi_impressora=300,
            densidade_impressao=10,
            velocidade_impressao=5,
            tipo_midia_etiqueta="GAP",
            linguagem_impressora="ZPL",
        )

        response = self.client.get("/configuracoes/impressoes/desktop.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["prontidao"]["contrato"], "print_readiness_v1")
        self.assertEqual(payload["prontidao"]["status"], "Atencao")
        self.assertEqual(payload["prontidao"]["resumo"]["sem_impressora"], 1)
        self.assertEqual(payload["prontidao"]["resumo"]["etiquetas_com_linguagem_nativa"], 1)
        self.assertIn("modelo profissional", " ".join(payload["prontidao"]["alertas"]))
        config = payload["configuracoes"][0]
        self.assertFalse(config["impressora_configurada"])
        self.assertIn("sem impressora padrão definida", config["mensagem"])
        etiqueta = config["etiqueta"]
        self.assertEqual(etiqueta["largura_mm"], 100.0)
        self.assertEqual(etiqueta["altura_mm"], 50.0)
        self.assertEqual(etiqueta["colunas"], 2)
        self.assertEqual(etiqueta["dpi"], 300)
        self.assertEqual(etiqueta["linguagem"], "ZPL")

    def test_modelos_de_etiqueta_mantem_um_padrao_e_sincronizam_com_desktop(self):
        config = ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            impressora_padrao="Zebra ZD220",
            linguagem_impressora="ZPL",
        )
        primeiro = ModeloEtiqueta.objects.create(configuracao=config, nome="Gondola compacta", padrao=True)

        response = self.client.post(
            "/configuracoes/impressoes/modelos-etiqueta/novo/",
            {
                "configuracao": config.id,
                "nome": "Promocional grande",
                "largura_mm": "100.00",
                "altura_mm": "50.00",
                "gap_horizontal_mm": "2.00",
                "gap_vertical_mm": "3.00",
                "colunas": "2",
                "orientacao": "PAISAGEM",
                "padrao": "on",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        primeiro.refresh_from_db()
        self.assertFalse(primeiro.padrao)
        novo = ModeloEtiqueta.objects.get(nome="Promocional grande")
        payload = self.client.get("/configuracoes/impressoes/desktop.json").json()
        self.assertEqual(payload["prontidao"]["resumo"]["modelos_profissionais"], 2)
        modelos = payload["configuracoes"][0]["etiqueta"]["modelos"]
        self.assertEqual(modelos[1]["id"], novo.id)
        self.assertEqual(modelos[1]["orientacao"], "PAISAGEM")
        self.assertTrue(modelos[1]["padrao"])
        self.assertContains(response, "label-test-print")

        teste = self.client.get(f"/configuracoes/impressoes/modelos-etiqueta/{novo.id}/teste.json")
        self.assertEqual(teste.status_code, 200)
        etiqueta_teste = teste.json()
        self.assertEqual(etiqueta_teste["status"], "ok")
        self.assertEqual(etiqueta_teste["contrato"], "label_print_v1")
        self.assertEqual(etiqueta_teste["origem"], "configuracoes_modelo_etiqueta_teste")
        self.assertEqual(etiqueta_teste["impressora_padrao"], "Zebra ZD220")
        self.assertEqual(etiqueta_teste["linguagem"], "ZPL")
        self.assertEqual(etiqueta_teste["modelo"]["id"], novo.id)
        self.assertEqual(etiqueta_teste["modelo"]["largura_mm"], 100.0)
        self.assertEqual(etiqueta_teste["itens"][0]["nome"], "ETIQUETA TESTE")
        self.assertEqual(etiqueta_teste["itens"][0]["codigo"], "789000000001")
        self.assertEqual(etiqueta_teste["itens"][0]["preco"], "9.99")
        self.assertEqual(etiqueta_teste["itens"][0]["copias"], 1)
        self.assertNotIn("pre?o", etiqueta_teste["itens"][0])

# Create your tests here.

class GovernancaPainelEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(razao_social="Empresa Painel", nome_fantasia="Empresa Painel", cnpj="60123456000110")
        filial = Filial.objects.create(empresa=empresa, nome="Matriz Painel")
        self.admin = User.objects.create_user("admin_painel_empresa", password="123")
        PerfilUsuario.objects.create(usuario=self.admin, filial=filial, tipo=TipoPerfil.ADMINISTRADOR)
        self.gerente = User.objects.create_user("gerente_painel_empresa", password="123")
        PerfilUsuario.objects.create(usuario=self.gerente, filial=filial, tipo=TipoPerfil.GERENTE)

    def test_admin_empresa_nao_ve_nem_acessa_recursos_master(self):
        self.client.force_login(self.admin)
        painel = self.client.get("/configuracoes/")
        self.assertEqual(painel.status_code, 200)
        for texto in ("Super admin", "Checklist do projeto", "Registros backup", "App PDV desktop", "Servidor local/admin"):
            self.assertNotContains(painel, texto)
        for url in ("/configuracoes/super-admin/", "/configuracoes/checklist/", "/configuracoes/backup/", "/empresas/sincronizacao/"):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_gerente_nao_acessa_painel_de_administracao(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get("/configuracoes/").status_code, 403)
class EscopoConfiguracoesOperacionaisTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.empresa = Empresa.objects.create(
            razao_social="Empresa Alfa Ltda",
            nome_fantasia="Empresa Alfa",
            cnpj="71.111.111/0001-71",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Alfa", cnpj=self.empresa.cnpj)
        self.outra_empresa = Empresa.objects.create(
            razao_social="Empresa Beta Ltda",
            nome_fantasia="Empresa Beta",
            cnpj="72.222.222/0001-72",
        )
        self.outra_filial = Filial.objects.create(
            empresa=self.outra_empresa,
            nome="Matriz Beta",
            cnpj=self.outra_empresa.cnpj,
        )
        self.admin = get_user_model().objects.create_user("admin_alfa", password="123")
        PerfilUsuario.objects.create(
            usuario=self.admin,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.client.force_login(self.admin)
        self.terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa Alfa")
        self.outro_terminal = TerminalPdv.objects.create(filial=self.outra_filial, nome="Caixa Beta")
        self.configuracao = ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="Impressora Alfa",
        )
        self.outra_configuracao = ConfiguracaoImpressao.objects.create(
            empresa=self.outra_empresa,
            filial=self.outra_filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="Impressora Beta",
        )
        self.modelo = ModeloEtiqueta.objects.create(configuracao=self.configuracao, nome="Etiqueta Alfa")
        self.outro_modelo = ModeloEtiqueta.objects.create(configuracao=self.outra_configuracao, nome="Etiqueta Beta")
        EventoDispositivoTerminal.objects.create(
            terminal=self.terminal,
            tipo="impressora",
            status="ok",
            mensagem="Evento Alfa",
        )
        EventoDispositivoTerminal.objects.create(
            terminal=self.outro_terminal,
            tipo="impressora",
            status="erro",
            mensagem="Evento Beta",
        )

    def test_admin_visualiza_somente_terminais_eventos_e_impressoes_da_empresa(self):
        terminais = self.client.get("/configuracoes/terminais-pdv/")
        diagnosticos = self.client.get("/configuracoes/terminais-pdv/diagnosticos/")
        diagnosticos_csv = self.client.get("/configuracoes/terminais-pdv/diagnosticos/exportar.csv")
        impressoes = self.client.get("/configuracoes/impressoes/")
        impressoras = self.client.get("/configuracoes/impressoes/impressoras-locais.json").json()
        desktop = self.client.get("/configuracoes/impressoes/desktop.json").json()

        self.assertContains(terminais, "Caixa Alfa")
        self.assertNotContains(terminais, "Caixa Beta")
        self.assertNotContains(terminais, "Liberar licenca")
        self.assertContains(diagnosticos, "Evento Alfa")
        self.assertNotContains(diagnosticos, "Evento Beta")
        self.assertIn("Evento Alfa", diagnosticos_csv.content.decode("utf-8-sig"))
        self.assertNotIn("Evento Beta", diagnosticos_csv.content.decode("utf-8-sig"))
        self.assertContains(impressoes, "Impressora Alfa")
        self.assertNotContains(impressoes, "Impressora Beta")
        self.assertContains(impressoes, "Etiqueta Alfa")
        self.assertNotContains(impressoes, "Etiqueta Beta")
        self.assertEqual(impressoras["impressoras_cadastradas"], ["Impressora Alfa"])
        self.assertEqual([item["empresa_id"] for item in desktop["configuracoes"]], [self.empresa.pk])

    def test_admin_nao_acessa_nem_referencia_objetos_de_outra_empresa(self):
        urls_protegidas = [
            f"/configuracoes/terminais-pdv/{self.outro_terminal.pk}/editar/",
            f"/configuracoes/impressoes/{self.outra_configuracao.pk}/editar/",
            f"/configuracoes/impressoes/modelos-etiqueta/{self.outro_modelo.pk}/editar/",
            f"/configuracoes/impressoes/modelos-etiqueta/{self.outro_modelo.pk}/teste.json",
        ]
        for url in urls_protegidas:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(f"/configuracoes/terminais-pdv/{self.outro_terminal.pk}/regenerar-chave/").status_code,
            404,
        )

        terminal_form = self.client.get("/configuracoes/terminais-pdv/novo/").context["form"]
        impressao_form = self.client.get("/configuracoes/impressoes/nova/").context["form"]
        modelo_form = self.client.get("/configuracoes/impressoes/modelos-etiqueta/novo/").context["form"]
        self.assertQuerySetEqual(terminal_form.fields["filial"].queryset, [self.filial])
        self.assertQuerySetEqual(impressao_form.fields["empresa"].queryset, [self.empresa])
        self.assertQuerySetEqual(impressao_form.fields["filial"].queryset, [self.filial])
        self.assertNotIn(self.outra_configuracao, modelo_form.fields["configuracao"].queryset)
        self.assertNotIn(self.outro_terminal, modelo_form.fields["terminal"].queryset)

        tentativa = self.client.post(
            "/configuracoes/terminais-pdv/novo/",
            {"filial": self.outra_filial.pk, "nome": "Caixa invasor", "ativo": "on"},
        )
        self.assertEqual(tentativa.status_code, 200)
        self.assertFalse(TerminalPdv.objects.filter(nome="Caixa invasor").exists())

    def test_lista_de_terminais_limita_cinquenta_por_pagina(self):
        TerminalPdv.objects.bulk_create(
            [TerminalPdv(filial=self.filial, nome=f"Caixa paginado {indice:02d}") for indice in range(51)]
        )
        primeira = self.client.get("/configuracoes/terminais-pdv/")
        segunda = self.client.get("/configuracoes/terminais-pdv/?page=2")

        self.assertEqual(len(primeira.context["pagina"]), 50)
        self.assertEqual(primeira.context["pagina"].paginator.num_pages, 2)
        self.assertEqual(segunda.context["pagina"].number, 2)
        self.assertNotContains(primeira, "Caixa Beta")
class EscopoFormasPagamentoFilialTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Empresa Pagamentos Alfa",
            nome_fantasia="Pagamentos Alfa",
            cnpj="81.111.111/0001-81",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Alfa")
        self.outra_empresa = Empresa.objects.create(
            razao_social="Empresa Pagamentos Beta",
            nome_fantasia="Pagamentos Beta",
            cnpj="82.222.222/0001-82",
        )
        self.outra_filial = Filial.objects.create(empresa=self.outra_empresa, nome="Matriz Beta")
        self.admin = get_user_model().objects.create_user("admin_pagamentos_alfa", password="123")
        PerfilUsuario.objects.create(
            usuario=self.admin,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.gerente = get_user_model().objects.create_user("gerente_pagamentos_alfa", password="123")
        PerfilUsuario.objects.create(
            usuario=self.gerente,
            filial=self.filial,
            tipo=TipoPerfil.GERENTE,
        )
        self.pix = FormaPagamento.objects.create(nome="PIX empresarial", tipo="PIX")
        self.dinheiro = FormaPagamento.objects.create(
            nome="Dinheiro empresarial",
            tipo="DINHEIRO",
            permite_troco=True,
        )
        self.conta = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX Matriz Alfa",
            tipo=TipoContaMovimento.PIX,
        )
        self.outra_conta = ContaMovimentoFinanceiro.objects.create(
            filial=self.outra_filial,
            nome="PIX Matriz Beta",
            tipo=TipoContaMovimento.PIX,
        )

    def test_admin_configura_somente_filial_e_conta_da_propria_empresa(self):
        self.client.force_login(self.admin)
        lista = self.client.get("/configuracoes/formas-pagamento/")

        self.assertContains(lista, "Matriz Alfa")
        self.assertNotContains(lista, "Matriz Beta")
        self.assertNotContains(lista, "Nova forma")
        self.assertEqual(
            FormaPagamentoFilial.objects.filter(filial=self.filial).count(),
            FormaPagamento.objects.count(),
        )
        self.assertFalse(FormaPagamentoFilial.objects.filter(filial=self.outra_filial).exists())

        formulario = self.client.get(
            f"/configuracoes/formas-pagamento/{self.pix.pk}/editar/?filial={self.filial.pk}"
        ).context["form"]
        self.assertQuerySetEqual(formulario.fields["filial"].queryset, [self.filial])
        self.assertIn(self.conta, formulario.fields["conta_movimento_padrao"].queryset)
        self.assertNotIn(self.outra_conta, formulario.fields["conta_movimento_padrao"].queryset)

        resposta = self.client.post(
            f"/configuracoes/formas-pagamento/{self.pix.pk}/editar/",
            {
                "filial": self.filial.pk,
                "conta_movimento_padrao": self.conta.pk,
                "ativo": "on",
            },
        )
        self.assertRedirects(resposta, "/configuracoes/formas-pagamento/")
        configuracao = FormaPagamentoFilial.objects.get(filial=self.filial, forma_pagamento=self.pix)
        self.assertEqual(configuracao.conta_movimento_padrao, self.conta)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CONFIGURAR_FORMA_PAGAMENTO_FILIAL",
                objeto_id=str(configuracao.pk),
            ).exists()
        )

    def test_admin_nao_forja_filial_ou_conta_de_outra_empresa(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(
                f"/configuracoes/formas-pagamento/{self.pix.pk}/editar/?filial={self.outra_filial.pk}"
            ).status_code,
            404,
        )
        resposta = self.client.post(
            f"/configuracoes/formas-pagamento/{self.pix.pk}/editar/",
            {
                "filial": self.filial.pk,
                "conta_movimento_padrao": self.outra_conta.pk,
                "ativo": "on",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "escolha válida")
        self.assertIsNone(
            FormaPagamentoFilial.objects.get(
                filial=self.filial,
                forma_pagamento=self.pix,
            ).conta_movimento_padrao
        )

    def test_gerente_nao_administra_formas_e_admin_nao_cria_catalogo(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get("/configuracoes/formas-pagamento/").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/configuracoes/formas-pagamento/nova/").status_code, 403)
