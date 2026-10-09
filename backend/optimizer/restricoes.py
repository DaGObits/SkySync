"""Restrições regulatórias do otimizador.

Cada classe aqui é uma regra da RBAC 117 isolada, com nome, justificativa e
método `aplicar`. Isolar assim tem duas consequências práticas:

1. O solver não sabe o que é "pouso noturno" — só recebe restrições. Isso deixa
   o solver testável e permite trocar a regulamentação sem mexer no motor.
2. Cada restrição vira um item documentável no capítulo de metodologia do TCC:
   o nome da regra, o artigo de referência e a formulação matemática.

Referências usadas na modelagem (ajuste os números conforme a versão vigente):
  - 117.030 — limite de jornada conforme apresentação e composição da tripulação
  - 117.040 — jornada máxima em função do número de pousos
  - 117.095 — período de descanso entre jornadas
  - 117.135 — adaptação ao fuso horário (aclimatação)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class Contexto:
    """Tudo o que uma restrição precisa saber sobre o problema.

    `variaveis` mapeia (id_tripulante, id_voo) -> BoolVar. `sobrecarga` mapeia
    id_tripulante -> IntVar (em minutos inteiros) da folga de jornada restante.
    """

    model: cp_model.CpModel
    variaveis: dict[tuple[str, str], cp_model.IntVar]
    sobrecarga: dict[str, cp_model.IntVar]
    tripulantes: list
    voos: list
    limite_horas: float
    minutos_por_voo: dict[str, int]

    def alocado(self, tripulante_id: str, voo_id: str) -> cp_model.IntVar:
        return self.variaveis[(tripulante_id, voo_id)]


class Restricao(ABC):
    """Uma regra regulatória aplicável ao modelo CP-SAT."""

    #: Identificador curto, usado em logs e na resposta da API.
    nome: str = "restricao"
    #: Referência regulatória, para rastrear a origem da regra.
    referencia: str = ""
    #: Explicação em linguagem natural — é o que a banca vai ler.
    descricao: str = ""

    @abstractmethod
    def aplicar(self, ctx: Contexto) -> None:
        """Adiciona as constraints ao modelo. Não retorna nada."""

    def __str__(self) -> str:  # pragma: no cover - conveniência
        return f"{self.nome} ({self.referencia})"


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

            # O tripulante já está bloqueado antes de otimizar: nenhuma
            # atribuição é permitida, mas ele continua no modelo para que a
            # resposta explique o bloqueio.
            if acumulado_min >= teto_min or not t.descanso_ok:
                for v in ctx.voos:
                    ctx.model.Add(ctx.alocado(t.id, v.id) == 0)
                continue

            carga = sum(
                ctx.alocado(t.id, v.id) * ctx.minutos_por_voo[v.id] for v in ctx.voos
            )
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
            for v in ctx.voos:
                ctx.model.Add(ctx.alocado(t.id, v.id) == 0)


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
                    ctx.model.Add(ctx.alocado(t.id, v.id) == 0)


# ---------------------------------------------------------------------------
# Cobertura: cada voo recebe exatamente um tripulante
# ---------------------------------------------------------------------------
class CoberturaDeVoos(Restricao):
    nome = "cobertura_voos"
    referencia = "Operacional"
    descricao = (
        "Todo voo listado precisa de exatamente um tripulante. Sem esta "
        "restrição o solver 'otimiza' deixando voos sem tripulação."
    )

    def aplicar(self, ctx: Contexto) -> None:
        for v in ctx.voos:
            ctx.model.AddExactlyOne(ctx.alocado(t.id, v.id) for t in ctx.tripulantes)


#: Ordem canônica de aplicação. Restrições de bloqueio primeiro, para que o
#: domínio já esteja reduzido quando a de jornada entrar.
RESTRICOES_PADRAO: tuple[Restricao, ...] = (
    DescansoMinimoEntreJornadas(),
    AclimatacaoDeFuso(),
    LimiteDeJornada(),
    CoberturaDeVoos(),
)


def catalogo_restricoes() -> list[dict[str, str]]:
    """Lista as restrições ativas — usado pelo endpoint /api/otimizacao/restricoes."""
    return [
        {"nome": r.nome, "referencia": r.referencia, "descricao": r.descricao}
        for r in RESTRICOES_PADRAO
    ]
