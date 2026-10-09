const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const template = fs.readFileSync(path.join(root, 'templates/pdv/pdv.html'), 'utf8');
const start = template.indexOf('<div class="pdv-checkout"');
const end = template.indexOf('<button class="primary-button pdv-main-action"', start);
assert(start >= 0 && end > start);
const modal = template.slice(start, end);
const css = fs.readFileSync(path.join(root, 'static/css/custom.css'), 'utf8');
const script = fs.readFileSync(path.join(root, 'static/js/pdv_checkout.js'), 'utf8');
const fixture = `<body class="pdv-mode">
  <button type="button" data-pdv-modal-open="open-cash">Abrir caixa</button>
  <details class="pdv-checkout-discount"><p id="pdv-checkout-discount-error"></p></details>
  <div class="pdv-summary" data-total="61,08"></div>
  <form id="pdv-finish-form" action="/pdv/">
    <input name="action" value="finish">
    <input name="csrfmiddlewaretoken" value="test-csrf">
    <input name="caixa" value="1">
    <input name="checkout_idempotency_key" value="test-key">
    <input name="desconto" value="0">
    <select name="cliente"><option value="">Avulso</option><option value="1">Teste</option></select>
    <input name="vencimento_financeiro" value="2026-10-30">
    <input name="documento_consumidor_tipo" id="id_documento_consumidor_tipo">
    <input name="documento_consumidor" id="id_documento_consumidor">
    <input type="radio" name="cpf_na_nota" value="NAO">
    <input type="radio" name="cpf_na_nota" value="CPF">
    <input type="radio" name="cpf_na_nota" value="CNPJ">
    <div id="pdv-payment-rows"><div class="pdv-payment-row"><select name="pagamento_forma"><option value="">Forma</option><option value="1" data-payment-type="DINHEIRO">Dinheiro</option><option value="2" data-payment-type="DEBITO">Débito</option><option value="3" data-payment-type="CREDITO">Crédito</option><option value="4" data-payment-type="PIX">PIX</option><option value="5" data-payment-type="CREDIARIO">Crediário</option></select><input name="pagamento_valor"><input name="pagamento_status"></div></div>
    <template id="pdv-payment-row-template"><div class="pdv-payment-row"><select name="pagamento_forma"><option value="">Forma</option><option value="1" data-payment-type="DINHEIRO">Dinheiro</option><option value="2" data-payment-type="DEBITO">Débito</option><option value="3" data-payment-type="CREDITO">Crédito</option><option value="4" data-payment-type="PIX">PIX</option><option value="5" data-payment-type="CREDIARIO">Crediário</option></select><input name="pagamento_valor"><input name="pagamento_status"></div></template>
    ${modal}
  </form>
</body>`;

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PDV_BROWSER_BINARY || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await page.setContent(fixture);
    await page.addStyleTag({ content: css });
    await page.addScriptTag({ content: script });
    assert.equal(await page.evaluate(() => document.getElementById('pdv-finish-form').getAttribute('action')), '/pdv/');
    assert.equal(await page.evaluate(() => document.getElementById('pdv-finish-form').action.tagName), 'INPUT');
    await page.evaluate(() => {
      window.bridgeCalls = 0;
      window.SupermercadoDesktop = { captureConsumerDocument() { window.bridgeCalls++; }, printSale() {} };
      window.drawerCalls = 0;
      window.printCalls = 0;
      window.pdvRunPendingCashDrawer = () => { window.drawerCalls++; };
      window.pdvPrintSale = () => { window.printCalls++; };
      window.fetchCalls = [];
      window.fetch = async (url, options) => {
        window.fetchUrls = window.fetchUrls || [];
        window.fetchUrls.push(url);
        window.fetchCalls.push(Array.from(options.body.entries()));
        return { ok: true, text: async () => '<div id="pdv-post-sale-modal" data-sale-id="1" data-print-url="/pdv/recibo/1/" data-desktop-print-url="/pdv/impressao/1/"></div><script id="pdv-cash-drawer-action" type="application/json">{}</script>' };
      };
      window.pdvSaleCheckout.open();
    });
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'CPF_ESCOLHA');
    assert.equal(await page.locator('[data-checkout-panel="CPF_ESCOLHA"] [data-checkout-total]').textContent(), 'R$ 61,08');
    const shortcut = await page.locator('[data-checkout-document="NAO"] kbd').evaluate(el => ({ color: getComputedStyle(el).color, background: getComputedStyle(el).backgroundColor, width: el.getBoundingClientRect().width }));
    assert.notEqual(shortcut.color, shortcut.background, 'numeric shortcut must be legible');
    assert(shortcut.width >= 24, 'numeric shortcut must have a stable hit area');
    const size = await page.locator('.pdv-checkout-dialog').evaluate(el => ({ scroll: el.scrollHeight, client: el.clientHeight }));
    assert(size.scroll <= size.client, '1366x768 must not scroll');
    await page.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-1366.png') });
    await page.getByRole('button', { name: 'CPF 2' }).click();
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'DOCUMENTO_CAPTURA');
    await page.locator('#pdv-checkout-document-input').press('Escape');
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'CPF_ESCOLHA');
    await page.getByRole('button', { name: 'CPF 2' }).click();
    await page.locator('#pdv-checkout-document-input').fill('123');
    await page.locator('#pdv-checkout-document-input').press('Enter');
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'DOCUMENTO_CAPTURA');
    await page.locator('#pdv-checkout-document-input').fill('52998224725');
    await page.locator('#pdv-checkout-document-input').press('Enter');
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'FORMA_PAGAMENTO');
    assert.deepEqual(await page.locator('#pdv-checkout-methods button').allTextContents(), ['Dinheiro', 'Débito', 'Crédito', 'PIX', 'Outros']);
    await page.getByRole('button', { name: 'Débito' }).click();
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'ELETRONICO_INDISPONIVEL');
    assert.equal(await page.evaluate(() => window.bridgeCalls), 0);
    assert.equal(await page.evaluate(() => window.fetchCalls.length), 0);
    await page.locator('[data-checkout-methods-back]').click();
    await page.getByRole('button', { name: 'Dinheiro' }).click();
    assert.equal(await page.locator('#pdv-checkout-cash').evaluate(el => el === document.activeElement), true);
    const cashSize = await page.locator('.pdv-checkout-dialog').evaluate(el => ({ scroll: el.scrollHeight, client: el.clientHeight }));
    assert(cashSize.scroll <= cashSize.client, 'cash at 1366x768 must not scroll');
    await page.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-cash-1366.png') });
    await page.locator('#pdv-checkout-cash').fill('60');
    await page.locator('#pdv-checkout-cash').press('Enter');
    assert.equal(await page.evaluate(() => window.pdvSaleCheckout.state()), 'FORMA_PAGAMENTO');
    assert.equal(await page.locator('[data-checkout-paid]').textContent(), 'R$ 60,00');
    await page.getByRole('button', { name: 'Dinheiro' }).click();
    await page.locator('#pdv-checkout-cash').fill('1,08');
    await page.locator('#pdv-checkout-cash').press('Enter');
    await page.waitForFunction(() => window.pdvSaleCheckout.state() === 'CONCLUIDO');
    assert.equal(await page.locator('#pdv-checkout-sale-id').textContent(), 'Venda #1');
    assert.equal(await page.locator('#pdv-checkout-finished-change').isVisible(), false);
    assert.equal(await page.evaluate(() => window.fetchCalls.length), 1);
    assert.deepEqual(await page.evaluate(() => window.fetchUrls), ['/pdv/']);
    assert.equal(await page.evaluate(() => window.fetchCalls[0].find(([key]) => key === 'action')[1]), 'finish');
    assert.equal(await page.evaluate(() => window.fetchCalls[0].find(([key]) => key === 'csrfmiddlewaretoken')[1]), 'test-csrf');
    assert.equal(await page.evaluate(() => window.drawerCalls), 1);
    assert.equal(await page.evaluate(() => window.printCalls), 1);
    assert.equal(await page.evaluate(() => window.fetchCalls[0].filter(([key]) => key === 'pagamento_valor').map(([, value]) => value).join(',')), '60.00,1.08');
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-1920.png') });
    const retryPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await retryPage.setContent(fixture);
    await retryPage.addStyleTag({ content: css });
    await retryPage.addScriptTag({ content: script });
    await retryPage.evaluate(() => {
      window.fetchCalls = [];
      window.fetchUrls = [];
      window.fetchBodies = [];
      window.fetch = async (url, options) => {
        window.fetchUrls.push(url);
        window.fetchBodies.push(options.body);
        window.fetchCalls.push(Array.from(options.body.entries()));
        if (window.fetchCalls.length === 1) throw new Error('connection lost');
        return { ok: true, text: async () => '<div id="pdv-post-sale-modal" data-sale-id="1" data-print-url="/pdv/recibo/1/"></div>' };
      };
      window.pdvSaleCheckout.open();
    });
    await retryPage.getByRole('button', { name: 'CNPJ 3' }).click();
    await retryPage.locator('#pdv-checkout-document-input').fill('123');
    await retryPage.locator('#pdv-checkout-document-input').press('Enter');
    assert.equal(await retryPage.evaluate(() => window.pdvSaleCheckout.state()), 'DOCUMENTO_CAPTURA');
    await retryPage.locator('#pdv-checkout-document-input').fill('11444777000161');
    await retryPage.locator('#pdv-checkout-document-input').press('Enter');
    assert.equal(await retryPage.evaluate(() => window.pdvSaleCheckout.state()), 'FORMA_PAGAMENTO');
    await retryPage.getByRole('button', { name: 'Dinheiro' }).click();
    await retryPage.locator('#pdv-checkout-cash').fill('0');
    await retryPage.locator('#pdv-checkout-cash').press('Enter');
    assert.equal(await retryPage.evaluate(() => window.pdvSaleCheckout.state()), 'DINHEIRO');
    await retryPage.locator('#pdv-checkout-cash').fill('100');
    assert.equal(await retryPage.locator('#pdv-checkout-change').textContent(), 'R$ 38,92');
    await retryPage.evaluate(() => { const button = document.getElementById('pdv-checkout-cash-confirm'); button.click(); button.click(); });
    await retryPage.waitForFunction(() => !document.getElementById('pdv-checkout-retry').hidden);
    assert.equal(await retryPage.evaluate(() => window.pdvSaleCheckout.state()), 'PROCESSANDO');
    await retryPage.locator('#pdv-checkout-retry').click();
    await retryPage.waitForFunction(() => window.pdvSaleCheckout.state() === 'CONCLUIDO');
    assert.equal(await retryPage.evaluate(() => window.fetchCalls.length), 2);
    assert.deepEqual(await retryPage.evaluate(() => window.fetchUrls), ['/pdv/', '/pdv/']);
    assert.equal(await retryPage.evaluate(() => window.fetchBodies[0] === window.fetchBodies[1]), true);
    assert.deepEqual(await retryPage.evaluate(() => window.fetchCalls.map(call => call.find(([key]) => key === 'checkout_idempotency_key')[1])), ['test-key', 'test-key']);
    const cashPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await cashPage.setContent(fixture.replace('data-total="61,08"', 'data-total="21,00"'));
    await cashPage.addStyleTag({ content: css });
    await cashPage.addScriptTag({ content: script });
    await cashPage.evaluate(() => {
      window.cashRequests = [];
      window.fetch = async (url, options) => {
        window.cashRequests.push({ url, method: options.method, body: Array.from(options.body.entries()), snapshot: options.body });
        if (window.cashRequests.length === 1) return { ok: false, text: async () => '<h1>Not found</h1>' };
        return { ok: true, text: async () => '<div id="pdv-post-sale-modal" data-sale-id="1" data-print-url="/pdv/recibo/1/"></div>' };
      };
      window.pdvSaleCheckout.open();
    });
    await cashPage.locator('[data-checkout-document="NAO"]').click();
    await cashPage.getByRole('button', { name: 'Dinheiro' }).click();
    await cashPage.locator('#pdv-checkout-cash').fill('25,00');
    assert.equal(await cashPage.locator('#pdv-checkout-change').textContent(), 'R$ 4,00');
    await cashPage.locator('#pdv-checkout-cash').press('Enter');
    await cashPage.waitForFunction(() => !document.getElementById('pdv-checkout-retry').hidden);
    assert.match(await cashPage.locator('.pdv-checkout-summary').textContent(), /Pago/);
    assert.equal(await cashPage.locator('[data-checkout-paid]').textContent(), 'R$ 21,00');
    await cashPage.locator('#pdv-checkout-retry').click();
    await cashPage.waitForFunction(() => window.pdvSaleCheckout.state() === 'CONCLUIDO');
    assert.equal(await cashPage.locator('#pdv-checkout-sale-id').textContent(), 'Venda #1');
    assert.equal(await cashPage.locator('#pdv-checkout-finished-change-value').textContent(), 'R$ 4,00');
    assert.equal(await cashPage.locator('#pdv-checkout-finished-change').isVisible(), true);
    const cashRequests = await cashPage.evaluate(() => window.cashRequests.map(request => ({ url: request.url, method: request.method, body: request.body })));
    assert.deepEqual(cashRequests.map(request => request.url), ['/pdv/', '/pdv/']);
    assert.deepEqual(cashRequests.map(request => request.method), ['POST', 'POST']);
    assert.deepEqual(cashRequests.map(request => request.body.find(([key]) => key === 'checkout_idempotency_key')[1]), ['test-key', 'test-key']);
    assert.deepEqual(cashRequests.map(request => request.body.find(([key]) => key === 'action')[1]), ['finish', 'finish']);
    assert.deepEqual(cashRequests.map(request => request.body.find(([key]) => key === 'pagamento_valor')[1]), ['25.00', '25.00']);
    assert.equal(await cashPage.evaluate(() => window.cashRequests[0].snapshot === window.cashRequests[1].snapshot), true);
    const closedPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await closedPage.setContent(fixture.replace('<input name="caixa" value="1">', ''));
    await closedPage.addStyleTag({ content: css });
    await closedPage.addScriptTag({ content: script });
    await closedPage.evaluate(() => {
      window.openCashClicks = 0;
      document.querySelector('[data-pdv-modal-open="open-cash"]').addEventListener('click', () => { window.openCashClicks++; });
      window.pdvSaleCheckout.open();
    });
    assert.equal(await closedPage.evaluate(() => window.pdvSaleCheckout.state()), 'CAIXA_FECHADO');
    assert.equal(await closedPage.locator('[data-checkout-panel="CAIXA_FECHADO"]').isVisible(), true);
    assert.equal(await closedPage.getByRole('heading', { name: 'Caixa fechado, deseja abrir caixa?' }).isVisible(), true);
    assert.equal(await closedPage.evaluate(() => document.activeElement.id), 'pdv-checkout-closed-no');
    await closedPage.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-caixa-fechado-1366.png') });
    await closedPage.keyboard.press('2');
    await closedPage.waitForFunction(() => document.getElementById('pdv-checkout').hidden);
    assert.equal(await closedPage.locator('#pdv-checkout').isVisible(), false);
    assert.equal(await closedPage.evaluate(() => window.openCashClicks), 0);
    await closedPage.evaluate(() => window.pdvSaleCheckout.open());
    await closedPage.keyboard.press('Escape');
    assert.equal(await closedPage.locator('#pdv-checkout').isVisible(), false);
    await closedPage.evaluate(() => window.pdvSaleCheckout.open());
    await closedPage.keyboard.press('Shift+Tab');
    assert.equal(await closedPage.evaluate(() => document.activeElement.id), 'pdv-checkout-open-cash');
    await closedPage.keyboard.press('Enter');
    assert.equal(await closedPage.evaluate(() => window.openCashClicks), 1);
    assert.equal(await closedPage.locator('#pdv-checkout').isVisible(), false);
    await closedPage.evaluate(() => window.pdvSaleCheckout.open());
    await closedPage.keyboard.press('1');
    await closedPage.waitForFunction(() => window.openCashClicks === 2);
    assert.equal(await closedPage.evaluate(() => window.openCashClicks), 2);
    const noMethodsPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await noMethodsPage.setContent(fixture.replaceAll(/<option value="[1-5]" data-payment-type="[A-Z]+">[^<]*<\/option>/g, ''));
    await noMethodsPage.addStyleTag({ content: css });
    await noMethodsPage.addScriptTag({ content: script });
    await noMethodsPage.evaluate(() => window.pdvSaleCheckout.open());
    assert.equal(await noMethodsPage.evaluate(() => window.pdvSaleCheckout.state()), 'FORMAS_INDISPONIVEIS');
    assert.equal(await noMethodsPage.locator('[data-checkout-panel="FORMAS_INDISPONIVEIS"]').isVisible(), true);
    const vouchers = '<option value="6" data-payment-type="VALE_ALIMENTACAO">Vale alimentação</option><option value="7" data-payment-type="VALE_REFEICAO">Vale refeição</option>';
    const voucherFixture = fixture.replaceAll(/<option value="[1-5]" data-payment-type="[A-Z]+">[^<]*<\/option>/g, '').replaceAll('<option value="">Forma</option>', '<option value="">Forma</option>' + vouchers);
    const voucherPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await voucherPage.setContent(voucherFixture);
    await voucherPage.addStyleTag({ content: css });
    await voucherPage.addScriptTag({ content: script });
    await voucherPage.evaluate(() => {
      window.bridgeCalls = 0;
      window.SupermercadoDesktop = { tefCapabilities() { window.bridgeCalls++; } };
      window.fetchCalls = 0;
      window.fetch = () => { window.fetchCalls++; throw new Error('electronic payment must not submit'); };
      window.pdvSaleCheckout.open();
    });
    await voucherPage.locator('[data-checkout-document="NAO"]').click();
    assert.deepEqual(await voucherPage.locator('#pdv-checkout-methods button').allTextContents(), ['Débito', 'Crédito', 'PIX', 'Outros']);
    assert.equal(await voucherPage.evaluate(() => document.activeElement.textContent.trim()), 'Débito');
    await voucherPage.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-formas-homologacao-1366.png') });
    await voucherPage.keyboard.press('Enter');
    assert.equal(await voucherPage.evaluate(() => window.pdvSaleCheckout.state()), 'ELETRONICO_INDISPONIVEL');
    assert.equal(await voucherPage.evaluate(() => window.bridgeCalls), 0);
    assert.equal(await voucherPage.evaluate(() => window.fetchCalls), 0);
    await voucherPage.locator('[data-checkout-methods-back]').click();
    await voucherPage.locator('#pdv-checkout-methods button', { hasText: 'Crédito' }).click();
    assert.equal(await voucherPage.evaluate(() => window.pdvSaleCheckout.state()), 'ELETRONICO_INDISPONIVEL');
    await voucherPage.locator('[data-checkout-methods-back]').click();
    await voucherPage.locator('#pdv-checkout-methods button', { hasText: 'PIX' }).click();
    assert.equal(await voucherPage.evaluate(() => window.pdvSaleCheckout.state()), 'ELETRONICO_INDISPONIVEL');
    await voucherPage.locator('[data-checkout-methods-back]').click();
    await voucherPage.locator('#pdv-checkout-methods button', { hasText: 'Outros' }).click();
    assert.deepEqual(await voucherPage.locator('#pdv-checkout-other-methods button').allTextContents(), ['Vale alimentação', 'Vale refeição']);
    assert.equal(await voucherPage.evaluate(() => window.fetchCalls), 0);
    const pinpadPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await pinpadPage.setContent(fixture);
    await pinpadPage.addStyleTag({ content: css });
    await pinpadPage.evaluate(() => {
      window.captureCalls = [];
      window.paymentCalls = 0;
      window.SupermercadoDesktop = {
        tefCapabilities: async () => ({ status: 'ok', captura_documento_consumidor: true }),
        captureConsumerDocument: async payload => {
          window.captureCalls.push(payload);
          return { status: 'ok', tipo: payload.tipo, documento: payload.tipo === 'CPF' ? '52998224725' : '11444777000161' };
        },
        processPayment: () => { window.paymentCalls++; }
      };
    });
    await pinpadPage.addScriptTag({ content: script });
    await pinpadPage.evaluate(() => window.pdvSaleCheckout.open());
    await pinpadPage.keyboard.press('ArrowRight');
    assert.equal(await pinpadPage.evaluate(() => document.activeElement.dataset.checkoutDocument), 'CPF');
    await pinpadPage.keyboard.press('Enter');
    await pinpadPage.waitForFunction(() => window.pdvSaleCheckout.state() === 'FORMA_PAGAMENTO');
    assert.deepEqual(await pinpadPage.evaluate(() => window.captureCalls), [{ tipo: 'CPF' }]);
    assert.equal(await pinpadPage.locator('#id_documento_consumidor').inputValue(), '52998224725');
    await pinpadPage.locator('#pdv-checkout-methods button', { hasText: 'PIX' }).click();
    assert.equal(await pinpadPage.evaluate(() => window.pdvSaleCheckout.state()), 'ELETRONICO_INDISPONIVEL');
    assert.equal(await pinpadPage.evaluate(() => window.paymentCalls), 0);
    await pinpadPage.keyboard.press('Escape');
    await pinpadPage.keyboard.press('Escape');
    await pinpadPage.keyboard.press('Escape');
    await pinpadPage.keyboard.press('3');
    await pinpadPage.waitForFunction(() => window.pdvSaleCheckout.state() === 'FORMA_PAGAMENTO');
    assert.deepEqual(await pinpadPage.evaluate(() => window.captureCalls), [{ tipo: 'CPF' }, { tipo: 'CNPJ' }]);
    assert.equal(await pinpadPage.locator('#id_documento_consumidor').inputValue(), '11444777000161');
    const pinpadFailure = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await pinpadFailure.setContent(fixture);
    await pinpadFailure.addStyleTag({ content: css });
    await pinpadFailure.evaluate(() => {
      window.captureResult = { status: 'ok', tipo: 'CPF', documento: '123' };
      window.captureCalls = 0;
      window.SupermercadoDesktop = {
        tefCapabilities: async () => ({ status: 'ok', captura_documento_consumidor: true }),
        captureConsumerDocument: async () => { window.captureCalls++; return window.captureResult; }
      };
    });
    await pinpadFailure.addScriptTag({ content: script });
    await pinpadFailure.evaluate(() => window.pdvSaleCheckout.open());
    await pinpadFailure.keyboard.press('2');
    await pinpadFailure.waitForFunction(() => !document.getElementById('pdv-checkout-capture').hidden);
    assert.equal(await pinpadFailure.evaluate(() => window.pdvSaleCheckout.state()), 'DOCUMENTO_CAPTURA');
    assert.match(await pinpadFailure.locator('#pdv-checkout-document-error').textContent(), /Documento inválido/);
    await pinpadFailure.locator('#pdv-checkout-manual-button').click();
    assert.equal(await pinpadFailure.locator('#pdv-checkout-document-input').isVisible(), true);
    await pinpadFailure.locator('#pdv-checkout-document-input').fill('52998224725');
    await pinpadFailure.keyboard.press('Enter');
    assert.equal(await pinpadFailure.evaluate(() => window.pdvSaleCheckout.state()), 'FORMA_PAGAMENTO');
    await pinpadFailure.keyboard.press('Escape');
    await pinpadFailure.keyboard.press('Escape');
    await pinpadFailure.evaluate(() => { window.captureResult = { status: 'cancelado' }; });
    await pinpadFailure.keyboard.press('2');
    await pinpadFailure.waitForFunction(() => window.captureCalls === 2);
    await pinpadFailure.waitForFunction(() => window.pdvSaleCheckout.state() === 'CPF_ESCOLHA');
    await pinpadFailure.evaluate(() => { window.captureResult = { status: 'erro' }; });
    await pinpadFailure.keyboard.press('2');
    await pinpadFailure.waitForFunction(() => !document.getElementById('pdv-checkout-capture').hidden);
    assert.match(await pinpadFailure.locator('#pdv-checkout-capture-status').textContent(), /Não foi possível capturar/);
    const noCapability = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await noCapability.setContent(fixture);
    await noCapability.addStyleTag({ content: css });
    await noCapability.evaluate(() => {
      window.captureCalls = 0;
      window.SupermercadoDesktop = {
        tefCapabilities: async () => ({ status: 'ok', captura_documento_consumidor: false }),
        captureConsumerDocument: async () => { window.captureCalls++; }
      };
    });
    await noCapability.addScriptTag({ content: script });
    await noCapability.evaluate(() => window.pdvSaleCheckout.open());
    await noCapability.keyboard.press('2');
    await noCapability.waitForFunction(() => window.pdvSaleCheckout.state() === 'DOCUMENTO_CAPTURA' && !document.getElementById('pdv-checkout-manual-document').hidden && document.activeElement.id === 'pdv-checkout-document-input');
    assert.equal(await noCapability.evaluate(() => window.captureCalls), 0);
    assert.equal(await noCapability.evaluate(() => document.activeElement.id), 'pdv-checkout-document-input');
    const webPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await webPage.setContent(fixture);
    await webPage.addStyleTag({ content: css });
    await webPage.addScriptTag({ content: script });
    await webPage.evaluate(() => window.pdvSaleCheckout.open());
    await webPage.keyboard.press('2');
    await webPage.waitForFunction(() => window.pdvSaleCheckout.state() === 'DOCUMENTO_CAPTURA');
    assert.equal(await webPage.evaluate(() => document.activeElement.id), 'pdv-checkout-document-input');
    await webPage.setViewportSize({ width: 1920, height: 1080 });
    await webPage.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-documento-web-1920.png') });
    const pendingPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await pendingPage.setContent(fixture);
    await pendingPage.addStyleTag({ content: css });
    await pendingPage.evaluate(() => {
      window.SupermercadoDesktop = {
        tefCapabilities: async () => ({ status: 'ok', captura_documento_consumidor: true }),
        captureConsumerDocument: () => new Promise(resolve => { window.resolveCapture = resolve; })
      };
    });
    await pendingPage.addScriptTag({ content: script });
    await pendingPage.evaluate(() => window.pdvSaleCheckout.open());
    await pendingPage.keyboard.press('2');
    await pendingPage.waitForFunction(() => document.getElementById('pdv-checkout-capture-status').textContent.includes('Aguardando identificação'));
    await pendingPage.screenshot({ path: path.join(process.env.TEMP, 'pdv-checkout-pinpad-aguardando-1366.png') });
    await pendingPage.locator('#pdv-checkout-manual-button').click();
    await pendingPage.locator('#pdv-checkout-document-input').fill('52998224725');
    await pendingPage.evaluate(() => window.resolveCapture({ status: 'ok', tipo: 'CPF', documento: '11111111111' }));
    assert.equal(await pendingPage.locator('#pdv-checkout-document-input').inputValue(), '52998224725');
    assert.equal(await pendingPage.evaluate(() => window.pdvSaleCheckout.state()), 'DOCUMENTO_CAPTURA');
    console.log('Checkout visual: CPF/CNPJ, dinheiro, troco, parcial, retry idempotente, eletrônico bloqueado e conclusão OK');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
