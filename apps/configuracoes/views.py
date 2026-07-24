import csv
import hashlib
from decimal import Decimal
from io import StringIO
from pathlib import Path
from urllib.parse import urlencode

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.accounts.permissions import SISTEMA, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, ModoImplantacao, StatusEventoEntrada, StatusSincronizacao
from apps.fiscal.models import ConfiguracaoFiscal
from apps.pdv.models import AcessoPdvNuvem, EventoDispositivoTerminal, StatusAcessoPdvNuvem, StatusLicencaTerminal, TerminalPdv
from apps.vendas.models import FormaPagamento

from .forms import ConfiguracaoImpressaoForm, FormaPagamentoForm, ModeloEtiquetaForm, TerminalPdvForm
from .models import ConfiguracaoImpressao, ModeloEtiqueta, TipoDocumentoImpressao
from .services import configuracao_impressao_para, criar_configuracoes_padrao


CHECKLIST_GRUPOS = [
    {
        "titulo": "Base técnica",
        "descricao": "Fundacao do projeto, arquitetura e segurança inicial.",
        "itens": [
            ("Projeto Django com apps modulares", "done", "Estrutura separada por accounts, produtos, estoque, compras, PDV, vendas e relatórios."),
            ("Settings, timezone e ambiente local", "done", "Configuracao por ambiente via .env, segurança de produção, logs e caminhos ajustáveis definidos."),
            ("Modelagem inicial e migrations", "done", "Modelos principais criados para usuários, produtos, estoque, compras, PDV, vendas e auditoria."),
            ("Permissoes por perfil no backend", "done", "Perfis e bloqueios por módulo implementados com tela 403 amigavel."),
            ("Cadastro próprio de empresas e filiais", "done", "Sistema possui telas internas para empresa e filiais, incluindo município, UF e código IBGE fiscal, sem depender do admin padrao."),
            ("Auditoria de ações críticas", "done", "Logs sensíveis possuem tela de consulta com filtros por período, módulo, acao, usuario e exportacao CSV."),
            ("Testes automatizados", "done", "Suíte formal cobre venda com baixa de estoque, pagamento dividido, backup e configuracoes de impressao."),
        ],
    },
    {
        "titulo": "PDV e caixa",
        "descricao": "Fluxo operacional do caixa de supermercado.",
        "itens": [
            ("Tela PDV em layout de operador", "done", "PDV sem sidebar, cabendo em 100% de zoom no desktop testado."),
            ("Venda com carrinho e baixa de estoque", "done", "Venda finaliza com itens, pagamentos e baixa automatica."),
            ("Pagamento dividido", "done", "Popup aceita múltiplas formas e calcula restante/troco. Atalhos F1/F2/F3/F4 preenchem a linha atual e só criam nova forma quando ainda existe saldo restante; se o pagamento já cobre o total, o PDV avisa o operador em vez de duplicar parcelas automaticamente. Para dois cartões, PIX + cartão ou outra divisão real, o operador informa o valor parcial e adiciona a próxima forma, ficando cada parcela registrada na venda."),
            ("PIX no pagamento do PDV", "done", "Forma PIX prevista nos dados iniciais e disponivel dentro da escolha de pagamento eletrônico do F3."),
            ("Campos monetarios no PDV", "done", "Pagamento, fechamento, sangria e suprimento exibem prefixo R$ e valor de pagamento ganhou campo maior."),
            ("Cliente avulso", "done", "Venda presencial pode finalizar sem cliente identificado."),
            ("DAV / pré-venda", "done", "Criacao, listagem, recibo, carregamento no PDV e cancelamento com supervisor."),
            ("Reimpressao de cupom", "done", "Detalhe da venda e modal de estorno/vendas recentes no PDV possuem acao separada para reimprimir o cupom ja registrado, usando a impressora do app desktop quando disponivel ou fallback do navegador, sem recriar venda, sem movimentar estoque e sem reabrir gaveta de dinheiro. No modal de estorno, a lista mostra somente vendas em cards compactos com largura controlada e paginação interna; as ações Abrir, Reimprimir e Estornar ficam em painel fixo da venda selecionada. Setas selecionam a venda, PageUp/PageDown trocam pagina, Enter abre o detalhe, F10 reimprime, F6 abre o estorno da venda selecionada e Ctrl+Enter confirma o estorno quando o formulário estiver preenchido. Cada reimpressao fica registrada na auditoria com usuario, venda, origem e IP."),
            ("Abertura e fechamento de caixa", "done", "Operador abre/fecha; supervisor/admin confere depois. Modal de caixas no PDV possui atalhos de teclado: F2 abre caixa ou foca suprimento, F5 foca fechamento, setas selecionam caixas da lista, Enter abre o caixa selecionado e Ctrl+Enter confirma o formulário ativo."),
            ("Sangria e suprimento", "done", "Exigem senha de supervisor/admin e geram lançamentos automáticos de saída/entrada no livro financeiro da conta Caixa PDV. No modal de caixas, F2 foca suprimento, F3 foca sangria e Ctrl+Enter registra o movimento com os campos preenchidos."),
            ("Estorno no PDV", "done", "PDV possui atalho F6 para cancelamento total de venda recente com motivo e senha de supervisor/admin; devolucao parcial segue pela tela da venda."),
            ("Operacao principal por teclado", "done", "Enter inclui produto; F2-F9 acessam funções; no carrinho, setas selecionam o produto mesmo quando o foco esta em outro campo, Del reduz uma unidade do item selecionado e remove a linha apenas quando zerar, e Ctrl+Del limpa a venda com confirmacao; no pagamento, Shift+ adiciona forma, Del remove forma e Enter confirma; Shift+M retorna ao menu."),
            ("Bip e retorno automático de foco", "done", "Leitor envia Enter, inclui o produto, soma repetições e devolve o foco ao campo após o recarregamento."),
            ("Alertas rapidos no PDV", "done", "Mensagens simples viram toasts temporarios; operações críticas continuam exigindo confirmacao ou supervisor."),
            ("Autorizacao do PDV em nuvem", "done", "Operador comum fica bloqueado em ambiente de nuvem, tentativa gera solicitacao, admin/gerente recebe alerta visual no topo/menu e decide pelo painel de aprovacao."),
            ("Arquitetura PDV desktop local", "partial", "PDV dos caixas deve ser um aplicativo instalado na máquina do operador, fiel ao layout, atalhos e fluxo de venda do PDV web já validado, para que o operador use a mesma experiência nos dois ambientes. O desktop acrescenta integrações locais com impressora, balanca, gaveta e TEF, operacao resiliente e acesso somente ao necessário para venda, pagamento, caixa, consulta e estorno autorizado, sem telas administrativas completas. O app se comunica com o servidor local da loja pela rede interna; esse servidor local conversa com os dispositivos e o banco operacional da filial. Cadastro por filial, chave individual protegida por hash e bootstrap com registro de conexao implementados. O bootstrap diario devolve a configuracao vigente de licenca, TEF, fiscal e balanca para o app instalado se atualizar sem novo pacote. A nuvem/sede sincroniza por API segura, filas e eventos, sem acessar diretamente o banco local do supermercado. Download/ativacao do app desktop deve exigir autorizacao do admin master, pois cada máquina instalada pode representar uma licenca comercial cobrada por terminal; pacote de ativacao so e entregue para terminal com licenca liberada."),
            ("Balanca integrada no PDV", "partial", "Produtos já possuem marcacao de produto pesavel. Terminal PDV agora permite configurar balanca por caixa com protocolo, porta/endereco e modelo; manifesto, pacote JSON e bootstrap do app desktop entregam essa configuracao por máquina usando o contrato pdv_scale_v1, com leitura automatica, unidade KG, precisao de 3 casas, timeout e fallback manual quando a balanca estiver ausente ou falhar. O app desktop já possui ponte local para expor a configuracao da balanca e retornar leitura estruturada com peso simulado para homologacao. A tela do PDV já chama a ponte local pelo botão Peso e atalho F12, preenchendo a quantidade quando recebe o peso ou orientando digitacao manual no navegador comum. Falhas e retornos manuais da balanca ficam registrados no log local devices.log.jsonl da máquina do caixa e podem ser consultados pela ponte deviceLogs; a Central do App PDV desktop já possui leitura visual desse diagnóstico quando aberta dentro do aplicativo instalado. O servidor já possui endpoint autenticado por terminal para receber lotes de diagnósticos locais e armazenar EventoDispositivoTerminal por caixa, e o app desktop tenta enviar automaticamente os eventos ainda não sincronizados na inicializacao sem bloquear a abertura do PDV. A Central do App PDV desktop agora exibe histórico consolidado dos eventos recebidos pelo servidor, com resumo por tipo/status e últimos eventos por terminal. Falta conectar o driver físico serial/TCP e ler peso automaticamente no PDV real."),
            ("TEF/API de maquininha", "partial", "Pagamentos possuem estados controlados, ID externo, NSU e autorizacao; venda rejeita transacao pendente, recusada ou estornada. Terminais PDV agora configuram provedor TEF e modo de integracao por adaptador, permitindo PagBank, Cielo, Stone, Getnet, Rede, SiTef ou outro fornecedor sem prender o sistema a uma operadora. O bootstrap do app desktop expõe o contrato pdv_tef_v1 com tipos crédito, débito e PIX dinâmico e retorno esperado. No PDV, pagamento eletrônico chama a ponte processPayment do app desktop, aguarda resposta da maquininha/simulador, grava transacao, NSU e autorizacao na linha de pagamento e bloqueia a finalizacao se não houver retorno confirmado; terminal sem TEF configurado retorna aviso ao operador. O app desktop possui simulador TEF rastreável para desenvolvimento enquanto o adaptador real da adquirente não estiver conectado, incluindo pagamento e refundPayment para estorno autorizado pela maquininha, e grava eventos locais tef em devices.log.jsonl, além de tef_estorno, para diagnóstico central de aprovações, falhas e terminais sem maquininha configurada."),
            ("Reversão de pagamento misto", "partial", "Cancelamento total estorna parcelas locais e marca PIX/TEF com transacao externa como estorno pendente, preservando motivo e rastreabilidade. A tela da venda permite confirmar o estorno eletrônico aprovado pela operadora com senha de supervisor/admin; ao confirmar, o pagamento vira estornado, o lançamento financeiro original recebe lançamento inverso e a auditoria registra a transação. Devoluções parciais agora rateiam o valor devolvido entre os pagamentos confirmados da venda e geram lançamentos financeiros inversos proporcionais, sem marcar a parcela inteira como estornada. Falta automatizar a chamada direta ao fornecedor/adquirente para devoluções eletrônicas parciais."),
            ("Padrão R$ em todos os formulários", "done", "Campos numéricos de preço, valor, custo, desconto, taxa, frete e total recebem automaticamente o prefixo R$ no PDV e nas telas administrativas."),
        ],
    },
    {
        "titulo": "Produtos, estoque e compras",
        "descricao": "Cadastros e controle físico/financeiro do estoque.",
        "itens": [
            ("Produtos, categorias e marcas", "done", "Cadastro, edição, busca, importacao CSV, etiquetas, kardex e formulários auxiliares com orientacao de uso operacional."),
            ("Pendências fiscais de produtos", "done", "Tela fiscal lista produtos com NCM, CEST, origem, CST/CSOSN ou alíquota pendentes e direciona para correção do cadastro."),
            ("Promoções", "done", "Preco vigente considera promocao ativa; formulário destaca produto, preço promocional, vigência e status para uso automático no PDV."),
            ("Estoque por filial", "done", "Saldo físico, reservado e disponivel por produto/filial."),
            ("Inventário", "done", "Contagem e aplicacao com autorizacao de supervisor/admin."),
            ("Perdas", "done", "Baixa de perdas com supervisor/admin e log."),
            ("Movimentacao manual", "done", "Entrada/saída/ajuste/reserva com supervisor/admin, auditoria e formulário separado entre operacao e autorizacao."),
            ("Compras", "done", "Entrada de compra com dados da nota, itens recebidos, rascunho sem movimentar estoque, finalizacao direta com supervisor/admin, atualizacao automatica de estoque, custo do produto, movimentacao de entrada e conta a pagar, baixa direta da conta vinculada com retorno para a entrada, rastreio financeiro da baixa no detalhe da compra, impressão/PDF individual auditável da entrada com itens, financeiro, rastreio financeiro do livro e rastreio de estoque, lista operacional separada do relatório com situacao financeira da entrada, retorno seguro do detalhe e da edição de rascunho para a lista filtrada, filtros por status da entrada e situacao financeira aberta, paga, cancelada, vencida ou sem conta, exportacao Excel/CSV e impressão/PDF da visão operacional filtrada, limpeza rapida de filtros ativos, chips visuais dos filtros aplicados, cards de resumo financeiro de contas abertas, vencidas e pagas com atalho para filtro preservando busca e status atuais, alerta de rascunhos pendentes, rastreio no estoque da entrada com movimentações de entrada e cancelamento vinculadas, e cancelamento protegido de compra finalizada com reversao de estoque, cancelamento da conta aberta, bloqueio quando a conta já foi paga, bloqueio quando o produto já foi consumido a ponto de não existir saldo para reverter e aviso antecipado desses bloqueios na tela da entrada."),
            ("Etiquetas de gôndola profissionais", "partial", "O documento complementar de etiquetas foi incorporado ao checklist. A tela busca por nome, código de barras e SKU, aceita leitor que envia Enter, cópias por produto e modelos compacto 110x30 mm, completo 100x50 mm, A4 e modelos profissionais salvos por empresa, filial e terminal, sempre sem fundo colorido forçado. Configuracao inclui medidas, gaps, colunas, orientacao, DPI, mídia, impressora e linguagem; a tela envia o lote ao agente desktop, que gera ZPL, EPL, PPLA ou PPLB e imprime em RAW sem pré-visualizacao. Ainda faltam testes com equipamentos físicos."),
            ("Desmembramento e fracionamento de produtos", "partial", 'Novo documento complementar incorporado ao checklist para estoque avançado. A frente ja possui models DesmembramentoProduto, ItemDesmembramentoProduto e ReceitaDesmembramento, receitas/conversões por empresa/filial, busca remota por código de barras, SKU e nome, simulação antes de confirmar, múltiplos destinos, lote/validade, rendimento esperado e alerta de rendimento abaixo do previsto. O serviço transacional faz baixa da origem, entrada dos destinos vendáveis ou subprodutos, descarte/perda vinculada sem aumentar saldo vendável, custo proporcional, auditoria e cancelamento seguro com movimentos inversos. As telas de lista, detalhe e receitas exibem quantidades no padrão brasileiro com quantidade_br, evitando 1,000 ou 20,000 quando o valor representa unidade inteira. Também foram iniciados kits/composições, produção interna, planejamento por demanda mínima, ordens de produção por setor, etapas, responsáveis, SLA, fila operacional, alertas auditáveis e relatórios/CSV gerenciais. Ainda faltam homologar fluxos reais de açougue, padaria e hortifruti com operação de loja.'),
        ],
    },
    {
        "titulo": "Relatórios e gestão",
        "descricao": "Visão administrativa para acompanhamento da operacao.",
        "itens": [
            ("Dashboard", "done", "Indicadores principais e atalhos por perfil."),
            ("Relatórios de vendas", "done", "Periodo, faturamento, descontos, devoluções e produtos vendidos."),
            ("Curva ABC e reposição", "done", "Analises para decisão de compra e estoque."),
            ("Relatórios de caixas", "done", 'Abertos, aguardando conferência, conferidos, declarado e conferido. Relatório de caixas/PDV por funcionário possui filtro por operador, resumo por operador com caixas, vendas, total vendido, sangrias, suprimentos, saldo operacional, valores inicial/declarado/conferido, diferença de conferência por caixa e por operador, formas de pagamento no relatório impresso/PDF, exportação Excel/CSV com valores monetários em duas casas e impressão/PDF preservando o filtro.'),
            ("Relatórios de perdas/devoluções/compras", "done", "Telas especificas criadas por período."),
            ("Exportacoes", "done", "Relatórios operacionais e gerenciais exportam CSV compativel com Excel e possuem versao para PDF."),
            ("Gráficos de pizza no dashboard", "done", "Dashboard usa Chart.js para composição por forma de pagamento, categorias e status dos caixas."),
        ],
    },
    {
        "titulo": "Revisão complementar v2",
        "descricao": "Requisitos acrescentados pelo documento de usabilidade, cadastros e entrega.",
        "itens": [
            ("Login sem caixa alta", "done", "Usuario, e-mail e senha preservam a digitacao original na tela de acesso."),
            ("Busca inteligente/autocomplete", "done", "PDV possui buscas locais por teclado; Select2 aplicado em filial, produto, fornecedor, cliente, categoria e marca nos formulários mais extensos. A busca remota por API foi ativada no Select2, com endpoints JSON para produtos, clientes, fornecedores, filiais, categorias e marcas, uso em compras, financeiro, marketplace, produtos, etiquetas e configuracoes, filtro para produtos vendidos no marketplace e permissões coerentes com os módulos operacionais."),
            ("Consulta de CNPJ e CEP", "partial", "Formularios de empresa e filial possuem mascaras, avisos, campo auxiliar de CEP, botao de consulta CNPJ/CEP, contrato JSON cadastro_lookup_v1, validacao formal de CNPJ, validacao de CEP, reaproveitamento de dados locais de empresas/filiais por CNPJ ou CEP e preenchimento automatico dos campos vazios quando houver cadastro local correspondente. O endpoint aceita provedores HTTP externos configurados por CADASTRO_CNPJ_PROVIDER_URL, CADASTRO_CEP_PROVIDER_URL e CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS, normaliza respostas de CNPJ/CEP, preserva fallback local/offline e retorna erro controlado quando o servico externo falhar. O front aplica tanto retorno local quanto retorno externo. Falta escolher e homologar a API oficial de producao para CNPJ e CEP."),
            ("Cadastros complementares padronizados", "done", "Clientes, fornecedores, produtos e usuários possuem formulários organizados por seções operacionais, com textos de apoio para PDV, compras e etapas futuras."),
            ("Imagens de produto", "done", "Foto principal e galeria adicional com legenda, ordenacao e remoção integradas ao cadastro e preparadas para exibicao no marketplace."),
            ("Políticas de entrega por filial", "partial", "Raio, faixas por distancia, pedido mínimo, frete grátis, bairros e horarios configuraveis implementados. O cálculo de entrega agora valida bairros atendidos e bloqueados, exigindo bairro quando a filial possui area atendida restrita. A tela de politicas permite simular subtotal, distancia manual, endereco para geocodificacao e bairro por filial usando a mesma regra do pedido real. O diagnóstico JSON informa o contrato delivery_geocode_v1, se MARKETPLACE_GEOCODING_PROVIDER_URL está configurado, timeout e fallback manual de distancia. O endpoint de status do parceiro marketplace_partner_v1 agora expõe a politica delivery_policy_v1 da filial, com retirada, entrega, raio, pedido minimo, frete gratis, bairros, faixas, geocoding e alertas antes do pedido real. Falta escolher e homologar provedor de mapa/rota de produção."),
            ("Certificado digital protegido", "done", "Configuracao fiscal aceita upload A1 .pfx/.p12, criptografa arquivo e senha, lê validade e mostra alertas de vencimento."),
            ("Identidade visual do supermercado", "done", "Logo no topo, marca d'água sutil no carrinho e paleta operacional restrita implementadas."),
        ],
    },
    {
        "titulo": "Etiquetas e impressoras profissionais",
        "descricao": "Requisitos do documento complementar de etiquetas de gôndola e impressoras profissionais.",
        "itens": [
            ("Modelo compacto 110x30", "done", "Modelo recomendado para gôndola horizontal criado no MVP, priorizando nome do produto, código de barras ou código interno, unidade e preço grande, sem foto, icones decorativos ou excesso de informacao."),
            ("Modelo completo 100x50", "done", "Modelo maior disponivel para etiquetas com mais espaco, mantendo preço como informacao principal e deixando logo, tributos e preço de referência como evolucao configuravel."),
            ("Busca por código de barras nas etiquetas", "done", "Campo de busca aceita digitacao manual e leitor como teclado, mantendo foco automático; a consulta prioriza código de barras/EAN/GTIN e código interno/SKU antes do nome."),
            ("Impressao em medidas reais", "done", "CSS de impressão usa medidas em mm, @media print e oculta menu, filtros e botoes; a cor da etiqueta fica a cargo do papel físico, com impressão limpa em preto."),
            ("Configuracao profissional de etiquetas", "partial", "Configuracao por empresa/filial persiste impressora, DPI, densidade, velocidade, mídia e linguagem. Modelos nomeados guardam largura, altura, gaps, colunas, orientacao, modelo padrao e vínculo opcional ao terminal; a tela de etiquetas aplica o modelo escolhido e o endpoint desktop sincroniza todos os parâmetros. A central de impressão também prepara etiqueta de teste por modelo para envio direto pelo app desktop. Ainda faltam testes físicos com equipamentos reais."),
            ("Linguagens nativas de impressoras", "partial", "Arquitetura contempla ZPL, EPL, PPLA e PPLB. A tela web monta um payload confiável no contrato label_print_v1, com modelo, produtos e cópias em chaves ASCII, e aciona printLabels somente no app desktop; o agente gera ZPL, EPL, PPLA ou PPLB, converte medidas por DPI e envia ao spooler Windows em RAW com limite e retorno visível. No navegador permanece a impressão convencional. O teste de modelo usa a mesma ponte local e o mesmo contrato do lote real. Ainda faltam homologacao por modelo e testes físicos."),
        ],
    },
    {
        "titulo": "Próximas fases",
        "descricao": "Itens previstos na documentacao, ainda fora do MVP atual.",
        "itens": [
            ("Fiscal/NFC-e e NF-e", "partial", "Fila fiscal mostra vendas prontas, pendencias antes da acao e ultima tentativa automatica auditada; tela de produtos fiscais antecipa correcoes de NCM, CEST, origem, CST/CSOSN e alíquota. XML local usa UF e código IBGE da filial. A NFC-e segue a regra de ocorrer somente após pagamento confirmado: por padrao a venda tenta preparar a NFC-e automaticamente, mas o admin pode desativar essa tentativa por terminal PDV quando a empresa decidir operar aquele caixa sem comunicacao fiscal automatica. O PDV exibe no topo se o terminal identificado esta com fiscal automático ligado ou desligado. A venda presencial agora aceita CPF opcional na nota sem cadastro de cliente, pergunta o documento dentro do popup de pagamento, grava o dado na venda e inclui o CPF no XML local da NFC-e; CNPJ solicitado no caixa é bloqueado para NFC-e automática e orientado para NF-e modelo 55. Pedidos online/marketplace agora possuem documento do destinatário e podem preparar NF-e modelo 55 local, com série e natureza fiscal próprias, vinculada ao pedido. Painel fiscal agora traz prontidão por filial, certificado, séries, vendas aguardando documento, produtos com pendência e diagnóstico JSON para suporte. Se faltar cadastro fiscal, a venda não trava e a pendencia fica auditada para correção. Transmissao simulada em homologacao gera chave, protocolo e auditoria, mas ainda faltam assinatura, schema oficial, transmissão SEFAZ real, captura de CPF/CNPJ pelo pinpad quando o TEF permitir e contingência quando a SEFAZ estiver indisponivel. Exportacao operacional de contingencia JSON agora gera pacote fiscal_contingencia_v1 com documentos prontos, rejeitados ou cancelados, XML, origem, filial, valores e auditoria, sem substituir assinatura ou autorizacao oficial da SEFAZ."),
            ("Financeiro completo", "partial", "Contas a pagar/receber, baixas, cancelamentos, categorias, fluxo de caixa, conciliacao PDV x financeiro, contas de movimento, vendas a vista do PDV no livro, transferencias entre contas, livro financeiro imutavel, estornos por lancamento inverso, resultado por receitas/despesas, cards gerenciais e exportacoes criadas. Resultado financeiro agora inclui visao por origem, categoria, conta de movimento, saldos por filial, balancete gerencial com saldo anterior, entradas, saidas e saldo final por conta, DRE gerencial com receita operacional, despesas, resultado e margem operacional, com CSV gerencial para Excel. A proxima evolucao inclui integracao final com fiscal/contábilidade e relatórios contábeis oficiais."),
            ("Entradas, saídas e livro contábil", "partial", "Contas de movimento por filial para caixa físico, banco, PIX e outras foram criadas com saldo inicial e saldo atual. Baixas geram entrada ou saída no livro imutavel, vendas a vista do PDV geram entradas automaticas por forma de pagamento, sangria e suprimento geram saída/entrada automatica no Caixa PDV, transferencias geram lançamentos espelhados, atômicos e auditados entre contas da mesma empresa, e estornos rastreáveis criam lancamento inverso sem alterar o original. O livro possui origem, usuario, data, filtros, exportacao CSV, validacao de saldo, relatório de receitas, despesas e resultado que ignora transferencias internas, e balancete gerencial que considera transferencias para refletir o saldo real das contas. Ainda faltam integracao automatica de origens fiscais/contábeis avancadas e relatórios contábeis oficiais. Referencia funcional identificada no ProjetoLimpoGitHub para migracao adaptada, sem alterar o projeto original."),
            ("Marketplace / pedido online", "partial", "Fluxo operacional completo, API segura com chave por plataforma, validacao de itens, idempotencia e acompanhamento visual de separacao/pagamento na listagem implementados. Pedidos agora guardam CPF, CNPJ ou documento estrangeiro do destinatário, inclusive pela API do parceiro, e o detalhe do pedido permite preparar NF-e modelo 55 local vinculada ao pedido online. A central de integracoes agora mostra saude operacional por canal, pedidos recebidos, pedidos abertos, pagamentos pendentes, alertas de homologacao e diagnostico JSON para suporte sem expor a chave completa. API de parceiros tambem possui endpoint autenticado marketplace_partner_v1 para validar chave, filial, recursos, idempotencia e alertas antes de enviar pedido real. Adaptadores especificos de cada parceiro e transmissão SEFAZ real seguem pendentes."),
            ("Impressao personalizada", "done", "Configuracoes de papel, margens, fonte, rodape, vias e impressão automatica aplicadas aos recibos. No app desktop, o botão pos-venda usa o payload autenticado existente, monta cupom operacional sem imagens e envia diretamente ao spooler Windows em RAW/ESC-POS, com até três vias, corte de papel e pulso opcional da gaveta, sem abrir pré-visualizacao."),
            ("Descoberta de impressoras locais", "done", "Central de impressão possui campo com sugestões e endpoint de configuracao. A ponte do app desktop consulta as impressoras instaladas no Windows sem shell interativo e devolve nome, porta, driver, estado e impressora padrao para a mesma interface do PDV, tratando timeout ou falha sem bloquear a venda."),
            ("Gaveta de dinheiro opcional", "partial", "Central de impressão permite habilitar ou desabilitar gaveta automatica por empresa/filial e documento de caixa. Bootstrap e pacote do terminal entregam o contrato pdv_cash_drawer_v1 com impressora, abertura em dinheiro e movimentos de caixa. O app desktop possui ponte openCashDrawer, envia pulso ESC/POS pela impressora configurada e registra diagnóstico local da gaveta em sucesso, falha ou desabilitado sem bloquear a venda. Venda em dinheiro, sangria, suprimento, abertura e fechamento de caixa agendam abertura somente depois da operacao ser aceita pelo servidor, preservando senha de supervisor/admin quando exigida. Falta testar com gavetas físicas reais."),
            ("Backup/restauracao operacional", "done", "Tela de backup JSON e roteiro de restauracao segura disponíveis em Sistema."),
            ("Modo local administrativo", "partial", "Para supermercados sem internet ou sem rede estruturada, o produto deve permitir instalação local do servidor administrativo na própria loja, em um computador servidor ou máquina principal, acessado por navegador em localhost ou rede interna. Não é necessário duplicar todo o ERP em um segundo app desktop administrativo; a abordagem profissional é empacotar o servidor local, banco, serviços, backup, atualizações controladas e um atalho/app shell opcional para abrir o painel administrativo. A central Sistema > Servidor local já apresenta arquitetura, requisitos, modos por empresa, riscos pendentes, manifesto JSON erp_local_admin_v1, guia docs/IMPLANTACAO_SERVIDOR_LOCAL.md e scripts scripts/run_local_server.ps1, scripts/register_local_server_task.ps1, scripts/backup_local.ps1, scripts/register_backup_task.ps1 e scripts/register_sync_task.ps1 para operação local inicial, backup e sincronização recorrente no Windows. O backup local já suporta criptografia opcional AES-256 por BACKUP_ENCRYPTION_PASSPHRASE e remoção do zip aberto com -RemoverOriginalCriptografado. Manifesto e tela do servidor local agora especificam o contrato de servico Windows MercaFlowServidorLocal, comando WSGI via Waitress, healthcheck, restart, logs e fallback operacional. O PDV desktop continua separado e restrito ao operador, enquanto gerente/admin acessa o mesmo sistema web local com permissões completas. Falta gerar instalador assinado, registrar o servico Windows real a partir do contrato e concluir a politica final de sincronizacao opcional com a nuvem."),
            ("Aplicativo desktop/PDF", "partial", "Endpoints de configuracao e payload de impressão da venda preparados para o app desktop, incluindo dados de pagamento eletrônico, NSU, autorizacao e transacao externa para cupom e comprovante. A interface desktop reutiliza o mesmo design, componentes, atalhos e regras do PDV web em um shell WebView separado, adaptando apenas a camada de integracao com hardware e serviços locais. O esqueleto desktop_pdv possui ativacao guiada na primeira execucao, valida o bootstrap licenciado antes de salvar a credencial em LOCALAPPDATA e abrir /pdv/, permite reconfiguracao e protege a chave de versionamento. O build reproduzivel do executavel Windows com PyInstaller também foi preparado. A Central do App PDV desktop publica o instalador somente quando o artefato configurado existe, apresenta tamanho e SHA-256, restringe o download ao admin master e registra a entrega na auditoria. Um script de publicacao atômica confere integridade, impede arquivo parcial na central e grava metadados de versao; versao e caminho do artefato sao configuraveis por ambiente. O app informa sua versao no bootstrap, recebe versao vigente e minima, avisa atualizacao opcional e bloqueia versao insegura; a instalacao continua exigindo o admin master, sem atualizacao automatica fora do licenciamento. O app desktop agora salva cache local do bootstrap autorizado e, se o servidor estiver indisponivel, abre com esse cache somente quando o terminal permite modo offline, registrando diagnostico local; recusa de licença, chave ou terminal bloqueado nunca usa o cache como atalho. O manifesto JSON do app desktop expõe disponibilidade, integridade, contratos e terminais autorizados. Pacote JSON por terminal entrega bootstrap, URL da interface compartilhada, TEF, fiscal, impressão, gaveta, balanca configurada, licenca por máquina e sincronizacao; o bootstrap operacional também devolve a configuracao atual a cada inicializacao. Terminais pendentes, bloqueados ou cancelados não recebem pacote de ativacao nem conseguem inicializar o bootstrap. O aplicativo continua sendo um projeto/artefato separado, baixado por dentro do sistema somente com autorizacao do admin master e configurado com o terminal autorizado. Falta assinar o executavel, gerar o instalador MSI, conectar dispositivos locais e implementar sincronizacao resiliente com servidor local/nuvem."),
            ("Sincronizacao loja-nuvem", "partial", "Empresa escolhe entre servidor local, hibrido e nuvem com agente. Caixa de saída, processador HTTP e caixa de entrada autenticada usam UUID, idempotencia, token fora do banco, timeout, lotes e retentativa exponencial. Eventos recebidos ficam armazenados antes de alterar dados e já passam por processador interno com handlers por tipo, erro controlado para domínios ainda não implementados, handler inicial de produtos, handler de saldo de estoque por filial, espelho de venda finalizada com painel de retaguarda, espelho fiscal sincronizado, detalhe auditável de eventos com payload e diagnóstico, resolução manual de conflitos com responsável e decisão registrada, exportacao CSV das filas de saída e entrada, diagnóstico JSON operacional com filas, alertas, próximos eventos, idade da fila mais antiga, eventos de sa?da com tentativas esgotadas, empresas por modo e comando sugerido, comando único agendável, roteiro do Agendador de Tarefas do Windows no painel e script scripts/register_sync_task.ps1 para registrar a rotina recorrente. Politica automatica opcional de conflito por empresa foi iniciada: manual por padrao, com nuvem prevalecendo apenas para produtos e saldo de estoque quando configurado, mantendo venda e fiscal para decisao auditavel; painel, diagnostico JSON, listagem de empresas e detalhe auditavel do evento exibem a politica aplicada, e o admin tecnico permite filtrar esse campo. Ainda faltam transmissao SEFAZ real e politicas finais para outros tipos de conflito."),
            ("Super admin personalizado", "partial", "Painel próprio centraliza empresas, usuários, fiscal, formas de pagamento, impressoes, backup, auditoria e checklist, sem atalho visual para o admin Django. A tela Sistema > Super admin já reúne visão executiva, atalhos críticos, pendências acionáveis, saúde da sincronização, cobertura de telas próprias, atividade recente, atalhos de investigação, diagnóstico de ambiente/segurança, inventário de modelos, diagnóstico JSON e exportação CSV restritos ao admin master para acompanhar dados avançados sem entrar no admin padrão; ainda faltam telas CRUD internas para alguns modelos avançados de baixa frequência."),
        ],
    },
]


def _instalador_pdv_desktop():
    caminho = settings.PDV_DESKTOP_INSTALLER_PATH
    if not caminho.is_file():
        return {
            "disponivel": False,
            "nome": caminho.name,
            "tamanho": 0,
            "sha256": "",
            "atualizado_em": None,
        }
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    stat = caminho.stat()
    return {
        "disponivel": True,
        "nome": caminho.name,
        "tamanho": stat.st_size,
        "sha256": digest.hexdigest(),
        "atualizado_em": timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
    }

DOCUMENTOS_PROJETO = [
    ("Complementar PDV, usabilidade, cadastros e entrega v2", "docs/protótipos/documento_complementar_pdv_usabilidade_cadastros_entrega_v2.docx"),
    ("Complementar desmembramento e fracionamento de produtos", "docs/protótipos/documento_complementar_desmembramento_fracionamento_produtos.docx"),
    ("Complementar etiquetas de gôndola e impressoras profissionais v2", "docs/protótipos/documento_complementar_etiquetas_gôndola_impressoras_profissionais_v2.docx"),
    ("Índice dos documentos finais", "docs/protótipos/00_indice_documentos_finais_supermercado.docx"),
    ("Arquitetura técnica", "docs/protótipos/01_arquitetura_técnica_sistema_supermercado.docx"),
    ("Modelagem banco de dados", "docs/protótipos/02_modelagem_banco_dados_sistema_supermercado.docx"),
    ("Regras de negócio", "docs/protótipos/03_regras_negócio_sistema_supermercado.docx"),
    ("MVP por fases", "docs/protótipos/04_mvp_por_fases_sistema_supermercado.docx"),
    ("Checklist de desenvolvimento", "docs/protótipos/05_checklist_desenvolvimento_sistema_supermercado.docx"),
    ("Mapa de telas e fluxos", "docs/protótipos/06_mapa_telas_fluxos_sistema_supermercado.docx"),
    ("Backup e restauracao", "docs/PLANO_BACKUP_RESTAURACAO_SUPERMERCADO.md"),
]
PDV_DESKTOP_VERSAO_PLANEJADA = settings.PDV_DESKTOP_VERSION


def _usuario_admin_master(user):
    if user.is_superuser:
        return True
    perfil = getattr(user, "perfil_supermercado", None)
    if perfil and perfil.is_active and perfil.tipo == TipoPerfil.ADMINISTRADOR:
        return True
    return False


def _exigir_admin_master(user):
    if _usuario_admin_master(user):
        return
    raise PermissionDenied


def _resumo_checklist(grupos):
    totais = {"done": 0, "partial": 0, "todo": 0}
    for grupo in grupos:
        grupo_totais = {"done": 0, "partial": 0, "todo": 0}
        for _, status, _ in grupo["itens"]:
            totais[status] += 1
            grupo_totais[status] += 1
        grupo["total"] = len(grupo["itens"])
        grupo["concluidos"] = grupo_totais["done"]
        grupo["parciais"] = grupo_totais["partial"]
        grupo["pendentes"] = grupo_totais["todo"]
        grupo["percentual"] = round((grupo_totais["done"] / grupo["total"]) * 100) if grupo["total"] else 0
        grupo_pontos = grupo_totais["done"] + (grupo_totais["partial"] * 0.5)
        grupo["percentual_ponderado"] = round((grupo_pontos / grupo["total"]) * 100) if grupo["total"] else 0
    total_itens = sum(totais.values())
    pontos = totais["done"] + (totais["partial"] * 0.5)
    return {
        "total": total_itens,
        "concluidos": totais["done"],
        "parciais": totais["partial"],
        "pendentes": totais["todo"],
        "percentual": round((totais["done"] / total_itens) * 100) if total_itens else 0,
        "percentual_ponderado": round((pontos / total_itens) * 100) if total_itens else 0,
    }


def _proximas_etapas_checklist(grupos, limite=6):
    proximas = []
    for grupo in grupos:
        for titulo, status, descricao in grupo["itens"]:
            if status == "partial":
                classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao)
                proximas.append(
                    {
                        "grupo": grupo["titulo"],
                        "titulo": titulo,
                        "descricao": descricao,
                        **classificacao,
                    }
                )
    return proximas[:limite]


def _classificar_etapa_roadmap(grupo, titulo, descricao):
    titulo_texto = titulo.lower()
    texto = f"{grupo} {titulo} {descricao}".lower()
    if any(chave in titulo_texto for chave in ["balanca", "gaveta", "impressora", "etiqueta", "zpl", "epl", "ppla", "pplb"]):
        return {
            "trilha": "Dispositivos",
            "prioridade": "Média",
            "acao": "Planejar teste em equipamento real e manter fallback manual para o operador.",
        }
    if any(chave in titulo_texto for chave in ["tef", "maquininha", "pagamento misto"]):
        return {
            "trilha": "Hardware/TEF",
            "prioridade": "Alta",
            "acao": "Homologar o adaptador TEF com provedor escolhido e manter simulador para desenvolvimento.",
        }
    if any(chave in texto for chave in ["arquitetura pdv desktop", "servidor local", "desktop", "instalador", "windows", "sincronizacao", "sincronização"]):
        return {
            "trilha": "Implantacao",
            "prioridade": "Alta",
            "acao": "Fechar pacote instalavel, servico local e politica de sincronizacao/atualizacao.",
        }
    if any(chave in texto for chave in ["sefaz", "certificado", "nf-e", "nfc-e", "fiscal"]):
        return {
            "trilha": "Fiscal",
            "prioridade": "Alta",
            "acao": "Separar homologacao fiscal, certificado, series e contingencia antes da transmissao real.",
        }
    if any(chave in texto for chave in ["maquininha", "tef", "adquirente", "pix dinâmico", "pagbank", "cielo", "stone", "getnet", "rede", "sitef"]):
        return {
            "trilha": "Hardware/TEF",
            "prioridade": "Alta",
            "acao": "Homologar o adaptador TEF com provedor escolhido e manter simulador para desenvolvimento.",
        }
    if any(chave in texto for chave in ["balanca", "gaveta", "impressora", "etiqueta", "zpl", "epl", "ppla", "pplb", "equipamentos físicos"]):
        return {
            "trilha": "Dispositivos",
            "prioridade": "Média",
            "acao": "Planejar teste em equipamento real e manter fallback manual para o operador.",
        }
    if any(chave in texto for chave in ["financeiro", "contáb", "contabil", "livro"]):
        return {
            "trilha": "Financeiro",
            "prioridade": "Média",
            "acao": "Consolidar relatórios contabeis e conciliar origem fiscal, PDV e livro financeiro.",
        }
    if any(chave in texto for chave in ["api externa", "geocodificacao", "marketplace", "adaptadores"]):
        return {
            "trilha": "Integracoes",
            "prioridade": "Média",
            "acao": "Escolher fornecedor/API, definir contrato e deixar fallback operacional.",
        }
    return {
        "trilha": "Produto",
        "prioridade": "Média",
        "acao": "Quebrar em tarefa menor, implementar no sistema e cobrir com teste automatizado.",
    }


def _mapa_trilhas_roadmap(grupos):
    trilhas = {}
    for grupo in grupos:
        for titulo, status, descricao in grupo["itens"]:
            if status != "partial":
                continue
            classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao)
            trilha = classificacao["trilha"]
            item = trilhas.setdefault(
                trilha,
                {
                    "trilha": trilha,
                    "total": 0,
                    "alta": 0,
                    "media": 0,
                    "grupos": set(),
                    "acao": classificacao["acao"],
                },
            )
            item["total"] += 1
            item["grupos"].add(grupo["titulo"])
            if classificacao["prioridade"] == "Alta":
                item["alta"] += 1
            else:
                item["media"] += 1
    ordenadas = sorted(trilhas.values(), key=lambda item: (-item["alta"], -item["total"], item["trilha"]))
    for item in ordenadas:
        item["grupos"] = ", ".join(sorted(item["grupos"]))
    return ordenadas


def _filtrar_checklist(grupos, *, termo="", status="", grupo_titulo="", trilha="", prioridade=""):
    termo = (termo or "").strip().lower()
    status = (status or "").strip()
    grupo_titulo = (grupo_titulo or "").strip()
    trilha = (trilha or "").strip()
    prioridade = (prioridade or "").strip()
    filtrados = []
    for grupo in grupos:
        if grupo_titulo and grupo["titulo"] != grupo_titulo:
            continue
        itens = []
        for titulo, item_status, descricao in grupo["itens"]:
            if status and item_status != status:
                continue
            if trilha or prioridade:
                if item_status != "partial":
                    continue
                classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao)
                if trilha and classificacao["trilha"] != trilha:
                    continue
                if prioridade and classificacao["prioridade"] != prioridade:
                    continue
            texto = f"{grupo['titulo']} {titulo} {descricao}".lower()
            if termo and termo not in texto:
                continue
            itens.append((titulo, item_status, descricao))
        if itens:
            filtrados.append({**grupo, "itens": itens})
    return filtrados


def _modelos_backup():
    modelos = []
    ignorar = {"Permission", "ContentType", "Session", "LogEntry"}
    for modelo in apps.get_models():
        if modelo._meta.object_name in ignorar:
            continue
        try:
            total = modelo._default_manager.count()
        except Exception:
            total = None
        modelos.append(
            {
                "app": modelo._meta.app_label,
                "modelo": modelo._meta.verbose_name_plural.title(),
                "total": total,
            }
        )
    return sorted(modelos, key=lambda item: (item["app"], item["modelo"]))


@login_required
@role_required(*SISTEMA)
def painel_sistema(request):
    modelos = _modelos_backup()
    total_registros = sum(item["total"] or 0 for item in modelos)
    checklist_grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    resumo_checklist = _resumo_checklist(checklist_grupos)
    configuracoes = ConfiguracaoImpressao.objects.all()
    configs_fiscais = ConfiguracaoFiscal.objects.select_related("filial")
    atalhos = [
        {
            "titulo": "Formas de pagamento",
            "descricao": "Meios aceitos no PDV, troco e autorizacao eletrônica.",
            "icone": "fa-money-check-dollar",
            "url": "configuracoes:formas_pagamento",
            "status": f"{FormaPagamento.objects.filter(ativo=True).count()} ativa(s)",
        },
        {
            "titulo": "Empresas e filiais",
            "descricao": "Cadastro das lojas, logo, UF e código IBGE fiscal.",
            "icone": "fa-building",
            "url": "empresas:lista",
            "status": f"{Filial.objects.count()} filial(is)",
        },
        {
            "titulo": "Usuarios",
            "descricao": "Perfis, permissoes e vínculo de operador com filial.",
            "icone": "fa-user-gear",
            "url": "accounts:usuarios",
            "status": f"{User.objects.filter(is_active=True).count()} ativo(s)",
        },
        {
            "titulo": "Fiscal",
            "descricao": "NFC-e, certificado A1, series, natureza e produtos fiscais.",
            "icone": "fa-receipt",
            "url": "fiscal:documentos",
            "status": f"{configs_fiscais.count()} configuracao(oes)",
        },
        {
            "titulo": "Impressoes",
            "descricao": "Central de impressoras, papel, vias e impressão automatica.",
            "icone": "fa-print",
            "url": "configuracoes:impressoes",
            "status": f"{configuracoes.filter(is_active=True).count()} ativa(s)",
        },
        {
            "titulo": "Acessos PDV nuvem",
            "descricao": "Aprovacao de operadores que tentam acessar o PDV em nuvem.",
            "icone": "fa-user-lock",
            "url": "pdv:acessos_pdv_nuvem",
            "status": f"{AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count()} pendente(s)",
        },
        {
            "titulo": "Terminais PDV",
            "descricao": "Maquinas de caixa autorizadas por filial para o aplicativo local.",
            "icone": "fa-cash-register",
            "url": "configuracoes:terminais_pdv",
            "status": f"{TerminalPdv.objects.filter(ativo=True).count()} ativo(s)",
        },
        {
            "titulo": "App PDV desktop",
            "descricao": "Instalador, requisitos e contrato local do caixa.",
            "icone": "fa-desktop",
            "url": "configuracoes:pdv_desktop",
            "status": "Bridge local",
        },
        {
            "titulo": "Servidor local/admin",
            "descricao": "Modo de implantação para lojas sem internet ou com operação em rede interna.",
            "icone": "fa-server",
            "url": "configuracoes:servidor_local",
            "status": "Admin local",
        },
        {
            "titulo": "Sincronizacao",
            "descricao": "Fila segura entre servidores locais e nuvem, com idempotencia e tentativas.",
            "icone": "fa-arrows-rotate",
            "url": "empresas:sincronizacao",
            "status": f"{EventoSincronizacao.objects.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).count()} aguardando",
        },
        {
            "titulo": "Backup",
            "descricao": "Exportacao operacional em JSON para contingência.",
            "icone": "fa-database",
            "url": "configuracoes:backup",
            "status": f"{len(modelos)} modelos",
        },
        {
            "titulo": "Auditoria",
            "descricao": "Consulta de ações críticas realizadas no sistema.",
            "icone": "fa-shield-halved",
            "url": "auditoria:logs",
            "status": "Logs",
        },
        {
            "titulo": "Super admin",
            "descricao": "Central avançada para admin master, sem depender do admin Django.",
            "icone": "fa-user-shield",
            "url": "configuracoes:super_admin",
            "status": "Master",
        },
        {
            "titulo": "Checklist",
            "descricao": "Roteiro vivo do projeto e proximas fases.",
            "icone": "fa-list-check",
            "url": "configuracoes:checklist",
            "status": f"{resumo_checklist['percentual']}%",
        },
    ]
    context = {
        "atalhos": atalhos,
        "resumo_checklist": resumo_checklist,
        "total_empresas": Empresa.objects.count(),
        "total_filiais": Filial.objects.count(),
        "filiais_sem_ibge": Filial.objects.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
        "usuarios_ativos": User.objects.filter(is_active=True).count(),
        "impressoes_sem_impressora": configuracoes.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
        "certificados_vencidos": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
        "total_registros": total_registros,
    }
    return render(request, "configuracoes/painel_sistema.html", context)


def _super_admin_payload(request):
    modelos = _modelos_backup()
    configs_fiscais = ConfiguracaoFiscal.objects.select_related("filial")
    checklist_grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    resumo_checklist = _resumo_checklist(checklist_grupos)
    perfis = PerfilUsuario.objects.select_related("usuario", "filial")
    sync_saida_alertas = EventoSincronizacao.objects.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).count()
    sync_entrada_alertas = EventoEntradaSincronizacao.objects.filter(
        status__in=[StatusEventoEntrada.RECEBIDO, StatusEventoEntrada.ERRO, StatusEventoEntrada.CONFLITO]
    ).count()
    sync_conflitos = EventoEntradaSincronizacao.objects.filter(status=StatusEventoEntrada.CONFLITO).count()
    sync_total_alertas = sync_saida_alertas + sync_entrada_alertas
    diagnosticos = [
        {
            "titulo": "Admin masters",
            "valor": User.objects.filter(is_superuser=True, is_active=True).count(),
            "descricao": "Usuarios com acesso total ao painel avançado.",
            "status": "Acesso",
        },
        {
            "titulo": "Usuarios sem perfil",
            "valor": User.objects.filter(perfil_supermercado__isnull=True).count(),
            "descricao": "Devem receber perfil e filial antes de operar.",
            "status": "Permissões",
        },
        {
            "titulo": "Filiais sem IBGE",
            "valor": Filial.objects.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
            "descricao": "Pendência crítica para emissão fiscal correta.",
            "status": "Fiscal",
        },
        {
            "titulo": "Certificados vencidos",
            "valor": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
            "descricao": "Certificados não configurados ou fora da validade.",
            "status": "Fiscal",
        },
        {
            "titulo": "PDV nuvem pendente",
            "valor": AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count(),
            "descricao": "Tentativas aguardando liberação do admin/gerente.",
            "status": "PDV",
        },
        {
            "titulo": "Terminais bloqueados",
            "valor": TerminalPdv.objects.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count(),
            "descricao": "Máquinas sem licença operacional ativa.",
            "status": "Licença",
        },
        {
            "titulo": "Alertas de sincronização",
            "valor": sync_total_alertas,
            "descricao": "Eventos de saída/entrada aguardando processamento, erro ou resolução de conflito.",
            "status": "Sincronização",
        },
    ]
    secoes = [
        {
            "titulo": "Estrutura e acessos",
            "itens": [
                ("Empresas e filiais", "empresas:lista", "Cadastro multiempresa, filiais, logo, UF e IBGE."),
                ("Usuários", "accounts:usuarios", "Perfis, filiais e permissões por função."),
                ("Auditoria", "auditoria:logs", "Rastreamento de ações críticas."),
            ],
        },
        {
            "titulo": "Operação sensível",
            "itens": [
                ("Terminais PDV", "configuracoes:terminais_pdv", "Licença por máquina, fiscal, TEF, balança e chave API."),
                ("Acessos PDV nuvem", "pdv:acessos_pdv_nuvem", "Aprovação de operadores fora do ambiente permitido."),
                ("Servidor local/admin", "configuracoes:servidor_local", "Implantação local, manifesto e scripts operacionais."),
                ("App PDV desktop", "configuracoes:pdv_desktop", "Instalador e pacote por terminal autorizado."),
            ],
        },
        {
            "titulo": "Fiscal, impressão e contingência",
            "itens": [
                ("Fiscal", "fiscal:documentos", "NFC-e, certificado e pendências fiscais."),
                ("Impressões", "configuracoes:impressoes", "Cupom, etiquetas, gaveta e impressoras locais."),
                ("Backup", "configuracoes:backup", "Exportação operacional e plano de restauração."),
                ("Sincronização", "empresas:sincronizacao", "Filas local/nuvem, conflitos e eventos."),
            ],
        },
        {
            "titulo": "Governança do projeto",
            "itens": [
                ("Checklist", "configuracoes:checklist", "Roadmap vivo e itens em andamento."),
                ("Formas de pagamento", "configuracoes:formas_pagamento", "Meios aceitos, TEF e contas financeiras."),
            ],
        },
    ]
    perfis_por_tipo = [
        {
            "tipo": label,
            "total": perfis.filter(tipo=valor, is_active=True).count(),
        }
        for valor, label in TipoPerfil.choices
    ]
    alertas = [
        item for item in diagnosticos
        if item["titulo"] != "Admin masters" and item["valor"]
    ]
    pendencias_acionaveis = [
        {
            "prioridade": "Alta",
            "titulo": "Usuários sem perfil",
            "total": User.objects.filter(perfil_supermercado__isnull=True).count(),
            "acao": "Vincular perfil e filial antes de liberar acesso operacional.",
            "url_name": "accounts:usuarios",
        },
        {
            "prioridade": "Alta",
            "titulo": "Filiais sem IBGE",
            "total": Filial.objects.filter(Q(uf="") | Q(codigo_municipio_ibge="")).count(),
            "acao": "Corrigir UF, município e código IBGE para emissão fiscal.",
            "url_name": "empresas:lista",
        },
        {
            "prioridade": "Alta",
            "titulo": "Fiscal sem certificado válido",
            "total": sum(1 for config in configs_fiscais if config.certificado_status in {"vencido", "nao_configurado"}),
            "acao": "Atualizar certificado A1 e validar configuração da filial.",
            "url_name": "fiscal:documentos",
        },
        {
            "prioridade": "Média",
            "titulo": "PDV nuvem aguardando liberação",
            "total": AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count(),
            "acao": "Aprovar ou recusar tentativas de operadores em ambiente de nuvem.",
            "url_name": "pdv:acessos_pdv_nuvem",
        },
        {
            "prioridade": "Média",
            "titulo": "Terminais bloqueados/cancelados",
            "total": TerminalPdv.objects.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count(),
            "acao": "Revisar licenças por máquina e substituir terminais inválidos.",
            "url_name": "configuracoes:terminais_pdv",
        },
        {
            "prioridade": "Média",
            "titulo": "Impressões sem impressora",
            "total": ConfiguracaoImpressao.objects.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
            "acao": "Definir impressora por documento, filial e terminal quando necessário.",
            "url_name": "configuracoes:impressoes",
        },
        {
            "prioridade": "Alta" if sync_conflitos else "Média",
            "titulo": "Sincronização com alerta",
            "total": sync_total_alertas,
            "acao": "Abrir o painel de sincronização, revisar diagnóstico JSON e reprocessar filas ou resolver conflitos.",
            "url_name": "empresas:sincronizacao",
        },
    ]
    cobertura_telas = [
        {
            "area": "Empresas e filiais",
            "modelos": "Empresa, Filial",
            "status": "Completa",
            "observacao": "Cadastro, edição, logo, UF, IBGE e modo de implantação.",
            "url_name": "empresas:lista",
        },
        {
            "area": "Usuários e perfis",
            "modelos": "User, PerfilUsuario",
            "status": "Completa",
            "observacao": "Cadastro próprio com filial, perfil e permissão operacional.",
            "url_name": "accounts:usuarios",
        },
        {
            "area": "Fiscal",
            "modelos": "ConfiguracaoFiscal, SerieFiscal, NaturezaOperacao, DocumentoFiscal",
            "status": "Operacional",
            "observacao": "Configuração, séries, naturezas, documentos, XML e pendências fiscais em telas próprias.",
            "url_name": "fiscal:documentos",
        },
        {
            "area": "Pagamentos",
            "modelos": "FormaPagamento",
            "status": "Completa",
            "observacao": "Formas de pagamento, TEF, PIX e conta financeira padrão.",
            "url_name": "configuracoes:formas_pagamento",
        },
        {
            "area": "Impressão e etiquetas",
            "modelos": "ConfiguracaoImpressao, ModeloEtiqueta",
            "status": "Completa",
            "observacao": "Cupom, etiquetas, impressora, gaveta, linguagem e modelos profissionais.",
            "url_name": "configuracoes:impressoes",
        },
        {
            "area": "Terminais PDV",
            "modelos": "TerminalPdv",
            "status": "Completa",
            "observacao": "Licença, chave API, fiscal por terminal, TEF, balança e pacote desktop.",
            "url_name": "configuracoes:terminais_pdv",
        },
        {
            "area": "Sincronização",
            "modelos": "EventoSincronizacao, EventoEntradaSincronizacao, VendaSincronizada, DocumentoFiscalSincronizado",
            "status": "Consulta",
            "observacao": "Painel com filas, detalhes, conflitos e exportação; CRUD direto não é recomendado.",
            "url_name": "empresas:sincronizacao",
        },
        {
            "area": "Auditoria e backup",
            "modelos": "LogAuditoria, modelos exportáveis",
            "status": "Consulta",
            "observacao": "Logs e exportação operacional protegidos em telas próprias.",
            "url_name": "auditoria:logs",
        },
    ]
    atividade_recente = [
        {
            "data": timezone.localtime(log.criado_em).isoformat(),
            "data_label": timezone.localtime(log.criado_em).strftime("%d/%m/%Y %H:%M"),
            "modulo": log.modulo,
            "acao": log.acao,
            "usuario": log.usuario.username if log.usuario else "sistema",
            "objeto": log.objeto_tipo,
            "objeto_id": log.objeto_id,
            "descricao": log.descricao,
        }
        for log in LogAuditoria.objects.select_related("usuario").order_by("-criado_em")[:8]
    ]
    auditoria_url = reverse("auditoria:logs")
    checklist_url = reverse("configuracoes:checklist")
    investigacoes = [
        {
            "titulo": "Auditoria de configurações",
            "descricao": "Filtra ações recentes em configurações, licenças, impressões e servidor local.",
            "url": f"{auditoria_url}?{urlencode({'modulo': 'configuracoes'})}",
        },
        {
            "titulo": "Auditoria do PDV",
            "descricao": "Investiga caixa, terminal, acesso em nuvem, estorno e eventos do operador.",
            "url": f"{auditoria_url}?{urlencode({'modulo': 'pdv'})}",
        },
        {
            "titulo": "Checklist em andamento",
            "descricao": "Mostra somente itens parciais para orientar a próxima fase de desenvolvimento.",
            "url": f"{checklist_url}?{urlencode({'status': 'partial'})}",
        },
        {
            "titulo": "Checklist Super admin",
            "descricao": "Filtra o roadmap pelo tema do painel master e dependências do admin próprio.",
            "url": f"{checklist_url}?{urlencode({'q': 'Super admin'})}",
        },
        {
            "titulo": "Diagnóstico da sincronização",
            "descricao": "Abre o contrato JSON com filas, alertas, empresas por modo e próximo evento.",
            "url": request.build_absolute_uri("/empresas/sincronizacao/diagnostico.json"),
        },
    ]
    database_engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    media_root = Path(settings.MEDIA_ROOT)
    static_root = Path(settings.STATIC_ROOT) if getattr(settings, "STATIC_ROOT", None) else None
    ambiente_operacional = [
        {
            "item": "DEBUG",
            "valor": "Ligado" if settings.DEBUG else "Desligado",
            "status": "Atenção" if settings.DEBUG else "OK",
            "descricao": "Em produção deve ficar desligado.",
        },
        {
            "item": "Banco padrão",
            "valor": database_engine.rsplit(".", 1)[-1] or "não identificado",
            "status": "OK",
            "descricao": "Motor de banco configurado para a instalação atual.",
        },
        {
            "item": "Hosts permitidos",
            "valor": str(len(settings.ALLOWED_HOSTS)),
            "status": "OK" if settings.ALLOWED_HOSTS else "Atenção",
            "descricao": ", ".join(settings.ALLOWED_HOSTS) if settings.ALLOWED_HOSTS else "Nenhum host configurado.",
        },
        {
            "item": "Pasta media",
            "valor": str(media_root),
            "status": "OK" if media_root.exists() else "Atenção",
            "descricao": "Logos, imagens de produtos, certificados criptografados e anexos dependem deste caminho.",
        },
        {
            "item": "Pasta static",
            "valor": str(static_root) if static_root else "não configurada",
            "status": "OK" if static_root and static_root.exists() else "Atenção",
            "descricao": "Em produção deve apontar para a pasta coletada pelo collectstatic.",
        },
        {
            "item": "Timezone",
            "valor": settings.TIME_ZONE,
            "status": "OK",
            "descricao": "Afeta caixa, vendas, fiscal, auditoria e sincronização.",
        },
    ]
    ambiente_alertas = sum(1 for item in ambiente_operacional if item["status"] != "OK")
    pendencias_altas = sum(1 for item in pendencias_acionaveis if item["prioridade"] == "Alta" and item["total"])
    total_alertas = len(alertas) + ambiente_alertas
    penalidade = (pendencias_altas * 15) + (ambiente_alertas * 8) + (len(alertas) * 5)
    prontidao_percentual = max(0, 100 - penalidade)
    if pendencias_altas:
        prontidao_status = "Crítica"
        prontidao_descricao = "Existem pendências altas antes de considerar a operação pronta."
    elif total_alertas:
        prontidao_status = "Atenção"
        prontidao_descricao = "A operação está funcional, mas há alertas que merecem revisão."
    else:
        prontidao_status = "Pronta"
        prontidao_descricao = "Nenhuma pendência crítica detectada no diagnóstico atual."
    prontidao_operacional = {
        "percentual": prontidao_percentual,
        "status": prontidao_status,
        "descricao": prontidao_descricao,
        "pendencias_altas": pendencias_altas,
        "alertas": total_alertas,
        "ambiente_alertas": ambiente_alertas,
    }
    return {
        "gerado_em": timezone.localtime().isoformat(),
        "usuario": request.user.username,
        "diagnosticos": diagnosticos,
        "secoes": secoes,
        "modelos": modelos,
        "total_modelos": len(modelos),
        "total_registros": sum(item["total"] or 0 for item in modelos),
        "perfis_por_tipo": perfis_por_tipo,
        "resumo_checklist": resumo_checklist,
        "alertas": alertas,
        "pendencias_acionaveis": pendencias_acionaveis,
        "cobertura_telas": cobertura_telas,
        "atividade_recente": atividade_recente,
        "investigacoes": investigacoes,
        "ambiente_operacional": ambiente_operacional,
        "prontidao_operacional": prontidao_operacional,
        "links": {
            "super_admin": request.build_absolute_uri("/configuracoes/super-admin/"),
            "diagnostico_json": request.build_absolute_uri("/configuracoes/super-admin/diagnostico.json"),
            "diagnostico_csv": request.build_absolute_uri("/configuracoes/super-admin/diagnostico.csv"),
            "sincronizacao_diagnostico_json": request.build_absolute_uri("/empresas/sincronizacao/diagnostico.json"),
            "checklist": request.build_absolute_uri("/configuracoes/checklist/"),
            "auditoria": request.build_absolute_uri("/auditoria/"),
        },
    }


@login_required
@role_required(*SISTEMA)
def super_admin(request):
    _exigir_admin_master(request.user)
    context = _super_admin_payload(request)
    return render(request, "configuracoes/super_admin.html", context)


@login_required
@role_required(*SISTEMA)
def super_admin_diagnostico(request):
    _exigir_admin_master(request.user)
    return JsonResponse(_super_admin_payload(request))


@login_required
@role_required(*SISTEMA)
def super_admin_diagnostico_csv(request):
    _exigir_admin_master(request.user)
    payload = _super_admin_payload(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="super_admin_diagnostico.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Secao", "Item", "Status/Prioridade", "Total/Valor", "Descricao/Acao"])
    for item in payload["diagnosticos"]:
        writer.writerow(["Diagnostico", item["titulo"], item["status"], item["valor"], item["descricao"]])
    for item in payload["pendencias_acionaveis"]:
        writer.writerow(["Pendencia", item["titulo"], item["prioridade"], item["total"], item["acao"]])
    for item in payload["cobertura_telas"]:
        writer.writerow(["Cobertura", item["area"], item["status"], item["modelos"], item["observacao"]])
    for item in payload["atividade_recente"]:
        writer.writerow(["Atividade", item["acao"], item["modulo"], item["data_label"], item["descricao"]])
    for item in payload["investigacoes"]:
        writer.writerow(["Investigacao", item["titulo"], "Link", item["url"], item["descricao"]])
    for item in payload["ambiente_operacional"]:
        writer.writerow(["Ambiente", item["item"], item["status"], item["valor"], item["descricao"]])
    prontidao = payload["prontidao_operacional"]
    writer.writerow(["Prontidao", prontidao["status"], prontidao["percentual"], prontidao["alertas"], prontidao["descricao"]])
    for item in payload["perfis_por_tipo"]:
        writer.writerow(["Perfil", item["tipo"], "Ativo", item["total"], "Usuarios ativos por perfil"])
    return response


@login_required
@role_required(*SISTEMA)
def checklist_projeto(request):
    grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    filtros = {
        "q": (request.GET.get("q") or "").strip(),
        "status": (request.GET.get("status") or "").strip(),
        "grupo": (request.GET.get("grupo") or "").strip(),
        "trilha": (request.GET.get("trilha") or "").strip(),
        "prioridade": (request.GET.get("prioridade") or "").strip(),
    }
    grupos_filtrados = _filtrar_checklist(
        grupos,
        termo=filtros["q"],
        status=filtros["status"],
        grupo_titulo=filtros["grupo"],
        trilha=filtros["trilha"],
        prioridade=filtros["prioridade"],
    ) if any(filtros.values()) else [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in grupos
    ]
    mapa_trilhas = _mapa_trilhas_roadmap(grupos)
    resumo_filtrado = _resumo_checklist(grupos_filtrados)
    context = {
        "grupos": grupos_filtrados,
        "resumo": _resumo_checklist(grupos),
        "resumo_filtrado": resumo_filtrado,
        "mapa_trilhas": mapa_trilhas,
        "proximas_etapas": _proximas_etapas_checklist(grupos_filtrados if any(filtros.values()) else grupos),
        "filtros": filtros,
        "grupos_opcoes": [grupo["titulo"] for grupo in grupos],
        "trilhas_opcoes": [item["trilha"] for item in mapa_trilhas],
        "prioridades_opcoes": ["Alta", "Média"],
        "status_opcoes": [
            ("", "Todos os status"),
            ("done", "Concluído"),
            ("partial", "Em andamento"),
            ("todo", "Pendente"),
        ],
        "documentos": DOCUMENTOS_PROJETO,
    }
    return render(request, "configuracoes/checklist.html", context)


@login_required
@role_required(*SISTEMA)
def checklist_projeto_csv(request):
    grupos = [
        {**grupo, "itens": list(grupo["itens"])}
        for grupo in CHECKLIST_GRUPOS
    ]
    grupos = _filtrar_checklist(
        grupos,
        termo=request.GET.get("q"),
        status=request.GET.get("status"),
        grupo_titulo=request.GET.get("grupo"),
        trilha=request.GET.get("trilha"),
        prioridade=request.GET.get("prioridade"),
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="checklist_projeto.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Grupo", "Item", "Status", "Trilha", "Prioridade", "Proxima acao", "Descricao"])
    status_labels = {"done": "Concluído", "partial": "Em andamento", "todo": "Pendente"}
    for grupo in grupos:
        for titulo, status, descricao in grupo["itens"]:
            classificacao = _classificar_etapa_roadmap(grupo["titulo"], titulo, descricao) if status == "partial" else {"trilha": "", "prioridade": "", "acao": ""}
            writer.writerow([grupo["titulo"], titulo, status_labels.get(status, status), classificacao["trilha"], classificacao["prioridade"], classificacao["acao"], descricao])
    return response


@login_required
@role_required(*SISTEMA)
def pdv_desktop(request):
    _exigir_admin_master(request.user)
    instalador = _instalador_pdv_desktop()
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
    total_terminais = terminais.count()
    licencas_liberadas = terminais.filter(status_licenca=StatusLicencaTerminal.LIBERADA, ativo=True).count()
    licencas_pendentes = terminais.filter(status_licenca=StatusLicencaTerminal.PENDENTE).count()
    licencas_bloqueadas = terminais.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count()
    eventos_dispositivo = EventoDispositivoTerminal.objects.select_related("terminal", "terminal__filial").order_by("-recebido_em")
    resumo_eventos_dispositivo = eventos_dispositivo.values("tipo", "status").annotate(total=Count("id")).order_by("tipo", "status")
    context = {
        "terminais": terminais,
        "total_terminais": total_terminais,
        "licencas_liberadas": licencas_liberadas,
        "licencas_pendentes": licencas_pendentes,
        "licencas_bloqueadas": licencas_bloqueadas,
        "eventos_dispositivo": eventos_dispositivo[:50],
        "total_eventos_dispositivo": eventos_dispositivo.count(),
        "resumo_eventos_dispositivo": resumo_eventos_dispositivo,
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "instalador": instalador,
        "artefatos": [
            {
                "nome": "Windows x64",
                "status": "Fonte iniciado",
                "descricao": "Shell WebView com ativacao guiada reutiliza /pdv/; build do .exe preparado, faltando assinatura e instalador MSI.",
            },
            {
                "nome": "Bridge local",
                "status": "Contrato pronto",
                "descricao": "Conecta impressora, gaveta, TEF, balanca e servidor local da loja.",
            },
        ],
    }
    return render(request, "configuracoes/pdv_desktop.html", context)


def _pdv_desktop_manifest_payload(request):
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
    instalador = _instalador_pdv_desktop()
    return {
        "status": "ok",
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "distribuicao": "erp",
        "licenciamento": {
            "modelo": "por_terminal",
            "download_requer_admin_master": True,
            "ativacao_requer_terminal_autorizado": True,
            "observacao": "Cada máquina de caixa deve ser liberada pelo admin master antes de baixar/ativar o app desktop.",
        },
        "contratos": {
            "tef": "pdv_tef_v1",
            "impressao": "pdv_print_v1",
            "sincronizacao": "pdv_sync_v1",
        },
        "recursos": {
            "tef_integrado": True,
            "impressao_desktop": True,
            "gaveta_opcional": True,
            "balanca_local": True,
            "fiscal_por_terminal": True,
            "modo_offline": True,
        },
        "artefatos": {
            "windows_x64": {
                "status": "disponivel" if instalador["disponivel"] else "aguardando_build",
                "nome": instalador["nome"],
                "url": request.build_absolute_uri("/configuracoes/pdv-desktop/download/windows/") if instalador["disponivel"] else "",
                "tamanho_bytes": instalador["tamanho"],
                "sha256": instalador["sha256"],
            }
        },
        "terminais": [
            {
                "identificador": str(terminal.identificador),
                "nome": terminal.nome,
                "filial": terminal.filial.nome,
                "empresa": str(terminal.filial.empresa),
                "ativo": terminal.ativo,
                "licenca": {
                    "status": terminal.status_licenca,
                    "liberada": terminal.licenca_liberada,
                    "liberada_em": terminal.licenca_liberada_em.isoformat() if terminal.licenca_liberada_em else None,
                },
                "emite_documento_fiscal": terminal.emite_documento_fiscal,
                "permite_modo_offline": terminal.permite_modo_offline,
                "provedor_tef": terminal.provedor_tef,
                "modo_integracao_tef": terminal.modo_integracao_tef,
                "balanca": terminal.balanca_configuracao(),
                "chave_api_prefixo": terminal.chave_api_prefixo,
                "bootstrap_url": request.build_absolute_uri("/pdv/api/terminal/bootstrap/"),
            }
            for terminal in terminais
        ],
    }


@login_required
@role_required(*SISTEMA)
def pdv_desktop_manifest(request):
    _exigir_admin_master(request.user)
    return JsonResponse(_pdv_desktop_manifest_payload(request))


@login_required
@role_required(*SISTEMA)
def pdv_desktop_download_windows(request):
    _exigir_admin_master(request.user)
    caminho = settings.PDV_DESKTOP_INSTALLER_PATH
    if not caminho.is_file():
        raise Http404("Instalador do PDV desktop ainda não publicado.")
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="DOWNLOAD_PDV_DESKTOP",
        descricao=f"Download do instalador PDV desktop {caminho.name}.",
        objeto_tipo="PdvDesktopInstaller",
        objeto_id=PDV_DESKTOP_VERSAO_PLANEJADA,
        ip=request.META.get("REMOTE_ADDR"),
    )
    return FileResponse(caminho.open("rb"), as_attachment=True, filename=caminho.name)


def _configuracao_gaveta_terminal(filial):
    impressao = configuracao_impressao_para(filial, TipoDocumentoImpressao.CUPOM_NAO_FISCAL)
    return {
        "contrato": "pdv_cash_drawer_v1",
        "opcional": True,
        "habilitada": bool(impressao and impressao.gaveta_automatica),
        "impressora_padrao": impressao.impressora_padrao if impressao else "",
        "abrir_em_dinheiro": bool(impressao and impressao.abrir_gaveta_em_dinheiro),
        "abrir_em_movimento_caixa": bool(impressao and impressao.abrir_gaveta_em_movimento_caixa),
        "bloqueia_venda_se_indisponivel": False,
    }


def _pdv_desktop_terminal_payload(request, terminal):
    return {
        "status": "ok",
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "terminal": {
            "identificador": str(terminal.identificador),
            "nome": terminal.nome,
            "descricao": terminal.descricao,
            "ativo": terminal.ativo,
            "chave_api_prefixo": terminal.chave_api_prefixo,
        },
        "licenciamento": {
            "modelo": "por_terminal",
            "download_requer_admin_master": True,
            "terminal_autorizado": terminal.licenca_liberada,
            "status": terminal.status_licenca,
            "observacao": "Pacote destinado apenas a máquina licenciada e autorizada pelo admin master.",
        },
        "filial": {
            "id": terminal.filial_id,
            "nome": terminal.filial.nome,
            "empresa": str(terminal.filial.empresa),
        },
        "servidor": {
            "base_url": request.build_absolute_uri("/").rstrip("/"),
            "bootstrap_url": request.build_absolute_uri("/pdv/api/terminal/bootstrap/"),
            "manifest_url": request.build_absolute_uri("/configuracoes/pdv-desktop/manifest.json"),
        },
        "interface": {
            "modo": "webview_compartilhada",
            "pdv_url": request.build_absolute_uri("/pdv/"),
            "mesmo_layout_do_pdv_web": True,
            "atalhos_compartilhados": True,
        },
        "fiscal": {
            "emissao_automatica": terminal.emite_documento_fiscal,
            "observacao": "Quando falso, este terminal não tenta preparar NFC-e automaticamente.",
        },
        "tef": {
            "contrato": "pdv_tef_v1",
            "provedor": terminal.provedor_tef,
            "modo_integracao": terminal.modo_integracao_tef,
            "tipos_pagamento": ["CREDITO", "DEBITO", "PIX"],
            "retorno_esperado": ["status", "transacao_externa_id", "nsu", "codigo_autorizacao", "mensagem_processadora"],
        },
        "dispositivos": {
            "impressora": {"contrato": "pdv_print_v1", "config_url": request.build_absolute_uri("/configuracoes/impressoes/desktop.json")},
            "gaveta": _configuracao_gaveta_terminal(terminal.filial),
            "balanca": terminal.balanca_configuracao(),
        },
        "sincronizacao": {
            "contrato": "pdv_sync_v1",
            "modo_offline_permitido": terminal.permite_modo_offline,
        },
    }


def _servidor_local_payload(request):
    empresas = Empresa.objects.prefetch_related("filiais").order_by("nome_fantasia")
    modos = {
        modo: empresas.filter(modo_implantacao=modo).count()
        for modo in ModoImplantacao.values
    }
    servico_windows = {
        "nome": "MercaFlowServidorLocal",
        "status": "especificado",
        "tipo": "Windows Service",
        "usuario_recomendado": "Conta local dedicada, sem permissao de administrador diario",
        "comando_producao": r".\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 config.wsgi:application",
        "fallback_operacional": "scripts/run_local_server.ps1 -Bind 0.0.0.0 -Port 8000",
        "healthcheck": "/login/",
        "restart": "Reiniciar automaticamente em falha e iniciar com o Windows",
        "logs": ["logs/django.log", "logs/servidor-local.log"],
        "observacao": "Contrato preparado para instalador/servico real; a tarefa agendada continua como fallback ate o empacotamento assinado.",
    }
    pendencias = [
        {
            "titulo": "Servico Windows/Linux",
            "status": "especificado",
            "descricao": "Contrato de servico Windows definido com nome, comando WSGI, healthcheck, restart e logs; scripts/register_local_server_task.ps1 continua como fallback operacional ate o instalador assinado.",
        },
        {
            "titulo": "Backup local automático",
            "status": "iniciado",
            "descricao": "Script scripts/backup_local.ps1 gera pacote zipado com dados, media, manifesto, checksum e criptografia opcional AES-256 via BACKUP_ENCRYPTION_PASSPHRASE; scripts/register_backup_task.ps1 agenda backup diário.",
        },
        {
            "titulo": "Atualização controlada",
            "status": "planejado",
            "descricao": "Aplicar pacotes assinados pelo admin master, com rollback e janela fora do expediente.",
        },
        {
            "titulo": "Sincronização opcional",
            "status": "iniciado",
            "descricao": "Reusar filas existentes para lojas híbridas, com scripts/register_sync_task.ps1 agendando a rotina recorrente e mantendo operação local quando a internet cair.",
        },
    ]
    return {
        "status": "ok",
        "contrato": "erp_local_admin_v1",
        "recomendacao": "Servidor local administrativo com acesso via navegador; app desktop completo apenas para PDV.",
        "acesso": {
            "admin_local_url": request.build_absolute_uri("/configuracoes/"),
            "usa_navegador": True,
            "app_shell_opcional": True,
            "pdv_desktop_separado": True,
        },
        "servico_windows": servico_windows,
        "scripts": {
            "subir_servidor": "scripts/run_local_server.ps1",
            "registrar_servidor": "scripts/register_local_server_task.ps1",
            "backup_local": "scripts/backup_local.ps1",
            "registrar_backup": "scripts/register_backup_task.ps1",
            "registrar_sincronizacao": "scripts/register_sync_task.ps1",
            "guia": "docs/IMPLANTACAO_SERVIDOR_LOCAL.md",
            "backup_criptografia_env": "BACKUP_ENCRYPTION_PASSPHRASE",
            "backup_criptografia_flag": "-RemoverOriginalCriptografado",
        },
        "modos_implantacao": {
            "local": {
                "codigo": ModoImplantacao.LOCAL,
                "descricao": "Loja opera sem depender da internet; backups e atualizações são controlados localmente.",
                "empresas": modos.get(ModoImplantacao.LOCAL, 0),
            },
            "hibrido": {
                "codigo": ModoImplantacao.HIBRIDO,
                "descricao": "Loja opera no servidor local e sincroniza com a nuvem quando houver conexão.",
                "empresas": modos.get(ModoImplantacao.HIBRIDO, 0),
            },
            "nuvem_agente": {
                "codigo": ModoImplantacao.NUVEM_AGENTE,
                "descricao": "Retaguarda em nuvem usa agente local para dispositivos e contingência.",
                "empresas": modos.get(ModoImplantacao.NUVEM_AGENTE, 0),
            },
        },
        "empresas": [
            {
                "id": empresa.id,
                "nome": empresa.nome_fantasia,
                "modo_implantacao": empresa.modo_implantacao,
                "modo_implantacao_label": empresa.get_modo_implantacao_display(),
                "sincronizacao_automatica": empresa.sincronizacao_automatica,
                "filiais": empresa.filiais.count(),
            }
            for empresa in empresas
        ],
        "pendencias": pendencias,
    }


@login_required
@role_required(*SISTEMA)
def pdv_desktop_terminal_pacote(request, pk):
    _exigir_admin_master(request.user)
    terminal = get_object_or_404(TerminalPdv.objects.select_related("filial", "filial__empresa"), pk=pk)
    if not terminal.licenca_liberada:
        raise PermissionDenied
    return JsonResponse(_pdv_desktop_terminal_payload(request, terminal))


@login_required
@role_required(*SISTEMA)
def servidor_local(request):
    payload = _servidor_local_payload(request)
    return render(
        request,
        "configuracoes/servidor_local.html",
        {
            "payload": payload,
            "empresas": payload["empresas"],
            "modos": payload["modos_implantacao"],
            "pendencias": payload["pendencias"],
        },
    )


@login_required
@role_required(*SISTEMA)
def servidor_local_manifest(request):
    _exigir_admin_master(request.user)
    return JsonResponse(_servidor_local_payload(request))


@login_required
@role_required(*SISTEMA)
def formas_pagamento(request):
    formas = FormaPagamento.objects.order_by("-ativo", "nome")
    return render(request, "configuracoes/formas_pagamento.html", {"formas": formas})


@login_required
@role_required(*SISTEMA)
def forma_pagamento_form(request, pk=None):
    forma = get_object_or_404(FormaPagamento, pk=pk) if pk else None
    form = FormaPagamentoForm(request.POST or None, instance=forma)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Forma de pagamento salva com sucesso.")
        return redirect("configuracoes:formas_pagamento")
    return render(request, "configuracoes/forma_pagamento_form.html", {"form": form, "object": forma})


@login_required
@role_required(*SISTEMA)
def terminais_pdv(request):
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
    busca = request.GET.get("q", "").strip()
    filtro_licenca = request.GET.get("licenca", "").strip()
    filtro_status = request.GET.get("status", "").strip()
    if busca:
        terminais = terminais.filter(
            Q(nome__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(filial__nome__icontains=busca)
            | Q(filial__empresa__nome_fantasia__icontains=busca)
            | Q(filial__empresa__razao_social__icontains=busca)
            | Q(identificador__icontains=busca)
            | Q(chave_api_prefixo__icontains=busca)
        )
    if filtro_licenca in StatusLicencaTerminal.values:
        terminais = terminais.filter(status_licenca=filtro_licenca)
    if filtro_status == "ativo":
        terminais = terminais.filter(ativo=True)
    elif filtro_status == "inativo":
        terminais = terminais.filter(ativo=False)
    chave_nova = request.session.pop("terminal_pdv_chave_nova", None)
    return render(
        request,
        "configuracoes/terminais_pdv.html",
        {
            "terminais": terminais,
            "chave_nova": chave_nova,
            "busca": busca,
            "filtro_licenca": filtro_licenca,
            "filtro_status": filtro_status,
            "status_licenca_choices": StatusLicencaTerminal.choices,
        },
    )


@login_required
@role_required(*SISTEMA)
def terminal_pdv_form(request, pk=None):
    terminal = get_object_or_404(TerminalPdv, pk=pk) if pk else None
    form = TerminalPdvForm(request.POST or None, instance=terminal)
    if request.method == "POST" and form.is_valid():
        terminal_anterior = terminal
        terminal = form.save(commit=False)
        if not _usuario_admin_master(request.user):
            if terminal_anterior:
                terminal.status_licenca = terminal_anterior.status_licenca
                terminal.licenca_liberada_em = terminal_anterior.licenca_liberada_em
                terminal.licenca_liberada_por = terminal_anterior.licenca_liberada_por
                terminal.observacao_licenca = terminal_anterior.observacao_licenca
            else:
                terminal.status_licenca = StatusLicencaTerminal.PENDENTE
                terminal.observacao_licenca = "Aguardando liberacao do admin master."
        elif terminal.status_licenca == StatusLicencaTerminal.LIBERADA and not terminal.licenca_liberada_em:
            terminal.licenca_liberada_em = timezone.now()
            terminal.licenca_liberada_por = request.user
        chave_nova = None
        if not terminal.chave_api_hash:
            chave_nova = terminal.gerar_chave_api()
        terminal.save()
        if chave_nova:
            request.session["terminal_pdv_chave_nova"] = {
                "terminal": terminal.nome,
                "identificador": str(terminal.identificador),
                "chave": chave_nova,
            }
        messages.success(request, "Terminal PDV salvo com sucesso.")
        return redirect("configuracoes:terminais_pdv")
    return render(request, "configuracoes/terminal_pdv_form.html", {"form": form, "object": terminal})


@login_required
@role_required(*SISTEMA)
def terminal_pdv_alterar_licenca(request, pk, acao):
    _exigir_admin_master(request.user)
    if request.method != "POST":
        return redirect("configuracoes:terminais_pdv")
    terminal = get_object_or_404(TerminalPdv, pk=pk)
    acoes = {
        "liberar": StatusLicencaTerminal.LIBERADA,
        "bloquear": StatusLicencaTerminal.BLOQUEADA,
        "cancelar": StatusLicencaTerminal.CANCELADA,
        "pendenciar": StatusLicencaTerminal.PENDENTE,
    }
    novo_status = acoes.get(acao)
    if not novo_status:
        messages.error(request, "Acao de licenca invalida.")
        return redirect("configuracoes:terminais_pdv")

    terminal.status_licenca = novo_status
    if novo_status == StatusLicencaTerminal.LIBERADA:
        terminal.licenca_liberada_em = timezone.now()
        terminal.licenca_liberada_por = request.user
        terminal.observacao_licenca = request.POST.get("observacao_licenca", "").strip() or "Licenca liberada pelo admin master."
    else:
        terminal.observacao_licenca = request.POST.get("observacao_licenca", "").strip() or f"Licenca marcada como {terminal.get_status_licenca_display()} pelo admin master."
    terminal.save(update_fields=["status_licenca", "licenca_liberada_em", "licenca_liberada_por", "observacao_licenca", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="configuracoes",
        acao="LICENCA_TERMINAL_PDV",
        descricao=(
            f"Licenca do terminal {terminal.nome} ({terminal.identificador}) alterada para "
            f"{terminal.get_status_licenca_display()}. Observacao: {terminal.observacao_licenca or '-'}"
        ),
        objeto_tipo="TerminalPdv",
        objeto_id=str(terminal.id),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, f"Licenca do terminal {terminal.nome} atualizada para {terminal.get_status_licenca_display()}.")
    return redirect("configuracoes:terminais_pdv")


@login_required
@role_required(*SISTEMA)
def terminal_pdv_regenerar_chave(request, pk):
    if request.method != "POST":
        return redirect("configuracoes:terminais_pdv")
    terminal = get_object_or_404(TerminalPdv, pk=pk)
    chave_nova = terminal.gerar_chave_api()
    terminal.save(update_fields=["chave_api_hash", "chave_api_prefixo", "atualizado_em"])
    request.session["terminal_pdv_chave_nova"] = {
        "terminal": terminal.nome,
        "identificador": str(terminal.identificador),
        "chave": chave_nova,
    }
    messages.success(request, "Chave do terminal renovada. Atualize o aplicativo instalado nesta máquina.")
    return redirect("configuracoes:terminais_pdv")


@login_required
@role_required(*SISTEMA)
def backup_operacional(request):
    modelos = _modelos_backup()
    total_registros = sum(item["total"] or 0 for item in modelos)
    context = {
        "modelos": modelos,
        "total_modelos": len(modelos),
        "total_registros": total_registros,
        "gerado_em": timezone.localtime(),
        "exclusoes": [
            "Permissoes internas do Django",
            "Tipos de conteudo tecnicos",
            "Sessoes de login",
            "Logs administrativos do painel Django",
        ],
        "backup_local_script": "scripts/backup_local.ps1",
        "backup_criptografia_env": "BACKUP_ENCRYPTION_PASSPHRASE",
        "backup_criptografia_flag": "-RemoverOriginalCriptografado",
    }
    return render(request, "configuracoes/backup.html", context)


@login_required
@role_required(*SISTEMA)
def backup_download(request):
    agora = timezone.localtime()
    arquivo = f"backup_supermercado_{agora:%Y%m%d_%H%M%S}.json"
    saída = StringIO()
    call_command(
        "dumpdata",
        exclude=["auth.permission", "contenttypes", "sessions", "admin.logentry"],
        indent=2,
        stdout=saída,
    )
    response = HttpResponse(saída.getvalue(), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{arquivo}"'
    return response


@login_required
@role_required(*SISTEMA)
def impressoes(request):
    configuracoes = ConfiguracaoImpressao.objects.select_related("empresa", "filial").order_by(
        "empresa__nome_fantasia",
        "filial__nome",
        "tipo_documento",
    )
    resumo = {
        "total": configuracoes.count(),
        "ativas": configuracoes.filter(is_active=True).count(),
        "automaticas": configuracoes.filter(impressao_automatica=True, is_active=True).count(),
        "gavetas": configuracoes.filter(gaveta_automatica=True, is_active=True).count(),
        "sem_impressora": configuracoes.filter(Q(impressora_padrao="") | Q(impressora_padrao__isnull=True), is_active=True).count(),
    }
    impressoras_cadastradas = [
        nome
        for nome in configuracoes.exclude(impressora_padrao="").values_list("impressora_padrao", flat=True).distinct()
        if nome
    ]
    return render(
        request,
        "configuracoes/impressoes.html",
        {
            "configuracoes": configuracoes,
            "resumo": resumo,
            "impressoras_cadastradas": impressoras_cadastradas,
            "modelos_etiqueta": ModeloEtiqueta.objects.select_related(
                "configuracao", "configuracao__empresa", "configuracao__filial", "terminal"
            ),
        },
    )


@login_required
@role_required(*SISTEMA)
def modelo_etiqueta_form(request, pk=None):
    modelo = get_object_or_404(ModeloEtiqueta, pk=pk) if pk else None
    if request.method == "POST":
        form = ModeloEtiquetaForm(request.POST, instance=modelo)
        if form.is_valid():
            with transaction.atomic():
                salvo = form.save()
                if salvo.padrao:
                    ModeloEtiqueta.objects.filter(configuracao=salvo.configuracao).exclude(pk=salvo.pk).update(padrao=False)
            messages.success(request, "Modelo de etiqueta salvo.")
            return redirect("configuracoes:impressoes")
    else:
        form = ModeloEtiquetaForm(instance=modelo)
    return render(request, "configuracoes/modelo_etiqueta_form.html", {"form": form, "modelo": modelo})


@login_required
@role_required(*SISTEMA)
def modelo_etiqueta_teste(request, pk):
    modelo = get_object_or_404(
        ModeloEtiqueta.objects.select_related("configuracao", "terminal"),
        pk=pk,
        is_active=True,
        configuracao__is_active=True,
    )
    config = modelo.configuracao
    return JsonResponse(
        {
            "status": "ok",
            "contrato": "label_print_v1",
            "origem": "configuracoes_modelo_etiqueta_teste",
            "mensagem": "Etiqueta de teste preparada para impressão direta no app desktop.",
            "impressora_padrao": config.impressora_padrao,
            "linguagem": config.linguagem_impressora,
            "dpi": config.dpi_impressora,
            "densidade": config.densidade_impressao,
            "velocidade": config.velocidade_impressao,
            "tipo_midia": config.tipo_midia_etiqueta,
            "modelo": {
                "id": modelo.id,
                "nome": modelo.nome,
                "largura_mm": float(modelo.largura_mm),
                "altura_mm": float(modelo.altura_mm),
                "gap_horizontal_mm": float(modelo.gap_horizontal_mm),
                "gap_vertical_mm": float(modelo.gap_vertical_mm),
                "colunas": modelo.colunas,
                "orientacao": modelo.orientacao,
            },
            "itens": [
                {
                    "nome": "ETIQUETA TESTE",
                    "codigo": "789000000001",
                    "unidade": "UN",
                    "preco": "9.99",
                    "copias": 1,
                }
            ],
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoras_locais(request):
    impressoras_cadastradas = list(
        ConfiguracaoImpressao.objects.exclude(impressora_padrao="")
        .values_list("impressora_padrao", flat=True)
        .distinct()
    )
    return JsonResponse(
        {
            "status": "desktop_bridge_required",
            "mensagem": "O navegador não permite listar impressoras locais diretamente. O app desktop usara este ponto para sincronizar as impressoras da máquina.",
            "impressoras_cadastradas": impressoras_cadastradas,
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoes_desktop(request):
    configuracoes = ConfiguracaoImpressao.objects.select_related("empresa", "filial").prefetch_related(
        "modelos_etiqueta", "modelos_etiqueta__terminal"
    ).filter(is_active=True).order_by(
        "empresa_id",
        "filial_id",
        "tipo_documento",
    )
    payload = []
    for config in configuracoes:
        impressora_padrao = (config.impressora_padrao or "").strip()
        impressora_configurada = bool(impressora_padrao)
        mensagem_impressora = ""
        if not impressora_configurada:
            mensagem_impressora = (
                f"{config.get_tipo_documento_display()} sem impressora padrão definida. "
                "Configure a impressora da máquina antes de usar impressão direta no app desktop."
            )
        payload.append(
            {
                "id": config.id,
                "empresa_id": config.empresa_id,
                "empresa": str(config.empresa),
                "filial_id": config.filial_id,
                "filial": str(config.filial) if config.filial else None,
                "tipo_documento": config.tipo_documento,
                "tipo_documento_label": config.get_tipo_documento_display(),
                "impressora_padrao": impressora_padrao,
                "impressora_configurada": impressora_configurada,
                "mensagem": mensagem_impressora,
                "modelo_papel": config.modelo_papel,
                "modelo_papel_label": config.get_modelo_papel_display(),
                "numero_vias": config.numero_vias,
                "impressao_automatica": config.impressao_automatica,
                "etiqueta": {
                    "largura_mm": float(config.largura_etiqueta_mm),
                    "altura_mm": float(config.altura_etiqueta_mm),
                    "gap_horizontal_mm": float(config.gap_horizontal_mm),
                    "gap_vertical_mm": float(config.gap_vertical_mm),
                    "colunas": config.colunas_etiqueta,
                    "dpi": config.dpi_impressora,
                    "densidade": config.densidade_impressao,
                    "velocidade": config.velocidade_impressao,
                    "tipo_midia": config.tipo_midia_etiqueta,
                    "linguagem": config.linguagem_impressora,
                    "modelos": [
                        {
                            "id": modelo.id,
                            "nome": modelo.nome,
                            "terminal_id": modelo.terminal_id,
                            "largura_mm": float(modelo.largura_mm),
                            "altura_mm": float(modelo.altura_mm),
                            "gap_horizontal_mm": float(modelo.gap_horizontal_mm),
                            "gap_vertical_mm": float(modelo.gap_vertical_mm),
                            "colunas": modelo.colunas,
                            "orientacao": modelo.orientacao,
                            "padrao": modelo.padrao,
                        }
                        for modelo in config.modelos_etiqueta.all()
                        if modelo.is_active
                    ],
                },
                "gaveta": {
                    "automatica": config.gaveta_automatica,
                    "abrir_em_dinheiro": config.gaveta_automatica and config.abrir_gaveta_em_dinheiro,
                    "abrir_em_movimento_caixa": config.gaveta_automatica and config.abrir_gaveta_em_movimento_caixa,
                    "bloqueia_venda_se_indisponivel": False,
                },
            }
        )
    return JsonResponse(
        {
            "status": "ok",
            "mensagem": "Configuracoes preparadas para sincronizacao com o app desktop local.",
            "configuracoes": payload,
        }
    )


@login_required
@role_required(*SISTEMA)
def impressoes_padroes(request):
    if request.method != "POST":
        return redirect("configuracoes:impressoes")
    criadas = criar_configuracoes_padrao()
    if criadas:
        messages.success(request, f"{criadas} configuracao(oes) de impressão criada(s).")
    else:
        messages.info(request, "As configuracoes padrao já estavam criadas.")
    return redirect("configuracoes:impressoes")


@login_required
@role_required(*SISTEMA)
def impressao_form(request, pk=None):
    configuracao = get_object_or_404(ConfiguracaoImpressao, pk=pk) if pk else None
    if request.method == "POST":
        form = ConfiguracaoImpressaoForm(request.POST, instance=configuracao)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuracao de impressão salva.")
            return redirect("configuracoes:impressoes")
    else:
        form = ConfiguracaoImpressaoForm(instance=configuracao)
    impressoras_cadastradas = [
        nome
        for nome in ConfiguracaoImpressao.objects.exclude(impressora_padrao="")
        .values_list("impressora_padrao", flat=True)
        .distinct()
        if nome
    ]
    return render(
        request,
        "configuracoes/impressao_form.html",
        {
            "form": form,
            "configuracao": configuracao,
            "impressoras_cadastradas": impressoras_cadastradas,
        },
    )

# Create your views here.
