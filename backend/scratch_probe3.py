from app import create_app
import db

app = create_app("testing")
with app.app_context():
    db.init_db()

c = app.test_client()
r = c.post("/api/auth/registrar", json={"nome":"Teste","email":"t@t.com","senha":"Senha123"})
print("status:", r.status_code)
print("corpo:", r.get_json())
