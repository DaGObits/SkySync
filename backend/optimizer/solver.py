"""Motor de otimização de escalas (CP-SAT).

Este módulo NÃO importa Flask — é regra de projeto, não detalhe. Assim ele roda
igual a partir da API, de um script de linha de comando ou de um notebook, e o
capítulo de resultados do TCC pode ser gerado com ele sem subir servidor.

Modelo (composição real de aeronave):
    variáveis  x[t, v] ∈ {0,1}     tripulante t designado ao voo v
    restrições                     ver optimizer/restricoes.py
    objetivo                       minimizar a folga de jornada total

DIMENSÃO: o modelo cria uma variável por par (tripulante, voo), então o
crescimento é quadrático. Medição com o gerador de cenários (seed 42):

    25 voos  →   3.530 variáveis  →  0,6 s   → OPTIMAL
    50 voos  →  14.036 variáveis  →  4,2 s   → OPTIMAL
   100 voos  →  56.426 variáveis  → 41,5 s   → OPTIMAL
   150 voos  →  ~130.000 variáveis → tempo esgotado

Provar a otimalidade é a parte cara, não encontrar uma solução: em 150 voos o
solver não prova o ótimo em 60 s, mas costuma ter uma escala viável em mãos.
Por isso `otimizar()` devolve a solução com status `UNKNOWN_TEMPO_ESGOTADO` em
vez de descartá-la — uma escala que respeita a RBAC 117 vale mais que nenhuma.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from optimizer.restricoes import (
    COMPOSICAO_PADRAO,
    RESTRICOES_PADRAO,
    Contexto,
    Restricao,
    catalogo_restricoes,
)

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
    cargo: str
    duracao_horas: float
    rota: str


@dataclass
class Solucao:
    status: str
    base: str
    alocacoes: list[Alocacao] = field(default_factory=list)
    nao_alocados: list[str] = field(default_factory=list)
    total_tripulantes: int = 0
    total_voos: int = 0
    total_alocacoes: int = 0
    tripulantes_em_risco: int = 0
    tripulantes_bloqueados: int = 0
    conformidade: float = 100.0
    horas_alocadas: float = 0.0
    wall_time_seconds: float = 0.0
    objetivo: float = 0.0
    variaveis_criadas: int = 0
    composicao_aplicada: dict = field(default_factory=dict)
    restricoes_aplicadas: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "base": self.base,
            "total_tripulantes": self.total_tripulantes,
            "total_voos": self.total_voos,
            "total_alocacoes": self.total_alocacoes,
            "tripulantes_em_risco": self.tripulantes_em_risco,
            "tripulantes_bloqueados": self.tripulantes_bloqueados,
            "conformidade": round(self.conformidade, 2),
            "horas_alocadas": round(self.horas_alocadas, 2),
            "wall_time_seconds": round(self.wall_time_seconds, 3),
            "objetivo": round(self.objetivo, 2),
            "variaveis_criadas": self.variaveis_criadas,
            "composicao_aplicada": self.composicao_aplicada,
            "nao_alocados": self.nao_alocados,
            "alocacoes": [
                {
                    "voo_id": a.voo_id,
                    "voo": a.voo_codigo,
                    "tripulante_id": a.tripulante_id,
                    "tripulante": a.tripulante_nome,
                    "cargo": a.cargo,
                    "horas": _formatar_horas(a.duracao_horas),
                    "duracao_horas": round(a.duracao_horas, 2),
                    "rota": a.rota,
                }
                for a in self.alocacoes
            ],
            "restricoes_aplicadas": self.restricoes_aplicadas,
        }


def _formatar_horas(horas: float) -> str:
    total_min = int(round(horas * 60))
    return f"{total_min // 60:02d}h{total_min % 60:02d}"


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
    composicao: dict[str, int] | None = None,
    restricoes: tuple[Restricao, ...] = RESTRICOES_PADRAO,
    raio_bases: int = 0,
) -> Solucao:
    """Resolve a designação tripulante x voo sob as restrições da RBAC 117.

    Composição padrão: 1 comandante, 1 copiloto e 3 comissários por voo — a
    configuração de um narrow-body (A320 / 737).

    TRÊS NÍVEIS DE FILTRO DE DOMÍNIO, porque o modelo cria uma variável por par
    (tripulante, voo) e o crescimento é quadrático:

      1. cargo compatível com a composição
      2. jornada restante suficiente para a duração do voo
      3. base compatível com a origem do voo

    O filtro 3 (`raio_bases`) está DESLIGADO por padrão, e isso é deliberado.
    Ele reduz o modelo, mas só é seguro quando o pool tem cobertura garantida em
    todas as bases de partida. Um cenário gerado por probabilidade não tem essa
    garantia — e um único voo sem candidato torna o cenário inteiro INFEASIBLE.

    Use `raio_bases=1` quando o pool distribuir tripulantes pelas bases onde há
    voos partindo (é o que `dados.gerador` faz desde a correção do
    dimensionamento por base de partida).
    """
    if not tripulantes:
        raise ValueError("informe ao menos um tripulante")
    if not voos:
        raise ValueError("informe ao menos um voo")

    composicao = composicao or COMPOSICAO_PADRAO
    model = cp_model.CpModel()

    bases_por_regiao = _bases_por_regiao() if raio_bases > 0 else {}

    # --- Variáveis de decisão -------------------------------------------------
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    for t in tripulantes:
        if t.cargo not in composicao:
            continue
        teto_min = minutos(min(t.limite_horas, limite_horas))
        restante = teto_min - minutos(t.horas_acumuladas)
        bases_elegiveis = _bases_elegiveis(t.base, bases_por_regiao)

        for v in voos:
            duracao = minutos(v.duracao_horas)
            if duracao > restante:
                continue  # voo maior que a jornada restante: par inviável
            if v.origem not in bases_elegiveis:
                continue  # base fora do alcance do tripulante
            if not t.aclimatado and v.pouso_noturno:
                continue  # 117.135
            x[(t.id, v.id)] = model.NewBoolVar(f"x_{t.id}_{v.id}")

    # --- Folga de jornada por tripulante --------------------------------------
    # Entra na função objetivo: é o que faz o solver distribuir a carga em vez
    # de saturar os primeiros tripulantes da lista.
    folga: dict[str, cp_model.IntVar] = {}
    for t in tripulantes:
        teto_min = int(min(t.limite_horas, limite_horas) * 60)
        acumulado_min = int(t.horas_acumuladas * 60)
        disponivel = max(teto_min - acumulado_min, 0)
        var = model.NewIntVar(0, disponivel, f"folga_{t.id}")
        folga[t.id] = var

        carga = sum(
            x[(t.id, v.id)] * minutos(v.duracao_horas)
            for v in voos
            if (t.id, v.id) in x
        )
        model.Add(var == disponivel - carga)

    ctx = Contexto(
        model=model,
        variaveis=x,
        folga=folga,
        tripulantes=tripulantes,
        voos=voos,
        limite_horas=limite_horas,
        minutos_por_voo={v.id: minutos(v.duracao_horas) for v in voos},
        composicao=composicao,
    )

    for restricao in restricoes:
        restricao.aplicar(ctx)

    # --- Objetivo -------------------------------------------------------------
    # Minimizar a folga total == usar o mínimo de recurso por voo, o que
    # naturalmente equilibra a carga entre os tripulantes.
    model.Minimize(sum(folga.values()))

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
            base, status_nome, solver, x, tripulantes, voos, limite_horas, composicao
        )

    if status == cp_model.INFEASIBLE:
        raise OtimizacaoInviavel(
            "Nenhuma escala satisfaz simultaneamente todas as restrições da RBAC 117.",
            _diagnostico(tripulantes, voos, limite_horas, composicao),
        )

    # UNKNOWN = o solver parou por tempo. Isso NÃO significa que não achou nada:
    # normalmente existe uma solução viável em mãos, só não provada ótima.
    # Descartá-la seria jogar fora uma escala que respeita todas as restrições
    # da RBAC 117 — que é exatamente o que a operação precisa em uma disrupção.
    if solver.NumBooleans() > 0:
        try:
            solucao = _montar_solucao(
                base, f"{status_nome}_TEMPO_ESGOTADO", solver, x,
                tripulantes, voos, limite_horas, composicao
            )
            if solucao.alocacoes:
                return solucao
        except Exception:  # noqa: BLE001 - se não der para ler, cai no erro abaixo
            pass

    raise RuntimeError(
        f"O solver não conseguiu nem uma solução viável (status={status_nome}) em "
        f"{max_time_seconds:.0f}s. Aumente o tempo máximo ou reduza o problema."
    )


def _bases_por_regiao() -> dict[str, set[str]]:
    """Agrupa os aeroportos por região, para o filtro de domínio por base.

    Um tripulante estacionado em Confins pode pegar um voo partindo de
    Guarulhos — mesma região, e é assim que a malha doméstica funciona. Já um
    comissário em Manaus não cobre um voo de Porto Alegre na mesma rodada.
    """
    from dados.malha import MALHA

    por_regiao: dict[str, set[str]] = {}
    for a in MALHA:
        por_regiao.setdefault(a.regiao, set()).add(a.iata)
    return por_regiao


def _bases_elegiveis(base: str, bases_por_regiao: dict[str, set[str]]) -> set[str]:
    """Bases de onde um tripulante pode partir.

    A base dele mais as bases da mesma região. Quando `bases_por_regiao` está
    vazio (filtro desligado), devolve a sentinela que aceita qualquer origem.
    """
    if not bases_por_regiao:
        return _TODAS_AS_BASES
    for regiao, bases in bases_por_regiao.items():
        if base in bases:
            return bases
    return {base}


def bases_de_partida(voos: list) -> dict[str, int]:
    """Quantos voos partem de cada aeroporto.

    É o dimensionamento que o gerador usa para distribuir tripulantes pelas
    bases certas — em vez de escolher hubs a priori, que deixa aeroportos
    secundários sem nenhum candidato.
    """
    contagem: dict[str, int] = {}
    for v in voos:
        contagem[v.origem] = contagem.get(v.origem, 0) + 1
    return contagem


#: Sentinela que desativa o filtro por base. Um `set` vazio não serve porque
#: `in` sempre devolveria False e nenhuma variável seria criada.
class _TodasAsBases:
    def __contains__(self, _item) -> bool:
        return True


_TODAS_AS_BASES = _TodasAsBases()


def _montar_solucao(
    base, status_nome, solver, x, tripulantes, voos, limite_horas, composicao
) -> Solucao:
    alocacoes: list[Alocacao] = []
    horas_por_tripulante: dict[str, float] = {t.id: 0.0 for t in tripulantes}
    voos_cobertos: set[str] = set()

    for v in voos:
        for t in tripulantes:
            chave = (t.id, v.id)
            if chave in x and solver.Value(x[chave]) == 1:
                alocacoes.append(
                    Alocacao(
                        voo_id=v.id,
                        voo_codigo=v.codigo,
                        tripulante_id=t.id,
                        tripulante_nome=t.nome,
                        cargo=t.cargo,
                        duracao_horas=v.duracao_horas,
                        rota=f"{v.origem} → {v.destino}".strip(" →"),
                    )
                )
                horas_por_tripulante[t.id] += v.duracao_horas
                voos_cobertos.add(v.id)

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
        total_voos=len(voos),
        total_alocacoes=len(alocacoes),
        tripulantes_em_risco=len(em_risco),
        tripulantes_bloqueados=len(bloqueados),
        conformidade=conformidade,
        horas_alocadas=sum(horas_por_tripulante.values()),
        wall_time_seconds=solver.WallTime(),
        objetivo=solver.ObjectiveValue(),
        variaveis_criadas=len(x),
        composicao_aplicada=dict(composicao),
        restricoes_aplicadas=catalogo_restricoes(),
    )


def _ocupacao(tripulante, horas_novas: float, limite_horas: float) -> float:
    teto = min(tripulante.limite_horas, limite_horas)
    if teto <= 0:
        return 1.0
    return (tripulante.horas_acumuladas + horas_novas) / teto


def _diagnostico(tripulantes, voos, limite_horas, composicao) -> dict:
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
    for cargo, exigidos in composicao.items():
        necessarios = exigidos * len(voos)
        do_cargo = [t for t in disponiveis if t.cargo == cargo]
        if len(do_cargo) < necessarios:
            causas.append(
                f"faltam {necessarios - len(do_cargo)} {cargo.lower()}(s): "
                f"{len(voos)} voos x {exigidos} exigem {necessarios}, "
                f"e há {len(do_cargo)} disponíveis"
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
            "as restrições combinadas de composição, descanso, aclimatação e "
            "jornada eliminam todas as combinações possíveis"
        )

    return {
        "total_voos": len(voos),
        "total_tripulantes": len(tripulantes),
        "tripulantes_disponiveis": len(disponiveis),
        "alocacoes_necessarias": sum(composicao.values()) * len(voos),
        "horas_demandadas": round(horas_totais, 2),
        "horas_disponiveis": round(capacidade, 2),
        "composicao_exigida": dict(composicao),
        "causas": causas,
    }
