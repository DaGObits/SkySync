from pathlib import Path
import re

print("=" * 70)
print("cenarios.py — a funcao criar_cenario, como esta em disco")
print("=" * 70)
c = Path("blueprints/cenarios.py").read_text(encoding="utf-8")
print("tem 'resumo'      :", 'resumo' in c)
print("tem return jsonify:", 'return jsonify(payload)' in c)
print()
# Mostra as 25 linhas finais, que e onde o resumo deveria entrar
linhas = c.splitlines()
print("--- ultimas 25 linhas ---")
for i, l in enumerate(linhas[-25:], len(linhas) - 24):
    print(f"{i:4}  {l}")

print()
print("=" * 70)
print("test_solver.py — a funcao do teste")
print("=" * 70)
s = Path("tests/test_solver.py").read_text(encoding="utf-8")
m = re.search(r"def test_conformidade_reflete_bloqueados.*?(?=\ndef |\Z)", s, re.DOTALL)
if m:
    print("--- funcao atual ---")
    print(m.group(0)[:1200])
else:
    print("FUNCAO NAO ENCONTRADA")
