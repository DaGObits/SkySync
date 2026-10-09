"""Dados operacionais do SkySync: malha aérea, nomes e gerador de cenários."""

from dados.gerador import Cenario, gerar_cenario
from dados.malha import HUBS, MALHA, POR_IATA, Aeroporto

__all__ = ["MALHA", "POR_IATA", "HUBS", "Aeroporto", "gerar_cenario", "Cenario"]
