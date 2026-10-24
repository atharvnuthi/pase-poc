# SPEC-01 - Infraestrutura e Convenções

**Fase:** F0 · **Depende de:** SPEC-00 · **Bloqueia:** todos os demais SPECs

## 1. Objetivo

Monorepo funcional onde `make up` sobe os 4 serviços de aplicação + banco, todos saudáveis, com banco vetorial pronto e o cliente de LLM testado.

## 2. Estrutura do monorepo

```
pase-poc/
├── docker-compose.yml
├── .env.example
├── Makefile
├── CLAUDE.md
├── README.md
├── docs/
│   ├── project_context.md          # contexto vivo do produto (ver SPEC-08)
│   ├── contracts/
│   │   └── resumo_financeiro.schema.json
│   └── specs/                      # SPEC-00 ... SPEC-10
├── scripts/demo/                   # d1.sh ... d8.sh
├── client-frontend/                # Next.js - o FinTrack
├── client-backend/                 # FastAPI - API do FinTrack
├── pase-core/                      # FastAPI - motor do PASE
└── pase-panel/                     # Next.js - painel de controle humano
```

## 3. docker-compose

| Serviço | Base | Porta | Volumes | Observações |
|---|---|---|---|---|
| db | `pgvector/pgvector:pg16` | 5432 | `pgdata` + `db/init/01-init.sql` | init roda `CREATE EXTENSION IF NOT EXISTS vector;` · healthcheck `pg_isready` |
| pase-core | build `./pase-core` | 8000 | `.:/workspace/repo` (monorepo inteiro, para o Executor clonar) · `./pase-core:/app` (reload) · `core-artifacts:/data` | `uvicorn --reload` · `depends_on: db (healthy)` |
| client-backend | build `./client-backend` | 8001 | `./client-backend:/app` (reload; SQLite em `/app/data/`) | `uvicorn --reload` |
| client-frontend | build `./client-frontend` | 3001 | `./client-frontend:/app` | `next dev` |
| pase-panel | build `./pase-panel` | 3000 | `./pase-panel:/app` | `next dev` |

Todos em modo dev com volume montado: um merge aprovado pelo PASE na branch principal aparece no app rodando via hot reload. Isso representa o "deploy" da PoC - não há pipeline de build separado neste estágio (ver SPEC-10).

**Dockerfile do pase-core:** `python:3.12-slim` + `git`. Instala `pase-core/requirements.txt` **e** `client-backend/requirements.txt` (o Executor roda `ruff`/`pytest` do alvo dentro do próprio ambiente do pase-core). `git config --global user.name "PASE Bot"` e `user.email` fixo.

## 4. `.env.example`

```
LLM_PROVIDER=anthropic
LLM_API_KEY=
LLM_MODEL=claude-sonnet-4-6
LLM_MODEL_EXPLORATORY=claude-sonnet-4-6
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
DATABASE_URL=postgresql+psycopg://pase:pase@db:5432/pase
REPO_PATH=/workspace/repo
SIMILARITY_THRESHOLD=0.85
BUDGET_TOLERANCE=0.3
MAX_RETRIES=1
MAX_LOCAL_FIX=2
COHERENCE_MAX_ADJUSTMENTS=2
DEMO_MODE=true
NEXT_PUBLIC_CORE_URL=http://localhost:8000
NEXT_PUBLIC_CLIENT_API_URL=http://localhost:8001
```

Nota de decisão: `LLM_MODEL` cobre normalização, coerência, qualificação, planejamento e execução - todos com temperatura baixa (0.1–0.3). `LLM_MODEL_EXPLORATORY` é usado apenas pelo P3 (Geração Exploratória), com temperatura 0.9. Dois nomes de variável, não dois providers necessariamente - permite trocar o modelo exploratório sem afetar o resto caso o custo ou a qualidade peçam ajuste.

## 5. Makefile

`up` · `down` · `logs` · `seed` (popula FinTrack e baseline do PASE) · `reset` (`down -v` + `up` + aguardar health + `seed`) · `test-core` (pytest do pase-core) · `test-client` (pytest do client-backend) · `demo-d1` … `demo-d8` (delegam a `scripts/demo/dN.sh`).

## 6. Módulos comuns do pase-core (entregues nesta fase)

- **`common/config.py`** - settings via env (`pydantic-settings`).
- **`common/db.py`** - engine, `SessionLocal`, `Base`; `create_all` no boot (sem Alembic nesta fase - ver SPEC-10).
- **`common/llm_client.py`** - contrato único de chamada a LLM (Seção 7 do SPEC-08). Loga `model`, `tokens_in/out`, `tags`, `trace_id` em toda chamada. Retentativa única automática para JSON inválido.
- **`common/vector_store.py`** - `save_embedding(kind, ref_id, text)` e `search(text, kinds, top_k=5) -> [(kind, ref_id, similarity, title)]` usando operador de cosseno do pgvector. Todo SQL vetorial vive aqui.
- **`common/git_service.py`** - clone/branch/commit/push/merge/diff sobre `REPO_PATH`.
- **`common/events.py`** - publicação e assinatura de eventos internos (Postgres LISTEN/NOTIFY, ver SPEC-06 Seção 2). Usado pelo painel para atualização ao vivo.

## 7. Convenções

Ver `CLAUDE.md` na raiz - é a fonte única de convenções (evita duplicação entre este SPEC e o arquivo que os agentes de fato leem a cada sessão).

## 8. Critérios de aceite

1. `make up` sobe os 4 serviços de app + db com health verde; `psql \dx` mostra `vector`.
2. `python -m app.smoke` no pase-core: uma chamada `chat` e uma `embed` funcionam e logam tokens.
3. `vector_store.save_embedding` + `search` gravam e recuperam com similaridade correta.
4. `make reset` é idempotente.
5. `common/events.py`: publicar um evento e recebê-lo de uma segunda conexão no mesmo processo de teste.
