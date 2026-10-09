"""Testes das rotas HTTP.

Depois da autenticação, as rotas de dados exigem sessão ativa — por isso os
testes usam a fixture `usuario_logado`.
"""
from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Saúde e rotas base
# ---------------------------------------------------------------------------
def test_health(client):
    resposta = client.get("/api/health")
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["status"] == "ok"
    assert corpo["banco"]["ok"] is True


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
def test_registrar_usuario(client):
    resposta = client.post(
        "/api/auth/registrar",
        json={"nome": "Marina Costa", "email": "marina@skysync.aero", "senha": "Senha123"},
    )
    assert resposta.status_code == 201
    assert "sucesso" in resposta.get_json()["mensagem"]


def test_registrar_com_senha_fraca_devolve_400(client):
    resposta = client.post(
        "/api/auth/registrar",
        json={"nome": "Marina", "email": "marina@skysync.aero", "senha": "fraca"},
    )
    assert resposta.status_code == 400
    assert "senha" in resposta.get_json()["campos"]


def test_registrar_email_duplicado_devolve_409(client):
    corpo = {"nome": "Marina", "email": "marina@skysync.aero", "senha": "Senha123"}
    client.post("/api/auth/registrar", json=corpo)
    assert client.post("/api/auth/registrar", json=corpo).status_code == 409


def test_email_e_case_insensitive(client):
    client.post(
        "/api/auth/registrar",
        json={"nome": "Marina", "email": "Marina@SkySync.aero", "senha": "Senha123"},
    )
    resposta = client.post(
        "/api/auth/login", json={"email": "marina@skysync.aero", "senha": "Senha123"}
    )
    assert resposta.status_code == 200


def test_login_com_senha_correta(client):
    client.post(
        "/api/auth/registrar",
        json={"nome": "Marina", "email": "marina@skysync.aero", "senha": "Senha123"},
    )
    resposta = client.post(
        "/api/auth/login", json={"email": "marina@skysync.aero", "senha": "Senha123"}
    )
    assert resposta.status_code == 200
    assert resposta.get_json()["usuario"]["email"] == "marina@skysync.aero"


def test_login_com_senha_errada_devolve_401(client):
    client.post(
        "/api/auth/registrar",
        json={"nome": "Marina", "email": "marina@skysync.aero", "senha": "Senha123"},
    )
    resposta = client.post(
        "/api/auth/login", json={"email": "marina@skysync.aero", "senha": "Errada123"}
    )
    assert resposta.status_code == 401


def test_login_de_usuario_inexistente_devolve_401(client):
    """Mesma resposta do caso anterior — não revela se o e-mail existe."""
    resposta = client.post(
        "/api/auth/login", json={"email": "ninguem@x.com", "senha": "Senha123"}
    )
    assert resposta.status_code == 401
    assert resposta.get_json()["erro"] == "e-mail ou senha inválidos"


def test_senha_nao_e_guardada_em_texto(app, client):
    client.post(
        "/api/auth/registrar",
        json={"nome": "Marina", "email": "marina@skysync.aero", "senha": "Senha123"},
    )
    with app.app_context():
        from db import transacao

        with transacao() as conexao:
            linha = conexao.execute(
                "SELECT senha_hash FROM usuarios WHERE LOWER(email) = %s",
                ("marina@skysync.aero",),
            ).fetchone()

    from werkzeug.security import check_password_hash

    hash_guardado = linha["senha_hash"]
    assert hash_guardado != "Senha123"
    assert "Senha123" not in hash_guardado
    assert check_password_hash(hash_guardado, "Senha123")


def test_sessao_sem_login(client):
    corpo = client.get("/api/auth/sessao").get_json()
    assert corpo["autenticado"] is False


def test_logout_encerra_sessao(usuario_logado):
    assert usuario_logado.get("/api/auth/sessao").get_json()["autenticado"] is True
    usuario_logado.post("/api/auth/logout")
    assert usuario_logado.get("/api/auth/sessao").get_json()["autenticado"] is False


# ---------------------------------------------------------------------------
# Rotas protegidas — 401 sem sessão
# ---------------------------------------------------------------------------
def test_escalas_exige_login(client):
    assert client.get("/api/escalas").status_code == 401


def test_perfil_exige_login(client):
    assert client.get("/api/perfil").status_code == 401


def test_otimizacao_exige_login(client):
    assert client.post("/api/otimizacao", json={"base": "GRU"}).status_code == 401


def test_cenarios_exige_login(client):
    assert client.post("/api/cenarios", json={"voos": 5}).status_code == 401


def test_rotas_informativas_nao_exigem_login(client):
    """Catálogo de restrições e malha são conteúdo informativo."""
    assert client.get("/api/otimizacao/restricoes").status_code == 200
    assert client.get("/api/malha").status_code == 200


# ---------------------------------------------------------------------------
# Malha aérea
# ---------------------------------------------------------------------------
def test_malha_lista_aeroportos_reais(client):
    corpo = client.get("/api/malha").get_json()
    assert corpo["total"] > 30
    iatas = {a["iata"] for a in corpo["aeroportos"]}
    assert {"GRU", "MAO", "REC", "BSB", "FOR"} <= iatas
    assert "GRU" in corpo["hubs"]


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------
def test_gerar_cenario_dimensiona_o_pool(usuario_logado):
    """5 voos exigem 5 comandantes e 5 copilotos — mais a folga padrão de 15%."""
    resposta = usuario_logado.post("/api/cenarios", json={"voos": 5, "seed": 1})
    assert resposta.status_code == 201

    corpo = resposta.get_json()
    resumo = corpo["resumo"]
    assert resumo["voos"] == 5
    assert resumo["alocacoes_necessarias"] == 25
    por_cargo = resumo["tripulantes_por_cargo"]
    assert por_cargo["Comandante"] >= 5
    assert por_cargo["Copiloto"] >= 5
    assert por_cargo["Comissário"] >= 15


def test_cenario_reprodutivel_com_mesma_seed(usuario_logado):
    """A mesma seed produz o mesmo cenário — a banca pode repetir o experimento."""
    a = usuario_logado.post("/api/cenarios", json={"voos": 3, "seed": 99}).get_json()
    b = usuario_logado.post("/api/cenarios", json={"voos": 3, "seed": 99}).get_json()
    assert a["voos"] == b["voos"]
    assert [v["codigo"] for v in a["voos"]] == [v["codigo"] for v in b["voos"]]


def test_cenario_com_pool_insuficiente_devolve_400(usuario_logado):
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
    assert "erro" in resposta.get_json()


def test_cenario_com_parametros_invalidos(usuario_logado):
    resposta = usuario_logado.post("/api/cenarios", json={"voos": 0})
    assert resposta.status_code == 400
    assert "campos" in resposta.get_json()


def test_listar_cenarios(usuario_logado):
    usuario_logado.post("/api/cenarios", json={"voos": 2, "seed": 5})
    corpo = usuario_logado.get("/api/cenarios").get_json()
    assert len(corpo) == 1
    assert corpo[0]["n_voos"] == 2


def test_recuperar_cenario_salvo(usuario_logado):
    criado = usuario_logado.post("/api/cenarios", json={"voos": 2, "seed": 5}).get_json()
    resposta = usuario_logado.get(f"/api/cenarios/{criado['id']}")
    assert resposta.status_code == 200
    assert len(resposta.get_json()["voos"]) == 2


def test_cenario_inexistente_devolve_404(usuario_logado):
    assert usuario_logado.get("/api/cenarios/999999").status_code == 404


# ---------------------------------------------------------------------------
# Otimização
# ---------------------------------------------------------------------------
def _payload_composicao(voos=1):
    """Payload com a composição mínima: 1 CM, 1 CP, 3 CC por voo."""
    tripulantes = []
    for i in range(voos):
        tripulantes += [
            {"id": f"cm{i}", "nome": f"CM {i}", "cargo": "Comandante",
             "horas_acumuladas": 1.0, "limite_horas": 11.0},
            {"id": f"cp{i}", "nome": f"CP {i}", "cargo": "Copiloto",
             "horas_acumuladas": 1.0, "limite_horas": 11.0},
            {"id": f"cc{i}a", "nome": f"CC {i}A", "cargo": "Comissário",
             "horas_acumuladas": 1.0, "limite_horas": 11.0},
            {"id": f"cc{i}b", "nome": f"CC {i}B", "cargo": "Comissário",
             "horas_acumuladas": 1.0, "limite_horas": 11.0},
            {"id": f"cc{i}c", "nome": f"CC {i}C", "cargo": "Comissário",
             "horas_acumuladas": 1.0, "limite_horas": 11.0},
        ]
    return {
        "base": "GRU",
        "tripulantes": tripulantes,
        "voos": [
            {"id": f"v{i}", "codigo": f"TAM-{1000 + i}", "duracao_horas": 2.0,
             "origem": "GRU", "destino": "VCP"}
            for i in range(voos)
        ],
    }


def test_otimizacao_compoe_a_tripulacao(usuario_logado):
    resposta = usuario_logado.post("/api/otimizacao", json=_payload_composicao(1))
    assert resposta.status_code == 200

    corpo = resposta.get_json()
    assert corpo["status"] in {"OPTIMAL", "FEASIBLE"}
    assert corpo["total_alocacoes"] == 5

    por_cargo: dict[str, int] = {}
    for a in corpo["alocacoes"]:
        por_cargo[a["cargo"]] = por_cargo.get(a["cargo"], 0) + 1
    assert por_cargo == {"Comandante": 1, "Copiloto": 1, "Comissário": 3}


def test_otimizacao_reporta_metricas(usuario_logado):
    corpo = usuario_logado.post("/api/otimizacao", json=_payload_composicao(3)).get_json()
    assert corpo["total_voos"] == 3
    assert corpo["total_alocacoes"] == 15
    assert corpo["variaveis_criadas"] > 0
    assert corpo["wall_time_seconds"] >= 0
    assert corpo["composicao_aplicada"] == {"Comandante": 1, "Copiloto": 1, "Comissário": 3}


def test_otimizacao_inviavel_sem_comandante(usuario_logado):
    payload = _payload_composicao(1)
    payload["tripulantes"] = [t for t in payload["tripulantes"] if t["cargo"] != "Comandante"]

    resposta = usuario_logado.post("/api/otimizacao", json=payload)
    assert resposta.status_code == 409
    corpo = resposta.get_json()
    assert corpo["status"] == "INFEASIBLE"
    assert corpo["diagnostico"]["causas"]


def test_cargo_invalido_devolve_400(usuario_logado):
    payload = _payload_composicao(1)
    payload["tripulantes"][0]["cargo"] = "Comissário-chefe"

    resposta = usuario_logado.post("/api/otimizacao", json=payload)
    assert resposta.status_code == 400
    assert "cargo" in json.dumps(resposta.get_json()["campos"])


def test_execucao_fica_registrada_na_auditoria(app, usuario_logado):
    """A trilha de auditoria grava cada execução — dado do capítulo de resultados."""
    usuario_logado.post("/api/otimizacao", json=_payload_composicao(2))

    with app.app_context():
        from db import transacao

        with transacao() as conexao:
            linha = conexao.execute(
                "SELECT status_solver, total_voos, variaveis_criadas "
                "FROM execucoes_otimizacao ORDER BY id DESC LIMIT 1"
            ).fetchone()

    assert linha is not None
    assert linha["status_solver"] in {"OPTIMAL", "FEASIBLE"}
    assert linha["total_voos"] == 2


def test_erro_interno_nao_vaza_detalhe(usuario_logado):
    resposta = usuario_logado.post(
        "/api/otimizacao",
        data=json.dumps({"base": "GRU", "tripulantes": "x", "voos": []}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    corpo = resposta.get_json()
    assert "campos" in corpo
    assert "Traceback" not in json.dumps(corpo)
