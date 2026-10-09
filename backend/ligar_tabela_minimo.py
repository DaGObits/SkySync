"""Alteracao MINIMA: a tabela tenta o banco; se falhar, mantem o que ja tinha.

Nao remove nada. Nao mexe em botao. Acrescenta UMA chamada no fim de
carregarDadosLocais(). Se a API nao responder, a tela fica exatamente como
esta hoje.
"""
from pathlib import Path

p = Path("static/index.html")
html = p.read_text(encoding="utf-8")

if "buscarEscalasDoBanco" in html:
    print("Ja aplicado.")
    raise SystemExit(0)

FUNCAO = """
    // ---------------------------------------------------------------------
    // LEITURA DO BANCO — aditivo.
    //
    // Roda DEPOIS de carregarDadosLocais(). Se a API responder com escalas,
    // elas substituem os itens locais. Se falhar, nada muda: a tela continua
    // exatamente como estava.
    //
    // Todo o bloco esta em try/catch: uma falha aqui nao derruba a pagina.
    // ---------------------------------------------------------------------
    function buscarEscalasDoBanco() {
      try {
        fetch(API_URL + '/escalas/alocacoes', { credentials: 'include' })
          .then(function (res) {
            if (!res.ok) return null;
            return res.json();
          })
          .then(function (dados) {
            if (!dados || !dados.escalas || !dados.escalas.length) return;

            var linhas = dados.escalas.map(function (e) {
              var min = Math.round((Number(e.limite_aplicado) || 0) * 60);
              var teto = String(Math.floor(min / 60)).padStart(2, '0') + 'h' +
                         String(min % 60).padStart(2, '0');
              return {
                tripulante: e.tripulante,
                cargo: e.cargo,
                voo: e.voo,
                horas: e.horas,
                limitRbac: teto,
                bloqueado: !e.conforme,
                risco: !e.conforme ? 'alto' : (e.ocupacao_percentual >= 85 ? 'medio' : 'baixo'),
                badgeKey: !e.conforme ? 'highFatigueRisk' : 'normalOperation',
                rota: e.rota,
                solucao: e.motivo,
                desc: 'Ocupacao de ' + e.ocupacao_percentual + '% do teto.'
              };
            });

            dadosOperacionais = linhas;
            gerarEscalasDinamicas();

            var cap = document.getElementById('historyCaptionText');
            if (cap) {
              cap.textContent = dados.total + ' alocacao(oes) do banco em ' + dados.data +
                                ' (' + dados.conformes + ' conformes)';
            }
            showStatus(dados.total + ' alocacao(oes) carregada(s) do banco.', 'ok');
          })
          .catch(function (e) { console.error('Banco indisponivel, mantendo dados locais:', e); });
      } catch (e) {
        console.error('buscarEscalasDoBanco falhou:', e);
      }
    }
"""

# Insere a funcao logo antes da chamada carregarDadosLocais();
ancora = "    carregarDadosLocais();"
if ancora not in html:
    print("ANCORA NAO ENCONTRADA — me avise.")
    raise SystemExit(1)

html = html.replace(ancora, FUNCAO + "\n" + ancora + "\n\n    // Tenta o banco imediatamente depois dos dados locais.\n    buscarEscalasDoBanco();", 1)

p.write_text(html, encoding="utf-8")
print("Aplicado: a tabela agora tenta o banco em seguida.")
print()
print("Se o console mostrar erro, restaure com:")
print("  Copy-Item static\\index.html.antes-limpeza static\\index.html -Force")
