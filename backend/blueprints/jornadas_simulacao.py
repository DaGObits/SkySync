"""Prévia de jornadas fictícias; não persiste jornadas ou escalas."""
from datetime import date

from flask import Blueprint, current_app, jsonify, request
from blueprints.auth import login_obrigatorio
from dados.jornadas import PERFIS, gerar_jornadas, resumir
from db import transacao

bp = Blueprint('jornadas_simulacao', __name__, url_prefix='/api/jornadas')


def validar_data(valor=None):
    if valor is None:
        return date.today().isoformat()
    if not isinstance(valor, str):
        raise ValueError('data deve estar no formato AAAA-MM-DD')
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        raise ValueError('data deve estar no formato AAAA-MM-DD') from None


def montar_cenario(parametros, dia):
    if not isinstance(parametros, dict):
        raise ValueError('simulacao_jornadas deve ser um objeto')
    seed, perfil = parametros.get('seed', 42), parametros.get('perfil', 'leve')
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483647:
        raise ValueError('seed deve ser um inteiro entre 0 e 2147483647')
    if not isinstance(perfil, str) or perfil not in PERFIS:
        raise ValueError('perfil deve ser leve, moderado ou critico')
    with transacao() as conn:
        pessoas = conn.execute('''
            SELECT t.id AS tripulante_id, t.nome, t.sobrenome, t.cargo, t.base,
                   COALESCE(j.limite_horas, %s) AS limite_horas
            FROM tripulantes t LEFT JOIN jornadas j ON j.tripulante_id=t.id AND j.periodo=%s
            WHERE t.status IN ('Disponível', 'Reserva') ORDER BY t.id
        ''', (current_app.config['SOLVER_DEFAULT_HOUR_LIMIT'], dia)).fetchall()
    if not pessoas:
        raise ValueError('Nenhum tripulante disponível ou em reserva cadastrado para simular')
    jornadas = gerar_jornadas(pessoas, seed, perfil)
    return {
        'simulado': True, 'parametros': {'seed': seed, 'perfil': perfil, 'data': dia},
        'resumo': resumir(jornadas), 'jornadas': jornadas,
    }


@bp.post('/simular')
@login_obrigatorio
def simular():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({'erro': 'envie um objeto JSON'}), 400
    try:
        cenario = montar_cenario(corpo, validar_data(corpo.get('data')))
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400
    return jsonify(cenario)
