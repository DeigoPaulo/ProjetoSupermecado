const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const app = fs.readFileSync(path.join(__dirname, '..', 'static/js/app.js'), 'utf8');
const cnpj = fs.readFileSync(path.join(__dirname, '..', 'static/js/cnpj-documento.js'), 'utf8');
const fixture = `<body class="pdv-mode">
  <div class="pdv-workspace" data-pdv-cash-open="1"></div>
  <form id="pdv-add-form"><input id="id_busca" name="busca"><input id="id_quantidade" name="quantidade"></form>
  <div class="pdv-summary" data-total="7,00"></div>
  <button data-pdv-modal-open="delivery">Entrega</button>
  <div class="pdv-modal" id="pdv-modal-delivery" aria-hidden="true"><div class="pdv-modal-dialog">
    <header><button type="button" data-pdv-modal-close>Fechar</button></header>
    <form data-quote-url="/cotacao.json">
      <input name="cliente" type="hidden"><input name="endereco_entrega" type="hidden"><input name="bairro_entrega" type="hidden">
      <section data-delivery-stage="0"><div class="pdv-delivery-client-field"><input name="nome_cliente" data-delivery-client-search required></div>
        <input name="telefone"><select name="documento_cliente_tipo"><option value="NAO_IDENTIFICADO">Não identificado</option><option value="CPF">CPF</option><option value="CNPJ">CNPJ</option></select><input name="documento_cliente"></section>
      <section data-delivery-stage="1" hidden>
        <label id="pdv-delivery-saved-choice" hidden><input type="radio" name="delivery_address_mode" value="saved"><span id="pdv-delivery-saved-address"></span></label>
        <label><input type="radio" name="delivery_address_mode" value="other" checked>Outro endereço</label>
        <div id="pdv-delivery-address-fields"><input name="entrega_cep"><input name="entrega_logradouro"><input name="entrega_numero"><input name="entrega_bairro"><input name="entrega_municipio"><input name="entrega_uf"></div>
        <input name="distancia_entrega_km"><input name="observacoes"><input name="salvar_cliente" type="checkbox">
      </section>
      <section data-delivery-stage="2" hidden><div class="pdv-delivery-quote"><span id="pdv-delivery-subtotal"></span><span id="pdv-delivery-frete"></span><span id="pdv-delivery-total"></span><span id="pdv-delivery-quote-feedback"></span></div>
        <label><input name="modo_pagamento" type="radio" value="NA_ENTREGA" checked>Na entrega</label>
      </section>
      <button id="pdv-delivery-back" type="button" hidden>Voltar</button><button id="pdv-delivery-continue" type="button">Continuar</button>
    </form>
  </div></div>
</body>`;

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PDV_BROWSER_BINARY || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    for (const width of [1366, 1920]) {
      const page = await browser.newPage({ viewport: { width, height: width === 1366 ? 768 : 1080 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.setContent(fixture);
      await page.evaluate(() => {
        window.deliverySubmits = 0;
        window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ subtotal: '7.00', frete: '0.00', total: '7.00', regra: 'Teste' }) });
        document.querySelector('#pdv-modal-delivery form').addEventListener('submit', event => {
          event.preventDefault();
          window.deliverySubmits += 1;
        });
      });
      await page.addScriptTag({ content: cnpj });
      await page.addScriptTag({ content: app });
      await page.evaluate(() => document.dispatchEvent(new Event('DOMContentLoaded')));
      assert.deepEqual(errors, [], 'PDV initialization must not throw');

      await page.keyboard.press('Control+e');
      assert.equal(await page.locator('#pdv-modal-delivery').evaluate(el => el.classList.contains('is-open')), true);
      await page.locator('[name="nome_cliente"]').focus();
      await page.keyboard.press('Control+Enter');
      assert.equal(await page.locator('[data-delivery-stage="0"]').isVisible(), true, 'invalid client must not advance');
      await page.locator('[name="nome_cliente"]').fill('Cliente de teste');
      await page.locator('#pdv-modal-delivery header button').focus();
      await page.keyboard.press('Control+Enter');
      assert.equal(await page.locator('[data-delivery-stage="1"]').isVisible(), true, 'header focus advances');

      await page.locator('#pdv-delivery-continue').focus();
      await page.keyboard.press('Control+Enter');
      assert.equal(await page.locator('[data-delivery-stage="1"]').isVisible(), true, 'invalid address must not advance');
      await page.locator('[name="entrega_cep"]').fill('74000000');
      await page.locator('[name="entrega_logradouro"]').fill('Rua Teste');
      await page.locator('[name="entrega_numero"]').fill('10');
      await page.locator('[name="entrega_bairro"]').fill('Centro');
      await page.locator('[name="entrega_municipio"]').fill('Goiânia');
      await page.locator('[name="entrega_uf"]').fill('GO');
      await page.locator('[name="entrega_bairro"]').focus();
      await page.keyboard.press('Control+Enter');
      assert.equal(await page.locator('[data-delivery-stage="2"]').isVisible(), true, 'input focus advances');
      assert.equal(await page.locator('[name="bairro_entrega"]').inputValue(), 'Centro');
      await page.locator('[name="modo_pagamento"]').focus();
      await page.keyboard.press('Control+Enter');
      await page.keyboard.press('Control+Enter');
      await page.waitForFunction(() => window.deliverySubmits === 1);
      assert.equal(await page.evaluate(() => window.deliverySubmits), 1, 'submit happens only once');
      assert.deepEqual(errors, [], 'keyboard flow must not throw');
      console.log(`Delivery keyboard smoke OK at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
