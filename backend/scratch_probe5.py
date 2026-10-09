import os
from pathlib import Path

# Banco limpo: remove qualquer arquivo de teste anterior.
alvo = Path(".teste_skysync.db")
for s in ("", "-wal", "-shm"):
    p = Path(str(alvo) + s)
    if p.exists():
        p.unlink()

from app import create_app
import db
app = create_app("testing")
with app.app_context():
    db.init_db()

c = app.test_client()
r1 = c.post("/api/auth/registrar", json={"nome":"M","email":"m@m.com","senha":"Senha123"})
print("registrar:", r1.status_code, r1.get_json())

r2 = c.post("/api/auth/login", json={"email":"m@m.com","senha":"Senha123"})
print("login:", r2.status_code, r2.get_json())

r3 = c.post("/api/cenarios", json={"voos":3,"seed":1})
print("cenarios:", r3.status_code)
corpo = r3.get_json()
print("corpo:", str(corpo)[:600])
