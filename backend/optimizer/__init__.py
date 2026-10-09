"""Pacote do motor de otimização do SkySync.

Ponto de entrada público:

    from optimizer.solver import otimizar, OtimizacaoInviavel
"""
from optimizer.solver import Alocacao, OtimizacaoInviavel, Solucao, otimizar

__all__ = ["otimizar", "OtimizacaoInviavel", "Solucao", "Alocacao"]
