# SkySync

**Sistema de replanejamento de escalas de tripulação com otimização por programação com restrições.**

O SkySync automatiza o replanejamento de escalas em situações de disrupção operacional (atrasos, restrições meteorológicas, manutenção não programada), respeitando os limites de jornada e repouso da **Lei do Aeronauta (Lei nº 13.475/2017)** e do **RBAC 117** da ANAC.

O motor de otimização usa **CP-SAT** (Google OR-Tools) para resolver o problema de alocação como um modelo de programação com restrições: em vez de aplicar regras em `if/else`, as exigências regulatórias viram restrições matemáticas que o solver não pode violar.

---

## Arquitetura

O sistema roda em três camadas independentes:

```
  Navegador
      │
      ▼
  GitHub Pages ──────────► front-end estático (HTML/CSS/JS)
      │
      │  fetch() para a API
      ▼
  Render ────────────────► Flask (API + motor CP-SAT)
      │
      │  psycopg
      ▼
  Neon ──────────────────► PostgreSQL
```

| Camada | Tecnologia | O que hospeda |
|---|---|---|
| Front-end | HTML + CSS + JS puro | Painel, login, 5 abas |
| API | Flask + Gunicorn | 20+ rotas REST, motor CP-SAT |
| Banco | PostgreSQL (Neon) | 10 tabelas, 900 tripulantes |

A separação permite que o front seja servido gratuitamente pelo GitHub Pages enquanto a API roda no Render — e o banco já nasce na nuvem.

---

## O que o sistema faz

### Motor de otimização (CP-SAT)

O modelo resolve a alocação tripulante × voo sob cinco restrições regulatórias, cada uma isolada em uma classe própria:

| Restrição | Referência | O que garante |
|---|---|---|
| `LimiteDeJornada` | RBAC 117.030 / 117.040 | Soma das durações + horas acumuladas não excede o teto do perfil |
| `ComposicaoPorCargo` | RBAC 117.035 | Cada voo recebe 1 comandante, 1 copiloto e 3 comissários |
| `DescansoMinimoEntreJornadas` | RBAC 117.095 | Quem não cumpriu o repouso não recebe nova atribuição |
| `AclimatacaoDeFuso` | RBAC 117.135 | Não aclimatado não recebe voo com pouso noturno |
| `UmVooPorTripulante` | Operacional | Ninguém é designado a dois voos na mesma rodada |

**Função objetivo:** minimizar a folga total de jornada, o que distribui a carga entre os tripulantes em vez de saturar os primeiros.

**Inviabilidade é resposta, não erro.** Quando as restrições tornam o cenário impossível, a API devolve **409** com um diagnóstico estruturado — quantos comandantes faltam, qual é a capacidade disponível, quais foram as causas. Isso é o que permite à operação reagir.

### Base de dados

| Tabela | Conteúdo |
|---|---|
| `tripulantes` | **900** profissionais em **15 bases** |
| `voos` | Malha com origem/destino reais, duração por distância geográfica |
| `jornadas` | Acumulado de cada tripulante — insumo das restrições da RBAC |
| `escalas` | Resultado da alocação, com a análise de conformidade |
| `aeroportos` | 36 aeroportos brasileiros (os vértices da malha) |
| `cenarios` | Cenários gerados, reprodutíveis por seed |
| `execucoes_otimizacao` | Trilha de auditoria de cada rodada do solver |
| `usuarios` | Autenticação, senha com hash |

**A base de tripulação** está na proporção real de uma companhia:

| Cargo | Quantidade |
|---|---|
| Comandante | 150 |
| Copiloto | 150 |
| Tripulante de cabine | 600 |
| **Disponíveis** | 840 |
| **Em reserva** | 60 |

> Os nomes são **sintéticos**, compostos a partir de listas de prenomes e sobrenomes de uso comum no Brasil. Não existe base pública de tripulantes reais, e usá-los seria problema de privacidade. Os parâmetros operacionais (aeroportos, companhias, limites da RBAC) são reais.

### Interface

Cinco abas, com dados vindos da API:

- **Painel** — KPIs de conformidade, risco de fadiga, feed de atividade
- **Disrupções** — ocorrências operacionais por nível de risco
- **Escalas** — alocações com jornada, limite aplicado e conformidade
- **Tripulantes** — a base completa, com filtro por base, cargo e status
- **Configurações** — perfil, aparência, idioma (pt-BR / en / es)

---

## Como rodar localmente

### Pré-requisitos

- Python 3.12+
- Um banco PostgreSQL (local ou em nuvem — [Neon](https://neon.tech) tem plano gratuito)

### Instalação

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### Configuração

```bash
cp .env.example .env
```

Preencha o `.env`:

```env
DATABASE_URL=postgresql://usuario:senha@host/skysync?sslmode=require
SKYSYNC_SECRET_KEY=<gere com: python -c "import secrets; print(secrets.token_hex(32))">
SKYSYNC_ENV=development
```

### Preparar o banco

```bash
flask --app app init-db          # aplica o esquema
python sincronizar.py            # completa tabelas que surgiram depois
python sincronizar_voos.py       # tabelas de voos, jornadas e escalas

python importar_tripulantes.py   # 900 tripulantes
python importar_voos.py          # ~140 voos + jornadas zeradas
python seed.py                   # aeroportos + conta de demonstração
```

### Subir

```bash
python app.py
```

- Painel: http://127.0.0.1:5000/
- Login: `demo@skysync.aero` / `Demo1234`

### Testes

```bash
pytest -v
```

### Disrupções operacionais

A aba **Disrupções** consulta `GET /api/disrupcoes`, que lê a tabela existente
`disrupcoes`. Ela não depende de haver escalas publicadas nem fabrica ocorrências
a partir de voos ao vivo. Os dados do OpenSky não identificam, por si só, causas
como meteorologia ou manutenção.

Usuários autenticados podem registrar voo, descrição, risco e rota pelo formulário
**Registrar ocorrência operacional** (`POST /api/disrupcoes`). A ocorrência
persiste no banco e continua disponível após recarregar. Os filtros distinguem
risco alto, médio e baixo; a contagem destaca risco alto/médio entre os registros
carregados. A lista informa quantos registros foram retornados, até 200 por padrão
(1.000 pelo parâmetro `limite` da API). Não há encerramento de ocorrências nesta versão.

Uma lista vazia significa que nenhuma ocorrência foi registrada; falhas de rede
ou do backend aparecem como erro com opção de atualizar. Esta versão exige novo
deploy do Render após o merge e usa o esquema já existente, sem migração adicional.

### Identidade, saída e diagnóstico

O painel confirma a identidade com `/api/perfil`; o conteúdo de `localStorage`
não autentica o usuário nem define o nome exibido. A conta de demonstração
`demo@skysync.aero` tem o nome “Marina Costa” no banco. Para usar outro perfil,
cadastre sua conta ou edite o perfil após entrar. O painel só confirma a alteração
quando a API a salva.

Em **Configurações → Estado da aplicação**, confira a versão `disrupcoes-4`, o
estado da sessão e o resultado de **Verificar conexão**. Se essa versão não
aparecer, a página servida ainda não contém esta correção. O diagnóstico não
exibe senhas ou cookies.

**Sair** solicita o encerramento da sessão no servidor e limpa a identidade
local. Se a API falhar, o login informa que a saída remota não foi confirmada e
não restaura automaticamente o usuário antigo.

### Testar alterações do fork sem publicar

O site e a API de produção usam a branch `lucas` do repositório
`DaGObits/SkySync`. Prepare a correção a partir dessa branch e abra o pull request
com destino a `DaGObits/SkySync:lucas`.

Para testar, siga a configuração local acima com um PostgreSQL de desenvolvimento
e execute `python app.py` em `backend`. Abra `http://127.0.0.1:5000/login.html`:
login e painel usam `/api` no servidor local. No GitHub Pages, continuam usando a
API do Render. O teste local não requer publicar o fork nem acessar o banco de
produção.

As escalas consultadas pela API são as do dia atual. Sem uma escala gravada para
essa data, o painel informa que não há escala publicada; use “Aplicar escala” no
ambiente local para persistir uma. “Simular” apenas mostra uma prévia.

Os testes de navegador cobrem carregamento, troca de abas, simulação, publicação,
resposta vazia e erro da API nas duas cópias do front-end. As respostas da API são
simuladas nesses testes, sem chamadas ao Render:

```bash
# A partir da raiz do repositório; dependências de teste fora do checkout.
npm install --prefix /tmp/skysync-browser playwright
/tmp/skysync-browser/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/skysync-browser/node_modules node --test backend/tests/frontend.test.cjs
# Se já houver Chromium instalado, defina CHROMIUM_PATH com o caminho do executável.
```

Após aceitar o pull request, publique a branch `lucas` no GitHub Pages e faça
novo deploy do serviço no Render para disponibilizar `/api/disrupcoes`.

---

## API

### Autenticação

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/auth/registrar` | Cria conta (valida e-mail e senha, hash com scrypt) |
| `POST` | `/api/auth/login` | Autentica e abre sessão em cookie HttpOnly |
| `POST` | `/api/auth/logout` | Encerra a sessão |
| `GET` | `/api/auth/sessao` | Diz quem está logado |

Senha nunca é guardada em texto. O login devolve a **mesma** mensagem para e-mail inexistente e senha errada — dizer qual falhou revelaria quais contas existem.

### Dados

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/tripulantes` | Base de tripulação, com filtros de base/cargo/status |
| `GET` | `/api/tripulantes/resumo` | Contagem por cargo, base e status |
| `GET` | `/api/voos` | Malha de voos |
| `GET` | `/api/jornadas` | Acumulado por tripulante |
| `GET` | `/api/escalas` | Alocações gravadas |
| `GET` | `/api/escalas/alocacoes` | Alocações do banco, por data |
| `GET` | `/api/malha` | Aeroportos da malha |
| `GET` | `/api/health` | Estado da app e do banco |

### Otimização

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/otimizacao` | Roda o solver sobre os dados enviados no corpo |
| `POST` | `/api/escalas/otimizar` | Roda sobre `voos` + `jornadas` do banco **e grava** o resultado |

O `POST /api/escalas/otimizar` é o que fecha o ciclo: ele lê as tabelas, resolve, grava em `escalas` com a análise, e **atualiza o acumulado em `jornadas`**. A próxima execução já enxerga as horas da anterior — o sistema tem memória.

Parâmetro `gravar: true` persiste o resultado; sem ele, apenas calcula.

---

## Estrutura do projeto

```
backend/
├── app.py                  # criação da app, CORS, CLI
├── config.py               # configuração por ambiente
├── db.py                   # conexão e transações
├── models.py               # validação de entrada
├── schema.sql              # esquema PostgreSQL
├── blueprints/
│   ├── auth.py             # autenticação
│   ├── perfil.py           # perfil do usuário
│   ├── escalas.py          # histórico de escalas
│   ├── escalas_voos.py     # voos, jornadas e alocação
│   ├── otimizacao.py       # motor CP-SAT
│   ├── cenarios.py         # geração de cenários
│   └── tripulantes.py      # base de tripulação
├── optimizer/
│   ├── solver.py           # o modelo CP-SAT
│   └── restricoes.py       # uma classe por regra da RBAC
├── dados/
│   ├── malha.py            # 36 aeroportos brasileiros
│   ├── malha_voos.py       # gerador de malha realista
│   ├── gerador.py          # gerador de cenários
│   └── nomes.py            # base de nomes sintéticos
├── static/                 # front-end
└── tests/                  # 62 testes
```

**O `optimizer/` não importa Flask.** É regra de projeto: o motor roda igual pela API, por linha de comando ou por notebook — o que permite gerar os dados do capítulo de resultados sem subir servidor.

---

## Decisões de projeto

**Um runtime, não dois.** A versão inicial tinha Flask e Express apontando para o mesmo SQLite. O projeto ficou só com o Flask, porque o motor CP-SAT precisa rodar no mesmo processo que serve a API — chamá-lo por subprocesso seria complexidade sem retorno.

**Inviabilidade devolve 409, não 500.** Cenário impossível é resultado regulatório, não falha do servidor. O diagnóstico estruturado (`causas`, `horas_disponiveis`, `alocacoes_necessarias`) foi o que permitiu encontrar, durante o desenvolvimento, um caso onde uma base com um único comandante sem reserva tornava o cenário inteiro inviável.

**`num_search_workers = 1` e `random_seed = 42`.** Uma única thread deixa a execução reprodutível: a banca pode repetir o experimento e comparar os números. Com paralelismo padrão, o CP-SAT devolve soluções diferentes a cada execução.

**O solver devolve a solução quando o tempo esgota.** Provar a otimalidade é a parte cara, não encontrar uma solução. Em 150 voos o solver não prova o ótimo em 60 s, mas costuma ter uma escala viável em mãos — e descartá-la seria jogar fora uma escala que respeita a RBAC 117.

---

## Desempenho

Medições com o gerador de cenários (seed 42), composição de 5 tripulantes por voo:

| Voos | Variáveis | Tempo | Status |
|---|---|---|---|
| 25 | 2.078 | 0,29 s | OPTIMAL |
| 50 | 7.704 | 1,62 s | OPTIMAL |
| 100 | 29.773 | 11,90 s | OPTIMAL |

O modelo cria uma variável por par (tripulante, voo), então o crescimento é quadrático — e o tempo cresce mais rápido que o número de variáveis.

**Filtro de domínio:** o solver descarta os pares que nascem inviáveis (voo mais longo que a jornada restante, cargo fora da composição, não aclimatado em voo noturno). Isso reduz o modelo sem alterar a formulação.

---

## Limitações conhecidas

**Migração de esquema.** O `init-db` usa `CREATE TABLE IF NOT EXISTS`, que cria tabela nova mas **nunca altera tabela existente**. Quando o esquema evoluiu, o banco em nuvem ficou na versão antiga e o erro só aparecia ao usar a funcionalidade nova. A ponte atual é o `sincronizar.py`; a solução definitiva é migração versionada.

**Escala do modelo.** Acima de ~100 voos, provar a otimalidade deixa de caber em 60 segundos. Para cenários maiores, o caminho é filtro de domínio por base ou mudança de formulação.

**Escalas no navegador.** A aba Escalas carrega as alocações do banco, mas o histórico de versões ainda não tem navegação por data implementada na interface.

**Testes do front.** A suíte cobre a API e o motor (62 testes); o `index.html` e o `login.html` não têm verificação automatizada.

---

## Tecnologias

- **Python 3.12** — linguagem do backend
- **Flask 3** — framework web
- **Google OR-Tools (CP-SAT)** — motor de otimização
- **PostgreSQL (Neon)** — banco de dados
- **psycopg 3** — driver PostgreSQL
- **Gunicorn** — servidor WSGI de produção
- **pytest** — testes
- **HTML/CSS/JS puro** — front-end, sem framework

---

## Contexto acadêmico

Projeto de Trabalho de Conclusão de Curso — Centro Universitário CEUNI FAMETRO, Coordenação de Ciência da Computação.

**Tema:** Aplicação da computação e da inteligência artificial à automatização logística na aviação comercial.

**Alinhamento:** ODS 9.1 da ONU — infraestrutura resiliente.

**Referências principais:**

- BRASIL. ANAC. **RBAC nº 117**: Requisitos para gerenciamento de risco de fadiga humana. Brasília: ANAC, 2020.
- BRASIL. **Lei nº 13.475/2017** — Lei do Aeronauta.
- GOOGLE. **OR-Tools: CP-SAT Solver Documentation**.
- ICAO. **Fatigue Management Guide for Airline Operations**. 2. ed. Montreal: ICAO, 2020.

---

## Licença

Projeto acadêmico. Os dados de tripulação são sintéticos e não representam pessoas reais.
