"""Liga SO a tabela de Escalas ao banco. Nao mexe em nenhum botao.

Seguro por desenho:
  * todo o codigo novo roda dentro de try/catch
  * nao substitui listeners existentes
  * se algo falhar, a pagina continua funcionando como antes
"""
from pathlib import Path
import re

p = Path("static/index.html")
html = p.read_text(encoding="utf-8")

if "escalasDoBanco" in html:
    print("Ja aplicado.")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# Modulo de leitura — so leitura, nenhum listener de botao
# ---------------------------------------------------------------------------
MODULO = '''
    // ---------------------------------------------------------------------
    // LEITURA DA ABA ESCALAS — dados reais do banco
    //
    // So LEITURA. Nenhum botao e alterado. Todo o bloco roda dentro de
    // try/catch, entao uma falha aqui nao derruba o resto da pagina.
    // ---------------------------------------------------------------------
    try {
      window.escalasDoBanco = [];

      window.formatarHorasEscala = function (horas) {
        var totalMin = Math.round((Number(horas) || 0) * 60);
        var h = String(Math.floor(totalMin / 60)).padStart(2, '0');
        var m = String(totalMin % 60).padStart(2, '0');
        return h + 'h' + m;
      };

      window.escalaParaLinha = function (e) {
        return {
          tripulante: e.tripulante,
          cargo: e.cargo,
          voo: e.voo,
          horas: e.horas,
          limitRbac: window.formatarHorasEscala(e.limite_aplicado),
          bloqueado: !e.conforme,
          risco: !e.conforme ? 'alto' : (e.ocupacao_percentual >= 85 ? 'medio' : 'baixo'),
          badgeKey: !e.conforme ? 'highFatigueRisk' : 'normalOperation',
          rota: e.rota,
          solucao: e.motivo,
          desc: 'Ocupacao de ' + e.ocupacao_percentual + '% do teto apos a alocacao.'
        };
      };

      window.carregarEscalasDoBanco = async function (silencioso) {
        var aviso = document.getElementById('liveStatus');
        try {
          var res = await fetch(API_URL + '/escalas/alocacoes', { credentials: 'include' });
          if (res.status === 401) { window.location.href = 'login.html'; return; }
          if (!res.ok) { throw new Error('HTTP ' + res.status); }

          var dados = await res.json();
          var linhas = (dados.escalas || []).map(window.escalaParaLinha);
          window.escalasDoBanco = linhas;

          if (!linhas.length) {
            if (aviso && !silencioso) {
              aviso.style.color = 'var(--text-600-solid)';
              aviso.textContent = 'Nenhuma escala publicada ainda. Use "Aplicar escala" para gravar uma.';
            }
            return;
          }

          var backup = dadosOperacionais;
          dadosOperacionais = linhas;
          try { gerarEscalasDinamicas(); } finally { dadosOperacionais = backup; }

          if (aviso && !silencioso) {
            aviso.style.color = 'var(--green)';
            aviso.textContent = dados.total + ' alocacao(oes) do banco - ' +
                                dados.conformes + ' conforme(s) - ' + dados.data + '.';
          }
        } catch (err) {
          console.error('Falha ao carregar escalas do banco:', err);
          if (aviso && !silencioso) {
            aviso.style.color = 'var(--red)';
            aviso.textContent = 'Nao foi possivel carregar as escalas do banco.';
          }
        }
      };
    } catch (e) {
      console.error('Modulo de escalas nao carregou:', e);
    }
'''

# ---------------------------------------------------------------------------
# Inserir antes da declaracao de screens (mesmo ponto de antes)
# ---------------------------------------------------------------------------
alvo = "    const screens = document.querySelectorAll('.screen');"
if alvo not in html:
    print("ANCORA NAO ENCONTRADA — me avise.")
    raise SystemExit(1)

html = html.replace(alvo, MODULO + "\n" + alvo, 1)

# ---------------------------------------------------------------------------
# Gancho: carrega ao entrar na aba Escalas, com guarda
# ---------------------------------------------------------------------------
m = re.search(r"function switchScreen\(name\)\s*\{", html)
if not m:
    print("switchScreen NAO ENCONTRADO — me avise.")
    raise SystemExit(1)

insercao = """
      try {
        if (name === 'escalas' && typeof window.carregarEscalasDoBanco === 'function') {
          window.carregarEscalasDoBanco(true);
        }
      } catch (e) { console.error('gancho escalas:', e); }
"""
html = html[:m.end()] + insercao + html[m.end():]

p.write_text(html, encoding="utf-8")
print("OK: tabela de Escalas ligada ao banco (somente leitura).")
print()
print("Teste: recarregue com Ctrl+F5 e clique na aba Escalas.")
print("A tela deve mostrar as alocacoes do banco, nao os 9 itens fixos.")
print()
print("Se travar de novo, restaure com:")
print("  copy /Y static\\index.html.bak3 static\\index.html")
