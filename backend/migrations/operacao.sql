CREATE TABLE IF NOT EXISTS operacao_simulada (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    estado TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
