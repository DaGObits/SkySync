"""O fundo cartográfico e os aeroportos precisam compartilhar a projeção."""
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import pytest
from blueprints.mapa import _projetar
from dados.malha_seed import COORDENADAS

RAIZ = Path(__file__).resolve().parents[2]


def aneis_svg():
    svg = ET.parse(RAIZ / 'docs/assets/brasil.svg')
    caminho = svg.getroot().find('{http://www.w3.org/2000/svg}path')
    return [[tuple(map(float, p.split(','))) for p in r.split('L')]
            for r in re.findall(r'M([^Z]+)Z', caminho.attrib['d'])]


def dentro(ponto, anel):
    x, y = ponto
    resultado = False
    for a, b in zip(anel, anel[1:]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0]) * (y-a[1]) / (b[1]-a[1]) + a[0]:
            resultado = not resultado
    return resultado


@pytest.mark.parametrize('iata', ['BEL', 'REC', 'FOR', 'SLZ', 'FLN', 'FEN'])
def test_aeroportos_costeiros_e_ilhas_ficam_em_terra_no_svg_publicado(iata):
    lat, lon = COORDENADAS[iata]
    ponto = _projetar(lat, lon, 900, 900)
    assert sum(dentro(ponto, r) for r in aneis_svg()) % 2 == 1


def test_todos_aeroportos_estao_no_enquadramento():
    for iata, (lat, lon) in COORDENADAS.items():
        x, y = _projetar(lat, lon, 900, 900)
        assert 0 <= x <= 900 and 0 <= y <= 900, iata


def test_svg_identico_nas_duas_publicacoes_e_servido_localmente(client):
    docs = (RAIZ / 'docs/assets/brasil.svg').read_bytes()
    assert (RAIZ / 'backend/static/assets/brasil.svg').read_bytes() == docs
    res = client.get('/assets/brasil.svg')
    assert res.status_code == 200
    assert res.mimetype == 'image/svg+xml'
    assert res.data == docs
