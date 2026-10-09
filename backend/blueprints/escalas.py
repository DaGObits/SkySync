"""Blueprint das escalas e do histórico de versões.

A numeração da versão é calculada dentro da transação, com MAX + 1, e o índice
UNIQUE em `versao_index` fecha a porta para duplicata em requisições
concorrentes.
"""
from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, request, session

from blueprints.auth import login_obrigatorio
from db import transacao
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


def _carregar_json(valor):
    """No PostgreSQL a coluna é JSONB e o driver já devolve objeto; no SQLite
    é TEXT e precisa de json.loads."""
    if isinstance(valor, (dict, list)):
        return valor
    return json.loads(valor)


@bp.get("")
@login_obrigatorio
def obter_escala_atual():
    """Última versão salva, ou a escala padrão se ainda não houver histórico."""
    with transacao() as conexao:
        linha = conexao.execute(
            "SELECT dados_json, versao_index, criado_em "
            "FROM historico_escalas ORDER BY versao_index DESC LIMIT 1"
        ).fetchone()

    if linha is None:
        return jsonify({"versao": None, "dados": ESCALA_PADRAO})

    return jsonify(
        {
            "versao": linha["versao_index"],
            "criado_em": str(linha["criado_em"]),
            "dados": _carregar_json(linha["dados_json"]),
        }
    )


@bp.get("/versoes")
@login_obrigatorio
def listar_versoes():
    """Lista o histórico sem o payload — leve, para o seletor de versões."""
    with transacao() as conexao:
        linhas = conexao.execute(
            "SELECT versao_index, criado_em FROM historico_escalas "
            "ORDER BY versao_index DESC LIMIT 100"
        ).fetchall()

    return jsonify(
        [
            {"versao": l["versao_index"], "criado_em": str(l["criado_em"])}
            for l in linhas
        ]
    )


@bp.get("/versoes/<int:versao>")
@login_obrigatorio
def obter_versao(versao: int):
    with transacao() as conexao:
        linha = conexao.execute(
            "SELECT dados_json, criado_em FROM historico_escalas WHERE versao_index = %s",
            (versao,),
        ).fetchone()

    if linha is None:
        return jsonify({"erro": "versão não encontrada", "versao": versao}), 404

    return jsonify(
        {
            "versao": versao,
            "criado_em": str(linha["criado_em"]),
            "dados": _carregar_json(linha["dados_json"]),
        }
    )


@bp.post("/historico")
@login_obrigatorio
def salvar_historico():
    """Salva uma nova versão da escala."""
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({"erro": "corpo deve ser um objeto JSON"}), 400

    limite = current_app.config["MAX_PAYLOAD_BYTES"]
    if request.content_length and request.content_length > limite:
        return jsonify({"erro": "payload excede o limite", "limite_bytes": limite}), 413

    try:
        itens = validar_lista_escalas(corpo.get("dados"))
    except ValidacaoError as err:
        return jsonify({"erro": "dados inválidos", "campos": err.campos}), 400

    payload = json.dumps([item.to_dict() for item in itens], ensure_ascii=False)

    try:
        with transacao() as conexao:
            proxima = conexao.execute(
                "SELECT COALESCE(MAX(versao_index), -1) + 1 AS proxima FROM historico_escalas"
            ).fetchone()["proxima"]

            conexao.execute(
                """
                INSERT INTO historico_escalas (usuario_id, versao_index, dados_json)
                VALUES (%s, %s, %s)
                """,
                (session.get("usuario_id"), proxima, payload),
            )
    except Exception as err:
        # Violação do índice UNIQUE significa corrida perdida: outra requisição
        # gravou a mesma versão primeiro. Isso é 409, não 500.
        if "unique" in str(err).lower() or "duplicate" in str(err).lower():
            return jsonify({"erro": "versão já gravada, tente novamente"}), 409
        current_app.logger.exception("falha ao salvar histórico")
        return jsonify({"erro": "não foi possível salvar a versão"}), 500

    return jsonify({"status": "sucesso", "versao": proxima, "total_itens": len(itens)}), 201
