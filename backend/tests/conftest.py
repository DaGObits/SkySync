"""Fixtures compartilhadas dos testes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permite rodar `pytest` da raiz do projeto sem instalar o pacote.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app import create_app  # noqa: E402
import db as db_module  # noqa: E402


@pytest.fixture
def app():
    aplicacao = create_app("testing")
    with aplicacao.app_context():
        db_module.init_db()
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
    cliente = client
    cliente.post("/api/auth/login", json={"email": "marina@skysync.aero", "senha": "Senha123"})
    return cliente


@pytest.fixture
def tripulante_factory():
    from models import Tripulante

    def _criar(tid="t1", nome="Rafael Nunes", horas=4.0, limite=11.0, **kwargs):
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

    def _criar(vid="v1", codigo="TAM-3482", duracao=3.0, noturno=False, **kwargs):
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
