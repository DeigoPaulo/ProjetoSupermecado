document.addEventListener("DOMContentLoaded", function () {
  function formatarQuantidadePtBR(valor) {
    return valor.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 3 });
  }

  document.querySelectorAll("[data-purchase-form]").forEach(function (form) {
    var revealButton = form.querySelector("[data-formset-reveal]");
    var draftButton = form.querySelector("[data-draft-submit]");
    var financeCheckbox = form.querySelector("#id_gerar_conta_financeira");
    var financeMessage = form.querySelector("[data-finance-message]");

    function rows() {
      return Array.from(form.querySelectorAll("[data-formset-item]"));
    }

    function rowHasUserData(row) {
      var objectId = row.querySelector("input[name$='-id']");
      if (objectId && objectId.value) return true;
      if (row.querySelector(".field-error")) return true;
      return Array.from(row.querySelectorAll("select, textarea, input:not([type='hidden']):not([type='checkbox']):not([type='radio'])"))
        .some(function (field) { return String(field.value || "").trim() !== ""; });
    }

    rows().forEach(function (row) {
      if (!rowHasUserData(row)) row.classList.add("is-formset-empty");
    });

    function updateRevealButton() {
      if (revealButton) revealButton.hidden = !form.querySelector("[data-formset-item].is-formset-empty");
    }

    function numberValue(field) {
      var value = field ? String(field.value || "").replace(",", ".") : "";
      var parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : 0;
    }

    function updateSummary() {
      var activeRows = rows().filter(function (row) {
        var deleted = row.querySelector("input[name$='-DELETE']");
        var product = row.querySelector("select[name$='-produto']");
        return !row.classList.contains("is-formset-empty") && !(deleted && deleted.checked) && product && product.value;
      });
      var quantity = 0;
      var total = 0;
      activeRows.forEach(function (row) {
        var rowQuantity = numberValue(row.querySelector("input[name$='-quantidade']"));
        var cost = row.querySelector("input[name$='-custo_unitario_previsto']") || row.querySelector("input[name$='-custo_unitario']");
        quantity += rowQuantity;
        total += rowQuantity * numberValue(cost);
      });
      var itemOutput = form.querySelector("[data-summary-items]");
      var quantityOutput = form.querySelector("[data-summary-quantity]");
      var totalOutput = form.querySelector("[data-summary-total]");
      if (itemOutput) itemOutput.textContent = String(activeRows.length);
      if (quantityOutput) quantityOutput.textContent = formatarQuantidadePtBR(quantity);
      if (totalOutput) totalOutput.textContent = total.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    function updateFinanceMessage() {
      if (!financeCheckbox || !financeMessage) return;
      financeMessage.textContent = financeCheckbox.checked
        ? "Será gerado contas a pagar ao finalizar."
        : "Nenhuma conta será criada.";
      financeMessage.className = financeCheckbox.checked ? "finance-message finance-enabled" : "finance-message finance-disabled";
    }

    if (revealButton) {
      revealButton.addEventListener("click", function () {
        var row = form.querySelector("[data-formset-item].is-formset-empty");
        if (!row) return;
        row.classList.remove("is-formset-empty");
        var field = row.querySelector("select[name$='-produto'], input:not([type='hidden'])");
        if (field) field.focus();
        updateRevealButton();
        updateSummary();
      });
    }

    form.addEventListener("input", updateSummary);
    form.addEventListener("change", function (event) {
      var deleteField = event.target.closest("input[name$='-DELETE']");
      if (deleteField) deleteField.closest("[data-formset-item]").classList.toggle("is-marked-delete", deleteField.checked);
      updateSummary();
      updateFinanceMessage();
    });

    document.addEventListener("keydown", function (event) {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
      if (!draftButton || !form.contains(document.activeElement)) return;
      event.preventDefault();
      draftButton.focus();
      form.requestSubmit(draftButton);
    });

    form.addEventListener("submit", function (event) {
      var submitter = event.submitter;
      var finalizing = submitter && submitter.matches("[data-finalize-submit]");
      if (finalizing && !window.confirm("Finalizar esta entrada? O estoque será atualizado e o financeiro será gerado conforme a opção selecionada.")) {
        event.preventDefault();
        return;
      }
      if (form.dataset.submitting === "1") {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = "1";
      if (submitter && submitter.name) {
        var action = document.createElement("input");
        action.type = "hidden";
        action.name = submitter.name;
        action.value = submitter.value;
        form.appendChild(action);
      }
      form.querySelectorAll("button[type='submit']").forEach(function (button) { button.disabled = true; });
      if (submitter) {
        submitter.setAttribute("aria-busy", "true");
        submitter.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processando...';
      }
    });

    updateRevealButton();
    updateSummary();
    updateFinanceMessage();
  });
});
