"""Controle simples da operação simulada e consulta dos remanejamentos."""
from flask import Blueprint, jsonify, request
from blueprints.auth import login_obrigatorio
from operacao import ler_estado, resumo, iniciar_ou_pausar, vagas_replanejamento, replanejar

from db import transacao

bp = Blueprint('operacao', __name__, url_prefix='/api/operacao')


def resposta(estado):
    # Importação tardia evita ciclo entre os blueprints e o mapa.
    from mapa_operacao import snapshot_mapa
    with transacao() as conn:
        aeroportos = conn.execute('SELECT iata,cidade,latitude,longitude FROM aeroportos').fetchall()
    dados = resumo(estado)
    dados['mapa'] = snapshot_mapa(estado, aeroportos)
    return jsonify(dados)


@bp.get('')
@login_obrigatorio
def consultar():
    return resposta(ler_estado())


@bp.post('/iniciar')
@login_obrigatorio
def iniciar():
    try:
        estado = iniciar_ou_pausar(True)
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400
    return resposta(estado)


@bp.post('/pausar')
@login_obrigatorio
def pausar():
    return resposta(iniciar_ou_pausar(False))

@bp.get('/replanejamento/<voo_id>')
@login_obrigatorio
def consultar_vagas(voo_id):
    estado = ler_estado() or {}
    voo = estado.get('voos', {}).get(voo_id)
    if not voo or voo['status'] != 'Aguardando tripulação':
        return jsonify(erro='Voo não está aguardando replanejamento.'), 409
    return jsonify(operacao_id=estado.get('operacao_id'), vagas=vagas_replanejamento(estado, voo))


@bp.post('/replanejamento/<voo_id>')
@login_obrigatorio
def confirmar_equipe(voo_id):
    corpo = request.get_json(silent=True)
    equipe = corpo.get('equipe') if isinstance(corpo, dict) else None
    if not isinstance(equipe, list) or not all(isinstance(tid, str) for tid in equipe):
        return jsonify(erro='Informe a equipe escolhida.'), 400
    try:
        estado = replanejar(voo_id, corpo.get('operacao_id'), equipe)
    except ValueError as exc:
        return jsonify(erro=str(exc)), 409
    return resposta(estado)
