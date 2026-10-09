"""Base de nomes para geração de tripulação sintética.

IMPORTANTE PARA O TCC: estes são nomes comuns brasileiros combinados
sinteticamente. Não existe base pública de tripulantes reais, e usá-los seria
problema de privacidade. A prática padrão em pesquisa operacional é gerar dados
sintéticos — vale um parágrafo no capítulo de metodologia:

    "Os dados de tripulação são sintéticos, compostos a partir de listas de
    prenomes e sobrenomes de uso comum no Brasil, por não haver base pública
    disponível. Os parâmetros operacionais (aeroportos, companhias, duração de
    voo e limites da RBAC 117) são reais e derivam da malha aérea brasileira."

A lista é longa de propósito: com 40 prenomes e 30 sobrenomes há 1.200
combinações, o suficiente para gerar centenas de tripulantes distintos.
"""
from __future__ import annotations

PRENOMES_M = (
    "Rafael", "Lucas", "Bruno", "Diego", "Thiago", "Renato", "Carlos", "Eduardo",
    "Marcos", "Roberto", "Fernando", "Gustavo", "André", "Felipe", "Rodrigo",
    "Leandro", "Vinícius", "Alexandre", "Paulo", "Sérgio", "Daniel", "Murilo",
    "Caio", "Otávio", "Henrique", "Igor", "Juliano", "Mateus", "Nelson", "Rui",
    "Vitor", "Wesley", "Alan", "Breno", "César", "Douglas", "Ênio", "Flávio",
    "Gabriel", "Hugo",
)

PRENOMES_F = (
    "Beatriz", "Juliana", "Camila", "Larissa", "Fernanda", "Mariana", "Patrícia",
    "Aline", "Carla", "Débora", "Eliane", "Gabriela", "Helena", "Isabela",
    "Jéssica", "Karina", "Letícia", "Michele", "Natália", "Olívia", "Priscila",
    "Renata", "Sabrina", "Tatiane", "Vanessa", "Wanessa", "Yasmin", "Zélia",
    "Amanda", "Bruna", "Cristina", "Daniela", "Eduarda", "Flávia", "Giovana",
    "Heloísa", "Ingrid", "Joana", "Kelly", "Lívia",
)

SOBRENOMES = (
    "Nunes", "Mendes", "Souza", "Ribeiro", "Rocha", "Farias", "Azevedo",
    "Moreira", "Prado", "Castilho", "Lima", "Mendonça", "Silveira", "Vinicius",
    "Martins", "Sampaio", "Dias", "Oliveira", "Santos", "Pereira", "Almeida",
    "Costa", "Carvalho", "Gomes", "Barbosa", "Araújo", "Cardoso", "Teixeira",
    "Correia", "Freitas", "Machado", "Pinheiro", "Batista", "Fonseca",
    "Miranda", "Campos", "Borges", "Neves", "Peixoto", "Queiroz",
)


def nome_completo(indice: int) -> str:
    """Nome determinístico: o mesmo índice sempre produz o mesmo nome.

    O determinismo importa para reprodutibilidade — a banca pode gerar o mesmo
    cenário e comparar os resultados.
    """
    todos_prenomes = PRENOMES_M + PRENOMES_F
    prenome = todos_prenomes[indice % len(todos_prenomes)]
    # Passos primos evitam repetir a mesma combinação em índices consecutivos.
    sobrenome1 = SOBRENOMES[(indice * 7) % len(SOBRENOMES)]
    sobrenome2 = SOBRENOMES[(indice * 13 + 5) % len(SOBRENOMES)]

    if sobrenome1 == sobrenome2:
        return f"{prenome} {sobrenome1}"
    return f"{prenome} {sobrenome1} {sobrenome2}"


def cargo_por_indice(indice: int) -> str:
    """Distribui os cargos na proporção real de uma companhia aérea.

    Para cada 5 posições: 1 comandante, 1 copiloto e 3 comissários — a mesma
    proporção da composição exigida por voo, garantindo que o pool sempre tenha
    gente suficiente de cada cargo.
    """
    resto = indice % 5
    if resto == 0:
        return "Comandante"
    if resto == 1:
        return "Copiloto"
    return "Comissário"
