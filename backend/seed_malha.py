"""Carrega a malha aérea (97 aeroportos) no banco.

Lê `aeroportos_voos_regulares_brasil.txt` e faz o upsert na tabela
`aeroportos`. Idempotente.

Use este script em vez do comando CLI quando quiser rodar fora do Flask:

    .venv\\Scripts\\python.exe seed_malha.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402
from dados.malha_seed import ARQUIVO_PADRAO, contar, semear  # noqa: E402
from db import transacao  # noqa: E402


def main(argumentos: list[str]) -> int:
    caminho = Path(argumentos[0]) if argumentos else Path(ARQUIVO_PADRAO)
    print(f"Arquivo: {caminho.resolve()}")

    app = create_app("development")
    with app.app_context():
        with transacao() as conexao:
            inseridos, atualizados = semear(conexao, caminho)
        with transacao() as conexao:
            total = contar(conexao)
            por_regiao = conexao.execute(
                "SELECT regiao, COUNT(*) AS n FROM aeroportos "
                "GROUP BY regiao ORDER BY regiao"
            ).fetchall()
            hubs = conexao.execute(
                "SELECT COUNT(*) AS n FROM aeroportos WHERE hub"
            ).fetchone()["n"]

    print(f"  {inseridos} inserido(s), {atualizados} atualizado(s)")
    print(f"  total na tabela: {total} aeroportos ({hubs} hubs)")
    print("  por regiao:")
    for l in por_regiao:
        print(f"    {l['regiao']:14} {l['n']:3}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
