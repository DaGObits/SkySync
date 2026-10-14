"""Malha aérea — leitura do banco de dados.

FONTE ÚNICA: a tabela `aeroportos`. A lista de 97 aeroportos regulares vive no
banco (importada de `aeroportos_voos_regulares_brasil.txt`), e este módulo é o
único ponto de acesso a ela.

POR QUE FUNÇÕES, E NÃO CONSTANTES:

A versão anterior expunha `MALHA`, `POR_IATA` e `HUBS` como constantes de
módulo, montadas de uma lista literal em Python. Fazer o mesmo com o banco não
funciona: a consulta precisa de uma conexão, e a conexão precisa de um
`app_context` do Flask. Uma constante avaliada na importação quebraria qualquer
módulo que importasse este sem contexto — os testes, por exemplo.

Então a interface é de funções. Cada chamada consulta o banco e devolve os
dados. Para quem chama várias vezes na mesma requisição, `cache=True` evita
repetir a consulta.

USO:

    from dados.malha import malha, por_iata, hubs

    aeroportos = malha()                 # lista de Aeroporto
    indice = por_iata()                  # dict iata -> Aeroporto
    bases = hubs()                       # tuple de iatas dos hubs

O `optimizer/solver.py` NÃO importa este módulo: ele recebe a malha por
parâmetro. É o que mantém a regra de o motor rodar sem Flask.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Regiões do país.
REGIOES: tuple[str, ...] = ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul")

#: Cache por requisição. A chave é o id do app_context, para não vazar dados
#: entre requisições diferentes.
_cache: dict[int, dict[str, Any]] = {}


@dataclass(frozen=True)
class Aeroporto:
    iata: str
    cidade: str
    uf: str
    regiao: str
    lat: float
    lon: float
    hub: bool = False

    def to_dict(self) -> dict:
        return {
            "iata": self.iata,
            "cidade": self.cidade,
            "uf": self.uf,
            "regiao": self.regiao,
            "latitude": self.lat,
            "longitude": self.lon,
            "hub": self.hub,
        }


def _carregar() -> dict[str, Any]:
    """Consulta o banco uma vez por requisição e guarda o resultado."""
    from flask import g

    try:
        chave = id(g)
    except RuntimeError:
        # Fora do contexto Flask: consulta direta, sem cache.
        return _consultar()

    if chave in _cache:
        return _cache[chave]

    dados = _consultar()
    _cache[chave] = dados
    return dados


def _consultar() -> dict[str, Any]:
    from db import transacao

    with transacao() as conexao:
        linhas = conexao.execute(
            """
            SELECT iata, cidade, uf, regiao, latitude, longitude, hub
            FROM aeroportos
            ORDER BY iata
            """
        ).fetchall()

    aeroportos = [
        Aeroporto(
            iata=l["iata"],
            cidade=l["cidade"],
            uf=l["uf"],
            regiao=l["regiao"],
            lat=float(l["latitude"]) if l["latitude"] is not None else 0.0,
            lon=float(l["longitude"]) if l["longitude"] is not None else 0.0,
            hub=bool(l["hub"]),
        )
        for l in linhas
    ]

    return {
        "lista": aeroportos,
        "por_iata": {a.iata: a for a in aeroportos},
        "hubs": tuple(a.iata for a in aeroportos if a.hub),
        "por_regiao": _agrupar_por_regiao(aeroportos),
    }


def _agrupar_por_regiao(aeroportos: list[Aeroporto]) -> dict[str, set[str]]:
    por_regiao: dict[str, set[str]] = {}
    for a in aeroportos:
        por_regiao.setdefault(a.regiao, set()).add(a.iata)
    return por_regiao


def limpar_cache() -> None:
    """Descarta o cache. Útil em testes e depois de reimportar a malha."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Interface pública
# ---------------------------------------------------------------------------
def malha() -> list[Aeroporto]:
    """Todos os aeroportos, em ordem de IATA."""
    return _carregar()["lista"]


def por_iata() -> dict[str, Aeroporto]:
    """Índice por código IATA."""
    return _carregar()["por_iata"]


def hubs() -> tuple[str, ...]:
    """Códigos das bases que concentram a malha."""
    return _carregar()["hubs"]


def bases_por_regiao() -> dict[str, set[str]]:
    """Bases agrupadas por região — é o que o filtro de domínio usa.

    Um tripulante estacionado em Confins pode pegar um voo partindo de
    Guarulhos (mesma região). Já um comissário em Manaus não cobre um voo de
    Porto Alegre na mesma rodada.
    """
    return _carregar()["por_regiao"]


def distancia_km(iata_a: str, iata_b: str) -> float:
    """Distância entre dois aeroportos, por Haversine.

    Usada para estimar a duração dos voos — a duração vem da geografia, não
    de um sorteio.
    """
    import math

    indice = por_iata()
    a = indice.get(iata_a)
    b = indice.get(iata_b)
    # (as coordenadas vêm do banco, coluna latitude/longitude)
    if a is None or b is None:
        return 600.0

    raio = 6371.0
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a.lat))
        * math.cos(math.radians(b.lat))
        * math.sin(dlon / 2) ** 2
    )
    return round(2 * raio * math.asin(min(1.0, math.sqrt(h))), 1)


def localizar(iata: str) -> Aeroporto | None:
    """Um aeroporto pelo código, ou None."""
    return por_iata().get(iata)
