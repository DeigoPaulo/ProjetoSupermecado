document.addEventListener("DOMContentLoaded", function () {
  function aplicarMascaras() {
    if (typeof window.jQuery === "undefined" || !window.jQuery.fn.mask) {
      window.setTimeout(aplicarMascaras, 100);
      return;
    }

    var $ = window.jQuery;
    var cpfCnpjBehavior = function (val) {
      return val.replace(/\D/g, "").length <= 11 ? "000.000.000-009" : "00.000.000/0000-00";
    };
    var cpfCnpjOptions = {
      onKeyPress: function (val, e, field, options) {
        field.mask(cpfCnpjBehavior.apply({}, arguments), options);
      },
    };

    $(".mask-cpf-cnpj, #id_cpf_cnpj, #cpf_cnpj, #id_cnpj, #cnpj").mask(cpfCnpjBehavior, cpfCnpjOptions);
    $(".mask-phone, #id_telefone, #telefone").mask("(00) 00000-0000");
    $(".mask-cep, #id_cep, #cep").mask("00000-000");
    $(".mask-money").mask("#.##0,00", { reverse: true });
    $(".mask-quantity").mask("#.##0,000", { reverse: true });
  }

  aplicarMascaras();

  function aplicarSelect2() {
    if (typeof window.jQuery === "undefined" || !window.jQuery.fn.select2) {
      window.setTimeout(aplicarSelect2, 100);
      return;
    }

    var $ = window.jQuery;
    $(".select2-field").each(function () {
      var $field = $(this);
      if ($field.data("select2")) return;
      $field.select2({
        width: "100%",
        placeholder: $field.data("placeholder") || "Selecione",
        allowClear: !$field.prop("required"),
        language: {
          noResults: function () { return "Nenhum resultado encontrado"; },
          searching: function () { return "Pesquisando..."; },
        },
      });
    });
  }

  aplicarSelect2();

  var labelsNativePrint = document.getElementById("labels-native-print");
  if (labelsNativePrint) {
    labelsNativePrint.addEventListener("click", function () {
      var feedback = document.getElementById("labels-print-feedback");
      var payloadElement = document.getElementById("labels-native-payload");
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printLabels;
      if (!bridge) {
        if (feedback) feedback.textContent = "Impressao direta disponivel somente no aplicativo desktop. Use a impressao pelo navegador neste computador.";
        return;
      }
      try {
        var payload = JSON.parse(payloadElement.textContent);
        labelsNativePrint.disabled = true;
        if (feedback) feedback.textContent = "Enviando etiquetas para a impressora...";
        Promise.resolve(bridge(payload)).then(function (resultado) {
          if (!resultado || resultado.status !== "ok") {
            throw new Error((resultado && resultado.mensagem) || "A impressora nao confirmou o lote.");
          }
          if (feedback) feedback.textContent = "Etiquetas enviadas para " + resultado.impressora + ".";
        }).catch(function (erro) {
          if (feedback) feedback.textContent = "Falha na impressao direta: " + erro.message;
        }).finally(function () {
          labelsNativePrint.disabled = false;
        });
      } catch (erro) {
        labelsNativePrint.disabled = false;
        if (feedback) feedback.textContent = "Nao foi possivel preparar o lote: " + erro.message;
      }
    });
  }

  function aplicarCamposMonetarios(root) {
    var escopo = root || document;
    var nomesMonetarios = /(^|_)(valor|preco|custo|desconto|taxa|frete|total)(_|$)/i;
    escopo.querySelectorAll("input[type='number']").forEach(function (input) {
      if (!nomesMonetarios.test(input.name || "") || input.closest(".money-input")) return;

      var wrapper = document.createElement("div");
      wrapper.className = "money-input money-input-admin";
      var prefix = document.createElement("span");
      prefix.textContent = "R$";
      prefix.setAttribute("aria-hidden", "true");
      input.parentNode.insertBefore(wrapper, input);
      wrapper.appendChild(prefix);
      wrapper.appendChild(input);
      input.classList.add("is-money-field");
      input.setAttribute("data-money-field", "true");
    });
  }

  aplicarCamposMonetarios(document);

  document.querySelectorAll("input[type='text']").forEach(function (input) {
    if (input.classList.contains("no-upper") || input.name.includes("email") || input.closest(".no-uppercase-fields")) return;
    input.addEventListener("input", function () {
      var start = this.selectionStart;
      var end = this.selectionEnd;
      this.value = this.value.toUpperCase();
      this.setSelectionRange(start, end);
    });
  });

  document.querySelectorAll(".form-confirm").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var msg = form.getAttribute("data-msg") || "Confirma esta operacao?";
      if (!window.confirm(msg)) event.preventDefault();
    });
  });

  if (document.body.classList.contains("pdv-mode")) {
    var buscaProduto = document.getElementById("id_busca");
    var descontoInput = document.getElementById("id_desconto");
    var recebidoInput = document.getElementById("id_valor_recebido");
    var finishForm = document.getElementById("pdv-finish-form");
    var finalizeButton = document.getElementById("pdv-finalize-button");
    var finishShortcut = document.getElementById("pdv-finish-shortcut");
    var paymentFeedback = document.getElementById("pdv-payment-feedback");
    var resumo = document.querySelector(".pdv-summary");
    var descontoDisplay = document.getElementById("pdv-desconto-display");
    var totalFinalDisplay = document.getElementById("pdv-total-final");
    var trocoDisplay = document.getElementById("pdv-troco-estimado");
    var paymentModal = document.getElementById("pdv-payment-modal");
    var openPaymentButton = document.getElementById("pdv-open-payment");
    var closePaymentButton = document.getElementById("pdv-close-payment");
    var confirmPaymentButton = document.getElementById("pdv-confirm-payment");
    var addPaymentButton = document.getElementById("pdv-add-payment");
    var paymentRows = document.getElementById("pdv-payment-rows");
    var paymentTemplate = document.getElementById("pdv-payment-row-template");
    var pagamentoLancado = document.getElementById("pdv-pagamento-lancado");
    var pagamentoRestante = document.getElementById("pdv-pagamento-restante");
    var modalTotal = document.getElementById("pdv-modal-total");
    var modalLancado = document.getElementById("pdv-modal-lancado");
    var modalRestante = document.getElementById("pdv-modal-restante");
    var modalTroco = document.getElementById("pdv-modal-troco");
    var electronicChoice = document.getElementById("pdv-electronic-choice");
    var pdvModals = document.querySelectorAll(".pdv-modal");
    var postSaleModal = document.getElementById("pdv-post-sale-modal");
    var postSalePrintButton = document.getElementById("pdv-print-last-sale");
    var postSaleCloseButton = document.getElementById("pdv-close-post-sale");

    if (buscaProduto) {
      buscaProduto.focus();
      buscaProduto.select();
    }

    function decimalFromInput(value) {
      if (!value) return 0;
      var raw = String(value).trim();
      var normalized = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
      var parsed = Number(normalized);
      return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatMoney(value) {
      return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    function totalPagamentosLancados() {
      if (!paymentRows) return 0;
      return Array.prototype.reduce.call(paymentRows.querySelectorAll("input[name='pagamento_valor']"), function (total, input) {
        return total + Math.max(decimalFromInput(input.value), 0);
      }, 0);
    }

    function totalFinalAtual() {
      if (!resumo) return 0;
      var subtotal = decimalFromInput(resumo.dataset.total);
      var desconto = Math.max(decimalFromInput(descontoInput && descontoInput.value), 0);
      return Math.max(subtotal - desconto, 0);
    }

    function atualizarResumoPdv() {
      if (!resumo) return;
      var subtotal = decimalFromInput(resumo.dataset.total);
      var desconto = Math.max(decimalFromInput(descontoInput && descontoInput.value), 0);
      var recebidoInformado = Math.max(decimalFromInput(recebidoInput && recebidoInput.value), 0);
      var recebidoPagamentos = totalPagamentosLancados();
      var recebido = Math.max(recebidoInformado, recebidoPagamentos);
      var totalFinal = Math.max(subtotal - desconto, 0);
      var restante = Math.max(totalFinal - recebidoPagamentos, 0);
      var troco = Math.max(recebido - totalFinal, 0);

      if (descontoDisplay) descontoDisplay.textContent = formatMoney(desconto);
      if (totalFinalDisplay) totalFinalDisplay.textContent = formatMoney(totalFinal);
      if (trocoDisplay) trocoDisplay.textContent = formatMoney(troco);
      if (pagamentoLancado) pagamentoLancado.textContent = formatMoney(recebidoPagamentos);
      if (pagamentoRestante) pagamentoRestante.textContent = formatMoney(restante);
      if (modalTotal) modalTotal.textContent = formatMoney(totalFinal);
      if (modalLancado) modalLancado.textContent = formatMoney(recebidoPagamentos);
      if (modalRestante) modalRestante.textContent = formatMoney(restante);
      if (modalTroco) modalTroco.textContent = formatMoney(Math.max(recebidoPagamentos - totalFinal, 0));
    }

    function abrirPagamentos() {
      if (!paymentModal) return;
      paymentModal.classList.add("is-open");
      paymentModal.setAttribute("aria-hidden", "false");
      atualizarResumoPdv();
      var firstSelect = paymentModal.querySelector("select");
      if (firstSelect) firstSelect.focus();
    }

    function informarPagamentoFeedback(texto) {
      if (paymentFeedback) paymentFeedback.textContent = texto || "";
    }

    function pagamentoCompleto() {
      return totalPagamentosLancados() + 0.005 >= totalFinalAtual();
    }

    function finalizarVendaPdv() {
      if (!finishForm) return;
      if (!pagamentoCompleto()) {
        informarPagamentoFeedback("Informe uma forma e complete o valor restante.");
        var primeiroSelect = paymentModal && paymentModal.querySelector("select");
        if (primeiroSelect) primeiroSelect.focus();
        return;
      }
      informarPagamentoFeedback("");
      finishForm.requestSubmit();
    }

    function selecionarFormaPagamento(atalho) {
      if (!paymentRows) return;
      if (atalho === "F3") {
        abrirEscolhaEletronica();
        return;
      }
      var termos = {
        F1: ["dinheiro"],
        F2: ["convenio", "convênio"],
        F3: ["credito", "crédito", "debito", "débito", "cartao", "cartão", "pos"],
        F4: ["troca", "outro", "vale"],
      }[atalho] || [];
      if (atalho === "F2") termos = ["pix"];
      if (atalho === "F4") termos = ["convenio", "convenio"];
      if (atalho === "F5") termos = ["troca", "outro", "vale"];
      if (atalho === "F2") termos = ["convenio", "convenio"];
      if (atalho === "F4") termos = ["troca", "outro", "vale"];
      var linhas = paymentRows.querySelectorAll(".pdv-payment-row");
      var linha = linhas[linhas.length - 1];
      if (linha && linha.querySelector("select").value) {
        adicionarLinhaPagamento();
        linhas = paymentRows.querySelectorAll(".pdv-payment-row");
        linha = linhas[linhas.length - 1];
      }
      var select = linha && linha.querySelector("select");
      var input = linha && linha.querySelector("input[name='pagamento_valor']");
      if (!select || !input) return;
      var opcao = Array.prototype.find.call(select.options, function (item) {
        var nome = item.textContent.trim().toLowerCase();
        return termos.some(function (termo) { return nome.includes(termo); });
      });
      if (!opcao) {
        informarPagamentoFeedback("Nenhuma forma correspondente ao " + atalho + " esta cadastrada.");
        select.focus();
        return;
      }
      select.value = opcao.value;
      input.value = Math.max(totalFinalAtual() - totalPagamentosLancados(), 0).toFixed(2);
      informarPagamentoFeedback("");
      atualizarResumoPdv();
      if (atalho === "F1") {
        input.focus();
        input.select();
      } else {
        select.focus();
      }
    }

    function abrirEscolhaEletronica() {
      if (!electronicChoice) return;
      electronicChoice.classList.add("is-open");
      electronicChoice.setAttribute("aria-hidden", "false");
      var firstButton = electronicChoice.querySelector("button");
      if (firstButton) firstButton.focus();
    }

    function fecharEscolhaEletronica() {
      if (!electronicChoice) return;
      electronicChoice.classList.remove("is-open");
      electronicChoice.setAttribute("aria-hidden", "true");
    }

    function selecionarPagamentoEletronico(tipo) {
      if (!paymentRows) return;
      var termosPorTipo = {
        credito: ["credito", "cartao de credito"],
        debito: ["debito", "cartao de debito"],
        pix: ["pix"],
      };
      var termos = termosPorTipo[tipo] || [];
      var linhas = paymentRows.querySelectorAll(".pdv-payment-row");
      var linha = linhas[linhas.length - 1];
      if (linha && linha.querySelector("select").value) {
        adicionarLinhaPagamento();
        linhas = paymentRows.querySelectorAll(".pdv-payment-row");
        linha = linhas[linhas.length - 1];
      }
      var select = linha && linha.querySelector("select");
      var input = linha && linha.querySelector("input[name='pagamento_valor']");
      if (!select || !input) return;
      var opcao = Array.prototype.find.call(select.options, function (item) {
        var nome = item.textContent.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        return termos.some(function (termo) { return nome.includes(termo); });
      });
      if (!opcao) {
        informarPagamentoFeedback("Forma eletronica nao cadastrada para " + tipo + ".");
        select.focus();
        return;
      }
      select.value = opcao.value;
      input.value = Math.max(totalFinalAtual() - totalPagamentosLancados(), 0).toFixed(2);
      fecharEscolhaEletronica();
      informarPagamentoFeedback("");
      atualizarResumoPdv();
      select.focus();
    }

    function fecharPagamentos() {
      if (!paymentModal) return;
      fecharEscolhaEletronica();
      paymentModal.classList.remove("is-open");
      paymentModal.setAttribute("aria-hidden", "true");
      if (openPaymentButton) openPaymentButton.focus();
    }

    function modalAberto() {
      return document.querySelector(".pdv-modal.is-open");
    }

    function abrirModalPdv(name) {
      var modal = document.getElementById("pdv-modal-" + name);
      if (!modal) return;
      fecharModalPdv();
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      var input = modal.querySelector("[data-pdv-modal-filter]");
      if (input) {
        input.value = "";
        filtrarModal(input);
        input.focus();
      }
    }

    function fecharModalPdv() {
      pdvModals.forEach(function (modal) {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
      });
    }

    function filtrarModal(input) {
      var modal = input.closest(".pdv-modal");
      if (!modal) return;
      var termo = input.value.trim().toLowerCase();
      modal.querySelectorAll(".pdv-modal-row").forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().includes(termo) ? "" : "none";
      });
    }

    function focarBuscaProduto() {
      if (!buscaProduto) return;
      fecharModalPdv();
      buscaProduto.focus();
      buscaProduto.select();
    }

    function fecharPosVenda() {
      if (!postSaleModal) return;
      postSaleModal.classList.remove("is-open");
      postSaleModal.setAttribute("aria-hidden", "true");
      focarBuscaProduto();
    }

    function imprimirUltimaVendaFallback(url) {
      if (!url) return;
      var frame = document.getElementById("pdv-print-frame");
      if (!frame) {
        frame = document.createElement("iframe");
        frame.id = "pdv-print-frame";
        frame.title = "Impressao do cupom";
        frame.setAttribute("aria-hidden", "true");
        frame.style.position = "fixed";
        frame.style.right = "0";
        frame.style.bottom = "0";
        frame.style.width = "0";
        frame.style.height = "0";
        frame.style.border = "0";
        frame.style.opacity = "0";
        document.body.appendChild(frame);
      }
      frame.src = url;
    }

    function imprimirUltimaVenda() {
      if (!postSaleModal) return;
      var url = postSaleModal.getAttribute("data-print-url");
      var desktopUrl = postSaleModal.getAttribute("data-desktop-print-url");
      var desktopBridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printSale;
      if (desktopBridge && desktopUrl && window.fetch) {
        window.fetch(desktopUrl, { credentials: "same-origin" })
          .then(function (response) { return response.json(); })
          .then(function (payload) { return desktopBridge(payload); })
          .catch(function () { imprimirUltimaVendaFallback(url); });
        return;
      }
      imprimirUltimaVendaFallback(url);
    }

    function adicionarLinhaPagamento() {
      if (!paymentRows || !paymentTemplate) return;
      paymentRows.appendChild(paymentTemplate.content.cloneNode(true));
      atualizarResumoPdv();
      var linhas = paymentRows.querySelectorAll(".pdv-payment-row");
      var novaLinha = linhas[linhas.length - 1];
      var select = novaLinha && novaLinha.querySelector("select");
      if (select) select.focus();
    }

    function removerLinhaPagamento(row) {
      if (!paymentRows || !row) return;
      var rows = paymentRows.querySelectorAll(".pdv-payment-row");
      if (rows.length > 1) {
        var proximaLinha = row.nextElementSibling || row.previousElementSibling;
        row.remove();
        if (proximaLinha) {
          var proximoCampo = proximaLinha.querySelector("select, input");
          if (proximoCampo) proximoCampo.focus();
        }
      } else {
        row.querySelector("select").value = "";
        row.querySelector("input").value = "";
        row.querySelector("select").focus();
      }
      atualizarResumoPdv();
    }

    if (descontoInput) descontoInput.addEventListener("input", atualizarResumoPdv);
    if (recebidoInput) recebidoInput.addEventListener("input", atualizarResumoPdv);
    if (openPaymentButton) openPaymentButton.addEventListener("click", abrirPagamentos);
    if (closePaymentButton) closePaymentButton.addEventListener("click", fecharPagamentos);
    if (confirmPaymentButton) confirmPaymentButton.addEventListener("click", finalizarVendaPdv);
    if (finalizeButton) finalizeButton.addEventListener("click", abrirPagamentos);
    if (finishShortcut) finishShortcut.addEventListener("click", abrirPagamentos);
    if (addPaymentButton) addPaymentButton.addEventListener("click", adicionarLinhaPagamento);
    if (postSalePrintButton) postSalePrintButton.addEventListener("click", imprimirUltimaVenda);
    if (postSaleCloseButton) postSaleCloseButton.addEventListener("click", fecharPosVenda);
    if (electronicChoice) {
      electronicChoice.addEventListener("click", function (event) {
        var button = event.target.closest("[data-pdv-electronic-payment]");
        if (button) selecionarPagamentoEletronico(button.getAttribute("data-pdv-electronic-payment"));
      });
    }
    if (postSaleModal) {
      postSaleModal.addEventListener("click", function (event) {
        if (event.target === postSaleModal) fecharPosVenda();
      });
      if (postSaleCloseButton) postSaleCloseButton.focus();
    }
    if (paymentModal) {
      paymentModal.addEventListener("click", function (event) {
        if (event.target === paymentModal) fecharPagamentos();
      });
    }
    document.querySelectorAll("[data-pdv-modal-open]").forEach(function (button) {
      button.addEventListener("click", function () {
        abrirModalPdv(button.getAttribute("data-pdv-modal-open"));
      });
    });
    document.querySelectorAll("[data-pdv-focus-search]").forEach(function (button) {
      button.addEventListener("click", focarBuscaProduto);
    });
    pdvModals.forEach(function (modal) {
      modal.addEventListener("click", function (event) {
        if (event.target === modal || event.target.closest("[data-pdv-modal-close]")) {
          fecharModalPdv();
          if (buscaProduto) buscaProduto.focus();
        }
        var produtoButton = event.target.closest("[data-pdv-copy-product]");
        if (produtoButton && buscaProduto) {
          buscaProduto.value = produtoButton.getAttribute("data-pdv-copy-product") || "";
          fecharModalPdv();
          buscaProduto.focus();
          buscaProduto.select();
        }
        var clientButton = event.target.closest("[data-pdv-select-client]");
        var clientSelect = document.getElementById("id_cliente");
        if (clientButton && clientSelect) {
          clientSelect.value = clientButton.getAttribute("data-pdv-select-client") || "";
          fecharModalPdv();
          clientSelect.focus();
        }
      });
      modal.addEventListener("input", function (event) {
        if (event.target.matches("[data-pdv-modal-filter]")) filtrarModal(event.target);
      });
    });
    if (paymentRows) {
      paymentRows.addEventListener("input", atualizarResumoPdv);
      paymentRows.addEventListener("change", atualizarResumoPdv);
      paymentRows.addEventListener("click", function (event) {
        var removeButton = event.target.closest(".pdv-remove-payment");
        if (!removeButton) return;
        removerLinhaPagamento(removeButton.closest(".pdv-payment-row"));
      });
    }
    var cartRows = Array.prototype.slice.call(document.querySelectorAll(".pdv-cart-row"));
    var clearCartLink = document.getElementById("pdv-clear-cart");

    function selecionarItemCarrinho(row, focus) {
      if (!row) return;
      cartRows.forEach(function (item) {
        var selected = item === row;
        item.classList.toggle("is-selected", selected);
        item.setAttribute("aria-selected", selected ? "true" : "false");
      });
      if (focus) row.focus();
    }

    cartRows.forEach(function (row) {
      row.addEventListener("click", function (event) {
        if (!event.target.closest("a, button")) selecionarItemCarrinho(row, false);
      });
      row.addEventListener("focus", function () { selecionarItemCarrinho(row, false); });
    });
    if (clearCartLink) {
      clearCartLink.addEventListener("click", function (event) {
        if (!window.confirm("Excluir todos os produtos desta venda?")) event.preventDefault();
      });
    }
    document.addEventListener("keydown", function (event) {
      var key = event.key;
      if (postSaleModal && postSaleModal.classList.contains("is-open")) {
        if (key === "F10") {
          event.preventDefault();
          imprimirUltimaVenda();
          return;
        }
        if (key === "Enter" || key === "Escape") {
          event.preventDefault();
          fecharPosVenda();
          return;
        }
      }
      if (key === "Escape") {
        if (paymentModal && paymentModal.classList.contains("is-open")) {
          event.preventDefault();
          if (electronicChoice && electronicChoice.classList.contains("is-open")) {
            fecharEscolhaEletronica();
            return;
          }
          fecharPagamentos();
          return;
        }
        if (modalAberto()) {
          event.preventDefault();
          fecharModalPdv();
          focarBuscaProduto();
        }
        return;
      }
      if (event.shiftKey && key.toLowerCase() === "m") {
        event.preventDefault();
        var menuLink = document.getElementById("pdv-menu-link");
        if (menuLink) window.location.href = menuLink.href;
        return;
      }
      if (paymentModal && paymentModal.classList.contains("is-open")) {
        if ((event.shiftKey && (key === "+" || key === "=")) || key === "Add") {
          event.preventDefault();
          adicionarLinhaPagamento();
          return;
        }
        if (key === "Delete" || key === "Del") {
          var linhaPagamentoAtiva = document.activeElement && document.activeElement.closest(".pdv-payment-row");
          if (linhaPagamentoAtiva) {
            event.preventDefault();
            removerLinhaPagamento(linhaPagamentoAtiva);
            return;
          }
        }
        if (electronicChoice && electronicChoice.classList.contains("is-open") && ["F1", "F2", "F3"].indexOf(key) !== -1) {
          event.preventDefault();
          if (key === "F1") selecionarPagamentoEletronico("credito");
          if (key === "F2") selecionarPagamentoEletronico("debito");
          if (key === "F3") selecionarPagamentoEletronico("pix");
          return;
        }
        if (["F1", "F2", "F3", "F4"].indexOf(key) !== -1) {
          event.preventDefault();
          selecionarFormaPagamento(key);
          return;
        }
        if (key === "Enter") {
          event.preventDefault();
          finalizarVendaPdv();
          return;
        }
      }
      if ((key === "Delete" || key === "Del") && cartRows.length) {
        event.preventDefault();
        if (event.ctrlKey) {
          if (clearCartLink && window.confirm("Excluir todos os produtos desta venda?")) window.location.href = clearCartLink.href;
          return;
        }
        var selectedCartRow = document.querySelector(".pdv-cart-row.is-selected") || cartRows[cartRows.length - 1];
        if (selectedCartRow && selectedCartRow.dataset.removeUrl) window.location.href = selectedCartRow.dataset.removeUrl;
        return;
      }
      if ((key === "ArrowUp" || key === "ArrowDown") && cartRows.length && document.activeElement && document.activeElement.classList.contains("pdv-cart-row")) {
        event.preventDefault();
        var currentIndex = cartRows.indexOf(document.activeElement);
        var nextIndex = key === "ArrowUp" ? Math.max(0, currentIndex - 1) : Math.min(cartRows.length - 1, currentIndex + 1);
        selecionarItemCarrinho(cartRows[nextIndex], true);
        return;
      }
      if (!key || !key.startsWith("F")) return;
      if (["F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"].indexOf(key) === -1) return;
      event.preventDefault();
      if (key === "F2") focarBuscaProduto();
      if (key === "F3") abrirModalPdv("price");
      if (key === "F4") abrirModalPdv("clients");
      if (key === "F5") abrirModalPdv("products");
      if (key === "F6") abrirModalPdv("refunds");
      if (key === "F7") {
        var davButton = document.getElementById("pdv-dav-shortcut");
        if (davButton && !davButton.disabled) davButton.click();
      }
      if (key === "F8") abrirModalPdv("boxes");
      if (key === "F9") {
        if (finishShortcut && !finishShortcut.disabled) abrirPagamentos();
      }
    });
    if (finishForm) {
      finishForm.addEventListener("submit", function (event) {
        if (!pagamentoCompleto()) {
          event.preventDefault();
          abrirPagamentos();
          informarPagamentoFeedback("Escolha a forma de pagamento antes de finalizar.");
        }
      });
    }
    document.querySelectorAll(".pdv-mode .content > .messages .message").forEach(function (message) {
      window.setTimeout(function () { message.remove(); }, message.classList.contains("error") ? 3800 : 1800);
    });
    atualizarResumoPdv();
  }
});
