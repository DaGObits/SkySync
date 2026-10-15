"""Testa se o 403 da airplanes.live e por falta de User-Agent.
A URL e montada por partes, para nenhum link colado entrar na string."""
import re
from urllib.request import Request, urlopen

host = "api.airplanes.live"
caminho = "/v2/point/-23.43/-46.47/250"
URL = "https://" + host + caminho

# Confere que a URL esta limpa antes de usar
assert re.fullmatch(r"https://[a-z0-9.-]+/v2/point/-?\d+(\.\d+)?/-?\d+(\.\d+)?/\d+", URL), URL
print("URL:", URL)
print()

def tentar(nome, headers):
    try:
        req = Request(URL, headers=headers)
        with urlopen(req, timeout=8) as r:
            corpo = r.read(400)
            texto = corpo.decode("utf-8", "replace")
            print(f"{nome}: HTTP {r.status}")
            print(f"      {texto[:150]}")
            return True
    except Exception as err:
        print(f"{nome}: {type(err).__name__} — {str(err)[:180]}")
        return False

tentar("sem User-Agent ", {})
print()
tentar("com User-Agent ", {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json",
})
print()
tentar("UA do projeto  ", {
    "User-Agent": "SkySync-TCC/3.0 (contato: lucas) python-requests",
    "Accept": "application/json",
})
