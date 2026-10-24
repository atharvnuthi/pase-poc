# SPEC-06 - Painel, Seeds, Demos e Métricas

**Fase:** F2–F4 · **Depende de:** SPEC-03/04/05

## 1. Shell do painel (pase-panel)

Layout com navegação **Tarefas | Zonas | Incidentes**. Atualização de listas e do detalhe via **SSE** (`GET /api/events/stream`, publicado por `common/events.py` no pase-core via Postgres LISTEN/NOTIFY) em vez de polling - mais simples de justificar na tese ("o painel reage a eventos reais do sistema, não pergunta em loop") e mais barato de rodar. TanStack Query mantido para cache local e para as poucas chamadas que são de fato request/response (aprovar, homologar). Toda decisão crítica acontece aqui - nunca automaticamente.

## 2. Tela **Tarefas**

- **Candidatas:** ordenadas por `impact − complexity + urgency_score`; colunas título, origem, impacto, complexidade, confiança, `risk_tier`; badge **incerteza**; ações **Aprovar** / **Recusar (motivo)**.
- **Em andamento:** agrupadas por estado; badges de alerta `retries` / `budget` / `merge_conflict`; suspensas com ações **Retomar** / **Recusar**.
- **Finalizadas** (adicionada após a primeira execução real no frontend, SPEC-11): tarefas com `status = "finalizada"`, mais recente primeiro, com o `final_outcome` (`aprovada`/`recusada`) como badge. Sem esta aba uma tarefa mergeada não é `candidata`, nem `em_andamento`, nem `descartada` - some do painel apesar de continuar em `implemented_items`, no `git log` e no `tasks.csv`. Sem ações: é histórico, não fila.
- **Descartadas:** aba com motivo (`duplicata` mostra o item correspondente e `duplicate_count`; `incoerente`/`recusa_humana` mostram o texto do motivo).
- Botões de ingestão: **Nova sugestão interna** (form autor, tipo funcional/engenharia, texto) e **Gerar proposta com IA** (select: exploratória / análise de lacunas).

## 3. Tela **Tarefa [id]**

Header: título, estado, metadados, `risk_tier`, alertas. Abas:
- **Planejamento:** `affected_files`, roadmap, `tokens_estimated`.
- **Execuções:** lista de runs (tentativa, trigger, status, tokens, duração, `deviation_files`) + para a run selecionada: diff viewer (bloco monoespaçado com linhas `+`/`−`), logs de lint/teste, transcript (JSONL renderizado como conversa).
- **Homologação** (visível em `em_homologacao`): botões **Aprovar** / **Ajustar (comentário)** / **Recusar (motivo)**. Se `risk_tier=alto`, comentário obrigatório mesmo em aprovação.

## 4. Tela **Incidentes**

Lista simples + formulário **Novo incidente** (título, descrição, severidade, módulo afetado). Existe para dar ao Fator de Urgência algo real para ler e para D-extra (opcional, ver Seção 6).

## 5. Métricas

- `GET /api/metrics/tasks.csv` → `task_id,title,origin,output_type,status,final_outcome,impact,complexity,confidence,uncertainty,risk_tier,urgency_score,tokens_estimated,tokens_real_total,runs,retries,deviation_count,duration_ms_total,created_at,finished_at`
- `GET /api/metrics/discards.csv` → `id,reason_type,reason_text,matched_ref,duplicate_count,origin,created_at`
- `GET /api/metrics/violations.csv` → `id,user_id,slot,reason,created_at`

Anexos do capítulo de validação do TCC. As três métricas citadas na conclusão da monografia - taxa de intervenção humana, densidade de retrabalho, incidência de regressões - são todas calculáveis a partir de `tasks.csv`: intervenção = proporção de `ajustar`/`recusar` sobre total homologado; retrabalho = média de `runs` por task finalizada; regressão = tasks com testes que falharam em uma run após terem passado em uma run anterior da mesma task.

## 6. Seeds (`make seed`)

1. **FinTrack:** Ana e Clara; 5 categorias; ~50 transações; 4–5 tickets de suporte, com pelo menos 3 tickets tocando o mesmo tema ("dificuldade de achar gasto por categoria") para o D7 ter o padrão que P1b precisa detectar.
2. **Baseline `implemented_items`** (com embeddings): cadastro de transações; edição/exclusão; resumo de saldo; gastos por categoria; relatórios mensais; seletor de persona; categorias fixas; validações do formulário.
3. **Descartes históricos** (com embeddings): "minerar criptomoedas no app", "editor de vídeo integrado", "rede social entre usuários" - motivos de incoerência escritos; um quarto descarte com motivo que ficará inválido após um ajuste manual no `project_context.md` durante o D8 (ex: "exportar dados para Excel" descartado citando "fora de escopo por ora", motivo que o D8 vai reverter).
4. **Fixtures de texto** para D2 em `scripts/demo/fixtures/`.

## 7. Roteiros de demonstração

| Demo | Pré | Passos | Esperado |
|---|---|---|---|
| d1 | seed; trabalho commitado | modal (ou curl) "Exportar minhas transações em CSV" → painel: aprovar → acompanhar estados → homologação: revisar diff/transcript → aprovar | merge na main; `GET /transactions/export.csv?user_id=` 200 no app rodando; `implemented_items` +1 |
| d2 | seed | 3 curls das fixtures (duplicata de implementada; incoerente; variação da incoerente) | `descartada_duplicata` com match e `duplicate_count`; `descartada_incoerente` com motivo; segunda barrada pela memória de descartes |
| d3 | seed | curl `ai-generate {mode: exploratoria}` e `ai-generate {mode: lacunas}` | candidata nova coerente em cada modo (ou descarte legítimo pelo próprio funil) |
| d4 | seed | `simulate(ana)` → abrir dashboard como Ana e como Clara | widget para Ana; nativo para Clara; `revoke` restaura |
| d5 | d4 revogado | 3 `inject-raw` inválidos → abrir dashboard da Ana → tela Zonas | fallback nativo; 3 violações com motivos distintos |
| d6 | seed | proposta interna "Demo de falha controlada" → `PATCH demo {force_fail_runs:2}` → aprovar; segunda tarefa → `PATCH demo {budget_cap_tokens:100}` → aprovar | 1ª: falha → retry → `suspensa/retries`; 2ª: `interrompida_budget` → `suspensa/budget` |
| d7 | seed (tickets do tema repetido) | rodar job de captação passiva | proposta extraída dos tickets → `requires_zone=true` após o padrão repetido → task final com `output_type=zona_dinamica` |
| d8 | seed; editar `project_context.md` removendo a restrição citada no 4º descarte histórico | rodar job de auditoria + job de reavaliação cíclica | auditoria gera ao menos uma proposta `origin=auditoria` sobre o client-backend; reavaliação reintroduz o descarte cujo motivo não é mais válido |

## 8. README

Subida (`make up`, env), seeds, mapa de serviços/portas, roteiro das 8 demos com resultado esperado, e a lista "fora de escopo" (SPEC-10) para citação no TCC.

## 9. Critério de aceite (Definition of Done do projeto)

`make reset && make seed` → `demo-d1` … `demo-d8` verdes → 3 CSVs de métricas preenchidos e coerentes com o que as demos produziram.
