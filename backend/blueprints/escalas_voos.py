"""Blueprint de voos, jornadas e escalas.

Fecha o ciclo de otimizacao:

    voos       -> a malha que precisa de tripulacao
    jornadas   -> o que cada tripulante ja cumpriu (insumo das restricoes)
    escalas    -> o resultado da alocacao, com a analise de conformidade

    GET  /api/voos                  a malha, com filtros
    GET  /api/jornadas              o acumulado por tripulante
    GET  /api/escalas               as alocacoes gravadas
    POST /api/escalas/otimizar      roda o CP-SAT sobre voos+jornadas e GRAVA

Antes deste modulo, voos e jornadas existiam so em memoria durante a chamada da
API — nada persistia, e nao havia como auditar uma decisao do motor depois.
"""
from __future__ import annotations

import json
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from blueprints.auth import login_obrigatorio
from db import transacao
from optimizer.restricoes import COMPOSICAO_PADRAO
from optimizer.solver import OtimizacaoInviavel, otimizar

bp = Blueprint("escalas_voos", __name__, url_prefix="/api")


def _formatar_horas(horas: float | None) -> str:
    total_min = int(round((horas or 0) * 60))
    return f"{total_min // 60:02d}h{total_min % 60:02d}"


def _limite_query(padrao: int, teto: int) -> int | None:
    """Le e valida o parametro `limite`. Devolve None quando invalido."""
    try:
        return max(1, min(int(request.args.get("limite", padrao)), teto))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Voos
# ---------------------------------------------------------------------------
@bp.get("/voos")
@login_obrigatorio
def listar_voos():
    """A malha de voos. Query string: origem, destino, noturno, limite."""
    origem = (request.args.get("origem") or "").strip().upper()
    destino = (request.args.get("destino") or "").strip().upper()
    noturno = request.args.get("noturno")

    limite = _limite_query(300, 1000)
    if limite is None:
        return jsonify({"erro": "limite deve ser um número"}), 400

    condicoes, parametros = [], []
    if origem:
        condicoes.append("origem = %s")
        parametros.append(origem)
    if destino:
        condicoes.append("destino = %s")
        parametros.append(destino)
    if noturno in ("1", "true"):
        condicoes.append("pouso_noturno = TRUE")

    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""

    with transacao() as conexao:
        linhas = conexao.execute(
            f"""
            SELECT id, codigo, origem, destino, partida, chegada,
                   duracao_horas, distancia_km, aeronave, pouso_noturno, status
            FROM voos {onde}
            ORDER BY partida, codigo
            LIMIT %s
            """,
            tuple(parametros + [limite]),
        ).fetchall()

        total = conexao.execute(
            f"SELECT COUNT(*) AS n FROM voos {onde}", tuple(parametros)
        ).fetchone()["n"]

    return jsonify({
        "total": total,
        "retornados": len(linhas),
        "voos": [
            {
                "id": l["id"],
                "codigo": l["codigo"],
                "origem": l["origem"],
                "destino": l["destino"],
                "rota": f"{l['origem']} → {l['destino']}",
                "partida": l["partida"],
                "chegada": l["chegada"],
                "duracao_horas": round(l["duracao_horas"], 2),
                "duracao": _formatar_horas(l["duracao_horas"]),
                "distancia_km": l["distancia_km"],
                "aeronave": l["aeronave"],
                "pouso_noturno": bool(l["pouso_noturno"]),
                "status": l["status"],
            }
            for l in linhas
        ],
    })


# ---------------------------------------------------------------------------
# Jornadas
# ---------------------------------------------------------------------------
@bp.get("/jornadas")
@login_obrigatorio
def listar_jornadas():
    """O acumulado de cada tripulante. Filtros: base, cargo, disponiveis."""
    base = (request.args.get("base") or "").strip().upper()
    cargo = (request.args.get("cargo") or "").strip()
    so_disponiveis = request.args.get("disponiveis") in ("1", "true")

    limite = _limite_query(300, 1000)
    if limite is None:
        return jsonify({"erro": "limite deve ser um número"}), 400

    condicoes, parametros = [], []
    if base:
        condicoes.append("t.base = %s")
        parametros.append(base)
    if cargo:
        condicoes.append("t.cargo = %s")
        parametros.append(cargo)
    if so_disponiveis:
        condicoes.append("j.descanso_ok = TRUE")
        condicoes.append("j.aclimatado = TRUE")
        condicoes.append("j.horas_acumuladas < j.limite_horas")

    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""

    with transacao() as conexao:
        linhas = conexao.execute(
            f"""
            SELECT j.tripulante_id, t.nome, t.sobrenome, t.cargo, t.base,
                   j.periodo, j.horas_voadas, j.horas_acumuladas, j.limite_horas,
                   j.voos_no_periodo, j.descanso_ok, j.aclimatado
            FROM jornadas j
            JOIN tripulantes t ON t.id = j.tripulante_id
            {onde}
            ORDER BY t.cargo, t.base, j.tripulante_id
            LIMIT %s
            """,
            tuple(parametros + [limite]),
        ).fetchall()

    return jsonify({
        "retornados": len(linhas),
        "jornadas": [
            {
                "tripulante_id": l["tripulante_id"],
                "nome_completo": f"{l['nome']} {l['sobrenome']}".strip(),
                "cargo": l["cargo"],
                "base": l["base"],
                "periodo": str(l["periodo"]),
                "horas_voadas": round(l["horas_voadas"], 2),
                "horas_acumuladas": round(l["horas_acumuladas"], 2),
                "limite_horas": l["limite_horas"],
                "voos_no_periodo": l["voos_no_periodo"],
                "ocupacao_percentual": round(
                    (l["horas_acumuladas"] / l["limite_horas"] * 100)
                    if l["limite_horas"] else 0.0,
                    1,
                ),
                "descanso_ok": bool(l["descanso_ok"]),
                "aclimatado": bool(l["aclimatado"]),
            }
            for l in linhas
        ],
    })


# ---------------------------------------------------------------------------
# Escalas gravadas
# ---------------------------------------------------------------------------
@bp.get("/escalas")
@login_obrigatorio
def listar_escalas():
    """As alocacoes gravadas. Query string: data, conforme, limite."""
    dia = (request.args.get("data") or "").strip() or str(date.today())
    conforme = request.args.get("conforme")

    limite = _limite_query(200, 1000)
    if limite is None:
        return jsonify({"erro": "limite deve ser um número"}), 400

    condicoes, parametros = ["e.data = %s"], [dia]
    if conforme in ("0", "false"):
        condicoes.append("e.conforme = FALSE")

    with transacao() as conexao:
        linhas = conexao.execute(
            f"""
            SELECT e.id, e.tripulante_id, t.nome, t.sobrenome, e.cargo,
                   e.voo_id, v.codigo AS voo, e.origem, e.destino,
                   e.duracao_horas, e.horas_antes, e.horas_depois,
                   e.limite_aplicado, e.ocupacao_percentual, e.conforme,
                   e.motivo, e.status, e.execucao_id
            FROM escalas e
            JOIN tripulantes t ON t.id = e.tripulante_id
            JOIN voos v ON v.id = e.voo_id
            WHERE {' AND '.join(condicoes)}
            ORDER BY v.partida, e.cargo
            LIMIT %s
            """,
            tuple(parametros + [limite]),
        ).fetchall()

    return jsonify({
        "data": dia,
        "total": len(linhas),
        "conformes": sum(1 for l in linhas if l["conforme"]),
        "escalas": [
            {
                "id": l["id"],
                "tripulante_id": l["tripulante_id"],
                "tripulante": f"{l['nome']} {l['sobrenome']}".strip(),
                "cargo": l["cargo"],
                "voo_id": l["voo_id"],
                "voo": l["voo"],
                "rota": f"{l['origem']} → {l['destino']}",
                "horas": _formatar_horas(l["duracao_horas"]),
                "horas_antes": round(l["horas_antes"], 2),
                "horas_depois": round(l["horas_depois"], 2),
                "limite_aplicado": l["limite_aplicado"],
                "ocupacao_percentual": round(l["ocupacao_percentual"], 1),
                "conforme": bool(l["conforme"]),
                "motivo": l["motivo"],
                "status": l["status"],
            }
            for l in linhas
        ],
    })


# ---------------------------------------------------------------------------
# Otimizacao sobre a malha real — roda e GRAVA
# ---------------------------------------------------------------------------
@bp.post("/escalas/otimizar")
@login_obrigatorio
def otimizar_e_gravar():
    """Roda CP-SAT com jornadas da data ou um cenário fictício em memória.

    Este e o endpoint que fecha o ciclo: antes dele, a otimizacao recebia tudo
    no corpo da requisicao e nada persistia. Aqui a entrada vem das tabelas
    `voos` e `jornadas`, e a saida vai para `escalas`.

    Corpo (opcional):
        {"data": "...", "limite_voos": 30, "base": "GRU", "gravar": false,
         "simulacao_jornadas": {"seed": 42, "perfil": "leve"}}

    Sem gravar=true, não altera jornadas nem escalas. Jornadas fictícias não
    podem ser publicadas; servem apenas para experimentar o solver.
    """
    from models import Tripulante, Voo

    corpo = request.get_json(silent=True) or {}
    if not isinstance(corpo, dict):
        return jsonify({"erro": "corpo deve ser um objeto JSON"}), 400

    from blueprints.jornadas_simulacao import validar_data, montar_cenario
    try:
        dia = validar_data(corpo.get('data'))
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400
    gravar = corpo.get('gravar', False)
    if not isinstance(gravar, bool):
        return jsonify({'erro': 'gravar deve ser true ou false'}), 400
    simulacao = corpo.get('simulacao_jornadas')
    if simulacao is not None and gravar:
        return jsonify({'erro': 'Jornadas simuladas não podem publicar uma escala. Use gravar=false.'}), 400
    try:
        cenario = montar_cenario(simulacao, dia) if simulacao is not None else None
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400
    base = str(corpo.get("base") or "GRU").strip().upper()
    so_disponiveis = bool(corpo.get("so_disponiveis", True))

    try:
        limite_voos = max(1, min(int(corpo.get("limite_voos", 30)), 200))
    except (TypeError, ValueError):
        return jsonify({"erro": "limite_voos deve ser um número"}), 400

    with transacao() as conexao:
        linhas_voos = conexao.execute(
            """
            SELECT id, codigo, origem, destino, duracao_horas, pouso_noturno
            FROM voos WHERE status = 'Programado'
            ORDER BY partida LIMIT %s
            """,
            (limite_voos,),
        ).fetchall()

        if not linhas_voos:
            return jsonify({
                "erro": "nenhum voo cadastrado",
                "dica": "rode importar_voos.py",
            }), 400

        condicao_disp = (
            " AND j.descanso_ok = TRUE"
            " AND j.horas_acumuladas < j.limite_horas"
            if so_disponiveis else ""
        )
        linhas_jornadas = conexao.execute(
            f"""
            SELECT j.tripulante_id, t.nome, t.cargo, t.base,
                   j.horas_acumuladas, j.limite_horas, j.descanso_ok, j.aclimatado
            FROM jornadas j
            JOIN tripulantes t ON t.id = j.tripulante_id
            WHERE j.periodo = %s AND t.status IN ('Disponível', 'Reserva'){condicao_disp}
            """, (dia,)
        ).fetchall() if cenario is None else []

    voos = [
        Voo(
            id=l["id"], codigo=l["codigo"], origem=l["origem"], destino=l["destino"],
            duracao_horas=l["duracao_horas"], pouso_noturno=bool(l["pouso_noturno"]),
            prioridade=1,
        )
        for l in linhas_voos
    ]

    tripulantes = [Tripulante(**j) for j in cenario['jornadas']] if cenario is not None else [
        Tripulante(
            id=l["tripulante_id"], nome=l["nome"], cargo=l["cargo"], base=l["base"],
            horas_acumuladas=l["horas_acumuladas"], limite_horas=l["limite_horas"],
            descanso_ok=bool(l["descanso_ok"]), aclimatado=bool(l["aclimatado"]),
        )
        for l in linhas_jornadas
    ]

    if not tripulantes:
        return jsonify({'erro': 'Nenhuma jornada disponível para a data escolhida.',
                        'dica': 'Gere um cenário de jornadas simuladas para testar ou cadastre jornadas dessa data.'}), 400

    # A malha é carregada AQUI (temos app_context) e passada ao solver, que
    # por regra não importa Flask.
    from dados.malha import bases_por_regiao as malha_por_regiao

    try:
        regioes = malha_por_regiao()
    except Exception:
        current_app.logger.warning("malha indisponível — filtro por região desligado")
        regioes = {}

    try:
        solucao = otimizar(
            base=base,
            tripulantes=tripulantes,
            voos=voos,
            limite_horas=current_app.config["SOLVER_DEFAULT_HOUR_LIMIT"],
            max_time_seconds=current_app.config["SOLVER_MAX_TIME_SECONDS"],
            composicao=COMPOSICAO_PADRAO,
            bases_por_regiao=regioes,
        )
    except OtimizacaoInviavel as err:
        if cenario is None:
            _registrar_execucao(base, "INFEASIBLE", None, len(tripulantes), len(voos))
        return jsonify({
            "status": "INFEASIBLE",
            "base": base,
            "mensagem": str(err),
            "diagnostico": err.diagnostico,
        }), 409
    except RuntimeError as err:
        return jsonify({"status": "UNKNOWN", "mensagem": str(err)}), 500

    execucao_id = None
    gravadas, ignoradas = 0, 0
    if gravar:
        execucao_id = _registrar_execucao(base, solucao.status, solucao, len(tripulantes), len(voos))
        try:
            gravadas, ignoradas = _gravar_escalas(solucao, dia, execucao_id)
        except RuntimeError as exc:
            return jsonify({'status': 'CONFLITO', 'mensagem': str(exc)}), 409

    resposta = solucao.to_dict()
    resposta["data"] = dia
    resposta['gravar'] = gravar
    resposta['origem_jornadas'] = 'simulacao' if cenario is not None else 'banco'
    if cenario is not None:
        resposta['simulacao_jornadas'] = {'parametros': cenario['parametros'], 'resumo': cenario['resumo']}
    resposta["escalas_gravadas"] = gravadas
    resposta["escalas_ignoradas"] = ignoradas
    resposta["execucao_id"] = execucao_id
    return jsonify(resposta)


def _registrar_execucao(base, status, solucao, n_trip, n_voos):
    """Grava a execucao na trilha de auditoria e devolve o id."""
    try:
        with transacao() as conexao:
            linha = conexao.execute(
                """
                INSERT INTO execucoes_otimizacao
                    (base, status_solver, wall_time_seconds, objetivo_valor,
                     conformidade, total_tripulantes, total_voos, total_alocacoes,
                     variaveis_criadas, total_bloqueados, detalhes_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    base, status,
                    round(solucao.wall_time_seconds, 4) if solucao else None,
                    round(solucao.objetivo, 4) if solucao else None,
                    getattr(solucao, "conformidade", None),
                    n_trip, n_voos,
                    getattr(solucao, "total_alocacoes", None),
                    getattr(solucao, "variaveis_criadas", None),
                    getattr(solucao, "tripulantes_bloqueados", None),
                    json.dumps(solucao.to_dict(), ensure_ascii=False) if solucao else None,
                ),
            ).fetchone()
        return linha["id"] if linha else None
    except Exception:
        current_app.logger.exception("falha ao registrar execucao")
        return None


def _gravar_escalas(solucao, dia: str, execucao_id) -> tuple[int, int]:
    """Grava as alocacoes em `escalas` com a analise, e atualiza as jornadas."""
    if solucao is None or not solucao.alocacoes:
        return 0, 0

    gravadas, ignoradas = 0, 0
    with transacao() as conexao:
        ids = tuple({a.tripulante_id for a in solucao.alocacoes})
        marcadores = ','.join(['%s'] * len(ids))
        bloqueio = '' if current_app.config.get('TESTING') else ' FOR UPDATE'
        atuais = conexao.execute(
            f'SELECT tripulante_id, horas_acumuladas, limite_horas FROM jornadas '
            f'WHERE periodo = %s AND tripulante_id IN ({marcadores})' + bloqueio,
            (dia,) + ids,
        ).fetchall()
        jornadas = {l['tripulante_id']: l for l in atuais}
        for a in solucao.alocacoes:
            j = jornadas.get(a.tripulante_id)
            if j is None:
                raise RuntimeError('Jornada da data não encontrada. Refaça a otimização.')
            existe = conexao.execute('SELECT id FROM escalas WHERE tripulante_id=%s AND voo_id=%s AND data=%s',
                                     (a.tripulante_id, a.voo_id, dia)).fetchone()
            if existe:
                ignoradas += 1
                continue
            antes, limite = j['horas_acumuladas'], j['limite_horas']
            depois = antes + a.duracao_horas
            if depois > limite + 1e-6:
                raise RuntimeError('As jornadas mudaram e a alocação excederia o limite. Refaça a otimização.')
            cursor = conexao.execute(
                """INSERT INTO escalas
                (tripulante_id, voo_id, data, cargo, origem, destino, duracao_horas,
                 horas_antes, horas_depois, limite_aplicado, ocupacao_percentual,
                 conforme, motivo, status, execucao_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tripulante_id, voo_id, data) DO NOTHING""",
                (a.tripulante_id, a.voo_id, dia, a.cargo,
                 a.rota.split(' → ')[0] if ' → ' in a.rota else '',
                 a.rota.split(' → ')[1] if ' → ' in a.rota else '',
                 a.duracao_horas, antes, depois, limite, round(depois / limite * 100, 1) if limite else 0,
                 True, 'Dentro do limite RBAC 117', 'planejado', execucao_id),
            )
            if not cursor.rowcount:
                ignoradas += 1
                continue
            conexao.execute("""UPDATE jornadas SET horas_voadas=horas_voadas+%s,
                horas_acumuladas=horas_acumuladas+%s, voos_no_periodo=voos_no_periodo+1,
                atualizado_em=NOW() WHERE tripulante_id=%s AND periodo=%s""",
                (a.duracao_horas, a.duracao_horas, a.tripulante_id, dia))
            j['horas_acumuladas'] = depois
            gravadas += 1
    return gravadas, ignoradas
