from pathlib import Path

print("=== conftest.py ===")
t = Path("tests/conftest.py").read_text(encoding="utf-8")
print("tem _limpar_tabelas :", "_limpar_tabelas" in t)
print("tem DELETE FROM     :", "DELETE FROM" in t)
print("tamanho             :", len(t), "caracteres")
print()

print("=== models.py ===")
m = Path("models.py").read_text(encoding="utf-8")
print("Tripulante.to_dict  :", '"aclimatado": self.aclimatado' in m)
print("Voo.to_dict         :", '"pouso_noturno": self.pouso_noturno' in m)
print()

print("=== test_solver.py ===")
s = Path("tests/test_solver.py").read_text(encoding="utf-8")
print("pool dobrado        :", "voos=2, horas=0.0" in s)
print()

print("=== restricoes.py ===")
r = Path("optimizer/restricoes.py").read_text(encoding="utf-8")
print("tem bloquear()      :", "def bloquear" in r)
print("tem pares_de()      :", "def pares_de" in r)
print()

print("=== banco de teste ===")
for nome in (".teste_skysync.db", "skysync.db"):
    p = Path(nome)
    print(f"{nome:22} existe: {p.exists()}", f"({p.stat().st_size} bytes)" if p.exists() else "")
