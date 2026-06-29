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

  document.querySelectorAll("input[type='text']").forEach(function (input) {
    if (input.classList.contains("no-upper") || input.name.includes("email")) return;
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
});
