from pathlib import Path
import shutil

# --- 1. solver.py: base vazia nao zera o modelo ---------------------------
p = Path("optimizer/solver.py")
t = p.read_text(encoding="utf-8")

antes = """    if not bases_por_regiao:
        return _TODAS_AS_BASES"""

depois = """    if not bases_por_regiao or not base:
        # Base ausente NAO deve zerar o modelo: sem ela nao ha como filtrar
        # por regiao, e derrubar todas as variaveis tornaria o cenario
        # INFEASIBLE por um dado incompleto. Ser permissivo e mais seguro.
        return _TODAS_AS_BASES"""

if antes in t:
    shutil.copy2(p, p.with_suffix(".py.bak3"))
    t = t.replace(antes, depois, 1)
    p.write_text(t, encoding="utf-8")
    print("1. solver.py: base vazia aceita qualquer origem")
else:
    print("1. solver.py: PADRAO NAO ENCONTRADO")

# --- 2. test_api.py: tripulantes informam base ----------------------------
f = Path("tests/test_api.py")
tf = f.read_text(encoding="utf-8")

# Acrescenta "base": "GRU" em cada tripulante do _payload_composicao
if '"base": "GRU", "cargo"' not in tf:
    pares = [
        ('{"id": f"cm{i}", "nome": f"CM {i}", "cargo": "Comandante",',
         '{"id": f"cm{i}", "nome": f"CM {i}", "base": "GRU", "cargo": "Comandante",'),
        ('{"id": f"cp{i}", "nome": f"CP {i}", "cargo": "Copiloto",',
         '{"id": f"cp{i}", "nome": f"CP {i}", "base": "GRU", "cargo": "Copiloto",'),
        ('{"id": f"cc{i}a", "nome": f"CC {i}A", "cargo": "Comissário",',
         '{"id": f"cc{i}a", "nome": f"CC {i}A", "base": "GRU", "cargo": "Comissário",'),
        ('{"id": f"cc{i}b", "nome": f"CC {i}B", "cargo": "Comissário",',
         '{"id": f"cc{i}b", "nome": f"CC {i}B", "base": "GRU", "cargo": "Comissário",'),
        ('{"id": f"cc{i}c", "nome": f"CC {i}C", "cargo": "Comissário",',
         '{"id": f"cc{i}c", "nome": f"CC {i}C", "base": "GRU", "cargo": "Comissário",'),
    ]
    n = 0
    for a, b in pares:
        if a in tf:
            tf = tf.replace(a, b, 1)
            n += 1
    f.write_text(tf, encoding="utf-8")
    print(f"2. test_api.py: {n} de 5 tripulantes ganharam base")
else:
    print("2. test_api.py: ja tinha base")

print()
print("Agora rode:  .venv\\Scripts\\python.exe -m pytest -v")
