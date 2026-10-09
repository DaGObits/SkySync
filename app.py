from flask import Flask, jsonify, request
from flask_cors import CORS
from database import get_db_connection, init_db
import json

app = Flask(__name__)
CORS(app)

# Inicializa o banco ao subir a aplicação
init_db()

@app.route('/api/escalas', methods=['GET'])
def get_escalas():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT dados_json FROM historico_escalas ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify(json.loads(row['dados_json']))
    
    # Dados padrão iniciais se a tabela estiver vazia
    dados_iniciais = [
        { id: 1, 'voo': 'TAM-3482', 'tripulante': 'Rafael Nunes', 'cargo': 'Comandante', 'risco': 'alto', 'badgeKey': 'highFatigueRisk', 'desc': 'Atraso operacional crítico devido a restrições meteorológicas severas em Guarulhos.', 'rota': 'GRU → VCP', 'horario': 'Partida prevista 23:40', 'horas': '11h30', 'limitRbac': '11h00 (pouso à noite)', 'solucao': 'Conexão direta GRU → CNF com reserva imediata', 'bloqueado': True }
    ]
    return jsonify(dados_iniciais)

@app.route('/api/escalas/historico', methods=['POST'])
def salvar_historico():
    content = request.json
    dados = content.get('dados')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total FROM historico_escalas')
    total = cursor.fetchone()['total']
    
    cursor.execute('INSERT INTO historico_escalas (versao_index, dados_json) VALUES (?, ?)', 
                   (total, json.dumps(dados)))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "sucesso", "versao": total}), 201

@app.route('/api/perfil', methods=['GET', 'POST'])
def gerenciar_perfil():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        cursor.execute('DELETE FROM usuarios') # Mantém apenas o usuário ativo atual
        cursor.execute('INSERT INTO usuarios (nome, email, cargo, base) VALUES (?, ?, ?, ?)',
                       (data.get('nome'), data.get('email'), data.get('cargo'), data.get('base')))
        conn.commit()
        conn.close()
        return jsonify({"status": "perfil atualizado com sucesso"})
    
    cursor.execute('SELECT * FROM usuarios LIMIT 1')
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify(dict(user))
    return jsonify({"nome": "Marina Costa", "email": "marina.costa@skysync.aero", "cargo": "Coordenadora Operacional", "base": "GRU — Guarulhos"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
