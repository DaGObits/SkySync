-- SkySync — esquema do banco de dados (PostgreSQL)
-- Versao: 4
--
-- Este arquivo e a fonte unica da verdade do esquema.
--
-- NOTA SOBRE MIGRACAO: o `init-db` usa CREATE TABLE IF NOT EXISTS, que cria
-- tabela nova mas nao altera tabela existente. Quando o esquema evolui, tabela
-- ja criada precisa de ALTER TABLE explicito — e por isso existe o
-- `sincronizar.py`. A solucao definitiva e migracao versionada; esta e a ponte.

-- ---------------------------------------------------------------------------
-- Usuarios (autenticacao)
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_email ON usuarios (LOWER(email));

-- ---------------------------------------------------------------------------
-- Malha aerea — os vertices do grafo descrito no pre-projeto
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aeroportos (
    iata       TEXT PRIMARY KEY,
    cidade     TEXT NOT NULL,
    uf         TEXT NOT NULL DEFAULT '',
    regiao     TEXT NOT NULL DEFAULT '',
    latitude   DOUBLE PRECISION,
    longitude  DOUBLE PRECISION,
    hub        BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_aeroportos_regiao ON aeroportos (regiao);
CREATE INDEX IF NOT EXISTS ix_aeroportos_hub ON aeroportos (hub) WHERE hub;

-- ---------------------------------------------------------------------------
-- Tripulacao disponivel — base simulada, fonte do pool do otimizador
-- ---------------------------------------------------------------------------
-- O `id` e TEXT de proposito: vem do arquivo da base ("0001"), e preservar o
-- formato original permite rastrear um tripulante de volta ate a planilha.
CREATE TABLE IF NOT EXISTS tripulantes (
    id         TEXT PRIMARY KEY,
    nome       TEXT NOT NULL,
    sobrenome  TEXT NOT NULL DEFAULT '',
    cargo      TEXT NOT NULL
               CHECK (cargo IN ('Comandante', 'Copiloto', 'Comissário')),
    base       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'Disponível'
               CHECK (status IN ('Disponível', 'Reserva', 'Indisponível')),
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_tripulantes_base ON tripulantes (base);
CREATE INDEX IF NOT EXISTS ix_tripulantes_cargo ON tripulantes (cargo);
CREATE INDEX IF NOT EXISTS ix_tripulantes_status ON tripulantes (status);
CREATE INDEX IF NOT EXISTS ix_tripulantes_base_cargo ON tripulantes (base, cargo);

-- ---------------------------------------------------------------------------
-- Cenarios de otimizacao gerados
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cenarios (
    id             SERIAL PRIMARY KEY,
    nome           TEXT NOT NULL DEFAULT '',
    base           TEXT NOT NULL DEFAULT 'GRU',
    seed           INTEGER NOT NULL,
    n_tripulantes  INTEGER NOT NULL,
    n_voos         INTEGER NOT NULL,
    disrupcao      REAL NOT NULL DEFAULT 0,
    composicao     JSONB,
    dados_json     JSONB NOT NULL,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cenarios_criado_em ON cenarios (criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_cenarios_base ON cenarios (base);

-- ---------------------------------------------------------------------------
-- Versoes de escala (historico imutavel)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_escalas (
    id           SERIAL PRIMARY KEY,
    usuario_id   INTEGER REFERENCES usuarios (id) ON DELETE SET NULL,
    versao_index INTEGER     NOT NULL,
    dados_json   JSONB       NOT NULL,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_historico_versao ON historico_escalas (versao_index);
CREATE INDEX IF NOT EXISTS ix_historico_criado_em ON historico_escalas (criado_em DESC);

-- ---------------------------------------------------------------------------
-- Disrupcoes operacionais
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
-- Execucoes do otimizador (auditoria + dados do capitulo de resultados)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execucoes_otimizacao (
    id                SERIAL PRIMARY KEY,
    base              TEXT        NOT NULL DEFAULT '',
    cenario_id        INTEGER REFERENCES cenarios (id) ON DELETE SET NULL,
    status_solver     TEXT        NOT NULL,
    wall_time_seconds DOUBLE PRECISION,
    objetivo_valor    DOUBLE PRECISION,
    conformidade      DOUBLE PRECISION,
    total_tripulantes INTEGER,
    total_voos        INTEGER,
    total_alocacoes   INTEGER,
    variaveis_criadas INTEGER,
    total_bloqueados  INTEGER,
    detalhes_json     JSONB,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_execucoes_criado_em ON execucoes_otimizacao (criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_execucoes_cenario ON execucoes_otimizacao (cenario_id);

-- ---------------------------------------------------------------------------
-- Metadados de migracao
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    versao      INTEGER PRIMARY KEY,
    aplicado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_version (versao) VALUES (4)
    ON CONFLICT (versao) DO NOTHING;
