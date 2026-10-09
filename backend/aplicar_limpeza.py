from pathlib import Path

c = Path("tests/conftest.py")
texto = c.read_text(encoding="utf-8")

antigo = '''@pytest.fixture
def app():
    """Aplicação de teste com o esquema já aplicado.

    O `init_db` roda a cada teste: como o arquivo é o mesmo, o esquema já existe
    e o `CREATE TABLE IF NOT EXISTS` apenas confirma. Idempotente de propósito.
    """
    aplicacao = create_app("testing")
    with aplicacao.app_context():
        db_module.init_db()
    yield aplicacao'''

novo = '''@pytest.fixture
def app():
    """Aplicação de teste com o esquema aplicado e os dados ZERADOS.

    O `init_db` roda a cada teste, mas ele só cria tabela que não existe — nao
    apaga dados. Sem a limpeza abaixo, um usuario criado num teste sobrevive
    para o proximo, e o segundo registro do mesmo e-mail devolve 409.
    """
    aplicacao = create_app("testing")
    with aplicacao.app_context():
        db_module.init_db()
        _limpar_tabelas()
    yield aplicacao


def _limpar_tabelas():
    """Apaga os dados de todas as tabelas, preservando o esquema.

    Roda DEPOIS do init_db e antes de cada teste, para que cada um comece do
    zero sem depender da ordem de execucao.
    """
    from db import transacao

    tabelas = [
        "execucoes_otimizacao",
        "historico_escalas",
        "disrupcoes",
        "cenarios",
        "usuarios",
    ]
    with transacao() as conexao:
        for tabela in tabelas:
            conexao.execute(f"DELETE FROM {tabela}")'''

if antigo in texto:
    c.write_text(texto.replace(antigo, novo), encoding="utf-8")
    print("conftest.py: limpeza por teste adicionada.")
elif "_limpar_tabelas" in texto:
    print("conftest.py: ja tinha limpeza.")
else:
    print("conftest.py: PADRAO NAO ENCONTRADO — me avisa.")
