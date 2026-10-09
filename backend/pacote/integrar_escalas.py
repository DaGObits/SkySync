"""Integra a aba Escalas com o banco (opcao B).

O que faz:
  1. a tabela de Escalas passa a ler GET /api/escalas (dados reais do banco)
  2. "Simular replanejamento" chama POST /api/escalas/otimizar com
     simular=true — roda o motor SEM gravar, e mostra o resultado na tabela
  3. "Aplicar escala" chama POST /api/escalas/otimizar — roda e GRAVA, e
     recarrega a tabela do banco
  4. "Atualizar" recarrega do banco em vez de sortear valores

A semantica da tela e preservada: simular nao altera a escala publicada,
aplicar publica. O botao Desfazer continua valendo para a simulacao.

Uso:  .venv\\Scripts\\python.exe integrar_escalas.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

ALVO = Path("static/index.html")

# ---------------------------------------------------------------------------
# 1. Modulo de integracao (inserido antes de `const screens = ...`)
# ---------------------------------------------------------------------------
MODULO = '''
    // ---------------------------------------------------------------------
    // INTEGRACAO DA ABA ESCALAS COM O BANCO
    //
    // A tabela passa a ler /api/escalas. Os campos vem com nomes diferentes
    // dos que a gerarEscalasDinamicas() espera, entao a conversao acontece
    // aqui, num lugar so — a funcao de render nao e tocada.
    //
    // Semantica preservada:
    //   SIMULAR  -> roda o motor e mostra o resultado, sem gravar
    //   APLICAR  -> roda o motor e publica a escala no banco
    // ---------------------------------------------------------------------
    let escalasDoBanco = [];
    let ultimaSimulacao = null;

    function formatarHorasApi(horas) {
      const totalMin = Math.round((Number(horas) || 0) * 60);
      const h = String(Math.floor(totalMin / 60)).padStart(2, '0');
      const m = String(totalMin % 60).padStart(2, '0');
      return `${h}h${m}`;
    }

    /** Converte uma linha de /api/escalas no formato da tabela. */
    function escalaParaLinha(e) {
      return {
        tripulante: e.tripulante,
        cargo: e.cargo,
        voo: e.voo,
        horas: e.horas,
        limitRbac: formatarHorasApi(e.limite_aplicado),
        bloqueado: !e.conforme,
        risco: !e.conforme ? 'alto' : (e.ocupacao_percentual >= 85 ? 'medio' : 'baixo'),
        badgeKey: !e.conforme ? 'highFatigueRisk' : 'normalOperation',
        rota: e.rota,
        solucao: e.motivo,
        desc: `Ocupação de ${e.ocupacao_percentual}% do teto após a alocação.`,
        deSimulacao: false,
      };
    }

    /** Converte uma alocacao de /api/escalas/otimizar no formato da tabela. */
    function alocacaoParaLinha(a) {
      const horasAntes = a.horas_antes ?? 0;
      const limite = a.limite_aplicado ?? 11;
      const depois = horasAntes + (a.duracao_horas || 0);
      const ocupacao = limite ? Math.round((depois / limite) * 1000) / 10 : 0;
      const conforme = depois <= limite;
      return {
        tripulante: a.tripulante,
        cargo: a.cargo,
        voo: a.voo,
        horas: a.horas || formatarHorasApi(a.duracao_horas),
        limitRbac: formatarHorasApi(limite),
        bloqueado: !conforme,
        risco: !conforme ? 'alto' : (ocupacao >= 85 ? 'medio' : 'baixo'),
        badgeKey: !conforme ? 'highFatigueRisk' : 'normalOperation',
        rota: a.rota,
        solucao: conforme ? 'Alocada pelo motor CP-SAT' : 'Excede o limite aplicado',
        desc: `Ocupação de ${ocupacao}% do teto após a alocação.`,
        deSimulacao: true,
      };
    }

    /** Carrega as escalas publicadas do banco. */
    async function carregarEscalasDoBanco(silencioso) {
      const aviso = document.getElementById('liveStatus');
      try {
        const res = await fetch(`${API_URL}/escalas`, { credentials: 'include' });
        if (res.status === 401) { window.location.href = 'login.html'; return; }
        if (!res.ok) throw new Error('HTTP ' + res.status);

        const dados = await res.json();
        escalasDoBanco = (dados.escalas || []).map(escalaParaLinha);

        if (escalasDoBanco.length) {
          const tabela = document.getElementById('mainCrewTable');
          if (tabela) tabela.dataset.fonte = 'banco';
          aplicarNaTabela(escalasDoBanco);
          if (aviso && !silencioso) {
            aviso.style.color = 'var(--green)';
            aviso.textContent = `${dados.total} alocação(ões) do banco — ${dados.conformes} conforme(s) — ${dados.data}.`;
          }
          addFeedItem(`Escalas carregadas do banco: ${dados.total} alocação(ões) em ${dados.data}.`);
        } else if (aviso && !silencioso) {
          aviso.style.color = 'var(--text-600-solid)';
          aviso.textContent = 'Nenhuma escala publicada ainda. Use "Aplicar escala" para gravar uma.';
        }
      } catch (err) {
        console.error('Falha ao carregar escalas do banco:', err);
        if (aviso) {
          aviso.style.color = 'var(--red)';
          aviso.textContent = 'Não foi possível carregar as escalas do banco.';
        }
      }
    }

    /**
     * Escreve uma lista de linhas na tabela, no MESMO formato da
     * gerarEscalasDinamicas(). Reutiliza o render existente trocando
     * temporariamente `dadosOperacionais`.
     */
    function aplicarNaTabela(linhas) {
      const backup = dadosOperacionais;
      try {
        dadosOperacionais = linhas;
        gerarEscalasDinamicas();
      } finally {
        dadosOperacionais = backup;
      }
    }

    /** Roda o motor. `gravar=true` publica no banco; `false` so simula. */
    async function rodarMotor(gravar, limiteVoos) {
      const aviso = document.getElementById('liveStatus');
      const btnSim = document.getElementById('btnSimular');
      const btnApl = document.getElementById('btnAplicar');
      const rotuloSim = btnSim ? btnSim.innerText : '';
      const rotuloApl = btnApl ? btnApl.innerText : '';

      if (btnSim) { btnSim.disabled = true; btnSim.innerText = gravar ? 'Publicando...' : 'Executando CP-SAT...'; }
      if (btnApl) btnApl.disabled = true;
      if (aviso) {
        aviso.style.color = 'var(--text-600-solid)';
        aviso.textContent = gravar
          ? 'Executando o motor e publicando a escala...'
          : 'Simulando — a escala publicada não será alterada.';
      }

      try {
        const res = await fetch(`${API_URL}/escalas/otimizar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            limite_voos: limiteVoos || 15,
            gravar: gravar === true,
          }),
        });

        const dados = await res.json();

        if (res.status === 401) { window.location.href = 'login.html'; return; }
        if (res.status === 409) {
          if (aviso) {
            aviso.style.color = 'var(--red)';
            aviso.textContent = 'Inviável: ' + (dados.diagnostico?.causas || []).join(' ');
          }
          addFeedItem('Otimização inviável: ' + (dados.diagnostico?.causas || []).join(' '));
          return;
        }
        if (!res.ok) {
          if (aviso) { aviso.style.color = 'var(--red)'; aviso.textContent = dados.mensagem || 'O motor não convergiu.'; }
          return;
        }

        const linhas = (dados.alocacoes || []).map(alocacaoParaLinha);
        ultimaSimulacao = linhas;

        aplicarNaTabela(linhas);

        const resumo = `${dados.status} · ${dados.total_alocacoes} alocação(ões) · `
          + `conformidade ${dados.conformidade}% · ${dados.wall_time_seconds}s`;

        if (gravar) {
          if (aviso) { aviso.style.color = 'var(--green)'; aviso.textContent = 'Escala publicada: ' + resumo; }
          addFeedItem(`Escala publicada no banco (${dados.escalas_gravadas} linha(s)): ${resumo}`);
          await carregarEscalasDoBanco(true);
        } else {
          if (aviso) { aviso.style.color = 'var(--blue, #2F6FE0)'; aviso.textContent = 'Simulação (não publicada): ' + resumo; }
          addFeedItem(`Simulação concluída sem publicar: ${resumo}`);
          const btnDesfazer = document.getElementById('btnDesfazer');
          if (btnDesfazer) btnDesfazer.disabled = false;
        }

        const engineLabel = document.getElementById('engineLabel');
        if (engineLabel) engineLabel.textContent = 'Motor CP-SAT — ' + dados.status;
      } catch (err) {
        console.error('Falha na otimização:', err);
        if (aviso) { aviso.style.color = 'var(--red)'; aviso.textContent = 'Não foi possível falar com o motor.'; }
      } finally {
        if (btnSim) { btnSim.disabled = false; btnSim.innerText = rotuloSim; }
        if (btnApl) { btnApl.disabled = false; btnApl.innerText = rotuloApl; }
      }
    }
'''

# ---------------------------------------------------------------------------
# 2. Handler dos botoes (substitui o listener antigo do btnSimular)
# ---------------------------------------------------------------------------
HANDLERS = '''
    // ---------------------------------------------------------------------
    // BOTOES DA ABA ESCALAS — ligados ao motor real
    // ---------------------------------------------------------------------
    const btnSimular = document.getElementById('btnSimular');
    if (btnSimular) {
      btnSimular.addEventListener('click', () => rodarMotor(false, 15));
    }

    const btnAplicarEscala = document.getElementById('btnAplicar');
    if (btnAplicarEscala) {
      btnAplicarEscala.addEventListener('click', () => rodarMotor(true, 15));
    }

    const btnDesfazerSim = document.getElementById('btnDesfazer');
    if (btnDesfazerSim) {
      btnDesfazerSim.addEventListener('click', () => {
        // Desfazer volta a exibir o que esta publicado no banco. Faz sentido
        // justamente porque "Simular" nao gravou nada.
        if (escalasDoBanco.length) {
          aplicarNaTabela(escalasDoBanco);
          showStatus('Simulação descartada. Exibindo a escala publicada.', 'ok');
        } else {
          gerarEscalasDinamicas();
          showStatus('Simulação descartada.', 'ok');
        }
        btnDesfazerSim.disabled = true;
      });
    }

    const btnAtualizarEscalas = document.getElementById('btnRefreshTable');
    if (btnAtualizarEscalas) {
      // Substitui o listener antigo (que sorteava valores) por recarga do banco.
      const clone = btnAtualizarEscalas.cloneNode(true);
      btnAtualizarEscalas.parentNode.replaceChild(clone, btnAtualizarEscalas);
      clone.addEventListener('click', () => carregarEscalasDoBanco(false));
    }
'''


def inserir_modulo(html: str) -> tuple[str, bool]:
    if 'escalasDoBanco' in html:
        return html, False
    alvo = "    const screens = document.querySelectorAll('.screen');"
    if alvo not in html:
        return html, False
    return html.replace(alvo, MODULO + "\n" + alvo, 1), True


def inserir_handlers(html: str) -> tuple[str, bool]:
    if 'rodarMotor(false, 15)' in html:
        return html, False
    alvo = "    gerarDisruptionsDinamicas();\r\n    gerarEscalasDinamicas();\r\n"
    if alvo in html:
        return html.replace(alvo, alvo + HANDLERS, 1), True
    # Tenta sem \r
    alvo2 = "    gerarDisruptionsDinamicas();\n    gerarEscalasDinamicas();\n"
    if alvo2 in html:
        return html.replace(alvo2, alvo2 + HANDLERS, 1), True
    return html, False


def ligar_switch(html: str) -> tuple[str, bool]:
    """Carrega as escalas do banco ao entrar na aba."""
    if "name === 'escalas'" in html and 'carregarEscalasDoBanco' in html.split("name === 'escalas'")[1][:400]:
        return html, False
    alvo = """        if (name === 'tripulantes') {
          carregarTripulantes(false);
        }"""
    if alvo in html:
        novo = alvo + """

        if (name === 'escalas') {
          carregarEscalasDoBanco(true);
        }"""
        return html.replace(alvo, novo, 1), True
    return html, False


def main() -> int:
    if not ALVO.exists():
        print(f"ERRO: {ALVO.resolve()} nao encontrado. Rode dentro de C:\\SkySync\\backend")
        return 1

    original = ALVO.read_text(encoding="utf-8")
    shutil.copy2(ALVO, ALVO.with_suffix(".html.bak2"))
    print(f"Backup: {ALVO.with_suffix('.html.bak2').name}")
    print()

    html = original

    html, ok_mod = inserir_modulo(html)
    print(f"1. modulo de integracao   {'OK' if ok_mod else 'ja existia / nao encontrado'}")

    html, ok_hand = inserir_handlers(html)
    print(f"2. handlers dos botoes    {'OK' if ok_hand else 'ja existia / nao encontrado'}")

    html, ok_sw = ligar_switch(html)
    print(f"3. gancho na aba Escalas  {'OK' if ok_sw else 'ja existia / nao encontrado'}")

    if html == original:
        print()
        print("Nada mudou — os blocos ja estavam aplicados.")
        return 0

    ALVO.write_text(html, encoding="utf-8")
    print()
    print(f"index.html atualizado ({len(original)} -> {len(html)} caracteres)")
    print()
    print("Teste: abra a aba Escalas. A tabela deve mostrar as 75 alocacoes")
    print("do banco (se voce ja rodou a otimizacao pelo console).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
