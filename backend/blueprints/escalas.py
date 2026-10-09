"""Blueprint das escalas e do histórico de versões."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from db import get_connection, transaction
from models import ValidacaoError, validar_lista_escalas

bp = Blueprint("escalas", __name__, url_prefix="/api/escalas")

ESCALA_PADRAO = [
    {
        "id": 1,
        "voo": "TAM-3482",
        "tripulante": "Rafael Nunes",
        "cargo": "Comandante",
        "risco": "alto",
        "badgeKey": "highFatigueRisk",
        "desc": (
            "Atraso operacional crítico devido a restrições meteorológicas "
            "severas em Guarulhos."
        ),
        "rota": "GRU → VCP",
        "horario": "Partida prevista 23:40",
        "horas": "11h30",
        "limitRbac": "11h00 (pouso à noite)",
        "solucao": "Conexão direta GRU → CNF com reserva imediata",
        "bloqueado": True,
    }
]


@bp.get("")
def obter_escala_atual():
    """Última versão salva, ou a escala padrão se ainda não houver histórico."""
    conn = get_connection()
    row = conn.execute(
        "SELECT dados_json, versao_index, criado_em "
        "FROM historico_escalas ORDER BY versao_index DESC LIMIT 1"
    ).fetchone()

    if row is None:
        return jsonify({"versao": None, "dados": ESCALA_PADRAO})

    import json

    return jsonify(
        {
            "versao": row["versao_index"],
            "criado_em": row["criado_em"],
            "dados": json.loads(row["dados_json"]),
        }
    )


@bp.get("/versoes")
def listar_versoes():
    """Lista o histórico sem o payload — leve, para o seletor de versões."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT versao_index, criado_em FROM historico_escalas "
        "ORDER BY versao_index DESC LIMIT 100"
    ).fetchall()

    return jsonify(
        [
            {"versao": r["versao_index"], "criado_em": r["criado_em"]}
            for r in rows
        ]
    )


@bp.get("/versoes/<int:versao>")
def obter_versao(versao: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT dados_json, criado_em FROM historico_escalas WHERE versao_index = ?",
        (versao,),
    ).fetchone()

    if row is None:
        return jsonify({"erro": "versão não encontrada", "versao": versao}), 404

    import json

    return jsonify(
        {"versao": versao, "criado_em": row["criado_em"], "dados": json.loads(row["dados_json"])}
    )


@bp.post("/historico")
def salvar_historico():
    """Salva uma nova versão da escala.

    A numeração da versão é calculada dentro da transação, com MAX + 1, e o
    índice UNIQUE em `versao_index` fecha a porta para duplicata em requisições
    concorrentes — antes, um `SELECT COUNT(*)` fora da transação fazia duas
    requisições simultâneas gravarem o mesmo número.
    """
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({"erro": "body deve ser um objeto JSON"}), 400

    limite = current_app.config["MAX_PAYLOAD_BYTES"]
    if request.content_length and request.content_length > limite:
        return (
            jsonify({"erro": "payload excede o limite", "limite_bytes": limite}),
            413,
        )

    try:
        itens = validar_lista_escalas(corpo.get("dados"))
    except ValidacaoError as err:
        return jsonify({"erro": "dados inválidos", "campos": err.campos}), 400

    import json

    payload = json.dumps([item.to_dict() for item in itens], ensure_ascii=False)

    with transaction() as conn:
        proxima = conn.execute(
            "SELECT COALESCE(MAX(versao_index), -1) + 1 AS proxima FROM historico_escalas"
        ).fetchone()["proxima"]

        cursor = conn.execute(
            "INSERT INTO historico_escalas (versao_index, dados_json) VALUES (?, ?)",
            (proxima, payload),
        )
        novo_id = cursor.lastrowid

    return (
        jsonify(
            {
                "status": "sucesso",
                "id": novo_id,
                "versao": proxima,
                "total_itens": len(itens),
            }
        ),
        201,
    )
