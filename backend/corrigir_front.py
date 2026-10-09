from pathlib import Path

p = Path("static/index.html")
t = p.read_text(encoding="utf-8")

antes = "fetch(`${API_URL}/escalas`, { credentials: 'include' })"
depois = "fetch(`${API_URL}/escalas/alocacoes`, { credentials: 'include' })"

if depois in t:
    print("Ja estava corrigido.")
elif antes in t:
    p.write_text(t.replace(antes, depois, 1), encoding="utf-8")
    print("Front apontado para /api/escalas/alocacoes")
else:
    print("PADRAO NAO ENCONTRADO — procurando variacoes:")
    for i, linha in enumerate(t.splitlines(), 1):
        if "/escalas" in linha and "fetch" in linha:
            print(f"  {i}: {linha.strip()[:100]}")
