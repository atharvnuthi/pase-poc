# PASE - Personalized Adaptive Software Ecosystem

**Atharv Nuthi** · **Felipe Vahia Malliagros**

PoC do TCC. O **PASE** é o motor: recebe demandas de quatro origens, filtra com IA,
prioriza, executa mudanças de código sob aprovação humana, e personaliza a interface em
runtime. O **FinTrack** é o produto-alvo que o PASE evolui - um dashboard financeiro
simples. Nunca confundir os dois: o FinTrack é o paciente, o PASE é o sistema.

O modelo opera em **três loops concêntricos** (SPEC-00 §1):

| Loop | O que faz | Latência | Gate |
|---|---|---|---|
| **Lento** - evolução de código | Task Layer → Orquestração → Execução | minutos | aprovação humana, sempre |
| **Rápido** - personalização | UPA preenche propriedades de componentes existentes | segundos | validação de contrato |
| **Manutenção** | auditoria de código e reavaliação de descartes | job periódico | reinjeta nos outros dois |

## Documentação

| Para saber | Leia |
|---|---|
| **sobre o projeto e o que ele demonstrou** | [`docs/sobre-o-projeto.md`](docs/sobre-o-projeto.md) |
| o que já existe, e o que não existe | [`docs/STATUS.md`](docs/STATUS.md) |
| o que o sistema faz | [`docs/features.md`](docs/features.md) |
| como está montado, e por quê | [`docs/architecture-and-design.md`](docs/architecture-and-design.md) |
| o que ele deliberadamente **não** faz | [`docs/scope-and-constraints.md`](docs/scope-and-constraints.md) |
| tabelas, colunas e busca vetorial | [`docs/database.md`](docs/database.md) |
| as duas interfaces | [`docs/ui-ux.md`](docs/ui-ux.md) |
| o contexto do **produto** (escopo, requisitos, guia de engenharia, ADRs...) | tela **Contexto** do painel: mora no banco, não no repositório |
| para onde o projeto vai | [`docs/roadmap.md`](docs/roadmap.md) |
| fluxo de ramos e entrega | [`docs/entrega-no-pase.md`](docs/entrega-no-pase.md) |

As especificações originais, escritas antes da primeira linha de código, estão em
[`docs/historico-specs/`](docs/historico-specs/). Elas descrevem o que foi *planejado* -
a distância entre elas e o `STATUS.md` é resultado do trabalho, não defeito dele.

## Subida

Requer Docker Desktop. GNU `make` é opcional - cada alvo tem um `docker compose`
equivalente logo abaixo.

```bash
cp .env.example .env     # preencha LLM_API_KEY
make up                  # sobe db + 4 serviços e espera todos ficarem healthy
make seed                # popula o FinTrack e o baseline do PASE
```

**Sobre a chave de API.** Nenhum componente depende da Anthropic: todo acesso a LLM passa
por `pase-core/app/common/llm_client.py`, que aceita `openai`, `anthropic` ou `mock`. Com
uma chave OpenAI apenas, use o perfil comentado no `.env.example`. Sem chave nenhuma, o
perfil `mock` sobe tudo e roda os testes - só as demos precisam de modelo real.

| Serviço | URL | Papel |
|---|---|---|
| `pase-panel` | http://localhost:3000 | painel de controle humano |
| `client-frontend` | http://localhost:3001 | FinTrack, o app-alvo |
| `pase-core` | http://localhost:8000 | motor do PASE |
| `client-backend` | http://localhost:8001 | API do FinTrack |
| `db` | localhost:5432 | Postgres 16 + pgvector (`pase`/`pase`) |

## Comandos

| Make | Equivalente sem make |
|---|---|
| `make up` | `docker compose up -d --build --wait` |
| `make down` · `make logs` · `make ps` | `docker compose down` · `logs -f` · `ps` |
| `make seed` | `docker compose exec -T client-backend python -m app.seed` e o mesmo em `pase-core` |
| `make reset` | `down -v` + `up` + `seed` |
| `make test-core` · `make test-client` | `docker compose exec -T <serviço> pytest -q` |
| `make migrate` · `make migration m="..."` | `docker compose exec -T pase-core alembic upgrade head` / `revision --autogenerate` |
| `make lint` | `docker compose exec -T pase-core sh -c "cd /workspace/repo && ruff check pase-core client-backend"` |
| `make demos` | roda os oito roteiros em sequência |
| `make demo-d1` … `demo-d8` | `bash scripts/demo/dN.sh` |
| `make metrics` | baixa os três CSVs para `./metrics/` |

Os testes rodam num banco separado (`pase_test`), criado sob demanda - rodar a suíte não
apaga os dados da aplicação.

## Os oito roteiros de demonstração

Cada script anuncia o que espera antes de cada passo, para ser lido em voz alta enquanto
roda. Pré-requisito comum: `make reset && make seed`, e o seu trabalho commitado (d1 e d6
fazem merge de verdade na branch principal).

| Demo | O que prova | Resultado esperado |
|---|---|---|
| **d1** | evolução de código de ponta a ponta | proposta → aprovação → planejamento → execução → diff, logs e transcript → homologação → merge → endpoint novo respondendo 200 no app rodando |
| **d2** | Memória Histórica | pedido do que já existe vira `descartada_duplicata`; pedido fora de escopo vira `descartada_incoerente`; a mesma ideia reescrita é barrada pela memória de descartes |
| **d3** | geração por IA | Geração Exploratória e Análise de Lacunas produzem propostas que passam pelo mesmo funil - inclusive para serem recusadas |
| **d4** | personalização em runtime | 5 acessos a `/relatorios` disparam a regra; a Ana recebe um widget, a Clara continua no componente nativo; revogar restaura |
| **d5** | defesa em profundidade | três payloads maliciosos gravados **pulando** a validação do core são recusados pelo cliente; o dashboard permanece no nativo e três violações ficam registradas |
| **d6** | contenção da generatividade | duas falhas seguidas → `suspensa/retries`; teto de 100 tokens → `interrompida_budget` sem gastar nada |
| **d7** | Captação Passiva → Zona Dinâmica | tickets de suporte sobre a mesma dor, com saídas divergentes, viram uma tarefa com `output_type=zona_dinamica` |
| **d8** | jobs de manutenção | a auditoria lê o código e propõe uma melhoria; a reavaliação relê descartes e reintroduz o que deixou de ser incoerente |

**Reproduzir a d1 do zero.** Ela adiciona um endpoint de exportação ao client-backend e o
merge fica no histórico. Para rodá-la de novo, `make reset` (limpa a memória do PASE) e
`git revert -m 1 <commit do merge>` (devolve o código ao estado anterior) - senão o próprio
funil, corretamente, barrará o segundo pedido como duplicata.

## Métricas

`make metrics` baixa os três anexos do capítulo de validação:

- `tasks.csv` - uma linha por tarefa, com o agregado das execuções
- `discards.csv` - uma linha por descarte, com motivo e contador de recorrência
- `violations.csv` - uma linha por payload que o cliente recusou renderizar

As três medidas citadas na conclusão da monografia saem de `tasks.csv`:

| Medida | Como calcular |
|---|---|
| taxa de intervenção humana | proporção de `ajustar`/`recusar` sobre o total que chegou à Homologação |
| densidade de retrabalho | média da coluna `runs` entre as tarefas finalizadas |
| incidência de regressões | tarefas com `retries > 0` cuja run anterior havia passado - use a aba Execuções do painel, ou a tabela `execution_runs`, para o caso a caso |

Uma ressalva honesta sobre a terceira: `tasks.csv` guarda o agregado, não o status de cada
run. Para afirmar "o teste passou numa run e falhou na seguinte" é preciso olhar
`execution_runs`, que o painel exibe por tarefa.

## Fora de escopo, por decisão

Autenticação real, multi-tenancy, CI, Alembic, PR remoto no GitHub, Langfuse, LangGraph como
dependência formal, RBAC real, sub-DAGs, replanejamento automático, prospecção competitiva,
múltiplas zonas simultâneas e geração de componentes React em runtime.

A lista completa, com a justificativa de cada item, está em
[`docs/scope-and-constraints.md`](docs/scope-and-constraints.md) - é a referência para citar
no TCC. Nenhum item de lá deve ser implementado sem pedido explícito.
