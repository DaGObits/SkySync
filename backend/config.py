"""Configuração central do SkySync.

Todos os valores que mudam entre ambientes (dev / teste / produção) ficam aqui.
Nada de credencial hardcoded: tudo vem de variável de ambiente com default seguro.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base — usada em produção."""

    # --- Flask ---
    SECRET_KEY = os.getenv("SKYSYNC_SECRET_KEY", "troque-esta-chave-em-producao")
    DEBUG = False
    TESTING = False
    JSON_SORT_KEYS = False

    # --- Banco de dados ---
    # Caminho absoluto para o SQLite, sobrescrevível por env.
    DB_PATH = os.getenv("SKYSYNC_DB_PATH", str(BASE_DIR / "skysync.db"))
    SCHEMA_PATH = os.getenv("SKYSYNC_SCHEMA_PATH", str(BASE_DIR / "schema.sql"))

    # --- CORS ---
    # Lista de origens permitidas, separadas por vírgula.
    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "SKYSYNC_CORS_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
        ).split(",")
        if o.strip()
    ]

    # --- Otimizador ---
    # Teto de tempo do CP-SAT. Sem isso, um modelo mal-formulado roda minutos
    # e trava a requisição.
    SOLVER_MAX_TIME_SECONDS = float(os.getenv("SKYSYNC_SOLVER_MAX_TIME", "10"))
    # Limite de horas de jornada (RBAC 117) usado como restrição padrão.
    SOLVER_DEFAULT_HOUR_LIMIT = float(os.getenv("SKYSYNC_HOUR_LIMIT", "11.0"))
    # Tamanho máximo do payload aceito na história de escalas (bytes).
    MAX_PAYLOAD_BYTES = int(os.getenv("SKYSYNC_MAX_PAYLOAD", str(2 * 1024 * 1024)))


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    DB_PATH = ":memory:"
    SOLVER_MAX_TIME_SECONDS = 5.0


class ProductionConfig(Config):
    DEBUG = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    """Devolve a classe de config do ambiente pedido (ou o default por env)."""
    name = name or os.getenv("SKYSYNC_ENV", "development")
    return _CONFIGS.get(name, DevelopmentConfig)
