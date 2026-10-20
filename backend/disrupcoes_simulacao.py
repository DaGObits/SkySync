"""Ocorrências do simulador, persistidas atomicamente com o avanço das jornadas."""
from datetime import date, timedelta
import json
from uuid import uuid4


def _horario(estado, minuto):
    dia = date.fromisoformat(estado['dia']) + timedelta(days=minuto // 1440)
    return f'{dia.isoformat()} · {minuto % 1440 // 60:02d}h{minuto % 60:02d}'


def registrar(estado, voo, tipo, minuto, *, descricao, solucao, risco='alto', ativo=True, status=None, detalhes=None):
    if 'operacao_id' not in estado:
        estado['operacao_id'] = uuid4().hex
    chave = f"{estado['operacao_id']}:{estado['dia_ciclo']}:{voo['id']}:{tipo}"
    eventos = estado.setdefault('ocorrencias', {})
    anterior = eventos.get(chave)
    conteudo = dict(descricao=descricao, solucao=solucao, risco=risco, ativo=ativo,
                    status=status or ('Em andamento' if ativo else 'Resolvida'), detalhes=detalhes or [])
    if anterior and all(anterior.get(k) == valor for k, valor in conteudo.items()):
        return anterior
    evento = {**(anterior or {}), **conteudo, 'id': chave, 'ciclo': estado['dia_ciclo'],
              'voo': voo['codigo'], 'voo_id': voo['id'], 'tipo': tipo,
              'rota': voo['origem'] + ' → ' + voo['destino'], 'base': voo['origem'],
              'fonte': 'simulacao', 'dia': estado['dia'],
              'minuto': anterior['minuto'] if anterior else minuto,
              'horario': anterior['horario'] if anterior else _horario(estado, minuto),
              'atualizado_minuto': minuto, 'atualizado_em': _horario(estado, minuto)}
    eventos[chave] = evento
    pendentes = estado.setdefault('ocorrencias_pendentes', [])
    if chave not in pendentes:
        pendentes.append(chave)
    return evento


def resolver(estado, voo, tipo, minuto, solucao, status='Resolvida'):
    eventos = estado.get('ocorrencias', {})
    for e in list(eventos.values()):
        if e['ciclo'] == estado['dia_ciclo'] and e['voo_id'] == voo['id'] and e['tipo'] == tipo and e['ativo']:
            registrar(estado, voo, tipo, minuto, descricao=e['descricao'], risco=e['risco'],
                      ativo=False, status=status, solucao=solucao, detalhes=e.get('detalhes'))


def salvar_pendentes(conn, estado):
    eventos = estado.get('ocorrencias', {})
    for chave in estado.get('ocorrencias_pendentes', []):
        evento = eventos[chave]
        conn.execute('''INSERT INTO disrupcoes_simuladas (id,operacao_id,risco,ativo,minuto,atualizado_minuto,registro)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET
            risco=excluded.risco,ativo=excluded.ativo,atualizado_minuto=excluded.atualizado_minuto,registro=excluded.registro''',
            (chave, estado['operacao_id'], evento['risco'], evento['ativo'], evento['minuto'],
             evento['atualizado_minuto'], json.dumps(evento, ensure_ascii=False)))
    estado['ocorrencias_pendentes'] = []
    # Histórico completo fica na tabela. O estado mantém só o ciclo atual.
    estado['ocorrencias'] = {k: e for k, e in eventos.items() if e['ciclo'] == estado['dia_ciclo']}
