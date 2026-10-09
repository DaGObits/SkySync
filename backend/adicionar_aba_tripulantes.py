"""Adiciona a aba TRIPULANTES ao index.html.

Faz 5 insercoes no arquivo, na ordem certa, e faz backup antes de tocar.

  1. botao de navegacao "Tripulantes" (depois de Escalas)
  2. secao <section id="screen-tripulantes"> (antes de Configuracoes)
  3. chaves de traducao pt-BR / en / es
  4. carregamento ao entrar na aba (dentro de switchScreen)
  5. o modulo JS que busca /api/tripulantes e monta a tabela

Uso:  .venv\\Scripts\\python.exe adicionar_aba_tripulantes.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ALVO = Path("static/index.html")

# ---------------------------------------------------------------------------
# 1. Botao de navegacao
# ---------------------------------------------------------------------------
BOTAO = (
    '      <li><button type="button" class="nav-btn" data-screen="tripulantes">'
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'aria-hidden="true"><circle cx="9" cy="8" r="3.2"/>'
    '<path d="M3.5 20a5.5 5.5 0 0111 0"/><path d="M16 5.5a3 3 0 010 5.9"/>'
    '<path d="M17.5 20a5.2 5.2 0 00-2.2-4.3"/></svg> '
    '<span data-i18n="menuCrew">Tripulantes</span></button></li>'
)

# ---------------------------------------------------------------------------
# 2. Secao da aba
# ---------------------------------------------------------------------------
SECAO = '''
    <!-- ABA DE TRIPULANTES -->
    <section class="screen" id="screen-tripulantes" aria-labelledby="tripulantes-h" tabindex="-1" hidden>
      <h1 id="tripulantes-h" data-i18n="crewTitle">Tripulantes</h1>
      <p class="lede" data-i18n="crewSubtitle">Base de tripulacao disponivel para otimizacao, por cargo, base e status.</p>

      <div class="kpi-grid">
        <div class="kpi-card kpi-card-static">
          <span class="kpi-label" data-i18n="crewKpiTotal">Tripulantes na base</span>
          <span class="kpi-value" id="crewKpiTotal">--</span>
          <span class="kpi-hint" data-i18n="crewKpiBases">bases distintas</span>
        </div>
        <div class="kpi-card kpi-card-static">
          <span class="kpi-label" data-i18n="crewKpiAvailable">Disponiveis</span>
          <span class="kpi-value" id="crewKpiAvailable">--</span>
          <span class="kpi-hint" id="crewKpiReserveHint" data-i18n="crewKpiReserve">em reserva</span>
        </div>
        <div class="kpi-card kpi-card-static">
          <span class="kpi-label" data-i18n="crewKpiCommanders">Comandantes</span>
          <span class="kpi-value" id="crewKpiCommanders">--</span>
          <span class="kpi-hint" id="crewKpiCopilotsHint">--</span>
        </div>
        <div class="kpi-card kpi-card-static">
          <span class="kpi-label" data-i18n="crewKpiCabin">Tripulantes de cabine</span>
          <span class="kpi-value" id="crewKpiCabin">--</span>
          <span class="kpi-hint" data-i18n="crewKpiHint">no pool do otimizador</span>
        </div>
      </div>

      <div class="table-wrap">
        <div class="table-toolbar">
          <span id="crewCaption">
            <span id="crewShown">0</span> <span data-i18n="crewOfWord">de</span>
            <span id="crewTotal">0</span> <span data-i18n="crewMembersWord">tripulantes</span>
          </span>
          <div class="history-controls">
            <label class="crew-filter-label">
              <span data-i18n="filterBase">Base</span>
              <select id="filtroBase" class="setting-input"></select>
            </label>
            <label class="crew-filter-label">
              <span data-i18n="filterRole">Cargo</span>
              <select id="filtroCargo" class="setting-input">
                <option value="" data-i18n="filterAllRoles">Todos</option>
                <option value="Comandante" data-i18n="roleCommander">Comandante</option>
                <option value="Copiloto" data-i18n="roleCopilot">Copiloto</option>
                <option value="Comissário" data-i18n="roleCabin">Comissario</option>
              </select>
            </label>
            <label class="crew-filter-label">
              <span data-i18n="filterStatus">Status</span>
              <select id="filtroStatus" class="setting-input">
                <option value="" data-i18n="filterAllStatus">Todos</option>
                <option value="Disponível" data-i18n="statusAvailable">Disponivel</option>
                <option value="Reserva" data-i18n="statusReserve">Reserva</option>
              </select>
            </label>
            <button type="button" class="btn-refresh-table" id="btnRefreshCrew" data-i18n="btnRefreshCrew">Atualizar</button>
          </div>
        </div>
        <table id="crewBaseTable" aria-label="Base de tripulantes disponiveis">
          <thead>
            <tr>
              <th scope="col" data-i18n="thCrewId">ID</th>
              <th scope="col" data-i18n="thCrewName">Nome</th>
              <th scope="col" data-i18n="thCrewRole">Cargo</th>
              <th scope="col" data-i18n="thCrewBase">Base</th>
              <th scope="col" data-i18n="thCrewStatus">Status</th>
            </tr>
          </thead>
          <tbody id="crewBaseBody">
            <!-- Preenchido por carregarTripulantes() -->
          </tbody>
        </table>
      </div>
      <div id="crewStatus" role="status" aria-live="polite"></div>
    </section>
'''

# ---------------------------------------------------------------------------
# 3. Traducoes (uma entrada por idioma)
# ---------------------------------------------------------------------------
TRADUCOES = {
    "pt-BR": """        menuCrew: 'Tripulantes',
        crewTitle: 'Tripulantes',
        crewSubtitle: 'Base de tripulação disponível para otimização, por cargo, base e status.',
        crewKpiTotal: 'Tripulantes na base',
        crewKpiBases: 'bases distintas',
        crewKpiAvailable: 'Disponíveis',
        crewKpiReserve: 'em reserva',
        crewKpiCommanders: 'Comandantes',
        crewKpiCabin: 'Tripulantes de cabine',
        crewKpiHint: 'no pool do otimizador',
        crewOfWord: 'de',
        crewMembersWord: 'tripulantes',
        filterBase: 'Base',
        filterRole: 'Cargo',
        filterAllRoles: 'Todos',
        filterStatus: 'Status',
        filterAllStatus: 'Todos',
        roleCommander: 'Comandante',
        roleCopilot: 'Copiloto',
        roleCabin: 'Comissário',
        statusAvailable: 'Disponível',
        statusReserve: 'Reserva',
        btnRefreshCrew: '🔄 Atualizar',
        thCrewId: 'ID',
        thCrewName: 'Nome',
        thCrewRole: 'Cargo',
        thCrewBase: 'Base',
        thCrewStatus: 'Status',
        crewLoading: 'Carregando tripulantes...',
        crewEmpty: 'Nenhum tripulante encontrado com esses filtros.',
        crewError: 'Não foi possível carregar a base de tripulantes.',
        crewAllBases: 'Todas as bases',
""",
    "en": """        menuCrew: 'Crew',
        crewTitle: 'Crew',
        crewSubtitle: 'Available crew database for optimization, by role, base and status.',
        crewKpiTotal: 'Crew in database',
        crewKpiBases: 'distinct bases',
        crewKpiAvailable: 'Available',
        crewKpiReserve: 'on reserve',
        crewKpiCommanders: 'Captains',
        crewKpiCabin: 'Cabin crew',
        crewKpiHint: 'in the optimizer pool',
        crewOfWord: 'of',
        crewMembersWord: 'crew members',
        filterBase: 'Base',
        filterRole: 'Role',
        filterAllRoles: 'All',
        filterStatus: 'Status',
        filterAllStatus: 'All',
        roleCommander: 'Captain',
        roleCopilot: 'First Officer',
        roleCabin: 'Cabin Crew',
        statusAvailable: 'Available',
        statusReserve: 'Reserve',
        btnRefreshCrew: '🔄 Refresh',
        thCrewId: 'ID',
        thCrewName: 'Name',
        thCrewRole: 'Role',
        thCrewBase: 'Base',
        thCrewStatus: 'Status',
        crewLoading: 'Loading crew...',
        crewEmpty: 'No crew found with these filters.',
        crewError: 'Could not load the crew database.',
        crewAllBases: 'All bases',
""",
    "es": """        menuCrew: 'Tripulantes',
        crewTitle: 'Tripulantes',
        crewSubtitle: 'Base de tripulación disponible para optimización, por cargo, base y estado.',
        crewKpiTotal: 'Tripulantes en la base',
        crewKpiBases: 'bases distintas',
        crewKpiAvailable: 'Disponibles',
        crewKpiReserve: 'en reserva',
        crewKpiCommanders: 'Comandantes',
        crewKpiCabin: 'Tripulantes de cabina',
        crewKpiHint: 'en el pool del optimizador',
        crewOfWord: 'de',
        crewMembersWord: 'tripulantes',
        filterBase: 'Base',
        filterRole: 'Cargo',
        filterAllRoles: 'Todos',
        filterStatus: 'Estado',
        filterAllStatus: 'Todos',
        roleCommander: 'Comandante',
        roleCopilot: 'Copiloto',
        roleCabin: 'Auxiliar de vuelo',
        statusAvailable: 'Disponible',
        statusReserve: 'Reserva',
        btnRefreshCrew: '🔄 Actualizar',
        thCrewId: 'ID',
        thCrewName: 'Nombre',
        thCrewRole: 'Cargo',
        thCrewBase: 'Base',
        thCrewStatus: 'Estado',
        crewLoading: 'Cargando tripulantes...',
        crewEmpty: 'No se encontraron tripulantes con esos filtros.',
        crewError: 'No se pudo cargar la base de tripulantes.',
        crewAllBases: 'Todas las bases',
""",
}

# ---------------------------------------------------------------------------
# 4. Modulo JS
# ---------------------------------------------------------------------------
MODULO_JS = '''
    // ---------------------------------------------------------------------
    // ABA DE TRIPULANTES
    // Carrega a base real do banco via /api/tripulantes. Sem lista fixa no
    // HTML: o que a tela mostra vem da mesma tabela que o otimizador consulta.
    // ---------------------------------------------------------------------
    const estadoTripulantes = { base: '', cargo: '', status: '', carregado: false };

    function texto(chave, padrao) {
      const dict = (translations[settings.idioma] || translations['pt-BR']);
      return dict[chave] || padrao || chave;
    }

    function montarLinhaTripulante(t) {
      const tr = document.createElement('tr');
      const statusClasse = t.status === 'Reserva' ? 'over' : '';
      tr.innerHTML = `
        <td class="hours">${t.id}</td>
        <td><span class="crew-name">${t.nome_completo}</span></td>
        <td>${t.cargo}</td>
        <td class="hours">${t.base}</td>
        <td><span class="limit-tag">${t.status}</span></td>
      `;
      void statusClasse;
      return tr;
    }

    async function carregarResumoTripulantes() {
      try {
        const res = await fetch(`${API_URL}/tripulantes/resumo`, { credentials: 'include' });
        if (res.status === 401) { window.location.href = 'login.html'; return; }
        if (!res.ok) return;
        const d = await res.json();

        const el = (id) => document.getElementById(id);
        if (el('crewKpiTotal')) el('crewKpiTotal').textContent = d.total;
        if (el('crewKpiAvailable')) el('crewKpiAvailable').textContent = d.por_status?.['Disponível'] ?? '--';
        if (el('crewKpiReserveHint')) el('crewKpiReserveHint').textContent =
          (d.por_status?.['Reserva'] ?? 0) + ' ' + texto('crewKpiReserve', 'em reserva');
        if (el('crewKpiCommanders')) el('crewKpiCommanders').textContent = d.por_cargo?.Comandante ?? '--';
        if (el('crewKpiCopilotsHint')) el('crewKpiCopilotsHint').textContent =
          (d.por_cargo?.Copiloto ?? 0) + ' ' + texto('roleCopilot', 'Copiloto');
        if (el('crewKpiCabin')) el('crewKpiCabin').textContent = d.por_cargo?.['Comissário'] ?? '--';

        const filtroBase = el('filtroBase');
        if (filtroBase && filtroBase.options.length <= 1) {
          const opcao = document.createElement('option');
          opcao.value = '';
          opcao.textContent = texto('crewAllBases', 'Todas as bases');
          filtroBase.appendChild(opcao);
          Object.keys(d.por_base || {}).sort().forEach((iata) => {
            const o = document.createElement('option');
            o.value = iata;
            o.textContent = `${iata} (${d.por_base[iata]})`;
            filtroBase.appendChild(o);
          });
        }
      } catch (e) {
        console.error('Resumo de tripulantes indisponivel:', e);
      }
    }

    async function carregarTripulantes(forcar) {
      if (estadoTripulantes.carregado && !forcar) return;

      const tbody = document.getElementById('crewBaseBody');
      const aviso = document.getElementById('crewStatus');
      if (!tbody) return;

      if (aviso) { aviso.style.color = 'var(--text-600-solid)'; aviso.textContent = texto('crewLoading', 'Carregando...'); }

      const filtros = new URLSearchParams();
      filtros.set('limite', '300');
      if (estadoTripulantes.base) filtros.set('base', estadoTripulantes.base);
      if (estadoTripulantes.cargo) filtros.set('cargo', estadoTripulantes.cargo);
      if (estadoTripulantes.status) filtros.set('status', estadoTripulantes.status);

      try {
        const res = await fetch(`${API_URL}/tripulantes?${filtros.toString()}`, { credentials: 'include' });
        if (res.status === 401) { window.location.href = 'login.html'; return; }
        if (!res.ok) throw new Error('HTTP ' + res.status);

        const dados = await res.json();
        tbody.innerHTML = '';

        if (!dados.tripulantes.length) {
          if (aviso) { aviso.style.color = 'var(--text-400)'; aviso.textContent = texto('crewEmpty', 'Nenhum resultado.'); }
        } else {
          dados.tripulantes.forEach((t) => tbody.appendChild(montarLinhaTripulante(t)));
          if (aviso) { aviso.style.color = 'var(--green)'; aviso.textContent = ''; }
        }

        const total = document.getElementById('crewTotal');
        const mostrados = document.getElementById('crewShown');
        if (total) total.textContent = dados.total;
        if (mostrados) mostrados.textContent = dados.retornados;

        estadoTripulantes.carregado = true;
        await carregarResumoTripulantes();
      } catch (e) {
        console.error('Falha ao carregar tripulantes:', e);
        if (aviso) { aviso.style.color = 'var(--red)'; aviso.textContent = texto('crewError', 'Falha ao carregar.'); }
      }
    }

    (function ligarFiltrosTripulantes() {
      const aplicar = () => {
        const fb = document.getElementById('filtroBase');
        const fc = document.getElementById('filtroCargo');
        const fs = document.getElementById('filtroStatus');
        estadoTripulantes.base = fb ? fb.value : '';
        estadoTripulantes.cargo = fc ? fc.value : '';
        estadoTripulantes.status = fs ? fs.value : '';
        estadoTripulantes.carregado = false;
        carregarTripulantes(true);
      };
      ['filtroBase', 'filtroCargo', 'filtroStatus'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', aplicar);
      });
      const btn = document.getElementById('btnRefreshCrew');
      if (btn) btn.addEventListener('click', () => carregarTripulantes(true));
    })();
'''


def inserir_botao(html: str) -> tuple[str, bool]:
    marcador = '<li><button type="button" class="nav-btn" data-screen="escalas">'
    if 'data-screen="tripulantes"' in html:
        return html, False
    # Insere depois da linha inteira das Escalas (que termina em </li>).
    idx = html.find(marcador)
    if idx == -1:
        return html, False
    fim = html.find('</li>', idx)
    if fim == -1:
        return html, False
    fim += len('</li>')
    return html[:fim] + '\r\n' + BOTAO + html[fim:], True


def inserir_secao(html: str) -> tuple[str, bool]:
    if 'id="screen-tripulantes"' in html:
        return html, False
    marcador = '<!-- ABA DE CONFIGURAÇÕES -->'
    idx = html.find(marcador)
    if idx == -1:
        return html, False
    return html[:idx] + SECAO + '\r\n    ' + html[idx:], True


def inserir_traducoes(html: str) -> tuple[str, int]:
    feitos = 0
    for idioma, bloco in TRADUCOES.items():
        if f"menuCrew:" in html and f"thCrewId:" in html:
            break
        # ancora: as 4 chaves de menu seguidas, que existem nos 3 idiomas
        for ancora in (
            "        menuSchedules: 'Escalas',",
            "        menuSchedules: 'Schedules',",
            "        menuSchedules: 'Tripulaciones',",
        ):
            alvo = html.find(ancora)
            if alvo == -1:
                continue
            fim_linha = html.find('\n', alvo)
            if fim_linha == -1:
                continue
            # Só insere se este idioma ainda não tem menuCrew depois da ancora
            trecho = html[alvo:alvo + 4000]
            if 'menuCrew:' in trecho:
                continue
            html = html[:fim_linha + 1] + bloco + html[fim_linha + 1:]
            feitos += 1
    return html, feitos


def inserir_chamada(html: str) -> tuple[str, bool]:
    if 'carregarTripulantes(true)' in html and 'name === ' in html and "tripulantes" in html:
        pass
    alvo = """        if (name === 'disrupcoes') {
          gerarDisruptionsDinamicas();
        }"""
    if 'carregarTripulantes' in html:
        return html, False
    if alvo not in html:
        return html, False
    novo = alvo + """

        if (name === 'tripulantes') {
          carregarTripulantes(false);
        }"""
    return html.replace(alvo, novo, 1), True


def inserir_modulo(html: str) -> tuple[str, bool]:
    if 'estadoTripulantes' in html:
        return html, False
    alvo = "    const screens = document.querySelectorAll('.screen');"
    if alvo not in html:
        return html, False
    return html.replace(alvo, MODULO_JS + '\n' + alvo, 1), True


def main() -> int:
    if not ALVO.exists():
        print(f"ERRO: {ALVO.resolve()} nao encontrado.")
        print("Rode este script dentro de C:\\SkySync\\backend")
        return 1

    original = ALVO.read_text(encoding="utf-8")
    shutil.copy2(ALVO, ALVO.with_suffix(".html.bak"))
    print(f"Backup: {ALVO.with_suffix('.html.bak').name}")
    print()

    html = original

    html, ok_botao = inserir_botao(html)
    print(f"1. botao de navegacao     {'OK' if ok_botao else 'ja existia / nao encontrado'}")

    html, ok_secao = inserir_secao(html)
    print(f"2. secao da aba           {'OK' if ok_secao else 'ja existia / nao encontrado'}")

    html, n_trad = inserir_traducoes(html)
    print(f"3. traducoes              {n_trad} idioma(s)")

    html, ok_modulo = inserir_modulo(html)
    print(f"4. modulo JS              {'OK' if ok_modulo else 'ja existia / nao encontrado'}")

    html, ok_chamada = inserir_chamada(html)
    print(f"5. gancho no switchScreen {'OK' if ok_chamada else 'ja existia / nao encontrado'}")

    if html == original:
        print()
        print("Nada mudou — os blocos ja estavam aplicados.")
        return 0

    ALVO.write_text(html, encoding="utf-8")
    print()
    print(f"index.html atualizado ({len(original)} -> {len(html)} caracteres)")
    print("Abra no navegador e clique em 'Tripulantes' no menu lateral.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
