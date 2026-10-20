"""Posições aproximadas calculadas do mesmo estado persistido das jornadas."""
from math import isfinite, atan2, degrees

from blueprints.mapa import CONTORNO_BRASIL, _projetar
from operacao import hhmm


def snapshot_mapa(estado, aeroportos):
    pontos = {}
    for a in aeroportos:
        lat, lon = a['latitude'], a['longitude']
        if lat is None or lon is None or not isfinite(lat) or not isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
            continue
        x, y = _projetar(lat, lon, 900, 900)
        pontos[a['iata']] = {'iata': a['iata'], 'cidade': a['cidade'], 'x': x, 'y': y}
    voos, sem_coordenadas = [], 0
    esperando = {}
    if estado:
        for v in estado['voos'].values():
            if v['status'] == 'Aguardando tripulação':
                esperando[v['origem']] = esperando.get(v['origem'], 0) + 1
            if v['status'] != 'Em voo':
                continue
            origem, destino = pontos.get(v['origem']), pontos.get(v['destino'])
            if not origem or not destino:
                sem_coordenadas += 1
                continue
            decolagem = v['pouso'] - v['duracao']
            progresso = max(0, min(1, (estado['minuto'] - decolagem) / v['duracao']))
            dx, dy = destino['x'] - origem['x'], destino['y'] - origem['y']
            tripulacao = []
            for tid in v['alocados']:
                p = estado['tripulantes'][tid]
                tripulacao.append({'nome': p['nome'], 'cargo': p['cargo'],
                                   'jornada': hhmm(p['horas']), 'limite': hhmm(p['limite'])})
            voos.append({'id': v['id'], 'codigo': v['codigo'], 'origem': origem, 'destino': destino,
                         'x': round(origem['x'] + progresso * dx, 2),
                         'y': round(origem['y'] + progresso * dy, 2),
                         'rumo': round(degrees(atan2(dx, -dy)), 1),
                         'progresso': round(progresso * 100, 1),
                         'restante': hhmm(max(0, v['pouso'] - estado['minuto'])),
                         'atraso_minutos': v['duracao'] - v['prevista'], 'tripulacao': tripulacao})
    usados = set(esperando)
    for v in voos:
        usados.update((v['origem']['iata'], v['destino']['iata']))
    return {'contorno': [_projetar(lat, lon, 900, 900) for lon, lat in CONTORNO_BRASIL],
            'aeroportos': [{**pontos[iata], 'aguardando': esperando.get(iata, 0)}
                          for iata in sorted(usados) if iata in pontos],
            'voos': voos, 'sem_coordenadas': sem_coordenadas}
