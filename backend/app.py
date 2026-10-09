"""SkySync — ponto de entrada da aplicação.

Este arquivo só monta a app: configuração, CORS, blueprints, tratamento de erro
e CLI. Nenhuma regra de negócio mora aqui.
"""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import blueprints
import db
from config import get_config


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.from_object(get_config(config_name)())

    _configurar_logging(app)
    _configurar_cors(app)

    # Conexão por-requisição fechada no teardown — é isso que impede o vazamento
    # de conexões que existia quando cada handler chamava close() só no sucesso.
    db.register(app)

    for bp in blueprints.TODOS:
        app.register_blueprint(bp)

    _registrar_handlers_de_erro(app)
    _registrar_rotas_base(app)
    _registrar_cli(app)
    return app


def _configurar_logging(app: Flask) -> None:
    nivel = logging.DEBUG if app.config["DEBUG"] else logging.INFO
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    app.logger.setLevel(nivel)


def _configurar_cors(app: Flask) -> None:
    # Com cookie de sessão, o navegador exige origem nomeada e credenciais
    # explícitas — curinga `*` é recusado quando há credenciais.
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )


def _registrar_handlers_de_erro(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def tratar_http_exception(err: HTTPException):
        return jsonify({"erro": err.description, "status": err.code}), err.code

    @app.errorhandler(Exception)
    def tratar_excecao(err: Exception):
        # Detalhe vai para o log do servidor; o cliente recebe mensagem genérica.
        app.logger.exception("erro não tratado")
        return (
            jsonify(
                {
                    "erro": "erro interno do servidor",
                    "mensagem": "a falha foi registrada e será investigada",
                }
            ),
            500,
        )


def _registrar_rotas_base(app: Flask) -> None:
    @app.get("/api/health")
    def health():
        """Verifica app e banco — é o que a banca roda primeiro."""
        from db import ErroDeBanco, transacao

        banco = {"ok": False, "backend": "postgres"}
        try:
            with transacao() as conexao:
                linha = conexao.execute("SELECT 1 AS ok").fetchone()
            banco = {"ok": bool(linha), "backend": "postgres" if conexao else "desconhecido"}
        except ErroDeBanco as err:
            banco = {"ok": False, "backend": "postgres", "erro": str(err)}
        except Exception:
            app.logger.exception("health check falhou ao consultar o banco")
            banco = {"ok": False, "backend": "postgres", "erro": "falha de conexão"}

        return (
            jsonify(
                {
                    "status": "ok" if banco["ok"] else "degradado",
                    "servico": "skysync-api",
                    "versao": "2.1.0",
                    "banco": banco,
                }
            ),
            200 if banco["ok"] else 503,
        )

    @app.get("/")
    def index():
        candidato = Path(app.static_folder or "") / "index.html"
        if candidato.exists():
            return app.send_static_file("index.html")
        return jsonify({"servico": "skysync-api", "docs": "/api/health"})


def _registrar_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_cmd():
        """Cria/atualiza o esquema no banco configurado em DATABASE_URL."""
        db.init_db()
        print("Esquema aplicado com sucesso.")
        print(f"  banco: {app.config['DATABASE_URL'][:40] or 'sqlite (teste)'}...")

    @app.cli.command("check-solver")
    def check_solver_cmd():
        """Roda um caso pequeno do otimizador — smoke test do CP-SAT."""
        from models import RequisicaoOtimizacao
        from optimizer.solver import otimizar

        requisicao = RequisicaoOtimizacao.from_payload(
            {
                "base": "GRU",
                "tripulantes": [
                    {"id": "t1", "nome": "Rafael Nunes", "horas_acumuladas": 6.0, "limite_horas": 11.0},
                    {"id": "t2", "nome": "Lucas Mendes", "horas_acumuladas": 2.0, "limite_horas": 11.0},
                ],
                "voos": [
                    {"id": "v1", "codigo": "TAM-3482", "duracao_horas": 4.5, "origem": "GRU", "destino": "VCP"},
                    {"id": "v2", "codigo": "GLO-1207", "duracao_horas": 3.0, "origem": "CGH", "destino": "SSA"},
                ],
            },
            limite_padrao=11.0,
        )
        solucao = otimizar(
            requisicao.base, requisicao.tripulantes, requisicao.voos, requisicao.limite_horas
        )
        for a in solucao.alocacoes:
            print(f"  {a.voo_codigo} -> {a.tripulante_nome} ({a.duracao_horas}h)")
        print(f"status={solucao.status} conformidade={solucao.conformidade}%")


app = create_app()


if __name__ == "__main__":
    import os

    # debug vem do ambiente, nunca de um True fixo: o debugger do Werkzeug em
    # modo debug permite execução de código pelo navegador.
    app.run(
        host=os.getenv("SKYSYNC_HOST", "127.0.0.1"),
        port=int(os.getenv("SKYSYNC_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
