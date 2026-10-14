"""Testes do motor de otimização.

Não tocam em Flask nem em banco — é o ganho de manter o solver isolado.
Cada teste corresponde a uma afirmação defensável na banca.
"""
from __future__ import annotations

import pytest

from optimizer.restricoes import COMPOSICAO_PADRAO, catalogo_restricoes
from optimizer.solver import OtimizacaoInviavel, minutos, otimizar


def pool(tripulante_factory, voos: int, descanso_ok=True, aclimatado=True, horas=2.0):
    """Monta um pool com a composição exata para N voos.

    Com 1 voo: 1 comandante, 1 copiloto, 3 comissários.
    """
    tripulantes = []
    for i in range(voos * COMPOSICAO_PADRAO["Comandante"]):
        tripulantes.append(
            tripulante_factory(f"cm{i}", nome=f"Comandante {i}", cargo="Comandante",
                               horas=horas, descanso_ok=descanso_ok, aclimatado=aclimatado)
        )
    for i in range(voos * COMPOSICAO_PADRAO["Copiloto"]):
        tripulantes.append(
            tripulante_factory(f"cp{i}", nome=f"Copiloto {i}", cargo="Copiloto",
                               horas=horas, descanso_ok=descanso_ok, aclimatado=aclimatado)
        )
    for i in range(voos * COMPOSICAO_PADRAO["Comissário"]):
        tripulantes.append(
            tripulante_factory(f"cc{i}", nome=f"Comissário {i}", cargo="Comissário",
                               horas=horas, descanso_ok=descanso_ok, aclimatado=aclimatado)
        )
    return tripulantes


# ---------------------------------------------------------------------------
# Composição por cargo — a restrição central
# ---------------------------------------------------------------------------
def test_cada_voo_recebe_a_composicao_completa(tripulante_factory, voo_factory):
    """Cinco lugares por voo: 1 CM, 1 CP e 3 CC. É a RBAC 117.035."""
    tripulantes = pool(tripulante_factory, voos=1)
    voos = [voo_factory("v1", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.status in {"OPTIMAL", "FEASIBLE"}
    assert len(solucao.alocacoes) == 5, "um voo precisa de exatamente 5 tripulantes"

    por_cargo: dict[str, int] = {}
    for a in solucao.alocacoes:
        por_cargo[a.cargo] = por_cargo.get(a.cargo, 0) + 1

    assert por_cargo == {"Comandante": 1, "Copiloto": 1, "Comissário": 3}


def test_sem_comandante_o_cenario_e_inviavel(tripulante_factory, voo_factory):
    """Pool sem comandante não tripula nada — e o diagnóstico diz por quê."""
    tripulantes = pool(tripulante_factory, voos=1)
    tripulantes = [t for t in tripulantes if t.cargo != "Comandante"]
    voos = [voo_factory("v1", duracao=1.0)]

    with pytest.raises(OtimizacaoInviavel) as exc:
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    causas = " ".join(exc.value.diagnostico["causas"])
    assert "comandante" in causas.lower()


def test_tres_voos_exigem_quinze_alocacoes(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=3)
    voos = [voo_factory(f"v{i}", duracao=1.0) for i in range(3)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.total_alocacoes == 15
    assert len(solucao.nao_alocados) == 0


# ---------------------------------------------------------------------------
# Um tripulante por voo
# ---------------------------------------------------------------------------
def test_tripulante_nao_e_designado_a_dois_voos(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=2)
    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    designados = [a.tripulante_id for a in solucao.alocacoes]
    assert len(designados) == len(set(designados)), "ninguém pode estar em dois voos"


# ---------------------------------------------------------------------------
# Limite de jornada
# ---------------------------------------------------------------------------
def test_respeita_teto_de_jornada(tripulante_factory, voo_factory):
    """t1 já está no teto: não pode receber voo nenhum."""
    tripulantes = pool(tripulante_factory, voos=1, horas=10.0)
    voos = [voo_factory("v1", duracao=3.0)]

    with pytest.raises(OtimizacaoInviavel):
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)


def test_par_inviavel_nao_e_criado_para_voo_longo(tripulante_factory, voo_factory):
    """O filtro de domínio descarta o par (tripulante, voo) quando o voo é
    maior que a jornada restante."""
    tripulantes = pool(tripulante_factory, voos=1, horas=9.0)
    voos = [voo_factory("v1", duracao=3.0)]

    with pytest.raises(OtimizacaoInviavel):
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)


# ---------------------------------------------------------------------------
# Descanso e aclimatação
# ---------------------------------------------------------------------------
def test_sem_descanso_nao_recebe_voo(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=1, descanso_ok=False)
    voos = [voo_factory("v1", duracao=1.0)]

    with pytest.raises(OtimizacaoInviavel):
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)


def test_sem_descanso_parcial_ainda_tripula(tripulante_factory, voo_factory):
    """Se há reserva descansada, o voo sai — com os disponíveis."""
    tripulantes = pool(tripulante_factory, voos=2)
    for i, t in enumerate(tripulantes):
        if i % 2 == 0:
            t.descanso_ok = False
    voos = [voo_factory("v1", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert len(solucao.alocacoes) == 5
    for a in solucao.alocacoes:
        escolhido = next(t for t in tripulantes if t.id == a.tripulante_id)
        assert escolhido.descanso_ok, "escalou alguém sem descanso"


def test_nao_aclimatado_nao_recebe_pouso_noturno(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=1, aclimatado=False)
    voos = [voo_factory("v1", duracao=1.0, noturno=True)]

    with pytest.raises(OtimizacaoInviavel):
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)


def test_nao_aclimatado_recebe_voo_diurno(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=1, aclimatado=False)
    voos = [voo_factory("v1", duracao=1.0, noturno=False)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)
    assert len(solucao.alocacoes) == 5


# ---------------------------------------------------------------------------
# Objetivo e métricas
# ---------------------------------------------------------------------------
def test_objetivo_distribui_a_carga(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=2, horas=0.0)
    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    designados = {a.tripulante_id for a in solucao.alocacoes}
    assert len(designados) == 10


def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):
    """A conformidade cai quando parte do pool está acima do teto.

    O pool é o DOBRO do necessário, e o bloqueio é UM POR CARGO: com o pool
    exato, bloquear 3 deixava alguns cargos sem ninguém elegível e o cenário
    virava INFEASIBLE — o que testaria outra coisa.
    """
    tripulantes = pool(tripulante_factory, voos=3, horas=0.0)

    cargos_bloqueados = set()
    for t in tripulantes:
        if t.cargo not in cargos_bloqueados:
            t.horas_acumuladas = 11.5
            cargos_bloqueados.add(t.cargo)

    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.tripulantes_bloqueados == 3, "um bloqueado por cargo"
    assert 0 <= solucao.conformidade < 100
    assert solucao.total_alocacoes == 10


def test_solucao_reporta_metricas_para_o_tcc(tripulante_factory, voo_factory):
    tripulantes = pool(tripulante_factory, voos=2)
    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=2.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.wall_time_seconds >= 0
    assert solucao.variaveis_criadas > 0
    assert solucao.total_voos == 2
    assert solucao.total_alocacoes == 10
    assert solucao.composicao_aplicada == COMPOSICAO_PADRAO


def test_conversao_de_horas_para_minutos():
    assert minutos(11.5) == 690
    assert minutos(0.5) == 30
    assert minutos(11.0) == 660


def test_catalogo_de_restricoes_documentado():
    nomes = set()
    for item in catalogo_restricoes():
        assert item["nome"]
        assert item["referencia"]
        assert item["descricao"]
        nomes.add(item["nome"])

    assert nomes == {
        "descanso_minimo",
        "aclimatacao_fuso",
        "limite_jornada",
        "composicao_cargo",
        "um_voo_por_tripulante",
    }


def test_cenario_realista_com_gerador(app):
    """Integração com o gerador: 30 voos devem resolver.

    O gerador lê a malha do BANCO (`dados.malha`), então este teste precisa do
    app_context e da tabela `aeroportos` populada — a fixture `app` garante
    isso, e a `banco_de_teste` carrega a malha uma vez por sessão.
    """
    from dados.gerador import gerar_cenario
    from dados.malha import bases_por_regiao

    # O gerador le a malha do BANCO, entao precisa de app_context ativo:
    # `dados.malha` consulta a tabela `aeroportos`. A fixture `app` abre o
    # contexto, mas so dentro do `with`.
    with app.app_context():
        cenario = gerar_cenario(voos=30, seed=7)

        solucao = otimizar(
            "GRU",
            cenario.tripulantes,
            cenario.voos,
            limite_horas=11.0,
            max_time_seconds=20,
            raio_bases=1,
            bases_por_regiao=bases_por_regiao(),
        )

    assert solucao.status in {"OPTIMAL", "FEASIBLE"}
    assert solucao.total_voos == 30
    assert solucao.total_alocacoes > 0
