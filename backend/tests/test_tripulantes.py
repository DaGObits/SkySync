"""Testes do endpoint de tripulacao.

Usam a fixture `base_de_tripulantes` (8 registros de amostra) em vez do arquivo
real de 900 linhas: uma suite automatizada nao deve depender de um arquivo que
esta fora do repositorio.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Protecao
# ---------------------------------------------------------------------------
def test_listagem_exige_login(client):
    assert client.get("/api/tripulantes").status_code == 401


def test_resumo_exige_login(client):
    assert client.get("/api/tripulantes/resumo").status_code == 401


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------
def test_lista_todos(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes").get_json()
    assert corpo["total"] == 8
    assert corpo["retornados"] == 8
    assert len(corpo["tripulantes"]) == 8


def test_tripulante_tem_nome_completo(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes").get_json()
    primeiro = corpo["tripulantes"][0]
    assert primeiro["nome_completo"] == f"{primeiro['nome']} {primeiro['sobrenome']}"


def test_filtro_por_base(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes?base=GRU").get_json()
    assert corpo["total"] == 5
    assert all(t["base"] == "GRU" for t in corpo["tripulantes"])


def test_filtro_por_cargo(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes?cargo=Copiloto").get_json()
    assert corpo["total"] == 2
    assert all(t["cargo"] == "Copiloto" for t in corpo["tripulantes"])


def test_filtro_por_status(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes?status=Reserva").get_json()
    assert corpo["total"] == 2
    assert all(t["status"] == "Reserva" for t in corpo["tripulantes"])


def test_filtros_combinados(usuario_logado, base_de_tripulantes):
    """Comandante disponivel em GRU: so o 0001."""
    corpo = usuario_logado.get(
        "/api/tripulantes?base=GRU&cargo=Comandante&status=Disponível"
    ).get_json()
    assert corpo["total"] == 1
    assert corpo["tripulantes"][0]["id"] == "0001"


def test_limite_e_respeitado(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes?limite=3").get_json()
    assert corpo["total"] == 8, "o total ignora o limite"
    assert corpo["retornados"] == 3, "o limite corta o que é devolvido"


def test_cargo_invalido_devolve_400(usuario_logado, base_de_tripulantes):
    resposta = usuario_logado.get("/api/tripulantes?cargo=Comissário-chefe")
    assert resposta.status_code == 400


def test_limite_invalido_devolve_400(usuario_logado, base_de_tripulantes):
    resposta = usuario_logado.get("/api/tripulantes?limite=abc")
    assert resposta.status_code == 400


def test_base_inexistente_devolve_lista_vazia(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes?base=XXX").get_json()
    assert corpo["total"] == 0
    assert corpo["tripulantes"] == []


# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------
def test_resumo_conta_por_cargo(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes/resumo").get_json()
    assert corpo["total"] == 8
    assert corpo["por_cargo"]["Comandante"] == 3
    assert corpo["por_cargo"]["Copiloto"] == 2
    assert corpo["por_cargo"]["Comissário"] == 3


def test_resumo_conta_por_status(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes/resumo").get_json()
    assert corpo["por_status"]["Disponível"] == 6
    assert corpo["por_status"]["Reserva"] == 2


def test_resumo_conta_por_base(usuario_logado, base_de_tripulantes):
    corpo = usuario_logado.get("/api/tripulantes/resumo").get_json()
    assert corpo["por_base"]["GRU"] == 5
    assert corpo["por_base"]["CWB"] == 1
    assert corpo["por_base"]["SSA"] == 1
    assert corpo["por_base"]["NAT"] == 1


# ---------------------------------------------------------------------------
# Integracao com o motor
# ---------------------------------------------------------------------------
def test_tripulantes_da_api_alimentam_o_solver(usuario_logado, base_de_tripulantes):
    """O pool vem da tabela; o solver aceita o que a API devolve.

    Este e o teste que prova a integracao: os cargos e bases gravados sao os
    mesmos que a composicao do motor exige.
    """
    from models import Tripulante, Voo
    from optimizer.restricoes import COMPOSICAO_PADRAO
    from optimizer.solver import otimizar

    corpo = usuario_logado.get("/api/tripulantes").get_json()

    pool = [
        Tripulante(
            id=t["id"],
            nome=t["nome_completo"],
            cargo=t["cargo"],
            base=t["base"],
            horas_acumuladas=1.0,
            limite_horas=11.0,
        )
        for t in corpo["tripulantes"]
        if t["status"] == "Disponível"
    ]

    # Um voo exige 1 CM + 1 CP + 3 CC. A amostra so tem 2 comissarios
    # disponiveis, entao o teste confirma que o motor DETECTA a falta em vez de
    # montar uma escala incompleta.
    from optimizer.solver import OtimizacaoInviavel

    voos = [Voo(id="v1", codigo="TAM-1", origem="GRU", destino="VCP",
                duracao_horas=2.0, pouso_noturno=False, prioridade=1)]

    try:
        solucao = otimizar("GRU", pool, voos, limite_horas=11.0)
    except OtimizacaoInviavel as err:
        causas = " ".join(err.diagnostico["causas"])
        assert "comiss" in causas.lower()
    else:
        # Se alcancar a amostra completa, a composicao tem de bater.
        por_cargo = {}
        for a in solucao.alocacoes:
            por_cargo[a.cargo] = por_cargo.get(a.cargo, 0) + 1
        assert por_cargo == COMPOSICAO_PADRAO
