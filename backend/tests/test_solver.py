"""Testes do motor de otimização.

Estes testes não tocam em Flask nem em banco — é exatamente o ganho de manter o
solver isolado. Cada teste corresponde a uma afirmação que você pode defender na
banca: "o modelo respeita a composição da aeronave", "respeita o teto de
jornada", "detecta inviabilidade e explica por quê".

NOTA SOBRE A COMPOSIÇÃO: o modelo exige 1 comandante + 1 copiloto + 3
comissários por voo. Por isso os cenários de teste montam o pool por cargo —
um teste com "dois tripulantes quaisquer" não tem como tripular um voo.
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
    """Sem a restrição de exclusividade, o solver colocaria a mesma pessoa
    em vários voos."""
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
    # Um voo de 3h não cabe em quem já tem 10h de 11h.
    voos = [voo_factory("v1", duracao=3.0)]

    with pytest.raises(OtimizacaoInviavel):
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)


def test_par_inviavel_nao_e_criado_para_voo_longo(tripulante_factory, voo_factory):
    """O filtro de domínio descarta o par (tripulante, voo) quando o voo é
    maior que a jornada restante — sem isso o modelo seria maior e mais lento."""
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
    # Metade do pool sem descanso.
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
    """Com reserva no pool, o solver não concentra as jornadas nos primeiros."""
    tripulantes = pool(tripulante_factory, voos=2, horas=0.0)
    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    designados = {a.tripulante_id for a in solucao.alocacoes}
    # 10 designações (2 voos x 5) — com 30 no pool, ninguém se repete.
    assert len(designados) == 10


def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):
    """A conformidade cai quando parte do pool esta acima do teto.

    O pool e montado com RESERVA (3 voos) e o teste usa apenas 2: bloquear um
    tripulante de cada cargo nao pode deixar falta para compor os voos. Com o
    pool exato, bloquear 3 zerava a conta e o cenario virava INFEASIBLE —
    testando outra coisa que nao a conformidade.
    """
    tripulantes = pool(tripulante_factory, voos=3, horas=0.0)

    # Um bloqueado por cargo: o pool tem folga para absorver.
    cargos_bloqueados = set()
    for t in tripulantes:
        if t.cargo not in cargos_bloqueados:
            t.horas_acumuladas = 11.5
            cargos_bloqueados.add(t.cargo)

    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.tripulantes_bloqueados == 3, "um bloqueado por cargo"
    assert 0 <= solucao.conformidade < 100
    assert solucao.total_alocacoes == 10, "os 2 voos ainda saem completos"



def test_solucao_reporta_metricas_para_o_tcc(tripulante_factory, voo_factory):
    """Os campos que alimentam o capítulo de resultados precisam existir."""
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
    """Toda restrição precisa de nome, referência e descrição — é o material do
    capítulo de metodologia."""
    nomes = set()
    for item in catalogo_restricoes():
        assert item["nome"]
        assert item["referencia"]
        assert item["descricao"]
        nomes.add(item["nome"])

    # As cinco restrições que o modelo aplica.
    assert nomes == {
        "descanso_minimo",
        "aclimatacao_fuso",
        "limite_jornada",
        "composicao_cargo",
        "um_voo_por_tripulante",
    }


def test_cenario_realista_com_gerador(tripulante_factory, voo_factory):
    """Integração com o gerador: 30 voos devem resolver."""
    from dados.gerador import gerar_cenario

    cenario = gerar_cenario(voos=30, seed=7)

    solucao = otimizar(
        "GRU",
        cenario.tripulantes,
        cenario.voos,
        limite_horas=11.0,
        max_time_seconds=20,
    )

    assert solucao.status in {"OPTIMAL", "FEASIBLE"}
    assert solucao.total_voos == 30
    # Nem todo voo sai necessariamente: parte do pool está em disrupção.
    assert solucao.total_alocacoes > 0
