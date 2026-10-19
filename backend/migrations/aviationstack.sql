-- Não altera os registros manuais nem os dados operacionais existentes.
CREATE TABLE IF NOT EXISTS importacao_voos_estado (
    fonte TEXT PRIMARY KEY,
    proxima_consulta TEXT NOT NULL,
    ultima_tentativa TEXT,
    ultimo_sucesso TEXT,
    ultimo_erro TEXT,
    dia_cota TEXT NOT NULL,
    chamadas_dia INTEGER NOT NULL DEFAULT 0,
    parcial BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS importacao_voos_eventos (
    chave TEXT PRIMARY KEY,
    disrupcao_id INTEGER UNIQUE NOT NULL REFERENCES disrupcoes(id) ON DELETE CASCADE,
    fonte TEXT NOT NULL DEFAULT 'aviationstack',
    observado_em TEXT NOT NULL
);
