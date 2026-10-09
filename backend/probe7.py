from pathlib import Path
for s in ("", "-wal", "-shm"):
    p = Path(str(Path(".teste_skysync.db")) + s)
    if p.exists():
        p.unlink()

from app import create_app
import db
app = create_app("testing")
with app.app_context():
    db.init_db()

c = app.test_client()
c.post("/api/auth/registrar", json={"nome":"Marina Costa","email":"m@m.com","senha":"Senha123"})
c.post("/api/auth/login", json={"email":"m@m.com","senha":"Senha123"})

r = c.post("/api/cenarios", json={"voos":5,"seed":1})
print("=== POST /api/cenarios ->", r.status_code)
corpo = r.get_json()
print("resumo:", corpo.get("resumo") if isinstance(corpo, dict) else str(corpo)[:200])
print("chaves:", list(corpo.keys()) if isinstance(corpo, dict) else "-")
print()

# --- Teste do solver que esta falhando -------------------------------------
from optimizer.solver import otimizar, OtimizacaoInviavel
from tests.conftest import TABELAS

def pool(n_voos, horas=0.0):
    from models import Tripulante
    t = []
    for i in range(n_voos):
        for cargo, qtd in (("Comandante",1),("Copiloto",1),("Comissário",3)):
            for j in range(qtd):
                t.append(Tripulante(id=f"{cargo[:2]}{i}{j}", nome=f"{cargo} {i}{j}",
                                    cargo=cargo, base="GRU", horas_acumuladas=horas,
                                    limite_horas=11.0))
    return t

from models import Voo
trip = pool(2)
for i, x in enumerate(trip):
    if i % 2 == 0:
        x.horas_acumuladas = 11.5
voos = [Voo(id="v1",codigo="A-1",origem="GRU",destino="VCP",duracao_horas=1.0,pouso_noturno=False,prioridade=1),
        Voo(id="v2",codigo="A-2",origem="GRU",destino="VCP",duracao_horas=1.0,pouso_noturno=False,prioridade=1)]
try:
    s = otimizar("GRU", trip, voos, limite_horas=11.0)
    print("=== solver OK:", s.status, s.total_alocacoes, "aloc")
except OtimizacaoInviavel as e:
    import json
    print("=== solver INFEASIBLE")
    print(json.dumps(e.diagnostico, indent=2, ensure_ascii=False))
