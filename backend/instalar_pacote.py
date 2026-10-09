"""Instala os arquivos da pasta `pacote` nos lugares certos.

Le TUDO que estiver em `pacote/` e copia para a estrutura do backend,
reconhecendo os nomes auxiliares (blueprints_*, schema_*) e colocando
cada arquivo no destino correto.

Uso:  .venv\\Scripts\\python.exe instalar_pacote.py
"""
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PACOTE = RAIZ / "pacote"

# Nome no pacote  ->  destino no backend
MAPA = {
    # scripts soltos na raiz do backend
    "sincronizar.py": "sincronizar.py",
    "sincronizar_voos.py": "sincronizar_voos.py",
    "importar_tripulantes.py": "importar_tripulantes.py",
    "importar_voos.py": "importar_voos.py",
    "integrar_escalas.py": "integrar_escalas.py",
    "adicionar_aba_tripulantes.py": "adicionar_aba_tripulantes.py",
    "seed.py": "seed.py",
    "migrar.py": "migrar.py",
    # sql
    "schema.sql": "schema.sql",
    "schema_voos.sql": "schema_voos.sql",
    "malha_seed.sql": "malha_seed.sql",
    # blueprints (nomes "achatados" no pacote)
    "blueprints_tripulantes.py": "blueprints/tripulantes.py",
    "blueprints_escalas_voos.py": "blueprints/escalas_voos.py",
    "escalas_voos.py": "blueprints/escalas_voos.py",
    "cenarios.py": "blueprints/cenarios.py",
    "blueprints_init.py": "blueprints/__init__.py",
    # dados
    "malha_voos.py": "dados/malha_voos.py",
    "gerador.py": "dados/gerador.py",
    "malha.py": "dados/malha.py",
    "nomes.py": "dados/nomes.py",
    # optimizer
    "solver.py": "optimizer/solver.py",
    "restricoes.py": "optimizer/restricoes.py",
    # raiz do backend
    "app.py": "app.py",
    "config.py": "config.py",
    "db.py": "db.py",
    "models.py": "models.py",
    # testes
    "conftest.py": "tests/conftest.py",
    "test_api.py": "tests/test_api.py",
    "test_solver.py": "tests/test_solver.py",
    "test_tripulantes.py": "tests/test_tripulantes.py",
    "schema_teste.sql": "tests/schema_teste.sql",
}

IGNORAR = {".txt", ".md", ".pdf", ".zip", ".png", ".jpg"}


def main() -> int:
    if not PACOTE.exists():
        print(f"ERRO: pasta 'pacote' nao encontrada em {RAIZ}")
        print("Coloque os arquivos em C:\\SkySync\\backend\\pacote\\ e rode de novo.")
        return 1

    arquivos = [p for p in PACOTE.rglob("*") if p.is_file()]
    print(f"Encontrados {len(arquivos)} arquivo(s) em pacote/")
    print()

    copiados = substituidos = ignorados = desconhecidos = 0

    for origem in sorted(arquivos):
        nome = origem.name
        if origem.suffix.lower() in IGNORAR:
            ignorados += 1
            continue

        destino_rel = MAPA.get(nome)
        if destino_rel is None:
            print(f"  ? {nome}  (nao mapeado — copie a mao se precisar)")
            desconhecidos += 1
            continue

        destino = RAIZ / destino_rel
        destino.parent.mkdir(parents=True, exist_ok=True)

        if destino.exists():
            shutil.copy2(destino, destino.with_suffix(destino.suffix + ".bak"))
            shutil.copy2(origem, destino)
            print(f"  SUBSTIT {destino_rel}  (backup .bak)")
            substituidos += 1
        else:
            shutil.copy2(origem, destino)
            print(f"  NOVO    {destino_rel}")
            copiados += 1

    print()
    print(f"{copiados} novo(s), {substituidos} substituido(s), "
          f"{ignorados} ignorado(s), {desconhecidos} sem mapa.")
    print()

    if desconhecidos:
        print("Arquivos sem mapa precisam ser copiados a mao.")
        print()

    print("Confira a estrutura:")
    print("  dir blueprints")
    print("  dir dados")
    print("  dir tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
