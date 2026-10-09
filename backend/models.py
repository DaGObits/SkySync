"""Modelos de entrada e saida da API."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CARGOS_VALIDOS = ("Comandante", "Copiloto", "Comissário")


class ValidacaoError(ValueError):
    def __init__(self, campos):
        self.campos = campos
        super().__init__("Campos invalidos: " + ", ".join(campos))


@dataclass
class Tripulante:
    id: str
    nome: str
    cargo: str
    base: str
    horas_acumuladas: float
    limite_horas: float
    descanso_ok: bool = True
    aclimatado: bool = True

    @classmethod
    def from_payload(cls, payload, indice):
        prefixo = f"tripulantes[{indice}]"
        if not isinstance(payload, dict):
            raise ValidacaoError({prefixo: "esperado um objeto"})
        erros = {}
        tid = _texto_obrigatorio(payload, "id", erros, prefixo)
        nome = _texto_obrigatorio(payload, "nome", erros, prefixo)
        cargo = str(payload.get("cargo", "")).strip()
        if cargo not in CARGOS_VALIDOS:
            erros[f"{prefixo}.cargo"] = "deve ser um de: " + ", ".join(CARGOS_VALIDOS)
        horas = _numero(payload.get("horas_acumuladas"), f"{prefixo}.horas_acumuladas", erros)
        limite = _numero(payload.get("limite_horas"), f"{prefixo}.limite_horas", erros)
        if horas is not None and horas < 0:
            erros[f"{prefixo}.horas_acumuladas"] = "nao pode ser negativo"
        if limite is not None and limite <= 0:
            erros[f"{prefixo}.limite_horas"] = "deve ser maior que zero"
        if erros:
            raise ValidacaoError(erros)
        return cls(
            id=tid, nome=nome, cargo=cargo,
            base=_texto_opcional(payload, "base"),
            horas_acumuladas=horas, limite_horas=limite,
            descanso_ok=bool(payload.get("descanso_ok", True)),
            aclimatado=bool(payload.get("aclimatado", True)),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "cargo": self.cargo,
            "base": self.base,
            "horas_acumuladas": self.horas_acumuladas,
            "limite_horas": self.limite_horas,
            "descanso_ok": self.descanso_ok,
            "aclimatado": self.aclimatado,
        }


@dataclass
class Voo:
    id: str
    codigo: str
    origem: str
    destino: str
    duracao_horas: float
    pouso_noturno: bool = False
    prioridade: int = 1

    @classmethod
    def from_payload(cls, payload, indice):
        prefixo = f"voos[{indice}]"
        if not isinstance(payload, dict):
            raise ValidacaoError({prefixo: "esperado um objeto"})
        erros = {}
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

    def to_dict(self):
        return {
            "id": self.id,
            "codigo": self.codigo,
            "origem": self.origem,
            "destino": self.destino,
            "duracao_horas": self.duracao_horas,
            "pouso_noturno": self.pouso_noturno,
            "prioridade": self.prioridade,
        }


@dataclass
class RequisicaoOtimizacao:
    base: str
    tripulantes: list
    voos: list
    limite_horas: float | None = None
    composicao: dict | None = None

    @classmethod
    def from_payload(cls, payload, limite_padrao):
        if not isinstance(payload, dict):
            raise ValidacaoError({"body": "esperado um objeto JSON"})
        erros = {}
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
        composicao = payload.get("composicao")
        if composicao is not None and not isinstance(composicao, dict):
            raise ValidacaoError({"composicao": "deve ser um objeto cargo -> quantidade"})
        return cls(base=base, tripulantes=tripulantes, voos=voos,
                   limite_horas=limite, composicao=composicao)


@dataclass
class Perfil:
    nome: str
    email: str
    cargo: str = ""
    base: str = ""

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValidacaoError({"body": "esperado um objeto JSON"})
        erros = {}
        nome = _texto_obrigatorio(payload, "nome", erros)
        email = _texto_obrigatorio(payload, "email", erros)
        if email and "@" not in email:
            erros["email"] = "e-mail invalido"
        if erros:
            raise ValidacaoError(erros)
        return cls(nome=nome, email=email,
                   cargo=_texto_opcional(payload, "cargo") or _texto_opcional(payload, "role"),
                   base=_texto_opcional(payload, "base"))

    def to_dict(self):
        return asdict(self)


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
    extra: dict = field(default_factory=dict)

    CAMPOS_CONHECIDOS = {
        "voo", "tripulante", "cargo", "risco", "desc", "descricao", "rota",
        "horario", "horas", "limitRbac", "limit_rbac", "solucao", "bloqueado",
        "badgeKey",
    }

    @classmethod
    def from_payload(cls, payload, indice):
        prefixo = f"escalas[{indice}]"
        if not isinstance(payload, dict):
            raise ValidacaoError({prefixo: "esperado um objeto"})
        erros = {}
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

    def to_dict(self):
        d = asdict(self)
        extra = d.pop("extra", {}) or {}
        d["desc"] = d.pop("descricao", "")
        d["limitRbac"] = d.pop("limit_rbac", "")
        d["badgeKey"] = "highFatigueRisk" if self.risco == "alto" else "normalOperation"
        d.update(extra)
        return d


def validar_lista_escalas(payload):
    if not isinstance(payload, list):
        raise ValidacaoError({"dados": "esperado uma lista de itens de escala"})
    return [ItemEscala.from_payload(item, i) for i, item in enumerate(payload)]


def _texto_obrigatorio(payload, chave, erros, prefixo=""):
    valor = payload.get(chave)
    if not isinstance(valor, str) or not valor.strip():
        erros[f"{prefixo}.{chave}".lstrip(".")] = "campo obrigatorio"
        return ""
    return valor.strip()


def _texto_opcional(payload, chave):
    valor = payload.get(chave)
    return valor.strip() if isinstance(valor, str) else ""


def _numero(valor, campo, erros):
    try:
        return float(valor)
    except (TypeError, ValueError):
        erros[campo] = "deve ser um numero"
        return None
