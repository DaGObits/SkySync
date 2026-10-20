import copy
from datetime import datetime, timedelta

import pytest
from db import transacao
from operacao import novo_estado, avancar_estado, ler_estado, executar_passo, situacao

CARGOS=['Comandante','Copiloto','Comissário','Comissário','Comissário']


def grupo(prefixo,base,reserva=False):
    return [{'id':prefixo+str(i),'nome':prefixo+str(i),'cargo':cargo,'base':base,
             'status':'Reserva' if reserva else 'Disponível','horas_acumuladas':0,
             'limite_horas':11,'descanso_ok':True,'aclimatado':True} for i,cargo in enumerate(CARGOS)]


def malha():
    return [dict(id='A',codigo='TEST-A',origem='GRU',destino='MAO',partida='00:01',duracao_horas=1,pouso_noturno=False),
            dict(id='B',codigo='TEST-B',origem='MAO',destino='GRU',partida='01:40',duracao_horas=1,pouso_noturno=False)]


@pytest.fixture
def atraso(monkeypatch):
    monkeypatch.setattr('operacao.atraso_simulado',lambda chave:60 if chave=='A' else 0)


def test_voa_acumula_e_so_muda_local_no_pouso(atraso):
    estado=novo_estado(grupo('G','GRU')+grupo('R','MAO',True),malha())
    avancar_estado(estado,61)
    assert all(estado['tripulantes']['G'+str(i)]['horas']==60 for i in range(5))
    assert estado['tripulantes']['G0']['local']=='GRU'
    assert situacao(estado['tripulantes']['G0'],estado)==('Em voo','GRU → MAO')
    assert estado['tripulantes']['R0']['horas']==0
    avancar_estado(estado,121)
    assert estado['tripulantes']['G0']['local']=='MAO'
    assert estado['tripulantes']['G0']['horas']==120


def test_remaneja_somente_substitutos_aptos_no_aeroporto(atraso):
    estado=novo_estado(grupo('G','GRU')+grupo('R','MAO',True),malha())
    assert estado['voos']['B']['plano']==['G'+str(i) for i in range(5)]
    avancar_estado(estado,100)
    assert estado['voos']['B']['status']=='Em voo'
    assert set(estado['voos']['B']['alocados'])=={'R'+str(i) for i in range(5)}
    assert len(estado['mudancas'])==5
    assert all(m['local']=='MAO' and m['motivo']=='Ainda está em outro voo' for m in estado['mudancas'])
    assert len({p['voo'] for p in estado['tripulantes'].values() if p['voo']})==2
    avancar_estado(estado,200)
    assert estado['rodando'] is True
    assert estado['concluidos_anteriores'] == 2
    assert estado['tripulantes']['R0']['local']=='GRU'
    assert estado['tripulantes']['R0']['horas']==60


def test_nao_teleporta_reserva_de_outra_base(atraso):
    estado=novo_estado(grupo('G','GRU')+grupo('R','BSB',True),malha())
    avancar_estado(estado,100)
    assert estado['voos']['B']['status']=='Aguardando tripulação'
    assert estado['voos']['B']['alocados']==[]
    assert estado['tripulantes']['R0']['local']=='BSB'
    assert estado['tripulantes']['R0']['horas']==0
    assert estado['mudancas']==[]


def test_preserva_plano_quando_nao_ha_motivo_para_trocar(monkeypatch):
    monkeypatch.setattr('operacao.atraso_simulado',lambda _:0)
    estado=novo_estado(grupo('G','GRU')+grupo('R','MAO',True),malha())
    avancar_estado(estado,200)
    assert estado['mudancas']==[]
    assert estado['tripulantes']['G0']['local']=='GRU'
    assert estado['tripulantes']['G0']['horas']==120


def test_substitui_ao_exceder_limite_e_nao_usa_descansando(atraso):
    pessoas=grupo('G','GRU')+grupo('R','GRU',True)
    estado=novo_estado(pessoas,malha()[:1])
    for i in range(5):
        estado['tripulantes']['G'+str(i)]['horas']=600
    avancar_estado(estado,1)
    assert set(estado['voos']['A']['alocados'])=={'R'+str(i) for i in range(5)}
    assert all('excede' in m['motivo'] for m in estado['mudancas'])
    outro=novo_estado(pessoas,malha()[:1])
    for p in outro['tripulantes'].values():
        p['descanso_ok']=False;p['descanso_ate']=720
    avancar_estado(outro,10)
    assert outro['voos']['A']['status']=='Aguardando tripulação'
    assert all(p['horas']==0 for p in outro['tripulantes'].values())


def test_pausa_nao_avanca(atraso):
    estado=novo_estado(grupo('G','GRU'),malha())
    estado['rodando']=False
    antes=copy.deepcopy(estado)
    assert avancar_estado(estado,1000)==antes


@pytest.fixture
def dados_operacao(app,atraso):
    with app.app_context(),transacao() as conn:
        for p in grupo('G','GRU')+grupo('R','MAO',True):
            conn.execute('INSERT INTO tripulantes (id,nome,cargo,base,status) VALUES (%s,%s,%s,%s,%s)',
                         tuple(p[k] for k in ['id','nome','cargo','base','status']))
        for v in malha():
            conn.execute('INSERT INTO voos (id,codigo,origem,destino,partida,duracao_horas,pouso_noturno) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                         tuple(v[k] for k in ['id','codigo','origem','destino','partida','duracao_horas','pouso_noturno']))
    return app


def test_api_sessao_e_inicio_sem_dados(client,usuario_logado):
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/operacao').status_code==401
    assert client.post('/api/operacao/iniciar').status_code==401
    client.post('/api/auth/login',json={'email':'marina@skysync.aero','senha':'Senha123'})
    assert client.post('/api/operacao/iniciar').status_code==400


def test_api_persistencia_reinicio_pausa_e_nao_altera_jornadas(usuario_logado,dados_operacao):
    assert usuario_logado.get('/api/operacao').get_json()['iniciada'] is False
    r=usuario_logado.post('/api/operacao/iniciar')
    assert r.status_code==200,r.get_json()
    assert r.get_json()['tripulantes']==10
    with dados_operacao.app_context():
        with transacao() as conn:
            inicio=conn.execute('SELECT atualizado_em FROM operacao_simulada').fetchone()['atualizado_em']
        agora=datetime.fromisoformat(inicio)+timedelta(seconds=10)
        executar_passo(agora)
        antes=ler_estado()
        executar_passo(agora)
        assert ler_estado()==antes
        with transacao() as conn:
            assert conn.execute('SELECT COUNT(*) AS n FROM jornadas').fetchone()['n']==0
            assert conn.execute('SELECT COUNT(*) AS n FROM escalas').fetchone()['n']==0
    itens=usuario_logado.get('/api/tripulantes').get_json()['tripulantes']
    assert any(p['situacao_atual']=='Em voo' and '→' in p['local_atual'] for p in itens)
    assert usuario_logado.post('/api/operacao/pausar').get_json()['rodando'] is False
    with dados_operacao.app_context():
        antes=ler_estado();executar_passo(agora+timedelta(hours=2));assert ler_estado()==antes


def test_novo_tripulante_entra_e_indisponivel_e_remanejado(usuario_logado,dados_operacao):
    usuario_logado.post('/api/operacao/iniciar')
    with dados_operacao.app_context():
        with transacao() as conn:
            conn.execute("UPDATE tripulantes SET status='Indisponível' WHERE id='G0'")
            conn.execute("INSERT INTO tripulantes (id,nome,cargo,base,status) VALUES ('NOVO','Nova reserva','Comandante','GRU','Reserva')")
            inicio=conn.execute('SELECT atualizado_em FROM operacao_simulada').fetchone()['atualizado_em']
        executar_passo(datetime.fromisoformat(inicio)+timedelta(seconds=5))
        estado=ler_estado()
        assert estado['tripulantes']['G0']['habilitado'] is False
        assert estado['tripulantes']['NOVO']['voo']=='A'
        assert estado['mudancas'][0]['entrou']=='Nova reserva'
        assert estado['mudancas'][0]['motivo']=='Indisponível no cadastro'


def test_proximo_dia_preserva_posicao_e_reinicia_jornada_apos_repouso(atraso):
    estado=novo_estado(grupo('G','GRU')+grupo('R','MAO',True),malha())
    avancar_estado(estado,200)
    assert estado['tripulantes']['R0']['base']=='MAO'
    assert estado['tripulantes']['R0']['local']=='GRU'
    assert estado['tripulantes']['R0']['horas']==60
    avancar_estado(estado,1441)
    assert set(estado['voos']['A@1']['alocados'])=={'R'+str(i) for i in range(5)}
    assert estado['tripulantes']['R0']['horas']==0
    assert estado['tripulantes']['G0']['local']=='MAO'
    assert estado['rodando'] is True
