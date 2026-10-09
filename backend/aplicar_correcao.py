"""Aplica a correcao do banco de teste (arquivo em vez de :memory:)."""
import re
from pathlib import Path

# --- 1. config.py -----------------------------------------------------------
cfg = Path("config.py")
texto = cfg.read_text(encoding="utf-8")

antigo = '''    DB_BACKEND = "sqlite"
    SQLITE_PATH = ":memory:"'''
novo = '''    DB_BACKEND = "sqlite"
    SQLITE_PATH = os.getenv(
        "SKYSYNC_TEST_DB", str(BASE_DIR / ".teste_skysync.db")
    )'''

if antigo in texto:
    cfg.write_text(texto.replace(antigo, novo), encoding="utf-8")
    print("config.py: SQLITE_PATH trocado para arquivo temporario.")
elif "SKYSYNC_TEST_DB" in texto:
    print("config.py: ja estava correto.")
else:
    print("config.py: PADRAO NAO ENCONTRADO — aplicar a mao.")

# --- 2. db.py --------------------------------------------------------------
dbp = Path("db.py")
texto_db = dbp.read_text(encoding="utf-8")

if "cache=shared" in texto_db:
    # Versao com memoria compartilhada: trocar por arquivo.
    alvo = re.search(
        r'    if caminho == ":memory:":.*?return _ConexaoSqlite\(conexao\)',
        texto_db,
        re.DOTALL,
    )
    if alvo:
        texto_db = texto_db[: alvo.start()] + '''    # O diretorio precisa existir antes do connect.
    if caminho != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(caminho, detect_types=sqlite3.PARSE_DECLTYPES)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return _ConexaoSqlite(conexao)''' + texto_db[alvo.end():]
        if "import os" in texto_db and "os.getpid" not in texto_db:
            texto_db = texto_db.replace("import os\nimport sqlite3", "import sqlite3", 1)
        dbp.write_text(texto_db, encoding="utf-8")
        print("db.py: trocado de memoria compartilhada para arquivo.")
    else:
        print("db.py: regex nao casou — aplicar a mao.")
elif "mkdir" in texto_db and "SQLITE_PATH" in texto_db:
    print("db.py: ja estava correto.")
else:
    print("db.py: formato desconhecido — aplicar a mao.")
