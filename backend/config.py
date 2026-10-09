"""Configuração central do SkySync.

Todos os valores que mudam entre ambientes (dev / teste / produção) ficam aqui.
Nada de credencial hardcoded: tudo vem de variável de ambiente com default seguro.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _normalizar_url(url: str) -> str:
    """Ajustes que o psycopg exige e os provedores não entregam.

    Neon, Supabase e Heroku entregam a URL no formato `postgres://`, que o
    psycopg rejeita — o esquema aceito é `postgresql://`. Também garantimos
    `sslmode=require`, porque banco em nuvem sem TLS recusa a conexão.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "sslmode=" not in url and "localhost" not in url and "127.0.0.1" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


class Config:
    """Base — usada em produção."""

    # --- Flask ---
    SECRET_KEY = os.getenv("SKYSYNC_SECRET_KEY", "troque-esta-chave-em-producao")
    DEBUG = False
    TESTING = False
    JSON_SORT_KEYS = False

    # --- Banco de dados (PostgreSQL) ---
    # A URL de conexão vem inteira do ambiente. É o único dado sensível do
    # projeto e não pode estar no código nem no Git.
    DATABASE_URL = _normalizar_url(os.getenv("DATABASE_URL", ""))
    SCHEMA_PATH = os.getenv("SKYSYNC_SCHEMA_PATH", str(BASE_DIR / "schema.sql"))
    DB_CONNECT_TIMEOUT = int(os.getenv("SKYSYNC_DB_TIMEOUT", "10"))

    # --- Sessão ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SKYSYNC_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SKYSYNC_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8

    # --- CORS ---
    # Com credenciais (cookie de sessão), o CORS precisa nomear as origens —
    # curinga `*` é rejeitado pelo navegador quando há credenciais.
    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "SKYSYNC_CORS_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500,"
            "http://localhost:5000,http://127.0.0.1:5000",
        ).split(",")
        if o.strip()
    ]

    # --- Otimizador ---
    SOLVER_MAX_TIME_SECONDS = float(os.getenv("SKYSYNC_SOLVER_MAX_TIME", "10"))
    SOLVER_DEFAULT_HOUR_LIMIT = float(os.getenv("SKYSYNC_HOUR_LIMIT", "11.0"))
    MAX_PAYLOAD_BYTES = int(os.getenv("SKYSYNC_MAX_PAYLOAD", str(2 * 1024 * 1024)))


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    # Testes não tocam o banco de nuvem: usam SQLite em memória pelo mesmo
    # código, graças ao adaptador em db.py.
    DB_BACKEND = "sqlite"
    SQLITE_PATH = ":memory:"
    SOLVER_MAX_TIME_SECONDS = 5.0
    SECRET_KEY = "chave-de-teste"


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
