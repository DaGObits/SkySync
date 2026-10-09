"""Blueprint do perfil do usuário autenticado.

Mudança de contrato em relação à versão anterior: o perfil pertence a quem
está logado. A rota não recebe mais e-mail pela URL e exige sessão ativa.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, session

from blueprints.auth import _usuario_para_json, login_obrigatorio
from db import transacao

bp = Blueprint("perfil", __name__, url_prefix="/api/perfil")

_CAMPOS = "id, nome, email, cargo, base"


@bp.get("")
@login_obrigatorio
def obter_perfil():
    with transacao() as conexao:
        linha = conexao.execute(
            f"SELECT {_CAMPOS} FROM usuarios WHERE id = %s",
            (session["usuario_id"],),
        ).fetchone()

    if linha is None:
        return jsonify({"erro": "usuário não encontrado"}), 404

    return jsonify(_usuario_para_json(linha))


@bp.post("")
@login_obrigatorio
def salvar_perfil():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({"erro": "corpo deve ser um objeto JSON"}), 400

    # O front envia `role` no lugar de `cargo`; aceitamos os dois nomes para
    # não quebrar a integração existente.
    nome = (corpo.get("nome") or "").strip()
    cargo = (corpo.get("cargo") or corpo.get("role") or "").strip()
    base = (corpo.get("base") or "").strip()

    if len(nome) < 2:
        return (
            jsonify({"erro": "dados inválidos", "campos": {"nome": "campo obrigatório"}}),
            400,
        )

    try:
        with transacao() as conexao:
            conexao.execute(
                """
                UPDATE usuarios
                   SET nome = %s, cargo = %s, base = %s
                 WHERE id = %s
                """,
                (nome, cargo, base, session["usuario_id"]),
            )
            linha = conexao.execute(
                f"SELECT {_CAMPOS} FROM usuarios WHERE id = %s",
                (session["usuario_id"],),
            ).fetchone()
    except Exception:
        current_app.logger.exception("falha ao salvar perfil")
        return jsonify({"erro": "não foi possível salvar o perfil"}), 500

    return jsonify({"status": "sucesso", "perfil": _usuario_para_json(linha)})
