from app import create_app
import db, sqlite3
app = create_app("testing")
with app.app_context():
    db.init_db()
    with db.transacao() as c:
        c.execute("SELECT 1")

print("sqlite versao:", sqlite3.sqlite_version)

from dados.gerador import gerar_cenario
cen = gerar_cenario(voos=3, seed=1)
print("cenario ok:", len(cen.tripulantes), len(cen.voos))

from blueprints.cenarios import criar_cenario
c = app.test_client()
c.post("/api/auth/registrar", json={"nome":"M","email":"m@m.com","senha":"Senha123"})
c.post("/api/auth/login", json={"email":"m@m.com","senha":"Senha123"})
r = c.post("/api/cenarios", json={"voos":3,"seed":1})
print("status:", r.status_code)
print("corpo:", str(r.get_json())[:400])
