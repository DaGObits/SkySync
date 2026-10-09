"""Insere o gancho de aba do jeito certo, sem depender de texto exato."""
from pathlib import Path
import re

p = Path("static/index.html")
html = p.read_text(encoding="utf-8")

# Onde a chamada ja aparece?
print("Ocorrencias de carregarEscalasDoBanco(true):", html.count("carregarEscalasDoBanco(true)"))
for i, linha in enumerate(html.splitlines(), 1):
    if "carregarEscalasDoBanco(true)" in linha:
        print(f"  linha {i}: {linha.strip()[:80]}")

# Localiza o switchScreen e insere dentro dele
m = re.search(r"function switchScreen\(name\)\s*\{", html)
if not m:
    print()
    print("switchScreen NAO ENCONTRADO — me avise.")
    raise SystemExit(1)

# Ja existe um gancho de aba para escalas?
trecho = html[m.start():m.start() + 1200]
if re.search(r"name\s*===\s*'escalas'", trecho):
    print()
    print("Gancho de aba JA existe dentro do switchScreen.")
    raise SystemExit(0)

insercao = """
        if (name === 'escalas') {
          carregarEscalasDoBanco(true);
        }
"""
# Insere logo apos a abertura da funcao (antes do try) — simples e seguro
pos = m.end()
html = html[:pos] + insercao + html[pos:]
p.write_text(html, encoding="utf-8")

print()
print("Gancho inserido dentro do switchScreen.")
print("Rode:  .venv\\Scripts\\python.exe verificar_integracao.py")
