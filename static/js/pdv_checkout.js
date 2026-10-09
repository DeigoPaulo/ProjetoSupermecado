(function () {
  "use strict";

  var shell = document.getElementById("pdv-checkout");
  var form = document.getElementById("pdv-finish-form");
  var rows = document.getElementById("pdv-payment-rows");
  var template = document.getElementById("pdv-payment-row-template");
  if (!shell || !form || !rows || !template) return;

  var states = ["CPF_ESCOLHA", "DOCUMENTO_CAPTURA", "FORMA_PAGAMENTO", "CAIXA_FECHADO", "FORMAS_INDISPONIVEIS", "DINHEIRO", "ELETRONICO_INDISPONIVEL", "OUTROS", "CREDIARIO", "OUTRO_VALOR", "PROCESSANDO", "CONCLUIDO"];
  var state = "CPF_ESCOLHA";
  var documentType = "NAO";
  var previousFocus = null;
  var inFlight = false;
  var requestSnapshot = null;
  var automaticPrintRequested = false;
  var currentMethod = null;
  var totalCents = 0;
  var payments = [];
  var methods = Array.prototype.map.call(rows.querySelector("select[name='pagamento_forma']").options, function (option) {
    return { id: option.value, type: (option.dataset.paymentType || "").toUpperCase(), name: option.textContent.trim() };
  }).filter(function (method) { return method.id; });
  var electronic = ["PIX", "CARTAO", "DEBITO", "CREDITO", "VALE_ALIMENTACAO", "VALE_REFEICAO"];
  var credit = ["CREDIARIO", "FIADO", "PRAZO"];
  var cashInput = document.getElementById("pdv-checkout-cash");
  var otherInput = document.getElementById("pdv-checkout-other-value");
  var documentInput = document.getElementById("pdv-checkout-document-input");
  var documentManual = document.getElementById("pdv-checkout-manual-document");
  var captureStatus = document.getElementById("pdv-checkout-capture-status");
  var captureButton = document.getElementById("pdv-checkout-capture");
  var manualButton = document.getElementById("pdv-checkout-manual-button");
  var captureSequence = 0;
  var capturePending = false;
  var capabilityPromise = null;
  var choiceTimer = null;
  var choiceBurst = 0;
  var lastChoiceKeyAt = 0;
  var originalDocument = document.getElementById("id_documento_consumidor");
  var originalDocumentType = document.getElementById("id_documento_consumidor_tipo");
  var client = document.getElementById("pdv-checkout-client");
  var originalClient = form.querySelector("select[name='cliente']");
  var dueDate = document.getElementById("pdv-checkout-due-date");
  var originalDueDate = form.querySelector("input[name='vencimento_financeiro']");
  var globalError = document.getElementById("pdv-checkout-error");
  var retryButton = document.getElementById("pdv-checkout-retry");

  if (originalClient) {
    client.innerHTML = originalClient.innerHTML;
    client.value = originalClient.value;
  }
  if (originalDueDate) dueDate.value = originalDueDate.value;

  function money(cents) {
    return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function parseMoney(value) {
    var raw = String(value || "").trim().replace(/\s|R\$/g, "");
    if (!raw || !/^[0-9.,]+$/.test(raw)) return null;
    var normalized = raw.indexOf(",") !== -1
      ? raw.replace(/\./g, "").replace(",", ".")
      : /^\d{1,3}(?:\.\d{3})+$/.test(raw) ? raw.replace(/\./g, "") : raw;
    if ((raw.match(/,/g) || []).length > 1 || !/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
    var cents = Math.round(Number(normalized) * 100);
    return Number.isSafeInteger(cents) ? cents : null;
  }

  function paidCents() {
    return payments.reduce(function (sum, item) { return sum + item.cents; }, 0);
  }

  function remainingCents() {
    return Math.max(totalCents - paidCents(), 0);
  }

  function error(id, message) {
    var target = document.getElementById(id);
    if (target) target.textContent = message || "";
  }

  function renderSummary() {
    shell.querySelectorAll("[data-checkout-total]").forEach(function (node) { node.textContent = money(totalCents); });
    shell.querySelectorAll("[data-checkout-paid]").forEach(function (node) { node.textContent = money(Math.min(paidCents(), totalCents)); });
    shell.querySelectorAll("[data-checkout-due]").forEach(function (node) { node.textContent = money(remainingCents()); });
    var summary = document.getElementById("pdv-checkout-summary");
    summary.hidden = ["CPF_ESCOLHA", "DOCUMENTO_CAPTURA", "CAIXA_FECHADO", "FORMAS_INDISPONIVEIS", "CONCLUIDO"].indexOf(state) !== -1;
    document.getElementById("pdv-checkout-method-title").textContent = payments.length
      ? "Como deseja pagar o restante?" : "Como deseja pagar?";
  }

  function transition(next) {
    if (states.indexOf(next) === -1) return;
    if (choiceTimer) clearTimeout(choiceTimer);
    choiceTimer = null;
    choiceBurst = 0;
    state = next;
    shell.querySelector(".pdv-checkout-close").hidden = next === "PROCESSANDO" || next === "CONCLUIDO";
    document.getElementById("pdv-checkout-title").textContent = next === "CONCLUIDO" ? "Caixa livre" : "Finalizar venda";
    shell.querySelectorAll("[data-checkout-panel]").forEach(function (panel) {
      panel.hidden = panel.dataset.checkoutPanel !== next;
    });
    globalError.textContent = "";
    renderSummary();
    var focus = {
      CPF_ESCOLHA: "[data-checkout-document='NAO']",
      DOCUMENTO_CAPTURA: "#pdv-checkout-document-input",
      FORMA_PAGAMENTO: "#pdv-checkout-methods button",
      CAIXA_FECHADO: "#pdv-checkout-closed-no",
      FORMAS_INDISPONIVEIS: "#pdv-checkout-no-methods-close",
      DINHEIRO: "#pdv-checkout-cash",
      ELETRONICO_INDISPONIVEL: "[data-checkout-methods-back]",
      OUTROS: "#pdv-checkout-other-methods button",
      CREDIARIO: "#pdv-checkout-client",
      OUTRO_VALOR: "#pdv-checkout-other-value",
      PROCESSANDO: ".pdv-checkout-dialog",
      CONCLUIDO: "#pdv-checkout-new-sale"
    }[next];
    var target = focus && shell.querySelector(focus);
    if (target && !target.hidden && !target.closest("[hidden]")) target.focus();
    if (next === "DINHEIRO") cashInput.select();
    if (next === "OUTRO_VALOR") otherInput.select();
  }

  function chooseDocument(type) {
    captureSequence += 1;
    capturePending = false;
    documentType = type;
    var radio = form.querySelector('input[name="cpf_na_nota"][value="' + type + '"]');
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (type === "NAO") {
      if (originalDocument) originalDocument.value = "";
      if (originalDocumentType) originalDocumentType.value = "NAO_IDENTIFICADO";
      transition("FORMA_PAGAMENTO");
      return;
    }
    document.getElementById("pdv-checkout-document-title").textContent = type + " na nota";
    documentInput.inputMode = type === "CPF" ? "numeric" : "text";
    documentInput.value = originalDocument ? originalDocument.value : "";
    error("pdv-checkout-document-error", "");
    transition("DOCUMENTO_CAPTURA");
    if (window.SupermercadoDesktop && window.SupermercadoDesktop.tefCapabilities && window.SupermercadoDesktop.captureConsumerDocument) {
      documentManual.hidden = true;
      captureStatus.hidden = false;
      captureStatus.textContent = "Verificando pinpad...";
      manualButton.hidden = false;
      manualButton.focus();
      var sequence = captureSequence;
      checkDocumentCapability().then(function (available) {
        if (sequence !== captureSequence || state !== "DOCUMENTO_CAPTURA") return;
        if (available) captureDocument();
        else showManualDocument();
      });
    } else showManualDocument();
  }

  function checkDocumentCapability() {
    if (!capabilityPromise) {
      var desktop = window.SupermercadoDesktop;
      capabilityPromise = desktop && desktop.tefCapabilities && desktop.captureConsumerDocument
        ? Promise.resolve().then(function () { return desktop.tefCapabilities(); }).then(function (result) {
          return !!(result && result.status === "ok" && result.captura_documento_consumidor === true);
        }).catch(function () { return false; })
        : Promise.resolve(false);
    }
    return capabilityPromise;
  }

  function showManualDocument(message) {
    documentManual.hidden = false;
    captureStatus.hidden = !message;
    captureStatus.textContent = message || "";
    manualButton.hidden = true;
    captureButton.hidden = true;
    documentInput.focus();
    documentInput.select();
  }

  function validCpf(value) {
    var digits = value.replace(/\D/g, "");
    if (digits.length !== 11 || /^(\d)\1{10}$/.test(digits)) return false;
    for (var length = 9; length <= 10; length += 1) {
      var sum = 0;
      for (var i = 0; i < length; i += 1) sum += Number(digits[i]) * (length + 1 - i);
      var digit = (sum * 10) % 11;
      if (Number(digits[length]) !== (digit === 10 ? 0 : digit)) return false;
    }
    return true;
  }

  function validCnpj(value) {
    var digits = value.trim().toUpperCase().replace(/[.\/-]/g, "");
    if (!/^[A-Z0-9]{12}[0-9]{2}$/.test(digits)) return false;
    function digit(base) {
      var weight = 2;
      var sum = 0;
      for (var i = base.length - 1; i >= 0; i -= 1) {
        sum += (base.charCodeAt(i) - 48) * weight;
        weight = weight === 9 ? 2 : weight + 1;
      }
      var rest = sum % 11;
      return rest < 2 ? "0" : String(11 - rest);
    }
    var first = digit(digits.slice(0, 12));
    return digits.slice(-2) === first + digit(digits.slice(0, 12) + first);
  }

  function confirmDocument() {
    var valid = documentType === "CPF" ? validCpf(documentInput.value) : validCnpj(documentInput.value);
    if (!valid) {
      error("pdv-checkout-document-error", "Informe um " + documentType + " válido.");
      documentInput.focus();
      documentInput.select();
      return;
    }
    error("pdv-checkout-document-error", "");
    if (originalDocument) originalDocument.value = documentInput.value.trim();
    if (originalDocumentType) originalDocumentType.value = documentType;
    transition("FORMA_PAGAMENTO");
  }

  function makeMethodButton(method, container) {
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = method.name;
    button.addEventListener("click", function () { chooseMethod(method); });
    container.appendChild(button);
  }

  function renderMethods() {
    var main = document.getElementById("pdv-checkout-methods");
    var other = document.getElementById("pdv-checkout-other-methods");
    main.replaceChildren();
    other.replaceChildren();
    var cash = methods.find(function (item) { return item.type === "DINHEIRO"; });
    if (cash) makeMethodButton({ id: cash.id, type: cash.type, name: "Dinheiro" }, main);
    [{ type: "DEBITO", name: "Débito" }, { type: "CREDITO", name: "Crédito" }, { type: "PIX", name: "PIX" }].forEach(function (display) {
      var configured = methods.find(function (item) { return item.type === display.type; });
      makeMethodButton({ id: configured ? configured.id : "", type: display.type, name: display.name }, main);
    });
    methods.filter(function (method) {
      return ["DINHEIRO", "DEBITO", "CREDITO", "PIX"].indexOf(method.type) === -1;
    }).forEach(function (method) { makeMethodButton(method, other); });
    if (other.children.length) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = "Outros";
      button.addEventListener("click", function () { transition("OUTROS"); });
      main.appendChild(button);
    }
  }

  function chooseMethod(method) {
    currentMethod = method;
    if (electronic.indexOf(method.type) !== -1) {
      transition("ELETRONICO_INDISPONIVEL");
    } else if (method.type === "DINHEIRO") {
      cashInput.value = "";
      error("pdv-checkout-cash-error", "");
      transition("DINHEIRO");
    } else if (credit.indexOf(method.type) !== -1) {
      transition("CREDIARIO");
    } else {
      otherInput.value = "";
      document.getElementById("pdv-checkout-other-title").textContent = method.name;
      transition("OUTRO_VALOR");
    }
  }

  function syncRows() {
    rows.replaceChildren();
    payments.forEach(function (payment) {
      var row = template.content.firstElementChild.cloneNode(true);
      row.querySelector("select[name='pagamento_forma']").value = payment.method.id;
      row.querySelector("input[name='pagamento_valor']").value = (payment.cents / 100).toFixed(2);
      rows.appendChild(row);
    });
    if (!payments.length) rows.appendChild(template.content.firstElementChild.cloneNode(true));
  }

  function addPayment(method, cents) {
    payments.push({ method: method, cents: cents });
    syncRows();
    if (remainingCents() > 0) {
      transition("FORMA_PAGAMENTO");
    } else {
      submitSale();
    }
  }

  function updateChange() {
    var entered = parseMoney(cashInput.value);
    document.getElementById("pdv-checkout-change").textContent = money(Math.max((entered || 0) - remainingCents(), 0));
  }

  function confirmCash() {
    if (inFlight) return;
    var cents = parseMoney(cashInput.value);
    if (cents === null || cents <= 0) {
      error("pdv-checkout-cash-error", "Informe um valor válido maior que zero.");
      cashInput.focus();
      return;
    }
    if (payments.some(function (payment) { return payment.method.type === "DINHEIRO"; }) && cents > remainingCents()) {
      error("pdv-checkout-cash-error", "Somente uma parcela em dinheiro pode gerar troco.");
      return;
    }
    error("pdv-checkout-cash-error", "");
    cashInput.value = money(cents);
    addPayment(currentMethod, cents);
  }

  function confirmCredit() {
    if (!client.value || !dueDate.value) {
      error("pdv-checkout-credit-error", "Selecione o cliente e informe o vencimento.");
      return;
    }
    error("pdv-checkout-credit-error", "");
    if (originalClient) originalClient.value = client.value;
    if (originalDueDate) originalDueDate.value = dueDate.value;
    addPayment(currentMethod, remainingCents());
  }

  function confirmOther() {
    var cents = parseMoney(otherInput.value);
    if (cents === null || cents <= 0 || cents > remainingCents()) {
      error("pdv-checkout-other-error", "Informe um valor maior que zero e não superior ao restante.");
      otherInput.focus();
      return;
    }
    error("pdv-checkout-other-error", "");
    addPayment(currentMethod, cents);
  }

  function responseMessage(page) {
    var field = page.querySelector(".message.error, .errorlist, .messages .message");
    return field ? field.textContent.trim() : "Não foi possível confirmar a venda. Confira os dados e tente novamente.";
  }

  function requestAutomaticPrint() {
    if (state !== "CONCLUIDO" || automaticPrintRequested || !window.SupermercadoDesktop || !window.SupermercadoDesktop.printSale || !window.pdvPrintSale) return;
    automaticPrintRequested = true;
    var receipt = document.getElementById("pdv-checkout-receipt");
    window.pdvPrintSale(receipt.href, receipt.dataset.desktopPrintUrl, { somenteAutomatico: true });
  }

  function sendSnapshot() {
    if (inFlight || !requestSnapshot) return;
    inFlight = true;
    retryButton.hidden = true;
    transition("PROCESSANDO");
    fetch(form.getAttribute("action") || window.location.pathname, {
      method: "POST", body: requestSnapshot, credentials: "same-origin"
    }).then(function (response) {
      return response.text().then(function (html) { return { response: response, html: html }; });
    }).then(function (result) {
      var page = new DOMParser().parseFromString(result.html, "text/html");
      var completed = page.getElementById("pdv-post-sale-modal");
      if (completed && result.response.ok) {
        document.getElementById("pdv-checkout-sale-id").textContent = completed.dataset.saleId ? "Venda #" + completed.dataset.saleId : "";
        var change = Math.max(paidCents() - totalCents, 0);
        document.getElementById("pdv-checkout-finished-change").hidden = change === 0;
        document.getElementById("pdv-checkout-finished-change-value").textContent = money(change);
        var receipt = document.getElementById("pdv-checkout-receipt");
        receipt.href = completed.dataset.printUrl || "#";
        receipt.dataset.desktopPrintUrl = completed.dataset.desktopPrintUrl || "";
        var drawerAction = page.getElementById("pdv-cash-drawer-action");
        if (drawerAction && window.pdvRunPendingCashDrawer) {
          var action = document.createElement("script");
          action.type = "application/json";
          action.id = "pdv-cash-drawer-action";
          action.textContent = drawerAction.textContent;
          document.body.appendChild(action);
          window.pdvRunPendingCashDrawer(0);
        }
        transition("CONCLUIDO");
        requestAutomaticPrint();
        return;
      }
      if (!result.response.ok || !page.getElementById("pdv-finish-form")) {
        globalError.textContent = "Verificando venda: resposta inesperada. Tente novamente com a mesma chave.";
        retryButton.hidden = false;
        return;
      }
      requestSnapshot = null;
      payments = [];
      syncRows();
      transition("FORMA_PAGAMENTO");
      globalError.textContent = responseMessage(page);
    }).catch(function () {
      globalError.textContent = "Sem resposta do servidor. Verifique a venda usando a mesma chave antes de continuar.";
      retryButton.hidden = false;
    }).finally(function () { inFlight = false; });
  }

  function submitSale() {
    if (inFlight || requestSnapshot) return;
    if (!form.querySelector('input[name="checkout_idempotency_key"]').value) {
      globalError.textContent = "Atualize o PDV para iniciar uma nova venda.";
      transition("FORMA_PAGAMENTO");
      return;
    }
    requestSnapshot = new FormData(form);
    sendSnapshot();
  }

  function close() {
    if (state === "PROCESSANDO" || state === "CONCLUIDO") return;
    captureSequence += 1;
    capturePending = false;
    if (choiceTimer) clearTimeout(choiceTimer);
    choiceTimer = null;
    choiceBurst = 0;
    payments = [];
    requestSnapshot = null;
    automaticPrintRequested = false;
    syncRows();
    shell.hidden = true;
    shell.setAttribute("aria-hidden", "true");
    if (window.pdvRestoreFocus) window.pdvRestoreFocus(true);
    else if (previousFocus) previousFocus.focus();
  }

  function back() {
    if (["CPF_ESCOLHA", "CAIXA_FECHADO", "FORMAS_INDISPONIVEIS"].indexOf(state) !== -1) close();
    else if (state === "DOCUMENTO_CAPTURA") { captureSequence += 1; capturePending = false; transition("CPF_ESCOLHA"); }
    else if (state === "FORMA_PAGAMENTO") transition(payments.length ? "CPF_ESCOLHA" : (documentType === "NAO" ? "CPF_ESCOLHA" : "DOCUMENTO_CAPTURA"));
    else if (["DINHEIRO", "ELETRONICO_INDISPONIVEL", "OUTROS", "CREDIARIO", "OUTRO_VALOR"].indexOf(state) !== -1) transition("FORMA_PAGAMENTO");
  }

  function open() {
    if (!shell.hidden || inFlight) return;
    if (!form.querySelector('input[name="caixa"]')) {
      previousFocus = document.activeElement;
      shell.hidden = false;
      shell.setAttribute("aria-hidden", "false");
      transition("CAIXA_FECHADO");
      return;
    }
    var rawTotal = document.querySelector(".pdv-summary");
    var subtotal = parseMoney(rawTotal && rawTotal.dataset.total);
    var discount = parseMoney(form.querySelector('input[name="desconto"]') && form.querySelector('input[name="desconto"]').value) || 0;
    var discountError = document.getElementById("pdv-checkout-discount-error");
    discountError.textContent = "";
    if (subtotal !== null && discount > subtotal) {
      if (window.pdvOpenDiscount) window.pdvOpenDiscount();
      discountError.textContent = "O desconto não pode ser maior que o total da venda.";
      return;
    }
    if (discount > 0) {
      var supervisor = form.querySelector('input[name="supervisor_usuario"]');
      var password = form.querySelector('input[name="supervisor_senha"]');
      if (!supervisor || !supervisor.value.trim() || !password || !password.value) {
        if (window.pdvOpenDiscount) window.pdvOpenDiscount(true);
        discountError.textContent = "Informe usuário e senha do supervisor para autorizar o desconto.";
        return;
      }
    }
    totalCents = Math.max((subtotal || 0) - discount, 0);
    if (!totalCents) return;
    var discountInput = form.querySelector('input[name="desconto"]');
    if (discountInput) discountInput.disabled = false;
    if (originalClient) {
      client.innerHTML = originalClient.innerHTML;
      client.value = originalClient.value;
    }
    if (originalDueDate) dueDate.value = originalDueDate.value;
    previousFocus = document.activeElement;
    payments = [];
    requestSnapshot = null;
    syncRows();
    renderMethods();
    shell.hidden = false;
    shell.setAttribute("aria-hidden", "false");
    transition(!methods.length ? "FORMAS_INDISPONIVEIS" : "CPF_ESCOLHA");
  }

  function captureDocument() {
    if (capturePending || state !== "DOCUMENTO_CAPTURA") return;
    var sequence = captureSequence;
    checkDocumentCapability().then(function (available) {
      if (sequence !== captureSequence || state !== "DOCUMENTO_CAPTURA") return;
      if (!available) { showManualDocument(); return; }
      capturePending = true;
      documentManual.hidden = true;
      captureStatus.hidden = false;
      captureStatus.textContent = "Aguardando identificação no pinpad...";
      manualButton.hidden = false;
      captureButton.hidden = true;
      manualButton.focus();
      return Promise.resolve().then(function () {
        return window.SupermercadoDesktop.captureConsumerDocument({ tipo: documentType });
      }).then(function (result) {
        if (sequence !== captureSequence || state !== "DOCUMENTO_CAPTURA") return;
        if (result && result.status === "cancelado") { transition("CPF_ESCOLHA"); return; }
        if (result && result.status === "ok" && (!result.tipo || result.tipo === documentType)) {
          documentInput.value = result.documento || "";
          if (documentType === "CPF" ? validCpf(documentInput.value) : validCnpj(documentInput.value)) {
            confirmDocument();
            return;
          }
          error("pdv-checkout-document-error", "Documento inválido. Confira ou digite manualmente.");
        }
        captureStatus.textContent = "Não foi possível capturar pelo pinpad.";
        captureButton.hidden = false;
        captureButton.focus();
      }).catch(function () {
        if (sequence !== captureSequence || state !== "DOCUMENTO_CAPTURA") return;
        captureStatus.textContent = "Não foi possível capturar pelo pinpad.";
        captureButton.hidden = false;
        captureButton.focus();
      }).finally(function () { if (sequence === captureSequence) capturePending = false; });
    });
  }

  document.querySelectorAll("[data-checkout-document]").forEach(function (button) {
    button.addEventListener("click", function () { chooseDocument(button.dataset.checkoutDocument); });
  });
  shell.querySelector("[data-checkout-back]").addEventListener("click", back);
  document.getElementById("pdv-checkout-open-cash").addEventListener("click", function () {
    close();
    var button = document.querySelector('[data-pdv-modal-open="open-cash"]');
    if (button) button.click();
  });
  document.getElementById("pdv-checkout-closed-no").addEventListener("click", close);
  document.getElementById("pdv-checkout-no-methods-close").addEventListener("click", close);
  shell.querySelector("[data-checkout-methods-back]").addEventListener("click", function () { transition("FORMA_PAGAMENTO"); });
  document.getElementById("pdv-checkout-document-next").addEventListener("click", confirmDocument);
  document.getElementById("pdv-checkout-cash-confirm").addEventListener("click", confirmCash);
  document.getElementById("pdv-checkout-credit-confirm").addEventListener("click", confirmCredit);
  document.getElementById("pdv-checkout-other-confirm").addEventListener("click", confirmOther);
  document.getElementById("pdv-checkout-new-sale").addEventListener("click", function () { window.location.assign(window.location.pathname); });
  document.getElementById("pdv-checkout-receipt").addEventListener("click", function (event) {
    if (!window.pdvPrintSale) return;
    event.preventDefault();
    window.pdvPrintSale(event.currentTarget.href, event.currentTarget.dataset.desktopPrintUrl);
  });
  retryButton.addEventListener("click", sendSnapshot);
  cashInput.addEventListener("input", function () { error("pdv-checkout-cash-error", ""); updateChange(); });
  otherInput.addEventListener("input", function () { error("pdv-checkout-other-error", ""); });
  documentInput.addEventListener("input", function () { error("pdv-checkout-document-error", ""); });
  captureButton.addEventListener("click", captureDocument);
  manualButton.addEventListener("click", function () { captureSequence += 1; capturePending = false; showManualDocument(); });
  document.getElementById("pdv-checkout-document-back").addEventListener("click", back);
  document.addEventListener("supermercado:desktop-ready", requestAutomaticPrint);
  document.addEventListener("supermercado:desktop-ready", function () { capabilityPromise = null; });

  document.addEventListener("keydown", function (event) {
    if (shell.hidden) return;
    var key = event.key;
    if (key === "Tab") {
      var activePanel = shell.querySelector('[data-checkout-panel="' + state + '"]');
      var focusable = Array.prototype.filter.call(shell.querySelectorAll("button, input, select, a[href]"), function (node) {
        return !node.disabled && !node.hidden && (activePanel.contains(node) || node.closest(".pdv-checkout-header")) && node.offsetParent !== null;
      });
      if (!focusable.length) { event.preventDefault(); event.stopImmediatePropagation(); return; }
      var index = focusable.indexOf(document.activeElement);
      if (index === -1 || (event.shiftKey && index === 0) || (!event.shiftKey && index === focusable.length - 1)) {
        event.preventDefault();
        focusable[event.shiftKey ? focusable.length - 1 : 0].focus();
      }
      event.stopImmediatePropagation();
      return;
    }
    if (key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); back(); return; }
    if (key === "F9") { event.preventDefault(); event.stopImmediatePropagation(); return; }
    if (["CPF_ESCOLHA", "CAIXA_FECHADO", "FORMA_PAGAMENTO", "OUTROS"].indexOf(state) !== -1 &&
        key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
      var now = Date.now();
      choiceBurst = now - lastChoiceKeyAt > 250 ? 1 : choiceBurst + 1;
      lastChoiceKeyAt = now;
      if (choiceTimer) clearTimeout(choiceTimer);
      choiceTimer = null;
      var selectedState = state;
      if (choiceBurst === 1 && ((state === "CPF_ESCOLHA" && ["1", "2", "3"].indexOf(key) !== -1) ||
          (state === "CAIXA_FECHADO" && ["1", "2", "s", "S", "n", "N"].indexOf(key) !== -1))) {
        choiceTimer = setTimeout(function () {
          choiceTimer = null;
          if (state !== selectedState || choiceBurst !== 1) return;
          choiceBurst = 0;
          if (selectedState === "CPF_ESCOLHA") chooseDocument(["NAO", "CPF", "CNPJ"][Number(key) - 1]);
          else document.getElementById(["1", "s", "S"].indexOf(key) !== -1 ? "pdv-checkout-open-cash" : "pdv-checkout-closed-no").click();
        }, 220);
      }
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (key === "Enter" && choiceBurst > 1 && Date.now() - lastChoiceKeyAt < 350) {
      choiceBurst = 0;
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (key === "Enter" && choiceTimer) {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(key) !== -1 &&
        document.activeElement && document.activeElement.closest(".pdv-checkout-choices")) {
      var choices = Array.prototype.filter.call(document.activeElement.closest(".pdv-checkout-choices").querySelectorAll("button"), function (button) {
        return !button.hidden && !button.disabled;
      });
      var current = choices.indexOf(document.activeElement);
      if (current !== -1 && choices.length > 1) {
        event.preventDefault(); event.stopImmediatePropagation();
        var step = key === "ArrowLeft" || key === "ArrowUp" ? -1 : 1;
        choices[(current + step + choices.length) % choices.length].focus();
        return;
      }
    }
    if (key === "Enter") {
      if (state === "DOCUMENTO_CAPTURA" && !documentManual.hidden && document.activeElement === documentInput) { event.preventDefault(); confirmDocument(); }
      else if (state === "DINHEIRO") { event.preventDefault(); confirmCash(); }
      else if (state === "CREDIARIO") { event.preventDefault(); confirmCredit(); }
      else if (state === "OUTRO_VALOR") { event.preventDefault(); confirmOther(); }
      else if (state === "CONCLUIDO" && document.activeElement !== document.getElementById("pdv-checkout-receipt")) { event.preventDefault(); window.location.assign(window.location.pathname); }
      else if (document.activeElement && document.activeElement.tagName === "BUTTON") { event.preventDefault(); document.activeElement.click(); }
      event.stopImmediatePropagation();
      return;
    }
    if (key.startsWith("F") || (event.ctrlKey && key.toLowerCase() === "e")) {
      event.preventDefault(); event.stopImmediatePropagation();
    }
  }, true);

  window.pdvSaleCheckout = { open: open, state: function () { return state; } };
})();
