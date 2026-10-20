"""Blueprints da API do SkySync."""

from blueprints import (
    ao_vivo,
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
    ao_vivo.bp,
    mapa.bp,
)

__all__ = [
    "TODOS",
    "ao_vivo",
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
