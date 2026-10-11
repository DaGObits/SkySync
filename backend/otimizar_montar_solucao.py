"""Otimiza _montar_solucao(): troca a varredura O(voos x tripulantes) por
uma iteracao sobre os pares que existem no modelo.

Uso:  .venv\\Scripts\\python.exe otimizar_montar_solucao.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

ALVO = Path("optimizer/solver.py")

NOVA_FUNCAO = '''def _montar_solucao(
    base, status_nome, solver, x, tripulantes, voos, limite_horas, composicao
) -> Solucao:
    """Le o resultado do solver.

    OTIMIZACAO: antes esta funcao varria a matriz completa de pares
    (tripulante, voo) perguntando ao solver o valor de cada um:

        for v in voos:
            for t in tripulantes:

    Com 150 voos e ~860 tripulantes eram ~129.000 chamadas a solver.Value()
    para encontrar 750 atribuicoes — o resto era trabalho descartado.

    Agora itera sobre `x.items()`, que so contem os pares viaveis criados
    pelo filtro de dominio. Sao ~4.000 consultas em vez de ~129.000, e a
    complexidade cai de O(voos x tripulantes) para O(pares viaveis).
    """
    por_tripulante = {t.id: t for t in tripulantes}
    por_voo = {v.id: v for v in voos}

    alocacoes: list[Alocacao] = []
    horas_por_tripulante: dict[str, float] = {t.id: 0.0 for t in tripulantes}
    voos_cobertos: set[str] = set()

    for (t_id, v_id), variavel in x.items():
        if solver.Value(variavel) != 1:
            continue

        t = por_tripulante.get(t_id)
        v = por_voo.get(v_id)
        if t is None or v is None:
            continue

        alocacoes.append(
            Alocacao(
                voo_id=v.id,
                voo_codigo=v.codigo,
                tripulante_id=t.id,
                tripulante_nome=t.nome,
                cargo=t.cargo,
                duracao_horas=v.duracao_horas,
                rota=f"{v.origem} \u2192 {v.destino}".strip(" \u2192"),
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
'''


def main() -> int:
    if not ALVO.exists():
        print(f"ERRO: {ALVO.resolve()} nao encontrado.")
        print("Rode dentro de C:\\SkySync\\backend")
        return 1

    texto = ALVO.read_text(encoding="utf-8")
    linhas = texto.split("\n")

    inicio = None
    for i, linha in enumerate(linhas):
        if linha.startswith("def _montar_solucao("):
            inicio = i
            break

    if inicio is None:
        print("ERRO: 'def _montar_solucao(' nao encontrada.")
        return 1

    fim = None
    for i in range(inicio + 1, len(linhas)):
        if linhas[i].startswith("def "):
            fim = i
            break

    if fim is None:
        print("ERRO: nao achei o fim da funcao.")
        return 1

    antigo = "\n".join(linhas[inicio:fim])
    print(f"Funcao encontrada: linhas {inicio + 1} a {fim} ({len(antigo)} chars)")

    shutil.copy2(ALVO, ALVO.with_suffix(".py.bak"))
    print(f"Backup: {ALVO.with_suffix('.py.bak').name}")

    novas_linhas = linhas[:inicio] + NOVA_FUNCAO.split("\n") + linhas[fim:]
    ALVO.write_text("\n".join(novas_linhas), encoding="utf-8")

    print()
    print("Substituida pela versao que itera sobre x.items().")
    print("Confirme com: .venv\\Scripts\\python.exe -m pytest tests/test_solver.py -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
