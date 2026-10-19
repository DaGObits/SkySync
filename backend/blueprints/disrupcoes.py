"""Ocorrências operacionais registradas, independentes das escalas calculadas."""
from flask import Blueprint, jsonify, request

from blueprints.auth import login_obrigatorio
from db import transacao

bp = Blueprint('disrupcoes', __name__, url_prefix='/api/disrupcoes')
RISCOS = {'alto', 'medio', 'baixo'}
CAMPOS = 'id, voo, tripulante, cargo, risco, descricao, rota, horario, horas, limit_rbac, solucao, bloqueado, base, criado_em'


def _serializar(linha):
    dado = dict(linha)
    dado['bloqueado'] = bool(dado['bloqueado'])
    dado['criado_em'] = str(dado['criado_em'])
    return dado


@bp.get('')
@login_obrigatorio
def listar():
    risco = request.args.get('risco', '').strip()
    if risco and risco not in RISCOS:
        return jsonify({'erro': 'risco deve ser alto, medio ou baixo'}), 400
    try:
        limite = max(1, min(1000, int(request.args.get('limite', 200))))
    except (ValueError, TypeError):
        return jsonify({'erro': 'limite deve ser um número'}), 400
    where, params = ('WHERE risco = %s', [risco]) if risco else ('', [])
    with transacao() as conn:
        linhas = conn.execute(
            f'SELECT {CAMPOS} FROM disrupcoes {where} ORDER BY criado_em DESC, id DESC LIMIT %s',
            tuple(params + [limite]),
        ).fetchall()
        total = conn.execute(f'SELECT COUNT(*) AS n FROM disrupcoes {where}', tuple(params)).fetchone()['n']
    return jsonify({'total': total, 'retornados': len(linhas), 'disrupcoes': [_serializar(l) for l in linhas]})


@bp.post('')
@login_obrigatorio
def registrar():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return jsonify({'erro': 'envie um objeto JSON'}), 400
    campos, erros = {}, {}
    for nome, tamanho in [('voo', 30), ('descricao', 2000), ('rota', 100), ('base', 10), ('risco', 10)]:
        valor = corpo.get(nome, '')
        if not isinstance(valor, str) or len(valor.strip()) > tamanho:
            erros[nome] = f'deve ser texto com até {tamanho} caracteres'
        else:
            campos[nome] = valor.strip()
    if not campos.get('voo'):
        erros['voo'] = 'informe o voo'
    if len(campos.get('descricao', '')) < 5:
        erros['descricao'] = 'descreva a ocorrência com ao menos 5 caracteres'
    if campos.get('risco') not in RISCOS:
        erros['risco'] = 'selecione alto, medio ou baixo'
    if erros:
        return jsonify({'erro': 'dados inválidos', 'campos': erros}), 400
    with transacao() as conn:
        linha = conn.execute(
            f'''INSERT INTO disrupcoes (voo, descricao, risco, rota, base)
                VALUES (%s, %s, %s, %s, %s) RETURNING {CAMPOS}''',
            (campos['voo'].upper(), campos['descricao'], campos['risco'], campos['rota'], campos['base'].upper()),
        ).fetchone()
    return jsonify({'disrupcao': _serializar(linha)}), 201
