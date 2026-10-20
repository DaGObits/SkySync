"""Histórico de ocorrências geradas pela mesma operação das jornadas e do mapa."""
import json
from flask import Blueprint, jsonify, request

from blueprints.auth import login_obrigatorio
from db import transacao
from operacao import ler_estado

bp = Blueprint('disrupcoes', __name__, url_prefix='/api/disrupcoes')


@bp.get('')
@login_obrigatorio
def listar():
    risco = request.args.get('risco', '').strip()
    if risco and risco not in {'alto', 'medio', 'baixo'}:
        return jsonify({'erro': 'risco deve ser alto, medio ou baixo'}), 400
    try:
        limite = max(1, min(1000, int(request.args.get('limite', 200))))
    except (ValueError, TypeError):
        return jsonify({'erro': 'limite deve ser um número'}), 400
    estado = ler_estado()
    operacao_id = (estado or {}).get('operacao_id', '')
    where, params = 'WHERE operacao_id = %s', [operacao_id]
    if risco:
        where += ' AND risco = %s'
        params.append(risco)
    with transacao() as conn:
        linhas = conn.execute(f'''SELECT registro FROM disrupcoes_simuladas {where}
            ORDER BY ativo DESC,atualizado_minuto DESC,id DESC LIMIT %s''', tuple(params + [limite])).fetchall()
        contagens = conn.execute(f'''SELECT COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN ativo THEN 1 ELSE 0 END),0) AS ativas,
            COALESCE(SUM(CASE WHEN ativo AND risco='alto' THEN 1 ELSE 0 END),0) AS altas
            FROM disrupcoes_simuladas {where}''', tuple(params)).fetchone()
    return jsonify({**contagens, 'retornados': len(linhas), 'disrupcoes': [json.loads(l['registro']) for l in linhas]})
