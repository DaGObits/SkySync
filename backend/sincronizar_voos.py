"""Sincroniza o banco com o esquema v5 (voos, jornadas, escalas).

Cria apenas as tres tabelas novas e seus indices. Nao altera nada existente.

Uso:  .venv\\Scripts\\python.exe sincronizar_voos.py
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402
from db import transacao  # noqa: E402

TABELAS = {
    "voos": """
        CREATE TABLE IF NOT EXISTS voos (
            id              TEXT PRIMARY KEY,
            codigo          TEXT NOT NULL,
            origem          TEXT NOT NULL DEFAULT '',
            destino         TEXT NOT NULL DEFAULT '',
            partida         TEXT NOT NULL DEFAULT '',
            chegada         TEXT NOT NULL DEFAULT '',
            duracao_horas   DOUBLE PRECISION NOT NULL,
            distancia_km    DOUBLE PRECISION,
            aeronave        TEXT NOT NULL DEFAULT '',
            pouso_noturno   BOOLEAN NOT NULL DEFAULT FALSE,
            status          TEXT NOT NULL DEFAULT 'Programado'
                            CHECK (status IN ('Programado', 'Em voo', 'Concluído', 'Cancelado')),
            criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """,
    "jornadas": """
        CREATE TABLE IF NOT EXISTS jornadas (
            id                 SERIAL PRIMARY KEY,
            tripulante_id      TEXT NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
            periodo            DATE NOT NULL,
            horas_voadas       DOUBLE PRECISION NOT NULL DEFAULT 0,
            horas_acumuladas   DOUBLE PRECISION NOT NULL DEFAULT 0,
            limite_horas       DOUBLE PRECISION NOT NULL DEFAULT 11.0,
            voos_no_periodo    INTEGER NOT NULL DEFAULT 0,
            ultimo_pouso       TEXT NOT NULL DEFAULT '',
            descanso_ok        BOOLEAN NOT NULL DEFAULT TRUE,
            aclimatado         BOOLEAN NOT NULL DEFAULT TRUE,
            observacao         TEXT NOT NULL DEFAULT '',
            criado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tripulante_id, periodo)
        )
    """,
    "escalas": """
        CREATE TABLE IF NOT EXISTS escalas (
            id                  SERIAL PRIMARY KEY,
            tripulante_id       TEXT NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
            voo_id              TEXT NOT NULL REFERENCES voos (id) ON DELETE CASCADE,
            data                DATE NOT NULL,
            cargo               TEXT NOT NULL DEFAULT '',
            origem              TEXT NOT NULL DEFAULT '',
            destino             TEXT NOT NULL DEFAULT '',
            duracao_horas       DOUBLE PRECISION NOT NULL DEFAULT 0,
            horas_antes         DOUBLE PRECISION NOT NULL DEFAULT 0,
            horas_depois        DOUBLE PRECISION NOT NULL DEFAULT 0,
            limite_aplicado     DOUBLE PRECISION NOT NULL DEFAULT 11.0,
            ocupacao_percentual DOUBLE PRECISION NOT NULL DEFAULT 0,
            conforme            BOOLEAN NOT NULL DEFAULT TRUE,
            motivo              TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'planejado'
                                CHECK (status IN ('planejado', 'confirmado', 'bloqueado', 'desfeito')),
            execucao_id         INTEGER REFERENCES execucoes_otimizacao (id) ON DELETE SET NULL,
            criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tripulante_id, voo_id, data)
        )
    """,
}

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_voos_origem ON voos (origem)",
    "CREATE INDEX IF NOT EXISTS ix_voos_destino ON voos (destino)",
    "CREATE INDEX IF NOT EXISTS ix_voos_partida ON voos (partida)",
    "CREATE INDEX IF NOT EXISTS ix_voos_codigo ON voos (codigo)",
    "CREATE INDEX IF NOT EXISTS ix_jornadas_tripulante ON jornadas (tripulante_id)",
    "CREATE INDEX IF NOT EXISTS ix_jornadas_periodo ON jornadas (periodo DESC)",
    "CREATE INDEX IF NOT EXISTS ix_escalas_data ON escalas (data DESC)",
    "CREATE INDEX IF NOT EXISTS ix_escalas_tripulante ON escalas (tripulante_id)",
    "CREATE INDEX IF NOT EXISTS ix_escalas_voo ON escalas (voo_id)",
    "CREATE INDEX IF NOT EXISTS ix_escalas_conforme ON escalas (conforme)",
    "CREATE INDEX IF NOT EXISTS ix_escalas_execucao ON escalas (execucao_id)",
]


def main() -> None:
    app = create_app("development")
    with app.app_context():
        print("1. Tabelas")
        with transacao() as conexao:
            for nome, ddl in TABELAS.items():
                existe = conexao.execute(
                    "SELECT to_regclass(%s) AS t", (f"public.{nome}",)
                ).fetchone()["t"]
                if existe:
                    print(f"   {nome:10} ja existe")
                else:
                    conexao.execute(ddl)
                    print(f"   {nome:10} CRIADA")

        print("2. Indices")
        with transacao() as conexao:
            for ddl in INDICES:
                conexao.execute(ddl)
            print(f"   {len(INDICES)} indices garantidos")

        print("3. Versao do schema")
        with transacao() as conexao:
            conexao.execute(
                "INSERT INTO schema_version (versao) VALUES (5) "
                "ON CONFLICT (versao) DO NOTHING"
            )
            versoes = conexao.execute(
                "SELECT versao FROM schema_version ORDER BY versao"
            ).fetchall()
            print(f"   versoes registradas: {[v['versao'] for v in versoes]}")

    print()
    print("Proximo passo:")
    print("  .venv\\Scripts\\python.exe importar_voos.py")


if __name__ == "__main__":
    main()
