from pathlib import Path

# --- 1. Renomeia a rota no backend ----------------------------------------
p = Path("blueprints/escalas_voos.py")
t = p.read_text(encoding="utf-8")

if '@bp.get("/escalas/alocacoes")' in t:
    print("1. rota backend: ja corrigida")
elif '@bp.get("/escalas")' in t:
    t = t.replace('@bp.get("/escalas")', '@bp.get("/escalas/alocacoes")', 1)
    p.write_text(t, encoding="utf-8")
    print("1. rota backend: GET /api/escalas -> GET /api/escalas/alocacoes")
else:
    print("1. rota backend: PADRAO NAO ENCONTRADO")

# --- 2. Confirma a rota no front ------------------------------------------
f = Path("static/index.html")
h = f.read_text(encoding="utf-8")

if "/escalas/alocacoes" in h:
    print("2. front: ja aponta para /api/escalas/alocacoes")
else:
    print("2. front: NAO aponta — rode o ligar_escalas_leitura.py")

# --- 3. Lista as rotas registradas no blueprint ---------------------------
print()
print("3. rotas declaradas em escalas_voos.py:")
for i, linha in enumerate(t.splitlines(), 1):
    if "@bp." in linha and "route" not in linha:
        print(f"   {i}: {linha.strip()}")
