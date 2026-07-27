import csv
import os
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
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.accounts.permissions import SISTEMA, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, ModoImplantacao, StatusEventoEntrada, StatusSincronizacao
from apps.fiscal.models import ConfiguracaoFiscal
from apps.pdv.models import AcessoPdvNuvem, CanalAtualizacaoPdv, EventoDispositivoTerminal, StatusAcessoPdvNuvem, StatusLicencaTerminal, TerminalPdv
from apps.vendas.models import FormaPagamento, PagamentoVenda, StatusPagamento

from .artifacts import artefato_pdv_desktop
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
            ("Tela PDV em layout de operador", "done", "PDV sem sidebar, cabendo em 100% de zoom no desktop testado. Após a venda, uma camada de tela cheia informa CAIXA LIVRE e aceita Enter, Escape ou o início da leitura do próximo código de barras para liberar imediatamente a nova compra."),
            ("Venda com carrinho e baixa de estoque", "done", "Venda finaliza com itens, pagamentos e baixa automatica."),
            ("Pagamento dividido", "done", "Popup aceita múltiplas formas e calcula restante/troco. Atalhos F1/F2/F3/F4 preenchem a linha atual e só criam nova forma quando ainda existe saldo restante; se o pagamento já cobre o total, o PDV avisa o operador em vez de duplicar parcelas automaticamente. Para dois cartões, PIX + cartão ou outra divisão real, o operador informa o valor parcial e adiciona a próxima forma, ficando cada parcela registrada na venda."),
            ("Desconto supervisionado no PDV", "done", "Todo desconto informado no pagamento exige usuário e senha de supervisor ou administrador. A venda é bloqueada sem credencial válida e a autorização registra desconto, venda, operador, supervisor e IP no log de auditoria."),
            ("PIX no pagamento do PDV", "done", "Forma PIX disponível dentro da escolha eletrônica do F3. O app desktop gera e exibe QR Code com valor destacado, mantém a parcela pendente e consulta o terminal até receber confirmação; somente o retorno aprovado libera a finalização. O QR do simulador é identificado como teste e o adaptador real poderá usar a tela do PDV, o pinpad compatível ou ambos."),
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
            ("Arquitetura PDV desktop local", "partial", "PDV dos caixas deve ser um aplicativo instalado na máquina do operador, fiel ao layout, atalhos e fluxo de venda do PDV web já validado, para que o operador use a mesma experiência nos dois ambientes. O desktop acrescenta integrações locais com impressora, balanca, gaveta e TEF, operacao resiliente e acesso somente ao necessário para venda, pagamento, caixa, consulta e estorno autorizado, sem telas administrativas completas. O app se comunica com o servidor local da loja pela rede interna; esse servidor local conversa com os dispositivos e o banco operacional da filial. Cadastro por filial, chave individual protegida por hash e bootstrap com registro de conexao implementados. O bootstrap diario devolve a configuracao vigente de licenca, TEF, fiscal e balanca para o app instalado se atualizar sem novo pacote. A nuvem/sede sincroniza por API segura, filas e eventos, sem acessar diretamente o banco local do supermercado. Download/ativacao do app desktop exige autorizacao do admin master, pois cada máquina instalada pode representar uma licenca comercial cobrada por terminal; pacote de ativacao so e entregue para terminal com licenca liberada. A Central do App oferece pré-homologação consolidada pelo contrato pdv_device_homologation_v1: inspeciona impressoras, balança, gaveta e TEF, não imprime nem cria cobrança no modo padrão, exige seleção e confirmação para leitura/pulso físico e grava a evidência em devices.log.jsonl para sincronização central. A fila local agora segue o contrato pdv_device_event_queue_v1: cada evento recebe ID estável, lotes são enviados do mais antigo ao mais novo a partir de cursor confirmado, reenvios são deduplicados por terminal no servidor e a compactação atômica remove somente registros já confirmados, preservando todos os pendentes. Durante o turno, uma thread exclusiva sincroniza periodicamente em intervalo local configurável de 15 a 3.600 segundos e é encerrada de forma limpa junto com a WebView, sem depender de reiniciar o caixa. O bootstrap agora publica o pacote vigente e o canal de atualização autenticado aceita somente terminal ativo com licença liberada pelo admin master; o rollout pdv_update_rollout_v1 permite promover uma versão primeiro em caixas piloto e depois no canal estável, congelar atualizações opcionais por máquina e sobrepor o congelamento quando a versão instalada ficar abaixo do mínimo de segurança. O app baixa para arquivo temporário, valida SHA-256, descarta pacote divergente, registra diagnóstico e mantém a instalação manual, sem atualização silenciosa. A contingência de conexão agora usa bootstrap local autorizado com validade padrão de 24 horas: em queda do servidor mostra uma tela local identificando o caixa, bloqueia venda, pagamento e estoque e permite reconectar por F5/Enter; somente uma nova validação de terminal e licença abre o PDV, enquanto cache vencido ou terminal recusado permanece bloqueado. A chave de ativação e os parâmetros sensíveis do adaptador TEF deixaram de permanecer em texto no config.json: o agente usa o contrato pdv_local_secret_v1 e DPAPI vinculado ao usuário do Windows, restaura os valores somente em memória, migra automaticamente instalações legadas, bloqueia conteúdo corrompido ou copiado para outro usuário e expõe ao diagnóstico somente o estado da proteção. O contrato pdv_single_instance_v1 usa mutex nomeado por hash da identidade do terminal para impedir duas janelas do mesmo caixa na sessão do Windows, sem expor o identificador e liberando o bloqueio ao encerrar. A reconfiguração também reserva primeiro a identidade atual, impedindo troca de ativação enquanto aquele caixa estiver em execução. Ainda faltam drivers/adaptadores reais e homologação presencial dos equipamentos."),
            ("Balanca integrada no PDV", "partial", "Produtos já possuem marcacao de produto pesavel. Terminal PDV agora permite configurar balanca por caixa com protocolo, porta/endereco e modelo; manifesto, pacote JSON e bootstrap do app desktop entregam essa configuracao por máquina usando o contrato pdv_scale_v1, com leitura automatica, unidade KG, precisao de 3 casas, timeout e fallback manual quando a balanca estiver ausente ou falhar. O app desktop já possui ponte local para expor a configuracao da balanca e retornar leitura estruturada com peso simulado para homologacao. A tela do PDV já chama a ponte local pelo botão Peso e atalho F12, preenchendo a quantidade quando recebe o peso ou orientando digitacao manual no navegador comum. Falhas e retornos manuais da balanca ficam registrados no log local devices.log.jsonl da máquina do caixa e podem ser consultados pela ponte deviceLogs; a Central do App PDV desktop já possui leitura visual desse diagnóstico quando aberta dentro do aplicativo instalado. O servidor já possui endpoint autenticado por terminal para receber lotes de diagnósticos locais e armazenar EventoDispositivoTerminal por caixa, e o app desktop tenta enviar automaticamente os eventos ainda não sincronizados na inicializacao sem bloquear a abertura do PDV. A Central do App PDV desktop exibe histórico consolidado dos eventos recebidos pelo servidor, e uma tela operacional própria oferece resumo, filtros por máquina/tipo/status/período, paginação e exportação CSV. A pré-homologação consolidada permite solicitar explicitamente uma leitura com peso conhecido e inclui protocolo, porta, modelo, peso e resultado na evidência sincronizável. O agente agora possui driver genérico real para Serial RS-232/USB via pyserial, TCP/IP e arquivo texto local, com timeout limitado, leitura máxima controlada, parser decimal, fator de conversão e rejeição de peso instável, zero, valor negativo e sobrecarga. O cadastro valida TCP/IP no formato endereço:porta e exige identificação do modelo para adaptadores proprietários. Falta validar parâmetros e comandos do fabricante escolhido, conectar a balança física e homologar precisão, estabilidade e timeout para ler peso automaticamente no PDV real."),
            ("TEF/API de maquininha", "partial", "Pagamentos possuem estados controlados, ID externo, NSU e autorizacao; venda rejeita transacao pendente, recusada ou estornada. Terminais PDV agora configuram provedor TEF e modo de integracao por adaptador, permitindo PagBank, Cielo, Stone, Getnet, Rede, SiTef ou outro fornecedor sem prender o sistema a uma operadora. O bootstrap do app desktop expõe o contrato pdv_tef_v1 com tipos crédito, débito e PIX dinâmico e retorno esperado. No PDV, pagamento eletrônico chama a ponte processPayment do app desktop, aguarda resposta da maquininha/simulador, grava transacao, NSU e autorizacao na linha de pagamento e bloqueia a finalizacao se não houver retorno confirmado; terminal sem TEF configurado retorna aviso ao operador. O app desktop possui simulador TEF rastreável para desenvolvimento enquanto o adaptador real da adquirente não estiver conectado, incluindo pagamento e refundPayment para estorno autorizado pela maquininha, e grava eventos locais tef em devices.log.jsonl, além de tef_estorno, para diagnóstico central de aprovações, falhas e terminais sem maquininha configurada. Antes de chamar o adaptador, a ponte valida modalidade liberada pelo bootstrap, valor monetário positivo e precisão máxima de centavos tanto no pagamento quanto no estorno. O front envia chave idempotente por tentativa e o bridge reutiliza a autorização ou estorno já aprovado quando a mesma solicitação for repetida na sessão, rejeitando a chave caso os dados mudem. Para PIX, o contrato também expõe checkPayment: primeiro retorna QR Code e estado pendente, depois consulta a transação até a adquirente confirmar, sem tratar a mera geração do QR como pagamento. A camada local agora possui contrato único de adaptadores para processar, consultar e estornar; o driver é escolhido na configuração protegida da máquina e respostas incompletas são rejeitadas sem aprovar a venda. O simulador deixou de ser implícito: depende de autorização explícita do servidor por PDV_TEF_SIMULATOR_ENABLED e fica bloqueado em produção, enquanto provedor configurado sem driver instalado falha de forma segura. Falta conectar e homologar o pacote real do provedor escolhido em equipamento físico, que também deverá honrar a chave idempotente."),
            ("Reversão de pagamento misto", "done", "Cancelamento total estorna parcelas locais e mantém PIX/TEF com transação externa em fila supervisionada até a confirmação da adquirente. Devoluções parciais rateiam o valor entre todos os pagamentos confirmados: a parcela local gera saída financeira imediata, enquanto cada fração eletrônica recebe solicitação própria, valor, motivo, vínculo com a devolução, estado e chave idempotente. O diagnóstico protegido payment_refund_readiness_v1 reúne estornos totais e parciais por antiguidade; a tela permite seleção por teclado e processamento com F10 ou Ctrl+Enter. A supervisão pode confirmar o estorno eletrônico aprovado pela operadora. A fila processa diretamente a parcela selecionada, aguarda a resposta da maquininha e, no navegador, exige evidência informada da adquirente. No app desktop, refundPayment chama o adaptador da maquininha com o valor proporcional e a transação original; somente a resposta aprovada cria o lançamento financeiro inverso, registra autorização, ID externo, usuário e auditoria. Reenvios confirmados são bloqueados, solicitações iguais do mesmo pagamento permanecem independentes e uma venda que já teve devolução parcial não aceita cancelamento total posterior, evitando duplicidade de estoque e reembolso. A conexão e homologação física de cada adquirente continuam controladas no item TEF/API de maquininha."),
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
            ("Etiquetas de gôndola profissionais", "partial", "O documento complementar de etiquetas foi incorporado ao checklist. A tela busca por nome, código de barras e SKU, aceita leitor que envia Enter, cópias por produto e modelos compacto 110x30 mm, completo 100x50 mm, A4 e modelos profissionais salvos por empresa, filial e terminal, sempre sem fundo colorido forçado. Configuracao inclui medidas, gaps, colunas, orientacao, DPI, mídia, impressora e linguagem; a tela envia o lote ao agente desktop, que gera ZPL, EPL, PPLA ou PPLB e imprime em RAW sem pré-visualizacao. O agente agora valida obrigatoriamente o contrato label_print_v1, impressora e código de barras/SKU, limita 500 produtos, 100 cópias por produto e 2.000 etiquetas por lote e grava diagnóstico local de sucesso ou falha para sincronização central. Ainda faltam testes com equipamentos físicos."),
            ("Desmembramento e fracionamento de produtos", "partial", 'Novo documento complementar incorporado ao checklist para estoque avançado. A frente ja possui models DesmembramentoProduto, ItemDesmembramentoProduto e ReceitaDesmembramento, receitas/conversões por empresa/filial, busca remota por código de barras, SKU e nome, simulação antes de confirmar, múltiplos destinos, lote/validade, rendimento esperado e alerta de rendimento abaixo do previsto. O serviço transacional faz baixa da origem, entrada dos destinos vendáveis ou subprodutos, descarte/perda vinculada sem aumentar saldo vendável, custo proporcional, auditoria e cancelamento seguro com movimentos inversos. Para açougue e hortifruti em KG, a prévia mostra rendimento total e excesso, e a confirmação exige fechamento exato da massa antes de qualquer movimento: produtos, subprodutos e perdas devem somar a origem, sem criação de peso nem desaparecimento de quebra não classificada; conversões de caixa/fardo para unidades continuam permitidas. As telas de lista, detalhe e receitas exibem quantidades no padrão brasileiro com quantidade_br, evitando 1,000 ou 20,000 quando o valor representa unidade inteira. Também foram iniciados kits/composições, produção interna, planejamento por demanda mínima, ordens de produção por setor, etapas, responsáveis, SLA, fila operacional, alertas auditáveis e relatórios/CSV gerenciais. Ainda faltam homologar fluxos reais de açougue, padaria e hortifruti com operação de loja.'),
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
            ("Consulta de CNPJ e CEP", "partial", "Formularios de empresa e filial possuem mascaras, avisos, campo auxiliar de CEP, botao de consulta CNPJ/CEP, contrato JSON cadastro_lookup_v1, validacao formal de CNPJ, validacao de CEP, reaproveitamento de dados locais de empresas/filiais por CNPJ ou CEP e preenchimento automatico dos campos vazios quando houver cadastro local correspondente. O endpoint aceita provedores HTTP externos configurados por CADASTRO_CNPJ_PROVIDER_URL, CADASTRO_CEP_PROVIDER_URL e CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS, normaliza respostas de CNPJ/CEP, expõe diagnóstico JSON com status dos provedores, timeout, modo local/offline, volume reaproveitável da base local e prontidão cadastro_lookup_readiness_v1 para distinguir fallback local, configuração parcial e provedores prontos para homologação, preserva fallback local/offline e retorna erro controlado quando o servico externo falhar. O front aplica tanto retorno local quanto retorno externo. Falta escolher e homologar a API oficial de producao para CNPJ e CEP."),
            ("Cadastros complementares padronizados", "done", "Clientes, fornecedores, produtos e usuários possuem formulários organizados por seções operacionais, com textos de apoio para PDV, compras e etapas futuras."),
            ("Imagens de produto", "done", "Foto principal e galeria adicional com legenda, ordenacao e remoção integradas ao cadastro e preparadas para exibicao no marketplace."),
            ("Políticas de entrega por filial", "partial", "Raio, faixas por distancia, pedido mínimo, frete grátis, bairros e horarios configuraveis implementados. O cálculo de entrega agora valida bairros atendidos e bloqueados, exigindo bairro quando a filial possui area atendida restrita. A tela de politicas permite simular subtotal, distancia manual, endereco para geocodificacao e bairro por filial usando a mesma regra do pedido real. O diagnóstico JSON informa os contratos delivery_geocode_v1 e delivery_policy_readiness_v1, valida ausência, lacunas, sobreposição e cobertura das faixas, classifica prontidão por filial, informa se MARKETPLACE_GEOCODING_PROVIDER_URL está configurado, timeout e fallback manual de distancia. O endpoint de status do parceiro marketplace_partner_v1 agora expõe a politica delivery_policy_v1 da filial, com retirada, entrega, raio, pedido minimo, frete gratis, bairros, faixas, geocoding e alertas antes do pedido real. Falta escolher e homologar provedor de mapa/rota de produção."),
            ("Certificado digital protegido", "done", "Configuracao fiscal aceita upload A1 .pfx/.p12, criptografa arquivo e senha, lê validade e mostra alertas de vencimento."),
            ("Identidade visual do supermercado", "done", "Logo no topo, marca d'água sutil no carrinho e paleta operacional restrita implementadas. A identidade do supermercado permanece em destaque; a assinatura do fornecedor Deigo Tecnologia será aplicada de forma discreta no aplicativo desktop, sem competir com a marca da loja."),
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
            ("Configuracao profissional de etiquetas", "partial", "Configuracao por empresa/filial persiste impressora, DPI, densidade, velocidade, mídia e linguagem. Modelos nomeados guardam largura, altura, gaps, colunas, orientacao, modelo padrao e vínculo opcional ao terminal; a tela de etiquetas aplica o modelo escolhido e o endpoint desktop sincroniza todos os parâmetros e expõe prontidão print_readiness_v1 com impressoras configuradas, linguagem nativa e modelos profissionais. A central de impressão também prepara etiqueta de teste por modelo para envio direto pelo app desktop. Ainda faltam testes físicos com equipamentos reais."),
            ("Linguagens nativas de impressoras", "partial", "Arquitetura contempla ZPL, EPL, PPLA e PPLB. A tela web monta um payload confiável no contrato label_print_v1, com modelo, produtos e cópias em chaves ASCII, consulta a prontidão print_readiness_v1 e aciona printLabels somente no app desktop; o agente gera ZPL, EPL, PPLA ou PPLB, converte medidas por DPI e envia ao spooler Windows em RAW com limite e retorno visível. No navegador permanece a impressão convencional. O teste de modelo usa a mesma ponte local e o mesmo contrato do lote real. A ponte bloqueia contrato incompatível ou lote excessivo antes do spooler e retorna ao operador a quantidade de produtos e cópias efetivamente enviada. Ainda faltam homologacao por modelo e testes físicos."),
        ],
    },
    {
        "titulo": "Escopo original a decidir",
        "descricao": "Itens previstos nos documentos iniciais que não devem desaparecer do roadmap sem uma decisão explícita de produto.",
        "itens": [
            ("Recuperação de senha", "partial", "Fluxo seguro por e-mail implementado com resposta pública neutra, link temporário de uso único, validação de senha do Django, telas próprias e configuração SMTP por ambiente. Em desenvolvimento, o backend de console permite testar sem provedor externo. O diagnóstico protegido não expõe host, senha ou credenciais e publica a prontidão password_reset_readiness_v1, distinguindo backend de desenvolvimento, configuração incompleta e SMTP pronto para homologação real. Falta configurar o provedor definitivo, validar SPF/DKIM/DMARC e homologar entrega e recuperação ponta a ponta para concluir o item."),
            ("Cotação e pedido de compra", "done", "Ciclo prévio completo com cotação por filial e itens, abertura controlada, propostas únicas por fornecedor, preços e disponibilidade por produto, comparação de totais e prazos e seleção auditada da proposta. A proposta escolhida gera pedido em rascunho sem estoque ou financeiro. O pedido possui envio, cancelamento e conversão única em entrada vinculada; excluir a entrada enquanto rascunho reabre o pedido. Somente a finalização da entrada usa o serviço existente para movimentar estoque e criar financeiro."),
            ("Importação de XML de entrada", "done", "Importação segura de NF-e autorizada implementada com limite de arquivo, bloqueio de DTD/entidades, validação da chave e prevenção de duplicidade. O sistema identifica fornecedor e filial por CNPJ, associa todos os produtos por GTIN ou código cadastrado e rejeita integralmente arquivos com itens sem correspondência. A NF-e cria somente uma entrada em rascunho auditada para revisão, separa total dos produtos do total fiscal usado no financeiro e não movimenta estoque ou contas antes da finalização pelo fluxo existente."),
            ("Estoque geral por lote, validade e custo histórico", "done", "Camada retrocompatível implementada sem substituir o saldo agregado: entradas manuais, compras e NF-e com grupo rastro podem gerar lotes com fabricação, validade, quantidade e custo histórico; saídas e vendas consomem as camadas por FEFO e registram a alocação por movimento. O painel lista saldos, vencidos e itens a vencer em 30 dias, enquanto estoque legado sem lote continua utilizável. A reconciliação permite atribuir saldo histórico a lotes com limite, autorização, motivo e auditoria sem alterar o físico; reduções de inventário ajustam camadas somente quando o rastreado excederia a nova contagem, e aumentos permanecem sem lote até atribuição explícita. Produção e desmembramento consomem lotes de componentes/origens por FEFO, criam camadas nos destinos identificados e seus cancelamentos restauram as alocações originais de forma transacional. A política de lote obrigatório por produto é opcional e vem desativada: quando ativada, bloqueia novas entradas, NF-e sem rastro e produtos gerados por produção ou desmembramento sem lote, sem impedir vendas e demais usos do saldo legado."),
        ],
    },
    {
        "titulo": "Próximas fases",
        "descricao": "Itens previstos na documentacao, ainda fora do MVP atual.",
        "itens": [
            ("Fiscal/NFC-e e NF-e", "partial", "Fila fiscal mostra vendas prontas, pendencias antes da acao e ultima tentativa automatica auditada; tela de produtos fiscais antecipa correcoes de NCM, CEST, origem, CST/CSOSN e alíquota. XML local usa UF e código IBGE da filial. A NFC-e segue a regra de ocorrer somente após pagamento confirmado: por padrao a venda tenta preparar a NFC-e automaticamente, mas o admin pode desativar essa tentativa por terminal PDV quando a empresa decidir operar aquele caixa sem comunicacao fiscal automatica. O PDV exibe no topo se o terminal identificado esta com fiscal automático ligado ou desligado. A venda presencial agora aceita CPF opcional na nota sem cadastro de cliente, pergunta o documento dentro do popup de pagamento, grava o dado na venda e inclui o CPF no XML local da NFC-e; CNPJ solicitado no caixa é bloqueado para NFC-e automática e orientado para NF-e modelo 55. Pedidos online/marketplace agora possuem documento do destinatário e podem preparar NF-e modelo 55 local, com série e natureza fiscal próprias, vinculada ao pedido. Painel fiscal agora traz prontidão por filial, certificado, séries, vendas aguardando documento, produtos com pendência e diagnóstico JSON fiscal_readiness_v1 para suporte. O diagnóstico também separa homologação simulada de produção real pelo contrato fiscal_production_readiness_v1, alertando quando existe filial em produção sem adaptador oficial SEFAZ configurado. Se faltar cadastro fiscal, a venda não trava e a pendencia fica auditada para correção. Transmissao simulada em homologacao gera chave, protocolo e auditoria, mas ainda faltam assinatura, schema oficial, transmissão SEFAZ real, captura de CPF/CNPJ pelo pinpad quando o TEF permitir e contingência quando a SEFAZ estiver indisponivel. Exportacao operacional de contingencia JSON agora gera pacote fiscal_contingencia_v1 com documentos prontos, rejeitados ou cancelados, XML, origem, filial, valores e auditoria, sem substituir assinatura ou autorizacao oficial da SEFAZ."),
            ("Financeiro completo", "partial", "Contas a pagar/receber, baixas, cancelamentos, categorias, fluxo de caixa, conciliacao PDV x financeiro, contas de movimento, vendas a vista do PDV no livro, transferencias entre contas, livro financeiro imutavel, estornos por lancamento inverso, resultado por receitas/despesas, cards gerenciais e exportacoes criadas. Resultado financeiro agora inclui visao por origem, categoria, conta de movimento, saldos por filial, balancete gerencial com saldo anterior, entradas, saidas e saldo final por conta, conciliação bancária imutável por lançamento com referência, responsável, filtros, paginação, CSV e auditoria, indicadores de cobertura conciliada por quantidade, valor e conta no fechamento gerencial e pacote contábil JSON, DRE gerencial com receita operacional, despesas, resultado e margem operacional, CSV gerencial para Excel e pacote contábil JSON financial_accounting_package_v1 para conferência interna com contador. A proxima evolucao inclui integracao final com fiscal/contábilidade e relatórios contábeis oficiais."),
            ("Entradas, saídas e livro contábil", "partial", "Contas de movimento por filial para caixa físico, banco, PIX e outras foram criadas com saldo inicial e saldo atual. Baixas geram entrada ou saída no livro imutavel, vendas a vista do PDV geram entradas automaticas por forma de pagamento, sangria e suprimento geram saída/entrada automatica no Caixa PDV, transferencias geram lançamentos espelhados, atômicos e auditados entre contas da mesma empresa, e estornos rastreáveis criam lancamento inverso sem alterar o original. O livro possui origem, usuario, data, filtros, exportacao CSV, validacao de saldo e conciliação bancária separada e imutável com referência de extrato, responsável e auditoria, relatório de receitas, despesas e resultado que ignora transferencias internas, e balancete gerencial que considera transferencias para refletir o saldo real das contas. Ainda faltam integracao automatica de origens fiscais/contábeis avancadas e relatórios contábeis oficiais. Referencia funcional identificada no ProjetoLimpoGitHub para migracao adaptada, sem alterar o projeto original."),
            ("Marketplace / pedido online", "partial", "Fluxo operacional completo, API segura com chave por plataforma, validacao de itens, idempotencia e acompanhamento visual de separacao/pagamento na listagem implementados. Pedidos agora guardam CPF, CNPJ ou documento estrangeiro do destinatário, inclusive pela API do parceiro, e o detalhe do pedido permite preparar NF-e modelo 55 local vinculada ao pedido online. A central de integracoes agora mostra saude operacional por canal, pedidos recebidos, pedidos abertos, pagamentos pendentes, alertas de homologacao e prontidão marketplace_partner_readiness_v1 por parceiro, com diagnostico JSON para suporte sem expor a chave completa. API de parceiros tambem possui endpoint autenticado marketplace_partner_v1 para validar chave, filial, recursos, idempotencia, politica de entrega e prontidão antes de enviar pedido real. Adaptadores especificos de cada parceiro e transmissão SEFAZ real seguem pendentes."),
            ("Impressao personalizada", "done", "Configuracoes de papel, margens, fonte, rodape, vias e impressão automatica aplicadas aos recibos. No app desktop, o botão pos-venda usa o payload autenticado existente, monta cupom operacional sem imagens e envia diretamente ao spooler Windows em RAW/ESC-POS, com até três vias, corte de papel e pulso opcional da gaveta, sem abrir pré-visualizacao."),
            ("Descoberta de impressoras locais", "done", "Central de impressão possui campo com sugestões e endpoint de configuracao. A ponte do app desktop consulta as impressoras instaladas no Windows sem shell interativo e devolve nome, porta, driver, estado e impressora padrao para a mesma interface do PDV, tratando timeout ou falha sem bloquear a venda."),
            ("Gaveta de dinheiro opcional", "partial", "Central de impressão permite habilitar ou desabilitar gaveta automatica por empresa/filial e documento de caixa. Bootstrap e pacote do terminal entregam o contrato pdv_cash_drawer_v1 com impressora, abertura em dinheiro e movimentos de caixa. O app desktop possui ponte openCashDrawer, envia pulso ESC/POS pela impressora configurada e registra diagnóstico local da gaveta em sucesso, falha ou desabilitado sem bloquear a venda. Venda em dinheiro, sangria, suprimento, abertura e fechamento de caixa agendam abertura somente depois da operacao ser aceita pelo servidor, preservando senha de supervisor/admin quando exigida. A pré-homologação não aciona a gaveta por padrão e só envia o pulso após seleção explícita e confirmação de segurança pelo operador, registrando a evidência consolidada. Falta testar com gavetas físicas reais."),
            ("Backup/restauracao operacional", "done", "Tela de backup JSON e roteiro de restauracao segura disponíveis em Sistema."),
            ("Modo local administrativo", "partial", "Para supermercados sem internet ou sem rede estruturada, o produto deve permitir instalação local do servidor administrativo na própria loja, em um computador servidor ou máquina principal, acessado por navegador em localhost ou rede interna. Não é necessário duplicar todo o ERP em um segundo app desktop administrativo; a abordagem profissional é empacotar o servidor local, banco, serviços, backup, atualizações controladas e um atalho/app shell opcional para abrir o painel administrativo. A central Sistema > Servidor local já apresenta arquitetura, requisitos, modos por empresa, riscos pendentes, manifesto JSON erp_local_admin_v1, guia docs/IMPLANTACAO_SERVIDOR_LOCAL.md e scripts scripts/run_local_server.ps1, scripts/install_local_server_service.ps1, scripts/test_local_server_service.ps1, scripts/uninstall_local_server_service.ps1, server_local/windows/MercaFlowServidorLocal.xml.template, scripts/register_local_server_task.ps1, scripts/backup_local.ps1, scripts/register_backup_task.ps1 e scripts/register_sync_task.ps1 para operação local inicial, backup e sincronização recorrente no Windows. O backup local já suporta criptografia opcional AES-256 por BACKUP_ENCRYPTION_PASSPHRASE e remoção do zip aberto com -RemoverOriginalCriptografado. Manifesto e tela do servidor local agora especificam o contrato de servico Windows MercaFlowServidorLocal, comando WSGI via Waitress, healthcheck, restart, logs, fallback operacional e contrato de prontidao local_admin_readiness_v1 validando scripts, guia, backup criptografado e modos de implantacao. O PDV desktop continua separado e restrito ao operador, enquanto gerente/admin acessa o mesmo sistema web local com permissões completas. O servico Windows real agora possui instalador WinSW validado por SHA-256, Waitress, inicio automatico, reinicio em falha, logs, diagnostico e remocao; a tarefa agendada fica como contingencia. Falta homologar em uma maquina Windows limpa, definir a conta dedicada, empacotar a distribuicao assinada e concluir a politica final de sincronizacao opcional com a nuvem."),
            ("Aplicativo desktop/PDF", "partial", "Endpoints de configuracao e payload de impressão da venda preparados para o app desktop, incluindo dados de pagamento eletrônico, NSU, autorizacao e transacao externa para cupom e comprovante. A interface desktop reutiliza o mesmo design, componentes, atalhos e regras do PDV web em um shell WebView separado, adaptando apenas a camada de integracao com hardware e serviços locais. O esqueleto desktop_pdv possui ativacao guiada na primeira execucao, valida o bootstrap licenciado antes de salvar a credencial em LOCALAPPDATA e abrir /pdv/, permite reconfiguracao e protege a chave de versionamento. O build reproduzivel do executavel Windows com PyInstaller também foi preparado. A Central do App PDV desktop publica o instalador somente quando o artefato configurado existe, apresenta tamanho e SHA-256, restringe o download ao admin master e registra a entrega na auditoria. Um script de publicacao atômica confere integridade, impede arquivo parcial na central e grava metadados de versao; versao e caminho do artefato sao configuraveis por ambiente. O app informa sua versao no bootstrap, recebe versao vigente e minima, avisa atualizacao opcional e bloqueia versao insegura; a instalacao continua exigindo o admin master, sem atualizacao automatica fora do licenciamento. O app desktop agora salva cache local do bootstrap autorizado e, se o servidor estiver indisponivel, abre com esse cache somente quando o terminal permite modo offline, registrando diagnostico local; recusa de licença, chave ou terminal bloqueado nunca usa o cache como atalho. O manifesto JSON do app desktop expõe disponibilidade, integridade, contratos, terminais autorizados e prontidão de distribuição pelo contrato pdv_desktop_readiness_v1, alertando falta de instalador assinado, ausência de terminais e licenças pendentes. Pacote JSON por terminal entrega bootstrap, URL da interface compartilhada, TEF, fiscal, impressão, gaveta, balanca configurada, licenca por máquina e sincronizacao; o bootstrap operacional também devolve a configuracao atual a cada inicializacao. Terminais pendentes, bloqueados ou cancelados não recebem pacote de ativacao nem conseguem inicializar o bootstrap. O aplicativo continua sendo um projeto/artefato separado, baixado por dentro do sistema somente com autorizacao do admin master e configurado com o terminal autorizado. O canal de manutenção por terminal licenciado baixa o artefato publicado pelo ERP, confere SHA-256 antes de promovê-lo na pasta local de updates e nunca instala silenciosamente; pacote adulterado ou incompleto é descartado. A estrutura pdv_windows_installer_v1 usa WiX v4 para MSI por maquina, upgrade, atalhos, desinstalacao, metadados SHA-256, exigencia opcional de executavel assinado e assinatura do MSI via signtool; a publicacao atomica prioriza o MSI da versao. A Central, o download administrativo, o bootstrap e a atualização do terminal compartilham o mesmo validador: exigem manifesto .version.json, versão vigente e SHA-256 correspondente; em produção, PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER também exige as assinaturas válidas declaradas pelo pipeline antes de distribuir. Falta executar o build com certificado real, publicar o MSI assinado, homologar instalacao/upgrade/desinstalacao em Windows limpo, conectar dispositivos locais e implementar sincronizacao resiliente com servidor local/nuvem."),
            ("Sincronizacao loja-nuvem", "partial", "Empresa escolhe entre servidor local, hibrido e nuvem com agente. Caixa de saída, processador HTTP e caixa de entrada autenticada usam UUID, idempotencia, token fora do banco, timeout, lotes e retentativa exponencial. Eventos recebidos ficam armazenados antes de alterar dados e já passam por processador interno com handlers por tipo, erro controlado para domínios ainda não implementados, handler inicial de produtos, handler de saldo de estoque por filial, espelho de venda finalizada com painel de retaguarda, espelho fiscal sincronizado, detalhe auditável de eventos com payload e diagnóstico, resolução manual de conflitos com responsável, decisão e LogAuditoria, reprocessamento de entrada/saída também auditado, exportacao CSV das filas de saída e entrada, diagnóstico JSON operacional com filas, alertas, próximos eventos, idade da fila mais antiga, eventos de saída com tentativas esgotadas, empresas por modo, contrato de prontidão sync_readiness_v1 e comando sugerido, comando único agendável, roteiro do Agendador de Tarefas do Windows no painel e script scripts/register_sync_task.ps1 para registrar a rotina recorrente. Movimentações locais de venda, compra, inventário, perda, produção e ajustes agora publicam automaticamente primeiro o snapshot do produto e depois o saldo consolidado da filial, pelos contratos produto_snapshot_v1 e estoque_saldo_v1. Revisões usam hash do conteúdo, saldos usam chave idempotente por movimento e atualizações recebidas da nuvem são marcadas para não gerar eco de produto ou estoque. O comando gerar_snapshot_sincronizacao e a acao protegida no painel preparam a carga inicial de catálogo e saldos já existentes por empresa ou filial, podem ser repetidos sem duplicar eventos, bloqueiam empresas que escolheram o modo somente local e registram a operacao web no log de auditoria. Politica automatica opcional de conflito por empresa foi iniciada: manual por padrao, com nuvem prevalecendo apenas para produtos e saldo de estoque quando configurado, mantendo venda e fiscal para decisao auditavel; painel, diagnostico JSON, listagem de empresas e detalhe auditavel do evento exibem a politica aplicada, e o admin tecnico permite filtrar esse campo. Ainda faltam transmissao SEFAZ real e politicas finais para outros tipos de conflito."),
            ("Super admin personalizado", "done", "Painel próprio centraliza empresas, usuários, fiscal, formas de pagamento, impressoes, backup, auditoria e checklist, sem atalho visual para o admin Django. A tela Sistema > Super admin reúne visão executiva, atalhos críticos, pendências acionáveis, saúde da sincronização, estornos eletrônicos pendentes com quantidade, valor e tela operacional própria, cobertura de telas próprias, atividade recente, atalhos de investigação, diagnóstico de ambiente/segurança, inventário de modelos, inspeção protegida e paginada por modelo, diagnóstico JSON e exportação CSV restritos ao admin master para acompanhar dados avançados sem entrar no admin padrão. Séries fiscais e naturezas de operação já possuem CRUD guiado, validação e auditoria próprios; sincronização e diagnósticos de dispositivos também possuem consultas protegidas, A fila interna de modelos avançados está concluída. Homologações externas e de hardware permanecem acompanhadas nos itens técnicos específicos."),
        ],
    },
]


def _instalador_pdv_desktop():
    return artefato_pdv_desktop()


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
        item["impacto_estimado"] = item["alta"] + (item["media"] * 0.5)
        item["peso_label"] = f"{item['impacto_estimado']:.1f}".replace(".", ",")
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
                "modelo_tecnico": modelo._meta.object_name,
                "total": total,
                "inspecao_url": reverse("configuracoes:super_admin_modelo", args=[modelo._meta.app_label, modelo._meta.model_name]),
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
    estornos_pendentes_qs = PagamentoVenda.objects.filter(status=StatusPagamento.ESTORNO_PENDENTE)
    estornos_pendentes = estornos_pendentes_qs.count()
    valor_estornos_pendentes = estornos_pendentes_qs.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
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
        {
            "titulo": "Estornos eletrônicos pendentes",
            "valor": estornos_pendentes,
            "descricao": f"PIX/TEF aguardando retorno da adquirente. Valor pendente: R$ {valor_estornos_pendentes:.2f}.",
            "status": "Pagamentos",
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
        {
            "prioridade": "Alta",
            "titulo": "Estornos eletrônicos pendentes",
            "total": estornos_pendentes,
            "acao": f"Processar na adquirente e confirmar o retorno aprovado. Valor pendente: R$ {valor_estornos_pendentes:.2f}.",
            "url_name": "pdv:estornos_eletronicos",
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
            "status": "Completa",
            "observacao": "Configuração, séries e naturezas com CRUD guiado e auditado, além de documentos, XML e pendências fiscais em telas próprias.",
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
            "observacao": "Licença, chave API, fiscal por terminal, TEF, balança, pacote desktop e diagnóstico paginado por máquina com filtros e CSV.",
            "url_name": "configuracoes:terminais_pdv",
        },
        {
            "area": "Sincronização",
            "modelos": "EventoSincronizacao, EventoEntradaSincronizacao, VendaSincronizada, DocumentoFiscalSincronizado",
            "status": "Completa",
            "observacao": "Painel protegido com filtros, espelhos de vendas e documentos, detalhes, CSV, conflitos e reprocessamento auditado; CRUD direto não é permitido.",
            "url_name": "empresas:sincronizacao",
        },
        {
            "area": "Auditoria e backup",
            "modelos": "LogAuditoria, modelos exportáveis",
            "status": "Completa",
            "observacao": "Logs filtráveis, exportação CSV e backup operacional protegidos em telas próprias.",
            "url_name": "auditoria:logs",
        },
    ]
    modelos_avancados_pendentes = []
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
        "modelos_avancados_pendentes": modelos_avancados_pendentes,
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
    for item in payload["modelos_avancados_pendentes"]:
        writer.writerow(["Modelo avancado", item["area"], item["prioridade"], item["status"], item["acao"]])
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


def _modelo_super_admin(app_label, model_name):
    ignorar = {"Permission", "ContentType", "Session", "LogEntry"}
    modelo = apps.get_model(app_label, model_name)
    if not modelo or modelo._meta.object_name in ignorar:
        raise Http404("Modelo indisponivel para inspecao.")
    return modelo


def _campos_inspecao_modelo(modelo):
    campos = []
    for campo in modelo._meta.fields:
        if campo.get_internal_type() == "BinaryField":
            continue
        campos.append(campo)
        if len(campos) >= 8:
            break
    return campos


def _valor_inspecao(objeto, campo):
    nome = campo.name.lower()
    if any(chave in nome for chave in ["password", "senha", "token", "secret", "chave", "hash"]):
        return "••••"
    valor = getattr(objeto, campo.name, None)
    if valor in (None, ""):
        return "-"
    if hasattr(valor, "name") and campo.get_internal_type() == "FileField":
        return valor.name or "-"
    texto = str(valor)
    return f"{texto[:117]}..." if len(texto) > 120 else texto


@login_required
@role_required(*SISTEMA)
def super_admin_modelo(request, app_label, model_name):
    _exigir_admin_master(request.user)
    modelo = _modelo_super_admin(app_label, model_name)
    termo = (request.GET.get("q") or "").strip()
    queryset = modelo._default_manager.all()
    campos_busca = [
        campo.name
        for campo in modelo._meta.fields
        if campo.get_internal_type() in {"CharField", "TextField", "EmailField", "SlugField", "URLField"}
    ]
    if termo and campos_busca:
        filtro = Q()
        for campo in campos_busca:
            filtro |= Q(**{f"{campo}__icontains": termo})
        queryset = queryset.filter(filtro)
    if modelo._meta.pk:
        queryset = queryset.order_by(modelo._meta.pk.name)
    campos = _campos_inspecao_modelo(modelo)
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    linhas = [
        {
            "pk": objeto.pk,
            "valores": [_valor_inspecao(objeto, campo) for campo in campos],
        }
        for objeto in page_obj.object_list
    ]
    context = {
        "modelo": modelo,
        "modelo_nome": str(modelo._meta.verbose_name_plural).capitalize(),
        "modelo_tecnico": modelo._meta.object_name,
        "modelo_app": modelo._meta.app_label,
        "app_label": app_label,
        "model_name": model_name,
        "termo": termo,
        "campos": campos,
        "linhas": linhas,
        "page_obj": page_obj,
        "total": paginator.count,
        "campos_busca": campos_busca,
    }
    return render(request, "configuracoes/super_admin_modelo.html", context)



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
    resumo = _resumo_checklist(grupos)
    resumo["diferenca_ponderada"] = max(0, resumo["percentual_ponderado"] - resumo["percentual"])
    resumo_filtrado = _resumo_checklist(grupos_filtrados)
    context = {
        "grupos": grupos_filtrados,
        "resumo": resumo,
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


def _pdv_desktop_readiness_payload(instalador, terminais_qs):
    total_terminais = terminais_qs.count()
    ativos = terminais_qs.filter(ativo=True).count()
    liberados = terminais_qs.filter(status_licenca=StatusLicencaTerminal.LIBERADA, ativo=True).count()
    pendentes = terminais_qs.filter(status_licenca=StatusLicencaTerminal.PENDENTE).count()
    bloqueados = terminais_qs.filter(status_licenca__in=[StatusLicencaTerminal.BLOQUEADA, StatusLicencaTerminal.CANCELADA]).count()
    sem_tef = terminais_qs.filter(ativo=True, provedor_tef="").count()
    sem_fiscal = terminais_qs.filter(ativo=True, emite_documento_fiscal=False).count()
    com_balanca = terminais_qs.filter(ativo=True, usa_balanca=True).count()
    pilotos = terminais_qs.filter(ativo=True, canal_atualizacao=CanalAtualizacaoPdv.PILOTO).count()
    atualizacoes_congeladas = terminais_qs.filter(ativo=True, bloquear_atualizacoes=True).count()
    build_msi_script = settings.BASE_DIR / "desktop_pdv" / "build_msi.ps1"
    build_msi_template = settings.BASE_DIR / "desktop_pdv" / "installer" / "Product.wxs.template"
    build_msi_preparado = build_msi_script.is_file() and build_msi_template.is_file()
    bloqueios = []
    recomendacoes = []
    if not instalador["disponivel"]:
        bloqueios.extend(instalador["problemas"] or ["Publicar o instalador Windows assinado antes de distribuir o app PDV desktop."])
    if not build_msi_preparado:
        bloqueios.append("Preparar script e template reproduziveis para gerar o instalador MSI.")
    if not total_terminais:
        bloqueios.append("Cadastrar ao menos um terminal PDV antes da instalacao.")
    if ativos and not liberados:
        bloqueios.append("Liberar a licenca de pelo menos um terminal ativo para baixar o pacote de ativacao.")
    if pendentes:
        recomendacoes.append(f"Revisar {pendentes} terminal(is) com licenca pendente.")
    if bloqueados:
        recomendacoes.append(f"Manter {bloqueados} terminal(is) bloqueado(s)/cancelado(s) fora da distribuicao.")
    if sem_tef:
        recomendacoes.append(f"{sem_tef} terminal(is) ativo(s) sem provedor TEF configurado usarao somente fallback/manual.")
    if sem_fiscal:
        recomendacoes.append(f"{sem_fiscal} terminal(is) ativo(s) com fiscal automatico desligado.")
    if atualizacoes_congeladas:
        recomendacoes.append(f"{atualizacoes_congeladas} terminal(is) com atualizacoes opcionais congeladas pelo admin master.")
    if bloqueios:
        status = "Bloqueada"
        percentual = 45
        proximo_passo = bloqueios[0]
    elif recomendacoes:
        status = "Pronta com ressalvas"
        percentual = 85
        proximo_passo = recomendacoes[0]
    else:
        status = "Pronta"
        percentual = 100
        proximo_passo = "Distribuicao pronta para terminais licenciados."
    return {
        "contrato": "pdv_desktop_readiness_v1",
        "status": status,
        "percentual": percentual,
        "proximo_passo": proximo_passo,
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "instalador": {
            "disponivel": instalador["disponivel"],
            "nome": instalador["nome"],
            "sha256": instalador["sha256"],
            "build_msi_preparado": build_msi_preparado,
            "assinatura_obrigatoria_producao": True,
        },
        "terminais": {
            "total": total_terminais,
            "ativos": ativos,
            "licencas_liberadas": liberados,
            "licencas_pendentes": pendentes,
            "bloqueados_cancelados": bloqueados,
            "sem_tef": sem_tef,
            "sem_fiscal_automatico": sem_fiscal,
            "com_balanca": com_balanca,
            "canal_piloto": pilotos,
            "atualizacoes_congeladas": atualizacoes_congeladas,
        },
    }


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
    prontidao_desktop = _pdv_desktop_readiness_payload(instalador, terminais)
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
        "prontidao_desktop": prontidao_desktop,
        "artefatos": [
            {
                "nome": "Windows x64",
                "status": "Empacotamento pronto",
                "descricao": "PyInstaller gera o executavel e WiX v4 monta MSI por maquina com upgrade, atalhos, desinstalacao, SHA-256 e assinatura opcional.",
            },
            {
                "nome": "Bridge local",
                "status": "Contrato pronto",
                "descricao": "Conecta impressora, gaveta, TEF, balanca e servidor local, mantendo a chave do terminal protegida pelo DPAPI do Windows.",
            },
            {
                "nome": "Atualizacao controlada",
                "status": "Canal pronto",
                "descricao": "Terminal licenciado baixa o pacote publicado, valida SHA-256 e mantém a instalacao manual.",
            },
        ],
    }
    return render(request, "configuracoes/pdv_desktop.html", context)


def _pdv_desktop_manifest_payload(request):
    terminais = TerminalPdv.objects.select_related("filial", "filial__empresa").order_by("filial__nome", "nome")
    instalador = _instalador_pdv_desktop()
    prontidao_desktop = _pdv_desktop_readiness_payload(instalador, terminais)
    return {
        "status": "ok",
        "versao_planejada": PDV_DESKTOP_VERSAO_PLANEJADA,
        "distribuicao": "erp",
        "politica_atualizacao": {
            "contrato": "pdv_update_rollout_v1",
            "canal_versao": settings.PDV_DESKTOP_RELEASE_CHANNEL,
            "instalacao_automatica": False,
            "versao_minima_sobrepoe_congelamento": True,
        },
        "licenciamento": {
            "modelo": "por_terminal",
            "download_requer_admin_master": True,
            "ativacao_requer_terminal_autorizado": True,
            "observacao": "Cada máquina de caixa deve ser liberada pelo admin master antes de baixar/ativar o app desktop.",
        },
        "prontidao": prontidao_desktop,
        "contratos": {
            "tef": "pdv_tef_v1",
            "impressao": "pdv_print_v1",
            "sincronizacao": "pdv_sync_v1",
            "fila_eventos_dispositivo": "pdv_device_event_queue_v1",
            "instalador_windows": "pdv_windows_installer_v1",
            "credencial_local": "pdv_local_secret_v1",
            "instancia_local": "pdv_single_instance_v1",
        },
        "recursos": {
            "tef_integrado": True,
            "impressao_desktop": True,
            "gaveta_opcional": True,
            "balanca_local": True,
            "fiscal_por_terminal": True,
            "modo_offline": True,
            "credencial_terminal_dpapi": True,
            "configuracao_tef_dpapi": True,
            "instancia_unica_por_terminal": True,
            "eventos_dispositivo_idempotentes": True,
            "compactacao_preserva_pendentes": True,
            "sincronizacao_periodica_eventos": True,
        },
        "artefatos": {
            "windows_x64": {
                "status": "disponivel" if instalador["disponivel"] else "aguardando_build",
                "nome": instalador["nome"],
                "url": request.build_absolute_uri("/configuracoes/pdv-desktop/download/windows/") if instalador["disponivel"] else "",
                "tamanho_bytes": instalador["tamanho"],
                "sha256": instalador["sha256"],
                "integridade_valida": instalador["integridade_valida"],
                "versao_valida": instalador["versao_valida"],
                "assinatura_valida": instalador["assinatura_valida"],
                "assinatura_exigida": instalador["assinatura_exigida"],
                "problemas": instalador["problemas"],
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
                "atualizacao": {
                    "canal": terminal.canal_atualizacao,
                    "bloqueada_pelo_admin": terminal.bloquear_atualizacoes,
                },
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
    instalador = artefato_pdv_desktop()
    if not instalador["publicavel"]:
        raise Http404("Instalador do PDV desktop indisponivel ou reprovado na validacao.")
    caminho = instalador["caminho"]
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
        "atualizacao": {
            "contrato": "pdv_update_rollout_v1",
            "canal_terminal": terminal.canal_atualizacao,
            "canal_versao": settings.PDV_DESKTOP_RELEASE_CHANNEL,
            "bloqueada_pelo_admin": terminal.bloquear_atualizacoes,
            "instalacao_automatica": False,
            "versao_minima_sobrepoe_congelamento": True,
        },        "filial": {
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


def _servidor_local_prontidao(base_dir, scripts, pendencias, modos):
    obrigatorios = {
        "subir_servidor": scripts["subir_servidor"],
        "registrar_servidor": scripts["registrar_servidor"],
        "instalar_servico": scripts["instalar_servico"],
        "diagnosticar_servico": scripts["diagnosticar_servico"],
        "remover_servico": scripts["remover_servico"],
        "template_servico": scripts["template_servico"],
        "backup_local": scripts["backup_local"],
        "registrar_backup": scripts["registrar_backup"],
        "registrar_sincronizacao": scripts["registrar_sincronizacao"],
        "guia": scripts["guia"],
    }
    arquivos = {
        chave: {
            "caminho": caminho,
            "existe": (base_dir / caminho).exists(),
        }
        for chave, caminho in obrigatorios.items()
    }
    ausentes = [info["caminho"] for info in arquivos.values() if not info["existe"]]
    planejados = [item["titulo"] for item in pendencias if item["status"] == "planejado"]
    iniciados = [item["titulo"] for item in pendencias if item["status"] == "iniciado"]
    backup_criptografia_configurada = bool(os.getenv("BACKUP_ENCRYPTION_PASSPHRASE"))
    bloqueios = []
    recomendacoes = []
    if ausentes:
        bloqueios.append("Arquivos obrigatorios ausentes: " + ", ".join(ausentes))
    if planejados:
        recomendacoes.append("Concluir itens planejados: " + ", ".join(planejados))
    if iniciados:
        recomendacoes.append("Homologar itens iniciados: " + ", ".join(iniciados))
    if not backup_criptografia_configurada:
        recomendacoes.append("Configurar BACKUP_ENCRYPTION_PASSPHRASE antes de usar backup criptografado em producao.")
    if bloqueios:
        status = "Bloqueada"
        percentual = 50
        proximo_passo = bloqueios[0]
    elif planejados:
        status = "Homologacao parcial"
        percentual = 78
        proximo_passo = recomendacoes[0]
    elif recomendacoes:
        status = "Pronta com ressalvas"
        percentual = 90
        proximo_passo = recomendacoes[0]
    else:
        status = "Pronta"
        percentual = 100
        proximo_passo = "Servidor local administrativo pronto para operacao assistida."
    return {
        "contrato": "local_admin_readiness_v1",
        "status": status,
        "percentual": percentual,
        "proximo_passo": proximo_passo,
        "backup_criptografia_configurada": backup_criptografia_configurada,
        "arquivos": arquivos,
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "empresas_por_modo": {
            "local": modos.get(ModoImplantacao.LOCAL, 0),
            "hibrido": modos.get(ModoImplantacao.HIBRIDO, 0),
            "nuvem_agente": modos.get(ModoImplantacao.NUVEM_AGENTE, 0),
        },
    }


def _servidor_local_payload(request):
    empresas = Empresa.objects.prefetch_related("filiais").order_by("nome_fantasia")
    modos = {
        modo: empresas.filter(modo_implantacao=modo).count()
        for modo in ModoImplantacao.values
    }
    servico_windows = {
        "contrato": "local_windows_service_v1",
        "nome": "MercaFlowServidorLocal",
        "status": "instalador_preparado",
        "tipo": "Windows Service via WinSW",
        "usuario_recomendado": "Conta de servico local dedicada e com acesso minimo aos arquivos do ERP",
        "comando_producao": r".\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 config.wsgi:application",
        "instalador": "scripts/install_local_server_service.ps1",
        "desinstalador": "scripts/uninstall_local_server_service.ps1",
        "diagnostico": "scripts/test_local_server_service.ps1",
        "template": "server_local/windows/MercaFlowServidorLocal.xml.template",
        "wrapper": "WinSW fornecido pelo administrador e validado por SHA-256 antes da instalacao",
        "fallback_operacional": "scripts/register_local_server_task.ps1 -Bind 0.0.0.0 -Port 8000 -AtStartup",
        "healthcheck": "/login/",
        "restart": "Inicio automatico com o Windows e reinicio 10 segundos apos falha",
        "logs": [r"%ProgramData%\MercaFlow\ServidorLocal\logs", "logs/django.log"],
        "observacao": "Scripts e contrato do servico estao preparados; a conclusao depende de instalar o WinSW verificado e homologar em uma maquina Windows da loja.",
    }
    pendencias = [
        {
            "titulo": "Servico Windows/Linux",
            "status": "iniciado",
            "descricao": "Servico Windows preparado com WinSW, Waitress, inicio automatico, reinicio em falha, logs rotativos, healthcheck e scripts de instalacao, diagnostico e remocao. A tarefa agendada permanece como fallback; falta homologar o servico em Windows de loja e definir a conta dedicada.",
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
    scripts = {
        "subir_servidor": "scripts/run_local_server.ps1",
        "registrar_servidor": "scripts/register_local_server_task.ps1",
        "instalar_servico": "scripts/install_local_server_service.ps1",
        "diagnosticar_servico": "scripts/test_local_server_service.ps1",
        "remover_servico": "scripts/uninstall_local_server_service.ps1",
        "template_servico": "server_local/windows/MercaFlowServidorLocal.xml.template",
        "backup_local": "scripts/backup_local.ps1",
        "registrar_backup": "scripts/register_backup_task.ps1",
        "registrar_sincronizacao": "scripts/register_sync_task.ps1",
        "guia": "docs/IMPLANTACAO_SERVIDOR_LOCAL.md",
        "backup_criptografia_env": "BACKUP_ENCRYPTION_PASSPHRASE",
        "backup_criptografia_flag": "-RemoverOriginalCriptografado",
    }
    prontidao = _servidor_local_prontidao(Path(settings.BASE_DIR), scripts, pendencias, modos)
    return {
        "status": "ok",
        "contrato": "erp_local_admin_v1",
        "recomendacao": "Servidor local administrativo com acesso via navegador; app desktop completo apenas para PDV.",
        "prontidao": prontidao,
        "acesso": {
            "admin_local_url": request.build_absolute_uri("/configuracoes/"),
            "usa_navegador": True,
            "app_shell_opcional": True,
            "pdv_desktop_separado": True,
        },
        "servico_windows": servico_windows,
        "scripts": scripts,
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
            "prontidao": payload["prontidao"],
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



def _eventos_dispositivo_filtrados(request):
    eventos = EventoDispositivoTerminal.objects.select_related(
        "terminal",
        "terminal__filial",
        "terminal__filial__empresa",
    ).order_by("-recebido_em")
    filtros = {
        "q": request.GET.get("q", "").strip(),
        "terminal": request.GET.get("terminal", "").strip(),
        "tipo": request.GET.get("tipo", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "inicio": request.GET.get("inicio", "").strip(),
        "fim": request.GET.get("fim", "").strip(),
    }
    if filtros["q"]:
        eventos = eventos.filter(
            Q(terminal__nome__icontains=filtros["q"])
            | Q(terminal__filial__nome__icontains=filtros["q"])
            | Q(terminal__filial__empresa__nome_fantasia__icontains=filtros["q"])
            | Q(tipo__icontains=filtros["q"])
            | Q(status__icontains=filtros["q"])
            | Q(mensagem__icontains=filtros["q"])
        )
    if filtros["terminal"].isdigit():
        eventos = eventos.filter(terminal_id=filtros["terminal"])
    if filtros["tipo"]:
        eventos = eventos.filter(tipo=filtros["tipo"])
    if filtros["status"]:
        eventos = eventos.filter(status=filtros["status"])
    inicio = parse_date(filtros["inicio"])
    fim = parse_date(filtros["fim"])
    if inicio:
        eventos = eventos.filter(recebido_em__date__gte=inicio)
    if fim:
        eventos = eventos.filter(recebido_em__date__lte=fim)
    return eventos, filtros


@login_required
@role_required(*SISTEMA)
def terminais_pdv_diagnosticos(request):
    eventos, filtros = _eventos_dispositivo_filtrados(request)
    resumo = eventos.values("tipo", "status").annotate(total=Count("id")).order_by("tipo", "status")
    pagina = Paginator(eventos, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "configuracoes/terminais_pdv_diagnosticos.html",
        {
            "pagina": pagina,
            "filtros": filtros,
            "query_sem_pagina": query.urlencode(),
            "terminais": TerminalPdv.objects.select_related("filial").order_by("filial__nome", "nome"),
            "tipos": EventoDispositivoTerminal.objects.exclude(tipo="").values_list("tipo", flat=True).distinct().order_by("tipo"),
            "status_opcoes": EventoDispositivoTerminal.objects.exclude(status="").values_list("status", flat=True).distinct().order_by("status"),
            "resumo": resumo,
            "total": eventos.count(),
        },
    )


@login_required
@role_required(*SISTEMA)
def terminais_pdv_diagnosticos_csv(request):
    eventos, _ = _eventos_dispositivo_filtrados(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="diagnosticos_terminais_pdv.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Recebido", "Ocorrido no caixa", "Empresa", "Filial", "Terminal", "Identificador", "Tipo", "Status", "Mensagem"])
    for evento in eventos:
        writer.writerow([
            timezone.localtime(evento.recebido_em).strftime("%d/%m/%Y %H:%M:%S"),
            timezone.localtime(evento.ocorrido_em).strftime("%d/%m/%Y %H:%M:%S") if evento.ocorrido_em else "",
            evento.terminal.filial.empresa.nome_fantasia,
            evento.terminal.filial.nome,
            evento.terminal.nome,
            evento.terminal.identificador,
            evento.tipo,
            evento.status,
            evento.mensagem,
        ])
    return response


@login_required
@role_required(*SISTEMA)
def terminal_pdv_form(request, pk=None):
    terminal = get_object_or_404(TerminalPdv, pk=pk) if pk else None
    politica_anterior = (
        terminal.canal_atualizacao,
        terminal.bloquear_atualizacoes,
    ) if terminal else None
    form = TerminalPdvForm(request.POST or None, instance=terminal)
    if not _usuario_admin_master(request.user):
        form.fields["canal_atualizacao"].disabled = True
        form.fields["bloquear_atualizacoes"].disabled = True
    if request.method == "POST" and form.is_valid():
        terminal_anterior = terminal
        terminal = form.save(commit=False)
        if not _usuario_admin_master(request.user):
            if terminal_anterior:
                terminal.status_licenca = terminal_anterior.status_licenca
                terminal.licenca_liberada_em = terminal_anterior.licenca_liberada_em
                terminal.licenca_liberada_por = terminal_anterior.licenca_liberada_por
                terminal.observacao_licenca = terminal_anterior.observacao_licenca
                terminal.canal_atualizacao = politica_anterior[0]
                terminal.bloquear_atualizacoes = politica_anterior[1]
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
        politica_atual = (terminal.canal_atualizacao, terminal.bloquear_atualizacoes)
        if politica_anterior != politica_atual and _usuario_admin_master(request.user):
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="configuracoes",
                acao="POLITICA_ATUALIZACAO_TERMINAL_PDV",
                descricao=(
                    f"Politica de atualizacao do terminal {terminal.nome}: "
                    f"canal {terminal.get_canal_atualizacao_display()}, "
                    f"congelada {'sim' if terminal.bloquear_atualizacoes else 'nao'}."
                ),
                objeto_tipo="TerminalPdv",
                objeto_id=str(terminal.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
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
    resumo = {
        "total": configuracoes.count(),
        "com_impressora": 0,
        "sem_impressora": 0,
        "etiquetas": 0,
        "etiquetas_com_linguagem_nativa": 0,
        "modelos_profissionais": 0,
    }
    alertas = []
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
        modelos_ativos = [modelo for modelo in config.modelos_etiqueta.all() if modelo.is_active]
        resumo["com_impressora" if impressora_configurada else "sem_impressora"] += 1
        if mensagem_impressora:
            alertas.append(mensagem_impressora)
        if config.tipo_documento == TipoDocumentoImpressao.ETIQUETA:
            resumo["etiquetas"] += 1
            if config.linguagem_impressora:
                resumo["etiquetas_com_linguagem_nativa"] += 1
            else:
                alertas.append("Configuracao de etiqueta sem linguagem nativa de impressora.")
            if modelos_ativos:
                resumo["modelos_profissionais"] += len(modelos_ativos)
            else:
                alertas.append("Configuracao de etiqueta sem modelo profissional ativo.")
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
                        for modelo in modelos_ativos
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
    alertas_unicos = list(dict.fromkeys(alertas))
    if resumo["sem_impressora"]:
        status_prontidao = "Atencao"
        percentual = 75
    elif alertas_unicos:
        status_prontidao = "Pronta com ressalvas"
        percentual = 88
    else:
        status_prontidao = "Pronta"
        percentual = 100
    prontidao = {
        "contrato": "print_readiness_v1",
        "status": status_prontidao,
        "percentual": percentual,
        "alertas": alertas_unicos,
        "resumo": resumo,
        "proximo_passo": alertas_unicos[0] if alertas_unicos else "Impressoes preparadas para o app desktop local.",
    }
    return JsonResponse(
        {
            "status": "ok",
            "mensagem": "Configuracoes preparadas para sincronizacao com o app desktop local.",
            "prontidao": prontidao,
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
