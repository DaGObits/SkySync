"""Fixtures compartilhadas dos testes.

TRÊS DETALHES QUE QUEBRAM SE IGNORADOS:

1. **Banco em ARQUIVO, não em memória.** No SQLite, cada `connect(":memory:")`
   abre um banco novo e vazio, e um banco em memória é destruído quando a
   última conexão fecha. O `init_db` roda num `app_context` que se encerra
   antes da requisição de teste, então o banco desaparecia.

2. **Limpeza entre testes.** O `init_db` só cria tabela que não existe — não
   apaga dados. Sem a limpeza, um usuário criado num teste sobrevive para o
   próximo, e o segundo registro do mesmo e-mail devolve 409.

3. **A malha NÃO é limpa.** `aeroportos` é dado de referência (os 97
   aeroportos regulares), não dado de teste. O `dados/malha.py` lê dela para
   gerar cenários e para o filtro por região do solver — apagá-la deixaria o
   sistema sem malha.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app import create_app  # noqa: E402
import db as db_module  # noqa: E402

CAMINHO_BANCO = Path(os.getenv("SKYSYNC_TEST_DB", str(RAIZ / ".teste_skysync.db")))

#: Tabelas limpas antes de cada teste. A ordem respeita as chaves estrangeiras.
#: `aeroportos` NÃO está aqui: é dado de referência, e o `dados.malha` lê dela.
TABELAS = [
    "importacao_voos_eventos",
    "importacao_voos_estado",
    "execucoes_otimizacao",
    "historico_escalas",
    "disrupcoes",
    "escalas",
    "jornadas",
    "voos",
    "cenarios",
    "tripulantes",
    "usuarios",
]


@pytest.fixture(scope="session", autouse=True)
def banco_de_teste():
    """Prepara um banco limpo, carrega a malha e remove tudo no fim."""
    for sufixo in ("", "-wal", "-shm"):
        p = Path(str(CAMINHO_BANCO) + sufixo)
        if p.exists():
            p.unlink()
    os.environ["SKYSYNC_TEST_DB"] = str(CAMINHO_BANCO)

    # A malha precisa existir: o gerador de cenários e o filtro por região do
    # solver leem dela. Carrega uma vez por sessão.
    aplicacao = create_app("testing")
    with aplicacao.app_context():
        db_module.init_db()
        from dados.malha import limpar_cache
        from dados.malha_seed import ARQUIVO_PADRAO, semear

        caminho = RAIZ / ARQUIVO_PADRAO
        if caminho.exists():
            with db_module.transacao() as conexao:
                semear(conexao, caminho)
            limpar_cache()

    yield CAMINHO_BANCO

    for sufixo in ("", "-wal", "-shm"):
        p = Path(str(CAMINHO_BANCO) + sufixo)
        if p.exists():
            p.unlink()


@pytest.fixture
def app():
    """Aplicação de teste com o esquema aplicado e os dados de teste ZERADOS."""
    aplicacao = create_app("testing")
    with aplicacao.app_context():
        db_module.init_db()
        with db_module.transacao() as conexao:
            for tabela in TABELAS:
                conexao.execute("DELETE FROM " + tabela)

        # O cache da malha guarda a lista por app_context; limpar aqui evita
        # que um teste veja dados de outro.
        from dados.malha import limpar_cache

        limpar_cache()
    yield aplicacao


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def usuario_logado(client):
    """Registra e autentica um usuário, devolvendo o cliente com sessão ativa."""
    client.post(
        "/api/auth/registrar",
        json={
            "nome": "Marina Costa",
            "email": "marina@skysync.aero",
            "senha": "Senha123",
            "cargo": "Coordenadora Operacional",
            "base": "GRU — Guarulhos",
        },
    )
    client.post("/api/auth/login", json={"email": "marina@skysync.aero", "senha": "Senha123"})
    return client


@pytest.fixture
def tripulante_factory():
    from models import Tripulante

    def _criar(tid="t1", nome="Rafael Nunes", horas=2.0, limite=11.0, **kwargs):
        return Tripulante(
            id=tid,
            nome=nome,
            cargo=kwargs.get("cargo", "Comandante"),
            base=kwargs.get("base", "GRU"),
            horas_acumuladas=horas,
            limite_horas=limite,
            descanso_ok=kwargs.get("descanso_ok", True),
            aclimatado=kwargs.get("aclimatado", True),
        )

    return _criar


@pytest.fixture
def voo_factory():
    from models import Voo

    def _criar(vid="v1", codigo="TAM-3482", duracao=1.0, noturno=False, **kwargs):
        return Voo(
            id=vid,
            codigo=codigo,
            origem=kwargs.get("origem", "GRU"),
            destino=kwargs.get("destino", "VCP"),
            duracao_horas=duracao,
            pouso_noturno=noturno,
            prioridade=kwargs.get("prioridade", 1),
        )

    return _criar


@pytest.fixture
def base_de_tripulantes(app, client):
    """Popula a tabela tripulantes com uma amostra pequena e diversa.

    Recebe `app` porque a fixture precisa de um app_context aberto: o
    `db.get_conexao()` lê `current_app.config`.
    """
    from db import transacao

    amostra = [
        ("0001", "Iara", "Ramos", "Comandante", "GRU", "Disponível"),
        ("0002", "Priscila", "Santos", "Comandante", "CWB", "Disponível"),
        ("0003", "Matheus", "Amaral", "Comandante", "GRU", "Reserva"),
        ("0101", "Ana", "Pinto", "Copiloto", "GRU", "Disponível"),
        ("0102", "Rodrigo", "Coelho", "Copiloto", "SSA", "Disponível"),
        ("0201", "Cecilia", "Guimarães", "Comissário", "GRU", "Disponível"),
        ("0202", "Alice", "Aguiar", "Comissário", "GRU", "Disponível"),
        ("0203", "Gustavo", "Souza", "Comissário", "NAT", "Reserva"),
    ]
    with app.app_context():
        with transacao() as conexao:
            for registro in amostra:
                conexao.execute(
                    "INSERT INTO tripulantes (id, nome, sobrenome, cargo, base, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    registro,
                )
    return amostra
