"""Blueprints da API do SkySync."""

from blueprints import auth, cenarios, escalas, escalas_voos, otimizacao, perfil, tripulantes

# Ordem de registro. O Flask roteia por url_prefix, entao a ordem aqui e so
# legibilidade.
TODOS = (
    auth.bp,
    perfil.bp,
    escalas.bp,
    otimizacao.bp,
    cenarios.bp,
    tripulantes.bp,
    escalas_voos.bp,
)

__all__ = [
    "TODOS",
    "auth",
    "cenarios",
    "escalas",
    "otimizacao",
    "perfil",
    "tripulantes",
]
