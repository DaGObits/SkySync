from app import create_app
from models import Tripulante, Voo
app = create_app("testing")

with app.app_context():
    from optimizer.solver import _bases_por_regiao, _bases_elegiveis, _TODAS_AS_BASES

    reg = _bases_por_regiao()
    print("regioes carregadas:", len(reg))

    eleg = _bases_elegiveis("GRU", reg)
    print("tipo de bases_elegiveis:", type(eleg).__name__)
    if isinstance(eleg, set):
        print("bases de GRU:", sorted(eleg)[:12])
    print("'GRU' esta em bases_elegiveis?", "GRU" in eleg)
    print("'GRU' in _TODAS_AS_BASES?", "GRU" in _TODAS_AS_BASES)
