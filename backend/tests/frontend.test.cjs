// node --test backend/tests/frontend.test.cjs (Playwright + Chromium; see README)
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve, dirname } = require('node:path');
const { chromium } = require('playwright');

async function abrir(file, responder = async () => false) {
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}), args: ['--no-sandbox']
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => {
    localStorage.setItem('usuario_logado', JSON.stringify({ nome: 'Marina em cache', email: 'old@example.test' }));
    const timeout = AbortSignal.timeout.bind(AbortSignal);
    AbortSignal.timeout = () => timeout(500);
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://localhost') return route.abort();
    if (await responder(route, url)) return;
    if (url.pathname.startsWith('/assets/leaflet/')) {
      const asset = resolve(__dirname, '../..', dirname(file), '.' + url.pathname);
      return route.fulfill({ contentType: url.pathname.endsWith('.js') ? 'application/javascript' : 'text/css', body: readFileSync(asset) });
    }
    if (['/', '/index.html', '/login.html'].includes(url.pathname)) {
      const arquivo = url.pathname === '/login.html' ? dirname(file) + '/login.html' : file;
      return route.fulfill({ contentType: 'text/html', body: readFileSync(resolve(__dirname, '../..', arquivo), 'utf8') });
    }
    const dados = {
      '/api/perfil': { nome: 'Usuário real', email: 'real@example.test', cargo: 'Operador', base: 'GRU' },
      '/api/operacao': { iniciada: false, rodando: false, mudancas: [] },
      '/api/disrupcoes': { total: 0, retornados: 0, disrupcoes: [] },
      '/api/disrupcoes/importacao/status': { configurada: false },
      '/api/tripulantes': { total: 0, retornados: 0, tripulantes: [] },
      '/api/tripulantes/resumo': { total: 0, por_cargo: {}, por_base: {}, por_status: {} },
      '/api/health': { status: 'ok', banco: { ok: true } }
    };
    return route.fulfill({ json: dados[url.pathname] || {} });
  });
  await page.goto('http://localhost/');
  return { page, browser, errors };
}

function estado(rodando = true) {
  return { iniciada: true, rodando, relogio: '2026-10-19 · 10h00', tripulantes: 900,
    em_voo: 10, em_repouso: 5, concluidos: 2, aguardando: 1, total_mudancas: 0, mudancas: [] };
}

for (const file of ['docs/index.html', 'backend/static/index.html']) {
  test(`${file}: radar real tem aviões, busca, detalhes e preserva posições na falha`, async () => {
    let falha = false;
    const voos = [
      { icao24: 'abc123', callsign: 'TAM1234', latitude: -23.43, longitude: -46.47, altitude_m: 10000, velocidade_kmh: 850, direcao: 90, atualizado_em: '2026-10-20T12:00:00Z' },
      { icao24: 'def456', callsign: 'GLO5678', latitude: -3.04, longitude: -60.05, altitude_m: 0, velocidade_kmh: 0, direcao: 0 },
      { icao24: 'sempos', callsign: 'TAM9999', latitude: null, longitude: null },
      { icao24: 'solo', callsign: 'GLO0000', latitude: -15, longitude: -47, no_solo: true }
    ];
    const { page, browser, errors } = await abrir(file, async (r, u) => {
      if (u.pathname !== '/api/ao-vivo') return false;
      assert.equal(u.searchParams.get('limite'), '500');
      await r.fulfill({ status: falha ? 503 : 200, json: { disponivel: true, fonte: 'OpenSky Network', consultado_em: '2026-10-20T12:00:00Z', voos } }); return true;
    });
    try {
      await page.waitForFunction(() => document.getElementById('radarMapa').dataset.voos === '2');
      assert.equal(await page.locator('#mapaMalha').count(), 0);
      assert.match(await page.locator('#radarStatus').textContent(), /OpenSky.*12:00:00 UTC/);
      await page.locator('.radar-aviao[aria-label="Ver voo TAM1234"]').click();
      assert.match(await page.locator('.radar-popup').textContent(), /TAM1234.*10.000 m.*850 km\/h/s);
      await page.locator('#radarBusca').fill('glo');
      assert.equal(await page.locator('.radar-aviao').count(), 1);
      await page.locator('.radar-aviao').click();
      assert.match(await page.locator('.radar-popup').textContent(), /0 m.*0 km\/h/s);
      await page.locator('#radarBusca').fill('');
      falha = true;
      await page.evaluate(() => window.carregarRadar());
      assert.match(await page.locator('#radarStatus').textContent(), /Mantendo as últimas posições/);
      assert.equal(await page.locator('.radar-aviao').count(), 2);
      falha = false; voos.splice(0, 1);
      await page.evaluate(() => window.carregarRadar());
      assert.equal(await page.locator('.radar-aviao').count(), 1);
      await page.locator('.nav-btn[data-screen="tripulantes"]').click();
      await page.locator('.nav-btn[data-screen="painel"]').click();
      assert.equal(await page.locator('#radarMapa').isVisible(), true);
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

  test(`${file}: radar vazio e fonte indisponível não mostram voos inventados`, async () => {
    let dados = { disponivel: false, atualizando: true, voos: [] };
    const { page, browser, errors } = await abrir(file, async (r, u) => {
      if (u.pathname !== '/api/ao-vivo') return false;
      await r.fulfill({ json: dados }); return true;
    });
    try {
      await page.waitForFunction(() => document.getElementById('radarStatus').textContent.includes('Atualizando posições'));
      assert.equal(await page.locator('.radar-aviao').count(), 0);
      dados = { disponivel: false, atualizando: false, voos: [] };
      await page.evaluate(() => window.carregarRadar());
      assert.match(await page.locator('#radarStatus').textContent(), /Fonte de voos indisponível/);
      dados = { disponivel: true, voos: [] };
      await page.evaluate(() => window.carregarRadar());
      assert.match(await page.locator('#radarStatus').textContent(), /Nenhum voo/);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

  test(`${file}: um controle, progresso persistido e somente remanejamentos na tabela`, async () => {
    let op = { iniciada: false, rodando: false, mudancas: [] };
    let inicios = 0;
    const { page, browser, errors } = await abrir(file, async (r, u) => {
      if (!u.pathname.startsWith('/api/operacao')) return false;
      if (u.pathname.endsWith('/iniciar')) { inicios++; op = estado(); }
      if (u.pathname.endsWith('/pausar')) op.rodando = false;
      await r.fulfill({ json: op }); return true;
    });
    try {
      await page.locator('.nav-btn[data-screen="escalas"]').click();
      assert.equal(await page.locator('#formSimularJornadas, #simJornadaSeed, #btnAplicar, #crewTable').count(), 0);
      await page.locator('#btnOperacao').click();
      await page.waitForFunction(() => document.getElementById('btnOperacao').textContent === 'Pausar operação');
      assert.equal(inicios, 1);
      assert.match(await page.locator('#operacaoResumo').innerText(), /900 tripulantes/);
      assert.equal(await page.locator('#remanejamentosRows tr').count(), 0);
      op.total_mudancas = 1;
      op.mudancas = [{ minuto: 600, voo: 'TEST-001', saiu: 'Pessoa A', entrou: 'Pessoa B', local: 'MAO', motivo: 'Ainda está em outro voo' }];
      await page.evaluate(() => window.carregarOperacao());
      assert.equal(await page.locator('#remanejamentosRows tr').count(), 1);
      assert.match(await page.locator('#remanejamentosRows').innerText(), /Pessoa A.*Pessoa B/s);
      await page.locator('#btnOperacao').click();
      await page.waitForFunction(() => document.getElementById('btnOperacao').textContent === 'Continuar operação');
      await page.reload();
      await page.waitForFunction(() => document.querySelectorAll('#remanejamentosRows tr').length === 1);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

  test(`${file}: perfil lento não trava navegação e falha da operação fica visível`, async () => {
    let falha = false;
    const { page, browser, errors } = await abrir(file, async (r, u) => {
      if (u.pathname === '/api/perfil') return true;
      if (u.pathname === '/api/operacao' && falha) { await r.fulfill({ status: 500, json: {} }); return true; }
      return false;
    });
    try {
      await page.locator('.nav-btn[data-screen="escalas"]').click();
      assert.equal(await page.locator('#screen-escalas').isVisible(), true);
      assert.match(await page.locator('#utcClock').innerText(), /\d{2}:\d{2}/);
      falha = true;
      await page.evaluate(() => window.carregarOperacao());
      assert.match(await page.locator('#operacaoStatus').innerText(), /Não foi possível consultar/);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

  test(`${file}: identidade da API, perfil confirmado e saída sem restauração do cache`, async () => {
    let salvar = false, falhaSalvar = true, logout = 0, sessoes = 0;
    const { page, browser, errors } = await abrir(file, async (r, u) => {
      if (u.pathname === '/api/perfil' && r.request().method() === 'POST') {
        salvar = true;
        await r.fulfill({ status: falhaSalvar ? 500 : 200, json: falhaSalvar ? { erro: 'Falha de teste' } : { perfil: { nome: 'Nome atualizado', email: 'real@example.test' } } }); return true;
      }
      if (u.pathname === '/api/auth/logout') { logout++; await r.fulfill({ status: 503, json: {} }); return true; }
      if (u.pathname === '/api/auth/sessao') { sessoes++; await r.fulfill({ json: { autenticado: true } }); return true; }
      return false;
    });
    try {
      await page.waitForFunction(() => document.getElementById('headerUserName').textContent === 'Usuário real');
      await page.locator('.nav-btn[data-screen="configuracoes"]').click();
      await page.locator('#inputName').fill('Nome atualizado');
      await page.locator('#inputName').press('Tab');
      await page.waitForFunction(() => document.getElementById('sessionStatus').textContent.includes('Perfil não salvo'));
      assert.equal(salvar, true);
      assert.equal(await page.locator('#headerUserName').innerText(), 'Usuário real');
      falhaSalvar = false;
      await page.evaluate(() => document.getElementById('inputName').dispatchEvent(new Event('change')));
      await page.waitForFunction(() => document.getElementById('headerUserName').textContent === 'Nome atualizado');
      await page.locator('#btnLogout').click();
      await page.waitForURL('**/login.html?logout=1');
      await page.waitForFunction(() => document.getElementById('login-msg').textContent.includes('não foi confirmada'));
      assert.equal(await page.evaluate(() => localStorage.getItem('usuario_logado')), null);
      assert.equal(sessoes, 0); assert.equal(logout, 2);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

  test(`${file}: disrupções continuam independentes, com registro, filtro e texto seguro`, async () => {
    const ocorrencias = [];
    let falha = false;
    const { page, browser } = await abrir(file, async (r, u) => {
      if (u.pathname !== '/api/disrupcoes') return false;
      if (r.request().method() === 'POST') { ocorrencias.push({ ...r.request().postDataJSON(), id: 1 }); await r.fulfill({ status: 201, json: { disrupcao: ocorrencias[0] } }); }
      else await r.fulfill({ status: falha ? 404 : 200, json: { total: ocorrencias.length, retornados: ocorrencias.length, disrupcoes: ocorrencias } });
      return true;
    });
    try {
      await page.locator('.nav-btn[data-screen="disrupcoes"]').click();
      await page.locator('#screen-disrupcoes summary').click();
      await page.locator('#disrupcaoVoo').fill('TEST-900');
      await page.locator('#disrupcaoDescricao').fill('<img src=x onerror="window.injetado=true"> Manutenção');
      await page.locator('#disrupcaoRisco').selectOption('alto');
      await page.locator('#btnRegistrarDisrupcao').click();
      await page.waitForFunction(() => document.querySelectorAll('#disruptionsGrid .alert-card').length === 1);
      assert.equal(await page.locator('#disruptionsGrid img').count(), 0);
      assert.equal(await page.locator('#kpiActiveCount').innerText(), '1');
      await page.locator('.filter-btn[data-filter="baixo"]').click();
      assert.match(await page.locator('#disruptionsGrid').innerText(), /Nenhuma ocorrência nesta categoria/);
      await page.locator('.filter-btn[data-filter="all"]').click();
      falha = true; await page.evaluate(() => window.carregarDisrupcoes());
      assert.match(await page.locator('#disruptionsStatus').innerText(), /Publique/);
      assert.equal(await page.locator('#disruptionsGrid .alert-card').count(), 1);
    } finally { await browser.close(); }
  });

  test(`${file}: mantém diagnóstico de cobertura e fonte externa`, async () => {
    let configurada = false;
    const { page, browser } = await abrir(file, async (r, u) => {
      if (u.pathname !== '/api/disrupcoes/importacao/status') return false;
      await r.fulfill({ json: { configurada, aeroporto: 'GRU', ultimo_sucesso: '2026-10-19T12:00:00+00:00', parcial: true, agendador_ativo: true, ultimo_erro: 'Cota do plano atingida.' } }); return true;
    });
    try {
      await page.waitForFunction(() => document.getElementById('importacaoStatus').textContent.includes('aguardando a chave'));
      configurada = true; await page.evaluate(() => window.carregarDisrupcoes());
      assert.match(await page.locator('#importacaoStatus').innerText(), /Cobertura parcial/);
      assert.match(await page.locator('#importacaoStatus').innerText(), /Cota do plano/);
    } finally { await browser.close(); }
  });

  test(`${file}: tripulantes mostram posição atual, horas e situação`, async () => {
    const { page, browser, errors } = await abrir(file, async (r, u) => {
      if (u.pathname !== '/api/tripulantes') return false;
      await r.fulfill({ json: { total: 1, retornados: 1, tripulantes: [{ id: 'T1', nome_completo: 'Pessoa A', cargo: 'Comandante', base: 'GRU', status: 'Disponível', local_atual: 'GRU → MAO', jornada_simulada: '03h00 / 11h00', situacao_atual: 'Em voo' }] } }); return true;
    });
    try {
      await page.locator('.nav-btn[data-screen="tripulantes"]').click();
      await page.waitForFunction(() => document.querySelectorAll('#crewBaseBody tr').length === 1);
      const texto = await page.locator('#crewBaseBody').innerText();
      assert.match(texto, /GRU → MAO/); assert.match(texto, /03h00 \/ 11h00/); assert.match(texto, /Em voo/);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}
