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
r1 = c.post("/api/auth/registrar", json={"nome":"Marina Costa","email":"m@m.com","senha":"Senha123"})
print("registrar:", r1.status_code, r1.get_json())

r2 = c.post("/api/auth/login", json={"email":"m@m.com","senha":"Senha123"})
print("login:", r2.status_code, r2.get_json())

r3 = c.post("/api/cenarios", json={"voos":3,"seed":1})
print("cenarios:", r3.status_code)
print("corpo:", str(r3.get_json())[:700])
