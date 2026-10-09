"""SkySync — ponto de entrada da aplicação.

Este arquivo só monta a app: configuração, CORS, blueprints, tratamento de erro
e o CLI. Nenhuma regra de negócio mora aqui.
"""
from __future__ import annotations

import logging
import os
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
    # de conexões que existia quando cada handler chamava conn.close() só no
    # caminho de sucesso.
    db.register(app)

    for bp in blueprints.TODOS:
        app.register_blueprint(bp)

    _registrar_handlers_de_erro(app)
    _registrar_rotas_base(app)
    _registrar_cli(app)

    with app.app_context():
        db.init_db()

    return app


def _configurar_logging(app: Flask) -> None:
    nivel = logging.DEBUG if app.config["DEBUG"] else logging.INFO
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    app.logger.setLevel(nivel)


def _configurar_cors(app: Flask) -> None:
    # Antes: CORS(app) liberava qualquer origem. Agora só as do config.
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
    )


def _registrar_handlers_de_erro(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def tratar_http_exception(err: HTTPException):
        return jsonify({"erro": err.description, "status": err.code}), err.code

    @app.errorhandler(Exception)
    def tratar_excecao(err: Exception):
        # Detalhe vai para o log do servidor; o cliente recebe mensagem genérica.
        # A versão antiga devolvia err.message do SQLite, expondo caminhos de
        # arquivo e nomes de tabela para quem chamasse a API.
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
        return jsonify(
            {
                "status": "ok",
                "servico": "skysync-api",
                "versao": "2.0.0",
                "env": os.getenv("SKYSYNC_ENV", "development"),
            }
        )

    @app.get("/")
    def index():
        # Serve o painel se ele estiver em static/, sem quebrar quando não está.
        candidato = Path(app.static_folder or "") / "index.html"
        if candidato.exists():
            return app.send_static_file("index.html")
        return jsonify({"servico": "skysync-api", "docs": "/api/health"})


def _registrar_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_cmd():
        """Recria o esquema do banco a partir de schema.sql."""
        db.init_db()
        print(f"Banco inicializado em {app.config['DB_PATH']}")

    @app.cli.command("check-solver")
    def check_solver_cmd():
        """Roda um caso pequeno do otimizador — útil como smoke test."""
        from models import RequisicaoOtimizacao
        from optimizer.solver import otimizar

        requisicao = RequisicaoOtimizacao.from_payload(
            {
                "base": "GRU",
                "tripulantes": [
                    {
                        "id": "t1",
                        "nome": "Rafael Nunes",
                        "horas_acumuladas": 6.0,
                        "limite_horas": 11.0,
                    },
                    {
                        "id": "t2",
                        "nome": "Lucas Mendes",
                        "horas_acumuladas": 2.0,
                        "limite_horas": 11.0,
                    },
                ],
                "voos": [
                    {"id": "v1", "codigo": "TAM-3482", "duracao_horas": 4.5, "origem": "GRU", "destino": "VCP"},
                    {"id": "v2", "codigo": "GLO-1207", "duracao_horas": 3.0, "origem": "CGH", "destino": "SSA"},
                ],
            },
            limite_padrao=11.0,
        )
        solucao = otimizar(
            requisicao.base,
            requisicao.tripulantes,
            requisicao.voos,
            requisicao.limite_horas,
        )
        for a in solucao.alocacoes:
            print(f"  {a.voo_codigo} -> {a.tripulante_nome} ({a.duracao_horas}h)")
        print(f"status={solucao.status} conformidade={solucao.conformidade}%")


app = create_app()


if __name__ == "__main__":
    # debug vem do ambiente, nunca de um True fixo no código: o debugger do
    # Werkzeug em modo debug permite execução de código pelo navegador.
    app.run(
        host=os.getenv("SKYSYNC_HOST", "127.0.0.1"),
        port=int(os.getenv("SKYSYNC_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
