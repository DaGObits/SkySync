"""Radar usa observações reais em cache sem bloquear requisições HTTP."""
import time

import pytest
from blueprints import ao_vivo as radar


@pytest.fixture
def consultas(monkeypatch):
    monkeypatch.setattr(radar, '_cache', {
        'dados': None, 'quando': 0, 'erro_consulta_opensky': None,
        'consultando': False, 'ultima_tentativa': 0, 'erro': None,
    })
    pendentes = []

    class ThreadCapturada:
        def __init__(self, target, args, **kwargs):
            self.executar = lambda: target(*args)

        def start(self):
            pendentes.append(self.executar)

    monkeypatch.setattr(radar, 'Thread', ThreadCapturada)
    return pendentes


def observacao():
    return {'disponivel': True, 'fonte': 'OpenSky Network', 'consultado_em': '2026-10-20T12:00:00Z',
            'total': 1, 'voos': [{'icao24': 'abc123', 'callsign': 'TAM1234', 'latitude': -23.4, 'longitude': -46.5}]}


def test_radar_exige_sessao(client):
    assert client.get('/api/ao-vivo').status_code == 401


def test_primeira_consulta_nao_espera_fonte_e_compartilha_atualizacao(usuario_logado, monkeypatch, consultas):
    monkeypatch.setattr(radar, '_consultar_com_fallback', observacao)
    resposta = usuario_logado.get('/api/ao-vivo?limite=500')
    assert resposta.status_code == 200
    assert resposta.json['atualizando'] is True
    assert resposta.json['voos'] == []
    usuario_logado.get('/api/ao-vivo')
    assert len(consultas) == 1
    consultas.pop()()
    dados = usuario_logado.get('/api/ao-vivo').json
    assert dados['disponivel'] is True
    assert dados['atualizando'] is False
    assert dados['voos'][0]['latitude'] == -23.4
    assert not consultas


def test_falha_preserva_observacao_e_limita_tentativas(usuario_logado, monkeypatch, consultas):
    radar._cache.update(dados=observacao(), quando=time.time()-400)

    def falhar():
        raise RuntimeError('sem rede')

    monkeypatch.setattr(radar, '_consultar_com_fallback', falhar)
    anterior = usuario_logado.get('/api/ao-vivo').json
    assert anterior['atualizando'] is True
    consultas.pop()()
    falha = usuario_logado.get('/api/ao-vivo').json
    assert falha['disponivel'] is False
    assert falha['atualizando'] is False
    assert falha['voos'] == anterior['voos']
    assert falha['consultado_em'] == anterior['consultado_em']
    assert not consultas
    # Após a espera mínima, uma atualização boa volta a liberar dados.
    radar._cache['ultima_tentativa'] -= 61
    monkeypatch.setattr(radar, '_consultar_com_fallback', observacao)
    usuario_logado.get('/api/ao-vivo')
    consultas.pop()()
    assert usuario_logado.get('/api/ao-vivo').json['disponivel'] is True


def test_filtro_e_limite_nao_alteram_cache(usuario_logado, consultas):
    radar._cache.update(dados=observacao(), quando=time.time())
    assert usuario_logado.get('/api/ao-vivo?casar=1').json['voos'] == []
    assert len(usuario_logado.get('/api/ao-vivo').json['voos']) == 1
    assert 'na_malha' not in radar._cache['dados']['voos'][0]
    assert usuario_logado.get('/api/ao-vivo?limite=errado').status_code == 400
    assert not consultas
