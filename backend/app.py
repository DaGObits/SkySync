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

# Carrega o .env explicitamente. O Flask só faz isso sozinho quando o
# python-dotenv está instalado — e depender disso silenciosamente foi o que
# fez a app subir sem DATABASE_URL. Aqui a falha é explícita.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.from_object(get_config(config_name)())

    _configurar_logging(app)
    _configurar_cors(app)
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

        try:
            with transacao() as conexao:
                linha = conexao.execute("SELECT 1 AS ok").fetchone()
            banco = {"ok": bool(linha), "backend": "postgres"}
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
                    "versao": "3.0.0",
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
        destino = app.config["DATABASE_URL"] or "sqlite (teste)"
        print("Esquema aplicado com sucesso.")
        print(f"  banco: {destino[:45]}...")

    @app.cli.command("seed-malha")
    def seed_malha_cmd():
        """Carrega os aeroportos da malha no banco. Não precisa de psql."""
        from dados.malha_seed import contar, semear
        from db import transacao

        with transacao() as conexao:
            inseridos = semear(conexao)
        with transacao() as conexao:
            total = contar(conexao)

        print(f"Malha carregada: {inseridos} aeroporto(s) inserido(s).")
        print(f"  total na tabela: {total}")

    @app.cli.command("diagnostico")
    def diagnostico_cmd():
        """Mostra o que a app leu do ambiente — útil quando algo não conecta.

        Não imprime a senha: só host e nome do banco.
        """
        import os
        from urllib.parse import urlparse

        url = app.config["DATABASE_URL"]
        print("Diagnóstico do SkySync")
        print(f"  ambiente        : {os.getenv('SKYSYNC_ENV', 'development')}")
        tem_env = (Path(app.root_path) / ".env").exists()
        print(f"  arquivo .env    : {'encontrado' if tem_env else 'NÃO ENCONTRADO'}")
        print(f"  DATABASE_URL    : {'definida' if url else 'VAZIA'}")
        if url:
            partes = urlparse(url)
            print(f"    host          : {partes.hostname}")
            print(f"    database      : {partes.path.lstrip('/')}")
        tem_chave = bool(os.getenv("SKYSYNC_SECRET_KEY"))
        print(f"  SECRET_KEY      : {'definida' if tem_chave else 'usando default'}")
        print(f"  psycopg         : {'instalado' if db.psycopg else 'NÃO INSTALADO'}")

    @app.cli.command("check-solver")
    def check_solver_cmd():
        """Roda um caso do otimizador — smoke test do CP-SAT com composição."""
        from optimizer.solver import otimizar

        tripulantes = []
        for cargo, quantidade in (("Comandante", 1), ("Copiloto", 1), ("Comissário", 3)):
            for i in range(quantidade):
                tripulantes.append(_tripulante_de_teste(cargo, f"{cargo[:2].lower()}{i}"))

        from models import Voo

        voos = [
            Voo(id="v1", codigo="TAM-3482", origem="GRU", destino="VCP",
                duracao_horas=2.0, pouso_noturno=False, prioridade=1),
        ]

        solucao = otimizar("GRU", tripulantes, voos, limite_horas=11.0)
        for a in solucao.alocacoes:
            print(f"  {a.voo_codigo} -> {a.tripulante_nome} [{a.cargo}]")
        print(
            f"status={solucao.status} alocacoes={solucao.total_alocacoes} "
            f"composicao={solucao.composicao_aplicada}"
        )


def _tripulante_de_teste(cargo: str, tid: str):
    from models import Tripulante

    return Tripulante(
        id=tid, nome=f"{cargo} {tid}", cargo=cargo, base="GRU",
        horas_acumuladas=1.0, limite_horas=11.0,
    )


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
