"""Verifica se o db.py em disco tem a correcao do banco de teste."""
from pathlib import Path

alvo = Path("db.py")
if not alvo.exists():
    print("ERRO: db.py nao encontrado nesta pasta.")
    print(f"     pasta atual: {Path.cwd()}")
    raise SystemExit(1)

texto = alvo.read_text(encoding="utf-8")

print("=== VERIFICACAO DO db.py ===")
print(f"arquivo : {alvo.resolve()}")
print(f"tamanho : {len(texto)} caracteres")
print()

tem_correcao = "cache=shared" in texto
tem_antiga = "_sql_para_sqlite" in texto

print(f"1. tem 'cache=shared'     : {tem_correcao}  {'OK' if tem_correcao else '<-- FALTA'}")
print(f"2. tem '_sql_para_sqlite' : {tem_antiga}   {'<-- ARQUIVO ANTIGO' if tem_antiga else 'OK (nao deve existir)'}")
print()

if not tem_correcao:
    print(">>> FALTANDO. Substituindo a funcao _conectar_sqlite...")

    trecho_antigo = '''def _conectar_sqlite():
    caminho = current_app.config.get("SQLITE_PATH", ":memory:")
    conexao = sqlite3.connect(caminho, detect_types=sqlite3.PARSE_DECLTYPES)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return _ConexaoSqlite(conexao)'''

    trecho_novo = '''def _conectar_sqlite():
    """No SQLite, cada connect(":memory:") abre um banco NOVO e vazio.
    Usamos cache=shared com um nome para que init_db e as requisicoes
    compartilhem o MESMO banco em memoria dentro do processo."""
    caminho = current_app.config.get("SQLITE_PATH", ":memory:")

    if caminho == ":memory:":
        nome = f"skysync_test_{os.getpid()}"
        conexao = sqlite3.connect(
            f"file:{nome}?mode=memory&cache=shared",
            uri=True,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
    else:
        conexao = sqlite3.connect(caminho, detect_types=sqlite3.PARSE_DECLTYPES)

    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return _ConexaoSqlite(conexao)'''

    if trecho_antigo in texto:
        texto = texto.replace(trecho_antigo, trecho_novo)
        if "import os" not in texto:
            texto = texto.replace("import sqlite3", "import os\nimport sqlite3", 1)
        alvo.write_text(texto, encoding="utf-8")
        print(">>> PRONTO: db.py corrigido com sucesso.")
    else:
        print(">>> ATENCAO: o trecho antigo nao foi encontrado literalmente.")
        print(">>> O db.py foi editado a mao. Cole o conteudo do db-corrigido.py.")
        raise SystemExit(2)
else:
    print(">>> O db.py JA ESTA CORRETO. O problema esta em outro lugar.")
