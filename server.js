const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const bodyParser = require('body-parser');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(bodyParser.json());

// Inicialização do Banco de Dados SQLite
const db = new sqlite3.Database('./skysync.db', (err) => {
  if (err) {
    console.error('Erro ao abrir o banco de dados:', err.message);
  } else {
    console.log('Conectado ao banco de dados SQLite do SkySync.');
  }
});

// Criar tabelas necessárias para o painel principal
db.serialize(() => {
  // Tabela de Configurações do Usuário Logado
  db.run(`CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    name TEXT,
    role TEXT,
    base TEXT,
    idioma TEXT,
    theme TEXT,
    contrast TEXT,
    font_size TEXT,
    density TEXT
  )`);

  // Tabela de Escalas e Tripulantes da Base
  db.run(`CREATE TABLE IF NOT EXISTS crew_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base TEXT,
    crew_name TEXT,
    role TEXT,
    flight_code TEXT,
    accumulated_hours TEXT,
    numeric_hours REAL,
    rbac_limit TEXT,
    is_blocked INTEGER,
    suggested_route TEXT
  )`);

  // Tabela de Atividades em Tempo Real (Feed)
  db.run(`CREATE TABLE IF NOT EXISTS realtime_feed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);
});

// --- ROTAS DA API DO PAINEL PRINCIPAL ---

// 1. Obter e atualizar configurações do usuário
app.get('/api/settings/:email', (req, res) => {
  const { email } = req.params;
  db.get(`SELECT * FROM user_settings WHERE email = ?`, [email], (err, row) => {
    if (err) {
      return res.status(500).json({ error: err.message });
    }
    if (!row) {
      // Retorna padrão se não encontrar
      return res.json({
        name: 'Marina Costa',
        role: 'Coordenadora Operacional',
        base: 'GRU — Guarulhos',
        email: email,
        idioma: 'pt-BR',
        theme: 'light',
        contrast: 'normal',
        font_size: '1',
        density: 'comfortable'
      });
    }
    res.json(row);
  });
});

app.post('/api/settings', (req, res) => {
  const { email, name, role, base, idioma, theme, contrast, font_size, density } = req.body;
  
  const query = `
    INSERT INTO user_settings (email, name, role, base, idioma, theme, contrast, font_size, density)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(email) DO UPDATE SET
      name = excluded.name,
      role = excluded.role,
      base = excluded.base,
      idioma = excluded.idioma,
      theme = excluded.theme,
      contrast = excluded.contrast,
      font_size = excluded.font_size,
      density = excluded.density
  `;

  db.run(query, [email, name, role, base, idioma, theme, contrast, font_size, density], function(err) {
    if (err) {
      return res.status(500).json({ error: err.message });
    }
    res.json({ success: true, message: 'Configurações atualizadas com sucesso!' });
  });
});

// 2. Obter Disrupções Dinâmicas com base na Base Aérea selecionada
app.get('/api/disruptions/:baseCode', (req, res) => {
  const baseCode = req.params.baseCode.toUpperCase();

  // Simulação inteligente de disrupções parametrizada pela base
  const disrupcoes = [
    { 
      voo: 'JJ-3482', 
      risco: 'alto', 
      badge: 'Risco alto de fadiga', 
      desc: `Atraso operacional crítico na base ${baseCode} devido a restrições meteorológicas severas. Tripulação aproxima o limite máximo de jornada da RBAC 117.`, 
      rota: `${baseCode} → GRU`, 
      horario: 'Partida prevista 23:40' 
    },
    { 
      voo: 'JJ-1207', 
      risco: 'medio', 
      badge: 'Risco moderado', 
      desc: `Manutenção não programada de aeronave oriunda de ${baseCode}. Tripulação reserva acionada em aeroporto alternativo.`, 
      rota: 'CGH → SSA', 
      horario: 'Partida prevista 06:15' 
    },
    { 
      voo: 'JJ-5590', 
      risco: 'alto', 
      badge: 'Risco alto de fadiga', 
      desc: `Fechamento parcial de pista afetando conexões diretas com ${baseCode}, estendendo o tempo de toque e repouso.`, 
      rota: `REC → ${baseCode}`, 
      horario: 'Chegada revisada 21:05' 
    },
    { 
      voo: 'JJ-4412', 
      risco: 'baixo', 
      badge: 'Operação normal', 
      desc: `Voo operando perfeitamente sem restrições ou alertas na malha da base ${baseCode}. Tripulação dentro dos parâmetros padrão.`, 
      rota: `${baseCode} → CNF`, 
      horario: 'Partida prevista 15:00' 
    }
  ];

  res.json({ base: baseCode, total: disrupcoes.length, disruptions: disrupcoes });
});

// 3. Obter Escalas Cruzadas e Conformidade da Tripulação
app.get('/api/schedules/:baseCode', (req, res) => {
  const baseCode = req.params.baseCode.toUpperCase();

  // Dados gerados dinamicamente para simular o motor CP-SAT
  const poolCrew = [
    { nome: 'Rafael Nunes', cargo: 'Comandante', horas: '11h30', numeric: 11.5, bloqueado: 1, limit: '11h00 (pouso à noite)', rota: `${baseCode} → GRU → reserva assume` },
    { nome: 'Beatriz Lima', cargo: 'Copiloto', horas: '08h15', numeric: 8.25, bloqueado: 0, limit: '11h00 (pouso à noite)', rota: 'CGH → SSA → sem alteração' },
    { nome: 'Carlos Mendonça', cargo: 'Comissário-chefe', horas: '12h00', numeric: 12.0, bloqueado: 1, limit: '14h00 (jornada padrão)', rota: `REC → ${baseCode} → descanso red.` },
    { nome: 'Juliana Prado', cargo: 'Comissária', horas: '07h45', numeric: 7.75, bloqueado: 0, limit: '14h00 (jornada padrão)', rota: 'BSB → GIG → apoio acionado' },
    { nome: 'Eduardo Silveira', cargo: 'Comandante', horas: '11h10', numeric: 11.16, bloqueado: 1, limit: '11h00 (pouso à noite)', rota: `${baseCode} → CNF → troca reserva` }
  ];

  const total = poolCrew.length;
  const blockedCount = poolCrew.filter(c => c.bloqueado === 1).length;
  const complianceRate = Math.round(((total - blockedCount) / total) * 100);

  res.json({
    base: baseCode,
    total_monitored: total,
    blocked_rbac117: blockedCount,
    compliance_percentage: complianceRate,
    crew: poolCrew
  });
});

// 4. Endpoint de Execução da Simulação do Replanejamento (Motor CP-SAT)
app.post('/api/simulate-optimization', (req, res) => {
  const { base } = req.body;
  // Simula o recálculo do motor de otimização de tripulações
  res.json({
    success: true,
    message: `Motor CP-SAT executado com sucesso para a base ${base}. Conflitos de fadiga mitigados.`,
    new_compliance: '100%'
  });
});

app.listen(PORT, () => {
  console.log(`Backend do SkySync rodando na porta ${PORT}`);
});