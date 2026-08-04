document.addEventListener("DOMContentLoaded", function () {
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
        options.minimumInputLength = 2;
        options.ajax = {
          url: $field.data("ajax-url"),
          dataType: "json",
          delay: 180,
          data: function (params) {
            return { q: params.term || "" };
          },
          processResults: function (data) {
            return { results: data.results || [] };
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
    var button = form.querySelector("[data-cadastro-lookup-button]");
    var feedback = form.querySelector("[data-cadastro-lookup-feedback]");
    var cnpjInput = form.querySelector("[data-lookup-target='cnpj'], #id_cnpj");
    var cepInput = form.querySelector("[data-lookup-target='cep'], #id_cep_consulta");
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
      var fields = ["razao_social", "nome_fantasia", "nome", "cnpj", "telefone", "email", "endereco", "municipio", "uf", "codigo_municipio_ibge", "regime_tributario"];
      fields.forEach(function (field) {
        fillIfEmpty(field, data.dados[field]);
      });
      setFeedback(data.mensagem || "Cadastro encontrado e aplicado aos campos vazios.", false);
    }

    function runLookup() {
      if (!lookupUrl) return;
      var cnpjDigits = cnpjInput ? (cnpjInput.value || "").replace(/\D/g, "") : "";
      var cepDigits = cepInput ? (cepInput.value || "").replace(/\D/g, "") : "";
      var tipo = cnpjDigits.length === 14 ? "cnpj" : (cepDigits.length === 8 ? "cep" : "");
      var digits = tipo === "cnpj" ? cnpjDigits : cepDigits;
      if (!tipo) {
        setFeedback("Informe um CNPJ com 14 digitos ou um CEP com 8 digitos para consultar.", true);
        if (cnpjInput && cnpjDigits.length !== 14) cnpjInput.focus();
        else if (cepInput) cepInput.focus();
        return;
      }
      if (button) button.disabled = true;
      setFeedback("Consultando cadastro...", false);
      fetch(lookupUrl + "?" + tipo + "=" + encodeURIComponent(digits), { headers: { "Accept": "application/json" } })
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
          if (button) button.disabled = false;
        });
    }

    if (button) button.addEventListener("click", runLookup);
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

  if (document.body.classList.contains("pdv-mode")) {
    var buscaProduto = document.getElementById("id_busca");
    var quantidadeInput = document.getElementById("id_quantidade");
    var scaleButton = document.querySelector("[data-pdv-read-scale]");
    var scaleFeedback = document.getElementById("pdv-scale-feedback");
    var descontoInput = document.getElementById("id_desconto");
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
    var paymentDeliveryButton = document.getElementById("pdv-payment-delivery");
    var deliveryQuestion = document.getElementById("pdv-delivery-question");
    var deliveryQuestionConfirm = document.getElementById("pdv-confirm-delivery-question");
    var deliveryQuestionCancel = document.getElementById("pdv-cancel-delivery-question");
    var paymentRows = document.getElementById("pdv-payment-rows");
    var paymentTemplate = document.getElementById("pdv-payment-row-template");
    var pagamentoLancado = document.getElementById("pdv-pagamento-lancado");
    var pagamentoRestante = document.getElementById("pdv-pagamento-restante");
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
    var deliverySaveClient = document.querySelector('#pdv-modal-delivery input[name="salvar_cliente"]');
    var deliveryClientItems = [];
    var deliveryClientIndex = -1;
    var deliveryClientRequest = 0;
    var deliveryClientTimer = null;

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

    function selecionarClienteEntrega(cliente) {
      if (!cliente || !deliveryClientSearch || !deliveryClientId) return;
      deliveryClientId.value = cliente.id;
      deliveryClientSearch.value = cliente.nome || "";
      var deliveryPhone = document.querySelector('#pdv-modal-delivery input[name="telefone"]');
      var deliveryAddress = document.querySelector('#pdv-modal-delivery textarea[name="endereco_entrega"]');
      if (deliveryPhone) deliveryPhone.value = cliente.telefone || "";
      if (deliveryAddress) deliveryAddress.value = cliente.endereco || "";
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
          if (deliverySaveClient) deliverySaveClient.disabled = false;
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
        if ((event.key === "Enter" || event.key === "Tab") && deliveryClientIndex >= 0) {
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

    function abrirPagamentos() {
      if (!paymentModal) return;
      paymentModal.classList.add("is-open");
      paymentModal.setAttribute("aria-hidden", "false");
      atualizarAutorizacaoDesconto();
      atualizarResumoPdv();
      var firstSelect = paymentModal.querySelector("select");
      if (firstSelect) firstSelect.focus();
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
      informarPagamentoFeedback("Aguardando CPF/CNPJ no pinpad...");
      Promise.resolve(bridge({ tipo: (documentTypeInput && documentTypeInput.value) || "AUTO" })).then(function (resultado) {
        if (resultado && resultado.status === "ok") {
          if (documentTypeInput) documentTypeInput.value = resultado.tipo;
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
      var desconto = Math.max(decimalFromInput(descontoInput && descontoInput.value), 0);
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
      var deliveryForm = document.querySelector("#pdv-modal-delivery form");
      if (!deliveryForm) return;
      deliveryForm.querySelectorAll("[data-pdv-delivery-payment]").forEach(function (field) { field.remove(); });
      var paymentInfo = document.getElementById("pdv-delivery-cash-payment");
      if (!pagamentoNoCaixa) {
        if (paymentInfo) paymentInfo.hidden = true;
        return;
      }
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
      if (paymentInfo) {
        var paidSummary = document.getElementById("pdv-delivery-cash-payment-value");
        if (paidSummary) paidSummary.textContent = formatMoney(totalPagamentosLancados());
        paymentInfo.hidden = false;
      }
    }

    function abrirEntregaDoPagamento(pagamentoNoCaixa) {
      prepararPagamentoNoCaixaParaEntrega(Boolean(pagamentoNoCaixa));
      fecharPerguntaEntrega();
      fecharPagamentos();
      abrirModalPdv("delivery");
      var deliveryName = document.querySelector('#pdv-modal-delivery input[name="nome_cliente"]');
      if (deliveryName) deliveryName.focus();
    }

    function abrirPerguntaEntrega() {
      if (!deliveryQuestion) {
        if (finishForm) finishForm.requestSubmit();
        return;
      }
      var noOption = deliveryQuestion.querySelector('input[value="no"]');
      if (noOption) noOption.checked = true;
      deliveryQuestion.classList.add("is-open");
      deliveryQuestion.setAttribute("aria-hidden", "false");
      if (noOption) noOption.focus();
    }

    function fecharPerguntaEntrega() {
      if (!deliveryQuestion) return;
      deliveryQuestion.classList.remove("is-open");
      deliveryQuestion.setAttribute("aria-hidden", "true");
    }

    function confirmarPerguntaEntrega() {
      if (!deliveryQuestion) return;
      var escolha = deliveryQuestion.querySelector('input[name="pdv_delivery_choice"]:checked');
      if (escolha && escolha.value === "yes") {
        abrirEntregaDoPagamento(true);
        return;
      }
      fecharPerguntaEntrega();
      if (finishForm) finishForm.requestSubmit();
    }

    function finalizarVendaPdv() {
      if (!validarFinalizacaoVendaPdv()) return;
      abrirPerguntaEntrega();
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
      ["pagamento_status", "pagamento_transacao_externa_id", "pagamento_nsu", "pagamento_codigo_autorizacao", "pagamento_mensagem_processadora"].forEach(function (nome) {
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
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.processPayment;
      var input = row && row.querySelector("input[name='pagamento_valor']");
      var select = row && row.querySelector("select");
      if (!row || !input || !select) return;
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
      informarPagamentoFeedback(tipoTef === "PIX" ? "Gerando QR Code PIX..." : "Aguardando resposta da maquininha...");
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
          informarPagamentoFeedback("Pagamento " + tipoTef.replaceAll("_", " ") + " aprovado. Aut. " + resultado.codigo_autorizacao + ".");
          select.focus();
        })
        .catch(function (erro) {
          limparAutorizacaoPagamento(row, true);
          ocultarPixPanel();
          informarPagamentoFeedback("Não foi possível confirmar na maquininha: " + erro.message);
          select.focus();
        });
    }
    function fecharPagamentos() {
      if (!paymentModal) return;
      fecharEscolhaEletronica();
      ocultarPixPanel();
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
      } else {
        aplicarPaginacaoModal(modal);
      }
      selecionarPrimeiraLinhaVisivelModal(modal, false);
    }

    function fecharModalPdv() {
      pdvModals.forEach(function (modal) {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
      });
    }

    function abrirConferenciaEntrega(deliveryId) {
      var detailModal = document.getElementById("pdv-modal-delivery-detail");
      if (!detailModal || !deliveryId) return;
      detailModal.querySelectorAll("[data-delivery-detail]").forEach(function (detail) {
        detail.hidden = detail.getAttribute("data-delivery-detail") !== String(deliveryId);
      });
      abrirModalPdv("delivery-detail");
      var focusTarget = detailModal.querySelector('[data-delivery-detail="' + deliveryId + '"] button, [data-delivery-detail="' + deliveryId + '"] input, [data-delivery-detail="' + deliveryId + '"] select');
      if (focusTarget) focusTarget.focus();
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
      var label = modal.querySelector("[data-refund-selected-label]");
      var openLink = modal.querySelector("[data-refund-open]");
      var printButton = modal.querySelector("[data-refund-print]");
      var cancelForm = modal.querySelector("[data-refund-cancel-form]");
      if (label) label.textContent = row.getAttribute("data-sale-label") || row.textContent.trim();
      if (openLink) openLink.href = row.getAttribute("data-detail-url") || "#";
      if (printButton) {
        printButton.setAttribute("data-sale-print-url", row.getAttribute("data-sale-print-url") || "");
        printButton.setAttribute("data-sale-desktop-print-url", row.getAttribute("data-sale-desktop-print-url") || "");
      }
      if (cancelForm) cancelForm.action = row.getAttribute("data-cancel-url") || "#";
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
        if (autorizados && autorizados.length) {
          autorizados.forEach(function (row) { limparAutorizacaoPagamento(row); });
          ocultarPixPanel();
          informarPagamentoFeedback("O desconto alterou o total. Reprocesse os pagamentos eletrônicos.");
        }
        atualizarAutorizacaoDesconto();
        atualizarResumoPdv();
      });
    }
    if (recebidoInput) recebidoInput.addEventListener("input", atualizarResumoPdv);
    if (openPaymentButton) openPaymentButton.addEventListener("click", abrirPagamentos);
    if (closePaymentButton) closePaymentButton.addEventListener("click", fecharPagamentos);
    if (confirmPaymentButton) confirmPaymentButton.addEventListener("click", finalizarVendaPdv);
    if (finalizeButton) finalizeButton.addEventListener("click", abrirPagamentos);
    if (finishShortcut) finishShortcut.addEventListener("click", abrirPagamentos);
    if (captureDocumentButton) captureDocumentButton.addEventListener("click", capturarDocumentoPinpad);
    document.addEventListener("supermercado:desktop-ready", atualizarCapacidadeDocumentoPinpad);
    atualizarCapacidadeDocumentoPinpad();
    if (paymentDeliveryButton) paymentDeliveryButton.addEventListener("click", function () { abrirEntregaDoPagamento(false); });
    if (deliveryQuestionConfirm) deliveryQuestionConfirm.addEventListener("click", confirmarPerguntaEntrega);
    if (deliveryQuestionCancel) {
      deliveryQuestionCancel.addEventListener("click", function () {
        fecharPerguntaEntrega();
        if (confirmPaymentButton) confirmPaymentButton.focus();
      });
    }
    if (addPaymentButton) {
      addPaymentButton.addEventListener("click", function () {
        adicionarLinhaPagamento({ somenteSeRestante: true });
      });
    }
    if (scaleButton) scaleButton.addEventListener("click", lerPesoBalancaPdv);
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
      if (deliveryQuestion && deliveryQuestion.classList.contains("is-open")) {
        var deliveryOptions = Array.prototype.slice.call(deliveryQuestion.querySelectorAll('input[name="pdv_delivery_choice"]'));
        if (["ArrowUp", "ArrowLeft", "ArrowDown", "ArrowRight"].indexOf(key) !== -1) {
          event.preventDefault();
          var selectedIndex = deliveryOptions.findIndex(function (option) { return option.checked; });
          var direction = key === "ArrowUp" || key === "ArrowLeft" ? -1 : 1;
          var nextOption = deliveryOptions[(selectedIndex + direction + deliveryOptions.length) % deliveryOptions.length];
          if (nextOption) {
            nextOption.checked = true;
            nextOption.focus();
          }
          return;
        }
        if (key === "Tab") {
          var deliveryFocusable = Array.prototype.slice.call(deliveryQuestion.querySelectorAll('input:not([disabled]), button:not([disabled])'));
          var activeIndex = deliveryFocusable.indexOf(document.activeElement);
          var nextIndex = event.shiftKey ? activeIndex - 1 : activeIndex + 1;
          event.preventDefault();
          if (!deliveryFocusable.length) return;
          if (nextIndex < 0) nextIndex = deliveryFocusable.length - 1;
          if (nextIndex >= deliveryFocusable.length) nextIndex = 0;
          deliveryFocusable[nextIndex].focus();
          return;
        }
        if (key === "Escape") {
          event.preventDefault();
          fecharPerguntaEntrega();
          if (confirmPaymentButton) confirmPaymentButton.focus();
          return;
        }
        if (key === "Enter") {
          event.preventDefault();
          confirmarPerguntaEntrega();
          return;
        }
        return;
      }
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
          fecharPosVenda();
          if (buscaProduto) {
            buscaProduto.value = key;
            buscaProduto.focus();
          }
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
          if (modalAberto().id === "pdv-modal-delivery-detail") {
            abrirModalPdv("deliveries");
          } else {
            fecharModalPdv();
            focarBuscaProduto();
          }
        }
        return;
      }
      if (event.shiftKey && key.toLowerCase() === "m") {
        var menuLink = document.getElementById("pdv-menu-link");
        if (menuLink) {
          event.preventDefault();
          window.location.href = menuLink.href;
        }
        return;
      }
      if (event.ctrlKey && key.toLowerCase() === "e") {
        event.preventDefault();
        if (paymentModal && paymentModal.classList.contains("is-open")) fecharPagamentos();
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
        abrirModalPdv("deliveries");
        return;
      }
      if (event.shiftKey && key.toLowerCase() === "s") {
        var exitButton = document.getElementById("pdv-exit-button");
        if (exitButton) {
          event.preventDefault();
          exitButton.click();
        }
        return;
      }
      var activeModal = modalAberto();
      if (activeModal && activeModal.id === "pdv-modal-refunds") {
        var focoEmFormulario = document.activeElement && document.activeElement.closest && document.activeElement.closest(".pdv-refund-form");
        if (key === "F6") {
          event.preventDefault();
          var refundDetails = activeModal.querySelector("[data-refund-details]");
          var refundForm = activeModal.querySelector("[data-refund-cancel-form]");
          if (refundDetails) refundDetails.open = true;
          var motivo = refundForm && refundForm.querySelector("input[name='motivo']");
          if (motivo) motivo.focus();
          return;
        }
        if (event.ctrlKey && key === "Enter" && focoEmFormulario) {
          event.preventDefault();
          var formEstorno = activeModal.querySelector("[data-refund-cancel-form]");
          if (formEstorno) {
            if (formEstorno.requestSubmit) formEstorno.requestSubmit();
            else formEstorno.submit();
          }
          return;
        }
        if ((key === "ArrowUp" || key === "ArrowDown") && !focoEmFormulario) {
          event.preventDefault();
          moverSelecaoModal(activeModal, key === "ArrowUp" ? -1 : 1);
          return;
        }
        if ((key === "PageUp" || key === "PageDown") && !focoEmFormulario) {
          event.preventDefault();
          trocarPaginaModal(activeModal, key === "PageUp" ? -1 : 1);
          return;
        }
        if (key === "F10") {
          event.preventDefault();
          var botaoReimprimir = activeModal.querySelector("[data-refund-print]");
          if (botaoReimprimir) botaoReimprimir.click();
          return;
        }
        if (key === "Enter" && !focoEmFormulario) {
          event.preventDefault();
          var linkVenda = activeModal.querySelector("[data-refund-open]");
          if (linkVenda) window.location.href = linkVenda.href;
          return;
        }
      }
      if (activeModal && activeModal.id === "pdv-modal-delivery") {
        var focoEmEntrega = document.activeElement && document.activeElement.closest && document.activeElement.closest("#pdv-modal-delivery form");
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
        if (event.ctrlKey && key === "Enter" && focoEmEntrega) {
          event.preventDefault();
          var formEntrega = activeModal.querySelector("form");
          if (formEntrega) {
            if (formEntrega.requestSubmit) formEntrega.requestSubmit();
            else formEntrega.submit();
          }
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
        if (key === "F10") {
          event.preventDefault();
          var deliveryPrintButton = activeModal.querySelector("[data-delivery-print-url]");
          if (deliveryPrintButton) deliveryPrintButton.click();
          return;
        }
        var detailPanel = activeModal.querySelector("[data-delivery-detail]:not([hidden])");
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
      }
      if (activeModal && activeModal.id === "pdv-modal-boxes") {
        var focoEmCaixaForm = document.activeElement && document.activeElement.closest && document.activeElement.closest(".pdv-cash-close-form, .pdv-cash-movement-form");
        if (key === "F2") {
          event.preventDefault();
          var openCashLink = activeModal.querySelector("#pdv-open-cash-link");
          var suprimentoForm = activeModal.querySelector("[data-cash-movement-form='suprimento']");
          if (openCashLink) window.location.href = openCashLink.href;
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
      if (key === "F12" && !(paymentModal && paymentModal.classList.contains("is-open"))) {
        event.preventDefault();
        lerPesoBalancaPdv();
        return;
      }
      if (paymentModal && paymentModal.classList.contains("is-open")) {
        if (event.shiftKey && key === "F4") {
          event.preventDefault();
          capturarDocumentoPinpad();
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
          event.preventDefault();
          finalizarVendaPdv();
          return;
        }
      }
      if ((key === "ArrowUp" || key === "ArrowDown") && cartRows.length && !modalAberto()) {
        if (document.activeElement && document.activeElement.closest && document.activeElement.closest(".pdv-payment-row")) return;
        event.preventDefault();
        var atual = Math.max(0, selectedCartIndex);
        var destino = key === "ArrowUp" ? Math.max(0, atual - 1) : Math.min(cartRows.length - 1, atual + 1);
        selecionarItemCarrinho(cartRows[destino], true);
        return;
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
    atualizarAutorizacaoDesconto();
    atualizarResumoPdv();
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
        window.alert((resultado && resultado.mensagem) || "Nao foi possivel ler o cartao. Use o leitor em modo teclado.");
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
