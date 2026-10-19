-- SkySync - esquema para os TESTES (SQLite)
--
-- Espelha o schema.sql de producao, com os tipos que o SQLite entende.
-- As tabelas e colunas sao as MESMAS, para o SQL das rotas e dos testes rodar
-- igual nos dois bancos.

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

CREATE TABLE IF NOT EXISTS tripulantes (
    id         TEXT PRIMARY KEY,
    nome       TEXT NOT NULL,
    sobrenome  TEXT NOT NULL DEFAULT '',
    cargo      TEXT NOT NULL
               CHECK (cargo IN ('Comandante', 'Copiloto', 'Comissário', 'Comissario')),
    base       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'Disponivel'
               CHECK (status IN ('Disponível', 'Disponivel', 'Reserva', 'Indisponível', 'Indisponivel')),
    criado_em  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voos (
    id              TEXT PRIMARY KEY,
    codigo          TEXT NOT NULL,
    origem          TEXT NOT NULL DEFAULT '',
    destino         TEXT NOT NULL DEFAULT '',
    partida         TEXT NOT NULL DEFAULT '',
    chegada         TEXT NOT NULL DEFAULT '',
    duracao_horas   REAL NOT NULL,
    distancia_km    REAL,
    aeronave        TEXT NOT NULL DEFAULT '',
    pouso_noturno   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'Programado',
    criado_em       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jornadas (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    tripulante_id      TEXT NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    periodo            DATE NOT NULL,
    horas_voadas       REAL NOT NULL DEFAULT 0,
    horas_acumuladas   REAL NOT NULL DEFAULT 0,
    limite_horas       REAL NOT NULL DEFAULT 11.0,
    voos_no_periodo    INTEGER NOT NULL DEFAULT 0,
    ultimo_pouso       TEXT NOT NULL DEFAULT '',
    descanso_ok        INTEGER NOT NULL DEFAULT 1,
    aclimatado         INTEGER NOT NULL DEFAULT 1,
    observacao         TEXT NOT NULL DEFAULT '',
    criado_em          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tripulante_id, periodo)
);

CREATE TABLE IF NOT EXISTS escalas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tripulante_id       TEXT NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    voo_id              TEXT NOT NULL REFERENCES voos (id) ON DELETE CASCADE,
    data                DATE NOT NULL,
    cargo               TEXT NOT NULL DEFAULT '',
    origem              TEXT NOT NULL DEFAULT '',
    destino             TEXT NOT NULL DEFAULT '',
    duracao_horas       REAL NOT NULL DEFAULT 0,
    horas_antes         REAL NOT NULL DEFAULT 0,
    horas_depois        REAL NOT NULL DEFAULT 0,
    limite_aplicado     REAL NOT NULL DEFAULT 11.0,
    ocupacao_percentual REAL NOT NULL DEFAULT 0,
    conforme            INTEGER NOT NULL DEFAULT 1,
    motivo              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'planejado',
    execucao_id         INTEGER REFERENCES execucoes_otimizacao (id) ON DELETE SET NULL,
    criado_em           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tripulante_id, voo_id, data)
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

INSERT OR IGNORE INTO schema_version (versao) VALUES (5);

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
