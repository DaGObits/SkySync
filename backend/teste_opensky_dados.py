"""Testa se o Render alcanca o host de DADOS do OpenSky (nao o de auth)."""
import json, urllib.request

url = "https://opensky-network.org/api/states/all?lamin=-34&lomin=-74&lamax=6&lomax=-33"
print("testando:", url)

req = urllib.request.Request(url, headers={"User-Agent": "SkySync-TCC/3.0"})
try:
    with urllib.request.urlopen(req, timeout=12) as r:
        dados = json.loads(r.read())
        estados = dados.get("states") or []
        print(f"HTTP {r.status} — {len(estados)} aeronaves")
        print("(sem autenticacao; o limite anonimo tambem permite isso)")
except Exception as err:
    print(f"{type(err).__name__}: {str(err)[:200]}")
