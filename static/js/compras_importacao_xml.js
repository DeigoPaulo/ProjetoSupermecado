(function () {
  "use strict";

  const form = document.querySelector("[data-xml-assistant-form]");
  if (!form) return;
  const area = form.querySelector("[data-xml-analysis]");
  const itemsArea = form.querySelector("[data-xml-items]");
  const summary = form.querySelector("[data-xml-analysis-summary]");
  const errorArea = form.querySelector("[data-xml-error]");
  const submit = form.querySelector("[data-xml-submit]");
  let analysis = null;

  const escapeHtml = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  function setError(message) {
    errorArea.hidden = !message;
    errorArea.textContent = message || "";
  }

  function field(label, input) {
    return `<label class="form-field"><span>${label}</span>${input}</label>`;
  }

  function conversionFields(item, includeBase) {
    const base = includeBase ? field("Unidade-base", `
      <select data-decision="unidade_base" required>
        <option value="UN">UN</option><option value="KG">KG</option><option value="G">G</option>
        <option value="L">L</option><option value="M">M</option><option value="CX">CX</option>
        <option value="FD">FD</option><option value="PCT">PCT</option>
      </select>`) : "";
    return `${base}${field("Unidade de compra", `
      <select data-decision="unidade_compra" required>
        <option value="${escapeHtml(item.unidade_documental === "PAC" ? "PCT" : item.unidade_documental)}">${escapeHtml(item.unidade_documental)}</option>
      </select>`)}${field("Unidades contidas em cada embalagem", `
      <input type="number" min="0.001" step="0.001" inputmode="decimal" data-decision="fator" required>
      <small data-preview>Informe o fator para visualizar a conversão.</small>`)}
      <label class="checkbox-field"><input type="checkbox" data-decision="definir_como_padrao">
        <span>Usar também como embalagem padrão de compra</span></label>`;
  }

  function renderItem(item) {
    const blocked = !["RESOLVIDO", "PRODUTO_NAO_ENCONTRADO", "CONVERSAO_NAO_CONFIGURADA"].includes(item.status);
    let controls = "";
    if (item.status === "CONVERSAO_NAO_CONFIGURADA" && analysis.pode_configurar) {
      controls = `<input type="hidden" data-decision="acao" value="configurar">
        <div class="form-grid form-grid-inner">${conversionFields(item, false)}</div>`;
    } else if (item.status === "PRODUTO_NAO_ENCONTRADO" && analysis.pode_configurar) {
      controls = `<div class="field checkbox-field">
          <label><input type="radio" name="acao-${escapeHtml(item.numero)}" value="vincular" checked data-action-choice> Vincular produto existente</label>
          <label><input type="radio" name="acao-${escapeHtml(item.numero)}" value="cadastrar" data-action-choice> Cadastrar novo produto</label>
        </div>
        <div data-link-fields class="form-grid form-grid-inner">
          ${field("Produto existente", `<select class="select2-field" data-ajax-url="/estoque/produtos/busca.json" data-placeholder="Busque por nome ou código" data-decision="produto_id" required><option value=""></option></select>`)}
          ${conversionFields(item, false)}
        </div>
        <div data-new-fields class="form-grid form-grid-inner" hidden>
          ${field("Nome", `<input data-decision="nome" value="${escapeHtml(item.descricao)}" required>`)}
          ${field("Categoria", `<select class="select2-field" data-ajax-url="/produtos/categorias/busca.json" data-placeholder="Busque a categoria" data-decision="categoria_id" required><option value=""></option></select>`)}
          ${conversionFields(item, true)}
          ${field("Preço de venda", `<input type="number" min="0.01" step="0.01" inputmode="decimal" data-decision="preco_venda" required>`)}
          ${field("Código principal confirmado", `<input data-decision="codigo_principal" autocomplete="off">`)}
          <label class="checkbox-field"><input type="checkbox" data-decision="usar_cean_como_principal">
            <span>Confirmo o código comercial ${escapeHtml(item.ean_comercial || "não informado")} como código principal</span></label>
        </div>`;
    } else if (item.status !== "RESOLVIDO" && !analysis.pode_configurar && !blocked) {
      controls = "<p class=\"operation-notice\">Seu perfil pode analisar esta pendência, mas um usuário de Cadastros deve resolvê-la.</p>";
    }
    return `<article class="form-section" data-item-number="${escapeHtml(item.numero)}" data-status="${escapeHtml(item.status)}">
      <div class="form-section-header"><h3>${escapeHtml(item.descricao)}</h3>
        <p><strong>${escapeHtml(item.quantidade_documental)} ${escapeHtml(item.unidade_documental)}</strong> recebidos. ${escapeHtml(item.motivo)}</p></div>
      ${controls}
      <details><summary>Detalhes da NF-e</summary><p>
        Item ${escapeHtml(item.numero)} · código do fornecedor ${escapeHtml(item.codigo_fornecedor)} ·
        cEAN ${escapeHtml(item.ean_comercial || "sem GTIN")} · cEANTrib ${escapeHtml(item.ean_tributavel || "sem GTIN")}<br>
        NCM ${escapeHtml(item.ncm_fornecedor || "não informado")} e CEST ${escapeHtml(item.cest_fornecedor || "não informado")}
        foram informados pelo fornecedor na NF-e de entrada e não definem a tributação de venda.
      </p></details>
    </article>`;
  }

  function updateChoices() {
    itemsArea.querySelectorAll("[data-item-number]").forEach((panel) => {
      const selected = panel.querySelector("[data-action-choice]:checked");
      if (!selected) return;
      const linking = selected.value === "vincular";
      panel.querySelector("[data-link-fields]").hidden = !linking;
      panel.querySelector("[data-new-fields]").hidden = linking;
      panel.querySelectorAll("[data-link-fields] [required]").forEach((field) => { field.disabled = !linking; });
      panel.querySelectorAll("[data-new-fields] [required]").forEach((field) => { field.disabled = linking; });
    });
  }

  function updatePreview(event) {
    if (!event.target.matches('[data-decision="fator"]')) return;
    const panel = event.target.closest("[data-item-number]");
    const item = analysis.itens.find((entry) => String(entry.numero) === panel.dataset.itemNumber);
    const factor = Number(String(event.target.value).replace(",", "."));
    const quantity = Number(item.quantidade_documental);
    const output = event.target.parentElement.querySelector("[data-preview]");
    output.textContent = Number.isFinite(factor) && factor > 0
      ? `${item.quantidade_documental} ${item.unidade_documental} × ${factor} = ${(quantity * factor).toFixed(3)} unidades-base. O servidor recalculará o valor.`
      : "Informe o fator para visualizar a conversão.";
  }

  function render(data) {
    analysis = data;
    area.hidden = false;
    summary.textContent = `NF-e ${data.numero_documento}, ${data.fornecedor.nome}. Revise apenas os itens pendentes.`;
    itemsArea.innerHTML = data.itens.map(renderItem).join("");
    updateChoices();
    itemsArea.querySelectorAll("[data-action-choice]").forEach((field) => field.addEventListener("change", updateChoices));
    itemsArea.addEventListener("input", updatePreview);
    if (typeof window.SupermercadoInitSelect2 === "function") window.SupermercadoInitSelect2();
    submit.innerHTML = '<i class="fa-solid fa-check"></i> Confirmar e criar rascunho';
    submit.disabled = !data.todos_resolvidos && (!data.pode_configurar || data.itens.some((item) => !["RESOLVIDO", "PRODUTO_NAO_ENCONTRADO", "CONVERSAO_NAO_CONFIGURADA"].includes(item.status)));
    area.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function decisions() {
    return analysis.itens.filter((item) => item.status !== "RESOLVIDO").map((item) => {
      const panel = itemsArea.querySelector(`[data-item-number="${CSS.escape(String(item.numero))}"]`);
      const choice = panel.querySelector("[data-action-choice]:checked");
      const activeArea = choice && choice.value === "cadastrar" ? panel.querySelector("[data-new-fields]")
        : choice ? panel.querySelector("[data-link-fields]") : panel;
      const result = { numero: item.numero, acao: choice ? choice.value : "configurar" };
      activeArea.querySelectorAll("[data-decision]").forEach((field) => {
        result[field.dataset.decision] = field.type === "checkbox" ? field.checked : field.value;
      });
      return result;
    });
  }

  async function post(action) {
    setError("");
    submit.disabled = true;
    const data = new FormData(form);
    data.set("acao", action);
    if (action === "confirmar") {
      data.set("hash_sha256", analysis.hash_sha256);
      data.set("decisoes", JSON.stringify(decisions()));
    }
    try {
      const response = await fetch(form.action || window.location.href, { method: "POST", body: data, headers: { "X-Requested-With": "XMLHttpRequest" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.erro || "Não foi possível processar a NF-e.");
      if (payload.redirect) window.location.assign(payload.redirect);
      else render(payload);
    } catch (error) {
      setError(error.message);
      submit.disabled = false;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    post(analysis ? "confirmar" : "analisar");
  });
  form.addEventListener("change", (event) => {
    if (event.target.name === "arquivo_xml" && analysis) {
      analysis = null;
      area.hidden = true;
      submit.disabled = false;
      submit.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Analisar NF-e';
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && analysis) {
      analysis = null;
      area.hidden = true;
      submit.disabled = false;
      submit.focus();
    }
  });
})();
