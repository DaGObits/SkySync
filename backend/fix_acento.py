from pathlib import Path

m = Path("models.py")
t = m.read_text(encoding="utf-8")

antes = t
t = t.replace('CARGOS_VALIDOS = ("Comandante", "Copiloto", "Comissario")',
              'CARGOS_VALIDOS = ("Comandante", "Copiloto", "Comissário")')

# Se a linha ja estava com acento, o replace nao muda nada — conferimos.
if t == antes and '"Comissário"' not in t:
    print("PADRAO NAO ENCONTRADO. Linha atual de CARGOS_VALIDOS:")
    for linha in t.splitlines():
        if "CARGOS_VALIDOS" in linha:
            print("   ", linha)
else:
    m.write_text(t, encoding="utf-8")
    print("models.py: CARGOS_VALIDOS padronizado para 'Comissário'.")

# --- Conferir a grafia nos outros arquivos -------------------------------
print()
print("=== Grafias de Comissario por arquivo ===")
for nome in ("models.py", "dados/gerador.py", "optimizer/restricoes.py",
             "optimizer/solver.py", "tests/test_api.py", "tests/test_solver.py"):
    p = Path(nome)
    if not p.exists():
        print(f"{nome:32} (nao existe)")
        continue
    texto = p.read_text(encoding="utf-8")
    com = texto.count("Comissário")
    sem = texto.count("Comissario")
    marca = "  <-- MISTURADO" if com and sem else ""
    print(f"{nome:32} com acento: {com:3}   sem acento: {sem:3}{marca}")

print()
print("Agora rode:  .venv\\Scripts\\python.exe -m pytest -v")
