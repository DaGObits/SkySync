"""Controle simples da operação simulada e consulta dos remanejamentos."""
from flask import Blueprint, jsonify
from blueprints.auth import login_obrigatorio
from operacao import ler_estado, resumo, iniciar_ou_pausar

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
