"""Blueprint do motor de otimização.

Diferença central em relação à versão antiga: o endpoint devolvia
`new_compliance: '100%'` hardcoded, sem calcular nada. Aqui ele roda o CP-SAT
de verdade e devolve o status real do solver.

A malha (bases por região) é carregada aqui — que tem `app_context` — e passada
ao solver por parâmetro. É o que mantém o motor livre de Flask.
"""
from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, request

from blueprints.auth import login_obrigatorio
from dados.malha import bases_por_regiao as malha_por_regiao
from db import transacao
from models import RequisicaoOtimizacao, ValidacaoError
from optimizer.restricoes import catalogo_restricoes
from optimizer.solver import OtimizacaoInviavel, otimizar

bp = Blueprint("otimizacao", __name__, url_prefix="/api/otimizacao")


@bp.get("/restricoes")
def listar_restricoes():
    """Catálogo de restrições ativas — documentação viva do modelo."""
    return jsonify(catalogo_restricoes())


@bp.post("")
@login_obrigatorio
def executar_otimizacao():
    """Recalcula a escala para uma base.

    Corpo:
        {
          "base": "GRU",
          "limite_horas": 11.0,
          "composicao": { "Comandante": 1, "Copiloto": 1, "Comissário": 3 },
          "tripulantes": [{...}, ...],
          "voos": [{...}, ...]
        }
    """
    try:
        requisicao = RequisicaoOtimizacao.from_payload(
            request.get_json(silent=True),
            limite_padrao=current_app.config["SOLVER_DEFAULT_HOUR_LIMIT"],
        )
    except ValidacaoError as err:
        return jsonify({"erro": "dados inválidos", "campos": err.campos}), 400

    try:
        regioes = malha_por_regiao()
    except Exception:
        current_app.logger.warning("malha indisponível — filtro por região desligado")
        regioes = {}

    try:
        solucao = otimizar(
            base=requisicao.base,
            tripulantes=requisicao.tripulantes,
            voos=requisicao.voos,
            limite_horas=requisicao.limite_horas,
            max_time_seconds=current_app.config["SOLVER_MAX_TIME_SECONDS"],
            composicao=requisicao.composicao,
            bases_por_regiao=regioes,
        )
    except OtimizacaoInviavel as err:
        current_app.logger.info(
            "otimização inviável para base=%s: %s", requisicao.base, err
        )
        _registrar_execucao(requisicao.base, "INFEASIBLE", None)
        return jsonify({
            "status": "INFEASIBLE",
            "base": requisicao.base,
            "mensagem": str(err),
            "diagnostico": err.diagnostico,
        }), 409
    except RuntimeError as err:
        current_app.logger.warning("solver sem convergência: %s", err)
        return jsonify({"status": "UNKNOWN", "mensagem": str(err)}), 500

    _registrar_execucao(requisicao.base, solucao.status, solucao)
    return jsonify(solucao.to_dict())


def _registrar_execucao(base: str, status: str, solucao) -> None:
    """Trilha de auditoria — permite à banca reconstruir cada execução."""
    try:
        with transacao() as conexao:
            conexao.execute(
                """
                INSERT INTO execucoes_otimizacao
                    (base, status_solver, wall_time_seconds, objetivo_valor,
                     conformidade, total_tripulantes, total_voos, total_alocacoes,
                     variaveis_criadas, total_bloqueados, detalhes_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    base,
                    status,
                    round(solucao.wall_time_seconds, 4) if solucao else None,
                    round(solucao.objetivo, 4) if solucao else None,
                    getattr(solucao, "conformidade", None),
                    getattr(solucao, "total_tripulantes", None),
                    getattr(solucao, "total_voos", None),
                    getattr(solucao, "total_alocacoes", None),
                    getattr(solucao, "variaveis_criadas", None),
                    getattr(solucao, "tripulantes_bloqueados", None),
                    json.dumps(solucao.to_dict(), ensure_ascii=False) if solucao else None,
                ),
            )
    except Exception:
        current_app.logger.exception("falha ao registrar execução da otimização")
