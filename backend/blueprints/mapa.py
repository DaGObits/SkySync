"""Blueprint do mapa da malha aérea.

Devolve aeroportos e rotas com as coordenadas do banco, para o front desenhar
um SVG. Nenhuma dependência externa: os dados são os 97 aeroportos e os 140
voos que já existem nas tabelas `aeroportos` e `voos`.

    GET /api/mapa/malha      aeroportos, rotas e contorno do Brasil

Por que SVG e não um mapa de tiles (Leaflet/OSM): depois do episódio com as
APIs de ADS-B, eliminar dependência de rede virou requisito. O SVG usa as
coordenadas reais do banco, funciona em qualquer ambiente e não depende de
CORS, de rate limit nem de serviço de terceiros.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from blueprints.auth import login_obrigatorio
from db import transacao

bp = Blueprint("mapa", __name__, url_prefix="/api/mapa")

#: Contorno simplificado do Brasil (lon, lat), para o fundo do mapa.
#: 30 pontos bastam para a silhueta; precisão de fronteira não é o objetivo —
#: o mapa mostra a rede de aeroportos dentro do território.
CONTORNO_BRASIL = (
    (-69.5, 0.7), (-67.9, 1.5), (-64.0, 4.1), (-60.0, 5.2), (-56.5, 2.0),
    (-51.5, 4.2), (-51.0, 0.0), (-49.5, -1.8), (-44.0, -2.5), (-38.5, -3.7),
    (-35.2, -5.8), (-37.0, -11.0), (-39.0, -13.0), (-39.7, -18.0),
    (-41.0, -21.9), (-44.5, -23.4), (-48.5, -25.5), (-48.6, -28.5),
    (-52.0, -32.0), (-53.4, -33.7), (-57.6, -30.2), (-55.0, -27.0),
    (-54.5, -25.5), (-57.6, -22.1), (-58.0, -19.8), (-60.0, -16.3),
    (-63.0, -12.5), (-66.0, -9.8), (-70.5, -9.5), (-73.5, -7.5),
    (-70.0, -4.2), (-69.5, -1.3), (-69.5, 0.7),
)

#: Projeção equiretangular simples com latitude de referência.
#: Sem isso, o Brasil aparece esticado: graus de longitude encurtam conforme a
#: latitude aumenta, e o norte do país ficaria mais largo do que é.
LAT_REF = -15.0


def _projetar(lat: float, lon: float, largura: int, altura: int) -> tuple[float, float]:
    """Converte (lat, lon) em (x, y) de SVG."""
    import math

    fator = math.cos(math.radians(LAT_REF))

    # Inclui Fernando de Noronha no enquadramento.
    lon_min, lon_max = -74.0, -32.0
    lat_min, lat_max = -34.0, 6.0

    x = (lon - lon_min) / (lon_max - lon_min) * largura
    # A latitude cresce para o norte e o y do SVG cresce para baixo.
    y = (lat_max - lat) / (lat_max - lat_min) * altura
    # Corrige a distorção horizontal da projeção.
    x = (x - largura / 2) * fator + largura / 2
    return round(x, 1), round(y, 1)


@bp.get("/malha")
@login_obrigatorio
def malha_mapa():
    """Aeroportos e rotas da malha, já projetados para SVG.

    Query string:
        largura=900    largura da viewBox
        altura=900     altura da viewBox
    """
    from flask import request

    try:
        largura = max(300, min(int(request.args.get("largura", 900)), 2000))
        altura = max(300, min(int(request.args.get("altura", 900)), 2000))
    except ValueError:
        return jsonify({"erro": "largura e altura devem ser números"}), 400

    with transacao() as conexao:
        aeroportos = conexao.execute(
            "SELECT iata, cidade, uf, regiao, latitude, longitude, hub "
            "FROM aeroportos ORDER BY iata"
        ).fetchall()

        # Cada rota = uma origem e um destino. A contagem por par alimenta a
        # espessura do arco e o volume de cada aeroporto.
        rotas = conexao.execute(
            "SELECT origem, destino, COUNT(*) AS frequencia, "
            "SUM(duracao_horas) AS horas, "
            "COUNT(*) FILTER (WHERE pouso_noturno) AS noturnos "
            "FROM voos GROUP BY origem, destino ORDER BY frequencia DESC"
        ).fetchall()

        totais = conexao.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM aeroportos) AS aeroportos, "
            "(SELECT COUNT(*) FROM voos) AS voos, "
            "(SELECT COUNT(*) FROM tripulantes) AS tripulantes, "
            "(SELECT COUNT(*) FROM escalas) AS alocacoes"
        ).fetchone()

    pontos = {}
    for a in aeroportos:
        if a["latitude"] is None or a["longitude"] is None:
            continue
        x, y = _projetar(a["latitude"], a["longitude"], largura, altura)
        pontos[a["iata"]] = {"x": x, "y": y}

    # Partidas e chegadas por aeroporto — dimensiona o ponto no mapa.
    partidas: dict[str, int] = {}
    for r in rotas:
        partidas[r["origem"]] = partidas.get(r["origem"], 0) + r["frequencia"]

    lista_aeroportos = []
    for a in aeroportos:
        p = pontos.get(a["iata"])
        if not p:
            continue
        lista_aeroportos.append({
            "iata": a["iata"],
            "cidade": a["cidade"],
            "uf": a["uf"],
            "regiao": a["regiao"],
            "hub": bool(a["hub"]),
            "latitude": a["latitude"],
            "longitude": a["longitude"],
            "x": p["x"],
            "y": p["y"],
            "partidas": partidas.get(a["iata"], 0),
        })

    lista_rotas = []
    for r in rotas:
        o, d = pontos.get(r["origem"]), pontos.get(r["destino"])
        if not o or not d:
            continue
        lista_rotas.append({
            "origem": r["origem"],
            "destino": r["destino"],
            "frequencia": r["frequencia"],
            "horas": round(float(r["horas"]), 1) if r["horas"] else 0,
            "noturnos": r["noturnos"],
            "x1": o["x"], "y1": o["y"],
            "x2": d["x"], "y2": d["y"],
        })

    contorno = [
        {"x": x, "y": y}
        for x, y in (_projetar(lat, lon, largura, altura)
                     for lon, lat in CONTORNO_BRASIL)
    ]

    return jsonify({
        "viewBox": {"largura": largura, "altura": altura},
        "contorno": contorno,
        "aeroportos": lista_aeroportos,
        "rotas": lista_rotas,
        "totais": {
            "aeroportos": totais["aeroportos"],
            "voos": totais["voos"],
            "tripulantes": totais["tripulantes"],
            "alocacoes": totais["alocacoes"],
        },
    })


@bp.get("/regioes")
@login_obrigatorio
def por_regiao():
    """Resumo por região — para a legenda do mapa."""
    with transacao() as conexao:
        linhas = conexao.execute(
            "SELECT a.regiao, COUNT(DISTINCT a.iata) AS aeroportos, "
            "COUNT(v.id) AS voos "
            "FROM aeroportos a LEFT JOIN voos v "
            "ON v.origem = a.iata OR v.destino = a.iata "
            "GROUP BY a.regiao ORDER BY voos DESC"
        ).fetchall()

    return jsonify([
        {
            "regiao": l["regiao"],
            "aeroportos": l["aeroportos"],
            "voos": l["voos"],
        }
        for l in linhas
    ])
