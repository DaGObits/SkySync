"""Dados operacionais do SkySync.

  malha        — leitura da malha aérea (tabela `aeroportos`)
  malha_seed   — carga inicial da malha a partir do arquivo de referência
  malha_voos   — geração de malha de voos realista
  gerador      — geração de cenários completos (tripulantes + voos)
  nomes        — base de nomes sintéticos

A malha vive no BANCO: `malha()` consulta a tabela `aeroportos` (97 aeroportos
regulares, 27 UFs). Não há lista de aeroportos em Python.
"""

from dados.gerador import Cenario, gerar_cenario
from dados.malha import (
    REGIOES,
    Aeroporto,
    bases_por_regiao,
    distancia_km,
    hubs,
    localizar,
    malha,
    por_iata,
)

__all__ = [
    "REGIOES",
    "Aeroporto",
    "bases_por_regiao",
    "distancia_km",
    "hubs",
    "localizar",
    "malha",
    "por_iata",
    "gerar_cenario",
    "Cenario",
]
