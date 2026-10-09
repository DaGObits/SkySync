-- SkySync — esquema para os TESTES (SQLite em memória)
--
-- Por que este arquivo existe: traduzir o schema PostgreSQL para SQLite por
-- expressão regular era frágil — cada mudança no schema quebrava os testes de
-- uma forma difícil de diagnosticar. Manter um schema próprio para o ambiente
-- de teste é mais honesto: o PostgreSQL continua sendo o banco de produção e é
-- validado ao subir a aplicação (`flask --app app init-db`).
--
-- Diferença em relação ao schema de produção:
--   * INTEGER PRIMARY KEY AUTOINCREMENT no lugar de SERIAL
--   * TEXT no lugar de JSONB e TIMESTAMPTZ
--   * Sem índices de expressão (LOWER(email)) — o SQLite não suporta
--
-- As tabelas e colunas são as MESMAS, para que o SQL das rotas e dos testes
-- rode igual nos dois bancos.

CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    senha_hash    TEXT,
    cargo         TEXT NOT NULL DEFAULT '',
    base          TEXT NOT NULL DEFAULT '',
    ativo         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aeroportos (
    iata      TEXT PRIMARY KEY,
    cidade    TEXT NOT NULL,
    uf        TEXT NOT NULL DEFAULT '',
    regiao    TEXT NOT NULL DEFAULT '',
    latitude  REAL,
    longitude REAL,
    hub       INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cenarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT NOT NULL DEFAULT '',
    base          TEXT NOT NULL DEFAULT 'GRU',
    seed          INTEGER NOT NULL,
    n_tripulantes INTEGER NOT NULL,
    n_voos        INTEGER NOT NULL,
    disrupcao     REAL NOT NULL DEFAULT 0,
    composicao    TEXT,
    dados_json    TEXT NOT NULL,
    criado_em     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_escalas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id   INTEGER REFERENCES usuarios (id) ON DELETE SET NULL,
    versao_index INTEGER NOT NULL UNIQUE,
    dados_json   TEXT NOT NULL,
    criado_em    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS disrupcoes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    voo        TEXT NOT NULL,
    tripulante TEXT NOT NULL DEFAULT '',
    cargo      TEXT NOT NULL DEFAULT '',
    risco      TEXT NOT NULL DEFAULT 'baixo'
               CHECK (risco IN ('alto', 'medio', 'baixo')),
    descricao  TEXT NOT NULL DEFAULT '',
    rota       TEXT NOT NULL DEFAULT '',
    horario    TEXT NOT NULL DEFAULT '',
    horas      TEXT NOT NULL DEFAULT '',
    limit_rbac TEXT NOT NULL DEFAULT '',
    solucao    TEXT NOT NULL DEFAULT '',
    bloqueado  INTEGER NOT NULL DEFAULT 0,
    base       TEXT NOT NULL DEFAULT '',
    criado_em  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS execucoes_otimizacao (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    base              TEXT NOT NULL DEFAULT '',
    cenario_id        INTEGER REFERENCES cenarios (id) ON DELETE SET NULL,
    status_solver     TEXT NOT NULL,
    wall_time_seconds REAL,
    objetivo_valor    REAL,
    conformidade      REAL,
    total_tripulantes INTEGER,
    total_voos        INTEGER,
    total_alocacoes   INTEGER,
    variaveis_criadas INTEGER,
    total_bloqueados  INTEGER,
    detalhes_json     TEXT,
    criado_em         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_version (
    versao      INTEGER PRIMARY KEY,
    aplicado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (versao) VALUES (3);
