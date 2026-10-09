"""Importa a base simulada de tripulantes para o banco (Neon).

Le o arquivo `skysync_tripulantes_simulados.txt` (formato de colunas separadas
por `|`) e popula a tabela `tripulantes`.

MAPEAMENTO DE CARGO: a base usa "Tripulante de Cabine", que e o termo correto
na aviacao. O motor CP-SAT trabalha com "Comissario" — o nome que ja esta nas
restricoes, nos testes e na composicao. A importacao faz a traducao para nao
ter duas grafias circulando pelo sistema.

Idempotente: rodar de novo atualiza os registros existentes em vez de duplicar.

Uso:  .venv\\Scripts\\python.exe importar_tripulantes.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# O .env precisa vir antes de importar config/db: o config.py le os.getenv no
# momento da importacao.
load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402
from db import transacao  # noqa: E402

ARQUIVO_PADRAO = "skysync_tripulantes_simulados.txt"

#: A base usa o termo da aviacao; o motor usa o nome curto. Traduzimos aqui,
#: num unico lugar, em vez de espalhar as duas grafias pelo codigo.
MAPA_CARGO = {
    "Tripulante de Cabine": "Comissário",
    "Comissario": "Comissário",
    "Comissário": "Comissário",
    "Comandante": "Comandante",
    "Copiloto": "Copiloto",
}

#: Linha no formato:  0001  | Iara  | Ramos  | Comandante  | GRU  | Disponível
LINHA = re.compile(
    r"^\s*(\d{4})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*"
    r"\|\s*([A-Z]{3})\s*\|\s*(.+?)\s*$"
)


def ler_arquivo(caminho: Path) -> list[dict]:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo nao encontrado: {caminho}\n"
            "Copie o arquivo da base para a pasta do backend e rode de novo."
        )

    registros: list[dict] = []
    ignoradas = 0
    cargos_desconhecidos: set[str] = set()

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        m = LINHA.match(linha)
        if not m:
            ignoradas += 1
            continue

        cargo_origem = m.group(4).strip()
        cargo = MAPA_CARGO.get(cargo_origem)
        if cargo is None:
            cargos_desconhecidos.add(cargo_origem)
            ignoradas += 1
            continue

        registros.append(
            {
                "id": m.group(1),
                "nome": m.group(2).strip(),
                "sobrenome": m.group(3).strip(),
                "cargo": cargo,
                "base": m.group(5).strip(),
                "status": m.group(6).strip(),
            }
        )

    if cargos_desconhecidos:
        print(f"  AVISO: cargos nao mapeados: {sorted(cargos_desconhecidos)}")
    print(f"  {len(registros)} registros lidos, {ignoradas} linhas ignoradas")
    return registros


def importar(conexao, registros: list[dict]) -> tuple[int, int]:
    """Insere ou atualiza. Devolve (inseridos, atualizados)."""
    inseridos = atualizados = 0

    for r in registros:
        existe = conexao.execute(
            "SELECT id FROM tripulantes WHERE id = %s", (r["id"],)
        ).fetchone()

        if existe:
            conexao.execute(
                """
                UPDATE tripulantes
                   SET nome = %s, sobrenome = %s, cargo = %s,
                       base = %s, status = %s
                 WHERE id = %s
                """,
                (r["nome"], r["sobrenome"], r["cargo"], r["base"], r["status"], r["id"]),
            )
            atualizados += 1
        else:
            conexao.execute(
                """
                INSERT INTO tripulantes (id, nome, sobrenome, cargo, base, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (r["id"], r["nome"], r["sobrenome"], r["cargo"], r["base"], r["status"]),
            )
            inseridos += 1

    return inseridos, atualizados


def main(argumentos: list[str]) -> int:
    caminho = Path(argumentos[0]) if argumentos else Path(ARQUIVO_PADRAO)

    print(f"Base: {caminho.resolve()}")
    registros = ler_arquivo(caminho)

    app = create_app("development")
    with app.app_context():
        with transacao() as conexao:
            inseridos, atualizados = importar(conexao, registros)

        with transacao() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) AS n FROM tripulantes"
            ).fetchone()["n"]
            por_cargo = conexao.execute(
                "SELECT cargo, COUNT(*) AS n FROM tripulantes GROUP BY cargo ORDER BY cargo"
            ).fetchall()
            por_status = conexao.execute(
                "SELECT status, COUNT(*) AS n FROM tripulantes GROUP BY status ORDER BY status"
            ).fetchall()
            bases = conexao.execute(
                "SELECT COUNT(DISTINCT base) AS n FROM tripulantes"
            ).fetchone()["n"]

    print(f"  {inseridos} inseridos, {atualizados} atualizados")
    print(f"  total na tabela: {total}")
    print(f"  bases distintas: {bases}")
    print("  por cargo:")
    for linha in por_cargo:
        print(f"    {linha['cargo']:14} {linha['n']:4}")
    print("  por status:")
    for linha in por_status:
        print(f"    {linha['status']:14} {linha['n']:4}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
