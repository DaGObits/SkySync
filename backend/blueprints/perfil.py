"""Blueprint do perfil do usuário ativo.

Antes: `POST /api/perfil` fazia `DELETE FROM usuarios` sem WHERE, e o id do
usuário nunca era devolvido de forma confiável.
Agora: upsert por e-mail dentro de uma transação, com validação de entrada.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from db import get_connection, transaction
from models import Perfil, ValidacaoError

bp = Blueprint("perfil", __name__, url_prefix="/api/perfil")

PERFIL_PADRAO = {
    "nome": "Marina Costa",
    "email": "marina.costa@skysync.aero",
    "cargo": "Coordenadora Operacional",
    "base": "GRU — Guarulhos",
}


@bp.get("")
def obter_perfil():
    conn = get_connection()
    row = conn.execute("SELECT * FROM usuarios ORDER BY id DESC LIMIT 1").fetchone()

    if row is None:
        return jsonify(PERFIL_PADRAO)

    return jsonify(
        {
            "id": row["id"],
            "nome": row["nome"],
            "email": row["email"],
            "cargo": row["cargo"] or "",
            "base": row["base"] or "",
        }
    )


@bp.post("")
def salvar_perfil():
    try:
        perfil = Perfil.from_payload(request.get_json(silent=True))
    except ValidacaoError as err:
        return jsonify({"erro": "dados inválidos", "campos": err.campos}), 400

    # Upsert por e-mail: reenviar o mesmo perfil atualiza em vez de duplicar,
    # e não apaga mais os outros usuários da base.
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO usuarios (nome, email, cargo, base, atualizado_em)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET
                nome = excluded.nome,
                cargo = excluded.cargo,
                base = excluded.base,
                atualizado_em = CURRENT_TIMESTAMP
            """,
            (perfil.nome, perfil.email, perfil.cargo, perfil.base),
        )
        linha = conn.execute(
            "SELECT id FROM usuarios WHERE email = ?", (perfil.email,)
        ).fetchone()

    return jsonify({"status": "sucesso", "id": linha["id"], "perfil": perfil.to_dict()})
