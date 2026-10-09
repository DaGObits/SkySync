"""Testes das rotas HTTP."""
from __future__ import annotations

import json


def test_health(client):
    resposta = client.get("/api/health")
    assert resposta.status_code == 200
    assert resposta.get_json()["status"] == "ok"


def test_escala_padrao_quando_sem_historico(client):
    resposta = client.get("/api/escalas")
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["versao"] is None
    assert len(corpo["dados"]) == 1


def test_salvar_e_recuperar_historico(client):
    payload = {
        "dados": [
            {
                "voo": "TAM-3482",
                "tripulante": "Rafael Nunes",
                "risco": "alto",
                "desc": "Atraso meteorológico",
                "bloqueado": True,
            }
        ]
    }

    criado = client.post("/api/escalas/historico", json=payload)
    assert criado.status_code == 201
    assert criado.get_json()["versao"] == 0

    atual = client.get("/api/escalas").get_json()
    assert atual["versao"] == 0
    assert atual["dados"][0]["voo"] == "TAM-3482"
    assert atual["dados"][0]["badgeKey"] == "highFatigueRisk"

    versoes = client.get("/api/escalas/versoes").get_json()
    assert len(versoes) == 1


def test_versoes_incrementam_sem_duplicar(client):
    for esperado in range(3):
        resposta = client.post(
            "/api/escalas/historico", json={"dados": [{"voo": f"JJ-{1000 + esperado}"}]}
        )
        assert resposta.get_json()["versao"] == esperado

    versoes = client.get("/api/escalas/versoes").get_json()
    numeros = [v["versao"] for v in versoes]
    assert numeros == [2, 1, 0], "a numeração não pode repetir"


def test_payload_invalido_devolve_400(client):
    resposta = client.post("/api/escalas/historico", json={"dados": "não é lista"})
    assert resposta.status_code == 400
    assert "erro" in resposta.get_json()


def test_item_sem_voo_devolve_400(client):
    resposta = client.post("/api/escalas/historico", json={"dados": [{"risco": "alto"}]})
    assert resposta.status_code == 400
    assert "campos" in resposta.get_json()


def test_perfil_padrao(client):
    corpo = client.get("/api/perfil").get_json()
    assert corpo["email"] == "marina.costa@skysync.aero"


def test_salvar_perfil_e_upsert(client):
    primeiro = client.post(
        "/api/perfil",
        json={"nome": "Marina Costa", "email": "marina@skysync.aero", "cargo": "Coordenadora"},
    )
    assert primeiro.status_code == 200
    id_primeiro = primeiro.get_json()["id"]

    segundo = client.post(
        "/api/perfil",
        json={"nome": "Marina C. Costa", "email": "marina@skysync.aero", "cargo": "Gerente"},
    )
    assert segundo.status_code == 200
    assert segundo.get_json()["id"] == id_primeiro, "mesmo e-mail não pode duplicar"

    atual = client.get("/api/perfil").get_json()
    assert atual["nome"] == "Marina C. Costa"
    assert atual["cargo"] == "Gerente"


def test_perfil_sem_email_devolve_400(client):
    resposta = client.post("/api/perfil", json={"nome": "Sem Email"})
    assert resposta.status_code == 400
    assert "email" in resposta.get_json()["campos"]


def test_otimizacao_retorna_solucao_real(client):
    payload = {
        "base": "GRU",
        "tripulantes": [
            {"id": "t1", "nome": "Rafael Nunes", "horas_acumuladas": 4.0, "limite_horas": 11.0},
            {"id": "t2", "nome": "Lucas Mendes", "horas_acumuladas": 2.0, "limite_horas": 11.0},
        ],
        "voos": [
            {"id": "v1", "codigo": "TAM-3482", "duracao_horas": 3.0, "origem": "GRU", "destino": "VCP"},
            {"id": "v2", "codigo": "GLO-1207", "duracao_horas": 2.0, "origem": "CGH", "destino": "SSA"},
        ],
    }

    resposta = client.post("/api/otimizacao", json=payload)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["status"] in {"OPTIMAL", "FEASIBLE"}
    # O valor antigo era hardcoded em 100%; aqui tem de vir do cálculo.
    assert 0 <= corpo["conformidade"] <= 100
    assert len(corpo["alocacoes"]) == 2
    assert corpo["wall_time_seconds"] >= 0


def test_otimizacao_inviavel_devolve_409(client):
    payload = {
        "base": "GRU",
        "tripulantes": [
            {"id": "t1", "nome": "Único", "horas_acumuladas": 10.5, "limite_horas": 11.0}
        ],
        "voos": [{"id": "v1", "codigo": "TAM-1", "duracao_horas": 3.0}],
    }

    resposta = client.post("/api/otimizacao", json=payload)
    assert resposta.status_code == 409
    corpo = resposta.get_json()
    assert corpo["status"] == "INFEASIBLE"
    assert corpo["diagnostico"]["causas"]


def test_otimizacao_sem_tripulantes_devolve_400(client):
    resposta = client.post("/api/otimizacao", json={"base": "GRU", "tripulantes": [], "voos": []})
    assert resposta.status_code == 400


def test_catalogo_de_restricoes_exposto(client):
    corpo = client.get("/api/otimizacao/restricoes").get_json()
    nomes = {r["nome"] for r in corpo}
    assert {"limite_jornada", "descanso_minimo", "aclimatacao_fuso", "cobertura_voos"} <= nomes


def test_erro_interno_nao_vaza_detalhe(client):
    """Um payload com tipo errado não pode devolver stack trace nem SQL."""
    resposta = client.post(
        "/api/otimizacao",
        data=json.dumps({"base": "GRU", "tripulantes": "x", "voos": []}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    corpo = resposta.get_json()
    assert "campos" in corpo
    assert "Traceback" not in json.dumps(corpo)
