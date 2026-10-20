"""Operação simulada contínua: posição, voo, repouso e remanejamentos.

Mantém jornadas, posições e ocorrências da simulação em tabelas isoladas.
O relógio avança 60 vezes mais rápido enquanto a simulação e o servidor rodam.
"""
import copy
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from threading import Event, Thread
from zoneinfo import ZoneInfo

from flask import current_app
from db import transacao
from models import Tripulante, Voo
from disrupcoes_simulacao import registrar, resolver, salvar_pendentes
from optimizer.solver import otimizar, OtimizacaoInviavel

CARGOS = ['Comandante', 'Copiloto', 'Comissário', 'Comissário', 'Comissário']
INTERVALO_SOLO = 30
REPOUSO = 720


def hhmm(minutos):
    return f'{int(minutos)//60:02d}h{int(minutos)%60:02d}'


def atraso_simulado(chave):
    valor = int(hashlib.sha256(chave.encode()).hexdigest()[:8], 16)
    return (30 + valor % 61) if valor % 5 == 0 else 0


def _descanso(p, minuto):
    if (p['descanso_ate'] and minuto >= p['descanso_ate']) or (not p['voo'] and p['horas'] and minuto >= p['livre_em'] + REPOUSO):
        p['horas'] = 0
        p['descanso_ate'] = 0
        p['descanso_ok'] = True
        p['aclimatado'] = True


def impedimento(p, v, minuto):
    if p is None:
        return 'Sem designação anterior'
    if not p.get('habilitado', True):
        return 'Indisponível no cadastro'
    if p['voo']:
        return 'Ainda está em outro voo'
    if p['local'] != v['origem']:
        return f"Está em {p['local']}; a partida é de {v['origem']}"
    if p['descanso_ate'] or not p['descanso_ok']:
        return 'Repouso em andamento'
    if p['livre_em'] > minuto:
        return 'Intervalo em solo ainda não cumprido'
    if not p['aclimatado'] and v['noturno']:
        return 'Não aclimatado para pouso noturno'
    if p['horas'] + v['duracao'] > p['limite']:
        return 'Jornada projetada de ' + hhmm(p['horas'] + v['duracao']) + ' excede ' + hhmm(p['limite'])
    return None


def planejar(estado):
    """Plano inicial viável pelas durações previstas, preservando posição futura."""
    previstos = copy.deepcopy(estado['tripulantes'])
    for v in sorted(estado['voos'].values(), key=lambda v: (v['partida'], v['id'])):
        nominal = {**v, 'duracao': v['prevista']}
        escolhidos = []
        for cargo in CARGOS:
            for p in previstos.values():
                _descanso(p, v['partida'])
            aptos = [p for p in previstos.values() if p['cargo'] == cargo and p['id'] not in escolhidos
                     and not impedimento(p, nominal, v['partida'])]
            aptos.sort(key=lambda p: (p['reserva'], p['horas'], p['id']))
            escolhidos.append(aptos[0]['id'] if aptos else None)
        v['plano'] = escolhidos
        if all(escolhidos):
            for tid in escolhidos:
                p = previstos[tid]
                p['local'] = v['destino']
                p['horas'] += v['prevista']
                p['livre_em'] = v['partida'] + v['prevista'] + INTERVALO_SOLO
                if p['horas'] >= p['limite'] * .85:
                    p['descanso_ok'] = False
                    p['descanso_ate'] = v['partida'] + v['prevista'] + REPOUSO


def novo_estado(pessoas, voos, dia=None):
    if not pessoas or not voos:
        raise ValueError('Cadastre tripulantes e voos programados antes de iniciar a operação.')
    lista = {}
    for v in voos:
        try:
            h, m = str(v['partida']).split(':')[:2]
            partida = int(h) * 60 + int(m)
            if not 0 <= int(h) <= 23 or not 0 <= int(m) <= 59:
                raise ValueError()
        except (ValueError, TypeError):
            continue
        if not v['origem'] or not v['destino'] or float(v['duracao_horas']) <= 0:
            continue
        duracao = max(1, round(float(v['duracao_horas']) * 60))
        lista[v['id']] = {'id': v['id'], 'id_base': v['id'], 'codigo': v['codigo'], 'origem': v['origem'],
            'destino': v['destino'], 'prevista': duracao, 'duracao': duracao + atraso_simulado(v['id']),
            'partida': partida, 'noturno': bool(v['pouso_noturno']), 'status': 'Programado',
            'alocados': [], 'pouso': None, 'motivo': ''}
    if not lista:
        raise ValueError('Nenhum voo com horário HH:MM, origem e destino válidos cadastrado.')
    minuto = max(0, min(v['partida'] for v in lista.values()) - 1)
    tripulantes = {}
    for p in pessoas:
        if not p['base'] or p['cargo'] not in CARGOS or float(p['limite_horas']) <= 0:
            continue
        descanso = bool(p['descanso_ok']) and float(p['horas_acumuladas']) < float(p['limite_horas']) * .85
        tripulantes[p['id']] = {'id': p['id'], 'nome': p['nome'], 'cargo': p['cargo'], 'base': p['base'],
            'local': p['base'], 'horas': round(float(p['horas_acumuladas']) * 60),
            'limite': round(float(p['limite_horas']) * 60), 'descanso_ok': descanso,
            'aclimatado': bool(p['aclimatado']), 'reserva': p['status'] == 'Reserva',
            'livre_em': minuto, 'descanso_ate': 0 if descanso else minuto + REPOUSO, 'voo': None}
    if not tripulantes:
        raise ValueError('Não há tripulantes elegíveis com base e limite configurados.')
    estado = {'rodando': True, 'dia': dia or datetime.now(ZoneInfo('America/Manaus')).date().isoformat(), 'dia_ciclo': 0, 'minuto': minuto,
        'tripulantes': tripulantes, 'voos': lista, 'mudancas': [], 'total_mudancas': 0,
        'erro': None, 'concluida': False, 'concluidos_anteriores': 0, 'nao_atendidos': 0}
    planejar(estado)
    return estado


def _decolar(estado, v, minuto):
    trip = estado['tripulantes']
    escolhidos, faltantes = [], {}
    for cargo, tid in zip(CARGOS, v['plano']):
        p = trip.get(tid)
        if p and p['cargo'] == cargo and not impedimento(p, v, minuto):
            escolhidos.append(tid)
        else:
            escolhidos.append(None)
            faltantes[cargo] = faltantes.get(cargo, 0) + 1
    if faltantes:
        aptos = [p for p in trip.values() if p['id'] not in escolhidos and p['cargo'] in faltantes
                 and not impedimento(p, v, minuto)]
        for cargo, quantidade in faltantes.items():
            if sum(p['cargo'] == cargo for p in aptos) < quantidade:
                v['status'] = 'Aguardando tripulação'
                v['motivo'] = f'Sem {quantidade} substituto(s) de {cargo} apto(s) em {v["origem"]}'
                registrar(estado, v, 'tripulacao', minuto, descricao=v['motivo'], solucao='Aguardando tripulação apta no aeroporto de origem.')
                return
        try:
            solucao = otimizar(v['origem'], [Tripulante(id=p['id'], nome=p['nome'], cargo=p['cargo'],
                base=p['local'], horas_acumuladas=p['horas']/60, limite_horas=p['limite']/60,
                descanso_ok=p['descanso_ok'], aclimatado=p['aclimatado']) for p in aptos],
                [Voo(id=v['id'], codigo=v['codigo'], origem=v['origem'], destino=v['destino'],
                     duracao_horas=v['duracao']/60, pouso_noturno=v['noturno'])],
                limite_horas=max(p['limite'] for p in aptos)/60, max_time_seconds=1,
                composicao=faltantes, bases_por_regiao={})
        except (OtimizacaoInviavel, RuntimeError):
            v['status'] = 'Aguardando tripulação'
            v['motivo'] = 'Não foi encontrada composição viável na origem.'
            registrar(estado, v, 'tripulacao', minuto, descricao=v['motivo'], solucao='Aguardando composição viável pelo otimizador.')
            return
        reservas = {}
        for a in solucao.alocacoes:
            reservas.setdefault(a.cargo, []).append(a.tripulante_id)
        for i, cargo in enumerate(CARGOS):
            if escolhidos[i] is None:
                escolhidos[i] = reservas[cargo].pop(0)
    trocas = []
    for anterior, novo in zip(v['plano'], escolhidos):
        if anterior != novo:
            antigo, atual = trip.get(anterior), trip[novo]
            estado['mudancas'].append({'voo': v['codigo'], 'minuto': minuto,
                'saiu': antigo['nome'] if antigo else 'Sem designação', 'entrou': atual['nome'],
                'local': atual['local'], 'cargo': atual['cargo'],
                'motivo': impedimento(antigo, v, minuto) or 'Completar tripulação',
                'jornada': hhmm(atual['horas']), 'limite': hhmm(atual['limite'])})
            trocas.append(estado['mudancas'][-1])
            estado['total_mudancas'] += 1
    estado['mudancas'] = estado['mudancas'][-200:]
    if trocas:
        registrar(estado, v, 'remanejamento', minuto, risco='medio', ativo=False,
                  descricao=f'{len(trocas)} substituição(ões) para viabilizar o voo.',
                  solucao='; '.join(m['saiu'] + ' → ' + m['entrou'] + ' (' + m['cargo'] + '): ' + m['motivo'] for m in trocas), detalhes=trocas)
    resolver(estado, v, 'tripulacao', minuto, 'Tripulação apta alocada na origem; voo decolou.')
    atraso_partida = max(0, minuto - v['partida'])
    acrescimo = max(0, v['duracao'] - v['prevista'])
    if atraso_partida or acrescimo:
        registrar(estado, v, 'atraso', minuto, risco='alto' if atraso_partida + acrescimo >= 60 else 'medio',
                  descricao=f'Atraso simulado: partida {atraso_partida} min após o previsto e acréscimo de {acrescimo} min à duração.',
                  solucao='Voo em andamento; acompanhamento até o pouso.')
    v.update(status='Em voo', alocados=escolhidos, pouso=minuto+v['duracao'], motivo='')
    for tid in escolhidos:
        trip[tid]['voo'] = v['id']
        trip[tid]['livre_em'] = v['pouso'] + INTERVALO_SOLO


def proximo_dia(estado):
    for v in estado['voos'].values():
        if v['status'] != 'Concluído':
            registrar(estado, v, 'tripulacao', estado['minuto'],
                      descricao=v.get('motivo') or 'Voo não atendido no ciclo da simulação.',
                      solucao='Ciclo encerrado sem tripulação apta para executar o voo.', ativo=False, status='Não atendida')
    estado['dia_ciclo'] += 1
    estado['concluidos_anteriores'] += sum(v['status'] == 'Concluído' for v in estado['voos'].values())
    estado['nao_atendidos'] += sum(v['status'] != 'Concluído' for v in estado['voos'].values())
    novos = {}
    for v in estado['voos'].values():
        chave = v['id_base'] + '@' + str(estado['dia_ciclo'])
        novos[chave] = {**v, 'id': chave,
            'partida': estado['dia_ciclo'] * 1440 + v['partida'] % 1440,
            'duracao': v['prevista'] + atraso_simulado(chave),
            'status': 'Programado', 'alocados': [], 'pouso': None, 'motivo': ''}
    estado['voos'] = novos
    planejar(estado)


def avancar_estado(estado, ate):
    """Passos de um minuto: horas só aumentam em voo e a posição só muda no pouso."""
    if not estado['rodando']:
        return estado
    for minuto in range(estado['minuto'] + 1, ate + 1):
        for p in estado['tripulantes'].values():
            _descanso(p, minuto)
            if not p['voo']:
                continue
            v = estado['voos'][p['voo']]
            p['horas'] += 1
            if minuto >= v['pouso']:
                p['local'] = v['destino']
                p['voo'] = None
                if p['horas'] >= p['limite'] * .85:
                    p['descanso_ok'] = False
                    p['descanso_ate'] = minuto + REPOUSO
        for v in estado['voos'].values():
            if v['status'] == 'Em voo' and minuto >= v['pouso']:
                v['status'] = 'Concluído'
                resolver(estado, v, 'atraso', minuto, 'Voo concluído; tripulação chegou ao destino.')
            if v['status'] in ('Programado', 'Aguardando tripulação') and v['partida'] <= minuto:
                _decolar(estado, v, minuto)
        estado['minuto'] = minuto
        # Repete a malha no dia seguinte, preservando posições e repousos.
        fim = max(v['partida'] + v['duracao'] for v in estado['voos'].values()) + 180
        if all(v['status'] == 'Concluído' for v in estado['voos'].values()) or (minuto >= fim and not any(v['status'] == 'Em voo' for v in estado['voos'].values())):
            proximo_dia(estado)
    return estado


def preparar_banco():
    with transacao() as conn:
        if not current_app.config.get('TESTING'):
            conn.execute('SELECT pg_advisory_xact_lock(5739201)')
        conn.execute((Path(__file__).parent / 'migrations' / 'operacao.sql').read_text())
        conn.execute((Path(__file__).parent / 'migrations' / 'disrupcoes_simuladas.sql').read_text())


def _lock(conn):
    if not current_app.config.get('TESTING'):
        conn.execute('SELECT pg_advisory_xact_lock(5739202)')


def ler_estado():
    with transacao() as conn:
        linha = conn.execute('SELECT estado FROM operacao_simulada WHERE id=1').fetchone()
    return json.loads(linha['estado']) if linha else None


def _salvar(conn, estado, agora):
    salvar_pendentes(conn, estado)
    conn.execute('''INSERT INTO operacao_simulada (id,estado,atualizado_em) VALUES (1,%s,%s)
        ON CONFLICT(id) DO UPDATE SET estado=excluded.estado,atualizado_em=excluded.atualizado_em''',
        (json.dumps(estado, ensure_ascii=False), agora.isoformat()))


def sincronizar_pessoas(conn, estado):
    pessoas = conn.execute('''SELECT t.id,TRIM(t.nome || ' ' || t.sobrenome) AS nome,
        t.cargo,t.base,t.status,COALESCE(j.horas_acumuladas,0) AS horas_acumuladas,
        COALESCE(j.limite_horas,%s) AS limite_horas,COALESCE(j.descanso_ok,TRUE) AS descanso_ok,
        COALESCE(j.aclimatado,TRUE) AS aclimatado FROM tripulantes t
        LEFT JOIN jornadas j ON j.tripulante_id=t.id AND j.periodo=%s''',
        (current_app.config['SOLVER_DEFAULT_HOUR_LIMIT'], datetime.now(ZoneInfo('America/Manaus')).date().isoformat())).fetchall()
    for p in estado['tripulantes'].values():
        p['habilitado'] = False
    for pessoa in pessoas:
        tid = pessoa['id']
        habilitado = pessoa['status'] in ('Disponível', 'Reserva')
        if tid not in estado['tripulantes'] and habilitado:
            # Novos cadastros começam na base; posições existentes não são alteradas.
            limite = round(float(pessoa['limite_horas']) * 60)
            if not pessoa['base'] or pessoa['cargo'] not in CARGOS or limite <= 0:
                continue
            horas = round(float(pessoa['horas_acumuladas']) * 60)
            descanso = bool(pessoa['descanso_ok']) and horas < limite * .85
            estado['tripulantes'][tid] = {'id': tid, 'nome': pessoa['nome'], 'cargo': pessoa['cargo'],
                'base': pessoa['base'], 'local': pessoa['base'], 'horas': horas, 'limite': limite,
                'descanso_ok': descanso, 'aclimatado': bool(pessoa['aclimatado']),
                'reserva': pessoa['status'] == 'Reserva', 'livre_em': estado['minuto'],
                'descanso_ate': 0 if descanso else estado['minuto'] + REPOUSO, 'voo': None}
        if tid in estado['tripulantes']:
            p = estado['tripulantes'][tid]
            p['habilitado'] = habilitado
            p['nome'], p['base'] = pessoa['nome'], pessoa['base']
            p['reserva'] = pessoa['status'] == 'Reserva'
            if not p['voo']:
                p['cargo'] = pessoa['cargo']


def iniciar_ou_pausar(rodando):
    agora = datetime.now(timezone.utc)
    with transacao() as conn:
        _lock(conn)
        linha = conn.execute('SELECT estado FROM operacao_simulada WHERE id=1').fetchone()
        estado = json.loads(linha['estado']) if linha else None
        if rodando and (estado is None or estado['concluida']):
            pessoas = conn.execute('''SELECT t.id,TRIM(t.nome || ' ' || t.sobrenome) AS nome,t.cargo,t.base,t.status,
                COALESCE(j.horas_acumuladas,0) AS horas_acumuladas,
                COALESCE(j.limite_horas,%s) AS limite_horas,
                COALESCE(j.descanso_ok,TRUE) AS descanso_ok,COALESCE(j.aclimatado,TRUE) AS aclimatado
                FROM tripulantes t LEFT JOIN jornadas j ON j.tripulante_id=t.id AND j.periodo=%s
                WHERE t.status IN ('Disponível','Reserva') ORDER BY t.id''',
                (current_app.config['SOLVER_DEFAULT_HOUR_LIMIT'], datetime.now(ZoneInfo('America/Manaus')).date().isoformat())).fetchall()
            voos = conn.execute("SELECT * FROM voos WHERE status='Programado' ORDER BY partida,id").fetchall()
            estado = novo_estado(pessoas, voos)
        if estado:
            estado['rodando'] = rodando
            estado['erro'] = None
            _salvar(conn, estado, agora)
    evento = current_app.extensions.get('operacao_acordar')
    if evento:
        evento.set()
    return estado


def executar_passo(agora=None):
    agora = agora or datetime.now(timezone.utc)
    with transacao() as conn:
        _lock(conn)
        linha = conn.execute('SELECT * FROM operacao_simulada WHERE id=1').fetchone()
        if not linha:
            return False
        estado = json.loads(linha['estado'])
        if not estado['rodando']:
            return False
        delta = (agora-datetime.fromisoformat(linha['atualizado_em'])).total_seconds()
        # Suspensão/reinício não dispara horas de processamento retroativo.
        minutos = max(0, min(30, int(delta))) if delta < 60 else 0
        try:
            sincronizar_pessoas(conn, estado)
            avancar_estado(estado, estado['minuto']+minutos)
        except Exception:
            # Não persiste passos parcialmente executados em caso de falha.
            estado = json.loads(linha['estado'])
            estado['rodando'] = False
            estado['erro'] = 'A simulação foi pausada após uma falha. Consulte os logs do servidor.'
            current_app.logger.exception('Falha na operação simulada')
        _salvar(conn, estado, agora)
        return estado['rodando']


def situacao(p, estado):
    if p['voo']:
        v = estado['voos'][p['voo']]
        return 'Em voo', v['origem'] + ' → ' + v['destino']
    if not p.get('habilitado', True):
        return 'Indisponível', p['local']
    if p['descanso_ate']:
        return 'Em repouso', p['local']
    if p['livre_em'] > estado['minuto']:
        return 'Intervalo em solo', p['local']
    return 'Disponível', p['local']


def resumo(estado):
    if not estado:
        return {'iniciada': False, 'rodando': False, 'mudancas': []}
    voos = list(estado['voos'].values())
    return {'iniciada': True, 'rodando': estado['rodando'], 'concluida': estado['concluida'],
        'relogio': str(date.fromisoformat(estado['dia']) + timedelta(days=estado['minuto']//1440)) + ' · ' + hhmm(estado['minuto']%1440),
        'tripulantes': len(estado['tripulantes']),
        'em_voo': sum(bool(p['voo']) for p in estado['tripulantes'].values()),
        'em_repouso': sum(bool(p['descanso_ate']) for p in estado['tripulantes'].values()),
        'restritos': sum(not p.get('habilitado', True) or bool(p['descanso_ate']) or p['horas'] >= p['limite'] for p in estado['tripulantes'].values()),
        'dentro_limite': sum(p['horas'] <= p['limite'] for p in estado['tripulantes'].values()),
        'concluidos': estado.get('concluidos_anteriores', 0) + sum(v['status']=='Concluído' for v in voos),
        'nao_atendidos': estado.get('nao_atendidos', 0),
        'aguardando': sum(v['status']=='Aguardando tripulação' for v in voos),
        'total_mudancas': estado['total_mudancas'], 'mudancas': list(reversed(estado['mudancas'])),
        'erro': estado['erro']}


def iniciar_agendador(app):
    if app.config.get('TESTING'):
        return None
    with app.app_context():
        preparar_banco()
    parar, acordar = Event(), Event()
    app.extensions['operacao_acordar'] = acordar
    def loop():
        while not parar.is_set():
            ativo = False
            with app.app_context():
                try:
                    ativo = executar_passo()
                except Exception:
                    app.logger.exception('Agendador da operação indisponível')
            acordar.wait(5 if ativo else 60)
            acordar.clear()
    thread = Thread(target=loop, daemon=True, name='operacao-simulada')
    thread.start()
    return parar, acordar
