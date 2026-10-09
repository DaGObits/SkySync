"""Corrige os 2 ultimos testes reescrevendo o bloco por POSICAO, nao por texto."""
from pathlib import Path
import re

# ===========================================================================
# 1. test_solver.py — substitui a funcao pelo nome, do def ate a proxima def
# ===========================================================================
s = Path("tests/test_solver.py")
t = s.read_text(encoding="utf-8")

padrao = re.compile(
    r"def test_conformidade_reflete_bloqueados\(.*?\n(?=def |\Z)",
    re.DOTALL,
)

novo_solver = '''def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):
    """A conformidade cai quando parte do pool esta acima do teto.

    O bloqueio e feito UM POR CARGO, nao por metade aleatoria. Com composicao
    de 5 por voo, bloquear metade generica zera um cargo inteiro e o cenario
    vira INFEASIBLE — testando outra coisa que nao a conformidade.

    O diagnostico do solver confirmou isso: com metade bloqueada faltavam
    "1 comandante, 1 copiloto e 3 comissarios" para cobrir 2 voos.
    """
    tripulantes = pool(tripulante_factory, voos=2, horas=0.0)

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


'''

if padrao.search(t):
    t = padrao.sub(novo_solver, t, count=1)
    s.write_text(t, encoding="utf-8")
    print("test_solver.py: OK (reescrito por posicao)")
else:
    print("test_solver.py: funcao NAO ENCONTRADA")

# ===========================================================================
# 2. cenarios.py — garante payload["resumo"] antes do return
# ===========================================================================
c = Path("blueprints/cenarios.py")
tc = c.read_text(encoding="utf-8")

if 'payload["resumo"]' in tc:
    print("cenarios.py: resumo JA presente")
else:
    # Insere antes da PRIMEIRA ocorrencia de "return jsonify(payload), 201"
    alvo = re.search(r"\n(\s*)return jsonify\(payload\), 201", tc)
    if alvo:
        indent = alvo.group(1)
        insercao = (
            "\n" + indent + "# O resumo permite ao front dimensionar o cenario sem carregar\n"
            + indent + "# o payload inteiro — informa tripulantes por cargo e alocacoes.\n"
            + indent + 'payload["resumo"] = cenario.resumo()\n'
        )
        tc = tc[: alvo.start()] + insercao + tc[alvo.start():]
        c.write_text(tc, encoding="utf-8")
        print("cenarios.py: resumo INSERIDO")
    else:
        print("cenarios.py: return NAO ENCONTRADO")
        print("   --- ultimas 15 linhas do arquivo ---")
        for linha in tc.splitlines()[-15:]:
            print("   ", linha)

print()
print("Confira com:  .venv\\Scripts\\python.exe -m pytest -v")
