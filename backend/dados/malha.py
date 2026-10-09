"""Malha aérea brasileira — os vértices do grafo.

Aeroportos com código IATA real. É este conjunto que alimenta o grafo descrito
no pré-projeto: os aeroportos são os vértices e os voos são as arestas que os
conectam.

O campo `hub` marca os aeroportos que concentram a malha — na modelagem, são
as bases onde as tripulações ficam estacionadas.

Coordenadas aproximadas, usadas para calcular distância e duração de voo.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Aeroporto:
    iata: str
    cidade: str
    uf: str
    regiao: str
    lat: float
    lon: float
    hub: bool = False


MALHA: tuple[Aeroporto, ...] = (
    # --- Sudeste ---
    Aeroporto("GRU", "São Paulo", "SP", "Sudeste", -23.43, -46.47, hub=True),
    Aeroporto("CGH", "São Paulo", "SP", "Sudeste", -23.63, -46.66, hub=True),
    Aeroporto("VCP", "Campinas", "SP", "Sudeste", -23.01, -47.13),
    Aeroporto("GIG", "Rio de Janeiro", "RJ", "Sudeste", -22.81, -43.25, hub=True),
    Aeroporto("SDU", "Rio de Janeiro", "RJ", "Sudeste", -22.91, -43.16),
    Aeroporto("CNF", "Belo Horizonte", "MG", "Sudeste", -19.62, -43.97, hub=True),
    Aeroporto("UDI", "Uberlândia", "MG", "Sudeste", -18.88, -48.23),
    Aeroporto("VIX", "Vitória", "ES", "Sudeste", -20.26, -40.29),
    Aeroporto("SJK", "São José dos Campos", "SP", "Sudeste", -23.23, -45.86),
    # --- Sul ---
    Aeroporto("CWB", "Curitiba", "PR", "Sul", -25.53, -49.17),
    Aeroporto("FLN", "Florianópolis", "SC", "Sul", -27.67, -48.55),
    Aeroporto("POA", "Porto Alegre", "RS", "Sul", -29.99, -51.17),
    Aeroporto("NVT", "Navegantes", "SC", "Sul", -26.88, -48.65),
    Aeroporto("LDB", "Londrina", "PR", "Sul", -23.33, -51.13),
    # --- Centro-Oeste ---
    Aeroporto("BSB", "Brasília", "DF", "Centro-Oeste", -15.87, -47.92, hub=True),
    Aeroporto("CGB", "Cuiabá", "MT", "Centro-Oeste", -15.65, -56.12),
    Aeroporto("GYN", "Goiânia", "GO", "Centro-Oeste", -16.63, -49.22),
    Aeroporto("CGR", "Campo Grande", "MS", "Centro-Oeste", -20.47, -54.67),
    # --- Nordeste ---
    Aeroporto("SSA", "Salvador", "BA", "Nordeste", -12.91, -38.33, hub=True),
    Aeroporto("REC", "Recife", "PE", "Nordeste", -8.13, -34.92, hub=True),
    Aeroporto("FOR", "Fortaleza", "CE", "Nordeste", -3.78, -38.53, hub=True),
    Aeroporto("NAT", "Natal", "RN", "Nordeste", -5.77, -35.37),
    Aeroporto("MCZ", "Maceió", "AL", "Nordeste", -9.51, -35.79),
    Aeroporto("JPA", "João Pessoa", "PB", "Nordeste", -7.15, -34.95),
    Aeroporto("THE", "Teresina", "PI", "Nordeste", -5.06, -42.82),
    Aeroporto("SLZ", "São Luís", "MA", "Nordeste", -2.58, -44.23),
    Aeroporto("AJU", "Aracaju", "SE", "Nordeste", -10.98, -37.07),
    Aeroporto("PHB", "Parnaíba", "PI", "Nordeste", -2.89, -41.73),
    # --- Norte ---
    Aeroporto("MAO", "Manaus", "AM", "Norte", -3.04, -60.05, hub=True),
    Aeroporto("BEL", "Belém", "PA", "Norte", -1.38, -48.48, hub=True),
    Aeroporto("PVH", "Porto Velho", "RO", "Norte", -8.71, -63.90),
    Aeroporto("RBR", "Rio Branco", "AC", "Norte", -9.87, -67.89),
    Aeroporto("MCP", "Macapá", "AP", "Norte", 0.05, -51.07),
    Aeroporto("STM", "Santarém", "PA", "Norte", -2.42, -54.79),
    Aeroporto("BVB", "Boa Vista", "RR", "Norte", 2.84, -60.69),
    Aeroporto("PMW", "Palmas", "TO", "Norte", -10.29, -48.36),
)

#: Índice por código IATA, para consulta rápida.
POR_IATA: dict[str, Aeroporto] = {a.iata: a for a in MALHA}

#: Códigos das bases onde tripulações ficam estacionadas.
HUBS: tuple[str, ...] = tuple(a.iata for a in MALHA if a.hub)

#: Regiões do país.
REGIOES: tuple[str, ...] = ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul")
