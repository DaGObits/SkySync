"""Motor de otimização de escalas (CP-SAT).

Este módulo NÃO importa Flask — é regra de projeto, não detalhe. Assim ele roda
igual a partir da API, de um script de linha de comando ou de um notebook, e o
capítulo de resultados do TCC pode ser gerado com ele sem subir servidor.

Modelo:
    variáveis  x[t, v] ∈ {0,1}     tripulante t opera o voo v
    restrições                     ver optimizer/restricoes.py
    objetivo                       minimizar a soma das folgas de jornada
                                   (distribuir a fadiga de forma equilibrada
                                    em vez de concentrar horas em poucos)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from optimizer.restricoes import (
    RESTRICOES_PADRAO,
    Contexto,
    Restricao,
    catalogo_restricoes,
)

# Status do CP-SAT traduzidos para o vocabulário da API.
_STATUS_MAP = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


class OtimizacaoInviavel(RuntimeError):
    """Nenhuma escala satisfaz as restrições — vira HTTP 409, não 500.

    Isso é uma resposta legítima do sistema: significa que a regulamentação
    torna o cenário impossível, e o operador precisa mudar a entrada (mais
    tripulantes, menos voos, ou autorizar uma extensão).
    """

    def __init__(self, mensagem: str, diagnostico: dict):
        super().__init__(mensagem)
        self.diagnostico = diagnostico


@dataclass
class Alocacao:
    voo_id: str
    voo_codigo: str
    tripulante_id: str
    tripulante_nome: str
    duracao_horas: float
    rota: str


@dataclass
class Solucao:
    status: str
    base: str
    alocacoes: list[Alocacao] = field(default_factory=list)
    nao_alocados: list[str] = field(default_factory=list)
    total_tripulantes: int = 0
    tripulantes_em_risco: int = 0
    tripulantes_bloqueados: int = 0
    conformidade: float = 100.0
    horas_alocadas: float = 0.0
    wall_time_seconds: float = 0.0
    objetivo: float = 0.0
    restricoes_aplicadas: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "base": self.base,
            "total_tripulantes": self.total_tripulantes,
            "tripulantes_em_risco": self.tripulantes_em_risco,
            "tripulantes_bloqueados": self.tripulantes_bloqueados,
            "conformidade": round(self.conformidade, 2),
            "horas_alocadas": round(self.horas_alocadas, 2),
            "wall_time_seconds": round(self.wall_time_seconds, 3),
            "objetivo": round(self.objetivo, 2),
            "nao_alocados": self.nao_alocados,
            "alocacoes": [
                {
                    "voo_id": a.voo_id,
                    "voo": a.voo_codigo,
                    "tripulante_id": a.tripulante_id,
                    "tripulante": a.tripulante_nome,
                    "horas": f"{int(a.duracao_horas):02d}h{int(round((a.duracao_horas % 1) * 60)):02d}",
                    "duracao_horas": round(a.duracao_horas, 2),
                    "rota": a.rota,
                }
                for a in self.alocacoes
            ],
            "restricoes_aplicadas": self.restricoes_aplicadas,
        }


def minutos(horas: float) -> int:
    """Horas decimais -> minutos inteiros.

    O CP-SAT só trabalha com inteiros. Arredondar aqui, uma única vez, evita
    erro de ponto flutuante dentro do modelo.
    """
    return int(round(horas * 60))


def otimizar(
    base: str,
    tripulantes: list,
    voos: list,
    limite_horas: float = 11.0,
    max_time_seconds: float = 10.0,
    restricoes: tuple[Restricao, ...] = RESTRICOES_PADRAO,
) -> Solucao:
    """Resolve a alocação tripulante x voo sob as restrições da RBAC 117."""

    if not tripulantes:
        raise ValueError("informe ao menos um tripulante")
    if not voos:
        raise ValueError("informe ao menos um voo")

    model = cp_model.CpModel()

    # --- Variáveis de decisão -------------------------------------------------
    x = {
        (t.id, v.id): model.NewBoolVar(f"x_{t.id}_{v.id}")
        for t in tripulantes
        for v in voos
    }

    # Folga de jornada por tripulante (minutos). Não é só métrica: entra na
    # função objetivo, e é o que faz o solver distribuir a carga em vez de
    # saturar o primeiro tripulante da lista.
    folgas: dict[str, cp_model.IntVar] = {}
    for t in tripulantes:
        teto = minutos(min(t.limite_horas, limite_horas))
        acumulado = minutos(t.horas_acumuladas)
        folga = model.NewIntVar(0, max(teto - acumulado, 0), f"folga_{t.id}")
        folgas[t.id] = folga
        carga = sum(x[(t.id, v.id)] * minutos(v.duracao_horas) for v in voos)

        # Relação folga = disponibilidade - carga. O teto já foi imposto em
        # LimiteDeJornada, então o lado direito nunca fica negativo e a folga
        # fica bem definida e >= 0.
        model.Add(folga == max(teto - acumulado, 0) - carga)

    ctx = Contexto(
        model=model,
        variaveis=x,
        sobrecarga=folgas,
        tripulantes=tripulantes,
        voos=voos,
        limite_horas=limite_horas,
        minutos_por_voo={v.id: minutos(v.duracao_horas) for v in voos},
    )

    for restricao in restricoes:
        restricao.aplicar(ctx)

    # --- Objetivo -------------------------------------------------------------
    # Minimizar a folga total == usar o mínimo de recurso possível por voo.
    # Troque por `model.Maximize(sum(peso_prioridade * x))` se o critério
    # operacional for "priorizar voos críticos" em vez de "economizar jornada".
    model.Minimize(sum(folgas.values()))

    # --- Resolve --------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    # Um único worker deixa a execução reprodutível — importante para um TCC em
    # que a banca pode querer repetir o experimento e comparar os números.
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42

    status = solver.Solve(model)
    status_nome = _STATUS_MAP.get(status, "UNKNOWN")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _montar_solucao(
            base, status_nome, solver, x, tripulantes, voos, limite_horas
        )

    if status == cp_model.INFEASIBLE:
        raise OtimizacaoInviavel(
            "Nenhuma escala satisfaz simultaneamente todas as restrições da RBAC 117.",
            _diagnostico(tripulantes, voos, limite_horas),
        )

    raise RuntimeError(
        f"O solver não convergiu (status={status_nome}) em "
        f"{max_time_seconds:.0f}s. Aumente o tempo máximo ou reduza o problema."
    )


def _montar_solucao(base, status_nome, solver, x, tripulantes, voos, limite_horas) -> Solucao:
    por_id = {t.id: t for t in tripulantes}
    alocacoes: list[Alocacao] = []
    horas_por_tripulante: dict[str, float] = {t.id: 0.0 for t in tripulantes}
    voos_cobertos: set[str] = set()

    for v in voos:
        for t in tripulantes:
            if solver.Value(x[(t.id, v.id)]) == 1:
                alocacoes.append(
                    Alocacao(
                        voo_id=v.id,
                        voo_codigo=v.codigo,
                        tripulante_id=t.id,
                        tripulante_nome=t.nome,
                        duracao_horas=v.duracao_horas,
                        rota=f"{v.origem} → {v.destino}".strip(" →"),
                    )
                )
                horas_por_tripulante[t.id] += v.duracao_horas
                voos_cobertos.add(v.id)
                break

    nao_alocados = [v.codigo for v in voos if v.id not in voos_cobertos]

    bloqueados = [
        t for t in tripulantes
        if not t.descanso_ok
        or t.horas_acumuladas >= min(t.limite_horas, limite_horas)
    ]
    em_risco = [
        t for t in tripulantes
        if t not in bloqueados
        and _ocupacao(t, horas_por_tripulante.get(t.id, 0.0), limite_horas) >= 0.9
    ]

    total = len(tripulantes)
    conformidade = round(((total - len(bloqueados)) / total) * 100, 2) if total else 100.0

    return Solucao(
        status=status_nome,
        base=base,
        alocacoes=alocacoes,
        nao_alocados=nao_alocados,
        total_tripulantes=total,
        tripulantes_em_risco=len(em_risco),
        tripulantes_bloqueados=len(bloqueados),
        conformidade=conformidade,
        horas_alocadas=sum(horas_por_tripulante.values()),
        wall_time_seconds=solver.WallTime(),
        objetivo=solver.ObjectiveValue(),
        restricoes_aplicadas=catalogo_restricoes(),
    )


def _ocupacao(tripulante, horas_novas: float, limite_horas: float) -> float:
    teto = min(tripulante.limite_horas, limite_horas)
    if teto <= 0:
        return 1.0
    return (tripulante.horas_acumuladas + horas_novas) / teto


def _diagnostico(tripulantes, voos, limite_horas) -> dict:
    """Explica *por que* o problema é inviável — evita um 409 sem contexto."""
    disponiveis = [
        t for t in tripulantes
        if t.descanso_ok and t.horas_acumuladas < min(t.limite_horas, limite_horas)
    ]
    horas_totais = sum(v.duracao_horas for v in voos)
    capacidade = sum(
        max(min(t.limite_horas, limite_horas) - t.horas_acumuladas, 0.0)
        for t in disponiveis
    )

    causas = []
    if len(tripulantes) < len(voos):
        causas.append(
            f"há {len(voos)} voos para {len(tripulantes)} tripulantes; "
            "como cada voo exige um tripulante, faltam "
            f"{len(voos) - len(tripulantes)}"
        )
    if not disponiveis:
        causas.append("todos os tripulantes estão bloqueados por descanso ou jornada")
    elif capacidade < horas_totais:
        causas.append(
            f"a capacidade de jornada disponível ({capacidade:.1f}h) é menor que "
            f"a demanda dos voos ({horas_totais:.1f}h)"
        )
    if not causas:
        causas.append(
            "as restrições combinadas de descanso, aclimatação e jornada "
            "eliminam todas as combinações possíveis"
        )

    return {
        "total_voos": len(voos),
        "total_tripulantes": len(tripulantes),
        "tripulantes_disponiveis": len(disponiveis),
        "horas_demandadas": round(horas_totais, 2),
        "horas_disponiveis": round(capacidade, 2),
        "causas": causas,
    }
