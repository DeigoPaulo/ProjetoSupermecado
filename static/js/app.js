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

  function imprimirCupomVenda(url, desktopUrl) {
    var desktopBridge = window.SupermercadoDesktop && window.SupermercadoDesktop.printSale;
    if (desktopBridge && desktopUrl && window.fetch) {
      window.fetch(desktopUrl, { credentials: "same-origin" })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          var impressao = payload && payload.impressao;
          if (impressao && impressao.mensagem && !impressao.impressora_configurada) {
            window.alert(impressao.mensagem);
            imprimirCupomFallback(url);
            return null;
          }
          return desktopBridge(payload);
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
          window.alert("Não foi possivel aplicar a receita: " + error.message);
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
        if (feedback) feedback.textContent = "Impressao direta disponível somente no aplicativo desktop. Use a impressão pelo navegador neste computador.";
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
          if (feedback) feedback.textContent = "Etiquetas enviadas para " + resultado.impressora + ".";
        }).catch(function (erro) {
          if (feedback) feedback.textContent = "Falha na impressão direta: " + erro.message;
        }).finally(function () {
          labelsNativePrint.disabled = false;
        });
      } catch (erro) {
        labelsNativePrint.disabled = false;
        if (feedback) feedback.textContent = "Não foi possivel preparar o lote: " + erro.message;
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
          if (!response.ok) throw new Error("Não foi possivel carregar a etiqueta de teste.");
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
            if (!response.ok) throw new Error(payload.mensagem || "Nao foi possivel consultar o cadastro.");
            return payload;
          });
        })
        .then(function (payload) {
          if (payload.dados) {
            applyLookupData(payload);
            return;
          }
          setFeedback(payload.mensagem || "Cadastro nao encontrado localmente.", payload.status === "invalid");
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
      var msg = form.getAttribute("data-msg") || "Confirma esta operacao?";
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
        idempotency_key: [
          "refund",
          form.getAttribute("data-refund-transacao") || "",
          form.getAttribute("data-refund-valor") || "",
        ].join(":"),
      }))
        .then(function (resultado) {
          if (!resultado || resultado.status !== "ok" || !resultado.estornado) {
            throw new Error((resultado && resultado.mensagem) || "Estorno nao confirmado pela maquininha.");
          }
          var autorizacao = form.querySelector("input[name='autorizacao']");
          var mensagem = form.querySelector("input[name='mensagem_processadora']");
          if (autorizacao && !autorizacao.value.trim()) {
            autorizacao.value = resultado.codigo_autorizacao || resultado.nsu || resultado.estorno_transacao_id || "";
          }
          if (mensagem) {
            mensagem.value = resultado.mensagem_processadora || "Estorno aprovado pela maquininha.";
          }
          form.dataset.tefRefundReady = "1";
          form.submit();
        })
        .catch(function (erro) {
          window.alert("Nao foi possivel confirmar o estorno na maquininha: " + erro.message);
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
      var mensagem = resultado.mensagem || "Não foi possivel ler a balança. Digite a quantidade manualmente.";
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
      var termosPorTipo = {
        crédito: ["crédito", "cartao de crédito"],
        débito: ["débito", "cartao de débito"],
        pix: ["pix"],
      };
      var termos = termosPorTipo[tipo] || [];
      var linha = prepararLinhaParaPagamento();
      var select = linha && linha.querySelector("select");
      var input = linha && linha.querySelector("input[name='pagamento_valor']");
      if (!select || !input) return;
      var opcao = Array.prototype.find.call(select.options, function (item) {
        var nome = item.textContent.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        return termos.some(function (termo) { return nome.includes(termo); });
      });
      if (!opcao) {
        informarPagamentoFeedback("Forma eletrônica não cadastrada para " + tipo + ".");
        select.focus();
        return;
      }
      select.value = opcao.value;
      input.value = valorRestantePagamento().toFixed(2);
      fecharEscolhaEletronica();
      atualizarResumoPdv();
      processarPagamentoEletronico(linha, tipo);
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

    function processarPagamentoEletronico(row, tipo) {
      var bridge = window.SupermercadoDesktop && window.SupermercadoDesktop.processPayment;
      var input = row && row.querySelector("input[name='pagamento_valor']");
      var select = row && row.querySelector("select");
      if (!row || !input || !select) return;
      limparAutorizacaoPagamento(row, true);
      if (!bridge) {
        informarPagamentoFeedback("Maquininha disponível somente no app desktop. Configure o terminal ou use uma forma manual.");
        select.focus();
        return;
      }
      var valor = Math.max(decimalFromInput(input.value), 0).toFixed(2);
      if (valor <= 0) {
        informarPagamentoFeedback("Informe o valor antes de chamar a maquininha.");
        input.focus();
        return;
      }
      var assinaturaRequisicao = tipo + "|" + valor;
      if (!row.dataset.tefRequestKey || row.dataset.tefRequestSignature !== assinaturaRequisicao) {
        row.dataset.tefRequestKey = window.crypto && window.crypto.randomUUID
          ? window.crypto.randomUUID()
          : "pdv-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        row.dataset.tefRequestSignature = assinaturaRequisicao;
      }
      informarPagamentoFeedback("Aguardando resposta da maquininha...");
      Promise.resolve(bridge.call(window.SupermercadoDesktop, {
        tipo: tipo,
        valor: valor,
        idempotency_key: row.dataset.tefRequestKey,
      }))
        .then(function (resultado) {
          if (!resultado || resultado.status !== "ok" || !resultado.aprovado) {
            throw new Error((resultado && resultado.mensagem) || "Pagamento recusado ou não confirmado.");
          }
          aplicarAutorizacaoPagamento(row, resultado);
          informarPagamentoFeedback("Pagamento " + tipo.toUpperCase() + " aprovado. Aut. " + resultado.codigo_autorizacao + ".");
          select.focus();
        })
        .catch(function (erro) {
          limparAutorizacaoPagamento(row, true);
          informarPagamentoFeedback("Não foi possivel confirmar na maquininha: " + erro.message);
          select.focus();
        });
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

    function imprimirUltimaVenda() {
      if (!postSaleModal) return;
      var url = postSaleModal.getAttribute("data-print-url");
      var desktopUrl = postSaleModal.getAttribute("data-desktop-print-url");
      imprimirCupomVenda(url, desktopUrl);
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

    if (descontoInput) descontoInput.addEventListener("input", atualizarResumoPdv);
    if (recebidoInput) recebidoInput.addEventListener("input", atualizarResumoPdv);
    if (openPaymentButton) openPaymentButton.addEventListener("click", abrirPagamentos);
    if (closePaymentButton) closePaymentButton.addEventListener("click", fecharPagamentos);
    if (confirmPaymentButton) confirmPaymentButton.addEventListener("click", finalizarVendaPdv);
    if (finalizeButton) finalizeButton.addEventListener("click", abrirPagamentos);
    if (finishShortcut) finishShortcut.addEventListener("click", abrirPagamentos);
    if (addPaymentButton) {
      addPaymentButton.addEventListener("click", function () {
        adicionarLinhaPagamento({ somenteSeRestante: true });
      });
    }
    if (scaleButton) scaleButton.addEventListener("click", lerPesoBalancaPdv);
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
        var pageButton = event.target.closest("[data-pdv-page]");
        if (pageButton && modal.contains(pageButton)) {
          trocarPaginaModal(modal, pageButton.getAttribute("data-pdv-page") === "prev" ? -1 : 1);
          return;
        }
        var modalRow = event.target.closest(".pdv-modal-row");
        if (modalRow && modal.contains(modalRow)) selecionarLinhaModal(modal, modalRow, false);
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
        if (electronicChoice && electronicChoice.classList.contains("is-open") && ["F1", "F2", "F3"].indexOf(key) !== -1) {
          event.preventDefault();
          if (key === "F1") selecionarPagamentoEletronico("crédito");
          if (key === "F2") selecionarPagamentoEletronico("débito");
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
    atualizarResumoPdv();
  }
});
