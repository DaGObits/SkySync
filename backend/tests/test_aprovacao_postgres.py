"""Integração opcional: SKYSYNC_TEST_POSTGRES deve permitir criar um schema temporário."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from app import create_app


@pytest.fixture
def banco_propostas():
    dsn = os.getenv("SKYSYNC_TEST_POSTGRES")
    if not dsn:
        pytest.skip("requer SKYSYNC_TEST_POSTGRES")
    schema = "teste_proposta_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        try:
            local = make_conninfo(dsn, options=f"-c search_path={schema}")
            with psycopg.connect(local, autocommit=True) as db:
                backend = Path(__file__).resolve().parents[1]
                for arquivo in ("schema.sql", "schema_voos.sql"):
                    db.execute((backend / arquivo).read_text())
                db.execute("""INSERT INTO voos (id,codigo,origem,destino,duracao_horas)
                              VALUES ('v1','DEMO1','GRU','VCP',1.5)""")
                for i, cargo in enumerate(["Comandante", "Copiloto"] + ["Comissário"] * 3):
                    db.execute("INSERT INTO tripulantes (id,nome,cargo,base) VALUES (%s,%s,%s,'GRU')",
                               (str(i), f"Pessoa {i}", cargo))
                db.execute("""INSERT INTO jornadas (tripulante_id, periodo)
                              SELECT id, CURRENT_DATE FROM tripulantes UNION ALL
                              SELECT id, CURRENT_DATE - 1 FROM tripulantes""")
                app = create_app("development")
                app.config.update(DATABASE_URL=local)
                yield app, db
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


def test_simular_revalidar_e_aprovar_uma_vez(banco_propostas):
    app, db = banco_propostas

    def enviar(dados, usuario=1):
        with app.test_client() as client:
            with client.session_transaction() as sessao:
                sessao["usuario_id"] = usuario
            return client.post("/api/escalas/propostas", json=dados)

    proposta = enviar({}).get_json()
    aprovar = {"gravar": True, "proposta_id": proposta["proposta_id"]}
    assert enviar({"gravar": True}).status_code == 400
    assert enviar(aprovar, usuario=2).status_code == 404
    db.execute("UPDATE jornadas SET descanso_ok = FALSE WHERE tripulante_id='0'")
    assert enviar(aprovar).status_code == 409
    assert db.execute("SELECT count(*) FROM escalas").fetchone() == (0,)
    assert db.execute("SELECT sum(horas_acumuladas) FROM jornadas").fetchone() == (0,)
    db.execute("UPDATE jornadas SET descanso_ok = TRUE")
    with ThreadPoolExecutor(2) as pool:
        respostas = list(pool.map(enviar, [aprovar, aprovar]))
    assert sorted(r.get_json()["escalas_gravadas"] for r in respostas) == [0, 5]
    assert set(db.execute("SELECT tripulante_id, voo_id FROM escalas")) == {
        (a["tripulante_id"], a["voo_id"]) for a in proposta["alocacoes"]
    }
    jornadas = db.execute("""SELECT periodo = CURRENT_DATE, sum(horas_acumuladas), sum(voos_no_periodo)
                             FROM jornadas GROUP BY periodo ORDER BY periodo""").fetchall()
    assert jornadas == [(False, 0, 0), (True, 7.5, 5)]
