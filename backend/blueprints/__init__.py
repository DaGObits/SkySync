"""Blueprints da API do SkySync."""

from blueprints import auth, escalas, otimizacao, perfil

# Ordem de registro dos blueprints. O Flask roteia por url_prefix, então a
# ordem aqui é só legibilidade.
TODOS = (auth.bp, perfil.bp, escalas.bp, otimizacao.bp)

__all__ = ["TODOS", "auth", "escalas", "perfil", "otimizacao"]
