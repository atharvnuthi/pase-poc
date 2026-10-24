# Banco de Dados

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

Dois bancos, um por sistema. As colunas abaixo foram lidas dos modelos em
`pase-core/app/**/models.py` e `client-backend/app/models.py`.

| Banco | Motor | De quem | Conteúdo |
|---|---|---|---|
| `pase` | Postgres 16 + **pgvector** | PASE | propostas, tarefas, execuções, zonas, telemetria |
| `fintrack.db` | SQLite | FinTrack | usuários, categorias, transações, tickets |

O esquema nasce no boot (`create_all`); não há migrações versionadas nesta fase. Para
voltar ao zero, `make reset`.

A suíte de testes usa um banco separado, `pase_test`, criado sob demanda - antes disso os
testes apagavam tarefas reais do banco da aplicação a cada execução.

---

## 1. Banco do PASE

### Por que estas tabelas existem

Rastreabilidade integral é um princípio do modelo: **toda decisão relevante vira linha**,
nunca só log. A cadeia de artefatos acompanha a demanda do começo ao fim:

```
proposals → tasks → planning_documents → execution_runs → implemented_items
                ↘ task_state_history (toda transição)
                ↘ discarded_proposals (todo desfecho negativo)
```

### `proposals` - a ideia como ela chegou

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int, PK | |
| `origin` | str(16) | `external`, `internal`, `passiva`, `ai`, `auditoria`, `reavaliacao` |
| `type` | str(16), nulo | `funcional` ou `engenharia` |
| `raw_text` | text | o texto como a pessoa escreveu |
| `user_id`, `author` | int / str, nulos | quem pediu |
| `title`, `description`, `module` | | preenchidos pela Normalização (P1) |
| `output_type` | str(32) | `codigo_permanente` ou `zona_dinamica` |
| `embedding` | **vector** | entra na Memória Histórica |
| `outcome` | str(32) | desfecho do funil, sempre explícito |
| `source_discard_id` | int, nulo | preenchido quando a Reavaliação Cíclica reabre um descarte |
| `created_at` | timestamptz | |

### `discarded_proposals` - o que foi barrado, e por quê

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int, PK | |
| `proposal_id`, `task_id` | int, nulos | de onde veio |
| `reason_type` | str(24) | `duplicata`, `incoerente`, `recusa_humana` |
| `reason_text` | text | o motivo por escrito |
| `matched_ref` | str(128), nulo | contra o que bateu, no caso de duplicata |
| `duplicate_count` | int | **quantas vezes a mesma dor foi pedida** |
| `duplicate_refs` | json | as referências acumuladas |
| `embedding` | vector, nulo | descarte por incoerência entra na memória; duplicata não |
| `created_at` | timestamptz | |

`duplicate_count` não é estatística decorativa: é o sinal de recorrência que a Avaliação de
Zona Dinâmica usa para decidir se um padrão é de cauda longa. Por isso duplicata
**incrementa a linha existente** em vez de criar uma nova - contar é o ponto.

### `implemented_items` - a memória do que já existe

Mesma estrutura de memória do descarte (`title`, `description`, `embedding`,
`duplicate_count`, `duplicate_refs`, `task_id`). É contra esta tabela que um pedido
repetido bate e vira duplicata.

### `tasks` - a unidade de trabalho

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int, PK | |
| `proposal_id` | FK → `proposals` | |
| `title`, `description`, `module` | | |
| `output_type` | str(32) | decide se a Execução escreve código ou abre uma zona |
| `impact`, `complexity` | int 1–5 | da Qualificação (P2b) |
| `confidence` | float 0–1 | |
| `uncertainty` | bool | `confidence < 0.5`; vira selo no painel |
| `risk_tier` | str(16) | `baixo`, `medio`, `alto`. Alto exige justificativa escrita até para aprovar |
| `status` | str(32) | ver máquina de estados abaixo |
| `final_outcome` | str(16), nulo | `aprovada` ou `recusada` |
| `branch_name` | str(128), nulo | `pase/task-{id}` |
| `waiting_on_task_id` | int, nulo | conflito de arquivos com outra tarefa |
| `alert` | str(24) | `none`, `retries`, `budget`, `merge_conflict` |
| `urgency_score` | float | somado por incidentes do mesmo módulo |
| `demo_force_fail_runs`, `demo_budget_cap_tokens` | int, nulos | só com `DEMO_MODE=true` |
| `created_at`, `updated_at` | timestamptz | |

**Máquina de estados.** Toda transição gera linha em `task_state_history`:

```
candidata → em_planejamento → pronta_para_despacho → em_execucao → em_homologacao → finalizada
                                                          ↕ suspensa (falha ou budget)
                                    em_homologacao → em_execucao (ajuste)
```

Uma transição longa é **commitada antes** do trabalho, nunca junto: marcar `em_execucao`
dentro da mesma transação da run deixava o status invisível a outras conexões por minutos,
e a checagem de conflito de arquivos nunca via a tarefa em andamento.

### `task_state_history`

`task_id`, `from_status`, `to_status`, `note`, `at`. É o que torna auditável quem decidiu o
quê e quando.

### `planning_documents`

`task_id`, `affected_files` (json), `roadmap` (text), `tokens_estimated`, `created_at`.

`tokens_estimated` é **artefato de planejamento, nunca teto sozinho**: medido, erra por
ordem de grandeza - estimou 1.200 para uma execução que consumiu 25.000. Daí o piso
`BUDGET_MIN_TOKENS`.

### `execution_runs`

| Coluna | Nota |
|---|---|
| `task_id`, `attempt`, `trigger` | `inicial`, `retry`, `ajuste` |
| `status` | `sucesso`, `falha`, `interrompida_budget` |
| `failure_reason` | |
| `deviation_files` (json) | arquivos tocados fora do plano - não bloqueiam, mas aparecem destacados na Homologação |
| `tokens_real`, `duration_ms` | |
| `diff_path`, `log_path`, `transcript_path` | artefatos em disco |

### `incidents`

`title`, `description`, `severity`, `module`, `source`, `resolved`, `task_id`. Alimentam o
fator de urgência: severidade alta soma +3 ao `urgency_score` das candidatas do mesmo
módulo; média soma +1.

### `llm_calls` - a trilha de custo e rastreabilidade

`trace_id`, `kind` (`chat`/`embed`), `provider`, `model`, `temperature`, `tokens_in`,
`tokens_out`, `duration_ms`, `attempts`, `tags` (json), `error`, `created_at`.

O `trace_id` é o que permite religar qualquer decisão do sistema à conversa exata que a
produziu.

> **Cuidado registrado:** esta tabela **não** entra no wipe do seed. `TRUNCATE` nela dentro
> de uma transação que depois chama o LLM trava o processo - o lock exclusivo bloqueia a
> conexão separada que grava o registro da chamada, e tudo congela.

### Tabelas do UPA

- **`telemetry_events`** - `user_id`, `event`, `path`, `at`. Só navegação; é o insumo do
  loop rápido e nunca passa pelo Task Layer.
- **`zone_payloads`** - `user_id`, `slot`, `payload` (json), `origin`
  (`autonoma`/`injetado`), `status` (`ativo`/`revogado`).
- **`zone_violations`** - `user_id`, `slot`, `reason`, `raw_payload` (json), `at`. É a
  evidência de que a defesa funcionou: payload recusado fica registrado com o motivo.

---

## 2. Banco do FinTrack

| Tabela | Colunas |
|---|---|
| `users` | `id`, `name` |
| `categories` | `id`, `name` |
| `transactions` | `id`, `user_id` FK, `category_id` FK, `type` (`income`/`expense`), `amount` (decimal), `date`, `description` |
| `support_tickets` | `id`, `user_id` FK, `text`, `created_at` |

**Validações**, que devolvem 422 com mensagem por campo: valor positivo, data não futura,
categoria existente. Elas são parte da rede de regressão do Executor - quebrar uma delas
reprova a run.

`support_tickets` existe por causa do modelo, não do produto: sem ela, a Captação Passiva
ficaria sem uma das quatro origens de demanda.

---

## 3. Busca vetorial

Todo SQL vetorial vive em `pase-core/app/common/vector_store.py`. Embeddings são
`text-embedding-3-small`, 1536 dimensões, comparados por cosseno.

**O limiar é 0.72, não 0.85.** O valor original ficava acima de *todos* os positivos
medidos - com ele a Memória Histórica nunca barraria nada. Calibrado por medição:
positivos entre 0.69 e 0.90, negativos até 0.65.

**O que o embedding não resolve:** agrupar tickets de suporte por tema. Em texto curto e
coloquial, tickets sobre a mesma dor ficaram entre 0.47 e 0.61 - *abaixo* de pares de
temas diferentes. Esse agrupamento é feito por um prompt (P0a), não por cosseno.
