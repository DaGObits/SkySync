"""Jornadas fictícias reproduzíveis para experimentar o otimizador.

Usa tripulantes cadastrados e limites configurados, sem alterar o banco.
Não representa horas efetivamente trabalhadas nem uma avaliação médica.
"""
import random

PERFIS = {
    'leve': (0.05, 0.45, 0.05, 0.05),
    'moderado': (0.25, 0.90, 0.15, 0.15),
    'critico': (0.60, 1.10, 0.30, 0.25),
}


def gerar_jornadas(tripulantes, seed=42, perfil='leve'):
    minimo, maximo, sem_descanso, sem_aclimatacao = PERFIS[perfil]
    jornadas = []
    for pessoa in sorted(tripulantes, key=lambda p: p['tripulante_id']):
        rng = random.Random(f'{seed}:{pessoa["tripulante_id"]}')
        limite = float(pessoa['limite_horas'])
        horas = round(rng.uniform(minimo, maximo) * limite * 4) / 4
        jornadas.append({
            'id': pessoa['tripulante_id'],
            'nome': ' '.join(p for p in [pessoa['nome'], pessoa.get('sobrenome')] if p),
            'cargo': pessoa['cargo'], 'base': pessoa['base'],
            'horas_acumuladas': horas, 'limite_horas': limite,
            'descanso_ok': rng.random() >= sem_descanso,
            'aclimatado': rng.random() >= sem_aclimatacao,
        })
    return jornadas


def resumir(jornadas):
    return {
        'total': len(jornadas),
        'sem_descanso': sum(not j['descanso_ok'] for j in jornadas),
        'nao_aclimatados': sum(not j['aclimatado'] for j in jornadas),
        'no_limite': sum(j['horas_acumuladas'] >= j['limite_horas'] for j in jornadas),
        'aptos_por_jornada': sum(j['descanso_ok'] and j['horas_acumuladas'] < j['limite_horas'] for j in jornadas),
    }
