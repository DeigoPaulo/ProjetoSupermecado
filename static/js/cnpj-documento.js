(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SupermercadoDocumentos = api;
}(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  function caracteresDocumento(valor) {
    return String(valor || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  }

  function normalizarCnpjEntrada(valor) {
    var texto = String(valor || "").trim().toUpperCase();
    var formatoPuro = /^[A-Z0-9]{12}[0-9]{2}$/;
    var formatoMascarado = /^[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}\/[A-Z0-9]{4}-[0-9]{2}$/;
    if (!formatoPuro.test(texto) && !formatoMascarado.test(texto)) return "";
    var canonico = texto.replace(/[.\/-]/g, "");
    return formatoPuro.test(canonico) ? canonico : "";
  }

  function formatarCnpjEntrada(valor) {
    var caracteres = caracteresDocumento(valor).slice(0, 14);
    if (caracteres.length > 12) {
      caracteres = caracteres.slice(0, 12) + caracteres.slice(12).replace(/[^0-9]/g, "");
    }
    var partes = [];
    if (caracteres.slice(0, 2)) partes.push(caracteres.slice(0, 2));
    if (caracteres.slice(2, 5)) partes.push("." + caracteres.slice(2, 5));
    if (caracteres.slice(5, 8)) partes.push("." + caracteres.slice(5, 8));
    if (caracteres.slice(8, 12)) partes.push("/" + caracteres.slice(8, 12));
    if (caracteres.slice(12, 14)) partes.push("-" + caracteres.slice(12, 14));
    return partes.join("");
  }

  function formatarCpfEntrada(valor) {
    var digitos = String(valor || "").replace(/\D/g, "").slice(0, 11);
    var partes = [];
    if (digitos.slice(0, 3)) partes.push(digitos.slice(0, 3));
    if (digitos.slice(3, 6)) partes.push("." + digitos.slice(3, 6));
    if (digitos.slice(6, 9)) partes.push("." + digitos.slice(6, 9));
    if (digitos.slice(9, 11)) partes.push("-" + digitos.slice(9, 11));
    return partes.join("");
  }

  function formatarCpfCnpjEntrada(valor) {
    var caracteres = caracteresDocumento(valor);
    return /[A-Z]/.test(caracteres) || caracteres.length > 11
      ? formatarCnpjEntrada(caracteres)
      : formatarCpfEntrada(caracteres);
  }

  return {
    normalizarCnpjEntrada: normalizarCnpjEntrada,
    formatarCnpjEntrada: formatarCnpjEntrada,
    formatarCpfCnpjEntrada: formatarCpfCnpjEntrada,
  };
}));
