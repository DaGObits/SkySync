"""Restrições regulatórias do otimizador.

Cada classe aqui é uma regra da RBAC 117 isolada, com nome, justificativa e
método `aplicar`. Isolar assim tem duas consequências práticas:

1. O solver não sabe o que é "pouso noturno" — só recebe restrições. Isso deixa
   o solver testável e permite trocar a regulamentação sem mexer no motor.
2. Cada restrição vira um item documentável no capítulo de metodologia do TCC:
   o nome da regra, o artigo de referência e a formulação matemática.

SOBRE O DOMÍNIO FILTRADO: o solver não cria variável para pares
(tripulante, voo) que já nascem inviáveis. Por isso as restrições nunca indexam
`variaveis` direto — usam `ctx.tem()` / `ctx.bloquear()` / `ctx.somar()`, que
tratam a ausência da variável como "já impossível".

SOBRE EXPRESSÕES DO CP-SAT: uma soma de variáveis NÃO é um número em Python —
é uma expressão linear que só existe dentro do modelo. Comparar essa expressão
com `== 0` em código Python levanta NotImplementedError. Por isso as
verificações abaixo testam a lista de termos, não o valor da soma.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ortools.sat.python import cp_model

#: Composição de um narrow-body (A320 / 737).
COMPOSICAO_PADRAO = {
    "Comandante": 1,
    "Copiloto": 1,
    "Comissário": 3,
}


@dataclass(frozen=True)
class Contexto:
    """Tudo o que uma restrição precisa saber sobre o problema.

    `variaveis` mapeia (id_tripulante, id_voo) -> BoolVar, mas pode não conter
    todos os pares: o solver filtra os inviáveis. Use os métodos abaixo em vez
    de indexar o dicionário.
    """

    model: cp_model.CpModel
    variaveis: dict[tuple[str, str], cp_model.IntVar]
    folga: dict[str, cp_model.IntVar]
    tripulantes: list
    voos: list
    limite_horas: float
    minutos_por_voo: dict[str, int]
    composicao: dict[str, int]

    # --- Acesso seguro às variáveis ---------------------------------------
    def tem(self, tripulante_id: str, voo_id: str) -> bool:
        """O par (tripulante, voo) existe no modelo?"""
        return (tripulante_id, voo_id) in self.variaveis

    def alocado(self, tripulante_id: str, voo_id: str) -> cp_model.IntVar:
        """A variável do par. Levanta KeyError se o par não existe."""
        return self.variaveis[(tripulante_id, voo_id)]

    def termo(self, tripulante_id: str, voo_id: str) -> int | cp_model.IntVar:
        """O termo do par, ou o INTEIRO 0 quando o par não existe.

        Devolver 0 (número) em vez de omitir o termo permite somar sem checar
        a lista vazia depois.
        """
        if self.tem(tripulante_id, voo_id):
            return self.alocado(tripulante_id, voo_id)
        return 0

    def bloquear(self, tripulante_id: str, voo_id: str) -> None:
        """Proíbe o par. Se a variável não existe, o par já está proibido."""
        if self.tem(tripulante_id, voo_id):
            self.model.Add(self.alocado(tripulante_id, voo_id) == 0)

    def bloquear_tripulante(self, tripulante_id: str) -> None:
        """Proíbe todos os pares de um tripulante (descanso ou teto estourado)."""
        for v in self.voos:
            self.bloquear(tripulante_id, v.id)

    def pares_de(self, tripulante_id: str, voos=None) -> list[tuple]:
        """Lista os pares viáveis de um tripulante. É *isto* que se testa para
        saber se há algo a restringir — nunca o valor da soma."""
        alvos = voos if voos is not None else self.voos
        return [
            (tripulante_id, v.id)
            for v in alvos
            if self.tem(tripulante_id, v.id)
        ]

    def soma_carga(self, tripulante_id: str, voos=None):
        """Soma ponderada da jornada de um tripulante.

        Devolve `None` quando não há nenhum par viável — sinal de que não há
        constraint a adicionar. Nunca devolve uma expressão que possa ser
        confundida com zero.
        """
        pares = self.pares_de(tripulante_id, voos)
        if not pares:
            return None
        return sum(
            self.alocado(t_id, v_id) * self.minutos_por_voo[v_id]
            for t_id, v_id in pares
        )

    def por_cargo(self, cargo: str) -> list:
        return [t for t in self.tripulantes if t.cargo == cargo]


class Restricao(ABC):
    """Uma regra regulatória aplicável ao modelo CP-SAT."""

    nome: str = "restricao"
    referencia: str = ""
    descricao: str = ""

    @abstractmethod
    def aplicar(self, ctx: Contexto) -> None:
        """Adiciona as constraints ao modelo. Não retorna nada."""

    def __str__(self) -> str:  # pragma: no cover - conveniência
        return f"{self.nome} ({self.referencia})"


# ---------------------------------------------------------------------------
# 117.035 — composição mínima por cargo
# ---------------------------------------------------------------------------
class ComposicaoPorCargo(Restricao):
    nome = "composicao_cargo"
    referencia = "RBAC 117.035"
    descricao = (
        "Cada voo exige a composição mínima da aeronave: 1 comandante, "
        "1 copiloto e 3 comissários. Não basta alocar cinco pessoas — elas "
        "precisam ocupar os postos corretos."
    )

    def aplicar(self, ctx: Contexto) -> None:
        for v in ctx.voos:
            for cargo, exigidos in ctx.composicao.items():
                elegiveis = [
                    t for t in ctx.por_cargo(cargo) if ctx.tem(t.id, v.id)
                ]
                if len(elegiveis) < exigidos:
                    # Não há gente suficiente desse cargo para este voo: o
                    # cenário é inviável, e declarar isso explicitamente produz
                    # um diagnóstico melhor do que uma falha muda.
                    ctx.model.Add(0 == 1)
                    continue
                ctx.model.Add(
                    sum(ctx.alocado(t.id, v.id) for t in elegiveis) == exigidos
                )


# ---------------------------------------------------------------------------
# 117.030 / 117.040 — teto de jornada por tripulante
# ---------------------------------------------------------------------------
class LimiteDeJornada(Restricao):
    nome = "limite_jornada"
    referencia = "RBAC 117.030 / 117.040"
    descricao = (
        "A soma das durações dos voos atribuídos a um tripulante, somada às "
        "horas já acumuladas no período, não pode exceder o teto de jornada "
        "aplicável ao perfil dele."
    )

    def aplicar(self, ctx: Contexto) -> None:
        for t in ctx.tripulantes:
            teto_min = int(min(t.limite_horas, ctx.limite_horas) * 60)
            acumulado_min = int(t.horas_acumuladas * 60)

            # Já bloqueado antes de otimizar: nenhuma atribuição é permitida.
            if acumulado_min >= teto_min or not t.descanso_ok:
                ctx.bloquear_tripulante(t.id)
                continue

            # `soma_carga` devolve None quando não há par viável — e None é
            # testável como booleano, diferente da expressão do CP-SAT.
            carga = ctx.soma_carga(t.id)
            if carga is None:
                continue
            ctx.model.Add(carga + acumulado_min <= teto_min)


# ---------------------------------------------------------------------------
# 117.095 — descanso mínimo entre jornadas
# ---------------------------------------------------------------------------
class DescansoMinimoEntreJornadas(Restricao):
    nome = "descanso_minimo"
    referencia = "RBAC 117.095"
    descricao = (
        "Tripulante que já cumpriu jornada sem o repouso regulamentar "
        "obrigatório não recebe nova atribuição nesta rodada de otimização."
    )

    def aplicar(self, ctx: Contexto) -> None:
        for t in ctx.tripulantes:
            if t.descanso_ok:
                continue
            ctx.bloquear_tripulante(t.id)


# ---------------------------------------------------------------------------
# 117.135 — aclimatação ao fuso
# ---------------------------------------------------------------------------
class AclimatacaoDeFuso(Restricao):
    nome = "aclimatacao_fuso"
    referencia = "RBAC 117.135"
    descricao = (
        "Tripulante não aclimatado ao fuso da base não pode receber voos com "
        "pouso noturno, situação em que a redução de jornada é mais restritiva."
    )

    def aplicar(self, ctx: Contexto) -> None:
        for t in ctx.tripulantes:
            if t.aclimatado:
                continue
            for v in ctx.voos:
                if v.pouso_noturno:
                    ctx.bloquear(t.id, v.id)


# ---------------------------------------------------------------------------
# Exclusividade: um tripulante por rodada
# ---------------------------------------------------------------------------
class UmVooPorTripulante(Restricao):
    nome = "um_voo_por_tripulante"
    referencia = "Operacional"
    descricao = (
        "Com composição de cinco pessoas por voo, o modelo precisa garantir "
        "que cada tripulante seja designado a no máximo um voo na rodada — "
        "sem isto, o solver 'otimiza' colocando a mesma pessoa em vários voos."
    )

    def aplicar(self, ctx: Contexto) -> None:
        for t in ctx.tripulantes:
            # Testa a LISTA de pares, não o valor da soma: a soma de variáveis
            # do CP-SAT não é um número em Python.
            pares = ctx.pares_de(t.id)
            if len(pares) <= 1:
                continue  # com 0 ou 1 par, a exclusividade é automática
            ctx.model.Add(
                sum(ctx.alocado(t_id, v_id) for t_id, v_id in pares) <= 1
            )


#: Ordem canônica de aplicação. Restrições de bloqueio primeiro, para que o
#: domínio já esteja reduzido quando a de jornada entrar.
RESTRICOES_PADRAO: tuple[Restricao, ...] = (
    DescansoMinimoEntreJornadas(),
    AclimatacaoDeFuso(),
    LimiteDeJornada(),
    ComposicaoPorCargo(),
    UmVooPorTripulante(),
)


def catalogo_restricoes() -> list[dict[str, str]]:
    """Lista as restrições ativas — usado pelo endpoint /api/otimizacao/restricoes."""
    return [
        {"nome": r.nome, "referencia": r.referencia, "descricao": r.descricao}
        for r in RESTRICOES_PADRAO
    ]
