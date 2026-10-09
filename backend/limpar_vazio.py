from pathlib import Path
p = Path("static/index.html")
h = p.read_text(encoding="utf-8")

# No carregarEscalasDoBanco, quando vier vazio: limpar a tabela em vez de
# deixar os 9 itens antigos.
antigo = """          if (!linhas.length) {
            if (aviso && !silencioso) {"""
novo = """          if (!linhas.length) {
            // Limpa a tabela: sem isto os 9 itens do localStorage ficam na
            // tela como se fossem dados do banco.
            try {
              var tb = document.getElementById('crewTable');
              if (tb) tb.innerHTML = '';
              var cap = document.getElementById('historyCaptionText');
              if (cap) cap.textContent = 'Nenhuma escala publicada';
            } catch (e) {}
            if (aviso && !silencioso) {"""

if antigo in h:
    p.write_text(h.replace(antigo, novo, 1), encoding="utf-8")
    print("front: tabela limpa quando o banco nao tem alocacoes")
else:
    print("front: padrao nao encontrado — confira o ligar_escalas_leitura.py")
