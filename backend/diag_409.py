from app import create_app
from db import init_db
import json

app = create_app("testing")
with app.app_context():
    init_db()          # <-- cria as tabelas no SQLite de teste

c = app.test_client()
c.post("/api/auth/registrar", json={"nome":"Marina Costa","email":"m@m.com","senha":"Senha123"})
c.post("/api/auth/login", json={"email":"m@m.com","senha":"Senha123"})

payload = {
  "base": "GRU",
  "tripulantes": [
    {"id":"cm0","nome":"CM 0","cargo":"Comandante","horas_acumuladas":1.0,"limite_horas":11.0},
    {"id":"cp0","nome":"CP 0","cargo":"Copiloto","horas_acumuladas":1.0,"limite_horas":11.0},
    {"id":"cc0a","nome":"CC 0A","cargo":"Comissário","horas_acumuladas":1.0,"limite_horas":11.0},
    {"id":"cc0b","nome":"CC 0B","cargo":"Comissário","horas_acumuladas":1.0,"limite_horas":11.0},
    {"id":"cc0c","nome":"CC 0C","cargo":"Comissário","horas_acumuladas":1.0,"limite_horas":11.0}
  ],
  "voos": [{"id":"v0","codigo":"TAM-1","duracao_horas":2.0,"origem":"GRU","destino":"VCP"}]
}

r = c.post("/api/otimizacao", json=payload)
print("status:", r.status_code)
print(json.dumps(r.get_json(), indent=2, ensure_ascii=False))
