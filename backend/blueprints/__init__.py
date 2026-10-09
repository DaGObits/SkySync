"""Blueprints da API do SkySync."""

from blueprints import escalas, otimizacao, perfil

TODOS = (escalas.bp, perfil.bp, otimizacao.bp)

__all__ = ["TODOS", "escalas", "perfil", "otimizacao"]
