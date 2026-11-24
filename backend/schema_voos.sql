-- SkySync — tabelas de voos, jornadas e escalas
-- Versao: 5
--
-- Estas tres tabelas fecham o ciclo de otimizacao:
--   voos      -> a malha que precisa de tripulacao
--   jornadas  -> o que cada tripulante ja voou (insumo das restricoes RBAC)
--   escalas   -> o resultado da alocacao, com a analise de conformidade
--
-- Antes disso, voos e jornadas existiam so em memoria durante a chamada da API:
-- nada persistia, e nao havia como auditar uma decisao do motor depois.

-- ---------------------------------------------------------------------------
-- Malha de voos
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS voos (
    id              TEXT PRIMARY KEY,          -- "V0001"
    codigo          TEXT NOT NULL,             -- "TAM-3482"
    origem          TEXT NOT NULL DEFAULT '',
    destino         TEXT NOT NULL DEFAULT '',
    partida         TEXT NOT NULL DEFAULT '',  -- HH:MM
    chegada         TEXT NOT NULL DEFAULT '',  -- HH:MM
    duracao_horas   DOUBLE PRECISION NOT NULL,
    distancia_km    DOUBLE PRECISION,
    aeronave        TEXT NOT NULL DEFAULT '',
    pouso_noturno   BOOLEAN NOT NULL DEFAULT FALSE,
    status          TEXT NOT NULL DEFAULT 'Programado'
                    CHECK (status IN ('Programado', 'Em voo', 'Concluído', 'Cancelado')),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_voos_origem ON voos (origem);
CREATE INDEX IF NOT EXISTS ix_voos_destino ON voos (destino);
CREATE INDEX IF NOT EXISTS ix_voos_partida ON voos (partida);
CREATE INDEX IF NOT EXISTS ix_voos_codigo ON voos (codigo);

-- ---------------------------------------------------------------------------
-- Jornadas — o que cada tripulante ja cumpriu
-- ---------------------------------------------------------------------------
-- A partir de agora as jornadas COMECAM A COMPUTAR: cada linha e um acumulado
-- do periodo de apuracao. As restricoes da RBAC 117 leem daqui:
--   horas_acumuladas -> base do limite de jornada (117.030 / 117.040)
--   descanso_ok      -> 117.095
--   aclimatado       -> 117.135
CREATE TABLE IF NOT EXISTS jornadas (
    id                 SERIAL PRIMARY KEY,
    tripulante_id      TEXT NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    periodo            DATE NOT NULL,
    horas_voadas       DOUBLE PRECISION NOT NULL DEFAULT 0,
    horas_acumuladas   DOUBLE PRECISION NOT NULL DEFAULT 0,
    limite_horas       DOUBLE PRECISION NOT NULL DEFAULT 11.0,
    voos_no_periodo    INTEGER NOT NULL DEFAULT 0,
    ultimo_pouso       TEXT NOT NULL DEFAULT '',
    descanso_ok        BOOLEAN NOT NULL DEFAULT TRUE,
    aclimatado         BOOLEAN NOT NULL DEFAULT TRUE,
    observacao         TEXT NOT NULL DEFAULT '',
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tripulante_id, periodo)
);

CREATE INDEX IF NOT EXISTS ix_jornadas_tripulante ON jornadas (tripulante_id);
CREATE INDEX IF NOT EXISTS ix_jornadas_periodo ON jornadas (periodo DESC);
CREATE INDEX IF NOT EXISTS ix_jornadas_disponiveis
    ON jornadas (descanso_ok, aclimatado) WHERE descanso_ok;

-- ---------------------------------------------------------------------------
-- Escalas — o resultado da alocacao, com a analise
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalas (
    id                  SERIAL PRIMARY KEY,
    tripulante_id       TEXT NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    voo_id              TEXT NOT NULL REFERENCES voos (id) ON DELETE CASCADE,
    data                DATE NOT NULL,
    cargo               TEXT NOT NULL DEFAULT '',
    origem              TEXT NOT NULL DEFAULT '',
    destino             TEXT NOT NULL DEFAULT '',
    duracao_horas       DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- Analise no momento da alocacao — e o dado do capitulo de resultados:
    -- permite reconstruir POR QUE o motor escolheu esta pessoa para este voo.
    horas_antes         DOUBLE PRECISION NOT NULL DEFAULT 0,
    horas_depois        DOUBLE PRECISION NOT NULL DEFAULT 0,
    limite_aplicado     DOUBLE PRECISION NOT NULL DEFAULT 11.0,
    ocupacao_percentual DOUBLE PRECISION NOT NULL DEFAULT 0,
    conforme            BOOLEAN NOT NULL DEFAULT TRUE,
    motivo              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'planejado'
                        CHECK (status IN ('planejado', 'confirmado', 'bloqueado', 'desfeito')),
    execucao_id         INTEGER REFERENCES execucoes_otimizacao (id) ON DELETE SET NULL,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Um tripulante nao pode estar em dois voos no mesmo dia.
    UNIQUE (tripulante_id, voo_id, data)
);

CREATE INDEX IF NOT EXISTS ix_escalas_data ON escalas (data DESC);
CREATE INDEX IF NOT EXISTS ix_escalas_tripulante ON escalas (tripulante_id);
CREATE INDEX IF NOT EXISTS ix_escalas_voo ON escalas (voo_id);
CREATE INDEX IF NOT EXISTS ix_escalas_conforme ON escalas (conforme);
CREATE INDEX IF NOT EXISTS ix_escalas_execucao ON escalas (execucao_id);

-- ---------------------------------------------------------------------------
-- Metadados de migracao
-- ---------------------------------------------------------------------------
INSERT INTO schema_version (versao) VALUES (5)
    ON CONFLICT (versao) DO NOTHING;
