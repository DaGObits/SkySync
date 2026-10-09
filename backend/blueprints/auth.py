"""Blueprint de autenticação.

O que existe aqui e por quê:

* Senha nunca é guardada em texto. `werkzeug.security` gera hash com salt e
  usa PBKDF2 — vem junto com o Flask, sem dependência extra.
* A comparação usa `check_password_hash`, que é resistente a timing attack.
* A sessão é um cookie assinado pelo Flask (`SECRET_KEY`), marcado HttpOnly.
  O cliente não precisa guardar token no localStorage.
* Mensagem de erro genérica no login: "e-mail ou senha inválidos" tanto para
  conta inexistente quanto para senha errada. Dizer qual dos dois falhou
  entrega ao atacante a informação de quais e-mails existem.
"""
from __future__ import annotations

import re
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from db import transacao
from models import ValidacaoError

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Mínimo 8 caracteres, uma maiúscula e um número — o mesmo requisito que o
# login.html já valida no cliente. Validar dos dois lados é correto: o cliente
# pela experiência, o servidor porque é o único em que se pode confiar.
_RE_SENHA = re.compile(r"^(?=.*[A-Z])(?=.*\d).{8,}$")
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def login_obrigatorio(funcao):
    """Decorator para rotas que exigem sessão ativa."""

    @wraps(funcao)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id"):
            return jsonify({"erro": "não autenticado", "codigo": "NAO_AUTENTICADO"}), 401
        return funcao(*args, **kwargs)

    return wrapper


def _validar_registro(corpo: dict) -> dict[str, str]:
    erros: dict[str, str] = {}

    nome = (corpo.get("nome") or "").strip()
    email = (corpo.get("email") or "").strip().lower()
    senha = corpo.get("senha") or ""

    if len(nome) < 2:
        erros["nome"] = "informe o nome completo"
    if not _RE_EMAIL.match(email):
        erros["email"] = "e-mail inválido"
    if not _RE_SENHA.match(senha):
        erros["senha"] = "mínimo 8 caracteres, com uma maiúscula e um número"

    return erros


def _usuario_para_json(linha: dict) -> dict:
    """Formato que o login.html já espera em `dados.usuario`."""
    return {
        "id": linha["id"],
        "nome": linha["nome"],
        "email": linha["email"],
        "cargo": linha["cargo"] or "",
        "base": linha["base"] or "",
    }


@bp.post("/registrar")
def registrar():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({"erro": "corpo deve ser um objeto JSON"}), 400

    erros = _validar_registro(corpo)
    if erros:
        return jsonify({"erro": "dados inválidos", "campos": erros}), 400

    nome = corpo["nome"].strip()
    email = corpo["email"].strip().lower()
    senha_hash = generate_password_hash(corpo["senha"])

    try:
        with transacao() as conexao:
            existente = conexao.execute(
                "SELECT id FROM usuarios WHERE LOWER(email) = %s", (email,)
            ).fetchone()

            if existente:
                return jsonify({"erro": "e-mail já cadastrado"}), 409

            conexao.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, cargo, base)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (nome, email, senha_hash, corpo.get("cargo", ""), corpo.get("base", "")),
            )
    except Exception:
        current_app.logger.exception("falha ao registrar usuário")
        return jsonify({"erro": "não foi possível criar a conta"}), 500

    return jsonify({"mensagem": "Conta criada com sucesso!"}), 201


@bp.post("/login")
def login():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({"erro": "corpo deve ser um objeto JSON"}), 400

    email = (corpo.get("email") or "").strip().lower()
    senha = corpo.get("senha") or ""

    if not email or not senha:
        return jsonify({"erro": "informe e-mail e senha"}), 400

    try:
        with transacao() as conexao:
            linha = conexao.execute(
                """
                SELECT id, nome, email, cargo, base, senha_hash, ativo
                FROM usuarios WHERE LOWER(email) = %s
                """,
                (email,),
            ).fetchone()
    except Exception:
        current_app.logger.exception("falha ao consultar usuário no login")
        return jsonify({"erro": "não foi possível concluir o login"}), 500

    # Mesma mensagem para conta inexistente e senha errada, de propósito.
    if linha is None or not linha["senha_hash"]:
        return jsonify({"erro": "e-mail ou senha inválidos"}), 401

    if not check_password_hash(linha["senha_hash"], senha):
        return jsonify({"erro": "e-mail ou senha inválidos"}), 401

    if not linha["ativo"]:
        return jsonify({"erro": "conta desativada"}), 403

    session.clear()
    session["usuario_id"] = linha["id"]
    session["email"] = linha["email"]
    session.permanent = True

    return jsonify({"usuario": _usuario_para_json(linha)})


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"status": "sessão encerrada"})


@bp.get("/sessao")
def sessao_atual():
    """Quem está logado — útil para o front validar antes de renderizar."""
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return jsonify({"autenticado": False}), 200

    try:
        with transacao() as conexao:
            linha = conexao.execute(
                "SELECT id, nome, email, cargo, base FROM usuarios WHERE id = %s",
                (usuario_id,),
            ).fetchone()
    except Exception:
        current_app.logger.exception("falha ao consultar sessão")
        return jsonify({"erro": "não foi possível ler a sessão"}), 500

    if linha is None:
        session.clear()
        return jsonify({"autenticado": False}), 200

    return jsonify({"autenticado": True, "usuario": _usuario_para_json(linha)})
