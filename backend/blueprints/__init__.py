"""Blueprints da API do SkySync."""

from blueprints import auth, cenarios, escalas, otimizacao, perfil

# Ordem de registro dos blueprints. O Flask roteia por url_prefix, então a
# ordem aqui é só legibilidade.
TODOS = (auth.bp, perfil.bp, escalas.bp, otimizacao.bp, cenarios.bp)

__all__ = ["TODOS", "auth", "cenarios", "escalas", "perfil", "otimizacao"]
