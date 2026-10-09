from app import create_app
import db
app = create_app("testing")
with app.app_context():
    print("DB_BACKEND:", app.config.get("DB_BACKEND"))
    print("TESTING:", app.config.get("TESTING"))
    print("backend escolhido:", db._backend())
    print("caminho do schema:", db._caminho_do_schema())
    print("existe?", db._caminho_do_schema().exists())
    db.init_db()
    with db.transacao() as c:
        linhas = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print("TABELAS:", [l["name"] for l in linhas])
