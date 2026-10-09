from pathlib import Path

p = Path("static/index.html")
if not p.exists():
    print("static/index.html NAO ENCONTRADO")
    raise SystemExit(1)

html = p.read_text(encoding="utf-8")
print("=== index.html ===")
print("tamanho :", len(html), "caracteres")
print()
print("escalasDoBanco        :", "escalasDoBanco" in html)
print("carregarEscalasDoBanco:", "carregarEscalasDoBanco" in html)
print("rodarMotor(           :", "rodarMotor(" in html)
print("alocacaoParaLinha     :", "alocacaoParaLinha" in html)
print("gancho name === escalas:", "name === 'escalas'" in html)
print()
print("=== backups ===")
for nome in ("index.html.bak", "index.html.bak2"):
    b = Path("static") / nome
    print(f"{nome:20} {'existe (' + str(b.stat().st_size) + ' bytes)' if b.exists() else 'nao existe'}")
