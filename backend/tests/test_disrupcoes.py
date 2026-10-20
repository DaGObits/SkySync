"""As ocorrências acompanham as mesmas decisões e transações das jornadas."""
import copy
import pytest
from datetime import datetime, timedelta, timezone

from db import transacao
from operacao import novo_estado, avancar_estado, ler_estado, executar_passo, _salvar
from test_operacao import grupo, malha, dados_operacao, atraso


def salvar(app, estado):
    with app.app_context(), transacao() as conn:
        _salvar(conn, estado, datetime.now(timezone.utc))


def estado_atrasado(monkeypatch, reserva='MAO'):
    monkeypatch.setattr('operacao.atraso_simulado', lambda chave: 60 if chave == 'A' else 0)
    return novo_estado(grupo('G', 'GRU') + grupo('R', reserva, True), malha())


def test_sessao_e_rotas_externas_removidas(client, usuario_logado):
    client.post('/api/auth/logout')
    assert client.get('/api/disrupcoes').status_code == 401
    assert client.get('/api/ao-vivo').status_code == 404
    assert client.get('/api/disrupcoes/importacao/status').status_code == 404
    assert client.post('/api/disrupcoes', json={}).status_code == 405


def test_lista_vazia_e_validacao(usuario_logado):
    assert usuario_logado.get('/api/disrupcoes').json == dict(disrupcoes=[], total=0, retornados=0, ativas=0, altas=0)
    assert usuario_logado.get('/api/disrupcoes?risco=outro').status_code == 400
    assert usuario_logado.get('/api/disrupcoes?limite=abc').status_code == 400


def test_atraso_remanejamento_resolucao_e_persistencia(usuario_logado, app, monkeypatch):
    estado = estado_atrasado(monkeypatch)
    avancar_estado(estado, 100)
    salvar(app, estado)
    dados = usuario_logado.get('/api/disrupcoes').json
    assert dados['total'] == 2
    assert dados['ativas'] == dados['altas'] == 1
    atraso_voo = next(e for e in dados['disrupcoes'] if e['tipo'] == 'atraso')
    trocas = next(e for e in dados['disrupcoes'] if e['tipo'] == 'remanejamento')
    assert atraso_voo['voo'] == 'TEST-A' and atraso_voo['ativo']
    assert trocas['status'] == 'Resolvida' and len(trocas['detalhes']) == 5
    assert trocas['detalhes'] == estado['mudancas']
    assert all(m['local'] == 'MAO' for m in trocas['detalhes'])
    assert 'Ainda está em outro voo' in trocas['solucao']
    avancar_estado(estado, 121)
    salvar(app, estado)
    depois = usuario_logado.get('/api/disrupcoes').json
    assert depois['total'] == 2 and depois['ativas'] == 0
    assert next(e for e in depois['disrupcoes'] if e['id'] == atraso_voo['id'])['status'] == 'Resolvida'
    antes = copy.deepcopy(depois)
    assert usuario_logado.get('/api/disrupcoes').json == antes
    assert usuario_logado.post('/api/operacao/pausar').status_code == 200
    assert usuario_logado.get('/api/disrupcoes').json == antes
    with app.app_context():
        assert ler_estado()['ocorrencias_pendentes'] == []
        with transacao() as conn:
            assert conn.execute('SELECT COUNT(*) AS n FROM jornadas').fetchone()['n'] == 0
            assert conn.execute('SELECT COUNT(*) AS n FROM escalas').fetchone()['n'] == 0


def test_espera_nao_duplica_e_resolve_ao_decolar(usuario_logado, app, monkeypatch):
    estado = estado_atrasado(monkeypatch, reserva='BSB')
    avancar_estado(estado, 110)
    salvar(app, estado)
    espera = next(e for e in usuario_logado.get('/api/disrupcoes').json['disrupcoes'] if e['tipo'] == 'tripulacao')
    assert espera['ativo'] and espera['minuto'] == 100
    for minuto in (111, 112, 113):
        avancar_estado(estado, minuto)
        salvar(app, estado)
    dados = usuario_logado.get('/api/disrupcoes').json
    assert len([e for e in dados['disrupcoes'] if e['tipo'] == 'tripulacao']) == 1
    # A equipe original chega ao destino e cumpre o intervalo em solo.
    avancar_estado(estado, 151)
    salvar(app, estado)
    atual = next(e for e in usuario_logado.get('/api/disrupcoes').json['disrupcoes'] if e['id'] == espera['id'])
    assert not atual['ativo'] and atual['status'] == 'Resolvida'
    assert atual['horario'] == espera['horario']
    assert atual['atualizado_minuto'] == 151


def test_sem_tripulacao_encerra_como_nao_atendido_e_preserva_historico(usuario_logado, app, monkeypatch):
    estado = estado_atrasado(monkeypatch)
    for p in estado['tripulantes'].values():
        p['habilitado'] = False
    avancar_estado(estado, 500)
    assert estado['dia_ciclo'] == 1
    salvar(app, estado)
    dados = usuario_logado.get('/api/disrupcoes').json
    assert dados['total'] == 2 and dados['ativas'] == 0
    assert all(e['status'] == 'Não atendida' for e in dados['disrupcoes'])
    assert estado['ocorrencias'] == {}
    avancar_estado(estado, 1541)
    salvar(app, estado)
    assert usuario_logado.get('/api/disrupcoes').json['total'] > dados['total']


def test_limite_nao_trunca_contagens_e_nova_operacao_nao_mistura(usuario_logado, app, monkeypatch):
    estado = estado_atrasado(monkeypatch)
    avancar_estado(estado, 100); salvar(app, estado)
    dados = usuario_logado.get('/api/disrupcoes?limite=1').json
    assert dados['total'] == 2 and dados['retornados'] == 1 and dados['ativas'] == 1
    assert usuario_logado.get('/api/disrupcoes?risco=medio').json['total'] == 1
    outra = estado_atrasado(monkeypatch)
    avancar_estado(outra, 1); salvar(app, outra)
    assert usuario_logado.get('/api/disrupcoes').json['total'] == 1
    with app.app_context(), transacao() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM disrupcoes_simuladas').fetchone()['n'] == 3


def test_agendador_grava_eventos_com_jornadas_e_nao_repete_mesmo_passo(usuario_logado, dados_operacao):
    usuario_logado.post('/api/operacao/iniciar')
    with dados_operacao.app_context():
        with transacao() as conn:
            inicio = conn.execute('SELECT atualizado_em FROM operacao_simulada').fetchone()['atualizado_em']
        agora = datetime.fromisoformat(inicio) + timedelta(seconds=10)
        executar_passo(agora)
        estado = ler_estado()
        assert estado.get('operacao_id')
        executar_passo(agora)
        assert ler_estado() == estado
    dados = usuario_logado.get('/api/disrupcoes').json
    assert dados['total'] == 1 and dados['disrupcoes'][0]['voo'] == 'TEST-A'


def test_falha_ao_salvar_estado_reverte_ocorrencias_da_mesma_transacao(app, monkeypatch):
    estado = estado_atrasado(monkeypatch)
    salvar(app, estado)
    with app.app_context():
        antes = ler_estado()
        avancar_estado(estado, 100)
        with pytest.raises(RuntimeError):
            with transacao() as conn:
                original = conn.execute
                def executar(sql, params=()):
                    if 'INSERT INTO operacao_simulada' in sql:
                        raise RuntimeError('falha controlada após gravar eventos')
                    return original(sql, params)
                monkeypatch.setattr(conn, 'execute', executar)
                _salvar(conn, estado, datetime.now(timezone.utc))
        assert ler_estado() == antes
        with transacao() as conn:
            assert conn.execute('SELECT COUNT(*) AS n FROM disrupcoes_simuladas').fetchone()['n'] == 0
