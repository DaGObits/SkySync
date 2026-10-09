from pathlib import Path

p = Path("blueprints/escalas_voos.py")
t = p.read_text(encoding="utf-8")

antes = '@bp.get("/escalas")'
depois = '@bp.get("/escalas/alocacoes")'

if depois in t:
    print("Ja estava corrigido.")
elif antes in t:
    p.write_text(t.replace(antes, depois, 1), encoding="utf-8")
    print("Rota renomeada: GET /api/escalas -> GET /api/escalas/alocacoes")
else:
    print("PADRAO NAO ENCONTRADO — me manda o trecho da rota.")
