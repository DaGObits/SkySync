-- SkySync — esquema do banco de dados (PostgreSQL)
-- Versão: 2
--
-- Este arquivo é a fonte única da verdade do esquema.
-- Diferenças em relação à versão SQLite:
--   * SERIAL no lugar de AUTOINCREMENT
--   * TIMESTAMPTZ no lugar de TIMESTAMP (banco em nuvem roda em UTC)
--   * CHECK constraints explícitas
--   * índice de expressão sobre LOWER(email)

-- ---------------------------------------------------------------------------
-- Usuários (autenticação)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id            SERIAL PRIMARY KEY,
    nome          TEXT        NOT NULL,
    email         TEXT        NOT NULL,
    senha_hash    TEXT,
    cargo         TEXT        NOT NULL DEFAULT '',
    base          TEXT        NOT NULL DEFAULT '',
    ativo         BOOLEAN     NOT NULL DEFAULT TRUE,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- E-mail único e comparado em minúsculas: sem isto, "Marina@x.com" e
-- "marina@x.com" viram duas contas.
CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_email
    ON usuarios (LOWER(email));

-- ---------------------------------------------------------------------------
-- Versões de escala (histórico imutável, uma linha por versão salva)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_escalas (
    id           SERIAL PRIMARY KEY,
    usuario_id   INTEGER REFERENCES usuarios (id) ON DELETE SET NULL,
    versao_index INTEGER     NOT NULL,
    dados_json   JSONB       NOT NULL,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_historico_versao
    ON historico_escalas (versao_index);

CREATE INDEX IF NOT EXISTS ix_historico_criado_em
    ON historico_escalas (criado_em DESC);

-- ---------------------------------------------------------------------------
-- Disrupções operacionais
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disrupcoes (
    id         SERIAL PRIMARY KEY,
    voo        TEXT        NOT NULL,
    tripulante TEXT        NOT NULL DEFAULT '',
    cargo      TEXT        NOT NULL DEFAULT '',
    risco      TEXT        NOT NULL DEFAULT 'baixo'
                           CHECK (risco IN ('alto', 'medio', 'baixo')),
    descricao  TEXT        NOT NULL DEFAULT '',
    rota       TEXT        NOT NULL DEFAULT '',
    horario    TEXT        NOT NULL DEFAULT '',
    horas      TEXT        NOT NULL DEFAULT '',
    limit_rbac TEXT        NOT NULL DEFAULT '',
    solucao    TEXT        NOT NULL DEFAULT '',
    bloqueado  BOOLEAN     NOT NULL DEFAULT FALSE,
    base       TEXT        NOT NULL DEFAULT '',
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_disrupcoes_base ON disrupcoes (base);

-- ---------------------------------------------------------------------------
-- Registro das execuções do otimizador (trilha de auditoria do CP-SAT)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execucoes_otimizacao (
    id                SERIAL PRIMARY KEY,
    base              TEXT        NOT NULL DEFAULT '',
    status_solver     TEXT        NOT NULL,
    wall_time_seconds DOUBLE PRECISION,
    objetivo_valor    DOUBLE PRECISION,
    conformidade      DOUBLE PRECISION,
    total_tripulantes INTEGER,
    total_bloqueados  INTEGER,
    detalhes_json     JSONB,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Metadados de migração
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    versao      INTEGER PRIMARY KEY,
    aplicado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_version (versao) VALUES (2)
    ON CONFLICT (versao) DO NOTHING;
