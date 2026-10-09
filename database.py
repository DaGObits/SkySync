import sqlite3
import json

DB_NAME = "skysync.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela de Usuários / Perfil
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            cargo TEXT,
            base TEXT
        )
    ''')

    # Tabela de Histórico de Versões de Escalas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_escalas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            versao_index INTEGER,
            dados_json TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de Disrupções e Voos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS disrupcoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voo TEXT NOT NULL,
            tripulante TEXT,
            cargo TEXT,
            risco TEXT,
            descricao TEXT,
            rota TEXT,
            horario TEXT,
            horas TEXT,
            limit_rbac TEXT,
            solucao TEXT,
            bloqueado BOOLEAN
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Banco de dados inicializado com sucesso!")
