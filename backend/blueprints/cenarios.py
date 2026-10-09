"""Blueprint de cenários operacionais.

Um cenário é o insumo do otimizador: um pool de tripulantes e uma lista de
voos, gerados com parâmetros reais da malha brasileira e uma seed que garante
reprodutibilidade.

    POST /api/cenarios          gera (e opcionalmente persiste) um cenário
    GET  /api/cenarios          lista os cenários salvos
    GET  /api/cenarios/<id>     recupera um cenário salvo
    GET  /api/malha             lista os aeroportos (os vértices do grafo)
"""
from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, request

from blueprints.auth import login_obrigatorio
from dados.gerador import gerar_cenario
from dados.malha import HUBS, MALHA
from db import transacao

bp = Blueprint("cenarios", __name__, url_prefix="/api")

MAX_TRIPULANTES = 2000
MAX_VOOS = 1000


@bp.get("/malha")
def listar_malha():
    """Aeroportos da malha — conteúdo informativo, aberto como o catálogo."""
    return jsonify(
        {
            "total": len(MALHA),
            "hubs": list(HUBS),
            "aeroportos": [
                {
                    "iata": a.iata,
                    "cidade": a.cidade,
                    "uf": a.uf,
                    "regiao": a.regiao,
                    "latitude": a.lat,
                    "longitude": a.lon,
                    "hub": a.hub,
                }
                for a in MALHA
            ],
        }
    )


@bp.post("/cenarios")
@login_obrigatorio
def criar_cenario():
    """Gera um cenário operacional.

    Corpo (todos opcionais; os defaults produzem um caso de porte médio):
        {
          "nome": "Carga alta - outubro",
          "base": "GRU",
          "tripulantes": 400,
          "voos": 150,
          "disrupcao": 0.15,
          "seed": 42,
          "salvar": true
        }
    """
    corpo = request.get_json(silent=True)
    if corpo is None:
        corpo = {}
    if not isinstance(corpo, dict):
        return jsonify({"erro": "corpo deve ser um objeto JSON"}), 400

    erros: dict[str, str] = {}

    def inteiro(chave: str, padrao: int, minimo: int, maximo: int) -> int:
        valor = corpo.get(chave, padrao)
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            erros[chave] = "deve ser um número inteiro"
            return padrao
        if valor < minimo or valor > maximo:
            erros[chave] = f"deve estar entre {minimo} e {maximo}"
            return padrao
        return valor

    n_tripulantes = inteiro("tripulantes", 400, 10, MAX_TRIPULANTES)
    n_voos = inteiro("voos", 150, 1, MAX_VOOS)
    seed = inteiro("seed", 42, 0, 2**31 - 1)

    try:
        disrupcao = float(corpo.get("disrupcao", 0.15))
    except (TypeError, ValueError):
        erros["disrupcao"] = "deve ser um número entre 0 e 1"
        disrupcao = 0.15
    else:
        if not 0 <= disrupcao <= 1:
            erros["disrupcao"] = "deve estar entre 0 e 1"

    base = str(corpo.get("base", "GRU")).strip().upper() or "GRU"

    if erros:
        return jsonify({"erro": "dados inválidos", "campos": erros}), 400

    try:
        cenario = gerar_cenario(
            tripulantes=n_tripulantes,
            voos=n_voos,
            disrupcao=disrupcao,
            base=base,
            seed=seed,
        )
    except ValueError as err:
        return jsonify({"erro": str(err)}), 400

    payload = cenario.to_dict()
    salvo = corpo.get("salvar", True)

    if salvo:
        try:
            with transacao() as conexao:
                linha = conexao.execute(
                    """
                    INSERT INTO cenarios
                        (nome, base, seed, n_tripulantes, n_voos, disrupcao,
                         composicao, dados_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        str(corpo.get("nome", "")).strip(),
                        base,
                        seed,
                        len(cenario.tripulantes),
                        len(cenario.voos),
                        disrupcao,
                        json.dumps(cenario.parametros.get("composicao", {})),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                ).fetchone()
            payload["id"] = linha["id"]
        except Exception:
            current_app.logger.exception("falha ao persistir cenário")
            # O cenário gerado ainda é útil: devolvemos sem id em vez de falhar.
            payload["aviso"] = "cenário gerado, mas não foi possível persistir"

    payload["resumo"] = cenario.resumo()
    return jsonify(payload), 201


@bp.get("/cenarios")
@login_obrigatorio
def listar_cenarios():
    """Lista os cenários salvos, sem o payload completo — leve de propósito."""
    with transacao() as conexao:
        linhas = conexao.execute(
            """
            SELECT id, nome, base, seed, n_tripulantes, n_voos, disrupcao, criado_em
            FROM cenarios ORDER BY id DESC LIMIT 50
            """
        ).fetchall()

    return jsonify(
        [
            {
                "id": l["id"],
                "nome": l["nome"],
                "base": l["base"],
                "seed": l["seed"],
                "n_tripulantes": l["n_tripulantes"],
                "n_voos": l["n_voos"],
                "disrupcao": l["disrupcao"],
                "criado_em": str(l["criado_em"]),
            }
            for l in linhas
        ]
    )


@bp.get("/cenarios/<int:cenario_id>")
@login_obrigatorio
def obter_cenario(cenario_id: int):
    """Recupera um cenário salvo, com os dados completos."""
    with transacao() as conexao:
        linha = conexao.execute(
            "SELECT dados_json FROM cenarios WHERE id = %s", (cenario_id,)
        ).fetchone()

    if linha is None:
        return jsonify({"erro": "cenário não encontrado", "id": cenario_id}), 404

    dados = linha["dados_json"]
    if not isinstance(dados, (dict, list)):
        dados = json.loads(dados)

    return jsonify({"id": cenario_id, **dados})
