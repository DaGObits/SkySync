"""Importa a malha de voos e gera as jornadas iniciais.

Tres etapas, idempotentes:
  1. gera a malha realista a partir dos 36 aeroportos e grava em `voos`
  2. cria uma jornada inicial (zerada) para cada tripulante em `jornadas`
  3. mostra o resumo do que ficou no banco

AS JORNADAS COMECAM A COMPUTAR A PARTIR DAQUI: cada tripulante entra com uma
linha zerada no periodo de hoje, e os campos vao sendo atualizados conforme as
escalas sao cumpridas (ver `registrar_jornada` em escalas.py).

Uso:
    .venv\\Scripts\\python.exe importar_voos.py
    .venv\\Scripts\\python.exe importar_voos.py 200      # outra quantidade
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402
from dados.malha_voos import gerar_voos  # noqa: E402
from db import transacao  # noqa: E402

QUANTIDADE_PADRAO = 140
BASE = "GRU"
SEED = 20261009


def importar_voos(conexao, voos) -> tuple[int, int]:
    inseridos = atualizados = 0
    for v in voos:
        existe = conexao.execute(
            "SELECT id FROM voos WHERE id = %s", (v.id,)
        ).fetchone()
        if existe:
            conexao.execute(
                """
                UPDATE voos
                   SET codigo = %s, origem = %s, destino = %s,
                       partida = %s, chegada = %s, duracao_horas = %s,
                       distancia_km = %s, aeronave = %s, pouso_noturno = %s,
                       atualizado_em = NOW()
                 WHERE id = %s
                """,
                (v.codigo, v.origem, v.destino, v.partida, v.chegada,
                 v.duracao_horas, v.distancia_km, v.aeronave,
                 v.pouso_noturno, v.id),
            )
            atualizados += 1
        else:
            conexao.execute(
                """
                INSERT INTO voos
                    (id, codigo, origem, destino, partida, chegada,
                     duracao_horas, distancia_km, aeronave, pouso_noturno)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (v.id, v.codigo, v.origem, v.destino, v.partida, v.chegada,
                 v.duracao_horas, v.distancia_km, v.aeronave, v.pouso_noturno),
            )
            inseridos += 1
    return inseridos, atualizados


def criar_jornadas(conexao, periodo: date) -> int:
    """Cria a jornada zerada de cada tripulante que ainda nao tem uma.

    Limite inicial por cargo: comandante e copiloto comecam com 11h (o teto
    padrao da RBAC para jornada diurna), comissario com 11h30. Ajuste conforme
    a politica da companhia — o valor fica gravado por tripulante, entao cada
    um pode ter o seu.
    """
    criadas = 0
    tripulantes = conexao.execute(
        "SELECT id, cargo FROM tripulantes"
    ).fetchall()

    for t in tripulantes:
        limite = 11.5 if t["cargo"] == "Comissário" else 11.0
        cursor = conexao.execute(
            """
            INSERT INTO jornadas
                (tripulante_id, periodo, horas_voadas, horas_acumuladas,
                 limite_horas, voos_no_periodo)
            VALUES (%s, %s, 0, 0, %s, 0)
            ON CONFLICT (tripulante_id, periodo) DO NOTHING
            """,
            (t["id"], periodo, limite),
        )
        criadas += getattr(cursor, "rowcount", 0) or 0

    return criadas


def main(argumentos: list[str]) -> int:
    quantidade = int(argumentos[0]) if argumentos else QUANTIDADE_PADRAO
    periodo = date.today()

    print(f"Malha: {quantidade} voos · base {BASE} · seed {SEED}")
    voos = gerar_voos(quantidade=quantidade, base=BASE, seed=SEED)

    app = create_app("development")
    with app.app_context():
        print("1. Voos")
        with transacao() as conexao:
            inseridos, atualizados = importar_voos(conexao, voos)
        print(f"   {inseridos} inseridos, {atualizados} atualizados")

        print(f"2. Jornadas (periodo {periodo})")
        with transacao() as conexao:
            criadas = criar_jornadas(conexao, periodo)
        print(f"   {criadas} jornada(s) criada(s)")

        print("3. Resumo do banco")
        with transacao() as conexao:
            total_voos = conexao.execute("SELECT COUNT(*) AS n FROM voos").fetchone()["n"]
            total_trip = conexao.execute("SELECT COUNT(*) AS n FROM tripulantes").fetchone()["n"]
            total_jorn = conexao.execute("SELECT COUNT(*) AS n FROM jornadas").fetchone()["n"]

            noturnos = conexao.execute(
                "SELECT COUNT(*) AS n FROM voos WHERE pouso_noturno"
            ).fetchone()["n"]

            por_aeronave = conexao.execute(
                "SELECT aeronave, COUNT(*) AS n FROM voos GROUP BY aeronave ORDER BY n DESC"
            ).fetchall()

            top_origens = conexao.execute(
                "SELECT origem, COUNT(*) AS n FROM voos "
                "GROUP BY origem ORDER BY n DESC LIMIT 5"
            ).fetchall()

        print(f"   voos: {total_voos} ({noturnos} com pouso noturno)")
        print(f"   tripulantes: {total_trip}")
        print(f"   jornadas: {total_jorn}")
        print("   por aeronave:")
        for l in por_aeronave:
            print(f"     {l['aeronave']:8} {l['n']:4}")
        print("   maiores origens:")
        for l in top_origens:
            print(f"     {l['origem']:5} {l['n']:4}")

    print()
    print("Pronto. As jornadas comecam a computar a partir de agora:")
    print("cada alocacao gravada em `escalas` atualiza o acumulado do tripulante.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
