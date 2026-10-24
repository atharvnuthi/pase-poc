# SPEC-03 - Task Layer (captação → normalização → zona → filtragem → candidata)

**Fase:** F1–F2 · **Depende de:** SPEC-01 · **Demos:** D2, D3, D7

## 1. As quatro origens de demanda

O modelo PASE define quatro fluxos de captação. Todos convergem no mesmo pipeline de normalização, com uma exceção deliberada (Sugestões de Engenharia, Seção 4).

| Origem | Endpoint | Disparo |
|---|---|---|
| Agente Externo - Captação Ativa | `POST /api/proposals/external` | modal do FinTrack |
| Agente Externo - Captação Passiva | job periódico, sem endpoint direto | lê `SupportTicket` do client-backend |
| Agente Interno - Sugestão Funcional | `POST /api/proposals/internal {type: "funcional", author, text}` | formulário do painel |
| Agente Interno - Sugestão de Engenharia | `POST /api/proposals/internal {type: "engenharia", author, text}` | formulário do painel, com checagem de papel |
| IA - Geração Exploratória | `POST /api/proposals/ai-generate {mode: "exploratoria"}` | botão do painel ou cron |
| IA - Análise de Lacunas | `POST /api/proposals/ai-generate {mode: "lacunas"}` | botão do painel ou cron |

Resposta síncrona de todo endpoint de ingestão = envelope da Seção 6. O pipeline roda na própria requisição (segundos, aceitável na PoC), exceto a Captação Passiva, que roda em background.

## 2. Captação Passiva

Job periódico (`APScheduler`, a cada execução manual via `make demo-d7` na PoC - em produção seria um cron real) que:

1. Lê tickets do client-backend criados desde a última execução (`GET /tickets`).
2. Para cada ticket (ou lote de tickets correlacionados), roda **P0 - Extração de Intenção**: converte a reclamação informal em uma proposta estruturada candidata a entrar no pipeline normal.
3. Cada proposta extraída entra no pipeline pela Seção 3 como se fosse uma proposta `external`, com `origin=passiva`.

Isso é deliberadamente distinto de telemetria de interface (cliques, tempo na tela), que pertence ao UPA (SPEC-05) e nunca passa pelo Task Layer - são dois canais de observação diferentes, um alimenta evolução de código, o outro alimenta personalização em runtime.

## 3. Pipeline principal (fluxo funcional e externo)

1. **Registro:** cria `proposals` com texto bruto e origem.
   - Para `ai-generate` modo `exploratoria`: antes disso, **P3** gera o texto a partir de `project_context.md` + títulos das implementadas + motivos dos descartes, com temperatura alta (0.9 - única chamada do sistema com temperatura alta).
   - Para `ai-generate` modo `lacunas`: **P3b** cruza módulos implementados (via `implemented_items`) buscando combinações não exploradas, temperatura baixa (é análise, não brainstorm).
2. **P1 - Normalização** → `{ title, description, module }` (module ∈ dashboard | transacoes | relatorios | suporte | geral).
3. **Avaliador de Zonas Dinâmicas** (só roda para propostas de módulo `dashboard`, `relatorios` ou `transacoes` - onde zonas fazem sentido; outras pulam direto para o passo 4):
   - **P1b - Avaliação de Zona** → `{ requires_zone: bool, reasoning }`. O modelo avalia: esta demanda tem solução homogênea aplicável a todos os usuários, ou é um padrão de cauda longa com soluções divergentes entre usuários?
   - Se `requires_zone=true` **e** já existe uma zona homologada cobrindo o módulo (consulta ao registro de zonas do SPEC-05): a proposta é redirecionada - não vira uma tarefa de código, vira um sinal para o UPA avaliar (não faz parte deste SPEC, é tratado no fluxo do SPEC-05).
   - Se `requires_zone=true` **e não existe** zona ainda cobrindo aquele módulo: a proposta é marcada `tipo=parametrizacao` e segue para o Motor de Filtragem como as demais, mas ao virar `task` carrega `output_type=zona_dinamica` em vez de `output_type=codigo_permanente`. Isso é o que a Execução usa depois para saber se está escrevendo uma funcionalidade fixa ou abrindo uma zona (ver SPEC-04 Seção 1).
   - Se `requires_zone=false`: segue normalmente como tarefa de funcionalidade estática.
4. **L1 - Memória Histórica:** `embed(title + description)` → `vector_store.search` contra `implemented ∪ candidatas ∪ discarded`.
   - `similarity ≥ SIMILARITY_THRESHOLD` → outcome `descartada_duplicata`. Não persiste nova linha com embedding - em vez disso, incrementa `duplicate_count` na linha já existente em `discarded_proposals` (ou `implemented_items`, se o match foi contra algo já implementado) e anexa a referência em `duplicate_refs` (json array). Isso preserva o dado de frequência que o Avaliador de Zonas Dinâmicas precisa para decidir se um padrão é recorrente - descartar sem contar destruiria esse sinal.
5. **P2a - Coerência:** contexto = `project_context.md` → `{ coherent: bool, reason, needs_adjustment: bool, adjusted_title?, adjusted_description? }`.
   - `coherent=false` → `descartada_incoerente`: grava em `discarded_proposals` **com embedding** (entra na memória) e encerra.
   - `needs_adjustment=true` → aplica o ajuste e **revalida contra L1** (passo 4) antes de prosseguir. Máximo `COHERENCE_MAX_ADJUSTMENTS` (padrão 2) rodadas; se ainda não estabilizar, descarta como `descartada_incoerente` com motivo "ajuste não convergiu".
6. **P2b - Qualificação:** → `{ impact 1–5, complexity 1–5, confidence 0–1, risk_tier: "baixo"|"medio"|"alto" }`. `risk_tier` é estimado a partir do módulo afetado e do `output_type` (zona dinâmica tende a `baixo`, mudança em `/transacoes` tende a `medio` ou `alto` por mexer em dados financeiros). Grava embedding na proposal, cria `tasks` com `status=candidata`, `uncertainty = confidence < 0.5`.

## 4. Sugestões de Engenharia (bypass)

Proposta com `type=engenharia` exige `author` com papel autorizado (`ENGINEERING_AUTHORS` - lista fixa em env para a PoC, ver SPEC-10 para RBAC real). Pula os passos 4 e 5 inteiramente (Memória e Coerência) e vai direto para P2b (Qualificação), sempre com `risk_tier` mínimo `medio` (tarefas de engenharia mexem em infraestrutura por definição). Justificativa: a autorização já transferiu a responsabilidade de julgamento para um humano qualificado, mas a tarefa ainda precisa de metadados para ser priorizada.

## 5. Reavaliação Cíclica

Job periódico (`make demo-d8` na PoC) que:
1. Lê `discarded_proposals` com `reason_type=incoerente` (duplicatas não fazem sentido reavaliar - a implementação ainda existe).
2. Para cada uma, roda **P9 - Análise de Deriva**: compara o motivo do descarte original contra o `project_context.md` atual → `{ still_valid_rejection: bool, reasoning }`.
3. Se `still_valid_rejection=false`: a proposta original é reinserida no pipeline (volta ao passo 3 da Seção 3) com `origin=reavaliacao` e uma referência ao descarte original.

## 6. Tabelas

- `proposals(id, origin external|internal|passiva|ai, type funcional|engenharia|null, raw_text, user_id?, author?, title, description, module, output_type codigo_permanente|zona_dinamica, embedding vector(EMBEDDING_DIM) null, outcome, created_at)`
- `discarded_proposals(id, proposal_id?, task_id?, reason_type duplicata|incoerente|recusa_humana, reason_text, matched_ref?, duplicate_count int default 1, duplicate_refs json default '[]', embedding vector null, created_at)`
- `implemented_items(id, title, description, embedding vector, task_id?, duplicate_count int default 1, created_at)`

`tasks` é definida no SPEC-04; este SPEC apenas a cria com os campos iniciais, incluindo `output_type` e `risk_tier`.

## 7. Prompts (pt-BR, versionados em `pase-core/app/prompts/`)

| P | Entrada | Saída (JSON estrito) | Diretrizes |
|---|---|---|---|
| **P0** extração de intenção | texto de 1+ tickets de suporte | `{title, description, module}` ou `null` se não há sinal de melhoria acionável | converter reclamação em proposta construtiva; nunca inventar um problema que o texto não sugere |
| **P1** normalização | texto bruto + lista de módulos | `{title, description, module}` | extrair o núcleo semântico; título ≤ 80 chars; não inventar requisitos |
| **P1b** avaliação de zona | proposta normalizada + `duplicate_count` de propostas correlatas já vistas | `{requires_zone, reasoning}` | zona só se o padrão for de cauda longa (soluções divergentes entre usuários); funcionalidade homogênea vira código permanente |
| **P2a** coerência | proposta normalizada + `project_context.md` | `{coherent, reason, needs_adjustment, adjusted_title?, adjusted_description?}` | descartar o que viola escopo ou regra central do FinTrack; ajuste só se a essência da proposta for preservada |
| **P2b** qualificação | proposta coerente + contexto técnico geral | `{impact, complexity, confidence, risk_tier}` | metadados relativos ao porte do app; `risk_tier` alto para qualquer coisa que toque saldo ou dados financeiros |
| **P3** geração exploratória | `project_context.md` + títulos implementadas + motivos de descartes | `{text}` | propor melhoria pequena e plausível; evitar temas já implementados ou descartados; temperatura 0.9 |
| **P3b** análise de lacunas | mapa de módulos implementados | `{text}` ou `null` | cruzar dois módulos existentes e sugerir uma integração ainda não feita; temperatura baixa |
| **P9** análise de deriva | motivo do descarte original + `project_context.md` atual | `{still_valid_rejection, reasoning}` | só reverter se o contexto realmente mudou, não por otimismo |

## 8. Critérios de aceite

1. `POST external` "Quero ver um relatório dos meus gastos por mês" → `descartada_duplicata`, `duplicate_count` incrementado na implementada "Relatórios mensais".
2. `POST external` "Adicionar minigame de corrida no app" → `descartada_incoerente` com motivo persistido.
3. Reenvio de variação do minigame → `descartada_duplicata` com `matched_ref` no descarte anterior, `duplicate_count=2`.
4. `POST internal {type: funcional}` "exportar transações em CSV" → `candidata` com metadados; se `confidence < 0.5`, marcador de incerteza.
5. `POST internal {type: engenharia, author: <autorizado>}` "atualizar dependências do client-backend" → pula L1 e P2a, vai direto a `candidata` com `risk_tier=medio` no mínimo.
6. `POST internal {type: engenharia, author: <não autorizado>}` → 403.
7. Três tickets de suporte simulando a mesma dor (ex: "não acho meus gastos por categoria facilmente") rodando `make demo-d7` → P1b marca `requires_zone=true` após o padrão se repetir; proposta final tem `output_type=zona_dinamica`.
8. `make demo-d8` após um descarte incoerente antigo cujo motivo não é mais válido no `project_context.md` atual → proposta reentra como `candidata`.
9. `POST ai-generate {mode: exploratoria}` → candidata nova coerente (ou descarte legítimo pelo próprio funil).
