from pathlib import Path
import re

print("=" * 70)
print("1. 'resumo' aparece ONDE no cenarios.py?")
print("=" * 70)
c = Path("blueprints/cenarios.py").read_text(encoding="utf-8")
for i, linha in enumerate(c.splitlines(), 1):
    if "resumo" in linha:
        print(f"  linha {i:4}: {linha}")

print()
print("=" * 70)
print("2. O que Cenario.resumo() devolve?")
print("=" * 70)
from dados.gerador import gerar_cenario
cen = gerar_cenario(voos=3, seed=1)
r = cen.resumo()
print("  chaves:", list(r.keys()))
print("  conteudo:", r)

print()
print("=" * 70)
print("3. A funcao pool() do test_solver.py passa o cargo?")
print("=" * 70)
s = Path("tests/test_solver.py").read_text(encoding="utf-8")
m = re.search(r"^def pool\(.*?(?=\n\ndef |\n\n# )", s, re.DOTALL | re.MULTILINE)
if m:
    print(m.group(0)[:1500])
else:
    print("  funcao pool NAO ENCONTRADA")
