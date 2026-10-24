# CLAUDE.md

**Autores do projeto:** Atharv Nuthi · Felipe Vahia Malliagros

Este arquivo é lido no início de toda sessão. Mantenha-o curto: só o que um novo colaborador (humano ou agente) precisa saber no primeiro dia. Atualize sempre que um erro se repetir.

## O que é este projeto

PASE (Personalized Adaptive Software Ecosystem) é o objeto do TCC. É um sistema que recebe demandas de várias origens, filtra com IA, prioriza, executa mudanças de código de forma autônoma sob aprovação humana, e personaliza a interface em runtime. O FinTrack é o produto-alvo que o PASE evolui - um dashboard financeiro simples. O PASE-core é o motor. Nunca confundir os dois: o FinTrack é o "paciente", o PASE é o "sistema".

Documentação em vigor, conferida contra o código em execução:

- `docs/STATUS.md` - **o que existe e o que não existe**. Comece por aqui.
- `docs/features.md` · `docs/architecture-and-design.md` · `docs/database.md` · `docs/ui-ux.md`
- `docs/roadmap.md` - para onde o projeto vai, e o que já foi feito.
- `docs/scope-and-constraints.md` - as regras invioláveis e o que **não** implementar sem pedido explícito.
- `docs/entrega-no-pase.md` - como o fluxo de ramos (git guide) é aplicado pelo sistema.

**O contexto do FinTrack mora no banco, não no repositório.** Escopo, requisitos, funcionalidades, arquitetura, banco, UI/UX, guia de engenharia, padrões, segurança, infraestrutura, git guide, ADRs e design systems são documentos da tabela `context_documents`, editados na tela **Contexto** do painel (cada edição é uma versão). Cada etapa do ciclo lê só o que precisa (`context_store.LEITURAS`). O conteúdo inicial vem de `pase-core/app/context_seed/`, usado só quando o banco não tem o documento. `make reset` preserva as edições (exporta e reimporta); `make reset-all` volta ao conteúdo inicial. Os `docs/*.md` que sobraram descrevem o **PASE**, não o FinTrack.

`docs/historico-specs/` guarda as especificações originais. Elas descrevem o que foi *planejado*, não o que existe - não implemente com base nelas.

## Comandos

```
make up            # sobe os 5 serviços via docker-compose
make down
make logs
make seed          # popula FinTrack + baseline do PASE (implemented_items, descartes históricos)
make reset          # down -v && up && aguarda health && seed
make test-core     # pytest do pase-core
make test-client   # pytest do client-backend
make demo-d1        # ... make demo-d8, ver docs/features.md §8
```

Nenhum comando de build/deploy real além destes. Não existe CI neste estágio (ver `docs/scope-and-constraints.md`).

## Convenções

- Código e identificadores em inglês. UI, prompts, docs e commits em português (pt-BR).
- Commits: `<tipo>(<escopo opcional>): descrição`, com tipo em `feature`, `fix`, `refactor`, `docs`, `test`, `chore`. Escopo = nome da pasta. **Conferido por código** em `commit_all`.
- Branches do Executor: `feature/pase-{id}-{slug}` (correção vira `hotfix/`), exclusivas dele, nunca editadas manualmente.
- **Fluxo de ramos: documento `git-guide` do contexto**, aplicado por `pipeline_rules.py`. `feature`/`hotfix` nunca vão direto à principal; aprovar na Homologação integra na `develop`; só `release/x.x.x` chega à principal, por PR e aprovação humana. Nunca crie branch de trabalho a partir da `develop`.
- Toda mudança de esquema é migração Alembic (`make migration m="..."`). `create_all` só na suíte de testes.
- **Regras de como escrever código: documento `engineering-guidelines` do contexto** - lido por humanos e injetado no P4, no P5 e no P12.
- Lint: `ruff` (Python), `eslint`/`prettier` (TypeScript). Rodar antes de todo commit.
- Toda chamada a LLM passa por `pase-core/app/common/llm_client.py`. Nunca chamar o provider diretamente de outro módulo.
- Todo SQL vetorial vive em `pase-core/app/common/vector_store.py`.
- Prompts versionados em `pase-core/app/prompts/`, um arquivo por prompt (P1.md, P2.md...), nunca inline no código Python.
- CORS liberado só para `localhost:3000` e `localhost:3001`. Sem autenticação. Isto é uma PoC local, nunca exposta publicamente - não adicionar auth "por precaução".

## Arquitetura em uma frase por camada

- **Task Layer**: transforma texto bruto em tarefa candidata qualificada, via normalização → avaliação de zona → memória → coerência → qualificação.
- **Orchestration Layer**: prioriza, monta o DAG de dependências, aplica gates humanos, trata falhas e budget.
- **Execution Layer**: planeja (mapeia arquivos, estima custo) e executa (escreve código em sandbox, testa, abre PR) em duas fases separadas.
- **UPA + Zonas Dinâmicas**: personaliza em runtime preenchendo propriedades validadas de componentes que já existem - nunca gera código executável.

## Erros que já aconteceram (atualizar conforme acontecem)

- Conexão a um Postgres fora do ar pendurava o processo por minutos no Windows - todo `create_engine`/`psycopg.connect` leva `connect_timeout` (`settings.db_connect_timeout`).
- `COPY ../algo` não funciona em Dockerfile: o contexto de build do `pase-core` é a **raiz** do monorepo (ver `docker-compose.yml`), porque ele precisa do `client-backend/requirements.txt`.
- Bind mount `./app:/app` em serviço Node apaga o `node_modules` da imagem - os dois serviços Next levam um volume anônimo em `/app/node_modules`.
- Healthcheck com `localhost` falha dentro do container: `localhost` resolve só para `::1` e o Next escuta em IPv4. Usar sempre `127.0.0.1` em healthcheck.
- `ruff` rodado de `/app` ignora o `ruff.toml` da raiz e aplica outro conjunto de regras - o alvo `lint` roda com `-w /workspace/repo`.
- `SIMILARITY_THRESHOLD=0.85` do SPEC-01 §4 fica **acima de todos os positivos** do `text-embedding-3-small`: com ele a Memória Histórica nunca barra nada. Calibrado por medição para 0.72 (positivos 0.69–0.90, negativos ≤0.65).
- Embedding não separa tema em texto curto e coloquial - tickets sobre a mesma dor ficaram em 0.47–0.61, abaixo de pares de temas diferentes. Agrupamento de tickets é feito pelo modelo (P0a), não por cosseno.
- Nunca dar `TRUNCATE` numa tabela que o `llm_client` escreve dentro da mesma transação que depois chama LLM: o lock exclusivo trava a conexão separada do `_record` e o processo congela. `llm_calls` ficou fora do wipe do seed.
- O `wipe` do seed com `session.delete()` linha a linha deixava o ORM escolher a ordem e batia na FK de `tasks`→`proposals`. Usar `TRUNCATE ... RESTART IDENTITY CASCADE`.
- Pedir veredito booleano ao LLM sobre "isto ainda consta no documento?" produz confabulação: ele lê a citação dentro do próprio texto sob julgamento, ou cola a seção inteira. O modelo aponta a evidência, o **código** confere e decide (ver `reevaluation.evidencia_confere`).
- O Executor **sobrescreveu um teste existente** na primeira execução real, e a verificação passou porque rodou a suíte adulterada. Pedir ao modelo não basta: o inventário de testes é tirado do clone intacto e conferido por código (`executor.rede_de_regressao_intacta`).
- Transição de estado longa tem que ser commitada **antes** do trabalho, não junto: marcar `em_execucao` dentro da mesma transação da run deixava o status invisível a outras conexões por minutos, e a checagem de conflito de arquivos nunca via tarefa em andamento.
- `tokens_estimated` do P4 erra por ordem de grandeza (estimou 1200 para uma tarefa de 25 mil). Serve como artefato de planejamento, nunca como teto sozinho - daí o `BUDGET_MIN_TOKENS`.
- Teste que limpa tabela tem que rodar em banco separado (`pase_test`). A suíte estava apagando tarefas reais do banco da aplicação a cada `make test-core`.
- Dependência nova no `package.json` não chega ao container só com `--build`: o volume anônimo de `node_modules` é do build anterior e sombreia o novo. Usar `docker compose up -d --force-recreate --renew-anon-volumes <serviço>`.
- `make reset` zera o banco e os ids das tarefas recomeçam do 1, mas não apaga as branches `pase/task-*`. A primeira execução de uma tarefa recria a branch a partir da principal; o reset também apaga as antigas.
- `make reset` **não** reverte o código que o PASE já mergeou. Para repetir a d1, é preciso `git revert -m 1` do merge antes - senão o Executor não tem o que escrever e o diff sai vazio.
- Deixar o modelo consertar o que o formatador conserta é desperdício: numa d1 real os 11 testes passaram, o ruff reprovou por ordem de import, e o ciclo gastou 51 mil tokens sem resolver. A verificação roda `ruff check --fix` antes de `ruff check`.
- `curl -d` no Windows corrompe acentos no corpo. Nos scripts, o JSON vai por stdin com `--data-binary @-`.
- Python embutido em heredoc de bash acumula três níveis de escape e quebra em silêncio. Script com regex vai em arquivo próprio (ver `scripts/demo/_rota.py`).
- O Executor clona a **branch principal**: rede de regressão não commitada não existe dentro do clone. Teste novo do alvo só protege depois do commit.
- `require()` dentro de mock ESM do vitest pendura o runner **em silêncio**, sem erro e sem timeout. Importar no topo do arquivo.
- Teste que importa `vitest.setup.ts` é avaliado duas vezes por causa do hoisting do `vi.mock` e trava antes da coleta. Os spies vivem em módulo próprio (`tests/_mocks.ts`).
- `useRouter()` mockado devolvendo objeto novo a cada render faz o `useEffect([router])` do `usePersona` rodar para sempre. O mock devolve sempre a **mesma** referência.
- `docker compose exec -w /caminho` no Git Bash do Windows falha com `Cwd must be an absolute path`: o MSYS reescreve o caminho. Usar `MSYS_NO_PATHCONV=1`.
- Bind mount do Docker Desktop no Windows não entrega evento de inotify para dentro do container: nenhum watcher percebe arquivo salvo no host. Sintoma: log só com `GET` rápido, sem `Compiling` nem `Reloading`. Resolvido com polling no `docker-compose.yml` - `WATCHFILES_FORCE_POLLING` (uvicorn) e `WATCHPACK_POLLING` (Next).
- Ligar o polling sozinho **pendura o pase-core**: o painel mantém um SSE aberto em `/api/events/stream` e o uvicorn espera as conexões fecharem antes de reiniciar - stream não fecha. Ficava parado em `Waiting for connections to close` e a API inteira parava. Vai junto `--timeout-graceful-shutdown 5`.
- `.gitignore` com `node_modules/` (com barra) casa só com diretório. O symlink que o gate do frontend cria é um blob (modo 120000), escapa do padrão, e entrou no diff que foi para a Homologação. O gate desfaz o symlink num `finally`, e o padrão perdeu a barra.
- Recusar uma tarefa na Homologação **não** atualiza o embedding `candidata` da proposta que a originou: reenviar a mesma demanda volta barrada como "aguardando avaliação", o que é falso. Memória de curto prazo do funil e estado da tarefa saem de sincronia na recusa.

- `tsc` e `vitest` **não** pegam erro de React Server Component: a fronteira `"use client"` é regra do compilador do Next, e o vitest renderiza páginas no jsdom sem passar pelo App Router - `app/layout.tsx` não é coberto por teste nenhum. Uma entrega com `useState` no layout raiz passou nos dois com exit 0 e quebrou o app inteiro. Quem pega é `next build`, que entrou no gate.
- `next dev` compila a rota só quando alguém a pede. Erro de compilação numa rota que o Executor não abre espera por um humano. Verificação de frontend precisa de build completo, não de servidor de dev.
- Reverter um merge na unha conserta o código mas **não** o sistema: a tarefa continua `aprovada` e o item segue em `implemented_items`, então pedir a mesma coisa de novo volta barrado como duplicata. Usar `POST /api/tasks/{id}/revert`, que desfaz as três coisas juntas.

- `create_all` **nunca altera** tabela existente: um banco de teste reaproveitado guarda o esquema do dia em que nasceu, e uma coluna nova quebra a suíte inteira enquanto a aplicação roda bem. O banco de teste é recriado a cada sessão.
- Banco montado por `create_all` já está em `head` - carimbá-lo é obrigatório, senão quem chamar `migrar()` depois acha que ele é anterior às migrações e tenta aplicar tudo de novo.
- Sinal que acende sempre deixa de ser sinal: arquivo de teste não conta como desvio do plano, porque acrescentar teste passou a ser obrigatório.

- A Memória Histórica indexa `candidata` como `proposals WHERE outcome = 'candidata'`, e **nada fechava a proposta** quando a tarefa acabava: toda demanda já decidida seguia lembrada como "aguardando avaliação". Aprovar, recusar e reverter agora chamam `homologation.encerrar_proposta`.
- Substituir `httpx.Client` por um lambda que chama `httpx.Client` faz o dublê chamar a si mesmo até estourar a pilha. Guardar a classe real antes do monkeypatch (ver `tests/test_github.py`).
- `session.delete()` sem `flush()` deixa a linha visível para a consulta seguinte na mesma sessão.
- Rebuild de imagem recria o container e mata o `pytest` que estava rodando nele. Não encadear as duas coisas em paralelo.
- **Duas execuções da suíte ao mesmo tempo se matam**: o `conftest` recria o banco de teste e dá `pg_terminate_backend` nas conexões dele, então a segunda derruba a primeira com `AdminShutdown`. Sintoma: dezenas de `ERROR` e `PendingRollbackError` sem nenhuma causa aparente no código. Rodar `make test-core` uma vez de cada vez.
- Gerar código com script Python que escapa barra-n produz quebra de linha real no arquivo e literal não terminado. Aconteceu três vezes nesta sessão, em TS e em Python. Para escrever código, usar a ferramenta de edição direta, não script com escape.

- Checagem de budget **retrospectiva** ("o gasto ainda não passou do teto") não diz que a execução consegue começar: com 35.592 de folga e chamadas de ~37.000, duas retomadas morreram em 7s com zero tokens. O guardrail do Executor sempre foi preditivo; o botão Retomar não era. Toda decisão sobre orçamento compara com o **custo da próxima chamada**, medido pelas chamadas anteriores da tarefa (`budget.cabe_mais_uma_chamada`).
- `.next/` corrompido depois de rodar `next build` num serviço que roda `next dev` dá `MODULE_NOT_FOUND` no boot. Apagar a pasta e subir de novo.

- Inventário de testes "antes" lido do disco de um clone reaproveitado inclui os testes da tentativa que falhou: nenhum teste novo conta como novo, e uma entrega com três foi reprovada quatro vezes. O "antes" vem do git (a principal), e o clone reaproveitado leva `reset --hard` + `clean`.
- Revisão que reprova por qualquer colateral queima rodadas em aspas e docstring (4 rodadas, ~270 mil tokens, numa tarefa que cumpria os 5 critérios). O revisor classifica a gravidade: só o que muda comportamento bloqueia, o resto é aviso.
- Gates mecânicos verdes não provam que a tarefa funciona: o modo escuro pôs a classe `dark` no `body`, testou a classe e nunca definiu uma cor. Critérios de aceite + revisão independente com evidência conferida por código.
- `docker compose restart` **não** relê o `env_file`: o container continua com o `.env` antigo (o Executor rodou com o modelo antigo). Usar `up -d --force-recreate <serviço>`.
- Modelos de raciocínio da OpenAI (`gpt-5*`, `o*`) não aceitam `temperature`, e os `-codex` só existem na Responses API (404 no chat).
- Script Python em heredoc com `
` dentro de string produz quebra de linha real no arquivo - recorreu **quatro** vezes. Para texto com `
`, usar a ferramenta de edição, nunca o script. Conferir com `ast.parse` antes de seguir.
- Merge de entrega acontece num clone próprio (`/tmp/pase/delivery`), nunca na árvore de trabalho do repositório, que pode estar suja.
- O container do `pase-core` herda o `GITHUB_TOKEN` do `.env`, e a suíte rodou o fluxo de entrega contra o GitHub **de verdade**: subiu `main`, `release/1.0.0` e a tag, abriu e mergeou PRs no repositório real (PR não se apaga). A fixture `github_desligado` do `conftest` zera token e repositório em todo teste, e o `git_service` recusa push para URL de rede. Teste que precisa do GitHub usa token falso e transporte dublado.
- Migração criada como esqueleto vazio é aplicada pelo `--reload` assim que o arquivo existe, e o banco fica carimbado sem as colunas. Escreva a migração inteira antes de salvá-la na pasta, ou recrie o banco.

## O que este projeto NÃO faz (não implementar sem pedir)

- Autenticação real, múltiplos papéis de usuário, multi-tenancy.
- Geração de componentes React em runtime (Zonas Dinâmicas só preenchem props, nunca código).
- Sub-DAGs, replanejamento automático de tarefas dependentes.
- Prospecção competitiva via scraping externo.
- Qualquer chamada de rede de dentro do sandbox do Executor além do provider de LLM.
