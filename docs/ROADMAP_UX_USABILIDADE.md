# Roadmap UX 2.0 e Usabilidade

Criado em 11/09/2026. Estado: planejamento documental; implementação não iniciada.

A avaliação de referência fornecida para este planejamento considera que o sistema já possui identidade visual boa e consistente, sem necessidade de redesign completo. O objetivo é reduzir carga cognitiva e melhorar hierarquia de informação, navegação, responsividade e acessibilidade. O PDV já possui boa operação por teclado e deve ser preservado.

Qualquer mudança futura deve preservar regras de negócio, permissões, auditoria, atalhos e segurança operacional. Este documento não representa uma nova auditoria visual executada nesta etapa. As oportunidades abaixo serão verificadas no sistema antes da implementação, com registro de evidências e sem duplicar trabalho já concluído.

## Diagnóstico atual

Avaliação de referência, sem certificação formal de mercado:

- UX geral: nível médio-alto.
- PDV: nível alto.
- Identidade visual: boa e consistente.
- Principal desafio: crescimento da quantidade de funções e informação por tela.
- Maior oportunidade: organização, navegação e priorização de ações.

## Prioridade e dependências

A criação deste roadmap é apenas documental. A sequência do [roadmap principal](ROADMAP_EVOLUCAO_POS_PILOTO.md) permanece intacta. A trilha fiscal da devolução precede esta frente: cEnq do IPI (concluído estruturalmente no ciclo 92), variantes PIS/COFINS (em andamento), consolidação da matriz campo → origem → regra → XML, gerador específico e validação de paridade Focus/SEFAZ direta. Homologação externa permanece pendente enquanto faltarem credenciais reais.

Depois dos marcos fiscais internos vem a primeira etapa da DRE 2.0 com reconciliação de CMV; somente então começa UX 2.0, salvo correção crítica de usabilidade que afete operação ou segurança. P1, P2 e P3 expressam prioridade dentro desta frente futura e não antecipam sua execução.

Escopo desta etapa: criar este documento e adicionar referência curta no roadmap principal. Não há implementação de interface, alteração de templates, CSS, JS, views, forms, backend, migrations, regras, permissões, PDV ou atalhos. Comportamentos fiscal, financeiro, estoque, compras e marketplace permanecem sob suas trilhas próprias.

## P1 — Navegação, contexto e hierarquia

### 1. Estado ativo no menu lateral

- [ ] Destacar claramente a página atual no menu.
- [ ] Destacar também a seção pai correspondente.
- [ ] Garantir contraste visual suficiente.
- [ ] Não depender apenas de cor para indicar seleção.
- [ ] Preservar permissões atuais.

Critério de aceite:
O usuário deve identificar onde está no sistema sem precisar interpretar URL ou título da página.

### 2. Contexto real de empresa e filial

- [ ] Substituir qualquer rótulo fixo como "Loja principal" por contexto real.
- [ ] Exibir empresa/filial atual quando a tela estiver filtrada por filial.
- [ ] Exibir claramente "Todas as filiais" quando a visão for consolidada.
- [ ] Evitar qualquer indicação visual que possa induzir o operador a acreditar que está em outra filial.

Critério de aceite:
Nenhuma tela consolidada ou filtrada pode apresentar contexto conflitante de filial.

### 3. Reorganização da navegação financeira

- [ ] Reduzir excesso de ações no cabeçalho da tela Financeiro.
- [ ] Criar subnavegação clara entre:
  - Contas
  - Fluxo de caixa
  - Conciliação
  - Recebíveis
  - Resultado
- [ ] Mover funções administrativas menos frequentes para menu secundário ou área "Mais".
- [ ] Manter "Nova conta" como ação primária evidente.

Critério de aceite:
As funções mais usadas devem ficar visíveis sem competir visualmente com configurações e exportações.

### 4. Reorganização da navegação fiscal

- [ ] Separar visualmente operações fiscais comuns de configurações técnicas.
- [ ] Estruturar navegação conceitual como:
  - Documentos
  - Pendências
  - DF-e recebidos
  - Devoluções
  - Configuração
- [ ] Não remover detalhes técnicos.
- [ ] Colocar informações avançadas atrás de áreas expansíveis quando apropriado.

Critério de aceite:
Um usuário operacional deve conseguir trabalhar no fiscal sem precisar interpretar informações destinadas ao suporte técnico.

### 5. Sidebar mobile/tablet offcanvas

- [ ] Substituir o menu completo empilhado em telas pequenas por menu recolhível/offcanvas.
- [ ] Preservar navegação por teclado.
- [ ] Preservar permissões.
- [ ] Garantir acesso rápido ao conteúdo.
- [ ] Testar tablets utilizados em loja.

Critério de aceite:
Em viewport reduzido, o conteúdo principal deve aparecer antes do menu completo.

## P2 — Orientação do usuário

### 6. Próxima ação recomendada

Criar padrão visual reutilizável para processos longos.

Aplicar futuramente em:

- compras;
- entrada de mercadoria;
- inventário;
- devolução;
- fiscal;
- homologação;
- marketplace quando aplicável.

Exemplo conceitual:

NF-e recebida      ✓
Pedido encontrado  ✓
Conferência        !
Finalização        ○

Próxima ação:
"Registrar conferência física"

Tarefas:

- [ ] Definir componente visual padrão.
- [ ] Exibir etapa atual.
- [ ] Exibir etapas concluídas.
- [ ] Exibir bloqueios.
- [ ] Exibir próxima ação possível.
- [ ] Não permitir que o componente decida regra de negócio; ele apenas representa o estado fornecido pelo domínio.

Critério de aceite:
O usuário deve saber o próximo passo sem precisar ler toda a página.

### 7. Resultado financeiro / DRE em navegação por abas

Após a implementação da DRE 2.0:

- [ ] Reorganizar a tela de resultado.
- [ ] Evitar uma única página contendo todas as tabelas simultaneamente.
- [ ] Criar navegação entre:
  - DRE
  - CMV
  - Categorias
  - Centros de custo
  - Contas contábeis
  - Conciliação
  - Fiscal x financeiro
  - Integração contábil
- [ ] Preservar filtros de período e filial.
- [ ] Preservar exportações.
- [ ] Garantir links diretos/estado previsível quando possível.

Critério de aceite:
O usuário deve visualizar um grupo de análise por vez sem perder o contexto do período.

### 8. Navegação interna do cadastro de produto

- [ ] Criar índice/âncoras para as seções do cadastro.
- [ ] Considerar navegação para:
  - Identificação
  - Embalagens e códigos
  - Balança/PLU
  - Fornecedores
  - Preços e estoque
  - Venda e imagens
  - Nutrição
  - Fiscal
- [ ] Manter seções opcionais recolhíveis.
- [ ] Criar ação de salvar facilmente acessível em formulários extensos, se isso não conflitar com comportamento atual.

Critério de aceite:
Um usuário deve alcançar qualquer grupo do produto sem rolagem extensa manual.

### 9. Dashboard orientado a ação

- [ ] Manter indicadores atuais úteis.
- [ ] Incluir futuramente alertas acionáveis, como:
  - estoque crítico;
  - produtos próximos do vencimento;
  - contas vencidas;
  - recebíveis atrasados;
  - divergências de caixa;
  - documentos fiscais pendentes;
  - conciliações pendentes;
  - falhas operacionais relevantes.
- [ ] Permitir clique para abrir o detalhe correspondente.
- [ ] Evitar transformar o dashboard em uma tela excessivamente carregada.

Critério de aceite:
O dashboard deve responder principalmente à pergunta:
"O que precisa da minha atenção agora?"

## P3 — Refinamento

### 10. Busca global real

O escopo real da busca superior deverá ser conferido antes de qualquer mudança.

- [ ] Se continuar pesquisando somente produtos, rotular claramente como busca de produto/código.
- [ ] Futuramente estudar busca global por:
  - produto;
  - cliente;
  - fornecedor;
  - venda;
  - pedido;
  - documento fiscal;
  - cadastro.
- [ ] Respeitar permissões e empresa/filial.
- [ ] Não expor dados de outro tenant.

Critério de aceite:
O texto da interface deve representar exatamente o escopo real da busca.

### 11. Diálogos próprios

- [ ] Inventariar uso de `window.alert` e `window.confirm`.
- [ ] Criar padrão próprio apenas onde houver benefício real.
- [ ] Preservar confirmações de ações perigosas.
- [ ] Exibir claramente:
  - ação;
  - consequência;
  - opção segura;
  - opção destrutiva.
- [ ] Não reduzir proteções existentes.

### 12. Acessibilidade

Executar auditoria futura específica cobrindo:

- [ ] foco visível;
- [ ] ordem de Tab;
- [ ] focus trap em modais;
- [ ] restauração de foco;
- [ ] Escape para fechamento quando apropriado;
- [ ] aria-label;
- [ ] aria-live;
- [ ] mensagens de erro;
- [ ] contraste;
- [ ] tabelas;
- [ ] gráficos;
- [ ] navegação somente por teclado;
- [ ] leitores de tela.

Dar atenção especial ao PDV, que já possui boa base de teclado e ARIA.

### 13. Modularização de CSS e JavaScript

Apenas após estabilização funcional.

Concentração de arquivos indicada na avaliação de referência, a confirmar antes da implementação:
- `static/css/custom.css` concentra grande volume de estilos;
- `static/js/app.js` concentra grande volume de comportamento.

Estudar evolução gradual para módulos como:

CSS:
- base
- layout
- components
- forms
- tables
- pdv
- financeiro
- fiscal

JS:
- core
- forms
- pdv
- financeiro
- fiscal

Regras:

- [ ] não realizar refatoração Big Bang;
- [ ] preservar comportamento;
- [ ] criar testes de regressão antes;
- [ ] mover código por domínio gradualmente.

Critério de aceite:
A modularização não pode produzir alteração visual ou funcional involuntária.

## PDV

Na avaliação de referência, o PDV atual é considerado uma das áreas mais maduras de UX.

Preservar:

- tela dedicada sem sidebar;
- foco automático na busca de produto;
- uso intensivo de teclado;
- atalhos operacionais;
- carrinho central;
- total em destaque;
- pagamento dividido;
- troco;
- integração com balança;
- fluxo de supervisor;
- mensagens de erro;
- operação desktop.

Melhorias futuras no PDV devem ser incrementais.

Não fazer redesign amplo sem teste com operador real.

Criar futuramente testes práticos cronometrados:

- venda simples;
- venda com produto pesável;
- pagamento em dinheiro;
- pagamento eletrônico;
- pagamento dividido;
- CPF na nota;
- desconto com supervisor;
- cancelamento de item;
- estorno;
- abertura;
- fechamento de caixa;
- entrega.

Registrar:
- número de cliques;
- número de teclas;
- tempo;
- erros;
- pontos de hesitação.

## Validação futura em ambiente real

Criar checklist para piloto:

Perfis:

- [ ] Validar tarefas com operador de caixa.
- [ ] Validar tarefas com estoquista.
- [ ] Validar tarefas com comprador.
- [ ] Validar tarefas com financeiro.
- [ ] Validar tarefas com gerente.
- [ ] Validar tarefas com fiscal/contador quando aplicável.

Para cada tarefa, medir:

- [ ] Registrar tempo para concluir.
- [ ] Registrar quantidade de ações.
- [ ] Registrar erros cometidos.
- [ ] Registrar necessidade de ajuda.
- [ ] Registrar retornos para a tela anterior.
- [ ] Registrar dificuldade de localizar informação.
- [ ] Registrar comentários do usuário.

Não alterar regra de negócio com base apenas em preferência visual.

## Disciplina de implementação

Quando essa frente começar no futuro:

1. Trabalhar uma melhoria por ciclo.
2. Evitar grandes mudanças simultâneas.
3. Criar teste/regressão quando aplicável.
4. Comparar antes/depois.
5. Preservar atalhos e fluxo operacional.
6. Atualizar este roadmap ao final de cada ciclo.
7. Não marcar tarefa como concluída sem evidência visual/funcional correspondente.
8. Priorizar redução de erro e tempo operacional acima de efeito estético.
