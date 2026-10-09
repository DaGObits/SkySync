"""Sincroniza o banco do Neon com o esquema atual, na ordem correta.

Ordem: 1) criar tabelas que faltam  2) adicionar colunas que faltam
       3) criar os indices

Por que existe: o `init-db` usa `CREATE TABLE IF NOT EXISTS`, que cria tabela
nova mas NUNCA altera tabela que ja existe. Quando o esquema evoluiu (`cenarios`,
`aeroportos`, colunas novas em `execucoes_otimizacao`), o banco em nuvem ficou
na versao antiga e o erro so aparecia ao usar a funcionalidade nova.

A solucao definitiva e migracao versionada; este script e a ponte ate la.

Idempotente: rodar de novo so imprime "ja existe".

Uso:  .venv\\Scripts\\python.exe sincronizar.py
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402
from db import transacao  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Tabelas que podem faltar (mesma definicao do schema.sql)
# ---------------------------------------------------------------------------
TABELAS = {
    "aeroportos": """
        CREATE TABLE IF NOT EXISTS aeroportos (
            iata       TEXT PRIMARY KEY,
            cidade     TEXT NOT NULL,
            uf         TEXT NOT NULL DEFAULT '',
            regiao     TEXT NOT NULL DEFAULT '',
            latitude   DOUBLE PRECISION,
            longitude  DOUBLE PRECISION,
            hub        BOOLEAN NOT NULL DEFAULT FALSE,
            criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """,
    "cenarios": """
        CREATE TABLE IF NOT EXISTS cenarios (
            id             SERIAL PRIMARY KEY,
            nome           TEXT NOT NULL DEFAULT '',
            base           TEXT NOT NULL DEFAULT 'GRU',
            seed           INTEGER NOT NULL,
            n_tripulantes  INTEGER NOT NULL,
            n_voos         INTEGER NOT NULL,
            disrupcao      REAL NOT NULL DEFAULT 0,
            composicao     JSONB,
            dados_json     JSONB NOT NULL,
            criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """,
    "tripulantes": """
        CREATE TABLE IF NOT EXISTS tripulantes (
            id         TEXT PRIMARY KEY,
            nome       TEXT NOT NULL,
            sobrenome  TEXT NOT NULL DEFAULT '',
            cargo      TEXT NOT NULL
                       CHECK (cargo IN ('Comandante', 'Copiloto', 'Comissário')),
            base       TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'Disponível'
                       CHECK (status IN ('Disponível', 'Reserva', 'Indisponível')),
            criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """,
}

# ---------------------------------------------------------------------------
# 2. Colunas a acrescentar em tabelas que ja existem
# ---------------------------------------------------------------------------
COLUNAS = [
    ("execucoes_otimizacao", "cenario_id",
     "INTEGER REFERENCES cenarios (id) ON DELETE SET NULL"),
    ("execucoes_otimizacao", "total_voos", "INTEGER"),
    ("execucoes_otimizacao", "total_alocacoes", "INTEGER"),
    ("execucoes_otimizacao", "variaveis_criadas", "INTEGER"),
]

# ---------------------------------------------------------------------------
# 3. Indices
# ---------------------------------------------------------------------------
INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_aeroportos_regiao ON aeroportos (regiao)",
    "CREATE INDEX IF NOT EXISTS ix_aeroportos_hub ON aeroportos (hub) WHERE hub",
    "CREATE INDEX IF NOT EXISTS ix_cenarios_base ON cenarios (base)",
    "CREATE INDEX IF NOT EXISTS ix_cenarios_criado_em ON cenarios (criado_em DESC)",
    "CREATE INDEX IF NOT EXISTS ix_execucoes_cenario ON execucoes_otimizacao (cenario_id)",
    "CREATE INDEX IF NOT EXISTS ix_tripulantes_base ON tripulantes (base)",
    "CREATE INDEX IF NOT EXISTS ix_tripulantes_cargo ON tripulantes (cargo)",
    "CREATE INDEX IF NOT EXISTS ix_tripulantes_status ON tripulantes (status)",
    "CREATE INDEX IF NOT EXISTS ix_tripulantes_base_cargo ON tripulantes (base, cargo)",
]


def existe_tabela(conexao, nome: str) -> bool:
    return bool(
        conexao.execute(
            "SELECT to_regclass(%s) AS t", (f"public.{nome}",)
        ).fetchone()["t"]
    )


def main() -> None:
    app = create_app("development")
    with app.app_context():
        print("1. Tabelas")
        with transacao() as conexao:
            for nome, ddl in TABELAS.items():
                if existe_tabela(conexao, nome):
                    print(f"   {nome:14} ja existe")
                else:
                    conexao.execute(ddl)
                    print(f"   {nome:14} CRIADA")

        print("2. Colunas")
        with transacao() as conexao:
            for tabela, coluna, tipo in COLUNAS:
                if not existe_tabela(conexao, tabela):
                    print(f"   {tabela}.{coluna}: tabela ausente, pulando")
                    continue
                atual = {
                    l["column_name"]
                    for l in conexao.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = %s",
                        (tabela,),
                    ).fetchall()
                }
                if coluna in atual:
                    print(f"   {tabela}.{coluna}: ja existe")
                else:
                    conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
                    print(f"   {tabela}.{coluna}: ADICIONADA")

        print("3. Indices")
        with transacao() as conexao:
            for ddl in INDICES:
                conexao.execute(ddl)
            print(f"   {len(INDICES)} indices garantidos")

    print()
    print("Pronto. Proximo passo:")
    print("  .venv\\Scripts\\python.exe importar_tripulantes.py")


if __name__ == "__main__":
    main()
