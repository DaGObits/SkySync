"""Aplica as tres ultimas correcoes de teste."""
from pathlib import Path

# --- 1. test_solver.py: bloquear por cargo, nao metade aleatoria ------------
s = Path("tests/test_solver.py")
t = s.read_text(encoding="utf-8")

marcador = "def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):"
if marcador not in t:
    print("test_solver.py: funcao nao encontrada!")
else:
    inicio = t.index(marcador)
    resto = t[inicio:]
    linhas = resto.split("\n")
    fim_relativo = len(resto)
    for i, linha in enumerate(linhas[1:], start=1):
        if linha and not linha[0].isspace() and linha.strip():
            fim_relativo = sum(len(l) + 1 for l in linhas[:i])
            break

    novo_bloco = '''def test_conformidade_reflete_bloqueados(tripulante_factory, voo_factory):
    """A conformidade cai quando parte do pool esta acima do teto.

    O bloqueio e feito UM POR CARGO, nao por metade aleatoria: com composicao
    de 5 por voo, bloquear metade generica pode zerar um cargo inteiro e o
    cenario vira INFEASIBLE — testando outra coisa.

    O diagnostico do solver confirmou: com metade bloqueada faltavam
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

    assert solucao.tripulantes_bloqueados == 3, "um por cargo"
    assert 0 <= solucao.conformidade < 100
    assert solucao.total_alocacoes == 10, "os 2 voos ainda saem completos"
'''

    t = t[:inicio] + novo_bloco + t[inicio + fim_relativo:]
    s.write_text(t, encoding="utf-8")
    print("test_solver.py: test reescrito (bloqueio por cargo).")

# --- 2. test_api.py: pool insuficiente agora e 400 -------------------------
a = Path("tests/test_api.py")
ta = a.read_text(encoding="utf-8")

antigo = '''def test_cenario_com_pool_explicito_menor(usuario_logado):
    """Pool pequeno gera cenário com pouca gente — útil para mostrar INFEASIBLE."""
    resposta = usuario_logado.post(
        "/api/cenarios", json={"voos": 10, "tripulantes": 5, "seed": 2}
    )
    assert resposta.status_code == 201
    assert len(resposta.get_json()["tripulantes"]) == 5'''

novo = '''def test_cenario_com_pool_insuficiente_devolve_400(usuario_logado):
    """Pool pequeno demais e RECUSADO com explicacao.

    Com 10 voos e composicao 1:1:3 o gerador precisa de 10 comandantes. Um
    pool de 5 nao cobre nem a metade. A versao anterior devolvia um cenario
    que o solver jamais resolveria — falha silenciosa. Recusar com mensagem e
    o comportamento honesto.
    """
    resposta = usuario_logado.post(
        "/api/cenarios", json={"voos": 10, "tripulantes": 5, "seed": 2}
    )
    assert resposta.status_code == 400
    assert "erro" in resposta.get_json()'''

if antigo in ta:
    a.write_text(ta.replace(antigo, novo), encoding="utf-8")
    print("test_api.py: pool insuficiente agora espera 400.")
elif "test_cenario_com_pool_insuficiente" in ta:
    print("test_api.py: ja estava corrigido.")
else:
    print("test_api.py: PADRAO NAO ENCONTRADO.")

# --- 3. cenarios.py: incluir o resumo no payload ---------------------------
c = Path("blueprints/cenarios.py")
tc = c.read_text(encoding="utf-8")

if 'payload["resumo"]' in tc:
    print("cenarios.py: resumo ja presente.")
else:
    antigo_ret = "    return jsonify(payload), 201"
    novo_ret = '''    # O resumo permite ao front dimensionar o cenario sem carregar o payload
    # inteiro — e o que informa quantos tripulantes por cargo foram gerados.
    payload["resumo"] = cenario.resumo()

    return jsonify(payload), 201'''
    if antigo_ret in tc:
        c.write_text(tc.replace(antigo_ret, novo_ret), encoding="utf-8")
        print("cenarios.py: resumo incluido no payload.")
    else:
        print("cenarios.py: RETURN NAO ENCONTRADO — conferir a mao.")

print()
print("Rode agora:  .venv\\Scripts\\python.exe -m pytest -v")
