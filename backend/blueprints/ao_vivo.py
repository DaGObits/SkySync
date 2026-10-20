"""Blueprint de dados ao vivo — voos em operação agora.

FONTE: OpenSky Network (https://opensky-network.org), rede de pesquisa aberta
que agrega dados ADS-B. A API é gratuita e a base é citável academicamente.

    GET /api/ao-vivo              voos ativos sobre o Brasil
    GET /api/ao-vivo/status       estado do cache e da autenticação

O cache é compartilhado por worker e atualizado em segundo plano para não
bloquear as consultas da operação simulada enquanto a fonte externa responde.
Posições são observações ADS-B, com cobertura e atraso dependentes da fonte.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from threading import Lock, Thread

import requests
from flask import Blueprint, current_app, jsonify

from blueprints.auth import login_obrigatorio
from db import transacao

bp = Blueprint("ao_vivo", __name__, url_prefix="/api/ao-vivo")

#: Caixa geográfica que cobre o Brasil (lat/lon mínimos e máximos).
BRASIL = {"lamin": -34.0, "lomin": -74.0, "lamax": 6.0, "lomax": -33.0}

#: Tempo de vida do cache, em segundos.
#: Atualização máxima a cada 5 minutos; limites externos podem interromper a fonte.
TTL_CACHE = 300

#: URL da API do OpenSky.
API_OPENSKY = "https://opensky-network.org/api/states/all"

#: Cache em memória. Só resultado BOM entra aqui.
_cache: dict = {"dados": None, "quando": 0.0, "erro_consulta_opensky": None,
                "consultando": False, "ultima_tentativa": 0.0, "erro": None}
_cache_lock = Lock()
REPETIR_FALHA = 60


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
def _consultar_opensky() -> dict:
    """Consulta o OpenSky e normaliza a resposta.

    O formato do OpenSky é uma lista por aeronave:
      [icao24, callsign, origem, hora_pos, hora_contato, lon, lat, altitude,
       on_ground, velocidade, direcao, taxa_vertical, ...]
    """
    # Sem autenticação: o endpoint público do OpenSky responde 200 daqui.
    # O limite anônimo (~100 consultas/dia por IP) cobre a demonstração.
    resposta = requests.get(
        API_OPENSKY,
        params=BRASIL,
        timeout=5,
    )
    resposta.raise_for_status()
    bruto = resposta.json()

    estados = bruto.get("states") or []
    voos = []

    for e in estados:
        callsign = (e[1] or "").strip()

        # Só transporte regular: 3 letras ICAO + 3 ou 4 dígitos.
        # Um Cessna decolando (PPSCF) ou um helicóptero (PUCDR) também emite
        # ADS-B, e apareceria no painel como se fosse voo de linha. O padrão
        # do callsign separa os dois sem precisar consultar a aeronave.
        if not re.fullmatch(r"[A-Z]{3}\d{3,4}", callsign.upper()):
            continue

        # Pula aeronave no solo e sem altitude — não é voo em operação.
        if e[8] is True:
            continue
        altitude = e[7] if e[7] is not None else e[13]
        if altitude is None:
            continue

        voos.append({
            "icao24": e[0],
            "callsign": callsign,
            "pais_origem": e[2],
            "longitude": e[5],
            "latitude": e[6],
            "altitude_m": round(altitude),
            "no_solo": bool(e[8]),
            "velocidade_ms": round(e[9]) if e[9] is not None else None,
            "velocidade_kmh": round(e[9] * 3.6) if e[9] is not None else None,
            "direcao": round(e[10]) if e[10] is not None else None,
            "atualizado_em": (
                datetime.fromtimestamp(e[4], tz=timezone.utc).isoformat()
                if e[4] else None
            ),
        })

    return {
        "disponivel": True,
        "fonte": "OpenSky Network",
        "consultado_em": datetime.now(timezone.utc).isoformat(),
        "autenticado": False,  # consulta anonima por decisao de projeto
        "total": len(voos),
        "voos": voos,
    }


# ---------------------------------------------------------------------------
# Fonte alternativa: airplanes.live
#
# O OpenSky nao responde a conexoes vindas do Render (timeout ao conectar em
# auth.opensky-network.org), embora funcione de uma rede residencial. Para o
# painel nao depender de uma unica fonte, cai para a airplanes.live, que serve
# os mesmos dados ADS-B sem autenticacao. A API consulta por ponto + raio
# (max. 250 NM), entao a fonte alternativa amostra cinco regioes.
# ---------------------------------------------------------------------------
API_AIRPLANES = "https://api.airplanes.live/v2/point/{lat}/{lon}/250"

#: Pontos de amostragem nas cinco regioes (lat, lon).
PONTOS_BRASIL = (
    (-23.43, -46.47),  # Sudeste — GRU
    (-15.87, -47.92),  # Centro-Oeste — BSB
    (-8.13, -34.92),   # Nordeste — REC
    (-3.04, -60.05),   # Norte — MAO
    (-29.99, -51.17),  # Sul — POA
)


def _consultar_airplanes_live() -> dict:
    """Consulta a airplanes.live em cinco pontos do Brasil (cobertura parcial).

    A API aceita ponto + raio (max. 250 NM) e nao exige autenticacao. Os raios
    se sobrepoem, entao a aeronave vista em dois pontos entra uma vez so —
    a deduplicacao e por `hex` (ICAO24).
    """
    vistos: dict[str, dict] = {}
    agora_iso = datetime.now(timezone.utc).isoformat()
    erros = []

    for i, (lat, lon) in enumerate(PONTOS_BRASIL):
        if i:
            time.sleep(1.1)  # a API pede no maximo ~1 requisicao por segundo
        url = API_AIRPLANES.replace("{lat}", str(lat)).replace("{lon}", str(lon))
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
        except Exception as err:
            erros.append(f"{lat},{lon}: {str(err)[:80]}")
            continue

        for a in r.json().get("ac") or []:
            callsign = (a.get("flight") or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{3}\d{3,4}", callsign):
                continue
            alt = a.get("alt_baro")
            if alt in (None, "ground"):
                continue
            hexid = a.get("hex")
            if not hexid or hexid in vistos:
                continue
            gs = a.get("gs")  # nos
            vistos[hexid] = {
                "icao24": hexid,
                "callsign": callsign,
                "pais_origem": None,
                "longitude": a.get("lon"),
                "latitude": a.get("lat"),
                "altitude_m": round(float(alt) * 0.3048),
                "no_solo": False,
                "velocidade_ms": round(gs * 0.5144) if gs is not None else None,
                "velocidade_kmh": round(gs * 1.852) if gs is not None else None,
                "direcao": round(a["track"]) if a.get("track") is not None else None,
                "atualizado_em": datetime.fromtimestamp(
                    time.time() - max(0, float(a.get("seen_pos") or 0)), tz=timezone.utc
                ).isoformat(),
            }

    voos = list(vistos.values())
    resultado = {
        "disponivel": True,
        "fonte": "airplanes.live",
        "parcial": True,
        "consultado_em": agora_iso,
        "autenticado": False,
        "total": len(voos),
        "voos": voos,
    }
    if not voos and erros:
        resultado["disponivel"] = False
        resultado["erro"] = " | ".join(erros)[:300]
    return resultado


def _consultar_com_fallback() -> dict:
    """OpenSky primeiro; airplanes.live so se o OpenSky falhar.

    Sem pausa entre tentativas: o host de dados do OpenSky responde em poucos
    segundos a partir do Render. A pausa era ligada por falha do host de AUTH
    (que nao responde de nuvem), e com ela ligada toda consulta ia direto para
    a airplanes.live, que responde 403.
    """
    try:
        return _consultar_opensky()
    except Exception as err:
        _cache["erro_consulta_opensky"] = str(err)[:200]
        current_app.logger.warning("OpenSky falhou, usando airplanes.live: %s", err)
    return _consultar_airplanes_live()


def _atualizar_cache(app):
    """Somente a thread consulta serviços externos; nunca segura o worker HTTP."""
    try:
        with app.app_context():
            dados = _consultar_com_fallback()
            if not dados.get("disponivel"):
                raise RuntimeError("Fonte externa indisponível")
        with _cache_lock:
            _cache.update(dados=dados, quando=time.time(), erro=None)
    except Exception:
        app.logger.warning("Fontes ADS-B indisponíveis; mantendo última consulta")
        with _cache_lock:
            _cache["erro"] = "Fonte externa indisponível"
    finally:
        with _cache_lock:
            _cache["consultando"] = False


def _do_cache() -> dict:
    """Consulta imediata do cache, com uma única atualização em segundo plano."""
    agora = time.time()
    with _cache_lock:
        vencido = not _cache["dados"] or agora - _cache["quando"] >= TTL_CACHE
        iniciar = (vencido and not _cache["consultando"] and
                   agora - _cache["ultima_tentativa"] >= REPETIR_FALHA)
        if iniciar:
            _cache["consultando"] = True
            _cache["ultima_tentativa"] = agora
        dados = dict(_cache["dados"] or {"voos": [], "total": 0})
        # Cópias independentes: filtros de uma requisição não alteram o cache.
        dados["voos"] = [dict(v) for v in dados["voos"]]
        dados.update(
            disponivel=bool(_cache["dados"]) and not bool(_cache["erro"]),
            atualizando=_cache["consultando"], cache=bool(_cache["dados"]),
            idade_segundos=round(agora - _cache["quando"]) if _cache["dados"] else None,
        )
        if _cache["erro"]:
            dados["erro"] = _cache["erro"]
    if iniciar:
        app = current_app._get_current_object()
        try:
            Thread(target=_atualizar_cache, args=(app,), daemon=True, name="radar-adsb").start()
        except Exception:
            with _cache_lock:
                _cache["consultando"] = False
                _cache["erro"] = "Não foi possível iniciar consulta ADS-B"
            dados.update(atualizando=False, disponivel=False)
    return dados


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@bp.get("")
@login_obrigatorio
def voos_ao_vivo():
    """Voos em operação agora sobre o Brasil.

    Query string opcional:
        limite=50        teto de voos devolvidos (padrão 100, máx 500)
        casar=1          só os que casam com códigos da tabela `voos`
    """
    try:
        limite = max(1, min(int(request_limite()), 500))
    except ValueError:
        return jsonify({"erro": "limite deve ser um número"}), 400

    dados = _do_cache()
    voos = dados.get("voos", [])

    # Correlação com a malha local: hoje provavelmente vazia, porque os
    # códigos do banco são sintéticos. Fica pronto para o VRA da ANAC.
    try:
        with transacao() as conexao:
            linhas = conexao.execute("SELECT codigo FROM voos").fetchall()
        codigos = {l["codigo"].replace("-", "").upper() for l in linhas}
        for v in voos:
            v["na_malha"] = v["callsign"].upper() in codigos
    except Exception:
        current_app.logger.warning("não foi possível correlacionar com a malha")
        for v in voos:
            v["na_malha"] = False

    so_casar = request_query("casar") in ("1", "true")
    if so_casar:
        voos = [v for v in voos if v.get("na_malha")]

    dados["voos"] = voos[:limite]
    dados["retornados"] = len(dados["voos"])
    dados["na_malha"] = sum(1 for v in dados["voos"] if v.get("na_malha"))
    return jsonify(dados)


@bp.get("/status")
@login_obrigatorio
def status():
    """Estado do cache e das credenciais — para diagnosticar o painel."""
    return jsonify({
        "cache_tem_dados": _cache["dados"] is not None,
        "cache_idade_segundos": (
            round(time.time() - _cache["quando"]) if _cache["quando"] else None
        ),
        "ttl_segundos": TTL_CACHE,
        "erro_opensky": _cache.get("erro_consulta_opensky"),
        "fonte_atual": (_cache.get("dados") or {}).get("fonte"),
        "erro_consulta": (_cache.get("dados") or {}).get("erro"),
    })


# ---------------------------------------------------------------------------
# Helpers de request (importados aqui para o módulo não depender de Flask no topo)
# ---------------------------------------------------------------------------
def request_limite() -> int:
    from flask import request
    return int(request.args.get("limite", 100))


def request_query(chave: str) -> str:
    from flask import request
    return (request.args.get(chave) or "").strip().lower()
