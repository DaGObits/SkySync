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

### Operação simulada e remanejamentos automáticos

Em **Escalas**, clique em **Iniciar operação simulada**. Esse é o único controle:
depois ele alterna entre **Pausar operação** e **Continuar operação**, preservando
o progresso. Não é necessário escolher seed, perfil, data ou publicar cenários.

Todos os tripulantes disponíveis/em reserva do cadastro entram no acompanhamento.
A posição inicial é a base cadastrada, pois o sistema não recebe localização real
de pessoas. Depois disso, a posição só muda após o pouso simulado. As horas iniciais
e os limites vêm da jornada cadastrada para a data de Manaus; sem jornada, começa
com zero horas e o limite padrão configurado. Pessoas ociosas não acumulam horas
artificialmente: só quem está voando acumula minutos de voo.

A malha usa origem, destino, horário e duração dos voos programados cadastrados.
O plano inicial considera deslocamentos futuros, jornada e intervalos; 20% dos
voos podem receber um atraso fictício de 30 a 90 minutos para exercitar mudanças
na operação. Esses atrasos pertencem à simulação e não são publicados como eventos
reais da Aviationstack.

Durante a execução, o sistema:

- atualiza horas e posição dos tripulantes, em memória e na tabela isolada de estado;
- preserva as designações ainda viáveis;
- usa CP-SAT para completar a composição quando alguém ficou impedido;
- só seleciona substitutos livres no aeroporto de partida, com cargo, descanso,
  aclimatação e jornada compatíveis; não transfere ninguém instantaneamente;
- deixa o voo aguardando quando não há equipe completa e tenta novamente após
  a evolução da operação;
- sincroniza novos cadastros e bloqueia futuras designações de pessoas marcadas
  indisponíveis, sem mudar a posição de quem já está na simulação.

A tabela mostra apenas mudanças: **voo, quem saiu, quem entrou, local e motivo**.
Na aba **Tripulantes**, consulte local atual, jornada simulada e situação de cada
pessoa. A tela atualiza a cada cinco segundos. O histórico visível retém as 200
últimas trocas, com um contador total acumulado.

O relógio avança 60 vezes mais rápido: um segundo equivale a um minuto. A malha se
repete nos dias seguintes, mantendo as posições e jornadas; repouso cumprido
reinicia a jornada. O protótipo usa 30 minutos de intervalo em solo e 12 horas de
repouso, com repouso preventivo após atingir 85% do limite. Esses critérios são
simplificações da demonstração, não uma implementação completa da regulamentação.

O estado é global e compartilhado pelos usuários na tabela `operacao_simulada`.
Jornadas, escalas, voos e ocorrências reais permanecem separados. Pausar e retomar
não apaga o progresso. As atualizações são serializadas no PostgreSQL para evitar
avanço duplicado entre workers. Enquanto o Render estiver suspenso, a operação
fica congelada; o reinício não tenta executar horas retroativas de uma só vez.

A migração aditiva `migrations/operacao.sql` e o agendador são carregados pelo mesmo
`gunicorn.conf.py` usado no Render. É necessário publicar backend e Pages após o
merge, sem nova chave. Endpoints autenticados: `GET /api/operacao`,
`POST /api/operacao/iniciar` e `POST /api/operacao/pausar`.
Os endpoints antigos de cenários continuam disponíveis para compatibilidade,
mas os seus formulários e botões foram removidos da interface.

### Mapa da operação simulada

O painel inicial mostra os voos da **mesma operação persistida** que acumula as
horas dos tripulantes e dispara os remanejamentos. O mapa recebe o snapshot no
`GET /api/operacao` já consultado a cada cinco segundos. Iniciar, continuar e
pausar em **Escalas** também atualiza o mapa. O botão **Controlar operação** abre
essa aba; não há outro relógio ou simulação paralela.

A posição de cada avião é aproximada por interpolação entre as coordenadas reais
dos aeroportos cadastrados, conforme os minutos transcorridos desde a decolagem
simulada e a duração efetiva do voo (incluindo seu atraso simulado). O avião só
aparece após a decolagem, sai do mapa ao pousar e fica parado quando a operação
está pausada. O clique ou Enter no avião mostra rota, progresso, tempo restante,
atraso e os tripulantes efetivamente alocados com suas horas e limites atuais.
A seleção **Voo em andamento** também permite escolher aviões sobrepostos no mapa.
As transições visuais duram um segundo entre snapshots; não adiantam o relógio.

Aeroportos com voos aguardando tripulação ficam amarelos. Voos sem coordenadas
válidas são contabilizados em um aviso, sem receber posições inventadas. Os
controles de zoom, arrasto e **Brasil** alteram apenas a visualização. Falhas na
consulta preservam as últimas posições com aviso; os GETs não avançam a operação.

O mapa é SVG local, sem iframe, API de rastreamento ou tiles externos. Não precisa
de conta, chave ou mudança de plano. Não representa tráfego real; a Aviationstack
continua independente e usada para as disrupções reais. Os endpoints antigos
`/api/ao-vivo` continuam disponíveis para compatibilidade, sem uso pelo painel.

Após o merge, publicar **Render e Pages**, sem migração de banco. A versão exibida
em Configurações é `simulacao-mapa-1`. Estados de simulação já existentes são
compatíveis, inclusive voos de dias seguintes e decolagens fora do horário previsto.

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

Em **Configurações → Estado da aplicação**, confira a versão `operacao-7`, o
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

Os testes de navegador cobrem início/pausa e persistência da operação, remanejamentos,
localização/jornada, identidade e saída, disrupções e erros da API nas duas cópias do front-end. As respostas da API são
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


## Importação automática: Aviationstack

O backend consulta `https://api.aviationstack.com/v1/flights` para saídas de um
aeroporto. Registra cancelamentos (`flight_status=cancelled`) e atrasos de partida
(`departure.delay`) a partir de 15 minutos. Cancelamentos e atrasos de 60 minutos
ou mais recebem risco alto; atrasos menores recebem risco médio. A descrição
informa fornecedor e data do voo, sem inventar causas de meteorologia/manutenção
nem diagnosticar fadiga.

Ative no Render, em **Environment**, com as seguintes variáveis:

| Variável | Padrão | Efeito |
|---|---|---|
| `AVIATIONSTACK_API_KEY` | ausente | Chave da conta; somente no backend. |
| `AVIATIONSTACK_AIRPORT` | `GRU` | Um aeroporto de partida por instalação. |
| `AVIATIONSTACK_INTERVAL_SECONDS` | `43200` | Intervalo de 12 horas; mínimo 300 segundos. |
| `AVIATIONSTACK_DAILY_REQUEST_LIMIT` | `2` | Cota diária UTC, incluindo falhas. |
| `AVIATIONSTACK_MIN_DELAY_MINUTES` | `15` | Atraso mínimo para gerar uma ocorrência. |

Nunca coloque a chave no GitHub, no front-end ou no chat. Confira no plano
Aviationstack a cobertura do aeroporto, o acesso HTTPS e a cota disponível.
**A integração ainda precisa ser validada com uma chave e respostas reais da
sua conta.** Não é feita nenhuma consulta externa enquanto a chave estiver ausente.

Cada consulta lê a primeira página, de até 100 voos. Se houver mais páginas, a
interface informa **cobertura parcial**; isso não representa todos os voos do
aeroporto. O padrão permite no máximo 62 chamadas por mês de 31 dias. Consultar a
cada hora exigiria intervalo 3600, limite diário 24 e até 744 chamadas por mês;
confira o plano e o uso da chave por outros sistemas antes de alterar esses valores.
Falhas aguardam o próximo horário, sem repetição imediata de tentativas.

Use este **Start Command** no Render (Root Directory: `backend`):

```bash
gunicorn --config gunicorn.conf.py app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
```

O agendador inicia com o worker e aplica a migração aditiva
`migrations/aviationstack.sql`. Ela cria tabelas de controle sem alterar registros
manuais. Horário e cota persistem no PostgreSQL entre reinícios; uma reserva no
banco impede chamadas duplicadas entre workers. O mesmo voo (fornecedor, código,
data e aeroporto de partida) atualiza o cartão existente quando o atraso muda ou
evolui para cancelamento. As ocorrências são histórico informado pelo fornecedor;
a ausência de um voo numa página seguinte não apaga esse histórico.

**No Render gratuito, o agendador para enquanto o serviço estiver suspenso.**
Após despertar, consulta se houver horário e cota disponíveis. Execução contínua
requer um serviço sempre ativo ou um agendador externo autorizado. Para cron ou
uma consulta avulsa no servidor, usando a mesma configuração e o mesmo banco:

```bash
cd backend
python importar_disrupcoes.py
```

O comando respeita o horário e a cota; não força consulta adicional. Em desenvolvimento
com `python app.py`, esse agendador não inicia: use o comando avulso ou Gunicorn.

A aba Disrupções mostra fonte, última consulta bem-sucedida, configuração pendente,
falha/cota e cobertura parcial. A atualização da tela a cada minuto consulta apenas
nosso backend, sem gastar chamadas adicionais no fornecedor.
`GET /api/disrupcoes/importacao/status` exige sessão e nunca retorna a chave.
