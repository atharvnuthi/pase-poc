# Estado de Construção do Modelo PASE

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros
**Última verificação:** 24 de outubro de 2026, contra o código em execução (não contra a intenção dos documentos de projeto).

Este é o documento de referência para "o que existe". Cada linha foi conferida no código
ou numa chamada real à API, não copiada de uma especificação. Onde a implementação
divergiu do que estava planejado, a divergência está registrada - ela costuma ser o
achado mais interessante.

Legenda: **✅ construído e verificado** · **◐ construído com ressalva** · **⭕ não construído (decisão registrada)**

---

## 1. Os três loops

O modelo se organiza em três loops concêntricos. Todo componente pertence a exatamente um
deles; o que não pertence a nenhum não faz parte do PASE.

| Loop | O que faz | Latência | Gate | Estado |
|---|---|---|---|---|
| **Lento** - evolução de código | Task Layer → Orquestração → Execução | minutos | aprovação humana, sempre | ✅ |
| **Rápido** - personalização | UPA preenche propriedades de componentes que já existem | segundos | validação de contrato | ✅ |
| **Manutenção** | auditoria de código e reavaliação de descartes | job manual | reinjeta nos outros dois | ◐ roda por comando, não por cron |

---

## 2. Loop lento

### 2.1 Task Layer - da frase crua à tarefa candidata

As quatro origens de demanda do modelo, todas em pé:

| Origem | Entrada | Estado |
|---|---|---|
| Captação Ativa (agente externo) | modal "Sugerir melhoria" no FinTrack → `POST /api/proposals/external` | ✅ |
| Captação Passiva (agente externo) | job que lê `GET /tickets` do FinTrack | ✅ |
| Sugestão Funcional (agente interno) | `POST /api/proposals/internal {type: "funcional"}` | ✅ |
| Sugestão de Engenharia (agente interno) | idem, `type: "engenharia"`, com checagem de autor | ✅ |
| Geração Exploratória (IA) | `POST /api/proposals/ai-generate {mode: "exploratoria"}` | ✅ |
| Análise de Lacunas (IA) | idem, `mode: "lacunas"` | ✅ |
| Prospecção Competitiva | scraping de concorrentes | ⭕ fora de escopo |

Pipeline de filtragem, na ordem em que roda:

| Etapa | Prompt | Estado | Observação |
|---|---|---|---|
| Extração de intenção (tickets) | P0 | ✅ | |
| Agrupamento de tickets por tema | P0a | ✅ | **Não estava no projeto original.** Criado porque embedding não separa tema em texto curto e coloquial - ver §6. A demanda leva o tamanho do grupo como `occurrences` |
| Normalização | P1 | ✅ | |
| Avaliação de Zona Dinâmica | P1b | ✅ | decide `codigo_permanente` vs `zona_dinamica` |
| Memória Histórica (L1) | - (pgvector) | ◐ | funciona; limiar recalibrado de 0.85 para 0.72 por medição - ver §6. Duplicata soma `occurrences` ao item achado (implementado, descartado ou em andamento) e não cria embedding |
| Coerência Sistêmica | P2a | ✅ | compara com os documentos de contexto (no banco) e com os 5 descartes mais parecidos; descarte só se o `trecho_violado` existir literalmente no contexto, senão vira candidata com incerteza |
| Recuperação por similaridade (RAG) | - (pgvector) | ✅ | P1b recebe os 5 pedidos mais parecidos do módulo; P2a, os 5 descartes mais parecidos |
| Devolutiva ao usuário | - | ✅ | `GET /api/proposals/mine`; "Minhas sugestões" no modal do FinTrack |
| Qualificação | P2b | ✅ | impacto, complexidade, confiança, `risk_tier` |
| Bypass de Engenharia | - | ✅ | pula Memória e Coerência; autor precisa estar em `ENGINEERING_AUTHORS` |

### 2.2 Orquestração

| Item | Estado | Observação |
|---|---|---|
| Máquina de estados com histórico de toda transição | ✅ | `task_state_history` |
| Priorização `impact − complexity + urgency_score` | ✅ | candidata nova já nasce com a urgência dos incidentes abertos no módulo |
| Marcador de incerteza | ✅ | confiança < 0,5 **ou** impacto ≤ 2 com complexidade ≥ 4 (`task_layer/uncertainty.py`); recalculado na edição |
| Fator de Urgência a partir de incidentes | ✅ | soma simples por severidade; sem SLA nem decaimento |
| Detecção de conflito de arquivos entre tarefas | ✅ | segunda tarefa espera em `waiting_on_task_id` |
| Gate humano como **registro**, nunca processo travado | ✅ | é sempre um status na tabela |
| Guardrail de budget | ✅ | preditivo, antes da chamada - ver §6 |
| Política de falhas com teto de tentativas | ✅ | vale também para o planejamento |
| Suspensão em cascata | ✅ | dependentes (arestas que bloqueiam) suspensos junto; voltam quando a predecessora é retomada, replanejada ou cancelada |
| Despacho paralelo | ✅ | cada tarefa liberada roda na sua thread; decisão de despacho sob trava |
| **Grafo de dependências** (`task_dependencies`) | ✅ | três origens: arquivo, semântica (similaridade ≥ 0,60, **não bloqueia**) e manual; ciclo recusado na criação |
| **Editar metadados da tarefa** | ✅ | com registro no histórico |
| **Cancelar tarefa** | ✅ | cooperativo quando em execução |
| **Ajustar o teto de tokens** | ✅ | `budget_cap_tokens`, vence o cálculo automático |
| **Replanejar do zero** | ✅ | joga o plano fora; o gasto anterior continua contando |
| **Aprovação do plano** (`aguardando_plano`) | ✅ | liga por risco (`PLAN_APPROVAL_TIERS`, padrão médio e alto) ou por escolha ao aprovar a candidata; aprovar, devolver com feedback ou editar à mão; nenhum token de execução antes |
| **Refazer** uma tarefa finalizada | ✅ | tarefa nova ligada à anterior; reverte o merge se estava integrada; leva plano, parecer e motivo ao P4 |
| **Fluxo de entrega** `feature/hotfix → develop → release → principal` | ✅ | ver §2.4 |
| Sub-DAGs e replanejamento automático | ⭕ | fora de escopo |

### 2.3 Execução

Duas fases separadas, como o modelo exige:

| Item | Prompt | Estado | Observação |
|---|---|---|---|
| Planejamento (mapeia arquivos, estima custo) | P4 | ✅ | |
| Geração e correção de código | P5 | ✅ | devolve arquivo inteiro, nunca diff textual |
| **Critérios de aceite** definidos antes do código | P4 | ✅ | observáveis pelo usuário, não o mecanismo; viram a régua da revisão |
| **Revisão independente** da entrega | P12 | ✅ | outro modelo confere cada critério citando o trecho e o teste; **o código confere que as citações existem** |
| Modelos separados por etapa | - | ✅ | `gpt-5.3-codex` escreve (Responses API), `gpt-5.5` revisa, funil em `gpt-4.1-mini` |
| Isolamento: clone em `/tmp`, branch `<feature\|hotfix>/pase-{id}-{slug}` | - | ✅ | |
| Verificação automática antes do humano | - | ✅ | backend: `ruff`, `pytest`, **smoke que sobe o app**; frontend: `tsc`, `vitest`, **`next build`** |
| **Teste novo obrigatório** para comportamento novo | - | ✅ | inventário conferido por código; mudança só em CSS/docs não exige |
| **Cobertura dos arquivos alterados não pode cair** | - | ✅ | fecha a saída do gate acima: teste trivial que não exercita nada |
| **Convenção de branch e commit conferida por código** | - | ✅ | `feature/pase-{id}-{slug}` (correção vira `hotfix/`) e `<tipo>(<escopo>): …` |
| Relato de desvio (arquivo fora do plano) | - | ✅ | `deviation_files` na run |
| Rede de regressão conferida por código | - | ✅ | inventário "antes" lido **do git (a principal)**, nunca do disco do clone - ver §6 |
| Fronteira de escrita | - | ✅ | caminho normalizado; só os dois alvos são graváveis; `dynamic-zones/`, `docs/contracts/` e `pase-core/` protegidos; vale para exclusão; verificada antes de tocar o disco |
| Ambiente das verificações sem credenciais | - | ◐ | sem chaves, token, URLs de serviço; proxies para um endereço morto; npm e pip offline. Não bloqueia socket direto: isso exigiria contêiner efêmero (fora de escopo) |
| Execução parte do roteiro | P5 | ✅ | recebe só os arquivos do plano, importações diretas, testes que os usam e a infraestrutura de testes; o planejamento lê o código inteiro |
| Plano com ação por arquivo, tempo e risco técnico | P4 | ✅ | modificar/criar/excluir; `minutes_estimated`; `technical_risk` |
| Asserções preservadas | - | ✅ | número de asserções por teste e por alvo, comparado com a principal |
| Homologação: aprovar / ajustar / recusar | - | ✅ | aprovar integra **na `develop`**, não na principal |
| Reversão por estágio | - | ✅ | desfaz na develop e na release; o que está em produção só se corrige com hotfix |
| Pull Request real no GitHub (da **release**) | - | ✅ | com `GITHUB_TOKEN`, a release sobe e o PR é aberto e mergeado no GitHub; sem ele, o PASE faz o papel do PR. A suíte de testes nunca fala com o GitHub (fixture `github_desligado`) |

### 2.4 Entrega - do código aprovado à produção

Aplica o [guia de fluxo de ramos](entrega-no-pase.md). As regras vivem em
`pipeline_rules.py` (sem efeito colateral, testável) e o fluxo em `delivery.py`.

| Item | Estado | Observação |
|---|---|---|
| Matriz de integrações e fluxos proibidos | ✅ | `feature→main`, `develop→qualquer coisa` levantam erro antes de tocar o repositório |
| Branch que incorporou a `develop` é recusada | ✅ | conferido antes de todo merge |
| Tarefa → `develop` por merge `--no-ff` | ✅ | num clone próprio; a árvore de trabalho do repositório não é tocada |
| CI da `develop` em segundo plano | ✅ | reprovou, a integração é desfeita |
| Aprovação funcional nos testes | ✅ | exige nota; só o aprovado entra numa release |
| Releases `release/x.x.x` a partir da principal | ✅ | versão semântica sugerida a partir das tags |
| Validação final da release | ✅ | suítes completas na branch, com tudo integrado |
| PR com o corpo que o guia §7 exige | ✅ | só abre depois da validação |
| Publicação: merge na principal + tag | ✅ | exige a aprovação humana por escrito |
| Proteção de branches no GitHub | ⭕ | configuração do repositório remoto, fora do código |

**Alvos do Executor:** `client-backend/` e `client-frontend/`, exceto
`client-frontend/dynamic-zones/`. O `pase-core` nunca é alvo - o sistema não se modifica.

---

## 3. Loop rápido - UPA e Zonas Dinâmicas

| Item | Estado | Observação |
|---|---|---|
| Telemetria de navegação | ✅ | `page_view` a cada troca de rota |
| Regra de disparo por zona (N visitas à rota da zona em 7 dias) | ✅ | cooldown de 24h por (pessoa, zona), para o custo não depender de quanto a pessoa navega |
| Geração de payload | ✅ | P6 |
| Validação no core (JSON Schema) antes de persistir | ✅ | defesa em profundidade |
| Validação no cliente (Zod) - a decisiva | ✅ | espelho do JSON Schema canônico |
| Fallback para o componente nativo em qualquer falha | ✅ | |
| Registro de violação | ✅ | com motivo e payload bruto |
| Catálogo de widgets | ✅ | 3: `shortcut_list`, `summary_card`, `alert_banner` |
| **Nunca executa código arbitrário** | ✅ | sem `dangerouslySetInnerHTML`; `href` restrito por regex; agora coberto por teste automatizado |
| **Seis zonas, uma por tela** | ✅ | `resumo_financeiro`, `transacoes_atalhos`, `relatorios_destaque`, `orcamentos_aviso`, `metas_incentivo`, `suporte_ajuda`; mesmo contrato, mesmo catálogo |
| **Pedido do usuário chega à zona** | ✅ | sugestão escrita que uma zona cobre ajusta a zona na hora em vez de virar tarefa de código |
| Voltar ao padrão pelo próprio usuário | ✅ | revogação durável: a zona não é repersonalizada automaticamente para essa pessoa |
| Avaliação registrada | ✅ | sinais enviados ao P6, decisão, motivo, trace e payload/violação resultante |
| Recusa no servidor vira violação | ✅ | `origem` = servidor ou cliente |
| Espelho do contrato conferido campo a campo | ✅ | o teste converte o Zod em JSON Schema e compara |
| Gatilhos de frustração (cliques repetidos, tempo, erros de validação) | ⭕ | fora de escopo; só navegação |
| Zonas sob demanda, event bus, fluxos declarativos | ⭕ | fora de escopo |

---

## 4. Loop de manutenção

| Job | Prompt | Estado | Observação |
|---|---|---|---|
| Ciclo de Auditoria (lê o **código**) | P10 | ✅ | gera proposta `origin=auditoria`; botão no painel (Sistema) ou `POST /api/jobs/auditoria` |
| Reavaliação Cíclica (lê o **histórico de descartes**) | P9 | ✅ | o modelo aponta a evidência, o código confere - ver §6; botão no painel ou `POST /api/jobs/reavaliacao` |
| Agendamento automático (cron) | - | ⭕ | roda por comando |

---

## 5. Superfícies

### Painel de controle (`pase-panel`, porta 3000)

| Tela | Estado |
|---|---|
| Tarefas - Candidatas, Em andamento, Finalizadas (com **Reverter merge**), Descartadas | ✅ |
| Tarefa [id] - trilho do ciclo, critérios de aceite, decisão sobre o plano, runs, diff, logs, transcript, **parecer da revisão com evidência**, homologação | ✅ |
| **Entrega** - develop, releases, PR, publicação, rastro do pipeline | ✅ |
| Zonas - payloads, violações, simulador e injetor com escolha da zona | ✅ |
| Incidentes | ✅ |
| **Contexto** - 19 documentos no banco, editáveis, com histórico de versões, leitura por etapa e sugestão de atualização depois de cada aprovação (P11), aceita por uma pessoa | ✅ |
| **Dependências** - o grafo ao vivo | ✅ |
| **Sistema** - fila, memória vetorial, custo, guardrails, prompts e glossário | ✅ |
| Atualização ao vivo por SSE (Postgres LISTEN/NOTIFY) | ✅ |

### FinTrack (`client-frontend`, porta 3001)

Sete rotas: seletor de persona, dashboard, transações (busca e filtros), **orçamentos**, **metas**, relatórios (variação mensal), suporte. Todas ✅. Cada tela tem a sua zona dinâmica.

### Métricas

Três CSVs (`tasks`, `discards`, `violations`), servidos pelo core e baixados por
`make metrics`. Delas saem as três medidas da monografia: taxa de intervenção humana,
densidade de retrabalho e incidência de regressões.

---

## 6. Divergências entre o projetado e o construído

Estas são as decisões que mudaram **depois de medir**. Cada uma nasceu de uma falha real.

| # | O que estava previsto | O que ficou | Por quê |
|---|---|---|---|
| 1 | `SIMILARITY_THRESHOLD = 0.85` | **0.72** | 0.85 fica acima de *todos* os positivos do `text-embedding-3-small`. Com ele a Memória Histórica nunca barra nada. Medido: positivos 0.69–0.90, negativos ≤0.65 |
| 2 | Agrupar tickets por similaridade de cosseno | Prompt **P0a** | Embedding não separa tema em texto curto e coloquial: tickets sobre a mesma dor ficaram em 0.47–0.61, *abaixo* de pares de temas diferentes |
| 3 | P9 devolve veredito booleano | P9 aponta **evidência**; o código confere | Pedir "isto ainda consta no documento?" produz confabulação - o modelo lê a citação dentro do próprio texto sob julgamento |
| 4 | Confiar que o modelo preserva os testes | Inventário tirado do clone intacto e conferido por código | Na primeira execução real o Executor **sobrescreveu um teste** e a verificação passou porque rodou a suíte adulterada |
| 5 | Budget conferido contra o gasto acumulado | Conferido contra o **custo previsto**, antes da chamada | Checagem retrospectiva deixa a primeira chamada passar - exatamente o que a demo de budget precisa barrar |
| 6 | `tokens_estimated` do P4 como teto | Teto com **piso** (`BUDGET_MIN_TOKENS`) | A estimativa erra por ordem de grandeza: estimou 1.200 para uma execução de 25.000 |
| 7 | Executor escreve só no `client-backend` | Escreve nos **dois alvos** | Uma tarefa aprovada saiu pela metade: a capacidade existia na API, faltava a tela, e o Executor não podia tocá-la |
| 8 | Modelo instruído a não tocar a defesa das zonas | Fronteira **verificada por código** | A garantia de que uma zona não executa código arbitrário não pode depender do julgamento do modelo que ela limita |
| 9 | Deixar o modelo corrigir falha de lint | `ruff check --fix` antes de `ruff check` | Um ciclo real gastou 51 mil tokens sem resolver uma ordem de import que o formatador conserta sozinho |
| 10 | Gates mecânicos bastam antes do humano | + **revisão independente por critério de aceite** | A tarefa do modo escuro passou em tudo e não fazia nada: pôs a classe `dark` no `body`, testou a classe, e nunca definiu uma cor escura |
| 11 | O revisor decide se a entrega cumpre | O revisor **cita**; o código confere o trecho | Mesma lição da #3: veredito booleano de LLM confabula |
| 12 | Todo colateral reprova a revisão | Só o que muda comportamento; o cosmético vira **aviso** | Aspas reformatadas e uma docstring consumiram 4 rodadas (~270 mil tokens) numa tarefa que cumpria os 5 critérios |
| 13 | Inventário de testes "antes" lido do clone | Lido **do git** | O clone reaproveitado guardava os testes da tentativa falha; nenhum teste novo podia contar como novo, e uma entrega com 3 foi reprovada 4 vezes |
| 14 | Aprovar na Homologação leva à principal | Leva à **`develop`**; só release chega à principal | O guia de fluxo de ramos separa "revisei o diff" de "publico em produção" |
| 15 | Aprovar a demanda aprova o plano | Plano tem gate próprio para risco médio e alto | O plano é o ponto mais barato para discordar: antes de gastar execução |

---

## 7. O que sabidamente não existe

Fora de escopo por decisão registrada, não por esquecimento. A lista completa com
justificativa está em [`scope-and-constraints.md`](scope-and-constraints.md).

Resumo: sem autenticação real, sem multi-tenancy, sem CI, sem proteção de branch no
remoto, sem observabilidade dedicada de LLM, sem deploy separado do
hot reload, sem sub-DAGs, sem prospecção competitiva, sem ambiente de testes
executável para a `develop`.

**Dívida conhecida, e não é "fora de escopo":**

- **Modo escuro no FinTrack.** Removido de propósito em 24/10/2026 para ser refeito pelo PASE na
  validação da monografia (ver `monografia/guia-capturas-fluxos.md`). Histórico: a primeira tentativa entregou só endpoints de
  preferência no backend, sem tela. A segunda quebrou o app, e a terceira (tarefa #4)
  passou em todos os gates sem definir uma cor escura - motivou as divergências #10 e #11.
  A sexta (task #6) foi publicada na 1.0.0 do ciclo de construção.
- **Jobs de manutenção rodam por comando,** não por agendador.

---

## 8. Como conferir

```bash
make reset && make seed     # estado limpo e reproduzível
make test-core              # 586 testes
make test-client            # 53 testes
docker compose exec client-frontend npm test   # 55 testes
make demos                  # d1 … d8
make metrics                # os três CSVs
```

A Definition of Done do projeto é: `make reset && make seed` → as oito demos verdes → os
três CSVs coerentes com o que as demos produziram.
