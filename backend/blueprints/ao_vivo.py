"""Blueprint de dados ao vivo — voos em operação agora.

FONTE: OpenSky Network (https://opensky-network.org), rede de pesquisa aberta
que agrega dados ADS-B. A API é gratuita e a base é citável academicamente.

    GET /api/ao-vivo              voos ativos sobre o Brasil
    GET /api/ao-vivo/status       estado do cache e da autenticação

DECISÕES DE PROJETO:

1. **Cache de 60 segundos.** O OpenSky limita requisições por dia. Se cada
   usuário do painel consultasse direto, o limite estouraria em minutos. Com o
   cache, N usuários compartilham a mesma resposta.

2. **Autenticação no backend.** As credenciais (`OPENSKY_CLIENT_ID` e
   `OPENSKY_CLIENT_SECRET`) ficam no `.env` e nunca chegam ao navegador. O
   token OAuth2 é renovado quando expira.

3. **Falha não quebra o painel.** Se o OpenSky não responder, a rota devolve
   `disponivel: false` com o último dado válido em cache, e o front mostra o
   estado em vez de uma tela vazia.

4. **Correlação com a malha local.** Cada voo ao vivo é comparado com a tabela
   `voos` do banco pelo callsign. Hoje provavelmente não casa — os códigos do
   banco são sintéticos. O campo existe para quando a malha for importada do
   VRA da ANAC.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone

import requests
from flask import Blueprint, current_app, jsonify

from blueprints.auth import login_obrigatorio
from db import transacao

bp = Blueprint("ao_vivo", __name__, url_prefix="/api/ao-vivo")

#: Caixa geográfica que cobre o Brasil (lat/lon mínimos e máximos).
BRASIL = {"lamin": -34.0, "lomin": -74.0, "lamax": 6.0, "lomax": -33.0}

#: Tempo de vida do cache, em segundos.
TTL_CACHE = 60

#: URL da API do OpenSky.
API_OPENSKY = "https://opensky-network.org/api/states/all"

#: URL do token OAuth2.
API_TOKEN = ("https://auth.opensky-network.org/auth/realms/opensky-network/"
             "protocol/openid-connect/token")

#: Cache em memória: {"dados": ..., "quando": timestamp, "token": ..., "expira": ...}
_cache: dict = {"dados": None, "quando": 0.0, "token": None, "expira": 0.0}


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
def _credenciais() -> tuple[str, str] | None:
    cid = os.getenv("OPENSKY_CLIENT_ID", "").strip()
    secret = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()
    return (cid, secret) if cid and secret else None


def _token() -> str | None:
    """Token OAuth2, renovado quando expira. Sem credenciais, devolve None e a
    consulta segue anônima (limite menor)."""
    creds = _credenciais()
    if creds is None:
        return None

    agora = time.time()
    if _cache["token"] and agora < _cache["expira"]:
        return _cache["token"]

    cid, secret = creds
    try:
        resposta = requests.post(
            API_TOKEN,
            data={
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": secret,
            },
            timeout=5,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        _cache["token"] = dados["access_token"]
        # Renova 30s antes de expirar, para não usar um token vencido.
        _cache["expira"] = agora + int(dados.get("expires_in", 1800)) - 30
        return _cache["token"]
    except Exception as err:
        detalhe = str(err)
        resp = getattr(err, "response", None)
        if resp is not None:
            detalhe = f"HTTP {resp.status_code}: {resp.text[:200]}"
        _cache["erro_token"] = detalhe
        if "timed out" in detalhe or "Max retries" in detalhe:
            _cache["opensky_pausado_ate"] = time.time() + PAUSA_OPENSKY
        current_app.logger.warning("OpenSky: falha ao obter token — %s", detalhe)
        _cache["token"] = None
        _cache["expira"] = 0.0
        return None


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
def _consultar_opensky() -> dict:
    """Consulta o OpenSky e normaliza a resposta.

    O formato do OpenSky é uma lista por aeronave:
      [icao24, callsign, origem, hora_pos, hora_contato, lon, lat, altitude,
       on_ground, velocidade, direcao, taxa_vertical, ...]
    """
    token = _token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    resposta = requests.get(
        API_OPENSKY,
        params=BRASIL,
        headers=headers,
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
        altitude = e[7] or e[13]
        if altitude is None:
            continue

        voos.append({
            "icao24": e[0],
            "callsign": callsign,
            "pais_origem": e[2],
            "longitude": e[5],
            "latitude": e[6],
            "altitude_m": round(e[7]) if e[7] is not None else None,
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
        "autenticado": token is not None,
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
# (max. 250 NM), entao o Brasil e coberto por cinco pontos.
# ---------------------------------------------------------------------------
API_AIRPLANES = "[api.airplanes.live](https://api.airplanes.live/v2/point/{lat}/{lon}/250)"

#: Pontos que cobrem as cinco regioes (lat, lon).
PONTOS_BRASIL = (
    (-23.43, -46.47),  # Sudeste — GRU
    (-15.87, -47.92),  # Centro-Oeste — BSB
    (-8.13, -34.92),   # Nordeste — REC
    (-3.04, -60.05),   # Norte — MAO
    (-29.99, -51.17),  # Sul — POA
)

#: Depois de um timeout, o OpenSky fica em pausa por este tempo (segundos).
PAUSA_OPENSKY = 600


def _consultar_airplanes_live() -> dict:
    vistos: dict[str, dict] = {}
    agora_iso = datetime.now(timezone.utc).isoformat()

    for i, (lat, lon) in enumerate(PONTOS_BRASIL):
        if i:
            time.sleep(1.1)  # a API pede no maximo ~1 requisicao por segundo
        r = requests.get(API_AIRPLANES.format(lat=lat, lon=lon), timeout=8)
        r.raise_for_status()
        for a in r.json().get("ac") or []:
            callsign = (a.get("flight") or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{3}\d{3,4}", callsign):
                continue
            alt = a.get("alt_baro")
            if alt in (None, "ground"):
                continue
            hexid = a.get("hex")
            if hexid in vistos:  # raios se sobrepoem
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
                "atualizado_em": agora_iso,
            }

    voos = list(vistos.values())
    return {
        "disponivel": True,
        "fonte": "airplanes.live",
        "consultado_em": agora_iso,
        "autenticado": False,
        "total": len(voos),
        "voos": voos,
    }


def _consultar_com_fallback() -> dict:
    """OpenSky primeiro; se falhar (ou estiver em pausa), airplanes.live."""
    if time.time() >= _cache.get("opensky_pausado_ate", 0.0):
        try:
            return _consultar_opensky()
        except Exception as err:
            _cache["erro_consulta_opensky"] = str(err)[:200]
            _cache["opensky_pausado_ate"] = time.time() + PAUSA_OPENSKY
            current_app.logger.warning("OpenSky falhou, usando airplanes.live: %s", err)
    return _consultar_airplanes_live()


def _do_cache() -> dict:
    """Devolve o cache se estiver fresco; consulta de novo se venceu."""
    agora = time.time()

    if _cache["dados"] and (agora - _cache["quando"]) < TTL_CACHE:
        dados = dict(_cache["dados"])
        dados["cache"] = True
        dados["idade_segundos"] = round(agora - _cache["quando"])
        return dados

    try:
        dados = _consultar_com_fallback()
        _cache["dados"] = dados
        _cache["quando"] = agora
        dados["cache"] = False
        dados["idade_segundos"] = 0
        return dados
    except Exception as err:
        current_app.logger.warning("OpenSky indisponível: %s", err)
        # Devolve o último dado válido, se houver — o painel mostra estado em
        # vez de ficar vazio.
        if _cache["dados"]:
            dados = dict(_cache["dados"])
            dados["disponivel"] = False
            dados["erro"] = "fonte externa indisponível — exibindo último estado"
            dados["cache"] = True
            dados["idade_segundos"] = round(agora - _cache["quando"])
            return dados
        return {
            "disponivel": False,
            "fonte": "OpenSky Network",
            "erro": str(err),
            "voos": [],
            "total": 0,
        }


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
    creds = _credenciais()
    # Busca o token se ainda não houver um válido: sem isto, o /status respondia
    # "token_valido": false logo após o boot mesmo com as credenciais corretas
    # — o token só nascia na primeira consulta de voos, e o diagnóstico mentia.
    token = _token()
    return jsonify({
        "credenciais": "configuradas" if creds else "ausentes (consulta anônima)",
        "token_valido": bool(token and _cache["token"] and time.time() < _cache["expira"]),
        "cache_tem_dados": _cache["dados"] is not None,
        "cache_idade_segundos": (
            round(time.time() - _cache["quando"]) if _cache["quando"] else None
        ),
        "ttl_segundos": TTL_CACHE,
        "erro_token": _cache.get("erro_token"),
        "fonte_atual": (_cache.get("dados") or {}).get("fonte"),
        "opensky_em_pausa": time.time() < _cache.get("opensky_pausado_ate", 0.0),
        "erro_consulta": (_cache.get("dados") or {}).get("erro"),
        "client_id_tamanho": len(os.getenv("OPENSKY_CLIENT_ID", "")),
        "client_id_tem_espaco_ou_aspas": any(
            c in os.getenv("OPENSKY_CLIENT_ID", "") for c in " \"'\n\r"
        ),
        "secret_tamanho": len(os.getenv("OPENSKY_CLIENT_SECRET", "")),
        "secret_tem_espaco_ou_aspas": any(
            c in os.getenv("OPENSKY_CLIENT_SECRET", "") for c in " \"'\n\r"
        ),
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
