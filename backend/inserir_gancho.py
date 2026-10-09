"""Insere o gancho da aba Escalas no switchScreen."""
from pathlib import Path

p = Path("static/index.html")
html = p.read_text(encoding="utf-8")

if "carregarEscalasDoBanco(true)" in html:
    print("Gancho JA existe.")
    raise SystemExit(0)

# Ancora: o trecho do switchScreen que trata as disrupcoes. Ele existe no
# arquivo desde o inicio, entao serve de ponto de insercao confiavel.
alvo = """        if (name === 'disrupcoes') {
          gerarDisruptionsDinamicas();
        }"""

if alvo not in html:
    print("ANCORA NAO ENCONTRADA. Alternativa: procurar outra.")
    for i, linha in enumerate(html.splitlines(), 1):
        if "switchScreen" in linha or "name ===" in linha:
            print(f"  {i}: {linha.strip()[:90]}")
    raise SystemExit(1)

novo = alvo + """

        if (name === 'escalas') {
          carregarEscalasDoBanco(true);
        }

        if (name === 'tripulantes') {
          carregarTripulantes(false);
        }"""

html = html.replace(alvo, novo, 1)
p.write_text(html, encoding="utf-8")

print("Gancho inserido com sucesso.")
print()
print("Confirme com:  .venv\\Scripts\\python.exe verificar_integracao.py")
