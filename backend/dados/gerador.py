"""Gerador de cenários operacionais.

Cria tripulantes e voos com parâmetros realistas da malha brasileira. Cada
chamada com a mesma `seed` produz exatamente o mesmo cenário — o que permite à
banca repetir um experimento e comparar os números.

DIMENSIONAMENTO POR BASE DE PARTIDA (a correção que importa): a versão anterior
escolhia as bases dos tripulantes por probabilidade — 60% nos hubs, 40% na
malha inteira. Isso deixava aeroportos secundários sem nenhum candidato, e um
único voo sem tripulante elegível torna o cenário inteiro INFEASIBLE.

Agora o gerador:

  1. sorteia os VOOS primeiro (origem e destino);
  2. conta quantos voos partem de cada aeroporto;
  3. distribui os tripulantes de acordo com essa contagem — cada base recebe
     o número de comandantes, copilotos e comissários necessários para cobrir
     os voos que partem dela, mais a folga.

Assim o filtro de domínio por base (raio_bases=1) fica seguro: há candidato
para todo voo, em toda base.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from dados.malha import HUBS, MALHA, POR_IATA
from dados.nomes import nome_completo

#: Companhias usadas nos códigos de voo.
COMPANHIAS = ("TAM", "GLO", "AZU", "PTB")

#: Composição de um narrow-body (A320 / 737).
COMPOSICAO_PADRAO = {"Comandante": 1, "Copiloto": 1, "Comissário": 3}

#: Teto de jornada por perfil de operação (RBAC 117.030 / 117.040).
LIMITES_RBAC = (
    (9.5, "9h30 (não aclimatizado)"),
    (10.0, "10h00 (múltiplos pousos / fuso)"),
    (11.0, "11h00 (pouso à noite)"),
    (11.5, "11h30 (limite adaptado setor)"),
    (12.0, "12h00 (jornada diurna padrão)"),
    (13.0, "13h00 (extensão por revezamento)"),
    (14.0, "14h00 (tripulação reforçada)"),
)

#: Duração de voo por distância — aproximações de malha doméstica.
FAIXAS_DURACAO = (
    (300, 0.8, 1.4),
    (700, 1.4, 2.2),
    (1200, 2.2, 3.2),
    (9999, 3.2, 4.5),
)


@dataclass
class Cenario:
    seed: int
    base: str
    tripulantes: list = field(default_factory=list)
    voos: list = field(default_factory=list)
    parametros: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "base": self.base,
            "parametros": self.parametros,
            "tripulantes": [t.to_dict() for t in self.tripulantes],
            "voos": [v.to_dict() for v in self.voos],
        }

    def resumo(self) -> dict:
        por_cargo: dict[str, int] = {}
        for t in self.tripulantes:
            por_cargo[t.cargo] = por_cargo.get(t.cargo, 0) + 1
        return {
            "seed": self.seed,
            "base": self.base,
            "voos": len(self.voos),
            "alocacoes_necessarias": sum(COMPOSICAO_PADRAO.values()) * len(self.voos),
            "tripulantes": len(self.tripulantes),
            "tripulantes_por_cargo": por_cargo,
            "composicao": COMPOSICAO_PADRAO,
            "disrupcao": self.parametros.get("disrupcao"),
        }


def _distancia_km(iata_a: str, iata_b: str) -> float:
    """Distância aproximada entre dois aeroportos (Haversine)."""
    import math

    a = POR_IATA.get(iata_a)
    b = POR_IATA.get(iata_b)
    if a is None or b is None:
        return 500.0

    raio = 6371.0
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a.lat))
        * math.cos(math.radians(b.lat))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * raio * math.asin(min(1.0, math.sqrt(h)))


def _duracao_estimada(km: float, rng: random.Random) -> float:
    for limite, minimo, maximo in FAIXAS_DURACAO:
        if km <= limite:
            return round(rng.uniform(minimo, maximo), 2)
    return 4.5


def _par_de_aeroportos(rng: random.Random, base: str) -> tuple[str, str]:
    """Escolhe origem e destino. 45% dos voos partem da base do cenário."""
    if rng.random() < 0.45 and base in POR_IATA:
        origem = base
    else:
        origem = rng.choice(MALHA).iata

    destino = rng.choice(MALHA).iata
    while destino == origem:
        destino = rng.choice(MALHA).iata
    return origem, destino


def gerar_voos(
    voos: int, base: str, seed: int = 42
) -> tuple[list, random.Random]:
    """Primeira etapa: sorteia os voos. A distribuição de bases vem deles."""
    from models import Voo

    rng = random.Random(seed)
    lista_voos = []
    for i in range(voos):
        origem, destino = _par_de_aeroportos(rng, base)
        km = _distancia_km(origem, destino)
        duracao = _duracao_estimada(km, rng)
        noturno = rng.random() < 0.25

        lista_voos.append(
            Voo(
                id=f"v{i + 1:04d}",
                codigo=f"{rng.choice(COMPANHIAS)}-{rng.randint(1000, 9999)}",
                origem=origem,
                destino=destino,
                duracao_horas=duracao,
                pouso_noturno=noturno,
                prioridade=rng.choice((1, 1, 1, 2, 3)),
            )
        )
    return lista_voos, rng


def dimensionar_por_base(
    voos: list, composicao: dict, folga: float = 0.15, disrupcao: float = 0.0
) -> dict[str, dict[str, int]]:
    """Quantos tripulantes de cada cargo são necessários em CADA base.

    O dimensionamento segue os voos: uma base de onde partem 4 voos precisa de
    4 comandantes, 4 copilotos e 12 comissários — mais reserva.

    TRÊS REGRAS DE RESERVA, cada uma por um motivo concreto:

    1. **Piso mínimo de 1 reserva por cargo e por base.** Sem isso, uma base com
       um único voo recebia exatamente 1 comandante — e bastava a disrupção
       marcá-lo como indisponível para aquele voo ficar impossível. Um piso
       absoluto é o que garante que toda base sobreviva a uma baixa.

    2. **A folga precisa superar a disrupção esperada.** Se ~15% do pool fica
       indisponível, uma reserva de 15% não cobre as baixas: o cenário nasce
       inviável por construção, e o solver não tem o que resolver.

    3. **Pilotos têm reserva maior que comissários.** Um comissário a mais é
       barato; um comandante a mais é o que salva o cenário. A criticidade do
       posto define a reserva.
    """
    from optimizer.solver import bases_de_partida

    #: Multiplicador de reserva por criticidade do posto.
    reserva_por_cargo = {
        "Comandante": 2.0,
        "Copiloto": 1.5,
        "Comissário": 1.0,
    }

    # Reserva efetiva = a folga pedida, mas nunca menor que a disrupção
    # esperada mais uma margem.
    reserva_efetiva = max(folga, disrupcao + 0.10)

    necessarios: dict[str, dict[str, int]] = {}
    for iata, quantidade in bases_de_partida(voos).items():
        por_cargo: dict[str, int] = {}
        for cargo, qtd in composicao.items():
            exigidos = qtd * quantidade
            multiplicador = reserva_por_cargo.get(cargo, 1.0)
            reserva = max(1, int(exigidos * reserva_efetiva * multiplicador + 0.999))
            por_cargo[cargo] = exigidos + reserva
        necessarios[iata] = por_cargo
    return necessarios


def gerar_cenario(
    voos: int = 150,
    disrupcao: float = 0.15,
    base: str = "GRU",
    seed: int = 42,
    composicao: dict | None = None,
    folga: float = 0.15,
    tripulantes: int | None = None,
) -> Cenario:
    """Gera um cenário completo, com cobertura garantida por base de partida.

    `voos` é o parâmetro que define o tamanho. O pool é dimensionado a partir
    da distribuição das origens — então todo voo tem candidato.

    Passe `tripulantes` explicitamente apenas para forçar um pool insuficiente
    e demonstrar o tratamento de INFEASIBLE.
    """
    from models import Tripulante

    if voos < 1:
        raise ValueError("informe ao menos um voo")

    composicao = composicao or COMPOSICAO_PADRAO

    # --- 1. Voos primeiro ------------------------------------------------------
    lista_voos, _ = gerar_voos(voos, base, seed)

    # --- 2. Dimensionamento por base de partida --------------------------------
    if tripulantes is None:
        necessario = dimensionar_por_base(lista_voos, composicao, folga, disrupcao)
        pool_explicito = False
    else:
        # Pool explícito: distribui na proporção da composição, concentrado na
        # base do cenário. Serve para forçar cenário inviável de propósito.
        pools = {c: int(round(tripulantes * q / sum(composicao.values())))
                 for c, q in composicao.items()}
        necessario = {base: pools}
        pool_explicito = True

    # --- 3. Tripulantes por base ----------------------------------------------
    rng = random.Random(seed + 1)
    lista_tripulantes = []
    indice_global = 0

    for iata, por_cargo in necessario.items():
        for cargo, quantidade in por_cargo.items():
            for _ in range(quantidade):
                limite, _ = _escolher_limite(rng)
                acumuladas = round(rng.uniform(0, limite * 0.55), 2)

                descanso_ok = True
                aclimatado = True
                if rng.random() < disrupcao:
                    if rng.random() < 0.5:
                        descanso_ok = False
                    else:
                        aclimatado = False

                lista_tripulantes.append(
                    Tripulante(
                        id=f"t{indice_global + 1:04d}",
                        nome=nome_completo(indice_global),
                        cargo=cargo,
                        base=iata,
                        horas_acumuladas=acumuladas,
                        limite_horas=limite,
                        descanso_ok=descanso_ok,
                        aclimatado=aclimatado,
                    )
                )
                indice_global += 1

    return Cenario(
        seed=seed,
        base=base,
        tripulantes=lista_tripulantes,
        voos=lista_voos,
        parametros={
            "voos_solicitados": voos,
            "tripulantes_gerados": len(lista_tripulantes),
            "tripulantes_explicito": pool_explicito,
            "disrupcao": disrupcao,
            "composicao": composicao,
            "folga": folga,
            "seed": seed,
            "bases_com_voos": len(necessario),
        },
    )


def _escolher_limite(rng: random.Random) -> tuple[float, str]:
    peso = rng.random()
    if peso < 0.35:
        return LIMITES_RBAC[2]
    if peso < 0.55:
        return LIMITES_RBAC[4]
    if peso < 0.7:
        return LIMITES_RBAC[1]
    if peso < 0.8:
        return LIMITES_RBAC[0]
    if peso < 0.9:
        return LIMITES_RBAC[3]
    return LIMITES_RBAC[5]
