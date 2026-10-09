"""Carga da malha aérea no banco, a partir do Python.

Existe como módulo — e não só como `malha_seed.sql` — para não depender do
cliente `psql` instalado na máquina. É usado pelo comando
`flask --app app seed-malha`.
"""
from __future__ import annotations

from dados.malha import MALHA


def semear(conexao) -> int:
    """Insere os aeroportos da malha. Idempotente (ON CONFLICT DO NOTHING).

    Devolve quantas linhas foram efetivamente inseridas.
    """
    inseridos = 0
    for a in MALHA:
        cursor = conexao.execute(
            """
            INSERT INTO aeroportos
                (iata, cidade, uf, regiao, latitude, longitude, hub)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (iata) DO NOTHING
            """,
            (a.iata, a.cidade, a.uf, a.regiao, a.lat, a.lon, a.hub),
        )
        inseridos += getattr(cursor, "rowcount", 0) or 0
    return inseridos


def contar(conexao) -> int:
    linha = conexao.execute("SELECT COUNT(*) AS total FROM aeroportos").fetchone()
    return linha["total"] if linha else 0
