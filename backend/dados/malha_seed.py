"""Semente da malha aérea — usada quando o banco ainda não tem aeroportos.

A malha oficial vem de `aeroportos_voos_regulares_brasil.txt`, importada pelo
`importar_malha.py`. Este módulo existe para o caso do banco novo: se a tabela
`aeroportos` estiver vazia, ele a popula a partir do arquivo.

Uso:
    flask --app app seed-malha       (comando CLI, ver app.py)
"""
from __future__ import annotations

from pathlib import Path

#: Região a partir da UF — o arquivo da malha não traz esse campo.
REGIAO_POR_UF = {
    "AC": "Norte", "AM": "Norte", "AP": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

#: Coordenadas por IATA. As dos aeroportos que já estavam na malha original
#: e as dos 61 acrescentados na expansão para 97.
COORDENADAS: dict[str, tuple[float, float]] = {
    # --- malha original (36) ---
    "GRU": (-23.43, -46.47), "CGH": (-23.63, -46.66), "VCP": (-23.01, -47.13),
    "GIG": (-22.81, -43.25), "SDU": (-22.91, -43.16), "CNF": (-19.62, -43.97),
    "UDI": (-18.88, -48.23), "VIX": (-20.26, -40.29), "SJK": (-23.23, -45.86),
    "CWB": (-25.53, -49.17), "FLN": (-27.67, -48.55), "POA": (-29.99, -51.17),
    "NVT": (-26.88, -48.65), "LDB": (-23.33, -51.13), "BSB": (-15.87, -47.92),
    "CGB": (-15.65, -56.12), "GYN": (-16.63, -49.22), "CGR": (-20.47, -54.67),
    "SSA": (-12.91, -38.33), "REC": (-8.13, -34.92), "FOR": (-3.78, -38.53),
    "NAT": (-5.77, -35.37), "MCZ": (-9.51, -35.79), "JPA": (-7.15, -34.95),
    "THE": (-5.06, -42.82), "SLZ": (-2.58, -44.23), "AJU": (-10.98, -37.07),
    "PHB": (-2.89, -41.73), "MAO": (-3.04, -60.05), "BEL": (-1.38, -48.48),
    "PVH": (-8.71, -63.90), "RBR": (-9.87, -67.89), "MCP": (0.05, -51.07),
    "STM": (-2.42, -54.79), "BVB": (2.84, -60.69), "PMW": (-10.29, -48.36),
    # --- expansão (61) ---
    "CZS": (-7.60, -72.77), "BRA": (-12.08, -45.01), "LAZ": (-13.26, -43.41),
    "GNM": (-14.21, -42.75), "IOS": (-14.82, -39.03), "LEC": (-12.48, -41.28),
    "PAV": (-9.40, -38.25), "BPS": (-16.44, -39.08), "TXF": (-17.52, -39.67),
    "VDC": (-14.86, -40.86), "JJD": (-2.91, -40.36), "JDO": (-7.22, -39.27),
    "CLV": (-17.73, -48.61), "RVD": (-17.83, -50.96), "IMP": (-5.53, -47.46),
    "AAX": (-19.56, -46.96), "GVR": (-18.90, -41.98), "IPN": (-19.47, -42.49),
    "MOC": (-16.71, -43.82), "UBA": (-19.77, -47.96), "IZA": (-21.51, -43.17),
    "BYO": (-21.25, -56.45), "DOU": (-22.20, -54.93), "AFL": (-9.87, -56.10),
    "BPG": (-15.86, -52.39), "ROO": (-16.59, -54.72), "OPS": (-11.88, -55.59),
    "SMT": (-12.48, -55.67), "ATM": (-3.25, -52.25), "CKS": (-6.12, -50.00),
    "ITB": (-4.24, -56.00), "MAB": (-5.37, -49.14), "RDC": (-8.03, -50.00),
    "TUR": (-3.79, -49.72), "FEN": (-3.85, -32.42), "PNZ": (-9.36, -40.56),
    "CAC": (-25.00, -53.50), "IGU": (-25.60, -54.49), "MGF": (-23.48, -52.01),
    "PGZ": (-25.18, -50.14), "CFB": (-22.92, -42.07), "MVF": (-5.20, -37.36),
    "OAL": (-11.50, -61.45), "JPR": (-10.87, -61.85), "BVH": (-12.69, -60.10),
    "CXJ": (-29.20, -51.19), "PFB": (-28.24, -52.33), "PET": (-31.72, -52.33),
    "RIA": (-29.71, -53.69), "URG": (-29.78, -57.04), "XAP": (-27.13, -52.66),
    "CCM": (-28.72, -49.42), "JJG": (-28.68, -49.06), "JOI": (-26.22, -48.80),
    "ARU": (-21.14, -50.42), "JTC": (-22.34, -49.05), "MII": (-22.20, -49.93),
    "PPB": (-22.18, -51.42), "RAO": (-21.13, -47.77), "SJP": (-20.82, -49.40),
    "AUX": (-7.23, -48.24),
}

#: Hubs nacionais — concentram a malha.
HUBS = {"GRU", "CGH", "GIG", "BSB", "CNF", "SSA", "REC", "FOR", "MAO", "BEL",
        "POA", "CWB", "VCP", "FLN"}

ARQUIVO_PADRAO = "aeroportos_voos_regulares_brasil.txt"


def ler_arquivo(caminho: Path) -> list[dict]:
    """Lê o arquivo da malha e devolve os registros prontos para gravar."""
    registros: list[dict] = []
    ignoradas = 0

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split(";")
        if len(partes) != 5 or len(partes[0]) != 2 or len(partes[3]) != 3:
            ignoradas += 1
            continue

        uf, municipio, nome, iata, categoria = (p.strip() for p in partes)
        regiao = REGIAO_POR_UF.get(uf)
        coord = COORDENADAS.get(iata)

        if not regiao or not coord:
            ignoradas += 1
            continue

        registros.append({
            "iata": iata,
            "cidade": municipio,
            "uf": uf,
            "regiao": regiao,
            "lat": coord[0],
            "lon": coord[1],
            "hub": iata in HUBS,
        })

    return registros


def semear(conexao, caminho: Path | None = None) -> tuple[int, int]:
    """Popula a tabela `aeroportos`. Devolve (inseridos, atualizados).

    Idempotente: aeroporto que já existe tem região e hub atualizados, e as
    coordenadas são preservadas.
    """
    caminho = caminho or Path(ARQUIVO_PADRAO)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo da malha não encontrado: {caminho}")

    registros = ler_arquivo(caminho)
    inseridos = atualizados = 0

    for r in registros:
        ja = conexao.execute(
            "SELECT iata FROM aeroportos WHERE iata = %s", (r["iata"],)
        ).fetchone()

        if ja:
            conexao.execute(
                "UPDATE aeroportos SET cidade = %s, regiao = %s, hub = %s WHERE iata = %s",
                (r["cidade"], r["regiao"], r["hub"], r["iata"]),
            )
            atualizados += 1
        else:
            conexao.execute(
                """
                INSERT INTO aeroportos
                    (iata, cidade, uf, regiao, latitude, longitude, hub)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (r["iata"], r["cidade"], r["uf"], r["regiao"], r["lat"], r["lon"], r["hub"]),
            )
            inseridos += 1

    return inseridos, atualizados


def contar(conexao) -> int:
    linha = conexao.execute("SELECT COUNT(*) AS n FROM aeroportos").fetchone()
    return linha["n"] if linha else 0
