// Run with: node --test backend/tests/frontend.test.cjs
// Requires Playwright and Chromium (see README).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { chromium } = require('playwright');

const escala = {
  tripulante: 'Tripulante de teste', cargo: 'Comandante', voo: 'TEST-001',
  horas: '12h00', limite_aplicado: 11, conforme: false,
  ocupacao_percentual: 109, rota: 'GRU → MAO', motivo: 'Limite excedido'
};

for (const file of ['docs/index.html', 'backend/static/index.html']) {
  test(`${file}: banco atualiza escalas e disrupções, inclusive resposta vazia`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      const errors = [];
      const requests = [];
      let escalas = [escala];
      let status = 200;
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('usuario_logado', JSON.stringify({ email: 'local@example.test', nome: 'Teste' }));
      });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        requests.push(url.href);
        if (url.href === 'http://localhost/') {
          return route.fulfill({ contentType: 'text/html', body: readFileSync(resolve(__dirname, '../..', file), 'utf8') });
        }
        if (url.pathname === '/api/perfil') return route.fulfill({ json: { nome: 'Teste', email: 'local@example.test', cargo: '', base: 'GRU' } });
        if (url.pathname === '/api/escalas/otimizar') {
          const publicada = { ...escala, voo: 'TEST-002', conforme: true, ocupacao_percentual: 9 };
          if (route.request().postDataJSON().gravar) escalas = [publicada];
          return route.fulfill({ json: {
            status: 'OPTIMAL', total_alocacoes: 1, conformidade: 100, wall_time_seconds: 0.1,
            alocacoes: [{ ...publicada, duracao_horas: 1, horas_antes: 0 }]
          } });
        }
        if (url.pathname === '/api/escalas') {
          return route.fulfill({ status, json: { data: '2026-10-19', total: escalas.length, conformes: 0, escalas } });
        }
        return route.fulfill({ json: {} });
      });
      await page.goto('http://localhost/');
      await page.waitForFunction(() => document.querySelectorAll('#crewTable tr').length === 1);
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 1);
      assert.match(await page.locator('#crewTable').innerText(), /Tripulante de teste/);
      assert.equal(await page.locator('#kpiActiveCount').innerText(), '1');
      assert.ok(requests.includes('http://localhost/api/escalas'));
      assert.ok(!requests.some(url => url.includes('onrender.com')));

      // Redraws triggered by settings/navigation must retain the loaded state.
      await page.evaluate(() => document.querySelector('[data-screen="disrupcoes"]').click());
      await page.evaluate(() => document.querySelector('[data-screen="escalas"]').click());
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.equal(await page.locator('#crewTable tr').count(), 1);
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 1);

      await page.evaluate(() => document.getElementById('btnSimular').click());
      await page.waitForFunction(() => document.getElementById('liveStatus').textContent.includes('Simulacao (nao publicada)'));
      assert.match(await page.locator('#crewTable').innerText(), /TEST-002/);
      assert.match(await page.locator('#disruptionsGrid').innerText(), /TEST-001/);
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.match(await page.locator('#crewTable').innerText(), /TEST-001/);

      await page.evaluate(() => document.getElementById('btnAplicar').click());
      await page.waitForFunction(() => document.getElementById('liveStatus').textContent.includes('Escala publicada:'));
      assert.match(await page.locator('#crewTable').innerText(), /TEST-002/);
      assert.match(await page.locator('#disruptionsGrid').innerText(), /TEST-002/);
      assert.equal(await page.locator('#kpiActiveCount').innerText(), '0');
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.match(await page.locator('#crewTable').innerText(), /TEST-002/);

      escalas = [];
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.equal(await page.locator('#crewTable tr').count(), 0);
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 0);
      assert.equal(await page.locator('#kpiActiveCount').innerText(), '0');
      assert.match(await page.locator('#historyCaptionText').innerText(), /Nenhuma escala publicada/);

      status = 500;
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.match(await page.locator('#liveStatus').innerText(), /Não foi possível carregar/);
      assert.deepEqual(errors, []);
    } finally {
      await browser.close();
    }
  });
}

for (const file of ['docs/index.html', 'backend/static/index.html']) {
  test(`${file}: perfil pendente não bloqueia interface e API sem resposta exibe erro`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      let slowScales = false;
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('usuario_logado', JSON.stringify({ email: 'local@example.test', nome: 'Teste' }));
        const timeout = AbortSignal.timeout.bind(AbortSignal);
        AbortSignal.timeout = () => timeout(500);
      });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.href === 'http://localhost/') {
          return route.fulfill({ contentType: 'text/html', body: readFileSync(resolve(__dirname, '../..', file), 'utf8') });
        }
        // Leave these requests pending to reproduce an unresponsive API.
        if (url.pathname === '/api/perfil') return;
        if (url.pathname === '/api/escalas') {
          if (slowScales) return;
          return route.fulfill({ json: { data: '2026-10-19', total: 1, conformes: 0, escalas: [escala] } });
        }
        return route.fulfill({ json: {} });
      });
      await page.goto('http://localhost/');
      await page.waitForFunction(() => document.querySelectorAll('#crewTable tr').length === 1);
      assert.match(await page.locator('#utcClock').innerText(), /\d{2}:\d{2}/);
      await page.evaluate(() => document.querySelector('.nav-btn[data-screen="escalas"]').click());
      assert.equal(await page.locator('#screen-escalas').isVisible(), true);
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 1);

      slowScales = true;
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.match(await page.locator('#liveStatus').innerText(), /Não foi possível carregar/);
      // Retain the last successful response when a refresh times out.
      assert.equal(await page.locator('#crewTable tr').count(), 1);
      assert.deepEqual(errors, []);
    } finally {
      await browser.close();
    }
  });
}

for (const folder of ['docs', 'backend/static']) {
  test(`${folder}: identidade vem da API, perfil só muda após salvar e logout não restaura usuário`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      const errors = [];
      let delayedScript;
      let saveFails = true;
      let logoutRequests = 0;
      let sessionRequests = 0;
      page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(() => {
        localStorage.setItem('usuario_logado', JSON.stringify({ nome: 'Marina em cache', email: 'old@example.test' }));
      });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== 'http://localhost') return route.abort();
        if (url.pathname === '/' || url.pathname === '/index.html' || url.pathname === '/login.html') {
          const name = url.pathname === '/login.html' ? 'login.html' : 'index.html';
          let html = readFileSync(resolve(__dirname, '../..', folder, name), 'utf8');
          if (name === 'index.html') {
            html = html.replace(/<script>([\s\S]*?)<\/script>/, (_, script) => {
              delayedScript = script; return '';
            });
          }
          return route.fulfill({ contentType: 'text/html', body: html });
        }
        if (url.pathname === '/api/perfil') {
          if (route.request().method() === 'POST') {
            if (saveFails) return route.fulfill({ status: 500, json: { erro: 'Falha de teste' } });
            return route.fulfill({ json: { perfil: { nome: 'Nome atualizado', email: 'real@example.test', cargo: '', base: 'GRU' } } });
          }
          return route.fulfill({ json: { nome: 'Usuário real', email: 'real@example.test', cargo: 'Operador', base: 'GRU' } });
        }
        if (url.pathname === '/api/auth/logout') {
          logoutRequests++;
          return route.fulfill({ status: 503, json: { erro: 'Servidor indisponível' } });
        }
        if (url.pathname === '/api/auth/sessao') {
          sessionRequests++;
          return route.fulfill({ json: { autenticado: true, usuario: { nome: 'Marina em cache', email: 'old@example.test' } } });
        }
        if (url.pathname === '/api/health') return route.fulfill({ json: { status: 'ok', banco: { ok: true } } });
        if (url.pathname === '/api/escalas') return route.fulfill({ json: { data: '2026-10-19', total: 0, conformes: 0, escalas: [] } });
        return route.fulfill({ json: {} });
      });
      await page.goto('http://localhost/');
      // Reproduce scripts injected after DOMContentLoaded by a deferred loader.
      await page.addScriptTag({ content: delayedScript });
      await page.waitForFunction(() => document.getElementById('headerUserName').textContent === 'Usuário real');
      assert.equal(await page.locator('#staticEmail').innerText(), 'real@example.test');
      await page.evaluate(() => document.querySelector('.nav-btn[data-screen="configuracoes"]').click());
      await page.evaluate(() => {
        const input = document.getElementById('inputName');
        input.value = 'Nome atualizado'; input.dispatchEvent(new Event('change'));
      });
      await page.waitForFunction(() => document.getElementById('sessionStatus').textContent.includes('Perfil não salvo'));
      assert.equal(await page.locator('#headerUserName').innerText(), 'Usuário real');
      saveFails = false;
      await page.evaluate(() => document.getElementById('inputName').dispatchEvent(new Event('change')));
      await page.waitForFunction(() => document.getElementById('headerUserName').textContent === 'Nome atualizado');
      await page.evaluate(() => document.getElementById('btnDiagnostico').click());
      await page.waitForFunction(() => document.getElementById('connectionStatus').textContent.includes('Banco: respondendo'));
      await page.evaluate(() => document.getElementById('btnLogout').click());
      await page.waitForURL('**/login.html?logout=1');
      await page.waitForFunction(() => document.getElementById('login-msg').textContent.includes('não foi confirmada'));
      assert.equal(await page.evaluate(() => localStorage.getItem('usuario_logado')), null);
      assert.equal(sessionRequests, 0);
      assert.equal(logoutRequests, 2);
      assert.deepEqual(errors, []);
    } finally {
      await browser.close();
    }
  });
}
