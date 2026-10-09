"""Testes das rotas HTTP.

Depois da autenticação, as rotas de dados exigem sessão ativa — por isso os
testes usam a fixture `usuario_logado`, que registra e autentica antes de
chamar a rota protegida. Sem ela, tudo devolveria 401.
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


def test_registrar_com_email_invalido_devolve_400(client):
    resposta = client.post(
        "/api/auth/registrar",
        json={"nome": "Marina", "email": "sem-arroba", "senha": "Senha123"},
    )
    assert resposta.status_code == 400
    assert "email" in resposta.get_json()["campos"]


def test_registrar_email_duplicado_devolve_409(client):
    corpo = {"nome": "Marina", "email": "marina@skysync.aero", "senha": "Senha123"}
    client.post("/api/auth/registrar", json=corpo)
    segunda = client.post("/api/auth/registrar", json=corpo)
    assert segunda.status_code == 409


def test_email_e_case_insensitive(client):
    """Marina@x.com e marina@x.com são a mesma conta."""
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

    assert linha["senha_hash"] != "Senha123"
    assert linha["senha_hash"].startswith("pbkdf2:")


def test_sessao_sem_login(client):
    resposta = client.get("/api/auth/sessao")
    assert resposta.status_code == 200
    assert resposta.get_json()["autenticado"] is False


def test_sessao_apos_login(usuario_logado):
    corpo = usuario_logado.get("/api/auth/sessao").get_json()
    assert corpo["autenticado"] is True
    assert corpo["usuario"]["email"] == "marina@skysync.aero"


def test_logout_encerra_sessao(usuario_logado):
    assert usuario_logado.get("/api/auth/sessao").get_json()["autenticado"] is True
    usuario_logado.post("/api/auth/logout")
    assert usuario_logado.get("/api/auth/sessao").get_json()["autenticado"] is False


# ---------------------------------------------------------------------------
# Rotas protegidas — 401 sem sessão
# ---------------------------------------------------------------------------
def test_escalas_exige_login(client):
    assert client.get("/api/escalas").status_code == 401


def test_historico_exige_login(client):
    assert client.post("/api/escalas/historico", json={"dados": []}).status_code == 401


def test_perfil_exige_login(client):
    assert client.get("/api/perfil").status_code == 401


def test_otimizacao_exige_login(client):
    assert client.post("/api/otimizacao", json={"base": "GRU"}).status_code == 401


def test_catalogo_de_restricoes_nao_exige_login(client):
    """Conteúdo informativo: fica aberto de propósito."""
    assert client.get("/api/otimizacao/restricoes").status_code == 200


# ---------------------------------------------------------------------------
# Escalas
# ---------------------------------------------------------------------------
def test_escala_padrao_quando_sem_historico(usuario_logado):
    corpo = usuario_logado.get("/api/escalas").get_json()
    assert corpo["versao"] is None
    assert len(corpo["dados"]) == 1


def test_salvar_e_recuperar_historico(usuario_logado):
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
    criado = usuario_logado.post("/api/escalas/historico", json=payload)
    assert criado.status_code == 201
    assert criado.get_json()["versao"] == 0

    atual = usuario_logado.get("/api/escalas").get_json()
    assert atual["versao"] == 0
    assert atual["dados"][0]["voo"] == "TAM-3482"
    assert atual["dados"][0]["badgeKey"] == "highFatigueRisk"


def test_versoes_incrementam_sem_duplicar(usuario_logado):
    for esperado in range(3):
        resposta = usuario_logado.post(
            "/api/escalas/historico", json={"dados": [{"voo": f"JJ-{1000 + esperado}"}]}
        )
        assert resposta.get_json()["versao"] == esperado

    versoes = usuario_logado.get("/api/escalas/versoes").get_json()
    assert [v["versao"] for v in versoes] == [2, 1, 0]


def test_payload_invalido_devolve_400(usuario_logado):
    assert usuario_logado.post("/api/escalas/historico", json={"dados": "x"}).status_code == 400


def test_item_sem_voo_devolve_400(usuario_logado):
    resposta = usuario_logado.post(
        "/api/escalas/historico", json={"dados": [{"risco": "alto"}]}
    )
    assert resposta.status_code == 400
    assert "campos" in resposta.get_json()


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------
def test_perfil_do_usuario_logado(usuario_logado):
    corpo = usuario_logado.get("/api/perfil").get_json()
    assert corpo["email"] == "marina@skysync.aero"
    assert corpo["nome"] == "Marina Costa"


def test_atualizar_perfil(usuario_logado):
    resposta = usuario_logado.post(
        "/api/perfil", json={"nome": "Marina C. Costa", "cargo": "Gerente", "base": "GRU"}
    )
    assert resposta.status_code == 200
    atual = usuario_logado.get("/api/perfil").get_json()
    assert atual["nome"] == "Marina C. Costa"
    assert atual["cargo"] == "Gerente"


def test_perfil_aceita_role_como_apelido_de_cargo(usuario_logado):
    """O front envia `role`; a API aceita os dois nomes."""
    usuario_logado.post("/api/perfil", json={"nome": "Marina", "role": "Supervisora"})
    assert usuario_logado.get("/api/perfil").get_json()["cargo"] == "Supervisora"


def test_perfil_sem_nome_devolve_400(usuario_logado):
    assert usuario_logado.post("/api/perfil", json={"nome": ""}).status_code == 400


# ---------------------------------------------------------------------------
# Otimização
# ---------------------------------------------------------------------------
def test_otimizacao_retorna_solucao_real(usuario_logado):
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
    resposta = usuario_logado.post("/api/otimizacao", json=payload)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["status"] in {"OPTIMAL", "FEASIBLE"}
    # O valor antigo era hardcoded em 100%; aqui tem de vir do cálculo.
    assert 0 <= corpo["conformidade"] <= 100
    assert len(corpo["alocacoes"]) == 2
    assert corpo["wall_time_seconds"] >= 0


def test_otimizacao_inviavel_devolve_409(usuario_logado):
    payload = {
        "base": "GRU",
        "tripulantes": [
            {"id": "t1", "nome": "Único", "horas_acumuladas": 10.5, "limite_horas": 11.0}
        ],
        "voos": [{"id": "v1", "codigo": "TAM-1", "duracao_horas": 3.0}],
    }
    resposta = usuario_logado.post("/api/otimizacao", json=payload)
    assert resposta.status_code == 409
    corpo = resposta.get_json()
    assert corpo["status"] == "INFEASIBLE"
    assert corpo["diagnostico"]["causas"]


def test_otimizacao_sem_tripulantes_devolve_400(usuario_logado):
    resposta = usuario_logado.post(
        "/api/otimizacao", json={"base": "GRU", "tripulantes": [], "voos": []}
    )
    assert resposta.status_code == 400


def test_execucao_fica_registrada_na_auditoria(app, usuario_logado):
    """A trilha de auditoria gravou a execução — prova para o capítulo de
    resultados de que o CP-SAT rodou de verdade."""
    usuario_logado.post(
        "/api/otimizacao",
        json={
            "base": "GRU",
            "tripulantes": [{"id": "t1", "nome": "Rafael", "horas_acumuladas": 1.0, "limite_horas": 11.0}],
            "voos": [{"id": "v1", "codigo": "TAM-1", "duracao_horas": 2.0}],
        },
    )
    with app.app_context():
        from db import transacao

        with transacao() as conexao:
            linha = conexao.execute(
                "SELECT status_solver FROM execucoes_otimizacao ORDER BY id DESC LIMIT 1"
            ).fetchone()

    assert linha is not None
    assert linha["status_solver"] in {"OPTIMAL", "FEASIBLE"}


def test_erro_interno_nao_vaza_detalhe(usuario_logado):
    """Payload com tipo errado não pode devolver stack trace nem SQL."""
    resposta = usuario_logado.post(
        "/api/otimizacao",
        data=json.dumps({"base": "GRU", "tripulantes": "x", "voos": []}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    corpo = resposta.get_json()
    assert "campos" in corpo
    assert "Traceback" not in json.dumps(corpo)
