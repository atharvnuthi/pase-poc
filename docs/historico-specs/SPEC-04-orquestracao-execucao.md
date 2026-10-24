# SPEC-04 - Orquestração + Execução

**Fase:** F3 · **Depende de:** SPEC-01, SPEC-02 (alvo congelado), SPEC-03 · **Demos:** D1, D6

## 1. Tabelas

- `tasks(id, proposal_id, title, description, module, output_type codigo_permanente|zona_dinamica, impact, complexity, confidence, uncertainty bool, risk_tier baixo|medio|alto, status, final_outcome aprovada|recusada null, branch_name null, waiting_on_task_id null, alert none|retries|budget|merge_conflict, urgency_score float default 0, demo_force_fail_runs int null, demo_budget_cap_tokens int null, created_at, updated_at)`
- `task_state_history(id, task_id, from_status, to_status, note, at)`
- `planning_documents(id, task_id, affected_files json, roadmap text, tokens_estimated int, created_at)`
- `execution_runs(id, task_id, attempt, trigger inicial|retry|ajuste, status sucesso|falha|interrompida_budget, failure_reason?, deviation_files json default '[]', tokens_real, duration_ms, diff_path, log_path, transcript_path, created_at)`
- `incidents(id, title, description, severity baixo|medio|alto, source manual|sentry_stub, resolved bool default false, task_id null, created_at)` - permite ao Fator de Urgência ter algo real para ler (ver Seção 2). `source=sentry_stub` sinaliza que na PoC isso é inserido manualmente pelo painel; em produção viria de uma integração real.

**Estados** (transições estritas; toda transição gera histórico):
`candidata → em_planejamento → pronta_para_despacho → em_execucao → em_homologacao → finalizada`, com `em_execucao → suspensa` (falhas/budget), `suspensa → em_execucao` (resume) e `em_homologacao → em_execucao` (ajuste).

## 2. Priorização

`GET /api/tasks?status=candidata` ordena por um score simples: `impact − complexity + urgency_score`. `urgency_score` é recalculado quando um incidente é criado: incidentes `alto` vinculados a um módulo somam `+3` a `urgency_score` de toda `task` candidata do mesmo módulo; `medio` soma `+1`. Isso é deliberadamente simples nesta fase (ver SPEC-10 para uma versão com SLA e decaimento temporal).

## 3. Endpoints

| Endpoint | Semântica |
|---|---|
| `GET /api/tasks?status=` | lista `{id, title, status, impact, complexity, confidence, uncertainty, risk_tier, urgency_score, alert, updated_at}` |
| `GET /api/tasks/{id}` | agregado: task + histórico + planejamento + runs |
| `POST /api/tasks/{id}/approve` | candidata → dispara cadeia em background (Seção 4) |
| `POST /api/tasks/{id}/reject {reason}` | candidata → `discarded_proposals(recusa_humana, com embedding)`; task `finalizada/recusada` |
| `POST /api/tasks/{id}/resume` | suspensa → nova run (zera contagem de retry) |
| `POST /api/tasks/{id}/homologation {decision, comment}` | ver Seção 5 |
| `POST /api/incidents {title, description, severity}` | cria incidente, recalcula urgência das tasks do módulo afetado |
| `PATCH /api/tasks/{id}/demo {force_fail_runs?, budget_cap_tokens?}` | **só com `DEMO_MODE=true`** |
| `GET /api/runs/{run_id}/artifact/{diff\|logs\|transcript}` | serve arquivos de `/data/artifacts/task-{id}/run-{n}/` |

## 4. Cadeia pós-aprovação (FastAPI BackgroundTasks; painel acompanha por SSE, ver SPEC-06)

1. `em_planejamento` → **P4 Planejamento**: contexto = árvore do `client-backend/` + conteúdo integral de fontes e testes (app pequeno, sem heurística de seleção) + `project_context.md` + `task.output_type` → `{affected_files[], roadmap, tokens_estimated}` → persiste `planning_documents`. Se `output_type=zona_dinamica`, o roadmap descreve a criação do contrato de zona e do componente nativo com fallback, não uma funcionalidade permanente de fluxo completo.
2. `pronta_para_despacho` → checagem de conflito: interseção de `affected_files` com tarefas em `em_execucao|em_homologacao` → se houver, seta `waiting_on_task_id`; senão, despacha.
3. `em_execucao` → Executor (Seção 6).
4. Sucesso → `em_homologacao`. Falha → política da Seção 7.

## 5. Homologação (decisão humana, painel)

- **aprovar:** `git merge --no-ff` da branch na main de `REPO_PATH` → registra `implemented_items` → `finalizada/aprovada`. Se `output_type=zona_dinamica`, também registra a zona no registro do SPEC-05. Conflito de merge → `alert=merge_conflict`, permanece `em_homologacao`.
- **ajustar:** `{comment}` → nova run `trigger=ajuste` na mesma branch → `em_execucao`.
- **recusar:** `{comment}` → `discarded_proposals(recusa_humana, com embedding)` → `finalizada/recusada` (branch fica para auditoria).

Tarefas com `risk_tier=alto` exigem que o campo `comment` seja preenchido mesmo em aprovação (justificativa obrigatória) - checagem simples no endpoint, não é RBAC real, é o suficiente para a PoC demonstrar que risco alto pede mais atenção humana.

## 6. Executor (uma run)

1. Workspace: `git clone REPO_PATH /tmp/pase/task-{id}` (ajuste: fetch + checkout da branch existente); branch `pase/task-{id}`.
2. **Guardrail de budget - antes de cada chamada LLM:** teto = `demo_budget_cap_tokens` ou `tokens_estimated × (1 + BUDGET_TOLERANCE)`; se ultrapassado → run `interrompida_budget`, task `suspensa`, `alert=budget`.
3. **P5 Geração**: roadmap + conteúdo atual dos arquivos → `{files: [{path, content}]}` (arquivo inteiro, nunca diff textual).
4. **Sem allowlist rígida de caminho** (decisão de modelo, ver SPEC-00 Seção 7): o Executor pode tocar arquivos correlacionados fora do `affected_files` original se necessário. Qualquer `path` fora de `affected_files` do planejamento é registrado em `deviation_files` na run - não bloqueia a execução, mas aparece destacado na Homologação para revisão humana.
5. Escreve arquivos → `ruff check` → `pytest -q`.
6. Falhou lint/teste → anexa saída ao transcript e repete P5 (correção) até `MAX_LOCAL_FIX`.
7. Sucesso → commit `pase: {title} (task #{id})` → push → `diff = git diff main...HEAD` → salva artefatos (`diff.patch`, `lint_test.log`, `transcript.jsonl`) → grava run `sucesso` com tokens/duração/`deviation_files`.
8. `demo_force_fail_runs > 0` → a run levanta falha controlada após a geração (decrementa o contador).

**Transcript:** todas as mensagens trocadas com o LLM na run, em JSONL - rastreabilidade integral exigida pelo modelo.

## 7. Política de falhas

Run `falha` → se `attempt ≤ MAX_RETRIES` → nova run `trigger=retry`; senão → `suspensa`, `alert=retries`. Ações na suspensa (painel): `resume` ou `homologation/recusar`.

## 8. Ciclo de Auditoria

Job periódico (`make demo-d8` cobre tanto isto quanto a Reavaliação Cíclica do SPEC-03, rodados em sequência) que:
1. Roda **P10 - Varredura de Auditoria**: contexto = árvore completa do `client-backend/` → identifica um ponto de refatoração ou inconsistência (ex: falta de validação repetida, código duplicado entre rotas).
2. Se encontrar algo, cria uma `proposals` com `origin=auditoria`, `type=engenharia` (segue o bypass do SPEC-03 Seção 4, mas com `author="PASE Audit"` fixo, sempre autorizado).

Distinto da Reavaliação Cíclica: este job lê o **código-fonte**, aquele lê o **histórico de descartes**. São dois inputs diferentes e não podem ser fundidos em um único job sem perder a distinção que o modelo estabelece.

## 9. Prompts

| P | Entrada | Saída | Diretrizes |
|---|---|---|---|
| **P4** planejamento | task + fontes/testes integrais + contexto + `output_type` | `{affected_files, roadmap, tokens_estimated}` | roadmap acionável por arquivo; estimar tokens como inteiro; não propor mudanças fora do client-backend |
| **P5** geração/correção | roadmap + arquivos atuais (+ saída de lint/teste nas correções, + comentário do gestor no ajuste) | `{files:[{path, content}]}` | devolver arquivos completos; preservar testes existentes passando; mudanças mínimas necessárias |
| **P10** auditoria | árvore completa do client-backend | `{finding: string}` ou `null` se nada relevante | achado específico e acionável, não genérico ("melhorar qualidade") |

## 10. Critérios de aceite

- **D1:** sugestão "Exportar minhas transações em CSV" → aprovar → acompanhar estados → diff/logs/transcript no painel → aprovar homologação → `GET /transactions/export.csv?user_id=` responde 200 no app rodando; `implemented_items` +1.
- **D6:** (a) `PATCH demo {force_fail_runs: 2}` + approve → falha → retry → falha → `suspensa/retries`; (b) `PATCH demo {budget_cap_tokens: 100}` + approve → `interrompida_budget` → `suspensa/budget`.
- Duas tarefas com arquivos em conflito: a segunda fica `pronta_para_despacho` com `waiting_on` até a primeira finalizar.
- `POST /api/incidents {severity: alto}` vinculado ao módulo `transacoes` → uma task candidata do mesmo módulo sobe de posição na lista ordenada.
- Uma run onde o Executor edita um arquivo fora de `affected_files` → `deviation_files` não vazio → aparece destacado na tela de Homologação.
