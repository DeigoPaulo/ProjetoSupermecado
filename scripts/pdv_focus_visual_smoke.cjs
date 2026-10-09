const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const cnpj = fs.readFileSync(path.join(root, 'static/js/cnpj-documento.js'), 'utf8');
const checkout = fs.readFileSync(path.join(root, 'static/js/pdv_checkout.js'), 'utf8');
const template = fs.readFileSync(path.join(root, 'templates/pdv/pdv.html'), 'utf8');
const start = template.indexOf('<div class="pdv-checkout"');
const end = template.indexOf('<button class="primary-button pdv-main-action"', start);
const checkoutHtml = template.slice(start, end);
const fixture = `<body class="pdv-mode">
  <div class="pdv-workspace" data-pdv-cash-open="1"></div>
  <form id="pdv-add-form"><input id="id_busca" name="busca"><input id="id_quantidade" name="quantidade"><button type="submit">Adicionar</button></form>
  <table><tbody><tr class="pdv-cart-row is-selected" tabindex="0" data-product-label="Teste" data-product-quantity="1" data-quantity-url="/pdv/item/quantidade/1/"><td><button type="button" data-pdv-edit-quantity>Editar quantidade</button></td></tr></tbody></table>
  <div class="pdv-summary" data-total="7,00"></div>
  <button id="pdv-finish-shortcut">F9</button>
  <form id="pdv-finish-form" action="/pdv/"><input name="caixa" value="1"><input name="checkout_idempotency_key" value="test-key"><input name="desconto" value="0"><select name="cliente"><option value="">Avulso</option></select><input name="vencimento_financeiro"><input name="documento_consumidor_tipo" id="id_documento_consumidor_tipo"><input name="documento_consumidor" id="id_documento_consumidor"><input type="radio" name="cpf_na_nota" value="NAO"><input type="radio" name="cpf_na_nota" value="CPF"><input type="radio" name="cpf_na_nota" value="CNPJ"><div id="pdv-payment-rows"><select name="pagamento_forma"><option value="1" data-payment-type="DINHEIRO">Dinheiro</option></select></div><template id="pdv-payment-row-template"><div class="pdv-payment-row"><select name="pagamento_forma"><option value="1" data-payment-type="DINHEIRO">Dinheiro</option></select><input name="pagamento_valor"></div></template>${checkoutHtml}</form>
  <div class="pdv-modal" id="pdv-modal-price" aria-hidden="true"><div><button data-pdv-modal-close>Fechar</button><input data-pdv-modal-filter></div></div>
  <div class="pdv-modal" id="pdv-modal-quantity" aria-hidden="true"><div><button data-pdv-modal-close>Fechar</button><form id="pdv-quantity-form"><strong id="pdv-quantity-product"></strong><strong id="pdv-quantity-current"></strong><input id="pdv-quantity-input"></form></div></div>
  <div id="pdv-post-sale-modal" aria-hidden="true"><button id="pdv-post-sale-close">Fechar</button></div>
  <details class="pdv-checkout-discount"><p id="pdv-checkout-discount-error"></p></details>
</body>`;

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PDV_BROWSER_BINARY || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    for (const width of [1366, 1920]) {
      const page = await browser.newPage({ viewport: { width, height: width === 1366 ? 768 : 1080 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.setContent(fixture);
      await page.addScriptTag({ content: cnpj });
      await page.addScriptTag({ content: app });
      await page.addScriptTag({ content: checkout });
      await page.evaluate(() => document.dispatchEvent(new Event('DOMContentLoaded')));
      assert.deepEqual(errors, [], 'PDV initialization must not throw');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      await page.evaluate(() => {
        window.scans = [];
        document.getElementById('pdv-add-form').addEventListener('submit', event => {
          event.preventDefault();
          window.scans.push(document.getElementById('id_busca').value);
          document.getElementById('id_busca').value = '';
          window.pdvRestoreFocus(true);
        });
      });
      for (const code of ['7894900704099', '7894900704105', '7894900704112']) {
        await page.keyboard.type(code);
        await page.keyboard.press('Enter');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      }
      assert.deepEqual(await page.evaluate(() => window.scans), ['7894900704099', '7894900704105', '7894900704112']);
      await page.locator('#id_quantidade').focus();
      await page.evaluate(() => window.pdvRestoreFocus());
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_quantidade');
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      await page.keyboard.press('F12');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_quantidade');
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      await page.locator('.pdv-cart-row').focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'pdv-quantity-input');
      await page.evaluate(() => window.pdvRestoreFocus());
      assert.equal(await page.evaluate(() => document.activeElement.id), 'pdv-quantity-input');
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      await page.keyboard.press('F3');
      assert.equal(await page.evaluate(() => document.activeElement.hasAttribute('data-pdv-modal-filter')), true);
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      await page.keyboard.press('F9');
      assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'CPF_ESCOLHA');
      assert.equal(await page.evaluate(() => document.activeElement.dataset.checkoutDocument), 'NAO');
      await page.keyboard.type('1234567890123');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);
      assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'CPF_ESCOLHA', 'scanner must not choose CPF/CNPJ');
      assert.equal(await page.evaluate(() => window.scans.length), 3, 'scanner must not add behind checkout');
      await page.keyboard.press('2');
      await page.waitForFunction(() => window.pdvSaleCheckout.state() === 'DOCUMENTO_CAPTURA');
      await page.keyboard.press('Escape');
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      await page.evaluate(() => {
        document.getElementById('pdv-post-sale-modal').classList.add('is-open');
        document.getElementById('pdv-post-sale-close').focus();
      });
      await page.keyboard.type('7894900704099');
      await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'id_busca');
      assert.equal(await page.evaluate(() => window.scans.at(-1)), '7894900704099');
      console.log(`PDV focus and scanner keyboard smoke OK at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
