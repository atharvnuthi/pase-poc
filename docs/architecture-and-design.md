# Arquitetura e Design

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

Como o sistema está montado e por que cada peça está onde está. Para saber o que já
funciona, veja [`STATUS.md`](STATUS.md); para os limites deliberados,
[`scope-and-constraints.md`](scope-and-constraints.md).

---

## 1. Os dois sistemas

O erro mais caro que alguém pode cometer aqui é confundir os dois:

- **PASE** é o sistema. Recebe demandas, filtra, prioriza, escreve código sob aprovação
  humana e personaliza interface em runtime.
- **FinTrack** é o produto-alvo - um dashboard financeiro pessoal. É o *paciente*: o que
  o PASE observa e evolui.

O PASE nunca se modifica. O `pase-core` está fora do alcance do Executor por construção.

## 2. Serviços

| Serviço | Stack | Porta | Papel |
|---|---|---|---|
| `db` | Postgres 16 + pgvector | 5432 | estado do PASE e busca vetorial |
| `pase-core` | FastAPI + SQLAlchemy | 8000 | o motor |
| `client-backend` | FastAPI + SQLModel + SQLite | 8001 | API do FinTrack |
| `client-frontend` | Next.js 15 (App Router) + Tailwind | 3001 | o FinTrack |
| `pase-panel` | Next.js 15 + TanStack Query | 3000 | painel de controle humano |

Todos em modo dev com volume montado. Um merge aprovado pelo PASE aparece no app rodando
por hot reload - é o que faz as vezes de "deploy" nesta fase.

**Hot reload sob Docker no Windows.** O bind mount do Docker Desktop não entrega eventos
de inotify para dentro do container: nenhum watcher percebe arquivo salvo no host. Por
isso os serviços rodam com polling (`WATCHFILES_FORCE_POLLING` no uvicorn,
`WATCHPACK_POLLING` no Next). E porque o painel mantém um SSE aberto - que por definição
não fecha - o `pase-core` precisa de `--timeout-graceful-shutdown`, senão o primeiro
salvamento o deixa parado esperando a conexão terminar.

## 3. Os três loops

Todo componente pertence a exatamente um loop. O que não pertence a nenhum não faz parte
do modelo.

### Loop lento - evolução de código

```
demanda → Task Layer → Orquestração → Execução → Homologação → merge
                                                      ↑
                                               gate humano (sempre)
```

Latência de minutos. Produz mudança permanente no código-fonte. **Nunca** entra na branch
principal sem aprovação humana explícita.

### Loop rápido - personalização

```
telemetria → regra → P6 gera payload → valida no core → valida no cliente → renderiza
                                                              ↓ falhou
                                                     componente nativo + violação
```

Latência de segundos. Não gera código e não toca o repositório: preenche propriedades de
componentes que já existem, foram revisados e testados. O gate aqui é a validação de
contrato, não uma pessoa.

### Loop de manutenção

Dois jobs que reinjetam trabalho nos outros dois loops, e que **não podem ser fundidos**
porque leem coisas diferentes:

- **Ciclo de Auditoria** lê o *código-fonte* e propõe refatoração.
- **Reavaliação Cíclica** lê o *histórico de descartes* e reabre o que o contexto de hoje
  já não rejeita.

## 4. Camadas do `pase-core`

```
app/
├── common/        config, db, llm_client, vector_store, git_service, events,
│                  prompts, routes_context
├── task_layer/    captação → normalização → zona → memória → coerência → qualificação
├── orchestration/ estados, priorização, DAG de conflito, gates, homologação
├── execution/     planejamento (P4) e execução (P5), em fases separadas
├── upa/           telemetria, regra, geração e validação de payload de zona
├── jobs/          captação passiva, auditoria, reavaliação cíclica
├── metrics/       os três CSVs da validação
└── prompts/       P0, P0a, P1, P1b, P2a, P2b, P3, P3b, P4, P5, P6, P9, P10
```

### Regras de fronteira

Três convenções que existem para o sistema continuar auditável:

1. **Toda chamada a LLM passa por `common/llm_client.py`.** Nenhum módulo fala com o
   provider direto. É o que garante que toda chamada registra `trace_id`, tokens e tags -
   e é o que permite religar qualquer decisão do sistema à conversa exata que a produziu.
2. **Todo SQL vetorial vive em `common/vector_store.py`.**
3. **Prompts são arquivos versionados**, um por prompt, nunca string embutida no Python.
   Interpolação por `{{var}}` - nunca `str.format`, porque os prompts contêm chaves
   literais de JSON.

## 5. O Executor

Uma run é um processo com fronteiras explícitas:

1. **Isolamento.** `git clone` do repositório para `/tmp/pase/task-{id}`, na branch
   `pase/task-{id}`. Nada é escrito na branch principal aqui.
2. **Budget antes da chamada.** O teto é conferido contra o *custo previsto*, não contra o
   gasto acumulado - checagem retrospectiva deixaria a primeira chamada passar.
3. **Geração.** P5 devolve o arquivo inteiro, nunca um diff textual.
4. **Fronteira de escrita.** Caminho sob `client-frontend/dynamic-zones/` reprova a run
   antes de o arquivo tocar o disco.
5. **Verificação por alvo.** `ruff --fix` → `ruff` → `pytest` no backend; `tsc` → `vitest`
   no frontend. Só o alvo tocado é verificado.
6. **Rede de regressão conferida por código.** O inventário de testes é tirado do clone
   *intacto* e comparado com o resultado. Teste que sumiu reprova a run.
7. **Correção local** até o teto, depois retry, depois `suspensa`.
8. **Artefatos.** `diff.patch`, `lint_test.log` e `transcript.jsonl` - o transcript traz
   todas as mensagens trocadas com o modelo na run.

**Sem allowlist rígida de caminho.** O Executor pode tocar arquivos correlacionados fora
do plano; o que estiver fora vira `deviation_files` na run e aparece destacado na
Homologação. Liberdade com relato, em vez de proibição que empurra o modelo a entregar
pela metade.

## 6. Princípios que o código precisa obedecer

Estes vêm da constituição do projeto e vencem qualquer decisão local em conflito.

**Rastreabilidade integral.** Toda decisão relevante vira linha em tabela, nunca só log:

| Estágio | Artefato |
|---|---|
| ideia bruta | `proposals` |
| ideia qualificada | `tasks` (candidata) |
| plano técnico | `planning_documents` |
| execução | `execution_runs` + diff + transcript |
| decisão humana | `task_state_history` |
| configuração de zona | `zone_payloads` |

**Gate humano é registro, nunca bloqueio.** Tarefa esperando decisão é um *status*
(`candidata`, `em_homologacao`, `suspensa`). O sistema segue rodando outras tarefas.

**Contenção da generatividade.** Onde a imprevisibilidade é permitida está declarado
(P3 roda a 0.9; todo o resto entre 0.1 e 0.3). Todo laço tem teto de tentativas e teto de
custo - e os tetos são *código que impede*, não prompt pedindo cautela.

**Verificação em duas camadas.** A máquina verifica antes do humano. A pessoa revisa o que
já passou por lint e testes; ela é a última linha de defesa, nunca a primeira.

**Zona Dinâmica nunca executa código arbitrário.** Sem exceção. O LLM escolhe um widget do
catálogo e preenche propriedades validadas; qualquer violação cai no componente nativo.

## 7. Comunicação com o painel

O painel reage a eventos reais do sistema em vez de perguntar em laço: o `pase-core`
publica por Postgres `LISTEN/NOTIFY` e serve um SSE em `/api/events/stream`. TanStack
Query cuida do cache e das poucas chamadas que são de fato request/response (aprovar,
homologar).

## 8. Onde cada estágio do SDLC acontece

O PASE não é um apêndice do ciclo de desenvolvimento - ele *é* uma implementação dele, com
a IA no trabalho mecânico e a pessoa nos pontos de decisão.

| Estágio | Componente | Gate humano | Artefato |
|---|---|---|---|
| Requisitos | Task Layer | aprovar a candidata | `tasks` |
| Design | Fase de Planejamento | implícito, revisável na Homologação | `planning_documents` |
| Implementação | Fase de Execução | nenhum durante a escrita | `execution_runs` + diff |
| Testes | ciclo de correção local | automático, bloqueia antes do humano | `lint_test.log` |
| Deploy | Homologação | aprovar o merge | commit na principal |
| Manutenção | Ciclo de Auditoria | aprovar a tarefa gerada | `proposals(origin=auditoria)` |
| Monitoramento | Captação Passiva e Incidentes | nenhum na captação | `proposals(origin=passiva)`, `incidents` |

## 9. Decisões de modelo tomadas por medição

O projeto mudou de ideia em alguns pontos, sempre depois de medir. O registro completo,
com números, está em [`STATUS.md` §6](STATUS.md#6-divergências-entre-o-projetado-e-o-construído).
Em resumo: o limiar de similaridade foi recalibrado, o agrupamento de tickets saiu do
cosseno e foi para um prompt, o veredito de deriva saiu do modelo e foi para o código, e a
defesa da rede de regressão deixou de ser um pedido no prompt para virar conferência
determinística.
