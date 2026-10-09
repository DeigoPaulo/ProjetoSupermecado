document.addEventListener("DOMContentLoaded", function () {
  function configureFormErrorFeedback() {
    if (document.querySelector(".login-page")) return;
    var errorLists = Array.from(document.querySelectorAll(".errorlist")).filter(function (list) {
      return list.textContent.trim().length > 0;
    });
    if (!errorLists.length) return;

    var summary = document.querySelector("[data-form-error-summary]");
    if (!summary) {
      var content = document.querySelector("main.content");
      if (content) {
        summary = document.createElement("div");
        summary.className = "form-error-summary";
        summary.setAttribute("role", "alert");
        summary.setAttribute("tabindex", "-1");
        summary.setAttribute("data-form-error-summary", "");
        summary.innerHTML = '<i class="fa-solid fa-circle-exclamation" aria-hidden="true"></i><div><strong>Não foi possível salvar.</strong><span>Revise os campos destacados abaixo e tente novamente.</span></div>';
        content.insertBefore(summary, content.firstElementChild || null);
      }
    }

    var firstField = null;
    errorLists.forEach(function (list) {
      var container = list.closest(".form-field, label, .form-section");
      var field = container && container.querySelector("input:not([type='hidden']), select, textarea");
      if (container) container.classList.add("has-error");
      if (field) {
        field.setAttribute("aria-invalid", "true");
        if (!field.getAttribute("aria-describedby") && list.id) field.setAttribute("aria-describedby", list.id);
        if (!firstField && !field.disabled) firstField = field;
      }
    });

    if (summary) {
      summary.focus({ preventScroll: true });
      summary.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (firstField) {
      window.setTimeout(function () {
        firstField.focus({ preventScroll: true });
      }, 350);
    }
  }

  configureFormErrorFeedback();
  var productCodeGenerator = document.querySelector("[data-product-code-generator]");
  if (productCodeGenerator) {
    var productCodeInput = document.getElementById("id_codigo_interno");
    var productCodeFeedback = document.querySelector("[data-product-code-feedback]");
    productCodeGenerator.addEventListener("click", function () {
      productCodeGenerator.disabled = true;
      if (productCodeFeedback) productCodeFeedback.textContent = "Gerando código...";
      fetch(productCodeGenerator.dataset.url, { credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) throw new Error("Não foi possível gerar o código interno.");
          return response.json();
        })
        .then(function (payload) {
          if (!payload.codigo) throw new Error("Código interno não retornado pelo servidor.");
          productCodeInput.value = payload.codigo;
          productCodeInput.dispatchEvent(new Event("input", { bubbles: true }));
          if (productCodeFeedback) productCodeFeedback.textContent = "Código sugerido. Você ainda pode alterá-lo antes de salvar.";
          productCodeInput.focus();
        })
        .catch(function (error) {
          if (productCodeFeedback) productCodeFeedback.textContent = error.message;
        })
        .finally(function () {
          productCodeGenerator.disabled = false;
        });
    });
  }

  var desktopCloseButton = document.getElementById("desktop-close-application");
  if (desktopCloseButton) {
    desktopCloseButton.addEventListener("click", function () {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.closeApplication;
      if (!bridge) return;
      if (!window.confirm("Fechar o aplicativo PDV?")) return;
      desktopCloseButton.disabled = true;
      Promise.resolve(bridge.call(window.SupermercadoDesktop)).catch(function () {
        desktopCloseButton.disabled = false;
        window.alert("Não foi possível fechar o aplicativo.");
      });
    });
  }

  var pdvReconfigureButton = document.getElementById("pdv-reconfigure-terminal");
  if (pdvReconfigureButton) {
    function atualizarReconfiguracaoDesktop() {
      pdvReconfigureButton.hidden = !(window.SupermercadoDesktop && window.SupermercadoDesktop.reconfigureTerminal);
    }
    pdvReconfigureButton.addEventListener("click", function () {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.reconfigureTerminal;
      if (!bridge) return;
      if (!window.confirm("Configurar uma nova credencial para este PDV? A chave atual será substituída somente após uma ativação válida.")) return;
      pdvReconfigureButton.disabled = true;
      Promise.resolve(bridge.call(window.SupermercadoDesktop)).catch(function () {
        pdvReconfigureButton.disabled = false;
        window.alert("Não foi possível abrir a reconfiguração do terminal.");
      });
    });
    document.addEventListener("supermercado:desktop-ready", atualizarReconfiguracaoDesktop, { once: true });
    atualizarReconfiguracaoDesktop();
  }

  var localPrinterPicker = document.querySelector("[data-local-printer-picker]");
  if (localPrinterPicker) {
    var localPrinterSelect = document.getElementById("local-printer-select");
    var localPrinterRefresh = document.getElementById("refresh-local-printers");
    var localPrinterFeedback = document.getElementById("local-printer-feedback");
    var configuredPrinterInput = document.getElementById("id_impressora_padrao");

    function informarImpressorasLocais(texto, erro) {
      if (!localPrinterFeedback) return;
      localPrinterFeedback.textContent = texto;
      localPrinterFeedback.classList.toggle("field-error", Boolean(erro));
    }

    function renderizarImpressorasLocais(payload) {
      if (!payload || payload.status !== "ok") {
        throw new Error((payload && payload.mensagem) || "Não foi possível consultar as impressoras desta máquina.");
      }
      var impressoras = Array.isArray(payload.impressoras) ? payload.impressoras : [];
      localPrinterSelect.innerHTML = "";
      var placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = impressoras.length ? "Selecione uma impressora" : "Nenhuma impressora encontrada";
      localPrinterSelect.appendChild(placeholder);
      impressoras.forEach(function (impressora) {
        var option = document.createElement("option");
        option.value = impressora.nome;
        option.textContent = impressora.nome + (impressora.padrao ? " (padrão)" : "") + (impressora.offline ? " - offline" : "");
        option.disabled = Boolean(impressora.offline);
        localPrinterSelect.appendChild(option);
      });
      localPrinterSelect.disabled = impressoras.length === 0;
      var atual = configuredPrinterInput ? configuredPrinterInput.value : "";
      if (atual && impressoras.some(function (item) { return item.nome === atual && !item.offline; })) {
        localPrinterSelect.value = atual;
      }
      informarImpressorasLocais(impressoras.length + " impressora(s) detectada(s) pelo Windows.", false);
    }

    function carregarImpressorasLocais() {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.listPrinters;
      if (!bridge) {
        localPrinterSelect.disabled = true;
        informarImpressorasLocais("Abra esta configuração pelo PDV Desktop para selecionar uma impressora instalada nesta máquina.", false);
        return;
      }
      localPrinterSelect.disabled = true;
      if (localPrinterRefresh) localPrinterRefresh.disabled = true;
      informarImpressorasLocais("Consultando impressoras do Windows...", false);
      Promise.resolve(bridge.call(window.SupermercadoDesktop))
        .then(renderizarImpressorasLocais)
        .catch(function (erro) {
          localPrinterSelect.innerHTML = '<option value="">Falha na consulta local</option>';
          informarImpressorasLocais(erro.message || "Falha ao consultar impressoras.", true);
        })
        .finally(function () {
          if (localPrinterRefresh) localPrinterRefresh.disabled = false;
        });
    }

    localPrinterSelect.addEventListener("change", function () {
      if (!configuredPrinterInput || !localPrinterSelect.value) return;
      configuredPrinterInput.value = localPrinterSelect.value;
      configuredPrinterInput.dispatchEvent(new Event("input", { bubbles: true }));
      informarImpressorasLocais("Impressora selecionada. Salve a configuração para aplicá-la.", false);
    });
    if (localPrinterRefresh) localPrinterRefresh.addEventListener("click", carregarImpressorasLocais);
    document.addEventListener("supermercado:desktop-ready", carregarImpressorasLocais, { once: true });
    carregarImpressorasLocais();
  }

  var pdvLogoutForm = document.getElementById("pdv-logout-form");
  var pdvExitButton = document.getElementById("pdv-exit-button");
  if (pdvLogoutForm) {
    pdvLogoutForm.addEventListener("submit", function (event) {
      if (!window.confirm("Sair do PDV? O carrinho atual sera descartado.")) {
        event.preventDefault();
      }
    });
  }

  var documentosEntrada = window.SupermercadoDocumentos;
  var normalizarCnpjEntrada = documentosEntrada.normalizarCnpjEntrada;
  var formatarCnpjEntrada = documentosEntrada.formatarCnpjEntrada;
  var formatarCpfCnpjEntrada = documentosEntrada.formatarCpfCnpjEntrada;

  function aplicarFormatacaoDocumento(seletor, formatador) {
    document.querySelectorAll(seletor).forEach(function (campo) {
      if (campo.dataset.documentoFormatado === "1") return;
      campo.dataset.documentoFormatado = "1";
      campo.addEventListener("input", function () {
        this.value = formatador(this.value);
      });
      campo.value = formatador(campo.value);
    });
  }

  function aplicarMascaras() {
    aplicarFormatacaoDocumento(".mask-cnpj, #id_cnpj, #cnpj", formatarCnpjEntrada);
    aplicarFormatacaoDocumento(".mask-cpf-cnpj, #id_cpf_cnpj, #cpf_cnpj", formatarCpfCnpjEntrada);
    if (typeof window.jQuery === "undefined" || !window.jQuery.fn.mask) {
      window.setTimeout(aplicarMascaras, 100);
      return;
    }

    var $ = window.jQuery;
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
      var options = {
        width: "100%",
        placeholder: $field.data("placeholder") || "Selecione",
        allowClear: !$field.prop("required"),
        language: {
          noResults: function () { return "Nenhum resultado encontrado"; },
          searching: function () { return "Pesquisando..."; },
        },
      };
      if ($field.data("ajax-url")) {
        options.minimumInputLength = Number($field.data("minimum-input-length") || 0);
        options.ajax = {
          url: $field.data("ajax-url"),
          dataType: "json",
          delay: 180,
          data: function (params) {
            return { q: params.term || "", page: params.page || 1 };
          },
          processResults: function (data) {
            return {
              results: data.results || [],
              pagination: data.pagination || { more: false },
            };
          },
        };
      }
      $field.select2(options);
    });
  }

  aplicarSelect2();
  window.SupermercadoInitSelect2 = aplicarSelect2;

  function imprimirCupomFallback(url) {
    if (!url) return;
    var frame = document.getElementById("pdv-print-frame");
    if (!frame) {
      frame = document.createElement("iframe");
      frame.id = "pdv-print-frame";
      frame.title = "Impressão do cupom";
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

  function imprimirCupomVenda(url, desktopUrl, opcoes) {
    opcoes = opcoes || {};
    var desktopBridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printSale;
    if (desktopBridge && desktopUrl && window.fetch) {
      window.fetch(desktopUrl, { credentials: "same-origin" })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          var impressao = payload && payload.impressao;
          if (opcoes.somenteAutomatico && !(impressao && impressao.impressao_automatica)) return null;
          if (impressao && impressao.mensagem && (!impressao.impressora_configurada || impressao.documento_pronto === false)) {
            window.alert(impressao.mensagem);
            imprimirCupomFallback(url);
            return null;
          }
          return Promise.resolve(desktopBridge(payload)).then(function (resultado) {
            if (resultado && resultado.status !== "ok") {
              window.alert(resultado.mensagem || "A impressora não confirmou a emissão do documento.");
              imprimirCupomFallback(url);
            }
            return resultado;
          });
        })
        .catch(function () { imprimirCupomFallback(url); });
      return;
    }
    imprimirCupomFallback(url);
  }

  window.pdvPrintSale = imprimirCupomVenda;

  document.querySelectorAll("[data-sale-print-url]").forEach(function (button) {
    button.addEventListener("click", function () {
      imprimirCupomVenda(button.getAttribute("data-sale-print-url"), button.getAttribute("data-sale-desktop-print-url"));
    });
  });

  function imprimirComandaEntrega(url, desktopUrl) {
    var desktopBridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printSale;
    if (desktopBridge && desktopUrl && window.fetch) {
      window.fetch(desktopUrl, { credentials: "same-origin" })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          var impressao = payload && payload.impressao;
          if (!impressao || !impressao.impressora_configurada) {
            window.alert((impressao && impressao.mensagem) || "Configure a impressora de Pedido de separação em Sistema > Impressões.");
            return null;
          }
          return Promise.resolve(desktopBridge(payload)).then(function (resultado) {
            if (!resultado || resultado.status !== "ok") {
              window.alert((resultado && resultado.mensagem) || "A impressora não confirmou a comanda de entrega.");
            }
            return resultado;
          });
        })
        .catch(function () {
          window.alert("Não foi possível preparar a comanda de entrega no servidor.");
        });
      return;
    }
    imprimirCupomFallback(url);
  }

  document.querySelectorAll("[data-delivery-print-url]").forEach(function (button) {
    button.addEventListener("click", function () {
      imprimirComandaEntrega(
        button.getAttribute("data-delivery-print-url"),
        button.getAttribute("data-delivery-desktop-print-url")
      );
    });
  });

  var deliveryAutoPrint = document.getElementById("pdv-delivery-auto-print");
  if (deliveryAutoPrint) {
    window.setTimeout(function () {
      imprimirComandaEntrega(
        deliveryAutoPrint.getAttribute("data-delivery-print-url"),
        deliveryAutoPrint.getAttribute("data-delivery-desktop-print-url")
      );
    }, 250);
  }

  function setSelect2Value(select, id, text) {
    if (!select || !id) return;
    var option = new Option(text || id, id, true, true);
    select.appendChild(option);
    if (typeof window.jQuery !== "undefined") {
      window.jQuery(select).trigger("change");
    } else {
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  document.querySelectorAll("[data-recipe-select]").forEach(function (select) {
    select.addEventListener("change", function () {
      if (!select.value) return;
      fetch("/estoque/receitas-desmembramento/" + select.value + ".json", { headers: { "Accept": "application/json" } })
        .then(function (response) {
          if (!response.ok) throw new Error("Receita indisponível.");
          return response.json();
        })
        .then(function (payload) {
          var receita = payload.receita;
          if (!receita) return;
          var filial = document.getElementById("id_filial");
          var tipo = document.getElementById("id_tipo");
          var tipoSaida = document.getElementById("id_destinos-0-tipo_saída_destino") || document.getElementById("id_tipo_saída_destino");
          var origem = document.getElementById("id_produto_origem");
          var destino = document.getElementById("id_destinos-0-produto_destino") || document.getElementById("id_produto_destino");
          var qtdOrigem = document.getElementById("id_quantidade_origem");
          var qtdDestino = document.getElementById("id_destinos-0-quantidade_destino") || document.getElementById("id_quantidade_destino");
          var observacao = document.getElementById("id_observacao");
          if (receita.filial_id && filial) setSelect2Value(filial, receita.filial_id, receita.filial_id);
          if (tipo) tipo.value = receita.tipo;
          if (tipoSaida) tipoSaida.value = receita.tipo_saída;
          setSelect2Value(origem, receita.produto_origem_id, receita.produto_origem_text);
          setSelect2Value(destino, receita.produto_destino_id, receita.produto_destino_text);
          if (qtdOrigem) qtdOrigem.value = receita.quantidade_origem;
          if (qtdDestino) qtdDestino.value = receita.quantidade_destino;
          if (observacao && receita.observacao) observacao.value = receita.observacao;
        })
        .catch(function (error) {
          window.alert("Não foi possível aplicar a receita: " + error.message);
        });
    });
  });

  document.querySelectorAll("[data-destinos-formset]").forEach(function (formset) {
    var rows = formset.querySelector("[data-destinos-rows]");
    var template = formset.querySelector("[data-destino-empty-form]");
    var totalInput = formset.querySelector("input[name$='-TOTAL_FORMS']");
    var addButton = formset.querySelector("[data-add-destino]");
    if (!rows || !template || !totalInput || !addButton) return;

    function refreshRemoveButtons() {
      var visibleRows = Array.prototype.filter.call(rows.querySelectorAll("[data-destino-row]"), function (row) {
        var deleteInput = row.querySelector("input[type='checkbox'][name$='-DELETE']");
        return !deleteInput || !deleteInput.checked;
      });
      rows.querySelectorAll("[data-remove-destino]").forEach(function (button) {
        button.disabled = visibleRows.length <= 1;
      });
    }

    function prepareDynamicSelect2(row) {
      row.querySelectorAll(".select2-container").forEach(function (container) { container.remove(); });
      row.querySelectorAll(".select2-hidden-accessible").forEach(function (select) {
        select.classList.remove("select2-hidden-accessible");
        select.removeAttribute("data-select2-id");
        select.removeAttribute("aria-hidden");
        select.removeAttribute("tabindex");
      });
      if (typeof window.SupermercadoInitSelect2 === "function") window.SupermercadoInitSelect2();
    }

    addButton.addEventListener("click", function () {
      var index = parseInt(totalInput.value || "0", 10);
      var html = template.innerHTML.replace(/__prefix__/g, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html.trim();
      var row = wrapper.firstElementChild;
      rows.appendChild(row);
      totalInput.value = index + 1;
      prepareDynamicSelect2(row);
      refreshRemoveButtons();
      var firstField = row.querySelector("select, input");
      if (firstField) firstField.focus();
    });

    rows.addEventListener("click", function (event) {
      var button = event.target.closest("[data-remove-destino]");
      if (!button) return;
      var row = button.closest("[data-destino-row]");
      var deleteInput = row && row.querySelector("input[type='checkbox'][name$='-DELETE']");
      if (!row || !deleteInput) return;
      deleteInput.checked = true;
      row.style.display = "none";
      refreshRemoveButtons();
    });

    refreshRemoveButtons();
  });

  var labelsNativePrint = document.getElementById("labels-native-print");
  if (labelsNativePrint) {
    labelsNativePrint.addEventListener("click", function () {
      var feedback = document.getElementById("labels-print-feedback");
      var payloadElement = document.getElementById("labels-native-payload");
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printLabels;
      if (!bridge) {
        if (feedback) feedback.textContent = "Impressão direta disponível somente no aplicativo desktop. Use a impressão pelo navegador neste computador.";
        return;
      }
      try {
        var payload = JSON.parse(payloadElement.textContent);
        labelsNativePrint.disabled = true;
        if (feedback) feedback.textContent = "Enviando etiquetas para a impressora...";
        Promise.resolve(bridge(payload)).then(function (resultado) {
          if (!resultado || resultado.status !== "ok") {
            throw new Error((resultado && resultado.mensagem) || "A impressora não confirmou o lote.");
          }
          if (feedback) feedback.textContent = resultado.copias + " etiqueta(s) de " + resultado.itens + " produto(s) enviadas para " + resultado.impressora + ".";
        }).catch(function (erro) {
          if (feedback) feedback.textContent = "Falha na impressão direta: " + erro.message;
        }).finally(function () {
          labelsNativePrint.disabled = false;
        });
      } catch (erro) {
        labelsNativePrint.disabled = false;
        if (feedback) feedback.textContent = "Não foi possível preparar o lote: " + erro.message;
      }
    });
  }

  document.querySelectorAll(".label-test-print").forEach(function (button) {
    button.addEventListener("click", function () {
      var feedback = document.getElementById("label-test-feedback");
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printLabels;
      if (!bridge) {
        if (feedback) feedback.textContent = "Teste direto disponível somente no app desktop desta máquina.";
        return;
      }
      button.disabled = true;
      if (feedback) feedback.textContent = "Preparando etiqueta de teste...";
      fetch(button.getAttribute("data-url"), { headers: { "Accept": "application/json" } })
        .then(function (response) {
          if (!response.ok) throw new Error("Não foi possível carregar a etiqueta de teste.");
          return response.json();
        })
        .then(function (payload) {
          if (payload.status && payload.status !== "ok") throw new Error(payload.mensagem || "Payload recusado.");
          if (feedback) feedback.textContent = "Enviando etiqueta de teste para a impressora...";
          return Promise.resolve(bridge(payload));
        })
        .then(function (resultado) {
          if (!resultado || resultado.status !== "ok") {
            throw new Error((resultado && resultado.mensagem) || "A impressora não confirmou o teste.");
          }
          if (feedback) feedback.textContent = "Etiqueta de teste enviada para " + resultado.impressora + ".";
        })
        .catch(function (erro) {
          if (feedback) feedback.textContent = "Falha no teste de etiqueta: " + erro.message;
        })
        .finally(function () {
          button.disabled = false;
        });
    });
  });

  var desktopDeviceLogsButton = document.getElementById("desktop-device-logs");
  if (desktopDeviceLogsButton) {
    desktopDeviceLogsButton.addEventListener("click", function () {
      var feedback = document.getElementById("desktop-device-logs-feedback");
      var tbody = document.getElementById("desktop-device-logs-body");
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.deviceLogs;
      function setFeedback(texto) {
        if (feedback) feedback.textContent = texto || "";
      }
      function renderEmpty(texto) {
        if (!tbody) return;
        tbody.innerHTML = "";
        var row = document.createElement("tr");
        var cell = document.createElement("td");
        cell.colSpan = 4;
        cell.className = "empty";
        cell.textContent = texto;
        row.appendChild(cell);
        tbody.appendChild(row);
      }
      function renderLogs(payload) {
        if (!tbody) return;
        var eventos = (payload && payload.eventos) || [];
        tbody.innerHTML = "";
        if (!eventos.length) {
          renderEmpty("Nenhum evento local registrado neste terminal.");
          return;
        }
        eventos.slice().reverse().forEach(function (evento) {
          var dados = evento.payload || {};
          var row = document.createElement("tr");
          [evento.em || "-", evento.tipo || "-", dados.status || "-", dados.mensagem || dados.porta || "-"].forEach(function (valor) {
            var cell = document.createElement("td");
            cell.textContent = valor;
            row.appendChild(cell);
          });
          tbody.appendChild(row);
        });
      }
      if (!bridge) {
        setFeedback("Diagnostico local disponível somente dentro do aplicativo desktop deste terminal.");
        renderEmpty("Abra esta tela no app desktop para ler o log local.");
        return;
      }
      desktopDeviceLogsButton.disabled = true;
      setFeedback("Lendo diagnóstico local...");
      Promise.resolve(bridge.call(window.SupermercadoDesktop, 50))
        .then(function (payload) {
          if (!payload || payload.status !== "ok") throw new Error((payload && payload.mensagem) || "Diagnostico indisponível.");
          renderLogs(payload);
          setFeedback("Eventos carregados: " + String((payload.eventos || []).length) + " de " + String(payload.total || 0) + ".");
        })
        .catch(function (erro) {
          setFeedback("Falha ao ler diagnóstico local: " + erro.message);
        })
        .finally(function () {
          desktopDeviceLogsButton.disabled = false;
        });
    });
  }

  var desktopDeviceDiagnosticsButton = document.getElementById("desktop-device-diagnostics");
  if (desktopDeviceDiagnosticsButton) {
    desktopDeviceDiagnosticsButton.addEventListener("click", function () {
      var feedback = document.getElementById("desktop-device-diagnostics-feedback");
      var tbody = document.getElementById("desktop-device-diagnostics-body");
      var scale = document.getElementById("desktop-diagnostic-scale");
      var drawer = document.getElementById("desktop-diagnostic-drawer");
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.runDeviceDiagnostics;
      var opcoes = {
        ler_balanca: Boolean(scale && scale.checked),
        acionar_gaveta: Boolean(drawer && drawer.checked)
      };
      if (!bridge) {
        if (feedback) feedback.textContent = "Pré-homologação disponível somente dentro do aplicativo desktop.";
        return;
      }
      if (opcoes.acionar_gaveta && !window.confirm("A gaveta está livre e pode ser aberta agora?")) return;
      desktopDeviceDiagnosticsButton.disabled = true;
      if (feedback) feedback.textContent = "Executando verificações locais...";
      Promise.resolve(bridge.call(window.SupermercadoDesktop, opcoes))
        .then(function (payload) {
          if (!payload || !Array.isArray(payload.verificacoes)) {
            throw new Error((payload && payload.mensagem) || "Resposta de diagnóstico inválida.");
          }
          if (tbody) {
            tbody.innerHTML = "";
            payload.verificacoes.forEach(function (item) {
              var row = document.createElement("tr");
              var nome = document.createElement("td");
              var status = document.createElement("td");
              var mensagem = document.createElement("td");
              var chip = document.createElement("span");
              nome.textContent = item.nome || item.codigo || "-";
              chip.className = "status " + (
                item.status === "ok" ? "status-success" :
                item.status === "erro" ? "status-warning" : "status-muted"
              );
              chip.textContent = item.status || "-";
              status.appendChild(chip);
              mensagem.textContent = item.mensagem || "-";
              row.appendChild(nome);
              row.appendChild(status);
              row.appendChild(mensagem);
              tbody.appendChild(row);
            });
          }
          if (feedback) feedback.textContent = payload.mensagem || "Pré-homologação concluída.";
        })
        .catch(function (erro) {
          if (feedback) feedback.textContent = "Falha na pré-homologação: " + erro.message;
        })
        .finally(function () {
          desktopDeviceDiagnosticsButton.disabled = false;
        });
    });
  }

  function aplicarCamposMonetarios(root) {
    var escopo = root || document;
    var nomesMonetarios = /(^|_)(valor|preço|custo|desconto|taxa|frete|total)(_|$)/i;
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
    var nome = (input.name || "").toLowerCase();
    var autocomplete = (input.getAttribute("autocomplete") || "").toLowerCase();
    var preservarDigitacao =
      input.classList.contains("no-upper") ||
      input.closest(".no-uppercase-fields") ||
      nome.includes("email") ||
      nome.includes("usuario") ||
      nome.includes("username") ||
      nome.includes("login") ||
      autocomplete === "username";
    if (preservarDigitacao) return;
    input.addEventListener("input", function () {
      var start = this.selectionStart;
      var end = this.selectionEnd;
      this.value = this.value.toUpperCase();
      this.setSelectionRange(start, end);
    });
  });

  document.querySelectorAll("form[data-cadastro-lookup-url]").forEach(function (form) {
    var buttons = Array.from(form.querySelectorAll("[data-cadastro-lookup-button]"));
    var feedback = form.querySelector("[data-cadastro-lookup-feedback]");
    var cnpjInput = form.querySelector("[data-lookup-target='cnpj'], #id_cnpj");
    var cepInput = form.querySelector("[data-lookup-target='cep'], #id_cep");
    var lookupUrl = form.getAttribute("data-cadastro-lookup-url");

    function setFeedback(message, isError) {
      if (!feedback) return;
      feedback.hidden = false;
      feedback.textContent = message || "";
      feedback.classList.toggle("form-note-danger", Boolean(isError));
    }

    function fillIfEmpty(name, value) {
      if (value === undefined || value === null || value === "") return;
      var field = form.querySelector("[name='" + name + "']");
      if (!field || field.value) return;
      field.value = value;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function applyLookupData(data) {
      if (!data || !data.dados) return;
      var fields = ["razao_social", "nome_fantasia", "nome", "cnpj", "telefone", "email", "cep", "logradouro", "numero", "complemento", "bairro", "endereco", "municipio", "uf", "codigo_municipio_ibge", "regime_tributario"];
      fields.forEach(function (field) {
        fillIfEmpty(field, data.dados[field]);
      });
      setFeedback(data.mensagem || "Cadastro encontrado e aplicado aos campos vazios.", false);
    }

    function runLookup(event) {
      if (!lookupUrl) return;
      var tipo = event.currentTarget.getAttribute("data-lookup-kind");
      var input = tipo === "cnpj" ? cnpjInput : cepInput;
      var valorConsulta = tipo === "cnpj"
        ? normalizarCnpjEntrada(input ? input.value : "")
        : (input ? (input.value || "").replace(/\D/g, "") : "");
      var expectedLength = tipo === "cnpj" ? 14 : 8;
      if (valorConsulta.length !== expectedLength) {
        setFeedback(tipo === "cnpj" ? "Informe um CNPJ válido com 14 caracteres." : "Informe um CEP com 8 dígitos.", true);
        if (input) input.focus();
        return;
      }
      buttons.forEach(function (button) { button.disabled = true; });
      setFeedback(tipo === "cnpj" ? "Consultando CNPJ..." : "Consultando CEP...", false);
      fetch(lookupUrl + "?" + tipo + "=" + encodeURIComponent(valorConsulta), { headers: { "Accept": "application/json" } })
        .then(function (response) {
          return response.json().then(function (payload) {
            if (!response.ok) throw new Error(payload.mensagem || "Não foi possível consultar o cadastro.");
            return payload;
          });
        })
        .then(function (payload) {
          if (payload.dados) {
            applyLookupData(payload);
            return;
          }
          setFeedback(payload.mensagem || "Cadastro não encontrado localmente.", payload.status === "invalid");
        })
        .catch(function (error) {
          setFeedback(error.message, true);
        })
        .finally(function () {
          buttons.forEach(function (button) { button.disabled = false; });
        });
    }

    buttons.forEach(function (button) { button.addEventListener("click", runLookup); });
  });

  document.querySelectorAll("[data-tef-refund-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.refundPayment;
      if (!bridge || form.dataset.tefRefundReady === "1") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      var msg = form.getAttribute("data-msg") || "Confirma esta operação?";
      if (!window.confirm(msg)) return;
      var supervisor = form.querySelector("input[name='supervisor_usuario']");
      var senha = form.querySelector("input[name='supervisor_senha']");
      if ((supervisor && !supervisor.value.trim()) || (senha && !senha.value.trim())) {
        window.alert("Informe supervisor e senha antes de chamar o estorno na maquininha.");
        if (supervisor && !supervisor.value.trim()) supervisor.focus();
        else if (senha) senha.focus();
        return;
      }
      var botao = form.querySelector("button[type='submit']");
      if (botao) {
        botao.disabled = true;
        botao.dataset.originalText = botao.textContent;
        botao.textContent = "Aguardando TEF...";
      }
      Promise.resolve(bridge.call(window.SupermercadoDesktop, {
        tipo: form.getAttribute("data-refund-tipo") || "",
        valor: form.getAttribute("data-refund-valor") || "",
        transacao_externa_id: form.getAttribute("data-refund-transacao") || "",
        idempotency_key: form.getAttribute("data-refund-key") || [
          "refund",
          form.getAttribute("data-refund-transacao") || "",
          form.getAttribute("data-refund-valor") || "",
        ].join(":"),
      }))
        .then(function (resultado) {
          if (!resultado || resultado.status !== "ok" || !resultado.estornado) {
            throw new Error((resultado && resultado.mensagem) || "Estorno não confirmado pela maquininha.");
          }
          var autorizacao = form.querySelector("input[name='autorizacao']");
          var mensagem = form.querySelector("input[name='mensagem_processadora']");
          var transacaoEstorno = form.querySelector("input[name='transacao_estorno_id']");
          if (autorizacao && !autorizacao.value.trim()) {
            autorizacao.value = resultado.codigo_autorizacao || resultado.nsu || resultado.estorno_transacao_id || "";
          }
          if (transacaoEstorno) {
            transacaoEstorno.value = resultado.estorno_transacao_id || "";
          }
          if (mensagem) {
            mensagem.value = resultado.mensagem_processadora || "Estorno aprovado pela maquininha.";
            if (resultado.estorno_transacao_id) {
              mensagem.value += " Transação de estorno: " + resultado.estorno_transacao_id + ".";
            }
          }          form.dataset.tefRefundReady = "1";
          form.submit();
        })
        .catch(function (erro) {
          window.alert("Não foi possível confirmar o estorno na maquininha: " + erro.message);
          if (botao) {
            botao.disabled = false;
            botao.textContent = botao.dataset.originalText || "Confirmar estorno";
          }
        });
    });
  });

  document.querySelectorAll(".form-confirm").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var msg = form.getAttribute("data-msg") || "Confirma esta operação?";
      if (!window.confirm(msg)) event.preventDefault();
    });
  });

  function executarGavetaPendente(tentativa) {
    var payloadNode = document.getElementById("pdv-cash-drawer-action");
    if (!payloadNode) return;
    var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.openCashDrawer;
    if (!bridge) {
      if ((tentativa || 0) < 12) {
        window.setTimeout(function () { executarGavetaPendente((tentativa || 0) + 1); }, 250);
      }
      return;
    }
    var payload;
    try {
      payload = JSON.parse(payloadNode.textContent || "{}");
    } catch (erro) {
      return;
    }
    payloadNode.remove();
    Promise.resolve(bridge.call(window.SupermercadoDesktop, payload)).catch(function () {});
  }

  executarGavetaPendente(0);
  window.pdvRunPendingCashDrawer = executarGavetaPendente;

  if (document.body.classList.contains("pdv-mode")) {
    var cashOpen = document.querySelector(".pdv-workspace")?.dataset.pdvCashOpen === "1";
    var buscaProduto = document.getElementById("id_busca");
    var quantidadeInput = document.getElementById("id_quantidade");
    var scaleButton = document.querySelector("[data-pdv-read-scale]");
    var scaleFeedback = document.getElementById("pdv-scale-feedback");
    var descontoInput = document.getElementById("id_desconto");
    var discountModal = document.getElementById("pdv-modal-discount");
    var discountEntry = document.getElementById("pdv-discount-entry");
    var discountEntryStep = document.getElementById("pdv-discount-entry-step");
    var discountAuthorizationStep = document.getElementById("pdv-discount-authorization-step");
    var discountApply = document.getElementById("pdv-discount-apply");
    var discountAuthorize = document.getElementById("pdv-discount-authorize");
    var discountMode = "amount";
    var clientSelect = document.getElementById("id_cliente");
    var clientCurrent = document.getElementById("pdv-client-current");
    var clientModal = document.getElementById("pdv-modal-clients");
    var clientSearch = document.getElementById("pdv-client-search");
    var clientResults = document.getElementById("pdv-client-results");
    var clientSelectStep = document.getElementById("pdv-client-select-step");
    var clientCreateForm = document.getElementById("pdv-client-create-form");
    var clientCreateError = document.getElementById("pdv-client-create-error");
    var clientCreateStage = 0;
    var clientSearchError = document.getElementById("pdv-client-search-error");
    var davModal = document.getElementById("pdv-modal-dav");
    var refundModal = document.getElementById("pdv-modal-refunds");
    var refundDetailModal = document.getElementById("pdv-modal-refund-detail");
    var refundSearch = refundModal && refundModal.querySelector("[data-pdv-refund-search]");
    var refundSearchTimer = null;
    var refundSearchSequence = 0;
    var clientSearchTimer = null;
    var clientSearchSequence = 0;
    var clientCreatePending = false;
    var discountAuthorization = document.getElementById("pdv-discount-authorization");
    var discountSupervisor = discountAuthorization && discountAuthorization.querySelector("input[name='supervisor_usuario']");
    var discountPassword = discountAuthorization && discountAuthorization.querySelector("input[name='supervisor_senha']");
    var recebidoInput = document.getElementById("id_valor_recebido");
    var finishForm = document.getElementById("pdv-finish-form");
    var finalizeButton = document.getElementById("pdv-finalize-button");
    var finishShortcut = document.getElementById("pdv-finish-shortcut");
    var paymentFeedback = document.getElementById("pdv-payment-feedback");
    var documentTypeInput = document.getElementById("id_documento_consumidor_tipo");
    var documentInput = document.getElementById("id_documento_consumidor");
    var documentLabel = document.getElementById("pdv-document-label");
    var cpfDecisionInputs = document.querySelectorAll('input[name="cpf_na_nota"]');
    var cpfDocumentPanel = document.getElementById("pdv-cpf-document");
    var captureDocumentButton = document.getElementById("pdv-capture-document");
    var resumo = document.querySelector(".pdv-summary");
    var descontoDisplay = document.getElementById("pdv-desconto-display");
    var totalFinalDisplay = document.getElementById("pdv-total-final");
    var trocoDisplay = document.getElementById("pdv-troco-estimado");
    var paymentModal = document.getElementById("pdv-payment-modal");
    var openPaymentButton = document.getElementById("pdv-open-payment");
    var closePaymentButton = document.getElementById("pdv-close-payment");
    var confirmPaymentButton = document.getElementById("pdv-confirm-payment");
    var addPaymentButton = document.getElementById("pdv-add-payment");
    var deliveryForm = document.querySelector("#pdv-modal-delivery form");
    var deliveryContinue = document.getElementById("pdv-delivery-continue");
    var deliveryBack = document.getElementById("pdv-delivery-back");
    var deliveryStage = 0;
    var deliveryContinuing = false;
    var deliverySavedAddress = "";
    var deliverySavedBairro = "";
    var deliverySelectedClient = null;
    var deliveryQuote = null;
    var checkoutMode = "sale";
    var paymentRows = document.getElementById("pdv-payment-rows");
    var paymentTemplate = document.getElementById("pdv-payment-row-template");
    var pagamentoLancado = document.getElementById("pdv-pagamento-lancado");
    var pagamentoRestante = document.getElementById("pdv-pagamento-restante");
    var modalSubtotal = document.getElementById("pdv-modal-subtotal");
    var modalDesconto = document.getElementById("pdv-modal-desconto");
    var modalTotal = document.getElementById("pdv-modal-total");
    var modalLancado = document.getElementById("pdv-modal-lancado");
    var modalRestante = document.getElementById("pdv-modal-restante");
    var modalTroco = document.getElementById("pdv-modal-troco");
    var electronicChoice = document.getElementById("pdv-electronic-choice");
    var pixPanel = document.getElementById("pdv-pix-panel");
    var pixQrCode = document.getElementById("pdv-pix-qrcode");
    var pixValue = document.getElementById("pdv-pix-value");
    var pixMessage = document.getElementById("pdv-pix-message");
    var pixSimulation = document.getElementById("pdv-pix-simulation");
    var pixPollingToken = 0;
    var pdvModals = document.querySelectorAll(".pdv-modal");
    var postSaleModal = document.getElementById("pdv-post-sale-modal");
    var postSalePrintButton = document.getElementById("pdv-print-last-sale");
    var postSaleCloseButton = document.getElementById("pdv-close-post-sale");
    var deliveryClientField = document.querySelector(".pdv-delivery-client-field");
    var deliveryClientSearch = deliveryClientField && deliveryClientField.querySelector("[data-delivery-client-search]");
    var deliveryClientId = document.querySelector('#pdv-modal-delivery input[name="cliente"]');
    var deliveryClientResults = document.getElementById("pdv-delivery-client-results");
    var deliveryClientStatus = document.getElementById("pdv-delivery-client-status");
    var deliveryClientEmail = document.getElementById("pdv-delivery-client-email");
    var deliverySaveClient = document.querySelector('#pdv-modal-delivery input[name="salvar_cliente"]');
    var deliveryCancelForm = document.getElementById("pdv-delivery-cancel-form");
    var deliveryCancelPedidoId = null;
    var deliveryReturnForm = document.getElementById("pdv-delivery-return-form");
    var deliveryReturnPedidoId = null;
    var deliveryItemsPedidoId = null;
    var deliveryClientItems = [];
    var deliveryClientIndex = -1;
    var deliveryClientRequest = 0;
    var deliveryClientTimer = null;
    var focusBeforePayment = null;
    var focusBeforeModal = null;
    var selectedItemStatus = document.getElementById("pdv-selected-item");
    var quantityModal = document.getElementById("pdv-modal-quantity");
    var quantityForm = document.getElementById("pdv-quantity-form");
    var quantityInput = document.getElementById("pdv-quantity-input");
    var quantityProduct = document.getElementById("pdv-quantity-product");
    var quantityCurrent = document.getElementById("pdv-quantity-current");

    function fecharResultadosClienteEntrega() {
      if (!deliveryClientResults || !deliveryClientSearch) return;
      deliveryClientResults.hidden = true;
      deliveryClientResults.innerHTML = "";
      deliveryClientSearch.setAttribute("aria-expanded", "false");
      deliveryClientSearch.removeAttribute("aria-activedescendant");
      deliveryClientItems = [];
      deliveryClientIndex = -1;
    }

    function atualizarSelecaoClienteEntrega() {
      if (!deliveryClientResults || !deliveryClientSearch) return;
      deliveryClientResults.querySelectorAll("[data-delivery-client-option]").forEach(function (option, index) {
        var selected = index === deliveryClientIndex;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-selected", selected ? "true" : "false");
        if (selected) {
          deliveryClientSearch.setAttribute("aria-activedescendant", option.id);
          option.scrollIntoView({ block: "nearest" });
        }
      });
    }

    function atualizarDocumentoEntrega(cliente) {
      if (!deliveryForm) return;
      var tipo = deliveryForm.elements.documento_cliente_tipo;
      var valor = deliveryForm.elements.documento_cliente;
      var cadastrado = document.getElementById("pdv-delivery-registered-document");
      var status = document.getElementById("pdv-delivery-document-status");
      var field = document.getElementById("pdv-delivery-document-field");
      var valido = cliente && ["CPF", "CNPJ"].indexOf(cliente.documento_fiscal_tipo) !== -1;
      var naoIdentificado = tipo && tipo.querySelector('option[value="NAO_IDENTIFICADO"]');
      if (naoIdentificado) naoIdentificado.disabled = Boolean(valido);
      if (valido && tipo && tipo.value === "NAO_IDENTIFICADO") tipo.value = cliente.documento_fiscal_tipo;
      if (cadastrado) {
        cadastrado.hidden = !cliente || !cliente.cpf_cnpj;
        cadastrado.textContent = cliente && cliente.cpf_cnpj ? "Documento cadastrado do cliente: " + cliente.cpf_cnpj : "";
      }
      if (field) field.hidden = Boolean(valido && tipo && tipo.value === cliente.documento_fiscal_tipo);
      if (status) status.textContent = valido && tipo && tipo.value === cliente.documento_fiscal_tipo
        ? (tipo.value === "CPF" ? "CPF cadastrado será utilizado no documento fiscal." : "CNPJ cadastrado será utilizado no documento fiscal.")
        : "Documento fiscal: informe apenas quando aplicável ao pedido.";
      if (valor && valido && tipo && tipo.value === cliente.documento_fiscal_tipo) valor.value = cliente.cpf_cnpj;
    }

    function selecionarClienteEntrega(cliente) {
      if (!cliente || !deliveryClientSearch || !deliveryClientId) return;
      deliverySelectedClient = cliente;
      deliveryClientId.value = cliente.id;
      deliveryClientSearch.value = cliente.nome || "";
      if (deliveryClientEmail) {
        deliveryClientEmail.hidden = !cliente.email;
        deliveryClientEmail.textContent = cliente.email ? "E-mail: " + cliente.email : "";
      }
      var deliveryPhone = document.querySelector('#pdv-modal-delivery input[name="telefone"]');
      var deliveryAddress = deliveryForm && deliveryForm.elements.endereco_entrega;
      if (deliveryPhone) deliveryPhone.value = cliente.telefone || "";
      deliverySavedAddress = [
        [cliente.logradouro, cliente.numero].filter(Boolean).join(", "),
        cliente.complemento, cliente.bairro,
        [cliente.municipio, cliente.uf].filter(Boolean).join("/"), cliente.cep
      ].filter(Boolean).join(" - ") || cliente.endereco || "";
      if (deliveryAddress) deliveryAddress.value = deliverySavedAddress;
      deliverySavedBairro = cliente.bairro || "";
      var savedChoice = document.getElementById("pdv-delivery-saved-choice");
      if (savedChoice) savedChoice.hidden = !deliverySavedAddress.trim();
      var savedSummary = document.getElementById("pdv-delivery-saved-address");
      if (savedSummary) savedSummary.textContent = deliverySavedAddress;
      var savedMode = deliveryForm && deliveryForm.querySelector('input[name="delivery_address_mode"][value="saved"]');
      if (savedMode && deliverySavedAddress.trim()) savedMode.checked = true;
      var deliveryBairro = deliveryForm && deliveryForm.elements.bairro_entrega;
      if (deliveryBairro) deliveryBairro.value = deliverySavedBairro;
      atualizarModoEnderecoEntrega();
      var fiscalFields = {
        destinatario_indicador_ie: "indicador_ie",
        destinatario_inscricao_estadual: "inscricao_estadual", destinatario_logradouro: "logradouro",
        destinatario_numero: "numero", destinatario_complemento: "complemento",
        destinatario_bairro: "bairro", destinatario_codigo_municipio_ibge: "codigo_municipio_ibge",
        destinatario_municipio: "municipio", destinatario_uf: "uf", destinatario_cep: "cep"
      };
      Object.keys(fiscalFields).forEach(function (name) {
        var field = deliveryForm && deliveryForm.elements[name];
        if (field) field.value = cliente[fiscalFields[name]] || "";
      });
      var docTipo = deliveryForm.elements.documento_cliente_tipo;
      var docValor = deliveryForm.elements.documento_cliente;
      var tipoInferido = cliente.documento_fiscal_tipo || "NAO_IDENTIFICADO";
      if (docTipo) docTipo.value = tipoInferido;
      if (docValor) docValor.value = tipoInferido === "NAO_IDENTIFICADO" ? "" : (cliente.cpf_cnpj || "");
      atualizarDocumentoEntrega(cliente);
      if (deliverySaveClient) {
        deliverySaveClient.checked = false;
        deliverySaveClient.disabled = true;
      }
      if (deliveryClientStatus) deliveryClientStatus.textContent = "Cliente cadastrado selecionado. Telefone e endereço foram preenchidos.";
      fecharResultadosClienteEntrega();
      if (deliveryPhone) deliveryPhone.focus();
    }

    function renderizarClientesEntrega(resultados) {
      if (!deliveryClientResults || !deliveryClientSearch) return;
      deliveryClientItems = resultados || [];
      deliveryClientResults.innerHTML = "";
      if (!deliveryClientItems.length) {
        fecharResultadosClienteEntrega();
        if (deliveryClientStatus) deliveryClientStatus.textContent = "Cliente não encontrado. Continue como avulso ou marque a opção para salvá-lo.";
        return;
      }
      deliveryClientItems.forEach(function (cliente, index) {
        var option = document.createElement("button");
        option.type = "button";
        option.id = "pdv-delivery-client-option-" + cliente.id;
        option.className = "pdv-delivery-client-option";
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        option.setAttribute("data-delivery-client-option", String(index));
        option.tabIndex = -1;
        var title = document.createElement("strong");
        title.textContent = cliente.nome || "";
        var detail = document.createElement("small");
        detail.textContent = [cliente.telefone, cliente.cpf_cnpj, cliente.endereco].filter(Boolean).join(" | ") || "Cliente cadastrado";
        option.appendChild(title);
        option.appendChild(detail);
        option.addEventListener("click", function () { selecionarClienteEntrega(cliente); });
        deliveryClientResults.appendChild(option);
      });
      deliveryClientIndex = 0;
      deliveryClientResults.hidden = false;
      deliveryClientSearch.setAttribute("aria-expanded", "true");
      atualizarSelecaoClienteEntrega();
      if (deliveryClientStatus) deliveryClientStatus.textContent = "Cliente localizado. Use as setas e Enter para selecionar.";
    }

    function buscarClientesEntrega() {
      if (!deliveryClientField || !deliveryClientSearch) return;
      var termo = deliveryClientSearch.value.trim();
      var url = deliveryClientField.getAttribute("data-client-search-url");
      if (!url || termo.length < 2) {
        fecharResultadosClienteEntrega();
        if (deliveryClientStatus) deliveryClientStatus.textContent = "Digite ao menos 2 caracteres para localizar um cliente salvo.";
        return;
      }
      var requestId = ++deliveryClientRequest;
      fetch(url + "?q=" + encodeURIComponent(termo), { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (response) {
          if (!response.ok) throw new Error("Falha ao consultar clientes.");
          return response.json();
        })
        .then(function (payload) {
          if (requestId !== deliveryClientRequest) return;
          renderizarClientesEntrega(payload.results || []);
        })
        .catch(function () {
          if (requestId !== deliveryClientRequest) return;
          fecharResultadosClienteEntrega();
          if (deliveryClientStatus) deliveryClientStatus.textContent = "Não foi possível consultar os clientes. A entrega avulsa continua disponível.";
        });
    }

    if (deliveryClientSearch) {
      deliveryClientSearch.addEventListener("input", function () {
        if (deliveryClientId && deliveryClientId.value) {
          deliveryClientId.value = "";
          deliverySelectedClient = null;
          if (deliveryClientEmail) { deliveryClientEmail.hidden = true; deliveryClientEmail.textContent = ""; }
          if (deliverySaveClient) deliverySaveClient.disabled = false;
          deliverySavedAddress = "";
          deliverySavedBairro = "";
          ["documento_cliente", "destinatario_indicador_ie", "destinatario_inscricao_estadual",
            "destinatario_logradouro", "destinatario_numero", "destinatario_complemento",
            "destinatario_bairro", "destinatario_codigo_municipio_ibge", "destinatario_municipio",
            "destinatario_uf", "destinatario_cep", "telefone", "endereco_entrega", "bairro_entrega"
          ].forEach(function (name) {
            var field = deliveryForm && deliveryForm.elements[name];
            if (field) field.value = "";
          });
          var savedChoice = document.getElementById("pdv-delivery-saved-choice");
          if (savedChoice) savedChoice.hidden = true;
          var otherMode = deliveryForm.querySelector('input[name="delivery_address_mode"][value="other"]');
          if (otherMode) otherMode.checked = true;
          atualizarModoEnderecoEntrega();
          var docTipo = deliveryForm.elements.documento_cliente_tipo;
          var naoIdentificado = docTipo && docTipo.querySelector('option[value="NAO_IDENTIFICADO"]');
          if (naoIdentificado) naoIdentificado.disabled = false;
          if (docTipo) docTipo.value = "NAO_IDENTIFICADO";
          atualizarDocumentoEntrega(null);
        }
        clearTimeout(deliveryClientTimer);
        deliveryClientTimer = setTimeout(buscarClientesEntrega, 180);
      });
      deliveryClientSearch.addEventListener("keydown", function (event) {
        if (!deliveryClientResults || deliveryClientResults.hidden) return;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          event.stopPropagation();
          var delta = event.key === "ArrowDown" ? 1 : -1;
          deliveryClientIndex = (deliveryClientIndex + delta + deliveryClientItems.length) % deliveryClientItems.length;
          atualizarSelecaoClienteEntrega();
          return;
        }
        if (((event.key === "Enter" && !event.ctrlKey && !event.altKey) || event.key === "Tab") && deliveryClientIndex >= 0) {
          event.preventDefault();
          event.stopPropagation();
          selecionarClienteEntrega(deliveryClientItems[deliveryClientIndex]);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          fecharResultadosClienteEntrega();
        }
      });
    }

    restaurarFocoPrincipalPdv();

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
      if (checkoutMode === "delivery") return deliveryQuote ? decimalFromInput(deliveryQuote.total) : 0;
      var subtotal = decimalFromInput(resumo.dataset.total);
      var desconto = Math.max(decimalFromInput(descontoInput && descontoInput.value), 0);
      return Math.max(subtotal - desconto, 0);
    }

    function atualizarResumoPdv() {
      if (!resumo) return;
      var subtotal = checkoutMode === "delivery" && deliveryQuote ? decimalFromInput(deliveryQuote.subtotal) : decimalFromInput(resumo.dataset.total);
      var desconto = checkoutMode === "delivery" ? 0 : Math.max(decimalFromInput(descontoInput && descontoInput.value), 0);
      var recebidoInformado = Math.max(decimalFromInput(recebidoInput && recebidoInput.value), 0);
      var recebidoPagamentos = totalPagamentosLancados();
      var recebido = Math.max(recebidoInformado, recebidoPagamentos);
      var totalFinal = totalFinalAtual();
      var restante = Math.max(totalFinal - recebidoPagamentos, 0);
      var troco = Math.max(recebido - totalFinal, 0);

      if (descontoDisplay) descontoDisplay.textContent = formatMoney(desconto);
      var discountBrief = document.getElementById("pdv-discount-brief");
      if (discountBrief) discountBrief.textContent = formatMoney(desconto);
      if (totalFinalDisplay) totalFinalDisplay.textContent = formatMoney(totalFinal);
      if (trocoDisplay) trocoDisplay.textContent = formatMoney(troco);
      if (pagamentoLancado) pagamentoLancado.textContent = formatMoney(recebidoPagamentos);
      if (pagamentoRestante) pagamentoRestante.textContent = formatMoney(restante);
      if (modalSubtotal) modalSubtotal.textContent = formatMoney(subtotal);
      var freteRow = document.getElementById("pdv-modal-frete-row");
      var freteValue = document.getElementById("pdv-modal-frete");
      if (freteRow) freteRow.hidden = checkoutMode !== "delivery";
      if (freteValue) freteValue.textContent = formatMoney(checkoutMode === "delivery" && deliveryQuote ? decimalFromInput(deliveryQuote.frete) : 0);
      if (modalDesconto) modalDesconto.textContent = formatMoney(desconto);
      if (modalTotal) modalTotal.textContent = formatMoney(totalFinal);
      if (modalLancado) modalLancado.textContent = formatMoney(recebidoPagamentos);
      if (modalRestante) modalRestante.textContent = formatMoney(restante);
      if (modalTroco) modalTroco.textContent = formatMoney(Math.max(recebidoPagamentos - totalFinal, 0));
    }

    function atualizarAutorizacaoDesconto() {
      if (!discountAuthorization) return;
      var exigeAutorizacao = Math.max(decimalFromInput(descontoInput && descontoInput.value), 0) > 0;
      discountAuthorization.hidden = !exigeAutorizacao;
      if (discountSupervisor) discountSupervisor.required = exigeAutorizacao;
      if (discountPassword) discountPassword.required = exigeAutorizacao;
      if (!exigeAutorizacao) {
        if (discountSupervisor) discountSupervisor.value = "";
        if (discountPassword) discountPassword.value = "";
      }
    }

    function decisaoCpfNaNota() {
      var selecionado = Array.prototype.find.call(cpfDecisionInputs, function (input) { return input.checked; });
      return selecionado ? selecionado.value : "";
    }

    function cpfValidoNoPdv(valor) {
      var cpf = String(valor || "").replace(/\D/g, "");
      if (cpf.length !== 11 || /^([0-9])\1{10}$/.test(cpf)) return false;
      var numeros = cpf.split("").map(Number);
      for (var tamanho = 9; tamanho <= 10; tamanho += 1) {
        var soma = 0;
        for (var indice = 0; indice < tamanho; indice += 1) soma += numeros[indice] * (tamanho + 1 - indice);
        var digito = (soma * 10) % 11;
        if (digito === 10) digito = 0;
        if (numeros[tamanho] !== digito) return false;
      }
      return true;
    }

    function cnpjValidoNoPdv(valor) {
      var cnpj = String(valor || "").trim().toUpperCase().replace(/[.\/-]/g, "");
      if (!/^[A-Z0-9]{12}[0-9]{2}$/.test(cnpj)) return false;
      function digito(base) {
        var peso = 2;
        var soma = 0;
        for (var indice = base.length - 1; indice >= 0; indice -= 1) {
          soma += (base.charCodeAt(indice) - 48) * peso;
          peso = peso === 9 ? 2 : peso + 1;
        }
        var resto = soma % 11;
        return resto === 0 || resto === 1 ? "0" : String(11 - resto);
      }
      var primeiro = digito(cnpj.slice(0, 12));
      return cnpj.slice(-2) === primeiro + digito(cnpj.slice(0, 12) + primeiro);
    }

    function atualizarCpfNaNota() {
      if (checkoutMode === "delivery") {
        if (cpfDocumentPanel) cpfDocumentPanel.hidden = true;
        if (documentInput) documentInput.required = false;
        return;
      }
      var decisao = decisaoCpfNaNota();
      var informar = decisao === "SIM" || decisao === "CPF" || decisao === "CNPJ";
      var tipo = decisao === "CNPJ" ? "CNPJ" : "CPF";
      if (cpfDocumentPanel) cpfDocumentPanel.hidden = !informar;
      if (documentInput) documentInput.required = informar;
      if (documentTypeInput) documentTypeInput.value = informar ? tipo : "NAO_IDENTIFICADO";
      if (documentLabel) documentLabel.textContent = tipo + " do consumidor";
      if (documentInput) {
        documentInput.inputMode = tipo === "CPF" ? "numeric" : "text";
        documentInput.placeholder = tipo === "CPF" ? "Digite os 11 números" : "Digite o CNPJ";
      }
      if (decisao === "NAO" && documentInput) documentInput.value = "";
    }

    function valorDescontoModal() {
      var raw = discountEntry ? discountEntry.value.trim() : "";
      var value = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
      if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null;
      var entered = Number(value);
      var subtotal = decimalFromInput(resumo && resumo.dataset.total);
      if (!Number.isFinite(entered) || entered < 0 || (discountMode === "percent" && entered > 100)) return null;
      return Math.round((discountMode === "percent" ? subtotal * entered / 100 : entered) * 100) / 100;
    }

    function atualizarPreviewDesconto() {
      var amount = valorDescontoModal();
      var subtotal = decimalFromInput(resumo && resumo.dataset.total);
      var preview = document.getElementById("pdv-discount-new-total");
      if (preview) preview.textContent = amount === null || amount > subtotal ? "—" : formatMoney(subtotal - amount);
    }

    function mostrarEtapaDesconto(authorization) {
      discountEntryStep.hidden = authorization;
      discountAuthorizationStep.hidden = !authorization;
      discountApply.hidden = authorization;
      discountAuthorize.hidden = !authorization;
      if (authorization) { if (discountSupervisor) discountSupervisor.focus(); }
      else if (discountEntry) { discountEntry.focus(); discountEntry.select(); }
    }

    function abrirDesconto(authorization) {
      if (!discountModal || !cashOpen || !cartRows.length) return;
      discountMode = "amount";
      discountModal.querySelectorAll("[data-pdv-discount-mode]").forEach(function (button) {
        button.setAttribute("aria-pressed", button.dataset.pdvDiscountMode === "amount" ? "true" : "false");
      });
      discountEntry.value = descontoInput ? String(descontoInput.value || "0").replace(".", ",") : "0";
      document.getElementById("pdv-checkout-discount-error").textContent = "";
      abrirModalPdv("discount");
      mostrarEtapaDesconto(Boolean(authorization && decimalFromInput(descontoInput && descontoInput.value) > 0));
      atualizarPreviewDesconto();
    }
    window.pdvOpenDiscount = abrirDesconto;

    function aplicarDesconto() {
      var amount = valorDescontoModal();
      var subtotal = decimalFromInput(resumo && resumo.dataset.total);
      var feedback = document.getElementById("pdv-checkout-discount-error");
      if (amount === null || amount > subtotal) {
        feedback.textContent = "Informe um desconto válido que não ultrapasse o total.";
        discountEntry.focus();
        return;
      }
      feedback.textContent = "";
      descontoInput.value = amount.toFixed(2);
      descontoInput.dispatchEvent(new Event("input", { bubbles: true }));
      if (amount > 0) mostrarEtapaDesconto(true);
      else { fecharModalPdv(false); restaurarFocoPrincipalPdv(true); }
    }

    function confirmarDescontoAutorizado() {
      var feedback = document.getElementById("pdv-checkout-discount-error");
      if (!discountSupervisor.value.trim() || !discountPassword.value) {
        feedback.textContent = "Informe usuário e senha do supervisor.";
        (!discountSupervisor.value.trim() ? discountSupervisor : discountPassword).focus();
        return;
      }
      feedback.textContent = "";
      fecharModalPdv(false);
      restaurarFocoPrincipalPdv(true);
    }

    function atualizarClienteAtual() {
      if (!clientSelect || !clientCurrent) return;
      clientCurrent.textContent = clientSelect.value ? clientSelect.selectedOptions[0].textContent.trim() : "Cliente avulso";
    }

    function selecionarClientePrincipal(id, name) {
      if (!clientSelect) return;
      if (id && !Array.prototype.some.call(clientSelect.options, function (option) { return option.value === String(id); })) {
        clientSelect.add(new Option(name, String(id)));
      }
      clientSelect.value = id ? String(id) : "";
      clientSelect.dispatchEvent(new Event("change", { bubbles: true }));
      fecharModalPdv(false);
      restaurarFocoPrincipalPdv(true);
    }

    function informarErroCadastroCliente(message) {
      if (!clientCreateForm) return;
      clientCreateForm.querySelectorAll("[data-client-create-error]").forEach(function (error) { error.textContent = message; });
    }

    function limparErrosCamposCliente() {
      clientCreateForm.querySelectorAll(".pdv-client-field-error").forEach(function (error) { error.remove(); });
      clientCreateForm.querySelectorAll("[aria-invalid]").forEach(function (field) { field.removeAttribute("aria-invalid"); });
    }

    function marcarErroCampoCliente(name, message) {
      var field = clientCreateForm.elements[name];
      var label = field && field.closest(".form-field");
      if (!label) return null;
      field.setAttribute("aria-invalid", "true");
      var error = document.createElement("small");
      error.className = "pdv-client-field-error";
      error.textContent = message;
      label.appendChild(error);
      return field;
    }

    function validarEnderecoCliente() {
      var names = ["logradouro", "numero", "bairro", "codigo_municipio_ibge", "municipio", "uf", "cep"];
      var started = names.some(function (name) { return clientCreateForm.elements[name].value.trim(); });
      if (!started) return true;
      var firstMissing = null;
      names.forEach(function (name) {
        var field = clientCreateForm.elements[name];
        if (!field.value.trim()) {
          var marked = marcarErroCampoCliente(name, "Complete o endereço fiscal estruturado.");
          if (!firstMissing) firstMissing = marked;
        }
      });
      if (firstMissing) {
        informarErroCadastroCliente("Complete os campos destacados do endereço ou deixe o endereço inteiro vazio.");
        firstMissing.focus();
        return false;
      }
      return true;
    }

    function mostrarEtapaCadastroCliente(stage) {
      if (!clientCreateForm) return;
      clientCreateStage = stage;
      clientCreateForm.querySelectorAll("[data-client-create-step]").forEach(function (section) {
        section.hidden = Number(section.dataset.clientCreateStep) !== stage;
      });
      clientCreateForm.querySelectorAll("[data-client-create-footer]").forEach(function (footer) {
        footer.hidden = Number(footer.dataset.clientCreateFooter) !== stage;
      });
      informarErroCadastroCliente("");
      var target = stage === 0 ? clientCreateForm.querySelector('input[name="nome"]') : clientCreateForm.querySelector('input[name="cep"]');
      if (target) target.focus();
    }

    function avancarCadastroCliente() {
      var step = clientCreateForm && clientCreateForm.querySelector('[data-client-create-step="0"]');
      if (!step) return;
      var fields = Array.prototype.slice.call(step.querySelectorAll("input, select"));
      var empresa = clientCreateForm.elements.empresa;
      if (empresa && empresa.offsetParent !== null) fields.unshift(empresa);
      var invalid = fields.find(function (field) { return !field.checkValidity(); });
      if (invalid) { invalid.reportValidity(); return; }
      mostrarEtapaCadastroCliente(1);
    }

    function mostrarCadastroCliente(show) {
      clientSelectStep.hidden = show;
      clientCreateForm.hidden = !show;
      if (show) mostrarEtapaCadastroCliente(0);
      else if (clientSearch) clientSearch.focus();
    }

    function buscarClientesPdv() {
      if (!clientSearch || !clientResults) return;
      if (clientSearchError) clientSearchError.textContent = "";
      var url = clientModal.querySelector("[data-client-search-url]").dataset.clientSearchUrl;
      var sequence = ++clientSearchSequence;
      fetch(url + "?q=" + encodeURIComponent(clientSearch.value.trim()), { credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error(); return response.json(); })
        .then(function (payload) {
          if (sequence !== clientSearchSequence || clientSelectStep.hidden) return;
          clientResults.replaceChildren();
          (payload.results || []).forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "pdv-modal-row";
            button.dataset.pdvSelectClient = String(item.id);
            button.dataset.clientName = item.nome;
            button.textContent = [item.nome, item.telefone || item.cpf_cnpj].filter(Boolean).join(" · ");
            clientResults.appendChild(button);
          });
          var casual = document.createElement("button");
          casual.type = "button";
          casual.className = "pdv-modal-row";
          casual.dataset.pdvSelectClient = "";
          casual.textContent = "Cliente avulso";
          clientResults.appendChild(casual);
          selecionarPrimeiraLinhaVisivelModal(clientModal, false);
        }).catch(function () { if (sequence === clientSearchSequence && clientSearchError) clientSearchError.textContent = "Não foi possível consultar clientes."; });
    }

    function focarPrimeiraFormaPagamento() {
      var firstSelect = paymentModal && paymentModal.querySelector(".pdv-payment-row select");
      if (firstSelect) firstSelect.focus();
    }

    function selecionarDecisaoCpf(indice) {
      var input = cpfDecisionInputs && cpfDecisionInputs[indice];
      if (!input) return false;
      input.checked = true;
      input.focus();
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }

    function avancarDocumentoConsumidor() {
      var decisao = decisaoCpfNaNota();
      var valido = decisao === "CNPJ"
        ? cnpjValidoNoPdv(documentInput && documentInput.value)
        : cpfValidoNoPdv(documentInput && documentInput.value);
      if (!valido) {
        informarPagamentoFeedback(decisao === "CNPJ" ? "Informe um CNPJ válido." : "Informe um CPF válido com 11 números.");
        if (documentInput) { documentInput.focus(); documentInput.select(); }
        return false;
      }
      informarPagamentoFeedback("");
      focarPrimeiraFormaPagamento();
      return true;
    }

    function abrirPagamentos(mode) {
      if (mode === "delivery") {
        if (!window.pdvSaleCheckout || !window.pdvSaleCheckout.openDelivery) return false;
        return window.pdvSaleCheckout.openDelivery({
          form: deliveryForm,
          total: deliveryQuote && deliveryQuote.total,
          onCancel: function () {
            var modal = document.getElementById("pdv-modal-delivery");
            modal.classList.add("is-open");
            modal.setAttribute("aria-hidden", "false");
            mostrarEtapaEntrega(2);
            if (deliveryContinue) deliveryContinue.focus();
          }
        });
      }
      if (mode !== "delivery" && window.pdvSaleCheckout) {
        window.pdvSaleCheckout.open();
        return;
      }
      if (!paymentModal) return;
      checkoutMode = mode === "delivery" ? "delivery" : "sale";
      focusBeforePayment = document.activeElement;
      paymentModal.classList.add("is-open");
      paymentModal.setAttribute("aria-hidden", "false");
      if (cpfDocumentPanel) cpfDocumentPanel.hidden = checkoutMode === "delivery";
      if (descontoInput) descontoInput.disabled = checkoutMode === "delivery";
      var discountPanel = paymentModal.querySelector(".pdv-modal-discount");
      if (discountPanel) discountPanel.hidden = checkoutMode === "delivery";
      if (confirmPaymentButton) confirmPaymentButton.textContent = checkoutMode === "delivery" ? "Receber e criar pedido" : "Receber agora e finalizar";
      atualizarAutorizacaoDesconto();
      atualizarCpfNaNota();
      atualizarResumoPdv();
      if (checkoutMode === "delivery") { focarPrimeiraFormaPagamento(); return; }
      var cpfEscolhido = decisaoCpfNaNota();
      var firstCpfDecision = cpfDecisionInputs && cpfDecisionInputs[0];
      if (!cpfEscolhido && firstCpfDecision) {
        firstCpfDecision.focus();
        return;
      }
      if (cpfEscolhido !== "NAO" && documentInput && !documentInput.value.trim()) {
        documentInput.focus();
        return;
      }
      focarPrimeiraFormaPagamento();
    }

    function informarPagamentoFeedback(texto) {
      if (paymentFeedback) paymentFeedback.textContent = texto || "";
    }

    function atualizarCapacidadeDocumentoPinpad() {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.tefCapabilities;
      if (!captureDocumentButton) return;
      captureDocumentButton.hidden = true;
      if (!bridge) return;
      Promise.resolve(bridge()).then(function (resultado) {
        captureDocumentButton.hidden = !(resultado && resultado.captura_documento_consumidor);
      }).catch(function () { captureDocumentButton.hidden = true; });
    }

    function capturarDocumentoPinpad() {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.captureConsumerDocument;
      if (!bridge || !captureDocumentButton || captureDocumentButton.hidden) {
        informarPagamentoFeedback("Captura pelo pinpad indisponivel. Digite o documento manualmente.");
        if (documentInput) documentInput.focus();
        return;
      }
      captureDocumentButton.disabled = true;
      var tipoSolicitado = decisaoCpfNaNota() === "CNPJ" ? "CNPJ" : "CPF";
      informarPagamentoFeedback("Aguardando " + tipoSolicitado + " no pinpad...");
      Promise.resolve(bridge({ tipo: tipoSolicitado })).then(function (resultado) {
        if (resultado && resultado.status === "ok") {
          if (resultado.tipo && resultado.tipo !== tipoSolicitado) {
            informarPagamentoFeedback("O documento retornado não corresponde à opção escolhida.");
            if (documentInput) { documentInput.value = ""; documentInput.focus(); }
            return;
          }
          if (documentTypeInput) documentTypeInput.value = tipoSolicitado;
          if (documentInput) { documentInput.value = resultado.documento; documentInput.focus(); documentInput.select(); }
          informarPagamentoFeedback("Documento recebido do pinpad.");
          return;
        }
        informarPagamentoFeedback((resultado && resultado.mensagem) || (resultado && resultado.status === "cancelado" ? "Captura cancelada no pinpad." : "Falha no pinpad. Digite o documento manualmente."));
        if (documentInput) documentInput.focus();
      }).catch(function () {
        informarPagamentoFeedback("Falha na comunicação com o pinpad. Digite o documento manualmente.");
        if (documentInput) documentInput.focus();
      }).finally(function () { captureDocumentButton.disabled = false; });
    }

    function informarBalanca(texto, tipo) {
      if (!scaleFeedback) return;
      scaleFeedback.textContent = texto || "";
      scaleFeedback.classList.remove("is-ok", "is-error");
      if (tipo) scaleFeedback.classList.add(tipo);
    }

    function ponteBalanca() {
      if (!window.SupermercadoDesktop) return null;
      return window.SupermercadoDesktop.readScale || window.SupermercadoDesktop.ler_peso_balanca || null;
    }

    function aplicarPesoLido(resultado) {
      if (!quantidadeInput || !resultado) return;
      if (resultado.status === "ok" && resultado.peso) {
        quantidadeInput.value = String(resultado.peso).replace(",", ".");
        quantidadeInput.focus();
        quantidadeInput.select();
        informarBalanca("Peso lido: " + String(resultado.peso).replace(".", ",") + " " + (resultado.unidade || "KG") + ".", "is-ok");
        return;
      }
      var mensagem = resultado.mensagem || "Não foi possível ler a balança. Digite a quantidade manualmente.";
      informarBalanca(mensagem, resultado.status === "manual" ? "" : "is-error");
      quantidadeInput.focus();
      quantidadeInput.select();
    }

    function lerPesoBalancaPdv() {
      var bridge = ponteBalanca();
      if (!bridge) {
        informarBalanca("Balanca automática disponível somente no app desktop. Digite a quantidade manualmente.", "is-error");
        if (quantidadeInput) {
          quantidadeInput.focus();
          quantidadeInput.select();
        }
        return;
      }
      if (scaleButton) scaleButton.disabled = true;
      informarBalanca("Lendo balança...", "");
      Promise.resolve(bridge.call(window.SupermercadoDesktop))
        .then(aplicarPesoLido)
        .catch(function (erro) {
          informarBalanca("Falha ao ler balança: " + erro.message, "is-error");
          if (quantidadeInput) quantidadeInput.focus();
        })
        .finally(function () {
          if (scaleButton) scaleButton.disabled = false;
        });
    }

    function pagamentoCompleto() {
      return totalPagamentosLancados() + 0.005 >= totalFinalAtual();
    }

    function valorRestantePagamento() {
      return Math.max(totalFinalAtual() - totalPagamentosLancados(), 0);
    }

    function linhaPagamentoAtual() {
      if (!paymentRows) return null;
      var linhas = paymentRows.querySelectorAll(".pdv-payment-row");
      var linhaAtiva = document.activeElement && document.activeElement.closest && document.activeElement.closest(".pdv-payment-row");
      if (linhaAtiva && paymentRows.contains(linhaAtiva)) return linhaAtiva;
      for (var indice = 0; indice < linhas.length; indice += 1) {
        var selectLinha = linhas[indice].querySelector("select");
        var inputLinha = linhas[indice].querySelector("input[name='pagamento_valor']");
        if (selectLinha && inputLinha && !selectLinha.value && decimalFromInput(inputLinha.value) <= 0) return linhas[indice];
      }
      return linhas[linhas.length - 1] || null;
    }

    function prepararLinhaParaPagamento() {
      if (!paymentRows) return null;
      atualizarResumoPdv();
      var restante = valorRestantePagamento();
      if (restante <= 0.005) {
        informarPagamentoFeedback("Pagamento ja cobre o total. Para dividir, reduza o valor lancado ou remova uma forma.");
        return null;
      }
      var linha = linhaPagamentoAtual();
      var select = linha && linha.querySelector("select");
      var input = linha && linha.querySelector("input[name='pagamento_valor']");
      if (linha && select && input && (!select.value || decimalFromInput(input.value) <= 0)) return linha;
      return adicionarLinhaPagamento({ somenteSeRestante: true });
    }

    function validarFinalizacaoVendaPdv() {
      if (!finishForm) return false;
      if (checkoutMode === "delivery") {
        var eletronicopendente = paymentRows && Array.prototype.some.call(
          paymentRows.querySelectorAll(".pdv-payment-row"), function (row) {
            var select = row.querySelector("select[name='pagamento_forma']");
            var option = select && select.selectedOptions[0];
            var tipo = option && option.dataset.paymentType;
            var eletronic = ["PIX", "CARTAO", "DEBITO", "CREDITO", "VALE_ALIMENTACAO", "VALE_REFEICAO"].indexOf(tipo) !== -1;
            var status = row.querySelector("input[name='pagamento_status']");
            return eletronic && (!status || status.value !== "CONFIRMADO");
          }
        );
        if (eletronicopendente) {
          informarPagamentoFeedback("Pagamento eletrônico da entrega exige confirmação confiável antes de criar o pedido.");
          return false;
        }
        if (!deliveryQuote || !pagamentoCompleto()) {
          informarPagamentoFeedback("Complete o pagamento do total do pedido, incluindo o frete.");
          return false;
        }
        informarPagamentoFeedback("");
        return true;
      }
      var decisaoCpf = decisaoCpfNaNota();
      if (!decisaoCpf) {
        informarPagamentoFeedback("Responda se o consumidor deseja CPF ou CNPJ na nota.");
        if (cpfDecisionInputs && cpfDecisionInputs[0]) cpfDecisionInputs[0].focus();
        return false;
      }
      if ((decisaoCpf === "SIM" || decisaoCpf === "CPF") && !cpfValidoNoPdv(documentInput && documentInput.value)) {
        informarPagamentoFeedback("Informe um CPF válido com 11 números.");
        if (documentInput) { documentInput.focus(); documentInput.select(); }
        return false;
      }
      if (decisaoCpf === "CNPJ" && !cnpjValidoNoPdv(documentInput && documentInput.value)) {
        informarPagamentoFeedback("Informe um CNPJ válido.");
        if (documentInput) { documentInput.focus(); documentInput.select(); }
        return false;
      }
      var desconto = Math.max(decimalFromInput(descontoInput && descontoInput.value), 0);
      var subtotal = Math.max(decimalFromInput(resumo && resumo.dataset.total), 0);
      if (desconto > subtotal) {
        informarPagamentoFeedback("O desconto não pode ser maior que o total da venda.");
        if (descontoInput) { descontoInput.focus(); descontoInput.select(); }
        return false;
      }
      if (desconto > 0 && (!discountSupervisor || !discountSupervisor.value.trim() || !discountPassword || !discountPassword.value)) {
        informarPagamentoFeedback("Informe usuário e senha do supervisor ou administrador para autorizar o desconto.");
        if (discountSupervisor && !discountSupervisor.value.trim()) discountSupervisor.focus();
        else if (discountPassword) discountPassword.focus();
        return false;
      }
      if (!pagamentoCompleto()) {
        informarPagamentoFeedback("Informe uma forma e complete o valor restante.");
        var primeiroSelect = paymentModal && paymentModal.querySelector("select");
        if (primeiroSelect) primeiroSelect.focus();
        return false;
      }
      informarPagamentoFeedback("");
      return true;
    }

    function prepararPagamentoNoCaixaParaEntrega(pagamentoNoCaixa) {
      if (!deliveryForm) return;
      deliveryForm.querySelectorAll("[data-pdv-delivery-payment]").forEach(function (field) { field.remove(); });
      if (!pagamentoNoCaixa) return;
      var createHidden = function (name, value) {
        var field = document.createElement("input");
        field.type = "hidden";
        field.name = name;
        field.value = value || "";
        field.setAttribute("data-pdv-delivery-payment", "1");
        deliveryForm.appendChild(field);
      };
      createHidden("pagamento_no_caixa", "1");
      var caixa = finishForm && finishForm.querySelector('input[name="caixa"]');
      if (caixa) createHidden("caixa", caixa.value);
      if (paymentRows) {
        paymentRows.querySelectorAll(".pdv-payment-row").forEach(function (row) {
          row.querySelectorAll("select[name], input[name]").forEach(function (field) {
            createHidden(field.name, field.value);
          });
        });
      }
    }

    function atualizarCotacaoEntrega() {
      if (!deliveryForm) return Promise.reject(new Error("Formulário de entrega indisponível."));
      var feedback = document.getElementById("pdv-delivery-quote-feedback");
      var params = new URLSearchParams();
      ["distancia_entrega_km", "bairro_entrega"].forEach(function (name) {
        var field = deliveryForm.elements[name];
        if (field) params.set(name, field.value);
      });
      if (feedback) feedback.textContent = "Calculando frete...";
      return fetch(deliveryForm.dataset.quoteUrl + "?" + params.toString(), { credentials: "same-origin" })
        .then(function (response) { return response.json().then(function (data) { if (!response.ok) throw new Error(data.erro || "Falha ao calcular o frete."); return data; }); })
        .then(function (data) {
          deliveryQuote = data;
          document.getElementById("pdv-delivery-subtotal").textContent = formatMoney(decimalFromInput(data.subtotal));
          document.getElementById("pdv-delivery-frete").textContent = formatMoney(decimalFromInput(data.frete));
          document.getElementById("pdv-delivery-total").textContent = formatMoney(decimalFromInput(data.total));
          if (feedback) feedback.textContent = data.regra || "";
          return data;
        }).catch(function (error) {
          deliveryQuote = null;
          document.getElementById("pdv-delivery-frete").textContent = "A calcular";
          document.getElementById("pdv-delivery-total").textContent = "A calcular";
          if (feedback) feedback.textContent = error.message;
          throw error;
        });
    }

    function continuarEntrega() {
      if (!deliveryForm || deliveryContinuing) return;
      if (deliveryStage === 0) {
        if (!deliveryClientSearch.value.trim()) {
          deliveryClientSearch.focus();
          deliveryClientSearch.setCustomValidity("Informe o cliente da entrega.");
          deliveryClientSearch.reportValidity();
          deliveryClientSearch.setCustomValidity("");
          return;
        }
        mostrarEtapaEntrega(1);
        return;
      }
      if (deliveryStage === 1) {
        var savedMode = deliveryForm.querySelector('input[name="delivery_address_mode"][value="saved"]');
        if (!savedMode || !savedMode.checked) {
          var addressFields = ["entrega_cep", "entrega_logradouro", "entrega_numero", "entrega_bairro", "entrega_municipio", "entrega_uf"];
          for (var i = 0; i < addressFields.length; i += 1) {
            var field = deliveryForm.elements[addressFields[i]];
            if (field && !field.value.trim()) {
              field.focus(); field.setCustomValidity("Informe este campo do endereço de entrega."); field.reportValidity(); field.setCustomValidity("");
              return;
            }
          }
        } else if (!deliverySavedAddress.trim()) {
          savedMode.focus();
          return;
        }
        mostrarEtapaEntrega(2);
        atualizarCotacaoEntrega().catch(function () {});
        return;
      }
      if (!deliveryForm.reportValidity()) return;
      deliveryContinuing = true;
      deliveryContinue.disabled = true;
      atualizarCotacaoEntrega().then(function () {
        var modo = deliveryForm.querySelector('input[name="modo_pagamento"]:checked');
        if (modo && modo.value === "PAGAR_AGORA") {
          fecharModalPdv(false);
          if (!abrirPagamentos("delivery")) {
            var modal = document.getElementById("pdv-modal-delivery");
            modal.classList.add("is-open");
            modal.setAttribute("aria-hidden", "false");
            mostrarEtapaEntrega(2);
            var feedback = document.getElementById("pdv-delivery-quote-feedback");
            if (feedback) feedback.textContent = "Não foi possível abrir o pagamento. Confira o total e o caixa.";
          }
          deliveryContinuing = false;
          deliveryContinue.disabled = false;
        } else {
          prepararPagamentoNoCaixaParaEntrega(false);
          deliveryForm.requestSubmit();
        }
      }).catch(function () {
        deliveryContinuing = false;
        deliveryContinue.disabled = false;
      });
    }

    function mostrarEtapaEntrega(stage) {
      deliveryStage = stage;
      document.querySelectorAll("#pdv-modal-delivery [data-delivery-stage]").forEach(function (section) {
        section.hidden = Number(section.dataset.deliveryStage) !== stage;
      });
      if (deliveryBack) deliveryBack.hidden = stage === 0;
      if (deliveryContinue) {
        deliveryContinue.innerHTML = stage === 2 ? 'Confirmar <kbd>Ctrl+Enter</kbd>' : 'Continuar <kbd>Ctrl+Enter</kbd>';
      }
      var focus = stage === 0 ? deliveryClientSearch : stage === 1 ? deliveryForm.querySelector('input[name="delivery_address_mode"]:checked') : deliveryForm.querySelector('input[name="modo_pagamento"]:checked');
      if (focus && !focus.closest("[hidden]")) focus.focus();
      else if (deliveryContinue) deliveryContinue.focus();
    }

    function atualizarModoEnderecoEntrega() {
      if (!deliveryForm) return;
      var savedMode = deliveryForm.querySelector('input[name="delivery_address_mode"][value="saved"]');
      var useSaved = savedMode && savedMode.checked && deliverySavedAddress.trim();
      var fields = document.getElementById("pdv-delivery-address-fields");
      if (fields) fields.hidden = Boolean(useSaved);
      if (useSaved) {
        deliveryForm.elements.endereco_entrega.value = deliverySavedAddress;
        deliveryForm.elements.bairro_entrega.value = deliverySavedBairro;
      } else if (savedMode && deliverySavedAddress.trim()) {
        if (deliveryForm.elements.endereco_entrega.value === deliverySavedAddress) deliveryForm.elements.endereco_entrega.value = "";
        deliveryForm.elements.bairro_entrega.value = deliveryForm.elements.entrega_bairro.value.trim();
      } else {
        deliveryForm.elements.bairro_entrega.value = deliveryForm.elements.entrega_bairro.value.trim();
      }
    }

    function finalizarVendaPdv() {
      if (finishForm && finishForm.dataset.submitting === "1") {
        informarPagamentoFeedback("Venda em processamento. Aguarde a confirmação.");
        return;
      }
      if (!validarFinalizacaoVendaPdv()) return;
      if (checkoutMode === "delivery") {
        prepararPagamentoNoCaixaParaEntrega(true);
        if (deliveryForm) deliveryForm.requestSubmit();
      } else if (finishForm) finishForm.requestSubmit();
    }

    function avancarPagamentoComEnter() {
      var active = document.activeElement;
      if (!active) return false;
      if (active === documentInput) return avancarDocumentoConsumidor();
      if (active === descontoInput) {
        atualizarAutorizacaoDesconto();
        atualizarResumoPdv();
        if (decimalFromInput(descontoInput.value) > 0 && discountAuthorization) {
          var primeiraCredencial = discountAuthorization.querySelector(
            "input[name='supervisor_credencial'], input[name='supervisor_usuario'], input[name='supervisor_pin'], input[name='supervisor_senha']"
          );
          if (primeiraCredencial) primeiraCredencial.focus();
        } else {
          focarPrimeiraFormaPagamento();
        }
        return true;
      }
      if (active === recebidoInput || active.name === "vencimento_financeiro") {
        focarPrimeiraFormaPagamento();
        return true;
      }
      if (discountAuthorization && discountAuthorization.contains(active)) {
        var proximoPorNome = {
          supervisor_credencial: "supervisor_pin",
          supervisor_usuario: "supervisor_senha",
        }[active.name];
        var proximo = proximoPorNome && discountAuthorization.querySelector("input[name='" + proximoPorNome + "']");
        if (proximo && !proximo.disabled) proximo.focus();
        else focarPrimeiraFormaPagamento();
        return true;
      }
      var paymentRow = active.closest && active.closest(".pdv-payment-row");
      if (paymentRow) {
        var select = paymentRow.querySelector("select");
        var input = paymentRow.querySelector("input[name='pagamento_valor']");
        if (active === select) {
          if (!select.value) return false;
          input.focus();
          input.select();
          return true;
        }
        if (active === input) {
          if (decimalFromInput(input.value) <= 0) {
            informarPagamentoFeedback("Informe um valor maior que zero.");
            input.focus();
            input.select();
            return true;
          }
          atualizarResumoPdv();
          if (pagamentoCompleto()) finalizarVendaPdv();
          else adicionarLinhaPagamento({ somenteSeRestante: true });
          return true;
        }
      }
      if (active === confirmPaymentButton) {
        finalizarVendaPdv();
        return true;
      }
      if (active.matches && active.matches("button, a")) return false;
      if (pagamentoCompleto()) finalizarVendaPdv();
      else focarPrimeiraFormaPagamento();
      return true;
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
        F3: ["crédito", "crédito", "débito", "débito", "cartao", "cartão", "pos"],
        F4: ["troca", "outro", "vale"],
      }[atalho] || [];
      var linha = prepararLinhaParaPagamento();
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
      input.value = valorRestantePagamento().toFixed(2);
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
      if (valorRestantePagamento() <= 0.005) {
        informarPagamentoFeedback("Pagamento ja cobre o total. Para dividir, reduza o valor lancado ou remova uma forma.");
        return;
      }
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
      var tipoTef = String(tipo || "").trim().toUpperCase();
      var tiposAceitos = {
        CREDITO: ["CREDITO", "CARTAO_CREDITO"],
        DEBITO: ["DEBITO", "CARTAO_DEBITO"],
        PIX: ["PIX"],
        VALE_ALIMENTACAO: ["VALE_ALIMENTACAO"],
        VALE_REFEICAO: ["VALE_REFEICAO"],
      }[tipoTef] || [];
      var linha = prepararLinhaParaPagamento();
      var select = linha && linha.querySelector("select");
      var input = linha && linha.querySelector("input[name='pagamento_valor']");
      if (!select || !input) return;
      var opcao = Array.prototype.find.call(select.options, function (item) {
        return tiposAceitos.indexOf(String(item.dataset.paymentType || "").toUpperCase()) !== -1;
      });
      if (!opcao) {
        informarPagamentoFeedback("Forma eletrônica não cadastrada para " + tipoTef.replaceAll("_", " ") + ".");
        select.focus();
        return;
      }
      select.value = opcao.value;
      input.value = valorRestantePagamento().toFixed(2);
      fecharEscolhaEletronica();
      atualizarResumoPdv();
      processarPagamentoEletronico(linha, tipoTef);
    }

    function limparAutorizacaoPagamento(row, preservarRequisicao) {
      if (!row) return;
      ["pagamento_status", "pagamento_transacao_externa_id", "pagamento_nsu", "pagamento_codigo_autorizacao", "pagamento_tipo_integracao", "pagamento_cnpj_instituicao", "pagamento_bandeira_cartao", "pagamento_cnpj_beneficiario", "pagamento_identificador_terminal", "pagamento_mensagem_processadora"].forEach(function (nome) {
        var campo = row.querySelector("input[name='" + nome + "']");
        if (campo) campo.value = "";
      });
      row.classList.remove("is-authorized");
      if (!preservarRequisicao) {
        delete row.dataset.tefRequestKey;
        delete row.dataset.tefRequestSignature;
      }
    }

    function aplicarAutorizacaoPagamento(row, resultado) {
      var mapa = {
        pagamento_status: "CONFIRMADO",
        pagamento_transacao_externa_id: resultado.transacao_externa_id || "",
        pagamento_nsu: resultado.nsu || "",
        pagamento_codigo_autorizacao: resultado.codigo_autorizacao || "",
        pagamento_tipo_integracao: resultado.tipo_integracao || "",
        pagamento_cnpj_instituicao: resultado.cnpj_instituicao_pagamento || "",
        pagamento_bandeira_cartao: resultado.bandeira_cartao || "",
        pagamento_cnpj_beneficiario: resultado.cnpj_beneficiario_pagamento || "",
        pagamento_identificador_terminal: resultado.identificador_terminal_pagamento || "",
        pagamento_mensagem_processadora: resultado.mensagem_processadora || "",
      };
      Object.keys(mapa).forEach(function (nome) {
        var campo = row.querySelector("input[name='" + nome + "']");
        if (campo) campo.value = mapa[nome];
      });
      row.classList.add("is-authorized");
    }

    function ocultarPixPanel() {
      pixPollingToken += 1;
      if (!pixPanel) return;
      pixPanel.hidden = true;
      if (pixQrCode) pixQrCode.removeAttribute("src");
      if (pixSimulation) pixSimulation.hidden = true;
    }

    function exibirPixPanel(resultado) {
      if (!pixPanel || !resultado) return;
      pixPanel.hidden = false;
      if (pixQrCode && resultado.pix_qr_code_image) pixQrCode.src = resultado.pix_qr_code_image;
      if (pixValue) pixValue.textContent = formatMoney(decimalFromInput(resultado.valor));
      if (pixMessage) pixMessage.textContent = resultado.mensagem_processadora || "Aguardando confirmação do PIX...";
      if (pixSimulation) pixSimulation.hidden = !resultado.pix_simulado;
    }

    function aguardarConfirmacaoPix(resultadoInicial, requestKey) {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.checkPayment;
      if (!bridge) return Promise.reject(new Error("Consulta PIX indisponivel neste aplicativo desktop."));
      exibirPixPanel(resultadoInicial);
      var token = ++pixPollingToken;
      var tentativas = 0;
      return new Promise(function (resolve, reject) {
        function consultar() {
          if (token !== pixPollingToken) {
            reject(new Error("Consulta PIX cancelada pelo operador."));
            return;
          }
          tentativas += 1;
          if (tentativas > 120) {
            reject(new Error("Tempo limite aguardando a confirmação do PIX."));
            return;
          }
          Promise.resolve(bridge.call(window.SupermercadoDesktop, {
            transacao_externa_id: resultadoInicial.transacao_externa_id,
            idempotency_key: requestKey,
          }))
            .then(function (resultado) {
              if (resultado && resultado.status === "ok" && resultado.aprovado) {
                resolve(resultado);
                return;
              }
              if (!resultado || resultado.status === "erro" || resultado.status === "recusado") {
                reject(new Error((resultado && resultado.mensagem) || "PIX recusado ou não confirmado."));
                return;
              }
              exibirPixPanel(resultado);
              window.setTimeout(consultar, 1000);
            })
            .catch(reject);
        }
        window.setTimeout(consultar, 800);
      });
    }

    function processarPagamentoEletronico(row, tipo) {
      var tipoTef = String(tipo || "").trim().toUpperCase();
      if (!window.pdvServerVerifierEnabled) {
        informarPagamentoFeedback("Pagamento eletronico indisponivel ate homologacao do verificador no servidor. Nenhuma cobranca foi iniciada.");
        return;
      }
      if (checkoutMode === "delivery") {
        informarPagamentoFeedback("TEF/PIX de entrega indisponível até configurar a confirmação confiável no servidor. Use dinheiro agora ou pagamento na entrega.");
        return;
      }
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.processPayment;
      var input = row && row.querySelector("input[name='pagamento_valor']");
      var select = row && row.querySelector("select");
      if (!row || !input || !select) return;
      if (row.dataset.tefProcessing === "1") {
        informarPagamentoFeedback("Pagamento eletrônico em processamento. Aguarde a resposta da maquininha.");
        return;
      }
      limparAutorizacaoPagamento(row, true);
      ocultarPixPanel();
      if (!bridge) {
        informarPagamentoFeedback("Maquininha disponivel somente no app desktop. Configure o terminal ou use uma forma manual.");
        select.focus();
        return;
      }
      var valor = Math.max(decimalFromInput(input.value), 0).toFixed(2);
      if (valor <= 0) {
        informarPagamentoFeedback("Informe o valor antes de chamar a maquininha.");
        input.focus();
        return;
      }
      var assinaturaRequisicao = tipoTef + "|" + valor;
      if (!row.dataset.tefRequestKey || row.dataset.tefRequestSignature !== assinaturaRequisicao) {
        row.dataset.tefRequestKey = window.crypto && window.crypto.randomUUID
          ? window.crypto.randomUUID()
          : "pdv-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        row.dataset.tefRequestSignature = assinaturaRequisicao;
      }
      row.dataset.tefProcessing = "1";
      row.setAttribute("aria-busy", "true");
      select.disabled = true;
      input.readOnly = true;
      informarPagamentoFeedback(tipoTef === "PIX" ? "Processando PIX: gerando QR Code..." : "Processando pagamento na maquininha...");
      Promise.resolve(bridge.call(window.SupermercadoDesktop, {
        tipo: tipoTef,
        valor: valor,
        idempotency_key: row.dataset.tefRequestKey,
      }))
        .then(function (resultado) {
          if (tipoTef === "PIX" && resultado && resultado.status === "pending") {
            informarPagamentoFeedback("QR Code PIX disponível. Aguardando pagamento do cliente...");
            return aguardarConfirmacaoPix(resultado, row.dataset.tefRequestKey);
          }
          return resultado;
        })
        .then(function (resultado) {
          if (!resultado || resultado.status !== "ok" || !resultado.aprovado) {
            throw new Error((resultado && resultado.mensagem) || "Pagamento recusado ou não confirmado.");
          }
          aplicarAutorizacaoPagamento(row, resultado);
          ocultarPixPanel();
          if (resultado.simulado) {
            informarPagamentoFeedback("SIMULACAO TEF: " + tipoTef.replaceAll("_", " ") + " aprovado para teste. Nenhuma cobranca foi enviada.");
          } else {
            informarPagamentoFeedback("Pagamento " + tipoTef.replaceAll("_", " ") + " aprovado. Aut. " + resultado.codigo_autorizacao + ".");
          }
        })
        .catch(function (erro) {
          limparAutorizacaoPagamento(row, true);
          ocultarPixPanel();
          informarPagamentoFeedback("Não foi possível confirmar na maquininha: " + erro.message);
        })
        .finally(function () {
          delete row.dataset.tefProcessing;
          row.removeAttribute("aria-busy");
          select.disabled = false;
          input.readOnly = false;
          select.focus();
        });
    }
    function fecharPagamentos() {
      if (!paymentModal) return;
      var voltarEntrega = checkoutMode === "delivery";
      fecharEscolhaEletronica();
      ocultarPixPanel();
      paymentModal.classList.remove("is-open");
      paymentModal.setAttribute("aria-hidden", "true");
      if (voltarEntrega) {
        abrirModalPdv("delivery");
        if (deliveryContinue) deliveryContinue.focus();
      } else restaurarFocoPrincipalPdv(true);
    }

    function modalAberto() {
      return document.querySelector(".pdv-modal.is-open");
    }

    function abrirModalPdv(name) {
      var modal = document.getElementById("pdv-modal-" + name);
      if (!modal) return;
      if (name === "dav" && clientSelect && modal.dataset.preserveBound !== "1") {
        var davClient = modal.querySelector('select[name="cliente"]');
        if (davClient) davClient.value = clientSelect.value || "";
      }
      if (name === "delivery" && paymentRows && paymentRows.querySelector(".pdv-payment-row.is-authorized")) {
        window.alert("Há pagamento eletrônico autorizado para a venda presencial. Conclua ou trate essa operação antes de criar uma entrega.");
        return;
      }
      if (name === "delivery") {
        deliveryContinuing = false;
        if (deliveryContinue) deliveryContinue.disabled = false;
        mostrarEtapaEntrega(0);
        if (clientSelect && clientSelect.value && deliveryClientId && !deliveryClientId.value) {
          deliveryClientId.value = clientSelect.value;
          deliveryClientSearch.value = clientSelect.selectedOptions[0].textContent.trim();
          var selectedId = clientSelect.value;
          var clientUrl = deliveryClientField && deliveryClientField.dataset.clientSearchUrl;
          if (clientUrl) fetch(clientUrl + "?q=" + encodeURIComponent(deliveryClientSearch.value), { credentials: "same-origin" })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
              var selected = (payload.results || []).find(function (item) { return String(item.id) === selectedId; });
              if (selected && modalAberto() === modal && deliveryStage === 0 && deliveryClientId.value === selectedId) selecionarClienteEntrega(selected);
            }).catch(function () {});
        }
        deliveryQuote = null;
        var subtotalEntrega = document.getElementById("pdv-delivery-subtotal");
        var freteEntrega = document.getElementById("pdv-delivery-frete");
        var totalEntrega = document.getElementById("pdv-delivery-total");
        if (subtotalEntrega) subtotalEntrega.textContent = formatMoney(decimalFromInput(resumo && resumo.dataset.total));
        if (freteEntrega) freteEntrega.textContent = "A calcular";
        if (totalEntrega) totalEntrega.textContent = "A calcular";
      }
      focusBeforeModal = document.activeElement;
      fecharModalPdv(false);
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      var input = modal.querySelector("[data-pdv-modal-filter]");
      if (input) {
        input.value = "";
        filtrarModal(input);
        input.focus();
      } else {
        aplicarPaginacaoModal(modal);
        var focusTarget = modal.querySelector("[data-pdv-modal-autofocus]") || ((name === "open-cash" || name === "dav") ? modal.querySelector("select, input:not([type='hidden'])") : null) || modal.querySelector("input:not([type='hidden']), select, textarea, button");
        if (focusTarget) focusTarget.focus();
      }
      var preservedRow = name === "refunds" && modal.querySelector(".pdv-modal-row.is-selected");
      if (preservedRow && preservedRow.style.display !== "none") selecionarLinhaModal(modal, preservedRow, false);
      else selecionarPrimeiraLinhaVisivelModal(modal, false);
    }

    function fecharModalPdv(restoreFocus) {
      pdvModals.forEach(function (modal) {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
      });
      if (restoreFocus !== false && focusBeforeModal && document.contains(focusBeforeModal)) focusBeforeModal.focus();
    }

    function abrirConferenciaEntrega(deliveryId) {
      var detailModal = document.getElementById("pdv-modal-delivery-detail");
      if (!detailModal || !deliveryId) return;
      var selectedDetail = detailModal.querySelector('[data-delivery-detail="' + String(deliveryId) + '"]');
      var missingDetail = detailModal.querySelector("[data-delivery-detail-missing]");
      detailModal.querySelectorAll("[data-delivery-detail]").forEach(function (detail) {
        detail.hidden = detail !== selectedDetail;
      });
      if (missingDetail) missingDetail.hidden = Boolean(selectedDetail);
      abrirModalPdv("delivery-detail");
      if (!selectedDetail) return;
      var focusTarget = selectedDetail.querySelector("button, input, select");
      if (focusTarget) focusTarget.focus();
    }

    function abrirProdutosEntrega(deliveryId) {
      var itemsModal = document.getElementById("pdv-modal-delivery-items");
      if (!itemsModal || !deliveryId) return;
      var selectedItems = itemsModal.querySelector('[data-delivery-items="' + String(deliveryId) + '"]');
      if (!selectedItems) return;
      deliveryItemsPedidoId = deliveryId;
      itemsModal.querySelectorAll("[data-delivery-items]").forEach(function (items) {
        items.hidden = items !== selectedItems;
      });
      abrirModalPdv("delivery-items");
      selectedItems.focus();
    }

    function voltarProdutosEntrega() {
      if (deliveryItemsPedidoId) abrirConferenciaEntrega(deliveryItemsPedidoId);
      else fecharModalPdv();
    }

    function filtrarModal(input) {
      var modal = input.closest(".pdv-modal");
      if (!modal) return;
      var termo = input.value.trim().toLowerCase();
      modal.querySelectorAll(".pdv-modal-row").forEach(function (row) {
        row.dataset.filterMatch = row.textContent.toLowerCase().includes(termo) ? "1" : "0";
      });
      modal.dataset.page = "0";
      aplicarPaginacaoModal(modal);
      selecionarPrimeiraLinhaVisivelModal(modal, false);
    }

    function linhasFiltradasModal(modal) {
      if (!modal) return [];
      return Array.prototype.slice.call(modal.querySelectorAll(".pdv-modal-row")).filter(function (row) {
        return row.dataset.filterMatch !== "0";
      });
    }

    function aplicarPaginacaoModal(modal) {
      if (!modal) return;
      var list = modal.querySelector("[data-pdv-modal-paginated]");
      var allRows = Array.prototype.slice.call(modal.querySelectorAll(".pdv-modal-row"));
      var filteredRows = linhasFiltradasModal(modal);
      if (!list) {
        allRows.forEach(function (row) {
          row.style.display = row.dataset.filterMatch === "0" ? "none" : "";
        });
        return;
      }
      var pageSize = parseInt(list.getAttribute("data-page-size") || "4", 10);
      pageSize = pageSize > 0 ? pageSize : 4;
      var totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
      var page = Math.max(0, Math.min(totalPages - 1, parseInt(modal.dataset.page || "0", 10) || 0));
      modal.dataset.page = String(page);
      allRows.forEach(function (row) { row.style.display = "none"; });
      filteredRows.slice(page * pageSize, page * pageSize + pageSize).forEach(function (row) {
        row.style.display = "";
      });
      var pagination = modal.querySelector("[data-pdv-modal-pagination]");
      if (pagination) {
        pagination.hidden = filteredRows.length <= pageSize;
        var info = pagination.querySelector("[data-pdv-page-info]");
        var prev = pagination.querySelector("[data-pdv-page='prev']");
        var next = pagination.querySelector("[data-pdv-page='next']");
        if (info) info.textContent = "Pagina " + String(page + 1) + " de " + String(totalPages);
        if (prev) prev.disabled = page <= 0;
        if (next) next.disabled = page >= totalPages - 1;
      }
    }

    function trocarPaginaModal(modal, delta) {
      if (!modal) return;
      var list = modal.querySelector("[data-pdv-modal-paginated]");
      if (!list) return;
      var pageSize = parseInt(list.getAttribute("data-page-size") || "4", 10);
      var totalPages = Math.max(1, Math.ceil(linhasFiltradasModal(modal).length / (pageSize > 0 ? pageSize : 4)));
      var page = Math.max(0, Math.min(totalPages - 1, (parseInt(modal.dataset.page || "0", 10) || 0) + delta));
      modal.dataset.page = String(page);
      aplicarPaginacaoModal(modal);
      selecionarPrimeiraLinhaVisivelModal(modal, true);
    }

    function linhasVisiveisModal(modal) {
      if (!modal) return [];
      return Array.prototype.slice.call(modal.querySelectorAll(".pdv-modal-row")).filter(function (row) {
        return row.style.display !== "none";
      });
    }

    function selecionarLinhaModal(modal, row, focus) {
      if (!modal || !row) return;
      linhasVisiveisModal(modal).forEach(function (item) {
        var selected = item === row;
        item.classList.toggle("is-selected", selected);
        item.setAttribute("aria-selected", selected ? "true" : "false");
        if (!item.hasAttribute("tabindex")) item.setAttribute("tabindex", "-1");
      });
      atualizarPainelRefund(modal, row);
      if (focus) row.focus();
    }

    function atualizarPainelRefund(modal, row) {
      if (!modal || modal.id !== "pdv-modal-refunds" || !row) return;
      var feedback = modal.querySelector("[data-refund-feedback]");
      if (feedback) feedback.textContent = "";
    }

    function voltarCancelamentoEntrega() {
      if (deliveryCancelPedidoId) abrirConferenciaEntrega(deliveryCancelPedidoId);
      else fecharModalPdv();
    }

    function voltarRetornoEntrega() {
      if (deliveryReturnPedidoId) abrirConferenciaEntrega(deliveryReturnPedidoId);
      else fecharModalPdv();
    }

    function limparPainelRefund() {
      if (!refundModal) return;
      var feedback = refundModal.querySelector("[data-refund-feedback]");
      if (feedback) feedback.textContent = "";
      refundModal.querySelectorAll(".pdv-modal-row.is-selected").forEach(function (row) {
        row.classList.remove("is-selected");
        row.setAttribute("aria-selected", "false");
      });
    }

    function mostrarEtapaEstorno(step) {
      if (!refundDetailModal) return;
      refundDetailModal.dataset.refundStep = step;
      refundDetailModal.querySelectorAll("[data-refund-step]").forEach(function (section) {
        section.hidden = section.dataset.refundStep !== step;
      });
      var summaryActions = refundDetailModal.querySelector("[data-refund-summary-actions]");
      if (summaryActions) summaryActions.hidden = step !== "summary";
      refundDetailModal.querySelectorAll("[data-refund-submit]").forEach(function (button) {
        button.hidden = button.dataset.refundSubmit !== step;
      });
      var focus = step === "summary" ? refundDetailModal.querySelector("[data-refund-detail-summary]") : refundDetailModal.querySelector('[data-refund-step="' + step + '"] input:not([type="hidden"]):not([type="number"])');
      if (focus) focus.focus();
    }

    function voltarEstorno() {
      if (!refundDetailModal) return;
      if (refundDetailModal.dataset.refundStep !== "summary") {
        mostrarEtapaEstorno("summary");
        return;
      }
      abrirModalPdv("refunds");
      var selected = refundModal && refundModal.querySelector(".pdv-modal-row.is-selected");
      if (selected) selected.focus();
      else if (refundSearch) refundSearch.focus();
    }

    function abrirDetalheEstorno() {
      if (!refundModal || !refundDetailModal) return;
      var selected = refundModal.querySelector(".pdv-refund-list .pdv-modal-row.is-selected");
      var url = selected && selected.dataset.detailJsonUrl;
      if (!url) {
        var feedback = refundModal.querySelector("[data-refund-feedback]");
        if (feedback) feedback.textContent = "Selecione uma venda para abrir.";
        return;
      }
      var summary = refundDetailModal.querySelector("[data-refund-detail-summary]");
      var items = refundDetailModal.querySelector("[data-refund-detail-items]");
      var payments = refundDetailModal.querySelector("[data-refund-detail-payments]");
      var returnItems = refundDetailModal.querySelector("[data-refund-return-items]");
      refundDetailModal.querySelector("[data-refund-cancel-form]").action = selected.dataset.cancelUrl;
      refundDetailModal.querySelector("[data-refund-return-form]").action = selected.dataset.returnUrl;
      var printButton = refundDetailModal.querySelector("[data-refund-print]");
      printButton.dataset.salePrintUrl = selected.dataset.salePrintUrl;
      printButton.dataset.saleDesktopPrintUrl = selected.dataset.saleDesktopPrintUrl;
      refundDetailModal.querySelectorAll("[data-refund-action]").forEach(function (button) { button.hidden = true; });
      abrirModalPdv("refund-detail");
      mostrarEtapaEstorno("summary");
      summary.textContent = "Carregando venda...";
      items.replaceChildren(); payments.replaceChildren(); returnItems.replaceChildren();
      fetch(url, { credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error("Não foi possível abrir esta venda."); return response.json(); })
        .then(function (sale) {
          if (!refundDetailModal.classList.contains("is-open")) return;
          refundDetailModal.querySelector("#pdv-refund-detail-title").textContent = "Venda #" + sale.id;
          summary.replaceChildren();
          [["Data / hora", sale.data], ["Operador", sale.operador], ["Cliente", sale.cliente], ["Caixa", "#" + sale.caixa], ["Total", "R$ " + sale.total.replace(".", ",")], ["Status", sale.status]].forEach(function (pair) {
            var fact = document.createElement("span");
            var value = document.createElement("strong"); value.textContent = pair[1];
            fact.append(pair[0], value); summary.appendChild(fact);
          });
          sale.itens.forEach(function (item) {
            var line = document.createElement("div");
            line.className = "pdv-refund-detail-line";
            [item.produto, "Qtd " + item.quantidade.replace(".", ","), "Devolvido " + item.devolvido.replace(".", ","), "R$ " + item.valor.replace(".", ",")].forEach(function (part) {
              var span = document.createElement("span"); span.textContent = part; line.appendChild(span);
            });
            items.appendChild(line);
            if (Number(item.disponivel) <= 0) return;
            var label = document.createElement("label");
            label.className = "form-field";
            var caption = document.createElement("span");
            caption.textContent = item.produto + " (disponível: " + item.disponivel.replace(".", ",") + ")";
            var input = document.createElement("input");
            input.type = "number"; input.name = "quantidade_" + item.id;
            input.min = "0"; input.max = item.disponivel; input.step = "0.001"; input.value = "0";
            label.append(caption, input);
            returnItems.appendChild(label);
          });
          sale.pagamentos.forEach(function (payment) {
            var line = document.createElement("div");
            line.className = "pdv-refund-detail-line";
            line.textContent = payment.forma + " · R$ " + payment.valor.replace(".", ",") + " · " + payment.status;
            payments.appendChild(line);
          });
          refundDetailModal.querySelector('[data-refund-action="return"]').hidden = sale.status !== "FINALIZADA" || !returnItems.children.length;
          refundDetailModal.querySelector('[data-refund-action="cancel"]').hidden = sale.status !== "FINALIZADA";
          summary.focus();
        }).catch(function (error) { summary.textContent = error.message; });
    }

    function buscarVendasEstorno() {
      if (!refundSearch || !refundModal) return;
      var sequence = ++refundSearchSequence;
      var list = refundModal.querySelector(".pdv-refund-list");
      fetch(refundSearch.dataset.searchUrl + "?q=" + encodeURIComponent(refundSearch.value.trim()), { credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error(); return response.json(); })
        .then(function (payload) {
          if (sequence !== refundSearchSequence) return;
          list.replaceChildren();
          (payload.results || []).forEach(function (sale) {
            var row = document.createElement("article");
            row.className = "pdv-refund-card pdv-modal-row";
            row.tabIndex = -1;
            row.setAttribute("role", "option");
            row.dataset.detailJsonUrl = sale.detail_url;
            row.dataset.cancelUrl = sale.cancel_url;
            row.dataset.returnUrl = sale.return_url;
            row.dataset.salePrintUrl = sale.print_url;
            row.dataset.saleDesktopPrintUrl = sale.desktop_print_url;
            row.dataset.saleLabel = "Venda #" + sale.id + " - R$ " + sale.total.replace(".", ",");
            var summary = document.createElement("div");
            summary.className = "pdv-refund-summary";
            var title = document.createElement("strong");
            title.textContent = "Venda #" + sale.id;
            var detail = document.createElement("small");
            detail.textContent = sale.data + " · " + sale.cliente + " · Caixa #" + sale.caixa;
            var amount = document.createElement("b");
            amount.textContent = "R$ " + sale.total.replace(".", ",");
            summary.append(title, detail); row.append(summary, amount); list.appendChild(row);
          });
          if (!list.children.length) {
            var empty = document.createElement("div");
            empty.className = "pdv-modal-empty";
            empty.textContent = "Nenhuma venda encontrada.";
            list.appendChild(empty);
          }
          refundModal.dataset.page = "0";
          aplicarPaginacaoModal(refundModal);
          selecionarPrimeiraLinhaVisivelModal(refundModal, false);
        }).catch(function () {
          if (sequence !== refundSearchSequence) return;
          list.textContent = "Não foi possível buscar vendas.";
        });
    }

    function selecionarPrimeiraLinhaVisivelModal(modal, focus) {
      var rows = linhasVisiveisModal(modal);
      if (rows.length) selecionarLinhaModal(modal, rows[0], focus);
    }

    function moverSelecaoModal(modal, delta) {
      var rows = linhasVisiveisModal(modal);
      if (!rows.length) return null;
      var atual = rows.findIndex(function (row) { return row.classList.contains("is-selected"); });
      var destino = Math.max(0, Math.min(rows.length - 1, (atual < 0 ? 0 : atual) + delta));
      selecionarLinhaModal(modal, rows[destino], true);
      return rows[destino];
    }

    function linhaSelecionadaModal(modal) {
      var rows = linhasVisiveisModal(modal);
      return modal && modal.querySelector(".pdv-modal-row.is-selected") || rows[0] || null;
    }

    function focarBuscaProduto() {
      if (!cashOpen) { abrirModalPdv("price"); return; }
      fecharModalPdv();
      restaurarFocoPrincipalPdv(true);
    }

    function restaurarFocoPrincipalPdv(force) {
      if (!cashOpen || !buscaProduto || buscaProduto.disabled) return false;
      if (modalAberto() || (paymentModal && paymentModal.classList.contains("is-open")) ||
          (postSaleModal && postSaleModal.classList.contains("is-open")) ||
          (document.getElementById("pdv-checkout") && !document.getElementById("pdv-checkout").hidden) ||
          (finishForm && finishForm.dataset.submitting === "1")) return false;
      var active = document.activeElement;
      if (!force && active && active !== buscaProduto &&
          (active.matches("input, textarea, select, [contenteditable='true']") || active.closest(".select2-container--open"))) return false;
      buscaProduto.focus();
      if (force) buscaProduto.select();
      return true;
    }
    window.pdvRestoreFocus = restaurarFocoPrincipalPdv;

    function fecharPosVenda(restoreFocus) {
      if (!postSaleModal) return;
      postSaleModal.classList.remove("is-open");
      postSaleModal.setAttribute("aria-hidden", "true");
      if (restoreFocus !== false) restaurarFocoPrincipalPdv(true);
    }

    function imprimirUltimaVenda(opcoes) {
      if (!postSaleModal) return;
      var url = postSaleModal.getAttribute("data-print-url");
      var desktopUrl = postSaleModal.getAttribute("data-desktop-print-url");
      imprimirCupomVenda(url, desktopUrl, opcoes);
    }

    function solicitarImpressaoAutomaticaPosVenda() {
      if (!postSaleModal || postSaleModal.dataset.autoPrintRequested === "1") return;
      if (!(window.SupermercadoDesktop && window.SupermercadoDesktop.printSale)) return;
      postSaleModal.dataset.autoPrintRequested = "1";
      imprimirUltimaVenda({ somenteAutomatico: true });
    }

    function adicionarLinhaPagamento(opcoes) {
      if (!paymentRows || !paymentTemplate) return;
      opcoes = opcoes || {};
      if (opcoes.somenteSeRestante && valorRestantePagamento() <= 0.005) {
        informarPagamentoFeedback("Pagamento ja cobre o total. Para dividir, reduza o valor lancado ou remova uma forma.");
        return null;
      }
      paymentRows.appendChild(paymentTemplate.content.cloneNode(true));
      atualizarResumoPdv();
      var linhas = paymentRows.querySelectorAll(".pdv-payment-row");
      var novaLinha = linhas[linhas.length - 1];
      var select = novaLinha && novaLinha.querySelector("select");
      if (select) select.focus();
      return novaLinha;
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

    if (descontoInput) {
      descontoInput.addEventListener("input", function () {
        var autorizados = paymentRows && paymentRows.querySelectorAll(".pdv-payment-row.is-authorized");
        var pagamentosReprocessados = Boolean(autorizados && autorizados.length);
        if (autorizados && autorizados.length) {
          autorizados.forEach(function (row) { limparAutorizacaoPagamento(row); });
          ocultarPixPanel();
        }
        atualizarAutorizacaoDesconto();
        atualizarResumoPdv();
        var desconto = Math.max(decimalFromInput(descontoInput.value), 0);
        var subtotal = Math.max(decimalFromInput(resumo && resumo.dataset.total), 0);
        if (desconto > subtotal) informarPagamentoFeedback("O desconto não pode ser maior que o total da venda.");
        else if (pagamentosReprocessados) informarPagamentoFeedback("O desconto alterou o total. Reprocesse os pagamentos eletrônicos.");
        else informarPagamentoFeedback("");
      });
    }
    if (discountEntry) discountEntry.addEventListener("input", atualizarPreviewDesconto);
    if (discountModal) discountModal.querySelectorAll("[data-pdv-discount-mode]").forEach(function (button) {
      button.addEventListener("click", function () {
        discountMode = button.dataset.pdvDiscountMode;
        discountModal.querySelectorAll("[data-pdv-discount-mode]").forEach(function (choice) {
          choice.setAttribute("aria-pressed", choice === button ? "true" : "false");
        });
        atualizarPreviewDesconto();
        discountEntry.focus();
      });
    });
    if (discountApply) discountApply.addEventListener("click", aplicarDesconto);
    if (discountAuthorize) discountAuthorize.addEventListener("click", confirmarDescontoAutorizado);
    if (clientSelect) { clientSelect.addEventListener("change", atualizarClienteAtual); atualizarClienteAtual(); }
    if (clientSearch) clientSearch.addEventListener("input", function () {
      clearTimeout(clientSearchTimer);
      clientSearchSequence += 1;
      if (clientResults) clientResults.replaceChildren();
      clientSearchTimer = setTimeout(buscarClientesPdv, 180);
    });
    var clientNew = document.getElementById("pdv-client-new");
    if (clientNew) clientNew.addEventListener("click", function () { mostrarCadastroCliente(true); });
    var clientCreateBack = document.getElementById("pdv-client-create-back");
    if (clientCreateBack) clientCreateBack.addEventListener("click", function () { mostrarCadastroCliente(false); });
    var clientCreateNext = document.getElementById("pdv-client-create-next");
    if (clientCreateNext) clientCreateNext.addEventListener("click", avancarCadastroCliente);
    var clientAddressBack = document.getElementById("pdv-client-address-back");
    if (clientAddressBack) clientAddressBack.addEventListener("click", function () { mostrarEtapaCadastroCliente(0); });
    if (refundModal) {
      var refundOpen = refundModal.querySelector("[data-refund-open]");
      if (refundOpen) refundOpen.addEventListener("click", abrirDetalheEstorno);
    }
    if (refundDetailModal) {
      refundDetailModal.querySelectorAll("[data-refund-back]").forEach(function (button) { button.addEventListener("click", voltarEstorno); });
      refundDetailModal.querySelectorAll("[data-refund-action]").forEach(function (button) {
        button.addEventListener("click", function () { mostrarEtapaEstorno(button.dataset.refundAction); });
      });
      var refundPrint = refundDetailModal.querySelector("[data-refund-print]");
      if (refundPrint) refundPrint.addEventListener("click", function () {
        var url = refundPrint.getAttribute("data-sale-print-url");
        if (url) imprimirCupomVenda(url, refundPrint.getAttribute("data-sale-desktop-print-url"));
      });
    }
    if (refundSearch) refundSearch.addEventListener("input", function () {
      clearTimeout(refundSearchTimer);
      refundSearchSequence += 1;
      var list = refundModal.querySelector(".pdv-refund-list");
      list.replaceChildren();
      limparPainelRefund();
      refundSearchTimer = setTimeout(buscarVendasEstorno, 180);
    });
    if (refundDetailModal) refundDetailModal.querySelectorAll(".pdv-refund-form").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!refundModal.querySelector(".pdv-refund-list .pdv-modal-row.is-selected")) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      }, true);
    });
    if (clientCreateForm) clientCreateForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (clientCreateStage === 0) { avancarCadastroCliente(); return; }
      if (clientCreatePending) return;
      informarErroCadastroCliente("");
      limparErrosCamposCliente();
      if (!validarEnderecoCliente()) return;
      clientCreatePending = true;
      var saveButton = document.getElementById("pdv-client-save");
      if (saveButton) saveButton.disabled = true;
      var url = clientModal.querySelector("[data-client-create-url]").dataset.clientCreateUrl;
      fetch(url, { method: "POST", body: new FormData(clientCreateForm), credentials: "same-origin" })
        .then(function (response) { return response.json().then(function (payload) { return { ok: response.ok, payload: payload }; }); })
        .then(function (result) {
          if (!result.ok) {
            var errorFields = Object.keys(result.payload.errors || {});
            var errors = Object.values(result.payload.errors || {}).flat().map(function (item) { return item.message; });
            var firstField = errorFields.map(function (name) { return clientCreateForm.elements[name]; }).find(function (field) { return field && field.closest("[data-client-create-step]"); });
            if (firstField && firstField.closest('[data-client-create-step="0"]')) mostrarEtapaCadastroCliente(0);
            limparErrosCamposCliente();
            errorFields.forEach(function (name) {
              var messages = result.payload.errors[name] || [];
              if (messages.length) marcarErroCampoCliente(name, messages[0].message);
            });
            informarErroCadastroCliente(errors[0] || "Não foi possível cadastrar o cliente.");
            if (firstField && firstField.offsetParent !== null) firstField.focus();
            return;
          }
          selecionarClientePrincipal(result.payload.id, result.payload.nome);
          clientCreateForm.reset();
          mostrarCadastroCliente(false);
        }).catch(function () { informarErroCadastroCliente("Não foi possível cadastrar o cliente. Tente novamente."); })
        .finally(function () { clientCreatePending = false; if (saveButton) saveButton.disabled = false; });
    });
    if (recebidoInput) recebidoInput.addEventListener("input", atualizarResumoPdv);
    if (openPaymentButton) openPaymentButton.addEventListener("click", function () { abrirPagamentos("sale"); });
    if (closePaymentButton) closePaymentButton.addEventListener("click", fecharPagamentos);
    if (confirmPaymentButton) confirmPaymentButton.addEventListener("click", finalizarVendaPdv);
    if (finalizeButton) finalizeButton.addEventListener("click", function () { abrirPagamentos("sale"); });
    if (finishShortcut) finishShortcut.addEventListener("click", function () { abrirPagamentos("sale"); });
    if (captureDocumentButton) captureDocumentButton.addEventListener("click", capturarDocumentoPinpad);
    cpfDecisionInputs.forEach(function (input) {
      input.addEventListener("change", function () {
        atualizarCpfNaNota();
        informarPagamentoFeedback("");
        if (input.value !== "NAO" && input.checked && documentInput) documentInput.focus();
        if (input.value === "NAO" && input.checked) {
          var firstSelect = paymentModal && paymentModal.querySelector("select");
          if (firstSelect) firstSelect.focus();
        }
      });
    });
    document.addEventListener("supermercado:desktop-ready", atualizarCapacidadeDocumentoPinpad);
    atualizarCapacidadeDocumentoPinpad();
    if (deliveryContinue) deliveryContinue.addEventListener("click", continuarEntrega);
    if (deliveryBack) deliveryBack.addEventListener("click", function () { if (deliveryStage > 0) mostrarEtapaEntrega(deliveryStage - 1); });
    if (deliveryForm) deliveryForm.querySelectorAll('input[name="delivery_address_mode"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (radio.value === "other" && radio.checked) {
          ["entrega_cep", "entrega_logradouro", "entrega_numero", "entrega_complemento", "entrega_bairro", "entrega_municipio", "entrega_uf"].forEach(function (name) {
            if (deliveryForm.elements[name]) deliveryForm.elements[name].value = "";
          });
        }
        atualizarModoEnderecoEntrega();
      });
    });
    if (deliveryForm && deliveryForm.elements.entrega_bairro) {
      deliveryForm.elements.entrega_bairro.addEventListener("input", atualizarModoEnderecoEntrega);
    }
    if (deliveryForm) deliveryForm.elements.documento_cliente_tipo.addEventListener("change", function () {
      atualizarDocumentoEntrega(deliverySelectedClient);
    });
    var deliveryCepLookup = document.querySelector("[data-delivery-cep-lookup]");
    if (deliveryCepLookup) deliveryCepLookup.addEventListener("click", function () {
      var fields = document.getElementById("pdv-delivery-address-fields");
      var cep = deliveryForm.elements.entrega_cep.value.replace(/\D/g, "");
      var feedback = fields.querySelector("[data-delivery-cep-feedback]");
      if (cep.length !== 8) { feedback.textContent = "Informe um CEP com 8 dígitos."; deliveryForm.elements.entrega_cep.focus(); return; }
      deliveryCepLookup.disabled = true;
      feedback.textContent = "Consultando CEP...";
      fetch(fields.dataset.cadastroLookupUrl + "?cep=" + encodeURIComponent(cep), { credentials: "same-origin" })
        .then(function (response) { return response.json().then(function (payload) { if (!response.ok) throw new Error(payload.mensagem || "Consulta indisponível."); return payload; }); })
        .then(function (payload) {
          var data = payload.dados || {};
          [["entrega_logradouro", "logradouro"], ["entrega_bairro", "bairro"], ["entrega_municipio", "municipio"], ["entrega_uf", "uf"]].forEach(function (pair) {
            var field = deliveryForm.elements[pair[0]];
            if (field && !field.value && data[pair[1]]) field.value = data[pair[1]];
          });
          feedback.textContent = payload.mensagem || "CEP consultado.";
        }).catch(function (error) { feedback.textContent = error.message; })
        .finally(function () { deliveryCepLookup.disabled = false; });
    });
    if (deliveryForm) {
      ["distancia_entrega_km", "bairro_entrega"].forEach(function (name) {
        var field = deliveryForm.elements[name];
        if (field) field.addEventListener("change", function () { atualizarCotacaoEntrega().catch(function () {}); });
      });
    }
    if (addPaymentButton) {
      addPaymentButton.addEventListener("click", function () {
        adicionarLinhaPagamento({ somenteSeRestante: true });
      });
    }
    if (scaleButton) scaleButton.addEventListener("click", lerPesoBalancaPdv);
    if (buscaProduto) buscaProduto.addEventListener("keydown", function (event) {
      if (event.key === "F12") {
        event.preventDefault();
        event.stopPropagation();
        lerPesoBalancaPdv();
        return;
      }
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (event.repeat || !buscaProduto.value.trim()) return;
      var addForm = document.getElementById("pdv-add-form");
      if (!addForm || addForm.dataset.submitting === "1") return;
      addForm.requestSubmit();
    });
    if (postSalePrintButton) postSalePrintButton.addEventListener("click", function () { imprimirUltimaVenda(); });
    if (postSaleCloseButton) postSaleCloseButton.addEventListener("click", fecharPosVenda);
    document.addEventListener("supermercado:desktop-ready", solicitarImpressaoAutomaticaPosVenda, { once: true });
    solicitarImpressaoAutomaticaPosVenda();
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
      button.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        var name = button.getAttribute("data-pdv-modal-open");
        if (name === "discount") abrirDesconto();
        else {
          if (name === "clients") mostrarCadastroCliente(false);
          abrirModalPdv(name);
        }
      });
    });
    document.querySelectorAll("[data-pdv-focus-search]").forEach(function (button) {
      button.addEventListener("click", focarBuscaProduto);
    });
    pdvModals.forEach(function (modal) {
      modal.addEventListener("click", function (event) {
        if (event.target === modal || event.target.closest("[data-pdv-modal-close]")) {
          if (modal === refundDetailModal) voltarEstorno();
          else {
            fecharModalPdv();
            restaurarFocoPrincipalPdv(true);
          }
        }
        var pageButton = event.target.closest("[data-pdv-page]");
        if (pageButton && modal.contains(pageButton)) {
          trocarPaginaModal(modal, pageButton.getAttribute("data-pdv-page") === "prev" ? -1 : 1);
          return;
        }
        var modalRow = event.target.closest(".pdv-modal-row");
        if (modalRow && modal.contains(modalRow)) selecionarLinhaModal(modal, modalRow, false);
        var deliveryButton = event.target.closest("[data-delivery-order]");
        if (deliveryButton && modal.contains(deliveryButton)) {
          abrirConferenciaEntrega(deliveryButton.getAttribute("data-delivery-id"));
          return;
        }
        var produtoButton = event.target.closest("[data-pdv-copy-product]");
        if (produtoButton && buscaProduto) {
          buscaProduto.value = produtoButton.getAttribute("data-pdv-copy-product") || "";
          fecharModalPdv();
          restaurarFocoPrincipalPdv(true);
        }
        var clientButton = event.target.closest("[data-pdv-select-client]");
        if (clientButton && clientSelect) {
          selecionarClientePrincipal(clientButton.getAttribute("data-pdv-select-client"), clientButton.dataset.clientName || clientButton.textContent.trim());
        }
      });
      modal.addEventListener("input", function (event) {
        if (event.target.matches("[data-pdv-modal-filter]")) filtrarModal(event.target);
      });
      modal.addEventListener("focusin", function (event) {
        var modalRow = event.target.closest(".pdv-modal-row");
        if (modalRow && modal.contains(modalRow)) selecionarLinhaModal(modal, modalRow, false);
      });
    });
    document.querySelectorAll(".pdv-delivery-separation-form").forEach(function (deliverySeparationForm) {
      deliverySeparationForm.addEventListener("keydown", function (event) {
        if (event.ctrlKey && event.key === "Enter") {
          event.preventDefault();
          if (deliverySeparationForm.requestSubmit) deliverySeparationForm.requestSubmit();
          else deliverySeparationForm.submit();
        }
      });
    });

    document.querySelectorAll(".pdv-delivery-payment-form").forEach(function (deliveryPaymentForm) {
      var paymentType = deliveryPaymentForm.querySelector('[name="forma_pagamento"]');
      var reference = deliveryPaymentForm.querySelector('[name="referencia_pagamento"]');
      if (!paymentType || !reference) return;
      var deliveryCards = ["CARTAO_CREDITO_ENTREGA", "CARTAO_DEBITO_ENTREGA"];
      function atualizarReferenciaEntrega() {
        var requiresReference = deliveryCards.indexOf(paymentType.value) !== -1;
        reference.required = requiresReference;
        reference.setAttribute("aria-required", requiresReference ? "true" : "false");
        reference.placeholder = requiresReference ? "Informe o NSU da maquininha" : "Opcional para esta forma de pagamento";
      }
      paymentType.addEventListener("change", atualizarReferenciaEntrega);
      atualizarReferenciaEntrega();
    });

    var deliveryParam = new URLSearchParams(window.location.search).get("delivery");
    if (deliveryParam) abrirConferenciaEntrega(deliveryParam);

    if (paymentRows) {
      paymentRows.addEventListener("input", function (event) {
        var row = event.target.closest(".pdv-payment-row");
        if (row) limparAutorizacaoPagamento(row);
        atualizarResumoPdv();
      });
      paymentRows.addEventListener("change", function (event) {
        var row = event.target.closest(".pdv-payment-row");
        if (row) limparAutorizacaoPagamento(row);
        atualizarResumoPdv();
      });
      paymentRows.addEventListener("click", function (event) {
        var removeButton = event.target.closest(".pdv-remove-payment");
        if (!removeButton) return;
        removerLinhaPagamento(removeButton.closest(".pdv-payment-row"));
      });
    }
    var cartRows = Array.prototype.slice.call(document.querySelectorAll(".pdv-cart-row"));
    var clearCartLink = document.getElementById("pdv-clear-cart");
    var selectedCartIndex = Math.max(0, cartRows.findIndex(function (row) { return row.classList.contains("is-selected"); }));

    function selecionarItemCarrinho(row, focus) {
      if (!row) return;
      cartRows.forEach(function (item) {
        var selected = item === row;
        item.classList.toggle("is-selected", selected);
        item.setAttribute("aria-selected", selected ? "true" : "false");
        if (selected) selectedCartIndex = cartRows.indexOf(item);
      });
      if (selectedItemStatus) {
        selectedItemStatus.textContent = "Selecionado: " + (row.dataset.productLabel || "item") + " (qtd. " + (row.dataset.productQuantity || "0") + ")";
      }
      if (focus) row.focus();
    }

    function campoEditavelAtivo() {
      var active = document.activeElement;
      if (!active) return false;
      return active.matches("input, textarea, select, [contenteditable='true']");
    }

    function confirmarRemocaoItem(row) {
      if (!row || !row.dataset.removeUrl) return;
      var produto = row.dataset.productLabel || "o item selecionado";
      if (window.confirm("Remover uma unidade de " + produto + "?")) window.location.href = row.dataset.removeUrl;
    }

    function abrirEdicaoQuantidade(row) {
      if (!row || !row.dataset.quantityUrl || !quantityModal || !quantityForm || !quantityInput) return;
      selecionarItemCarrinho(row, false);
      quantityForm.action = row.dataset.quantityUrl;
      if (quantityProduct) quantityProduct.textContent = row.dataset.productLabel || "Item selecionado";
      if (quantityCurrent) quantityCurrent.textContent = row.dataset.productQuantity || "0";
      quantityInput.value = String(row.dataset.productQuantity || "").replace(",", ".");
      abrirModalPdv("quantity");
      quantityInput.focus();
      quantityInput.select();
    }

    function manterFocoNoDialog(container, event) {
      if (!container || event.key !== "Tab") return false;
      var focusable = Array.prototype.slice.call(container.querySelectorAll("button:not([disabled]), a[href], input:not([type='hidden']):not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")).filter(function (element) {
        return element.offsetParent !== null && !element.closest("[hidden]");
      });
      if (!focusable.length) return false;
      var index = focusable.indexOf(document.activeElement);
      var next = event.shiftKey ? index - 1 : index + 1;
      if (index === -1 || next < 0 || next >= focusable.length) {
        event.preventDefault();
        focusable[event.shiftKey ? focusable.length - 1 : 0].focus();
        return true;
      }
      return false;
    }

    cartRows.forEach(function (row) {
      row.addEventListener("click", function (event) {
        if (!event.target.closest("a, button")) selecionarItemCarrinho(row, false);
      });
      row.addEventListener("focus", function () { selecionarItemCarrinho(row, false); });
    });
    document.querySelectorAll("[data-delivery-cancel-url]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!deliveryCancelForm) return;
        deliveryCancelPedidoId = button.dataset.deliveryCancelId;
        deliveryCancelForm.action = button.dataset.deliveryCancelUrl;
        deliveryCancelForm.reset();
        delete deliveryCancelForm.dataset.submitting;
        abrirModalPdv("delivery-cancel");
        deliveryCancelForm.elements.motivo.focus();
      });
    });
    document.querySelectorAll("[data-delivery-return-url]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!deliveryReturnForm) return;
        deliveryReturnPedidoId = button.dataset.deliveryReturnId;
        deliveryReturnForm.action = button.dataset.deliveryReturnUrl;
        deliveryReturnForm.reset();
        delete deliveryReturnForm.dataset.submitting;
        abrirModalPdv("delivery-return");
        deliveryReturnForm.elements.motivo.focus();
      });
    });
    document.querySelectorAll("[data-delivery-return-back]").forEach(function (button) {
      button.addEventListener("click", voltarRetornoEntrega);
    });
    document.querySelectorAll("[data-delivery-items-id]").forEach(function (button) {
      button.addEventListener("click", function () { abrirProdutosEntrega(button.dataset.deliveryItemsId); });
    });
    document.querySelectorAll("[data-delivery-items-back]").forEach(function (button) {
      button.addEventListener("click", voltarProdutosEntrega);
    });
    var deliveryCancelBack = document.querySelector("[data-delivery-cancel-back]");
    if (deliveryCancelBack) deliveryCancelBack.addEventListener("click", voltarCancelamentoEntrega);
    document.querySelectorAll("[data-pdv-edit-quantity]").forEach(function (button) {
      button.addEventListener("click", function () {
        abrirEdicaoQuantidade(button.closest(".pdv-cart-row"));
      });
    });
    document.querySelectorAll("[data-pdv-remove-item]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        confirmarRemocaoItem(link.closest(".pdv-cart-row"));
      });
    });
    if (clearCartLink) {
      clearCartLink.addEventListener("click", function (event) {
        if (!window.confirm("Excluir todos os produtos desta venda?")) event.preventDefault();
      });
    }
    document.addEventListener("keydown", function (event) {
      var key = event.key;
      var activeCheckout = document.getElementById("pdv-checkout");
      if (activeCheckout && !activeCheckout.hidden) return;
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
        if (key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
          event.preventDefault();
          fecharPosVenda(false);
          if (buscaProduto) {
            buscaProduto.value = key;
            restaurarFocoPrincipalPdv();
          }
          return;
        }
      }
      if (key === "Escape") {
        if (refundDetailModal && refundDetailModal.classList.contains("is-open")) {
          event.preventDefault();
          voltarEstorno();
          return;
        }
        if (modalAberto() && modalAberto().id === "pdv-modal-delivery" && deliveryStage > 0) {
          event.preventDefault();
          mostrarEtapaEntrega(deliveryStage - 1);
          return;
        }
        if (modalAberto() && modalAberto().id === "pdv-modal-delivery-cancel") {
          event.preventDefault();
          voltarCancelamentoEntrega();
          return;
        }
        if (modalAberto() && modalAberto().id === "pdv-modal-delivery-return") {
          event.preventDefault();
          voltarRetornoEntrega();
          return;
        }
        if (modalAberto() && modalAberto().id === "pdv-modal-delivery-items") {
          event.preventDefault();
          voltarProdutosEntrega();
          return;
        }
        if (clientModal && clientModal.classList.contains("is-open") && clientCreateForm && !clientCreateForm.hidden) {
          event.preventDefault();
          if (clientCreateStage === 1) mostrarEtapaCadastroCliente(0);
          else mostrarCadastroCliente(false);
          return;
        }
        if (discountModal && discountModal.classList.contains("is-open") && !discountAuthorizationStep.hidden) {
          event.preventDefault();
          mostrarEtapaDesconto(false);
          return;
        }
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
          if (modalAberto().id === "pdv-modal-delivery-detail") {
            abrirModalPdv("deliveries");
          } else {
            fecharModalPdv();
            restaurarFocoPrincipalPdv(true);
          }
        } else if (document.activeElement === quantidadeInput) {
          event.preventDefault();
          restaurarFocoPrincipalPdv(true);
        }
        return;
      }
      if (event.shiftKey && key.toLowerCase() === "m") {
        if (modalAberto() || (paymentModal && paymentModal.classList.contains("is-open")) || (document.getElementById("pdv-checkout") && !document.getElementById("pdv-checkout").hidden)) return;
        var menuLink = document.getElementById("pdv-menu-link");
        if (menuLink) {
          event.preventDefault();
          window.location.href = menuLink.href;
        }
        return;
      }
      if (event.ctrlKey && key.toLowerCase() === "e") {
        event.preventDefault();
        if (modalAberto() || (document.getElementById("pdv-checkout") && !document.getElementById("pdv-checkout").hidden)) return;
        if (paymentModal && paymentModal.classList.contains("is-open")) {
          if (paymentRows && paymentRows.querySelector(".pdv-payment-row.is-authorized")) {
            informarPagamentoFeedback("Há pagamento eletrônico autorizado nesta venda. Conclua ou trate a operação antes de mudar para entrega.");
            return;
          }
          fecharPagamentos();
        }
        var deliveryButton = document.querySelector('[data-pdv-modal-open="delivery"]:not([disabled])');
        if (deliveryButton) {
          abrirModalPdv("delivery");
          var deliveryName = document.querySelector('#pdv-modal-delivery input[name="nome_cliente"]');
          if (deliveryName) deliveryName.focus();
        }
        return;
      }
      if (event.shiftKey && key.toLowerCase() === "e") {
        event.preventDefault();
        if (modalAberto() || (paymentModal && paymentModal.classList.contains("is-open")) || (document.getElementById("pdv-checkout") && !document.getElementById("pdv-checkout").hidden)) return;
        abrirModalPdv("deliveries");
        return;
      }
      if (event.shiftKey && key.toLowerCase() === "s") {
        if (modalAberto() || (paymentModal && paymentModal.classList.contains("is-open")) || (document.getElementById("pdv-checkout") && !document.getElementById("pdv-checkout").hidden)) return;
        var exitButton = document.getElementById("pdv-exit-button");
        if (exitButton) {
          event.preventDefault();
          exitButton.click();
        }
        return;
      }
      var activeModal = modalAberto();
      if (activeModal && manterFocoNoDialog(activeModal, event)) return;
      if (activeModal === clientModal && clientCreateForm && !clientCreateForm.hidden) {
        if (event.ctrlKey && key === "Enter") {
          event.preventDefault();
          if (event.repeat) return;
          if (clientCreateStage === 0) avancarCadastroCliente();
          else clientCreateForm.requestSubmit();
          return;
        }
        if (key === "Enter" && clientCreateStage === 1 && document.activeElement === clientCreateForm.elements.cep) {
          event.preventDefault();
          var clientCepButton = clientCreateForm.querySelector('[data-lookup-kind="cep"]');
          if (clientCepButton) clientCepButton.click();
          return;
        }
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery-cancel") {
        if (event.ctrlKey && key === "Enter") {
          event.preventDefault();
          event.stopPropagation();
          if (deliveryCancelForm && !deliveryCancelForm.dataset.submitting && deliveryCancelForm.reportValidity()) {
            deliveryCancelForm.dataset.submitting = "1";
            deliveryCancelForm.requestSubmit();
          }
        }
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery-return") {
        if (event.ctrlKey && key === "Enter") {
          event.preventDefault();
          if (!event.repeat && deliveryReturnForm && !deliveryReturnForm.dataset.submitting && deliveryReturnForm.reportValidity()) {
            deliveryReturnForm.dataset.submitting = "1";
            deliveryReturnForm.requestSubmit();
          }
          return;
        }
        if (key.startsWith("F")) { event.preventDefault(); return; }
      }
      if (discountModal && activeModal === discountModal) {
        if (key === "Enter") {
          event.preventDefault();
          if (discountAuthorizationStep.hidden) aplicarDesconto();
          else confirmarDescontoAutorizado();
        }
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-refunds") {
        if (event.ctrlKey && key === "Enter") {
          event.preventDefault();
          abrirDetalheEstorno();
          return;
        }
        if (key === "Enter" && document.activeElement && document.activeElement.matches("[data-refund-open]")) {
          event.preventDefault();
          return;
        }
        if (key === "ArrowUp" || key === "ArrowDown") {
          event.preventDefault();
          moverSelecaoModal(activeModal, key === "ArrowUp" ? -1 : 1);
          return;
        }
        if (key === "Home" || key === "End") {
          var rows = linhasVisiveisModal(activeModal);
          if (rows.length) { event.preventDefault(); selecionarLinhaModal(activeModal, key === "Home" ? rows[0] : rows[rows.length - 1], true); }
          return;
        }
        if (key === "PageUp" || key === "PageDown") {
          event.preventDefault();
          trocarPaginaModal(activeModal, key === "PageUp" ? -1 : 1);
          return;
        }
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-refund-detail") {
        if (key === "F10" && activeModal.dataset.refundStep === "summary") {
          event.preventDefault();
          var botaoReimprimir = activeModal.querySelector("[data-refund-print]");
          if (botaoReimprimir) botaoReimprimir.click();
          return;
        }
        if (event.ctrlKey && key === "Enter" && activeModal.dataset.refundStep !== "summary") {
          event.preventDefault();
          var formEstorno = activeModal.querySelector('[data-refund-step="' + activeModal.dataset.refundStep + '"] form');
          if (formEstorno) formEstorno.requestSubmit();
          return;
        }
        if ((key === "ArrowDown" || key === "ArrowUp" || key === "PageDown" || key === "PageUp" || key === "Home" || key === "End") && document.activeElement === activeModal.querySelector("[data-refund-detail-items]")) {
          event.preventDefault();
          var itemsArea = document.activeElement;
          if (key === "Home") itemsArea.scrollTop = 0;
          else if (key === "End") itemsArea.scrollTop = itemsArea.scrollHeight;
          else itemsArea.scrollTop += (key === "ArrowUp" || key === "PageUp" ? -1 : 1) * (key === "ArrowDown" || key === "ArrowUp" ? 42 : itemsArea.clientHeight);
          return;
        }
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery") {
        var focoEmEntrega = document.activeElement && document.activeElement.closest && document.activeElement.closest("#pdv-modal-delivery form");
        if (event.altKey && !event.ctrlKey && !event.metaKey && key.toLowerCase() === "s") {
          event.preventDefault();
          if (!deliverySaveClient || deliverySaveClient.disabled) {
            if (deliveryClientStatus) deliveryClientStatus.textContent = "Cliente cadastrado selecionado. Esta opção não precisa ser marcada.";
            return;
          }
          deliverySaveClient.checked = !deliverySaveClient.checked;
          deliverySaveClient.focus();
          if (deliveryClientStatus) deliveryClientStatus.textContent = deliverySaveClient.checked ? "Cliente sera salvo para proximas entregas." : "Pedido sera criado como cliente avulso.";
          return;
        }
        if (key === "Tab" && focoEmEntrega) {
          var camposEntrega = Array.prototype.slice.call(
            activeModal.querySelectorAll('input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])')
          ).filter(function (field) { return !field.closest("[hidden]") && field.offsetParent !== null; });
          if (camposEntrega.length) {
            var indiceEntrega = camposEntrega.indexOf(document.activeElement);
            var proximoIndiceEntrega = event.shiftKey ? indiceEntrega - 1 : indiceEntrega + 1;
            if (indiceEntrega === -1 || proximoIndiceEntrega < 0 || proximoIndiceEntrega >= camposEntrega.length) {
              event.preventDefault();
              camposEntrega[event.shiftKey ? camposEntrega.length - 1 : 0].focus();
              return;
            }
          }
        }
        if (event.ctrlKey && key === "Enter") {
          event.preventDefault();
          event.stopPropagation();
          if (!deliveryContinuing && deliveryContinue && !deliveryContinue.disabled) continuarEntrega();
          return;
        }
      }
      if (activeModal && activeModal.id === "pdv-modal-deliveries") {
        if (key === "ArrowUp" || key === "ArrowDown") {
          event.preventDefault();
          moverSelecaoModal(activeModal, key === "ArrowUp" ? -1 : 1);
          return;
        }
        if (key === "Enter") {
          event.preventDefault();
          var entregaSelecionada = linhaSelecionadaModal(activeModal);
          if (entregaSelecionada) abrirConferenciaEntrega(entregaSelecionada.getAttribute("data-delivery-id"));
          return;
        }
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery-detail") {
        var detailPanel = activeModal.querySelector("[data-delivery-detail]:not([hidden])");
        if (key === "F7") {
          event.preventDefault();
          if (detailPanel) abrirProdutosEntrega(detailPanel.dataset.deliveryDetail);
          return;
        }
        if (key === "F8") {
          event.preventDefault();
          var cancelButton = detailPanel && detailPanel.querySelector("[data-delivery-return-url], [data-delivery-cancel-url]");
          if (cancelButton && !event.repeat) cancelButton.click();
          return;
        }
        if (key === "F10") {
          event.preventDefault();
          var deliveryPrintButton = activeModal.querySelector("[data-delivery-print-url]");
          if (deliveryPrintButton) deliveryPrintButton.click();
          return;
        }
        if (key === "Tab" && detailPanel) {
          var focusable = Array.prototype.slice.call(detailPanel.querySelectorAll('button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])'));
          if (focusable.length) {
            var currentIndex = focusable.indexOf(document.activeElement);
            var nextIndex = event.shiftKey ? currentIndex - 1 : currentIndex + 1;
            if (currentIndex === -1 || nextIndex < 0 || nextIndex >= focusable.length) {
              event.preventDefault();
              focusable[event.shiftKey ? focusable.length - 1 : 0].focus();
              return;
            }
          }
        }
        var focoNoFormularioEntrega = document.activeElement && document.activeElement.closest && document.activeElement.closest("#pdv-modal-delivery-detail form");
        if (event.ctrlKey && key === "Enter" && focoNoFormularioEntrega && focoNoFormularioEntrega.classList.contains("pdv-delivery-separation-form")) {
          event.preventDefault();
          if (focoNoFormularioEntrega.requestSubmit) focoNoFormularioEntrega.requestSubmit();
          else focoNoFormularioEntrega.submit();
          return;
        }
        if (event.altKey && key === "Enter" && focoNoFormularioEntrega && focoNoFormularioEntrega.classList.contains("pdv-delivery-payment-form")) {
          event.preventDefault();
          if (focoNoFormularioEntrega.requestSubmit) focoNoFormularioEntrega.requestSubmit();
          else focoNoFormularioEntrega.submit();
          return;
        }
        if (key === "F6") {
          var paymentInput = activeModal.querySelector(".pdv-delivery-payment-form select, .pdv-delivery-payment-form input:not([type=hidden])");
          if (paymentInput) { event.preventDefault(); paymentInput.focus(); }
          return;
        }
        var deliveryShortcuts = {F2: "reserve", F3: "ready", F4: "dispatch", F5: "complete"};
        var deliveryAction = deliveryShortcuts[key];
        var actionButton = deliveryAction && activeModal.querySelector('[data-delivery-action="' + deliveryAction + '"]');
        if (actionButton) { event.preventDefault(); actionButton.click(); return; }
        if (key.startsWith("F")) { event.preventDefault(); return; }
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery-items" && key.startsWith("F")) {
        event.preventDefault();
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery-cancel" && key.startsWith("F")) {
        event.preventDefault();
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-open-cash") {
        var openCashForm = activeModal.querySelector(".pdv-open-cash-form");
        if (event.ctrlKey && key === "Enter" && openCashForm) {
          event.preventDefault();
          if (openCashForm.requestSubmit) openCashForm.requestSubmit();
          else openCashForm.submit();
        }
        return;
      }
      if (activeModal && activeModal.id === "pdv-modal-boxes") {
        var focoEmCaixaForm = document.activeElement && document.activeElement.closest && document.activeElement.closest(".pdv-cash-close-form, .pdv-cash-movement-form");
        if (key === "F2") {
          event.preventDefault();
          var openCashLink = activeModal.querySelector("#pdv-open-cash-link");
          var suprimentoForm = activeModal.querySelector("[data-cash-movement-form='suprimento']");
          if (openCashLink) abrirModalPdv("open-cash");
          else if (suprimentoForm) {
            var suprimentoValor = suprimentoForm.querySelector("input[name='valor']");
            if (suprimentoValor) suprimentoValor.focus();
          }
          return;
        }
        if (key === "F3") {
          event.preventDefault();
          var sangriaForm = activeModal.querySelector("[data-cash-movement-form='sangria']");
          var sangriaValor = sangriaForm && sangriaForm.querySelector("input[name='valor']");
          if (sangriaValor) sangriaValor.focus();
          return;
        }
        if (key === "F5") {
          event.preventDefault();
          var closeCashForm = activeModal.querySelector("[data-cash-close-form]");
          var closeCashValue = closeCashForm && closeCashForm.querySelector("input[name='valor_final']");
          if (closeCashValue) closeCashValue.focus();
          return;
        }
        if (event.ctrlKey && key === "Enter" && focoEmCaixaForm) {
          event.preventDefault();
          var caixaForm = document.activeElement.closest(".pdv-cash-close-form, .pdv-cash-movement-form");
          if (caixaForm) {
            if (caixaForm.requestSubmit) caixaForm.requestSubmit();
            else caixaForm.submit();
          }
          return;
        }
        if ((key === "ArrowUp" || key === "ArrowDown") && !focoEmCaixaForm) {
          event.preventDefault();
          moverSelecaoModal(activeModal, key === "ArrowUp" ? -1 : 1);
          return;
        }
        if (key === "Enter" && !focoEmCaixaForm) {
          event.preventDefault();
          var caixaSelecionado = linhaSelecionadaModal(activeModal);
          if (caixaSelecionado && caixaSelecionado.href) window.location.href = caixaSelecionado.href;
          else {
            var manageCashLink = activeModal.querySelector("#pdv-manage-cash-link");
            if (manageCashLink) window.location.href = manageCashLink.href;
          }
          return;
        }
      }
      if (activeModal && ["pdv-modal-products", "pdv-modal-clients", "pdv-modal-promos", "pdv-modal-price"].indexOf(activeModal.id) !== -1) {
        if (activeModal === clientModal && ((clientCreateForm && !clientCreateForm.hidden) || document.activeElement === clientNew)) return;
        if (key === "ArrowUp" || key === "ArrowDown") {
          event.preventDefault();
          moverSelecaoModal(activeModal, key === "ArrowUp" ? -1 : 1);
          return;
        }
        if (key === "PageUp" || key === "PageDown") {
          event.preventDefault();
          trocarPaginaModal(activeModal, key === "PageUp" ? -1 : 1);
          return;
        }
        if (key === "Enter") {
          var selectedModalRow = linhaSelecionadaModal(activeModal);
          if (selectedModalRow && selectedModalRow.matches("button, a")) {
            event.preventDefault();
            selectedModalRow.click();
          }
          return;
        }
      }
      if (activeModal) return;
      if (key === "F12" && !(paymentModal && paymentModal.classList.contains("is-open"))) {
        event.preventDefault();
        lerPesoBalancaPdv();
        return;
      }
      if (paymentModal && paymentModal.classList.contains("is-open")) {
        if (manterFocoNoDialog(paymentModal, event)) return;
        if (["1", "2", "3"].indexOf(key) !== -1 && document.activeElement && document.activeElement.name === "cpf_na_nota") {
          event.preventDefault();
          selecionarDecisaoCpf(Number(key) - 1);
          return;
        }
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(key) !== -1 && document.activeElement && document.activeElement.name === "cpf_na_nota") {
          event.preventDefault();
          var currentCpfIndex = Array.prototype.indexOf.call(cpfDecisionInputs, document.activeElement);
          var cpfDirection = key === "ArrowLeft" || key === "ArrowUp" ? -1 : 1;
          selecionarDecisaoCpf((currentCpfIndex + cpfDirection + cpfDecisionInputs.length) % cpfDecisionInputs.length);
          return;
        }
        if (key === "Enter" && document.activeElement && document.activeElement.name === "cpf_na_nota") {
          event.preventDefault();
          document.activeElement.checked = true;
          document.activeElement.dispatchEvent(new Event("change", { bubbles: true }));
          return;
        }
        if (event.shiftKey && key === "F4") {
          event.preventDefault();
          capturarDocumentoPinpad();
          return;
        }
        if (key === "F6") {
          event.preventDefault();
          if (descontoInput) {
            descontoInput.focus();
            descontoInput.select();
          }
          return;
        }
        if ((event.shiftKey && (key === "+" || key === "=")) || key === "Add") {
          event.preventDefault();
          adicionarLinhaPagamento({ somenteSeRestante: true });
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
        if (electronicChoice && electronicChoice.classList.contains("is-open") && ["F1", "F2", "F3", "F4", "F5"].indexOf(key) !== -1) {
          event.preventDefault();
          if (key === "F1") selecionarPagamentoEletronico("CREDITO");
          if (key === "F2") selecionarPagamentoEletronico("DEBITO");
          if (key === "F3") selecionarPagamentoEletronico("PIX");
          if (key === "F4") selecionarPagamentoEletronico("VALE_ALIMENTACAO");
          if (key === "F5") selecionarPagamentoEletronico("VALE_REFEICAO");
          return;
        }
        if (["F1", "F2", "F3", "F4"].indexOf(key) !== -1) {
          event.preventDefault();
          selecionarFormaPagamento(key);
          return;
        }
        if (key === "Enter") {
          if (avancarPagamentoComEnter()) event.preventDefault();
          return;
        }
        return;
      }
      if ((key === "ArrowUp" || key === "ArrowDown") && cartRows.length && !modalAberto() && !campoEditavelAtivo()) {
        event.preventDefault();
        var atual = Math.max(0, selectedCartIndex);
        var destino = key === "ArrowUp" ? Math.max(0, atual - 1) : Math.min(cartRows.length - 1, atual + 1);
        selecionarItemCarrinho(cartRows[destino], true);
        return;
      }
      if (key === "Enter" && document.activeElement && document.activeElement.classList.contains("pdv-cart-row")) {
        event.preventDefault();
        abrirEdicaoQuantidade(document.activeElement);
        return;
      }
      if ((key === "Delete" || key === "Del") && cartRows.length && !campoEditavelAtivo()) {
        event.preventDefault();
        if (event.ctrlKey) {
          if (clearCartLink && window.confirm("Excluir todos os produtos desta venda?")) window.location.href = clearCartLink.href;
          return;
        }
        var selectedCartRow = document.querySelector(".pdv-cart-row.is-selected") || cartRows[cartRows.length - 1];
        confirmarRemocaoItem(selectedCartRow);
        return;
      }
      if (!key || !key.startsWith("F")) {
        if (key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey && !campoEditavelAtivo() && cashOpen && !modalAberto() && !(paymentModal && paymentModal.classList.contains("is-open")) && !(document.getElementById("pdv-checkout") && !document.getElementById("pdv-checkout").hidden) && !(finishForm && finishForm.dataset.submitting === "1")) {
          event.preventDefault();
          if (restaurarFocoPrincipalPdv()) buscaProduto.value += key;
        }
        return;
      }
      if (["F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11"].indexOf(key) === -1) return;
      event.preventDefault();
      if (key === "F2") focarBuscaProduto();
      if (key === "F3") abrirModalPdv("price");
      if (key === "F4") abrirModalPdv("clients");
      if (key === "F5") abrirModalPdv("products");
      if (key === "F6") abrirModalPdv("refunds");
      if (key === "F7") {
        var davButton = document.getElementById("pdv-dav-shortcut");
        if (davButton && !davButton.disabled) abrirModalPdv("dav");
      }
      if (key === "F8") abrirModalPdv("boxes");
      if (key === "F9") {
        if (finishShortcut && !finishShortcut.disabled) abrirPagamentos("sale");
      }
      if (key === "F10") abrirDesconto();
      if (key === "F11") abrirModalPdv("promos");
    });
    if (finishForm) {
      finishForm.addEventListener("submit", function (event) {
        if (!pagamentoCompleto()) {
          event.preventDefault();
          abrirPagamentos("sale");
          informarPagamentoFeedback("Escolha a forma de pagamento antes de finalizar.");
        }
      });
    }
    document.querySelectorAll(".pdv-mode form[method='post']").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented) return;
        if (form.dataset.submitting === "1") {
          event.preventDefault();
          return;
        }
        form.dataset.submitting = "1";
        form.setAttribute("aria-busy", "true");
        var submitter = event.submitter || (form === finishForm ? confirmPaymentButton : form.querySelector("button[type='submit']"));
        if (submitter) {
          submitter.disabled = true;
          submitter.setAttribute("aria-busy", "true");
          submitter.dataset.originalHtml = submitter.innerHTML;
          submitter.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processando...';
        }
      });
    });
    document.querySelectorAll(".pdv-mode .content > .messages .message").forEach(function (message) {
      window.setTimeout(function () { message.remove(); }, message.classList.contains("error") ? 3800 : 1800);
    });
    atualizarAutorizacaoDesconto();
    atualizarCpfNaNota();
    atualizarResumoPdv();
    var blockingOverlay = (paymentModal && paymentModal.classList.contains("is-open")) || (postSaleModal && postSaleModal.classList.contains("is-open")) || modalAberto();
    if (davModal && davModal.dataset.openOnLoad === "1") abrirModalPdv("dav");
    if (!blockingOverlay) restaurarFocoPrincipalPdv();
  }
});


(function () {
  function visible(element) {
    return Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
  }

  function configureSupervisorCredential(form) {
    var username = form.querySelector("input[name='supervisor_usuario']");
    var password = form.querySelector("input[name='supervisor_senha']");
    if (!username || !password || form.hasAttribute("data-supervisor-credential-ready")) return;
    form.setAttribute("data-supervisor-credential-ready", "true");

    var block = document.createElement("div");
    block.className = "supervisor-credential-block";
    block.innerHTML =
      '<div class="supervisor-credential-heading"><i class="fa-solid fa-id-card"></i><span><strong>Cartão do supervisor</strong><small>Aproxime, passe ou leia o crachá. Login e senha continuam disponíveis.</small></span></div>' +
      '<div class="supervisor-credential-fields"><button type="button" class="secondary-button" data-supervisor-card-focus title="Ler credencial"><i class="fa-solid fa-wifi"></i> Ler cartão</button>' +
      '<input type="password" name="supervisor_credencial" class="no-upper" autocomplete="off" placeholder="Aguardando leitura" aria-label="Credencial do supervisor">' +
      '<input type="password" name="supervisor_pin" autocomplete="off" inputmode="numeric" placeholder="PIN, quando exigido" aria-label="PIN da credencial"></div>';

    var reference = username.closest("label") || username;
    reference.parentNode.insertBefore(block, reference);
    var credential = block.querySelector("input[name='supervisor_credencial']");
    var focusButton = block.querySelector("[data-supervisor-card-focus]");
    var usernameRequired = username.required;
    var passwordRequired = password.required;

    function updateMode() {
      var usingCard = Boolean(credential.value.trim());
      username.required = usingCard ? false : usernameRequired;
      password.required = usingCard ? false : passwordRequired;
      block.classList.toggle("has-credential", usingCard);
    }

    focusButton.addEventListener("click", function () {
      var api = window.pywebview && window.pywebview.api;
      if (!api || typeof api.readSupervisorCredential !== "function") {
        credential.focus();
        credential.select();
        return;
      }
      focusButton.disabled = true;
      api.readSupervisorCredential("").then(function (resultado) {
        if (resultado && resultado.status === "ok" && resultado.credencial) {
          window.deigoSupervisorCredential(resultado.credencial);
          return;
        }
        window.alert((resultado && resultado.mensagem) || "Não foi possível ler o cartão. Use o leitor em modo teclado.");
        credential.focus();
      }).catch(function () {
        window.alert("Leitor NFC indisponivel. Use o leitor em modo teclado ou informe login e senha.");
        credential.focus();
      }).finally(function () {
        focusButton.disabled = false;
      });
    });
    credential.addEventListener("input", updateMode);
    credential.addEventListener("change", updateMode);
    form.addEventListener("reset", function () { window.setTimeout(updateMode, 0); });
    updateMode();
  }

  function configureAllSupervisorCredentials(root) {
    (root || document).querySelectorAll("form").forEach(configureSupervisorCredential);
  }

  window.deigoSupervisorCredential = function (token) {
    var forms = Array.from(document.querySelectorAll("form[data-supervisor-credential-ready]"));
    var activeForm = document.activeElement && document.activeElement.closest("form[data-supervisor-credential-ready]");
    var form = activeForm || forms.find(visible);
    if (!form) return false;
    var input = form.querySelector("input[name='supervisor_credencial']");
    input.value = String(token || "").trim();
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
    return Boolean(input.value);
  };

  configureAllSupervisorCredentials(document);
  document.addEventListener("pdv:modal-opened", function (event) {
    configureAllSupervisorCredentials(event.target || document);
  });
})();
