"""Controle simples da operação simulada e consulta dos remanejamentos."""
from flask import Blueprint, jsonify
from blueprints.auth import login_obrigatorio
from operacao import ler_estado, resumo, iniciar_ou_pausar

bp = Blueprint('operacao', __name__, url_prefix='/api/operacao')


@bp.get('')
@login_obrigatorio
def consultar():
    return jsonify(resumo(ler_estado()))


@bp.post('/iniciar')
@login_obrigatorio
def iniciar():
    try:
        estado = iniciar_ou_pausar(True)
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400
    return jsonify(resumo(estado))


@bp.post('/pausar')
@login_obrigatorio
def pausar():
    return jsonify(resumo(iniciar_ou_pausar(False)))
