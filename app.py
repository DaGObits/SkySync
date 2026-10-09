from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import requests
from database import conectar_banco
from optimizer import executar_otimizacao_cp_sat

app = Flask(__name__)
CORS(app)  # Libera a comunicação com o front-end

@app.route('/api/status', methods=['GET'])
def status_sistema():
    conexao = conectar_banco()
    db_status = "Conectado ao SQLite" if conexao else "Erro na conexão com o banco"
    if conexao:
        conexao.close()

    return jsonify({
        "sistema": "SkySync API",
        "banco_dados": db_status,
        "motor": "Ativo"
    })

@app.route('/api/simular', methods=['POST'])
def simular():
    return jsonify({"sucesso": True, "mensagem": "Simulação executada com sucesso!"})

# --- ROTA DE CADASTRO ---
@app.route('/api/register', methods=['POST'])
def register():
    dados = request.get_json()
    nome = dados.get('nome')
    email = dados.get('email')
    senha = dados.get('senha')

    if not nome or not email or not senha:
        return jsonify({"erro": "Preencha todos os campos!"}), 400

    senha_hash = hashlib.sha256(senha.encode()).hexdigest()

    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL
            )
        """)

        # Verifica explicitamente se o e-mail já existe
        cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
        usuario_existente = cursor.fetchone()

        if usuario_existente:
            conexao.close()
            return jsonify({"erro": "Este e-mail já está cadastrado no sistema."}), 400

        cursor.execute("INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)", (nome, email, senha_hash))
        conexao.commit()
        conexao.close()
        
        return jsonify({"sucesso": True, "mensagem": "Usuário cadastrado com sucesso!"}), 201

    except Exception as e:
        return jsonify({"erro": f"Ocorreu um erro no servidor: {str(e)}"}), 500

# --- ROTA DE LOGIN ---
@app.route('/api/login', methods=['POST'])
def login():
    dados = request.get_json()
    email = dados.get('email')
    senha = dados.get('senha')

    senha_hash = hashlib.sha256(senha.encode()).hexdigest()

    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute("SELECT id, nome, email FROM usuarios WHERE email = ? AND senha = ?", (email, senha_hash))
    usuario = cursor.fetchone()
    conexao.close()

    if usuario:
        return jsonify({
            "sucesso": True,
            "usuario": {
                "id": usuario[0],
                "nome": usuario[1],
                "email": usuario[2]
            }
        }), 200
    else:
        return jsonify({"erro": "E-mail ou senha incorretos."}), 401

# --- ROTA DE LOGIN COM GOOGLE ---
@app.route('/api/google-login', methods=['POST'])
def google_login():
    dados = request.get_json()
    token = dados.get('token')

    try:
        url_validacao = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
        resposta = requests.get(url_validacao)
        
        if resposta.status_code != 200:
            return jsonify({"erro": "Token do Google inválido."}), 401

        info_google = resposta.json()
        email = info_google.get('email')
        nome = info_google.get('name')

        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL
            )
        """)

        cursor.execute("SELECT id, nome, email FROM usuarios WHERE email = ?", (email,))
        usuario = cursor.fetchone()

        if not usuario:
            cursor.execute("INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)", (nome, email, "GOOGLE_AUTH"))
            conexao.commit()
            cursor.execute("SELECT id, nome, email FROM usuarios WHERE email = ?", (email,))
            usuario = cursor.fetchone()

        conexao.close()

        return jsonify({
            "sucesso": True,
            "usuario": {
                "id": usuario[0],
                "nome": usuario[1],
                "email": usuario[2]
            }
        }), 200

    except Exception as e:
        return jsonify({"erro": "Erro ao processar o login com o Google."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)