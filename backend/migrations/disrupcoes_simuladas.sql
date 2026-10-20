CREATE TABLE IF NOT EXISTS disrupcoes_simuladas (
    id TEXT PRIMARY KEY,
    operacao_id TEXT NOT NULL,
    risco TEXT NOT NULL,
    ativo BOOLEAN NOT NULL,
    minuto INTEGER NOT NULL,
    atualizado_minuto INTEGER NOT NULL,
    registro TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_disrupcoes_simuladas_operacao ON disrupcoes_simuladas (operacao_id, ativo, atualizado_minuto);
