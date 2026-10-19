from types import SimpleNamespace

import pytest
from db import transacao
from blueprints.escalas_voos import _gravar_escalas

DIA = '2026-10-19'
ANTERIOR = '2026-10-18'


@pytest.fixture
def pool(app):
    with app.app_context(), transacao() as conn:
        for i in range(50):
            cargo = 'Comandante' if i < 10 else 'Copiloto' if i < 20 else 'Comissário'
            conn.execute('INSERT INTO tripulantes (id,nome,cargo,base,status) VALUES (%s,%s,%s,%s,%s)',
                         (f'T{i:03}', f'Pessoa {i}', cargo, 'GRU', 'Disponível'))
        conn.execute('INSERT INTO voos (id,codigo,origem,destino,duracao_horas,pouso_noturno) VALUES (%s,%s,%s,%s,%s,%s)',
                     ('V1','TEST-001','GRU','MAO',1.5,False))
    return app


def contagem(app, tabela):
    with app.app_context(), transacao() as conn:
        return conn.execute('SELECT COUNT(*) AS n FROM '+tabela).fetchone()['n']


def jornadas_reais(app):
    with app.app_context(), transacao() as conn:
        for i in range(50):
            for dia, horas in [(DIA,2),(ANTERIOR,10.5)]:
                conn.execute('INSERT INTO jornadas (tripulante_id,periodo,horas_acumuladas,limite_horas) VALUES (%s,%s,%s,%s)',
                             (f'T{i:03}',dia,horas,11))


def test_exige_login(client):
    assert client.post('/api/jornadas/simular',json={}).status_code == 401


def test_previa_reproduzivel_sem_persistencia(usuario_logado,pool):
    corpo={'data':DIA,'seed':42,'perfil':'moderado'}
    a=usuario_logado.post('/api/jornadas/simular',json=corpo)
    assert a.status_code==200
    assert a.get_json()==usuario_logado.post('/api/jornadas/simular',json=corpo).get_json()
    assert a.get_json()['resumo']['total']==50
    assert a.get_json()['resumo']['sem_descanso']>0
    assert a.get_json()['jornadas']!=usuario_logado.post('/api/jornadas/simular',json={**corpo,'seed':43}).get_json()['jornadas']
    assert contagem(pool,'jornadas')==0
    assert contagem(pool,'escalas')==0


def test_simulacao_otimiza_sem_gravar(usuario_logado,pool):
    corpo={'data':DIA,'seed':42,'perfil':'leve'}
    previa=usuario_logado.post('/api/jornadas/simular',json=corpo).get_json()
    r=usuario_logado.post('/api/escalas/otimizar',json={
        'data':DIA,'limite_voos':1,'gravar':False,'simulacao_jornadas':{'seed':42,'perfil':'leve'}})
    assert r.status_code==200, r.get_json()
    d=r.get_json()
    assert d['status'] in ('OPTIMAL','FEASIBLE')
    assert d['total_alocacoes']==5
    assert d['origem_jornadas']=='simulacao'
    assert d['simulacao_jornadas']['resumo']==previa['resumo']
    assert d['escalas_gravadas']==0
    for tabela in ['jornadas','escalas','execucoes_otimizacao']:
        assert contagem(pool,tabela)==0


def test_valida_e_impede_publicar_ficticio(usuario_logado,pool):
    for corpo in [{'seed':True},{'seed':-1},{'perfil':'outro'},{'data':'31/10/2026'},{'data':123}]:
        assert usuario_logado.post('/api/jornadas/simular',json=corpo).status_code==400
    for corpo in [
        {'gravar':True,'simulacao_jornadas':{'seed':42}},
        {'gravar':'false'}, {'data':'inválida'}, {'simulacao_jornadas':[]},
    ]:
        assert usuario_logado.post('/api/escalas/otimizar',json=corpo).status_code==400
    assert contagem(pool,'jornadas')==0
    assert contagem(pool,'escalas')==0


def test_real_previa_nao_grava_e_publicacao_usa_somente_data(usuario_logado,pool):
    jornadas_reais(pool)
    r=usuario_logado.post('/api/escalas/otimizar',json={'data':DIA,'limite_voos':1,'gravar':False})
    assert r.status_code==200,r.get_json()
    assert r.get_json()['total_alocacoes']==5
    assert contagem(pool,'escalas')==0
    with pool.app_context(),transacao() as conn:
        assert conn.execute('SELECT SUM(horas_acumuladas) AS n FROM jornadas WHERE periodo=%s',(DIA,)).fetchone()['n']==100
    r=usuario_logado.post('/api/escalas/otimizar',json={'data':DIA,'limite_voos':1,'gravar':True})
    assert r.status_code==200,r.get_json()
    assert r.get_json()['escalas_gravadas']==5
    with pool.app_context(),transacao() as conn:
        assert conn.execute('SELECT SUM(horas_acumuladas) AS n FROM jornadas WHERE periodo=%s',(DIA,)).fetchone()['n']==107.5
        assert conn.execute('SELECT SUM(horas_acumuladas) AS n FROM jornadas WHERE periodo=%s',(ANTERIOR,)).fetchone()['n']==525


def test_sem_jornada_da_data_nao_usa_historico(usuario_logado,pool):
    jornadas_reais(pool)
    r=usuario_logado.post('/api/escalas/otimizar',json={'data':'2026-10-20','limite_voos':1})
    assert r.status_code==400
    assert 'Nenhuma jornada' in r.get_json()['erro']


def test_publicacao_repetida_nao_soma_horas_outras_datas(pool):
    jornadas_reais(pool)
    solucao=SimpleNamespace(alocacoes=[SimpleNamespace(tripulante_id='T000',voo_id='V1',cargo='Comandante',rota='GRU → MAO',duracao_horas=1.5)])
    with pool.app_context():
        assert _gravar_escalas(solucao,DIA,None)==(1,0)
        assert _gravar_escalas(solucao,DIA,None)==(0,1)
        with transacao() as conn:
            assert conn.execute('SELECT horas_acumuladas FROM jornadas WHERE tripulante_id=%s AND periodo=%s',('T000',DIA)).fetchone()['horas_acumuladas']==3.5
            assert conn.execute('SELECT horas_acumuladas FROM jornadas WHERE tripulante_id=%s AND periodo=%s',('T000',ANTERIOR)).fetchone()['horas_acumuladas']==10.5


def test_falha_na_publicacao_desfaz_todas_alteracoes(pool):
    jornadas_reais(pool)
    with pool.app_context():
        with transacao() as conn:
            conn.execute('UPDATE jornadas SET horas_acumuladas=%s WHERE tripulante_id=%s AND periodo=%s',(10.9,'T001',DIA))
        alocacoes=[SimpleNamespace(tripulante_id=tid,voo_id='V1',cargo='Comandante',rota='GRU → MAO',duracao_horas=1.5) for tid in ['T000','T001']]
        with pytest.raises(RuntimeError,match='excederia'):
            _gravar_escalas(SimpleNamespace(alocacoes=alocacoes),DIA,None)
        with transacao() as conn:
            assert conn.execute('SELECT COUNT(*) AS n FROM escalas').fetchone()['n']==0
            assert conn.execute('SELECT horas_acumuladas FROM jornadas WHERE tripulante_id=%s AND periodo=%s',('T000',DIA)).fetchone()['horas_acumuladas']==2
