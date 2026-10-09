"""Camada de acesso ao banco.

O ponto central: `get_db_connection()` é um *context manager* que garante
commit no sucesso e rollback no erro, sempre fechando a conexão. Nenhum handler
de rota fecha conexão na mão — era aí que a versão antiga vazava conexões.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from flask import current_app, g


def _db_path() -> str:
    """Caminho do banco: config da app, ou a da app de teste."""
    try:
        return current_app.config["DB_PATH"]
    except RuntimeError:
        # Fora do contexto Flask (scripts, CLI) cai no default do módulo.
        from config import Config

        return Config.DB_PATH


def _connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    # WAL melhora a concorrência de leitura; foreign_keys precisa ser ligado
    # por conexão no SQLite.
    conn.execute("PRAGMA foreign_keys = ON")
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_connection() -> sqlite3.Connection:
    """Conexão por-requisição, guardada em `g` e fechada no teardown."""
    if "db" not in g:
        g.db = _connect(_db_path())
    return g.db


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    """Uso fora do ciclo de requisição (scripts, testes, init)."""
    conn = _connect(_db_path())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Transação explícita dentro de uma requisição.

    Use quando várias escritas precisam ser atômicas — por exemplo ler o último
    `versao_index` e inserir a versão seguinte sem corrida.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_connection(_exception=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    """Aplica o schema.sql. Idempotente."""
    schema_path = Path(current_app.config["SCHEMA_PATH"])
    if not schema_path.exists():
        raise FileNotFoundError(f"schema.sql não encontrado em {schema_path}")

    with get_db_connection() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))


def register(app) -> None:
    """Liga o teardown da conexão ao ciclo de vida da app."""
    app.teardown_appcontext(close_connection)
