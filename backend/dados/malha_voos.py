"""Gera uma malha aérea realista a partir dos aeroportos do banco.

Os VOOS são reais no sentido operacional: origem e destino existem na malha,
a duração vem da distância geográfica (Haversine) e a partida se distribui ao
longo do dia como uma malha doméstica de verdade. Os NÚMEROS de voo e as
aeronaves são sintéticos.

A malha vem do BANCO (`dados.malha`) — são os 97 aeroportos regulares.

Uso:
    from dados.malha_voos import gerar_voos
    voos = gerar_voos(quantidade=140, base="GRU", seed=42)
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from dados.malha import distancia_km, malha, por_iata

#: Companhias brasileiras, usadas nos códigos de voo.
COMPANHIAS = ("TAM", "GLO", "AZU")

#: Modelos por faixa de distância — narrow-body no curto, wide-body no longo.
AERONAVES = {
    "curto": ("A320", "B737", "E195"),
    "medio": ("A320", "B738", "A321"),
    "longo": ("A321", "B738", "A330"),
}

#: Faixas de duração por distância (km): (limite, min_h, max_h).
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
    partida: str
    chegada: str
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
    """Gera a malha. Reproduzível: a mesma seed produz os mesmos voos."""
    rng = random.Random(seed)
    codigos = [a.iata for a in malha()]
    indice = por_iata()

    voos: list[VooGerado] = []
    codigos_usados: set[str] = set()

    for i in range(quantidade):
        if rng.random() < 0.45 and base in indice:
            origem = base
        else:
            origem = rng.choice(codigos)

        destino = rng.choice(codigos)
        while destino == origem:
            destino = rng.choice(codigos)

        km = distancia_km(origem, destino)
        duracao = _duracao(km, rng)

        partida_min = rng.randint(5 * 60, 23 * 60 + 30)
        chegada_min = partida_min + int(round(duracao * 60))

        hora_chegada = (chegada_min // 60) % 24
        noturno = hora_chegada >= 21 or hora_chegada < 6

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
