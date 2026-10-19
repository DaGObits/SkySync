from datetime import datetime, timedelta, timezone
import logging
from unittest.mock import Mock

import requests

from db import transacao
from importador_voos import ConfigImportacao, consultar, executar_ciclo, normalizar, status_importacao, ErroFornecedor

AGORA = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
CFG = ConfigImportacao(chave='chave-secreta-de-teste', intervalo=3600, limite_diario=2)


def voo(status='scheduled', atraso=30):
    return {
        'flight_date': '2026-10-19', 'flight_status': status,
        'flight': {'iata': 'LA1234'},
        'departure': {'iata': 'GRU', 'scheduled': '2026-10-19T12:00:00+00:00', 'delay': atraso},
        'arrival': {'iata': 'MAO'},
    }


def resposta(monkeypatch, voos=None, **extra):
    get = Mock(return_value=Mock(status_code=200, json=Mock(return_value={
        'data': voos if voos is not None else [voo()], **extra
    })))
    monkeypatch.setattr('importador_voos.requests.get', get)
    return get


def test_sem_chave_nao_consulta(app, monkeypatch):
    get = resposta(monkeypatch)
    with app.app_context():
        assert not executar_ciclo(ConfigImportacao(), AGORA)['executado']
        assert status_importacao()['configurada'] is False
    get.assert_not_called()


def test_real_criterios_sem_inventar_causa():
    assert normalizar(voo(atraso=0), CFG) is None
    assert normalizar(voo(atraso=14), CFG) is None
    assert normalizar(voo(atraso=float('inf')), CFG) is None
    assert normalizar({'flight_status': 'cancelled'}, CFG) is None
    assert normalizar(voo(atraso=15), CFG)['risco'] == 'medio'
    assert normalizar(voo(atraso=60), CFG)['risco'] == 'alto'
    evento = normalizar(voo(status='cancelled', atraso=None), CFG)
    assert evento['risco'] == 'alto'
    assert 'Cancelamento informado' in evento['descricao']
    assert 'causa não informada' in evento['descricao']
    assert 'chave-secreta' not in repr(CFG)


def test_persiste_atualiza_sem_duplicar_e_respeita_cota(app, monkeypatch):
    get = resposta(monkeypatch, pagination={'total': 300})
    with app.app_context():
        result = executar_ciclo(CFG, AGORA)
        assert result == {'executado': True, 'ocorrencias': 1, 'parcial': True}
        assert not executar_ciclo(CFG, AGORA + timedelta(minutes=20))['executado']
        get.return_value.json.return_value = {'data': [voo(status='cancelled')]}
        assert executar_ciclo(CFG, AGORA + timedelta(hours=1))['executado']
        assert not executar_ciclo(CFG, AGORA + timedelta(hours=2))['executado']
        with transacao() as conn:
            assert conn.execute('SELECT COUNT(*) AS n FROM disrupcoes').fetchone()['n'] == 1
            assert conn.execute('SELECT descricao FROM disrupcoes').fetchone()['descricao'].startswith('Cancelamento')
        # Simula reinício: nova configuração não apaga orçamento/agendamento no banco.
        assert not executar_ciclo(CFG, AGORA + timedelta(hours=3))['executado']
        assert executar_ciclo(CFG, AGORA + timedelta(days=1))['executado']
    assert get.call_count == 3
    args, kwargs = get.call_args
    assert args[0].startswith('https://')
    assert kwargs['params']['dep_iata'] == 'GRU'
    assert kwargs['timeout'] == (5, 20)
    assert kwargs.get('verify', True) is True


def test_falha_preserva_ocorrencias_sem_expor_chave(app, monkeypatch, caplog):
    get = resposta(monkeypatch)
    with app.app_context():
        executar_ciclo(CFG, AGORA)
        get.side_effect = requests.Timeout('URL access_key=chave-secreta-de-teste')
        with caplog.at_level(logging.WARNING):
            result = executar_ciclo(CFG, AGORA + timedelta(hours=1))
        assert 'erro' in result
        assert 'chave-secreta-de-teste' not in str(result) + caplog.text
        with transacao() as conn:
            assert conn.execute('SELECT COUNT(*) AS n FROM disrupcoes').fetchone()['n'] == 1
            estado = conn.execute('SELECT * FROM importacao_voos_estado').fetchone()
            assert estado['ultimo_sucesso'] == AGORA.isoformat()
            assert estado['chamadas_dia'] == 2


def test_cota_fornecedor_nao_vira_lista_vazia(monkeypatch):
    get = resposta(monkeypatch)
    get.return_value.json.return_value = {'error': {'type': 'usage_limit_reached', 'info': 'access_key=nao-exibir'}}
    try:
        consultar(CFG)
        assert False, 'deveria informar erro do fornecedor'
    except ErroFornecedor as exc:
        assert 'Cota' in str(exc)
        assert 'nao-exibir' not in str(exc)


def test_status_autenticado_e_fonte_na_lista(usuario_logado, app, monkeypatch):
    resposta(monkeypatch)
    with app.app_context():
        executar_ciclo(CFG, AGORA)
    status = usuario_logado.get('/api/disrupcoes/importacao/status')
    assert status.status_code == 200
    assert status.get_json()['ultimo_sucesso'] == AGORA.isoformat()
    assert 'chave' not in status.get_json()
    lista = usuario_logado.get('/api/disrupcoes').get_json()
    assert lista['disrupcoes'][0]['fonte'] == 'aviationstack'
