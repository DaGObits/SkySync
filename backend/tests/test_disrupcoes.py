"""Disrupções persistem e aparecem mesmo sem nenhuma escala publicada."""


def test_exige_sessao(client):
    assert client.get('/api/disrupcoes').status_code == 401
    assert client.post('/api/disrupcoes', json={}).status_code == 401


def test_lista_vazia(usuario_logado):
    resposta = usuario_logado.get('/api/disrupcoes')
    assert resposta.status_code == 200
    assert resposta.get_json() == {'disrupcoes': [], 'total': 0, 'retornados': 0}


def test_registro_persistido_sem_escala(usuario_logado):
    payload = {'voo': 'tam-123', 'descricao': 'Manutenção não programada', 'risco': 'alto', 'rota': 'GRU → MAO'}
    resposta = usuario_logado.post('/api/disrupcoes', json=payload)
    assert resposta.status_code == 201
    dado = resposta.get_json()['disrupcao']
    assert dado['voo'] == 'TAM-123'
    assert dado['descricao'] == payload['descricao']
    assert dado['bloqueado'] is False
    assert usuario_logado.get('/api/escalas').get_json()['escalas'] == []
    lista = usuario_logado.get('/api/disrupcoes').get_json()
    assert lista['total'] == 1
    assert lista['disrupcoes'][0]['id'] == dado['id']
    assert usuario_logado.get('/api/disrupcoes?risco=baixo').get_json()['disrupcoes'] == []


def test_valida_entrada(usuario_logado):
    for payload in [[], {}, {'voo': [], 'descricao': 'Motivo', 'risco': 'alto'}, {'voo': 'A', 'descricao': 'ok', 'risco': 'inventado'}, {'voo': 'A'*31, 'descricao': 'Motivo válido', 'risco': 'alto'}]:
        assert usuario_logado.post('/api/disrupcoes', json=payload).status_code == 400
    assert usuario_logado.get('/api/disrupcoes?risco=outro').status_code == 400
    assert usuario_logado.get('/api/disrupcoes?limite=abc').status_code == 400


def test_ordem_e_limite(usuario_logado):
    for voo in ['PRIMEIRO', 'SEGUNDO']:
        assert usuario_logado.post('/api/disrupcoes', json={'voo': voo, 'descricao': 'Atraso operacional', 'risco': 'medio'}).status_code == 201
    lista = usuario_logado.get('/api/disrupcoes?limite=1').get_json()
    assert lista['total'] == 2
    assert lista['retornados'] == 1
    assert lista['disrupcoes'][0]['voo'] == 'SEGUNDO'
