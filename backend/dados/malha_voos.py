"""Gera uma malha aerea realista a partir dos 36 aeroportos do banco.

Os VOOS sao reais no sentido operacional: origem e destino existem, a duracao
vem da distancia geografica entre eles (Haversine) e a partida se distribui ao
longo do dia como uma malha domestica de verdade. Os NUMEROS de voo e as placas
sao sinteticos.

Distribuicao pensada para a operacao brasileira:
  * 45% dos voos partem do hub principal (GRU por padrao)
  * os demais partem de qualquer aeroporto da malha
  * duracao calculada pela distancia, nao sorteada
  * partidas espalhadas entre 05:00 e 23:30
  * ~25% com pouso noturno (aciona a restricao 117.135)

Uso:
    from dados.malha_voos import gerar_voos
    voos = gerar_voos(quantidade=140, base="GRU", seed=42)
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from dados.malha import MALHA, POR_IATA

#: Companhias brasileiras, usadas nos codigos de voo.
COMPANHIAS = ("TAM", "GLO", "AZU", "PTB")

#: Modelos por faixa de distancia — narrow-body no curto, wide-body no longo.
AERONAVES = {
    "curto": ("A320", "B737", "E195"),
    "medio": ("A320", "B738", "A321"),
    "longo": ("A321", "B738", "A330"),
}

#: Faixas de duracao por distancia (km): (limite, min_h, max_h).
FAIXAS = (
    (400, 0.7, 1.3),
    (800, 1.3, 2.1),
    (1400, 2.1, 3.1),
    (9999, 3.1, 4.6),
)


@dataclass
class VooGerado:
    id: str
    codigo: str
    origem: str
    destino: str
    partida: str          # HH:MM
    chegada: str          # HH:MM
    duracao_horas: float
    distancia_km: float
    aeronave: str
    pouso_noturno: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "codigo": self.codigo,
            "origem": self.origem,
            "destino": self.destino,
            "partida": self.partida,
            "chegada": self.chegada,
            "duracao_horas": self.duracao_horas,
            "distancia_km": self.distancia_km,
            "aeronave": self.aeronave,
            "pouso_noturno": self.pouso_noturno,
        }


def distancia_km(iata_a: str, iata_b: str) -> float:
    """Distancia entre dois aeroportos da malha (Haversine)."""
    import math

    a = POR_IATA.get(iata_a)
    b = POR_IATA.get(iata_b)
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


def _duracao(km: float, rng: random.Random) -> float:
    for limite, minimo, maximo in FAIXAS:
        if km <= limite:
            return round(rng.uniform(minimo, maximo), 2)
    return 4.6


def _aeronave(km: float, rng: random.Random) -> str:
    if km <= 700:
        return rng.choice(AERONAVES["curto"])
    if km <= 1500:
        return rng.choice(AERONAVES["medio"])
    return rng.choice(AERONAVES["longo"])


def _hhmm(minutos_totais: int) -> str:
    minutos_totais %= 24 * 60
    return f"{minutos_totais // 60:02d}:{minutos_totais % 60:02d}"


def gerar_voos(quantidade: int = 140, base: str = "GRU", seed: int = 42) -> list[VooGerado]:
    """Gera a malha. Reproduzivel: a mesma seed produz os mesmos voos."""
    rng = random.Random(seed)
    voos: list[VooGerado] = []
    codigos_usados: set[str] = set()

    for i in range(quantidade):
        if rng.random() < 0.45 and base in POR_IATA:
            origem = base
        else:
            origem = rng.choice(MALHA).iata

        destino = rng.choice(MALHA).iata
        while destino == origem:
            destino = rng.choice(MALHA).iata

        km = distancia_km(origem, destino)
        duracao = _duracao(km, rng)

        # Partida entre 05:00 e 23:30.
        partida_min = rng.randint(5 * 60, 23 * 60 + 30)
        chegada_min = partida_min + int(round(duracao * 60))

        # Pouso noturno: chegada depois das 21:00 ou antes das 06:00.
        hora_chegada = (chegada_min // 60) % 24
        noturno = hora_chegada >= 21 or hora_chegada < 6

        # Codigo unico, como na operacao real.
        while True:
            codigo = f"{rng.choice(COMPANHIAS)}-{rng.randint(1000, 9999)}"
            if codigo not in codigos_usados:
                codigos_usados.add(codigo)
                break

        voos.append(
            VooGerado(
                id=f"V{i + 1:04d}",
                codigo=codigo,
                origem=origem,
                destino=destino,
                partida=_hhmm(partida_min),
                chegada=_hhmm(chegada_min),
                duracao_horas=duracao,
                distancia_km=km,
                aeronave=_aeronave(km, rng),
                pouso_noturno=noturno,
            )
        )

    return voos
