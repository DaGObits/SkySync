from pathlib import Path
s = Path("tests/test_solver.py")
t = s.read_text(encoding="utf-8")

antigo = '''def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):
    """A conformidade cai quando parte do pool está acima do teto.

    O pool é dobrado antes de bloquear metade: com composição de 5 por voo,
    bloquear dentro de um pool exato deixa alguns cargos sem ninguém elegível e
    o cenário vira INFEASIBLE — o que testaria outra coisa.
    """
    tripulantes = pool(tripulante_factory, voos=2, horas=0.0)
    # Metade do pool já estourada — mas sempre há uma metade inteira livre.
    for i, t in enumerate(tripulantes):
        if i % 2 == 0:
            t.horas_acumuladas = 11.5
    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.tripulantes_bloqueados > 0
    assert 0 <= solucao.conformidade < 100
    # Os voos ainda saem: há gente suficiente na metade disponível.
    assert solucao.total_alocacoes == 10'''

novo = '''def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):
    """A conformidade cai quando parte do pool está acima do teto.

    O bloqueio é feito UM POR CARGO, nao por metade aleatoria: com composicao
    de 5 por voo, bloquear metade generica pode zerar um cargo inteiro e o
    cenario vira INFEASIBLE — testando outra coisa que nao a conformidade.
    """
    tripulantes = pool(tripulante_factory, voos=2, horas=0.0)

    # Bloqueia exatamente um de cada cargo, preservando a composicao.
    bloqueados = set()
    for cargo in ("Comandante", "Copiloto", "Comissario"):
        for t in tripulantes:
            if t.cargo == cargo and cargo not in bloqueados:
                t.horas_acumuladas = 11.5
                bloqueados.add(cargo)
                break

    voos = [voo_factory("v1", duracao=1.0), voo_factory("v2", duracao=1.0)]

    solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)

    assert solucao.tripulantes_bloqueados == 3
    assert 0 <= solucao.conformidade < 100
    assert solucao.total_alocacoes == 10'''

if antigo in t:
    s.write_text(t.replace(antigo, novo), encoding="utf-8")
    print("test_solver.py corrigido.")
else:
    print("PADRAO NAO ENCONTRADO — o teste ja foi editado.")
