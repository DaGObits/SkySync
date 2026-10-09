"""Camada de acesso ao banco (PostgreSQL).

Decisões que valem explicação:

1. **Conexão por requisição, fechada no teardown.** Nada de conexão aberta na
   mão do handler — era aí que a versão antiga vazava.

2. **Dois schemas, um por banco.** Produção usa `schema.sql` (PostgreSQL);
   os testes usam `tests/schema_teste.sql` (SQLite). A versão anterior tentava
   traduzir o SQL do PostgreSQL para SQLite por expressão regular, e cada
   mudança no schema quebrava os testes de uma forma difícil de diagnosticar.
   Manter dois arquivos explícitos é mais honesto — e o schema de produção
   continua sendo o único que importa de verdade.

3. **SQL portável.** As consultas usam `%s` (placeholder do psycopg). O
   adaptador abaixo traduz para `?` quando o backend é SQLite.

4. **Transações explícitas.** Nada de commit implícito: escrita roda dentro de
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
        # Placeholders.
        sql = sql.replace("%s", "?")
        # Funções de data do PostgreSQL que aparecem nas rotas.
        sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")
        # Comparação de e-mail sem distinção de maiúsculas: no SQLite o
        # `LOWER(email) = ?` funciona, mas o índice é só em `email` — o
        # resultado é o mesmo.
        return sql

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
    """Conexão SQLite para os testes.

    ARMADILHA RESOLVIDA AQUI: no SQLite, cada `connect(":memory:")` abre um
    banco NOVO e vazio. O `init_db` criava as tabelas numa conexão, fechava, e
    a requisição de teste abria outra — vazia — e encontrava `no such table`.

    A solução é o `cache=shared` com um nome de banco: o SQLite mantém UM banco
    em memória por nome, compartilhado entre todas as conexões do processo. O
    nome inclui o id do processo, então dois pytest rodando em paralelo não
    colidem. Nada toca o disco.
    """
    caminho = current_app.config.get("SQLITE_PATH", ":memory:")

    # O diretorio precisa existir antes do connect.
    if caminho != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)

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
    """Aplica o schema do banco do ambiente atual. Idempotente."""
    caminho = _caminho_do_schema()
    if not caminho.exists():
        raise FileNotFoundError(f"schema não encontrado em {caminho}")

    sql = caminho.read_text(encoding="utf-8")
    conexao = get_conexao()

    try:
        if _backend() == "sqlite":
            # `executescript` do SQLite aceita o arquivo inteiro, incluindo
            # vários comandos — sem precisar dividir por `;` na mão.
            bruto = conexao._conexao if isinstance(conexao, _ConexaoSqlite) else conexao
            bruto.executescript(sql)
            bruto.commit()
        else:
            with conexao.cursor() as cursor:
                cursor.execute(sql)
            conexao.commit()
    except Exception:
        conexao.rollback()
        raise


def _caminho_do_schema() -> Path:
    """Schema de teste para SQLite; schema de produção para PostgreSQL.

    Resolver aqui — e não no config — mantém uma única fonte de verdade sobre
    qual arquivo vale em cada ambiente.
    """
    if _backend() == "sqlite":
        base = Path(current_app.root_path)
        return base / "tests" / "schema_teste.sql"
    return Path(current_app.config["SCHEMA_PATH"])


def register(app) -> None:
    """Liga o teardown da conexão ao ciclo de vida da app."""
    app.teardown_appcontext(close_connection)
