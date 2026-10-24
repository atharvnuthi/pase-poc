# SPEC-09 - Divisão do Trabalho e Cronograma

**Papel:** este documento não é um componente técnico, é organizacional. Serve para orientar como as sessões de Claude Code devem ser divididas caso o projeto seja trabalhado em paralelo (dois desenvolvedores, ou um desenvolvedor com múltiplas sessões paralelas, ver o "Parallel sessions" do playbook).

## 1. Frentes

**Frente PASE (motor):** SPEC-01 (infra), SPEC-03 (Task Layer), SPEC-04 (Orquestração + Execução), SPEC-06 telas Tarefas/Tarefa[id]/Incidentes, SPEC-08.

**Frente FinTrack + Personalização (alvo e runtime):** SPEC-02 (FinTrack completo), SPEC-05 (UPA + Zonas), SPEC-06 tela Zonas, seeds, consolidação dos roteiros de demo.

## 2. Mapa de propriedade

| Caminho | Frente | SPEC |
|---|---|---|
| `docker-compose.yml`, `Makefile`, `.env.example`, `pase-core/Dockerfile` | PASE | 01 |
| `client-*/Dockerfile`, `pase-panel/Dockerfile` | FinTrack | 01 |
| `pase-core/app/common/` | PASE | 01/08 |
| `pase-core/app/task_layer/`, `orchestration/`, `execution/` + rotas de tarefas/incidentes | PASE | 03/04 |
| `pase-core/app/upa/` + rotas `/api/upa/*` | FinTrack | 05 |
| `client-backend/` | FinTrack | 02 |
| `client-frontend/` (inclui SDK DynamicZone) | FinTrack | 02/05 |
| `pase-panel/` shell + telas Tarefas, Tarefa[id], Incidentes | PASE | 06 |
| `pase-panel/` tela Zonas | FinTrack | 05 |
| `scripts/demo/`, seeds, README | consolidação conjunta | 06 |
| `docs/project_context.md` | humano, ambas as frentes | 07 |

Regra: cada frente só edita suas pastas. Mudança cruzada exige aviso explícito à outra frente antes do merge.

## 3. Cronograma (referência - ajustar aos três meses reais do TCC)

| Fase | Frente PASE | Frente FinTrack | Sincronização |
|---|---|---|---|
| F0 (~3d) | compose + db + `common/` (config, db, llm_client, vector_store, events) + shell do painel | Dockerfiles + esqueletos de client-backend/frontend/panel | `make up` verde; contratos deste documento congelados |
| F1 (~5d) | SPEC-03 completo (P0, P1, P1b, L1, P2a, P2b, bypass, exploratória, lacunas) | SPEC-02 completo (API + 9 testes + 5 rotas + telemetria + modal) | **client-backend congelado ao fim da F1** |
| F2 (~4d) | tela Tarefas → D2, D3, D7 rodam | SPEC-05 parte 1 (regra do UPA + P6 + simulate + payload) | modal integra com `/proposals/external` |
| F3 (~7-8d) | SPEC-04 completo + tela Tarefa[id] → D1, D6 rodam; Ciclo de Auditoria + Reavaliação Cíclica → D8 roda | SPEC-05 parte 2 (SDK + widgets + violações + inject-raw + tela Zonas) → D4, D5 rodam | teste cruzado: D1 altera o app-alvo; D4/D5 no dashboard |
| F4 (~3-4d, conjunto) | roteiros d1, d2, d3, d6, d8 + métricas CSV | seeds finais + roteiros d4, d5, d7 + README | **DoD: 8 demos verdes após `make reset && make seed`** |

Total de referência: aproximadamente 22-24 dias corridos de implementação, deixando o restante das 12 semanas do TCC para escrita da monografia, ajustes e ensaio da defesa.

## 4. Dependências críticas

1. **client-backend congelado ao fim da F1** - é o alvo do Executor.
2. **`llm_client`, `vector_store`, `events` prontos na F0** - todo o resto depende deles.
3. **`POST /api/proposals/external` no ar antes da F2** - até lá, o modal falha silenciosamente (try/catch com toast genérico).
4. **Demos do Executor mexem na main local** - sempre commitar o próprio trabalho antes de rodar d1/d6.

## 5. Definition of Done

`make reset && make seed` → `demo-d1` … `demo-d8` verdes → 3 CSVs de métricas preenchidos e coerentes com o que as demos produziram.
