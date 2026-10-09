"""Contratos de entrada e saída da API.

Sem Pydantic: dataclasses + validação explícita, para o projeto continuar com
dependência mínima. Se preferir Pydantic, a troca é direta — o formato dos
erros já é compatível com o que a API devolve hoje.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class ValidacaoError(ValueError):
    """Erro de entrada do cliente — vira HTTP 400, nunca 500."""

    def __init__(self, campos: dict[str, str]):
        self.campos = campos
        super().__init__(f"Campos inválidos: {', '.join(campos)}")


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------
@dataclass
class Perfil:
    nome: str
    email: str
    cargo: str = ""
    base: str = ""

    @classmethod
    def from_payload(cls, payload: Any) -> "Perfil":
        if not isinstance(payload, dict):
            raise ValidacaoError({"body": "esperado um objeto JSON"})

        erros: dict[str, str] = {}
        nome = _texto_obrigatorio(payload, "nome", erros)
        email = _texto_obrigatorio(payload, "email", erros)

        if email and "@" not in email:
            erros["email"] = "e-mail inválido"

        if erros:
            raise ValidacaoError(erros)

        return cls(
            nome=nome,
            email=email,
            cargo=_texto_opcional(payload, "cargo"),
            base=_texto_opcional(payload, "base"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Tripulante / alocação (entrada do otimizador)
# ---------------------------------------------------------------------------
@dataclass
class Tripulante:
    """Tripulante disponível para alocação.

    `horas_acumuladas` é o que ele já voou no período de apuração, em horas
    decimais (11.5 = 11h30). `limite_horas` é o teto RBAC 117 aplicável ao
    perfil dele (pouso noturno, aclimatação, revezamento...).
    """

    id: str
    nome: str
    cargo: str
    base: str
    horas_acumuladas: float
    limite_horas: float
    descanso_ok: bool = True
    aclimatado: bool = True

    @classmethod
    def from_payload(cls, payload: Any, indice: int) -> "Tripulante":
        prefixo = f"tripulantes[{indice}]"
        if not isinstance(payload, dict):
            raise ValidacaoError({prefixo: "esperado um objeto"})

        erros: dict[str, str] = {}
        tid = _texto_obrigatorio(payload, "id", erros, prefixo)
        nome = _texto_obrigatorio(payload, "nome", erros, prefixo)

        horas = _numero(payload.get("horas_acumuladas"), f"{prefixo}.horas_acumuladas", erros)
        limite = _numero(payload.get("limite_horas"), f"{prefixo}.limite_horas", erros)

        if horas is not None and horas < 0:
            erros[f"{prefixo}.horas_acumuladas"] = "não pode ser negativo"
        if limite is not None and limite <= 0:
            erros[f"{prefixo}.limite_horas"] = "deve ser maior que zero"

        if erros:
            raise ValidacaoError(erros)

        return cls(
            id=tid,
            nome=nome,
            cargo=_texto_opcional(payload, "cargo"),
            base=_texto_opcional(payload, "base"),
            horas_acumuladas=horas,
            limite_horas=limite,
            descanso_ok=bool(payload.get("descanso_ok", True)),
            aclimatado=bool(payload.get("aclimatado", True)),
        )


@dataclass
class Voo:
    """Voo que precisa de tripulação."""

    id: str
    codigo: str
    origem: str
    destino: str
    duracao_horas: float
    pouso_noturno: bool = False
    prioridade: int = 1

    @classmethod
    def from_payload(cls, payload: Any, indice: int) -> "Voo":
        prefixo = f"voos[{indice}]"
        if not isinstance(payload, dict):
            raise ValidacaoError({prefixo: "esperado um objeto"})

        erros: dict[str, str] = {}
        vid = _texto_obrigatorio(payload, "id", erros, prefixo)
        duracao = _numero(payload.get("duracao_horas"), f"{prefixo}.duracao_horas", erros)

        if duracao is not None and duracao <= 0:
            erros[f"{prefixo}.duracao_horas"] = "deve ser maior que zero"

        if erros:
            raise ValidacaoError(erros)

        return cls(
            id=vid,
            codigo=_texto_opcional(payload, "codigo") or vid,
            origem=_texto_opcional(payload, "origem"),
            destino=_texto_opcional(payload, "destino"),
            duracao_horas=duracao,
            pouso_noturno=bool(payload.get("pouso_noturno", False)),
            prioridade=int(payload.get("prioridade", 1) or 1),
        )


@dataclass
class RequisicaoOtimizacao:
    base: str
    tripulantes: list[Tripulante]
    voos: list[Voo]
    limite_horas: float | None = None

    @classmethod
    def from_payload(cls, payload: Any, limite_padrao: float) -> "RequisicaoOtimizacao":
        if not isinstance(payload, dict):
            raise ValidacaoError({"body": "esperado um objeto JSON"})

        erros: dict[str, str] = {}
        base = _texto_obrigatorio(payload, "base", erros)

        tripulantes_raw = payload.get("tripulantes")
        voos_raw = payload.get("voos")

        if not isinstance(tripulantes_raw, list) or not tripulantes_raw:
            erros["tripulantes"] = "informe ao menos um tripulante"
            tripulantes_raw = []
        if not isinstance(voos_raw, list) or not voos_raw:
            erros["voos"] = "informe ao menos um voo"
            voos_raw = []

        if erros:
            raise ValidacaoError(erros)

        tripulantes = [Tripulante.from_payload(t, i) for i, t in enumerate(tripulantes_raw)]
        voos = [Voo.from_payload(v, i) for i, v in enumerate(voos_raw)]

        limite = payload.get("limite_horas")
        limite = float(limite) if isinstance(limite, (int, float)) else limite_padrao

        return cls(base=base, tripulantes=tripulantes, voos=voos, limite_horas=limite)


# ---------------------------------------------------------------------------
# Escala (payload aceito no histórico)
# ---------------------------------------------------------------------------
@dataclass
class ItemEscala:
    voo: str
    tripulante: str = ""
    cargo: str = ""
    risco: str = "baixo"
    descricao: str = ""
    rota: str = ""
    horario: str = ""
    horas: str = ""
    limit_rbac: str = ""
    solucao: str = ""
    bloqueado: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    CAMPOS_CONHECIDOS = {
        "voo", "tripulante", "cargo", "risco", "desc", "descricao", "rota",
        "horario", "horas", "limitRbac", "limit_rbac", "solucao", "bloqueado",
        "badgeKey",
    }

    @classmethod
    def from_payload(cls, payload: Any, indice: int) -> "ItemEscala":
        prefixo = f"escalas[{indice}]"
        if not isinstance(payload, dict):
            raise ValidacaoError({prefixo: "esperado um objeto"})

        erros: dict[str, str] = {}
        voo = _texto_obrigatorio(payload, "voo", erros, prefixo)

        risco = str(payload.get("risco", "baixo")).lower()
        if risco not in {"alto", "medio", "baixo"}:
            erros[f"{prefixo}.risco"] = "deve ser alto, medio ou baixo"

        if erros:
            raise ValidacaoError(erros)

        extra = {k: v for k, v in payload.items() if k not in cls.CAMPOS_CONHECIDOS}

        return cls(
            voo=voo,
            tripulante=_texto_opcional(payload, "tripulante"),
            cargo=_texto_opcional(payload, "cargo"),
            risco=risco,
            descricao=_texto_opcional(payload, "desc") or _texto_opcional(payload, "descricao"),
            rota=_texto_opcional(payload, "rota"),
            horario=_texto_opcional(payload, "horario"),
            horas=_texto_opcional(payload, "horas"),
            limit_rbac=_texto_opcional(payload, "limitRbac") or _texto_opcional(payload, "limit_rbac"),
            solucao=_texto_opcional(payload, "solucao"),
            bloqueado=bool(payload.get("bloqueado", False)),
            extra=extra,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        extra = d.pop("extra", {}) or {}
        d["desc"] = d.pop("descricao", "")
        d["limitRbac"] = d.pop("limit_rbac", "")
        d["badgeKey"] = "highFatigueRisk" if self.risco == "alto" else "normalOperation"
        d.update(extra)
        return d


def validar_lista_escalas(payload: Any) -> list[ItemEscala]:
    if not isinstance(payload, list):
        raise ValidacaoError({"dados": "esperado uma lista de itens de escala"})
    return [ItemEscala.from_payload(item, i) for i, item in enumerate(payload)]


# ---------------------------------------------------------------------------
# Helpers de validação
# ---------------------------------------------------------------------------
def _texto_obrigatorio(
    payload: dict, chave: str, erros: dict[str, str], prefixo: str = ""
) -> str:
    valor = payload.get(chave)
    if not isinstance(valor, str) or not valor.strip():
        erros[f"{prefixo}.{chave}".lstrip(".")] = "campo obrigatório"
        return ""
    return valor.strip()


def _texto_opcional(payload: dict, chave: str) -> str:
    valor = payload.get(chave)
    return valor.strip() if isinstance(valor, str) else ""


def _numero(valor: Any, campo: str, erros: dict[str, str]) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        erros[campo] = "deve ser um número"
        return None
    return numero
