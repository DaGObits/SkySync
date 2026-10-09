-- SkySync — esquema do banco de dados
-- Versão: 1
--
-- Este arquivo é a fonte única da verdade do esquema. O app executa este script
-- na inicialização; não há CREATE TABLE espalhado pelo código.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Perfil do usuário ativo
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    cargo      TEXT,
    base       TEXT,
    criado_em  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Versões de escala (histórico imutável, uma linha por versão salva)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_escalas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    versao_index INTEGER NOT NULL,
    dados_json   TEXT    NOT NULL,
    criado_em    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Impede versões duplicadas em requisições concorrentes: o índice UNIQUE faz o
-- banco rejeitar a segunda escrita em vez de gravar silenciosamente.
CREATE UNIQUE INDEX IF NOT EXISTS ux_historico_versao
    ON historico_escalas (versao_index);

CREATE INDEX IF NOT EXISTS ix_historico_criado_em
    ON historico_escalas (criado_em DESC);

-- ---------------------------------------------------------------------------
-- Disrupções operacionais
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disrupcoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    voo         TEXT    NOT NULL,
    tripulante  TEXT,
    cargo       TEXT,
    risco       TEXT    CHECK (risco IN ('alto', 'medio', 'baixo')),
    descricao   TEXT,
    rota        TEXT,
    horario     TEXT,
    horas       TEXT,
    limit_rbac  TEXT,
    solucao     TEXT,
    bloqueado   BOOLEAN NOT NULL DEFAULT 0,
    base        TEXT,
    criado_em   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_disrupcoes_base ON disrupcoes (base);

-- ---------------------------------------------------------------------------
-- Registro das execuções do otimizador (trilha de auditoria do CP-SAT)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execucoes_otimizacao (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    base              TEXT,
    status_solver     TEXT NOT NULL,   -- OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN
    wall_time_seconds REAL,
    conformidade      REAL,
    total_tripulantes INTEGER,
    total_bloqueados  INTEGER,
    detalhes_json     TEXT,
    criado_em         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Metadados de migração, para versionar o esquema nas próximas entregas.
CREATE TABLE IF NOT EXISTS schema_version (
    versao     INTEGER PRIMARY KEY,
    aplicado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (versao) VALUES (1);
