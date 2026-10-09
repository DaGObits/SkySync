"""Adiciona as colunas novas em execucoes_otimizacao (idempotente)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app
from db import transacao

COLUNAS = [
    ("cenario_id", "INTEGER REFERENCES cenarios (id) ON DELETE SET NULL"),
    ("total_voos", "INTEGER"),
    ("total_alocacoes", "INTEGER"),
    ("variaveis_criadas", "INTEGER"),
]

app = create_app("development")
with app.app_context():
    with transacao() as conexao:
        existentes = {
            l["column_name"]
            for l in conexao.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'execucoes_otimizacao'"
            ).fetchall()
        }
        print("colunas atuais:", sorted(existentes))
        for nome, tipo in COLUNAS:
            if nome in existentes:
                print(f"  {nome}: ja existe")
                continue
            conexao.execute(
                f"ALTER TABLE execucoes_otimizacao ADD COLUMN {nome} {tipo}"
            )
            print(f"  {nome}: ADICIONADA")
