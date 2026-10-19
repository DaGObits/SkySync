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
  test(`${file}: escalas e ocorrências carregam de fontes independentes`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      const errors = [];
      const requests = [];
      let escalas = [escala];
      let ocorrencias = [{ id: 1, voo: "TEST-001", descricao: "Manutenção operacional", risco: "alto", rota: "GRU → MAO" }];
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
        if (url.pathname === '/api/disrupcoes') return route.fulfill({ json: { total: ocorrencias.length, retornados: ocorrencias.length, disrupcoes: ocorrencias } });
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
      assert.match(await page.locator('#disruptionsGrid').innerText(), /TEST-001/);
      assert.equal(await page.locator('#kpiActiveCount').innerText(), '1');
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.match(await page.locator('#crewTable').innerText(), /TEST-002/);

      escalas = [];
      await page.evaluate(() => window.carregarEscalasDoBanco(true));
      assert.equal(await page.locator('#crewTable tr').count(), 0);
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 1);
      ocorrencias = [];
      await page.evaluate(() => window.carregarDisrupcoes());
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
        if (url.pathname === '/api/disrupcoes') return route.fulfill({ json: { total: 1, retornados: 1, disrupcoes: [{ id: 1, voo: 'TEST-001', descricao: 'Atraso operacional', risco: 'alto' }] } });
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

for (const file of ['docs/index.html', 'backend/static/index.html']) {
  test(`${file}: registra e filtra disrupção sem escala, preserva texto e distingue falha`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      let ocorrencias = [];
      let status = 200;
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.href === 'http://localhost/') return route.fulfill({ contentType: 'text/html', body: readFileSync(resolve(__dirname, '../..', file), 'utf8') });
        if (url.pathname === '/api/perfil') return route.fulfill({ json: { nome: 'Operador', email: 'local@example.test' } });
        if (url.pathname === '/api/escalas') return route.fulfill({ json: { total: 0, data: '2026-10-19', escalas: [] } });
        if (url.pathname === '/api/disrupcoes') {
          if (route.request().method() === 'POST') {
            const dado = { ...route.request().postDataJSON(), id: 1 };
            ocorrencias.push(dado);
            return route.fulfill({ status: 201, json: { disrupcao: dado } });
          }
          return route.fulfill({ status, json: { total: ocorrencias.length, retornados: ocorrencias.length, disrupcoes: ocorrencias } });
        }
        return route.fulfill({ json: {} });
      });
      await page.goto('http://localhost/');
      await page.waitForFunction(() => document.getElementById('disruptionsStatus').textContent.includes('0 de 0'));
      assert.match(await page.locator('#disruptionsGrid').innerText(), /Nenhuma ocorrência registrada/);
      await page.locator('.nav-btn[data-screen="disrupcoes"]').click();
      await page.locator('#screen-disrupcoes summary').click();
      await page.locator('#disrupcaoVoo').fill('TEST-900');
      const descricao = '<img src=x onerror="window.injetado=true"> Manutenção';
      await page.locator('#disrupcaoDescricao').fill(descricao);
      await page.locator('#disrupcaoRisco').selectOption('alto');
      await page.locator('#btnRegistrarDisrupcao').click();
      await page.waitForFunction(() => document.querySelectorAll('#disruptionsGrid .alert-card').length === 1);
      assert.equal(await page.locator('#crewTable tr').count(), 0);
      assert.match(await page.locator('#disruptionsGrid').innerText(), /TEST-900/);
      assert.equal(await page.locator('#disruptionsGrid img').count(), 0);
      assert.equal(await page.evaluate(() => Boolean(window.injetado)), false);
      assert.equal(await page.locator('#kpiActiveCount').innerText(), '1');
      await page.locator('.filter-btn[data-filter="baixo"]').click();
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 0);
      assert.match(await page.locator('#disruptionsGrid').innerText(), /Nenhuma ocorrência nesta categoria/);
      await page.locator('.filter-btn[data-filter="all"]').click();
      status = 404;
      await page.locator('#btnAtualizarDisrupcoes').click();
      await page.waitForFunction(() => document.getElementById('disruptionsStatus').textContent.includes('Publique'));
      // A failed refresh must preserve the last successfully loaded events.
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 1);
      status = 200;
      await page.reload();
      await page.waitForFunction(() => document.querySelectorAll('#disruptionsGrid .alert-card').length === 1);
    } finally { await browser.close(); }
  });
}

for (const file of ['docs/index.html', 'backend/static/index.html']) {
  test(`${file}: mostra configuração pendente e cobertura parcial da importação`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      let configurada = false;
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.href === 'http://localhost/') return route.fulfill({ contentType: 'text/html', body: readFileSync(resolve(__dirname, '../..', file), 'utf8') });
        if (url.pathname === '/api/disrupcoes/importacao/status') return route.fulfill({ json: {
          configurada, aeroporto: 'GRU', ultimo_sucesso: '2026-10-19T12:00:00+00:00', parcial: true,
          agendador_ativo: true, ultimo_erro: 'Cota do plano Aviationstack atingida.'
        } });
        if (url.pathname === '/api/disrupcoes') return route.fulfill({ json: { total: 1, retornados: 1, disrupcoes: [{
          id: 1, voo: 'LA1234', descricao: 'Cancelamento informado pela Aviationstack.', risco: 'alto', fonte: 'aviationstack'
        }] } });
        return route.fulfill({ json: {} });
      });
      await page.goto('http://localhost/');
      await page.waitForFunction(() => document.getElementById('importacaoStatus').textContent.includes('aguardando a chave'));
      assert.match(await page.locator('#disruptionsGrid').innerText(), /Fonte: Aviationstack/);
      configurada = true;
      await page.evaluate(() => window.carregarDisrupcoes());
      assert.match(await page.locator('#importacaoStatus').innerText(), /Cobertura parcial/);
      assert.match(await page.locator('#importacaoStatus').innerText(), /Cota do plano/);
    } finally { await browser.close(); }
  });
}

for (const file of ['docs/index.html', 'backend/static/index.html']) {
  test(`${file}: prévia de jornadas alimenta uma otimização fictícia sem permitir publicação`, async () => {
    const browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox']
    });
    try {
      const page = await browser.newPage();
      let parametros;
      const pedidos = [];
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.href === 'http://localhost/') return route.fulfill({ contentType: 'text/html', body: readFileSync(resolve(__dirname, '../..', file), 'utf8') });
        if (url.pathname === '/api/jornadas/simular') {
          parametros = route.request().postDataJSON();
          return route.fulfill({ json: { simulado: true, parametros, resumo: { total: 1, sem_descanso: 0, nao_aclimatados: 0, no_limite: 0 }, jornadas: [{
            id: 'T1', nome: 'Pessoa simulada', cargo: 'Comandante', base: 'GRU', horas_acumuladas: 4.5, limite_horas: 11, descanso_ok: true, aclimatado: true
          }] } });
        }
        if (url.pathname === '/api/escalas/otimizar') {
          const pedido = route.request().postDataJSON(); pedidos.push(pedido);
          return route.fulfill({ json: { status: 'OPTIMAL', total_alocacoes: 1, conformidade: 100, wall_time_seconds: 0.1,
            origem_jornadas: pedido.simulacao_jornadas ? 'simulacao' : 'banco',
            simulacao_jornadas: { parametros }, alocacoes: [{ ...escala, duracao_horas: 1, horas_antes: 4.5 }]
          } });
        }
        if (url.pathname === '/api/escalas') return route.fulfill({ json: { total: 0, data: '2026-10-19', escalas: [] } });
        if (url.pathname === '/api/disrupcoes') return route.fulfill({ json: { total: 0, retornados: 0, disrupcoes: [] } });
        return route.fulfill({ json: {} });
      });
      await page.goto('http://localhost/');
      await page.locator('.nav-btn[data-screen="escalas"]').click();
      await page.locator('#simuladorJornadas summary').click();
      await page.locator('#simJornadaSeed').fill('123');
      await page.locator('#simJornadaVoos').fill('2');
      await page.locator('#simJornadaPerfil').selectOption('moderado');
      await page.locator('#simJornadaData').fill('2026-10-19');
      await page.locator('#btnGerarJornadas').click();
      await page.waitForFunction(() => document.getElementById('usarJornadasSimuladas').checked);
      assert.match(await page.locator('#jornadaSimRows').innerText(), /Pessoa simulada/);
      assert.equal(await page.locator('#btnAplicar').isDisabled(), true);
      await page.locator('#btnSimular').click();
      await page.waitForFunction(() => document.getElementById('liveStatus').textContent.includes('JORNADAS FICTÍCIAS'));
      assert.equal(pedidos.length, 1);
      assert.equal(pedidos[0].gravar, false);
      assert.equal(pedidos[0].limite_voos, 2);
      assert.deepEqual(pedidos[0].simulacao_jornadas, { seed: 123, perfil: 'moderado' });
      assert.equal(pedidos[0].data, '2026-10-19');
      await page.locator('#usarJornadasSimuladas').uncheck();
      assert.equal(await page.locator('#btnAplicar').isDisabled(), false);
      await page.locator('#btnSimular').click();
      await page.waitForFunction(() => document.getElementById('liveStatus').textContent.includes('OPTIMAL') && !document.getElementById('liveStatus').textContent.includes('JORNADAS FICTÍCIAS'));
      assert.equal(pedidos.length, 2);
      assert.equal(pedidos[1].simulacao_jornadas, undefined);
      await page.locator('#simJornadaSeed').fill('124');
      await page.locator('#simJornadaSeed').press('Tab');
      assert.equal(await page.locator('#usarJornadasSimuladas').isDisabled(), true);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}
