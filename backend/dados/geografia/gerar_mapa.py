"""Gera o fundo local do mapa com a mesma projeção usada para aeroportos e voos.

Na raiz do repositório: python backend/dados/geografia/gerar_mapa.py
"""
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / 'backend'))
from blueprints.mapa import _projetar


def gerar():
    pasta = Path(__file__).resolve().parent
    geometria = json.loads((pasta / 'brasil.json').read_text())
    caminhos = []
    for poligono in geometria['coordinates']:
        for anel in poligono:
            pontos = [_projetar(lat, lon, 900, 900) for lon, lat in anel]
            caminhos.append('M' + 'L'.join(f'{x},{y}' for x, y in pontos) + 'Z')
    licenca = escape((pasta / 'LICENSE-world-atlas').read_text())
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 900">'
           '<title>Brasil — Natural Earth 1:10m</title>'
           '<metadata>Natural Earth 4.1.0, via world-atlas 2.0.2. ' + licenca + '</metadata>'
           '<path fill="#183b48" stroke="#3d6975" stroke-width="1.2" fill-rule="evenodd" d="'
           + ''.join(caminhos) + '"/></svg>\n')
    for diretorio in ('docs', 'backend/static'):
        destino = RAIZ / diretorio / 'assets' / 'brasil.svg'
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(svg)


if __name__ == '__main__':
    gerar()
