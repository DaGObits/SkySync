"""Blueprints da API do SkySync."""

from blueprints import (
    auth,
    cenarios,
    disrupcoes,
    escalas,
    escalas_voos,
    mapa,
    jornadas_simulacao,
    otimizacao,
    perfil,
    operacao,
    tripulantes,
)

# Ordem de registro. O Flask roteia por url_prefix, entao a ordem aqui e so
# legibilidade.
TODOS = (
    auth.bp,
    perfil.bp,
    operacao.bp,
    jornadas_simulacao.bp,
    disrupcoes.bp,
    escalas.bp,
    otimizacao.bp,
    cenarios.bp,
    tripulantes.bp,
    escalas_voos.bp,
    mapa.bp,
)

__all__ = [
    "TODOS",
    "auth",
    "cenarios",
    "disrupcoes",
    "escalas",
    "mapa",
    "jornadas_simulacao",
    "otimizacao",
    "perfil",
    "operacao",
    "tripulantes",
]
