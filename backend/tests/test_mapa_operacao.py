import copy

from mapa_operacao import snapshot_mapa
from operacao import novo_estado, avancar_estado
from test_operacao import grupo, malha

AEROPORTOS = [dict(iata='GRU', cidade='Guarulhos', latitude=-23.43, longitude=-46.47),
              dict(iata='MAO', cidade='Manaus', latitude=-3.04, longitude=-60.05)]


def estado_voando(monkeypatch):
    monkeypatch.setattr('operacao.atraso_simulado', lambda _: 0)
    return novo_estado(grupo('G', 'GRU') + grupo('R', 'MAO', True), malha())


def test_mapa_sem_operacao_nao_fabrica_voos():
    dados = snapshot_mapa(None, AEROPORTOS)
    assert len(dados['contorno']) > 20
    assert dados['voos'] == []
    assert dados['aeroportos'] == []


def test_posicao_tripulacao_e_pausa_seguem_estado_sem_modifica_lo(monkeypatch):
    estado = estado_voando(monkeypatch)
    assert snapshot_mapa(estado, AEROPORTOS)['voos'] == []
    avancar_estado(estado, 1)
    partida = snapshot_mapa(estado, AEROPORTOS)['voos'][0]
    assert partida['x'] == partida['origem']['x']
    assert partida['progresso'] == 0
    avancar_estado(estado, 31)
    antes = copy.deepcopy(estado)
    voo = snapshot_mapa(estado, AEROPORTOS)['voos'][0]
    assert voo['progresso'] == 50
    assert voo['restante'] == '00h30'
    assert voo['x'] == round((voo['origem']['x'] + voo['destino']['x']) / 2, 2)
    assert {p['nome'] for p in voo['tripulacao']} == {'G' + str(i) for i in range(5)}
    assert all(p['jornada'] == '00h30' for p in voo['tripulacao'])
    assert estado == antes
    estado['rodando'] = False
    avancar_estado(estado, 59)
    assert snapshot_mapa(estado, AEROPORTOS)['voos'][0] == voo
    estado['rodando'] = True
    avancar_estado(estado, 61)
    assert snapshot_mapa(estado, AEROPORTOS)['voos'] == []


def test_partida_atrasada_usa_decolagem_real_e_tripulacao_remanejada(monkeypatch):
    estado = estado_voando(monkeypatch)
    for p in estado['tripulantes'].values():
        if p['base'] == 'GRU':
            p['livre_em'] = 11
    avancar_estado(estado, 11)
    voo = snapshot_mapa(estado, AEROPORTOS)['voos'][0]
    assert voo['progresso'] == 0  # Não começa 10 minutos à frente pelo horário previsto.
    avancar_estado(estado, 41)
    assert snapshot_mapa(estado, AEROPORTOS)['voos'][0]['progresso'] == 50


def test_voos_sem_coordenadas_nao_ganham_posicao_inventada(monkeypatch):
    estado = estado_voando(monkeypatch)
    avancar_estado(estado, 31)
    aeroportos = copy.deepcopy(AEROPORTOS)
    aeroportos[1]['latitude'] = None
    dados = snapshot_mapa(estado, aeroportos)
    assert dados['voos'] == []
    assert dados['sem_coordenadas'] == 1
    estado['voos']['A']['status'] = 'Aguardando tripulação'
    dados = snapshot_mapa(estado, AEROPORTOS)
    assert dados['voos'] == []
    assert dados['aeroportos'][0]['aguardando'] == 1


def test_api_mapa_no_mesmo_snapshot_da_operacao(usuario_logado, app, monkeypatch):
    estado = estado_voando(monkeypatch)
    avancar_estado(estado, 31)
    monkeypatch.setattr('blueprints.operacao.ler_estado', lambda: estado)
    dados = usuario_logado.get('/api/operacao').json
    assert dados['em_voo'] == 5
    assert dados['mapa']['voos'][0]['progresso'] == 50
    assert dados['mapa']['voos'][0]['tripulacao'][0]['jornada'] == '00h30'


def test_mapa_mostra_tripulacao_remanejada_em_vez_do_plano_original(monkeypatch):
    estado = estado_voando(monkeypatch)
    assert estado['voos']['B']['plano'] == ['G' + str(i) for i in range(5)]
    estado['voos']['A']['duracao'] = 120
    avancar_estado(estado, 100)
    mapa = snapshot_mapa(estado, AEROPORTOS)
    voo = next(v for v in mapa['voos'] if v['id'] == 'B')
    assert {p['nome'] for p in voo['tripulacao']} == {'R' + str(i) for i in range(5)}
    assert len(estado['mudancas']) == 5
    assert voo['progresso'] == 0
