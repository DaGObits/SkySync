from pathlib import Path

# --- 1. models.py: adicionar to_dict() em Tripulante e Voo -------------------
m = Path("models.py")
texto = m.read_text(encoding="utf-8")

METODO_TRIP = '''    def to_dict(self) -> dict[str, Any]:
        """Formato serializavel — usado pelo gerador de cenarios e pela API."""
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
class Voo:'''

if "def to_dict" in texto and '"aclimatado": self.aclimatado' in texto:
    print("models.py: Tripulante.to_dict ja existe.")
else:
    alvo = "@dataclass\nclass Voo:"
    if alvo in texto:
        texto = texto.replace(alvo, METODO_TRIP, 1)
        print("models.py: Tripulante.to_dict adicionado.")
    else:
        print("models.py: PADRAO DO VOO NAO ENCONTRADO.")

METODO_VOO = '''    def to_dict(self) -> dict[str, Any]:
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
class RequisicaoOtimizacao:'''

if '"pouso_noturno": self.pouso_noturno' in texto:
    print("models.py: Voo.to_dict ja existe.")
else:
    alvo2 = "@dataclass\nclass RequisicaoOtimizacao:"
    if alvo2 in texto:
        texto = texto.replace(alvo2, METODO_VOO, 1)
        print("models.py: Voo.to_dict adicionado.")
    else:
        print("models.py: PADRAO DO REQUISICAO NAO ENCONTRADO.")

m.write_text(texto, encoding="utf-8")

# --- 2. test_api.py: verificacao de senha sem fixar algoritmo ---------------
t = Path("tests/test_api.py")
tt = t.read_text(encoding="utf-8")

antigo = '''    assert linha["senha_hash"] != "Senha123"
    assert linha["senha_hash"].startswith("pbkdf2:")'''
novo = '''    from werkzeug.security import check_password_hash

    hash_guardado = linha["senha_hash"]
    assert hash_guardado != "Senha123"
    assert "Senha123" not in hash_guardado
    assert check_password_hash(hash_guardado, "Senha123")'''

if antigo in tt:
    t.write_text(tt.replace(antigo, novo), encoding="utf-8")
    print("test_api.py: verificacao de senha corrigida.")
elif "check_password_hash" in tt:
    print("test_api.py: ja estava corrigido.")
else:
    print("test_api.py: PADRAO NAO ENCONTRADO.")

print()
print("Agora rode:  .venv\\Scripts\\python.exe -m pytest -v")
