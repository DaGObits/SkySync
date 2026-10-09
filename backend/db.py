"""Camada de acesso ao banco (PostgreSQL).

Decisões que valem explicação:

1. **Conexão por requisição, fechada no teardown.** Nada de conexão aberta na
   mão do handler — era aí que a versão antiga vazava.

2. **SQL portável.** As consultas usam `%s` (placeholder do psycopg). O
   adaptador `_CursorSqlite` traduz para `?` quando o backend é SQLite, o que
   permite rodar os testes em memória sem tocar o banco de nuvem.

3. **Transações explícitas.** Nada de commit implícito: escrita roda dentro de
   `transacao()`, que faz commit no sucesso e rollback no erro.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from flask import current_app, g

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - obrigatório apenas em produção
    psycopg = None


class ErroDeBanco(RuntimeError):
    """Falha de banco já traduzida, sem vazar detalhe de driver para o cliente."""


# ---------------------------------------------------------------------------
# Adaptador leve para SQLite (usado apenas nos testes)
# ---------------------------------------------------------------------------
class _CursorSqlite:
    """Traduz o SQL escrito para PostgreSQL em SQL entendido pelo SQLite."""

    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor

    @staticmethod
    def _traduzir(sql: str) -> str:
        return sql.replace("%s", "?")

    def execute(self, sql: str, params: tuple | list = ()) -> "_CursorSqlite":
        self._cursor.execute(self._traduzir(sql), params)
        return self

    def fetchone(self):
        linha = self._cursor.fetchone()
        return dict(linha) if linha is not None else None

    def fetchall(self):
        return [dict(linha) for linha in self._cursor.fetchall()]

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount


class _ConexaoSqlite:
    """Adaptador que imita a interface usada do psycopg.Connection."""

    def __init__(self, conexao: sqlite3.Connection):
        self._conexao = conexao

    def execute(self, sql: str, params: tuple | list = ()) -> _CursorSqlite:
        return _CursorSqlite(self._conexao.cursor()).execute(sql, params)

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self) -> None:
        self._conexao.commit()

    def rollback(self) -> None:
        self._conexao.rollback()

    def close(self) -> None:
        self._conexao.close()


# ---------------------------------------------------------------------------
# Conexões
# ---------------------------------------------------------------------------
def _backend() -> str:
    """`sqlite` nos testes; `postgres` em qualquer outro ambiente."""
    if current_app.config.get("DB_BACKEND") == "sqlite":
        return "sqlite"
    if current_app.config.get("TESTING"):
        return "sqlite"
    return "postgres"


def _conectar_postgres():
    if psycopg is None:
        raise ErroDeBanco(
            "psycopg não instalado. Rode: pip install 'psycopg[binary]'"
        )

    url = current_app.config["DATABASE_URL"]
    if not url:
        raise ErroDeBanco(
            "DATABASE_URL não configurada. Copie .env.example para .env e cole "
            "a string de conexão do seu banco (Neon, Supabase, Railway)."
        )

    return psycopg.connect(
        url,
        row_factory=dict_row,
        connect_timeout=current_app.config["DB_CONNECT_TIMEOUT"],
        autocommit=False,
    )


def _conectar_sqlite():
    caminho = current_app.config.get("SQLITE_PATH", ":memory:")
    conexao = sqlite3.connect(caminho, detect_types=sqlite3.PARSE_DECLTYPES)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return _ConexaoSqlite(conexao)


def get_conexao():
    """Conexão por-requisição, guardada em `g` e fechada no teardown."""
    if "db" not in g:
        g.db = _conectar_sqlite() if _backend() == "sqlite" else _conectar_postgres()
    return g.db


@contextmanager
def transacao() -> Iterator[Any]:
    """Transação em uma única conexão."""
    conexao = get_conexao()
    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise


def close_connection(_exception=None) -> None:
    conexao = g.pop("db", None)
    if conexao is not None:
        conexao.close()


def init_db() -> None:
    """Aplica o schema.sql. Idempotente (usa IF NOT EXISTS)."""
    caminho = Path(current_app.config["SCHEMA_PATH"])
    if not caminho.exists():
        raise FileNotFoundError(f"schema.sql não encontrado em {caminho}")

    sql = caminho.read_text(encoding="utf-8")

    if _backend() == "sqlite":
        # O SQLite não entende SERIAL, JSONB nem ON CONFLICT DO NOTHING.
        # Nos testes aplicamos um subconjunto equivalente; a validação do
        # schema real acontece no PostgreSQL.
        conexao = get_conexao()
        for comando in _dividir_comandos(_sql_para_sqlite(sql)):
            conexao.execute(comando)
        conexao.commit()
        return

    conexao = get_conexao()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(sql)
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise


def _sql_para_sqlite(sql: str) -> str:
    """Converte o schema PostgreSQL no equivalente mínimo para SQLite."""
    substituicoes = [
        ("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("TIMESTAMPTZ", "TIMESTAMP"),
        ("JSONB", "TEXT"),
        ("BOOLEAN", "INTEGER"),
        ("FALSE", "0"),
        ("TRUE", "1"),
        ("NOW()", "CURRENT_TIMESTAMP"),
        ("LOWER(email)", "email"),
        ("DOUBLE PRECISION", "REAL"),
        ("INSERT INTO schema_version (versao) VALUES (2)\n    ON CONFLICT (versao) DO NOTHING;",
         "INSERT OR IGNORE INTO schema_version (versao) VALUES (2);"),
    ]
    for antigo, novo in substituicoes:
        sql = sql.replace(antigo, novo)
    return sql


def _dividir_comandos(sql: str) -> list[str]:
    """Divide o script em comandos, ignorando comentários."""
    linhas = [linha for linha in sql.splitlines() if not linha.strip().startswith("--")]
    texto = "\n".join(linhas)
    return [c.strip() for c in texto.split(";") if c.strip()]


def register(app) -> None:
    """Liga o teardown da conexão ao ciclo de vida da app."""
    app.teardown_appcontext(close_connection)
