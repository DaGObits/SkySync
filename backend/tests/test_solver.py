"""Testes do motor de otimização.

Estes testes não tocam em Flask nem em banco — é exatamente o ganho de manter o
solver isolado. Cada teste corresponde a uma afirmação que você pode defender na
banca: "o modelo respeita o teto de jornada", "o modelo detecta inviabilidade".
"""
from __future__ import annotations

import pytest

from optimizer.restricoes import catalogo_restricoes
from optimizer.solver import OtimizacaoInviavel, minutos, otimizar


def test_aloca_todos_os_voos_quando_ha_capacidade(tripulante_factory, voo_factory):
    tripulantes = [tripulante_factory("t1", horas=4.0), tripulante_factory("t2", horas=2.0)]
    voos = [
        voo_factory("v1", "TAM-3482", duracao=3.0),
        voo_factory("v2", "GLO-1207", duracao=2.0),
    ]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.status in {"OPTIMAL", "FEASIBLE"}
    assert len(solucao.alocacoes) == 2
    assert solucao.nao_alocados == []
    # Cada voo aparece exatamente uma vez.
    voos_alocados = [a.voo_id for a in solucao.alocacoes]
    assert sorted(voos_alocados) == ["v1", "v2"]


def test_respeita_teto_de_jornada(tripulante_factory, voo_factory):
    """t1 já tem 10h de 11h: não pode receber um voo de 3h."""
    tripulantes = [tripulante_factory("t1", horas=10.0)]
    voos = [voo_factory("v1", duracao=3.0)]

    with pytest.raises(OtimizacaoInviavel) as exc:
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    diagnostico = exc.value.diagnostico
    assert diagnostico["horas_disponiveis"] < diagnostico["horas_demandadas"]


def test_tripulante_sem_descanso_nao_recebe_voo(tripulante_factory, voo_factory):
    tripulantes = [
        tripulante_factory("t1", descanso_ok=False),
        tripulante_factory("t2", horas=0.0),
    ]
    voos = [voo_factory("v1", duracao=2.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    alocado = solucao.alocacoes[0].tripulante_id
    assert alocado == "t2", "tripulante sem descanso não pode ser escalado"
    assert solucao.tripulantes_bloqueados == 1


def test_nao_aclimatado_nao_recebe_pouso_noturno(tripulante_factory, voo_factory):
    tripulantes = [tripulante_factory("t1", aclimatado=False)]
    voos = [voo_factory("v1", duracao=2.0, noturno=True)]

    with pytest.raises(OtimizacaoInviavel):
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)


def test_objetivo_distribui_a_carga(tripulante_factory, voo_factory):
    """Com dois tripulantes livres e dois voos, a solução ótima não concentra
    as duas jornadas em um único tripulante."""
    tripulantes = [tripulante_factory("t1", horas=0.0), tripulante_factory("t2", horas=0.0)]
    voos = [
        voo_factory("v1", duracao=2.0),
        voo_factory("v2", duracao=2.0),
    ]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    por_tripulante = {a.tripulante_id for a in solucao.alocacoes}
    assert por_tripulante == {"t1", "t2"}


def test_inviabilidade_quando_faltam_tripulantes(tripulante_factory, voo_factory):
    tripulantes = [tripulante_factory("t1")]
    voos = [voo_factory("v1"), voo_factory("v2"), voo_factory("v3")]

    with pytest.raises(OtimizacaoInviavel) as exc:
        otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    causas = " ".join(exc.value.diagnostico["causas"])
    assert "faltam" in causas


def test_conformidade_reflete_tripulantes_bloqueados(tripulante_factory, voo_factory):
    tripulantes = [
        tripulante_factory("t1", horas=11.5),  # acima do teto
        tripulante_factory("t2", horas=1.0),
    ]
    voos = [voo_factory("v1", duracao=2.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.tripulantes_bloqueados == 1
    assert solucao.conformidade == 50.0


def test_conversao_de_horas_para_minutos():
    assert minutos(11.5) == 690
    assert minutos(0.5) == 30
    assert minutos(11.0) == 660


def test_catalogo_de_restricoes_documentado():
    """Toda restrição precisa de nome, referência e descrição — é o material do
    capítulo de metodologia."""
    for item in catalogo_restricoes():
        assert item["nome"]
        assert item["referencia"]
        assert item["descricao"]
