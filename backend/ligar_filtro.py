from pathlib import Path
import shutil

p = Path("optimizer/solver.py")
t = p.read_text(encoding="utf-8")

if "raio_bases: int = 1," in t:
    print("Ja esta ligado por padrao.")
    raise SystemExit(0)

shutil.copy2(p, p.with_suffix(".py.bak2"))

# 1. O padrao da assinatura
antes = "raio_bases: int = 0,"
if antes not in t:
    print("PADRAO NAO ENCONTRADO na assinatura.")
    raise SystemExit(1)
t = t.replace(antes, "raio_bases: int = 1,", 1)
print("1. assinatura: raio_bases = 1")

# 2. O bloco de comentario que dizia estar desligado.
#    Substitui linha por linha, contando as que comecam com "    O filtro 3".
linhas = t.split("\n")
saida = []
i = 0
trocou = False
while i < len(linhas):
    linha = linhas[i]
    if linha.strip().startswith("O filtro 3") and "DESLIGADO" in linha:
        # Novo bloco, com a medicao real
        saida.append("    O filtro 3 (`raio_bases`) esta LIGADO por padrao, com medicao")
        saida.append("    que o justifica sobre a base real do banco (30 voos, 900 tripulantes):")
        saida.append("")
        saida.append("        raio_bases=0:  OPTIMAL  8,70 s   25.897 variaveis")
        saida.append("        raio_bases=1:  OPTIMAL  1,43 s    6.595 variaveis")
        saida.append("")
        saida.append("    Mesma solucao (150 alocacoes), 6x menos tempo e 4x menos")
        saida.append("    variaveis. A condicao para o filtro ser seguro e o pool ter")
        saida.append("    cobertura em todas as bases de partida — o que `dados.gerador`")
        saida.append("    garante, dimensionando os tripulantes pelas ORIGENS dos voos.")
        saida.append("")
        saida.append("    Use `raio_bases=0` para desligar (util em diagnostico).")
        trocou = True
        # Pula as linhas do bloco antigo (ele ia ate a linha em branco seguinte)
        i += 1
        while i < len(linhas) and linhas[i].strip() and not linhas[i].strip().startswith('"""'):
            i += 1
        continue
    saida.append(linha)
    i += 1

if not trocou:
    print("2. AVISO: o comentario antigo nao foi encontrado — o padrao foi mudado.")

p.write_text("\n".join(saida), encoding="utf-8")
print("2. comentario:", "atualizado" if trocou else "nao encontrado (padrao mudou mesmo assim)")
print()
print("Backup: solver.py.bak2")
print("Agora rode:  .venv\\Scripts\\python.exe -m pytest -v")
