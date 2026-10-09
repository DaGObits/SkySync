import random

RBAC_LIMITS = [
    '11h00 (pouso à noite)',
    '10h00 (múltiplos pousos / fuso)',
    '12h00 (jornada diurna padrão)',
    '13h00 (extensão por revezamento)',
    '9h30 (não aclimatizado)',
    '14h00 (tripulação reforçada)',
    '11h30 (limite adaptado setor)'
]

def gerar_nova_escala_otimizada(dados_atuais):
    nomes = ['Lucas Mendes', 'Fernanda Souza', 'Bruno Ribeiro', 'Camila Rocha', 'Diego Farias', 'Larissa Azevedo', 'Thiago Moreira', 'Mariana Prado', 'Renato Castilho']
    rotas = [
        {'origem': 'GRU', 'destino': 'VCP', 'solucao': 'Conexão direta GRU → CNF com reserva imediata'},
        {'origem': 'CGH', 'destino': 'SSA', 'solucao': 'Realocação CGH → BSB via malha integrada'},
        {'origem': 'REC', 'destino': 'GRU', 'solucao': 'Ajuste de tripulação REC → GIG com repouso em base'},
        {'origem': 'BSB', 'destino': 'GIG', 'solucao': 'Substituição por tripulação de apoio em BSB'},
        {'origem': 'GRU', 'destino': 'CGB', 'solucao': 'Manutenção da escala regular GRU → CGB'}
    ]
    cias = ['TAM', 'GLO', 'AZU', 'PTB']

    nova_escala = []
    for item in dados_atuais:
        novo_item = item.copy()
        novo_item['tripulante'] = random.choice(nomes)
        rota_sel = random.choice(rotas)
        novo_item['rota'] = f"{rota_sel['origem']} → {rota_sel['destino']}"
        novo_item['solucao'] = rota_sel['solucao']
        
        cia = random.choice(cias)
        num = random.randint(1000, 9999)
        novo_item['voo'] = f"{cia}-{num}"

        is_blocked = random.choice([True, False])
        novo_item['bloqueado'] = is_blocked
        novo_item['risco'] = 'alto' if is_blocked else 'baixo'
        novo_item['badgeKey'] = 'highFatigueRisk' if is_blocked else 'normalOperation'
        
        horas = random.randint(6, 13)
        mins = random.randint(0, 59)
        novo_item['horas'] = f"{str(horas).padStart(2, '0') if hasattr(str, 'padStart') else f'{horas:02d}'}h{str(mins).padStart(2, '0') if hasattr(str, 'padStart') else f'{mins:02d}'}"
        novo_item['limitRbac'] = random.choice(RBAC_LIMITS)
        
        nova_escala.append(novo_item)
        
    return nova_escala
