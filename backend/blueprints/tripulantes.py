"""Blueprint da tripulacao disponivel.

O painel carrega daqui em vez de manter uma lista fixa no HTML. Os filtros
existem porque o motor consulta por base e por cargo, e o front precisa da
mesma capacidade para nao trafegar 900 registros quando quer 50.

    GET /api/tripulantes                  lista (com filtros opcionais)
    GET /api/tripulantes/resumo           contagem por cargo, base e status
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from blueprints.auth import login_obrigatorio
from db import transacao

bp = Blueprint("tripulantes", __name__, url_prefix="/api/tripulantes")

CARGOS = ("Comandante", "Copiloto", "Comissário")


@bp.get("")
@login_obrigatorio
def listar():
    """Lista a tripulacao, com filtros opcionais.

    Query string:
        base=GRU            so de uma base
        cargo=Comandante    so de um cargo
        status=Reserva      so de um status
        limite=100          teto de registros (padrao 200, max 1000)
    """
    base = (request.args.get("base") or "").strip().upper()
    cargo = (request.args.get("cargo") or "").strip()
    status = (request.args.get("status") or "").strip()

    try:
        limite = int(request.args.get("limite", 200))
    except (TypeError, ValueError):
        return jsonify({"erro": "limite deve ser um numero"}), 400
    limite = max(1, min(limite, 1000))

    if cargo and cargo not in CARGOS:
        return jsonify({"erro": f"cargo inválido. Use: {', '.join(CARGOS)}"}), 400

    condicoes = []
    parametros: list = []
    if base:
        condicoes.append("base = %s")
        parametros.append(base)
    if cargo:
        condicoes.append("cargo = %s")
        parametros.append(cargo)
    if status:
        condicoes.append("status = %s")
        parametros.append(status)

    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    parametros.append(limite)

    with transacao() as conexao:
        linhas = conexao.execute(
            f"""
            SELECT id, nome, sobrenome, cargo, base, status
            FROM tripulantes {onde}
            ORDER BY cargo, base, id
            LIMIT %s
            """,
            tuple(parametros),
        ).fetchall()

        total = conexao.execute(
            f"SELECT COUNT(*) AS n FROM tripulantes {onde}",
            tuple(parametros[:-1]),
        ).fetchone()["n"]

    return jsonify(
        {
            "total": total,
            "retornados": len(linhas),
            "filtros": {"base": base or None, "cargo": cargo or None, "status": status or None},
            "tripulantes": [
                {
                    "id": l["id"],
                    "nome": l["nome"],
                    "sobrenome": l["sobrenome"],
                    "nome_completo": f"{l['nome']} {l['sobrenome']}".strip(),
                    "cargo": l["cargo"],
                    "base": l["base"],
                    "status": l["status"],
                }
                for l in linhas
            ],
        }
    )


@bp.get("/resumo")
@login_obrigatorio
def resumo():
    """Contagem por cargo, base e status — o painel usa para os filtros."""
    with transacao() as conexao:
        total = conexao.execute(
            "SELECT COUNT(*) AS n FROM tripulantes"
        ).fetchone()["n"]

        por_cargo = conexao.execute(
            "SELECT cargo, COUNT(*) AS n FROM tripulantes GROUP BY cargo ORDER BY cargo"
        ).fetchall()

        por_base = conexao.execute(
            "SELECT base, COUNT(*) AS n FROM tripulantes GROUP BY base ORDER BY base"
        ).fetchall()

        por_status = conexao.execute(
            "SELECT status, COUNT(*) AS n FROM tripulantes GROUP BY status ORDER BY status"
        ).fetchall()

    return jsonify(
        {
            "total": total,
            "por_cargo": {l["cargo"]: l["n"] for l in por_cargo},
            "por_base": {l["base"]: l["n"] for l in base_ordenada(por_base)},
            "por_status": {l["status"]: l["n"] for l in por_status},
        }
    )


def base_ordenada(linhas):
    return sorted(linhas, key=lambda l: l["base"])
