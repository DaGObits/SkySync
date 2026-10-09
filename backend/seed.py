"""Popula o banco (Neon) com dados de demonstracao para testar o site.

O que ele grava:
  1. os 36 aeroportos da malha (tabela aeroportos)
  2. uma conta de demonstracao (tabela usuarios)
  3. tres cenarios de tamanhos diferentes, com tripulantes nomeados
     (tabela cenarios) — reprodutiveis pela seed

Pode rodar quantas vezes quiser: nao duplica nada.

Uso:  .venv\\Scripts\\python.exe seed.py
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# O .env PRECISA ser carregado antes de importar config/db: o config.py le
# os.getenv no momento da importacao, entao qualquer coisa importada antes
# desta linha veria DATABASE_URL vazia.
load_dotenv(Path(__file__).resolve().parent / ".env")

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from dados.gerador import gerar_cenario  # noqa: E402
from dados.malha_seed import contar, semear  # noqa: E402
from db import transacao  # noqa: E402

from werkzeug.security import generate_password_hash

from app import create_app
from dados.gerador import gerar_cenario
from dados.malha_seed import contar, semear
from db import transacao

DEMO_EMAIL = "demo@skysync.aero"
DEMO_SENHA = "Demo1234"

CENARIOS = [
    # (nome, voos, seed)
    ("Demonstracao pequena - 10 voos", 10, 101),
    ("Operacao media - 25 voos", 25, 202),
    ("Carga alta - 50 voos", 50, 303),
]


def semear_usuario(conexao):
    existe = conexao.execute(
        "SELECT id FROM usuarios WHERE LOWER(email) = %s", (DEMO_EMAIL,)
    ).fetchone()
    if existe:
        print(f"  usuario {DEMO_EMAIL} ja existe (id {existe['id']})")
        return
    conexao.execute(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, base)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "Marina Costa",
            DEMO_EMAIL,
            generate_password_hash(DEMO_SENHA),
            "Coordenadora Operacional",
            "GRU",
        ),
    )
    print(f"  usuario criado: {DEMO_EMAIL} / {DEMO_SENHA}")


def semear_cenarios(conexao):
    for nome, voos, seed in CENARIOS:
        existe = conexao.execute(
            "SELECT id FROM cenarios WHERE nome = %s", (nome,)
        ).fetchone()
        if existe:
            print(f"  cenario '{nome}' ja existe (id {existe['id']})")
            continue

        cen = gerar_cenario(voos=voos, seed=seed, base="GRU")
        dados = cen.to_dict()
        dados["resumo"] = cen.resumo()

        conexao.execute(
            """
            INSERT INTO cenarios
                (nome, base, seed, n_tripulantes, n_voos, disrupcao,
                 composicao, dados_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                nome,
                "GRU",
                seed,
                len(cen.tripulantes),
                len(cen.voos),
                cen.parametros["disrupcao"],
                json.dumps(cen.parametros["composicao"], ensure_ascii=False),
                json.dumps(dados, ensure_ascii=False),
            ),
        )
        exemplos = ", ".join(t.nome for t in cen.tripulantes[:3])
        print(
            f"  cenario '{nome}': {len(cen.voos)} voos, "
            f"{len(cen.tripulantes)} tripulantes (ex.: {exemplos})"
        )


def main():
    app = create_app("development")
    with app.app_context():
        print("1. Aeroportos")
        with transacao() as conexao:
            inseridos = semear(conexao)
        with transacao() as conexao:
            print(f"  {inseridos} inserido(s), total na tabela: {contar(conexao)}")

        print("2. Conta de demonstracao")
        with transacao() as conexao:
            semear_usuario(conexao)

        print("3. Cenarios com tripulantes")
        with transacao() as conexao:
            semear_cenarios(conexao)

    print()
    print("Pronto. Entre no site com:")
    print(f"  e-mail: {DEMO_EMAIL}")
    print(f"  senha : {DEMO_SENHA}")


if __name__ == "__main__":
    main()
