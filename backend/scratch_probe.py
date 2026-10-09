import sqlite3
sql = open("tests/schema_teste.sql", encoding="utf-8").read()
c = sqlite3.connect(":memory:")
c.executescript(sql)
tabelas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("TABELAS CRIADAS:", tabelas)
