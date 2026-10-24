# Plano de Evolução

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros
**Escrito em:** 22 de setembro de 2026, depois de levantar o estado real do código.

O que existe hoje prova o modelo PASE de ponta a ponta. O que está aqui é o que falta para
ele deixar de ser uma prova e virar uma ferramenta que dá vontade de usar.

---

## 1. Diagnóstico: cinco limitações, não vinte pedidos

A lista de incômodos é longa, mas as causas são poucas. Vale atacar as causas.

### L1 - Não existe migração de esquema

O banco nasce com `create_all` no boot. Acrescentar uma coluna exige zerar tudo.

Isto **bloqueia metade do resto**: grafo de dependências precisa de tabela de arestas, PR
real precisa de `pr_url`, etiquetas precisam de tabela própria. Já custou caro uma vez -
para reverter um merge tive de **procurar o commit pela mensagem no `git log`**, porque não
havia onde guardar o SHA.

É a primeira coisa a fazer, e é a menos glamourosa.

### L2 - O que não é código é desejo

A lição mais cara deste projeto, medida cinco vezes: o Executor sobrescreveu um teste, o P9
confabulou, o budget deixou passar, a fronteira dependia de boa vontade, e o `next build`
não existia. Em todos, a correção foi a mesma - **tirar a garantia do prompt e pôr no
código**.

Agora o mesmo padrão outra vez. O P5 diz, com todas as letras: *"Acrescente testes novos
para o comportamento novo."* **Nada verifica isso.** Uma tarefa pode adicionar cem linhas
de comportamento e zero testes, e passar.

### L3 - O Executor escreve código sem conhecer a casa

Ele recebe a árvore de arquivos e o roadmap. Não recebe: as convenções de commit e branch,
quais bibliotecas pode usar, o que é proibido, qual o padrão de erro, como se nomeia um
componente.

Não é hipótese. Na entrega de modo escuro ele escreveu `fetch("/theme?...")` na mão -
enquanto `lib/api.ts`, **dentro do contexto que ele recebeu**, já tinha o helper certo.
Ninguém disse a ele que existe um jeito de fazer as coisas aqui.

### L4 - A tarefa é um trilho, não um objeto

Dá para aprovar, ajustar, recusar e (desde ontem) reverter. Não dá para: editar o título ou
o escopo, refazer só o planejamento, corrigir o plano antes de executar, marcar dependência
entre duas tarefas na mão, ou reordenar.

E "dependência" hoje é `waiting_on_task_id` - **um escalar**, derivado de sobreposição de
arquivos, calculado uma vez no despacho. Isso é um mutex, não um grafo. Não há arestas para
desenhar.

### L5 - O painel mostra tarefas, não o sistema

Não há tela que responda "como está o motor?": quantos vetores na memória, quais prompts
existem, quanto se gastou, o que está na fila. E as etiquetas (`risco alto`, `incerteza`,
`zona dinâmica`, `budget`) são jargão sem legenda.

---

## 2. Respostas diretas

### `scripts/demo/` - manter

**Não remover.** São 482 linhas que constituem a Definition of Done do projeto e a evidência
do capítulo de validação: cada roteiro prova uma propriedade do modelo. Apagá-los apagaria a
prova.

O que eles têm de ruim é serem bash - frágil no Windows, difícil de rodar em CI. Proposta
para depois, não agora: **promover d1–d8 a uma suíte `tests/e2e/` em pytest**, que roda no
CI, e manter os `.sh` só como narração para a defesa. Fica registrado, não entra nas
primeiras fases.

### O esquema do banco - bom no desenho, incompleto para o que vem

O desenho central está certo: a cadeia `proposals → tasks → planning_documents →
execution_runs → implemented_items` cobre a rastreabilidade integral, e separar memória de
implementadas, candidatas e descartadas preserva a proveniência. Isso não muda.

O que falta:

| Falta | Para quê | Onde |
|---|---|---|
| **Migrações** | tudo abaixo | L1 |
| `task_dependencies(from, to, kind, created_by)` | o grafo; hoje é um escalar | L4 |
| `tasks.merge_commit`, `tasks.pr_url`, `tasks.pr_number` | reverter sem grepar o `git log`; PR real | L1 |
| `tasks.branch_name` conforme convenção | `feature/…` em vez de `pase/task-N` | §4 |
| `labels` + `task_labels` | classificação e a legenda do painel | L5 |
| Índice vetorial (`ivfflat`/`hnsw`) | hoje toda busca é **varredura sequencial** - irrelevante com 12 linhas, não com 12 mil | escala |
| `llm_calls.cost_usd` | custo em dinheiro, não só em tokens, para o capítulo de validação | métricas |

Nada disso é reescrita. É acréscimo - desde que L1 seja resolvido primeiro.

---

## 3. O plano, em fases

Cada fase existe onde está porque **destrava a seguinte**. A ordem não é de importância, é
de dependência.

### Fase 0 - Fundação ✅ **concluída**

Barata, sem brilho, e sem ela o resto não acontece.

1. **Alembic.** Migração inicial capturando o esquema atual; daí em diante toda mudança é
   uma revisão versionada. `make reset` continua existindo, mas deixa de ser o único jeito
   de mudar uma coluna.
2. **`engineering-guidelines`** (hoje um documento do contexto, no banco) - o livro de regras que hoje não existe. Conteúdo:
   - stack e versões fixas; **bibliotecas permitidas e proibidas** (por exemplo: nada de
     `axios`, use o `request` de `lib/api.ts`; nada de `moment`, use `Intl`)
   - convenção de commit e de branch (§4)
   - padrões do backend: erro 422 por campo, `Decimal` para dinheiro, nunca `float`
   - padrões do frontend: **sempre** usar as primitivas de `components/ui.tsx`; **sempre**
     usar o cliente de `lib/api.ts` em vez de `fetch` cru; `"use client"` em tudo que tem
     hook; `app/layout.tsx` é Server Component e continua sendo
   - o que é somente leitura para o agente e por quê
3. **Injetar o livro de regras no P4 e no P5.** Hoje eles não o recebem porque ele não
   existe.
4. **Alinhar as convenções** com o padrão de vocês (§4), inclusive no CLAUDE.md.

### Fase 1 - Código que funciona, verificado ✅ **concluída**

O pedido "a IA precisa gerar código que funcione" traduzido em hooks determinísticos.

1. **Teste novo é obrigatório para comportamento novo.** Espelha o
   `rede_de_regressao_intacta` que já existe: se o diff toca arquivo de código que não é
   teste, o inventário de testes **tem de crescer**. Não cresceu, run reprovada com motivo.
   Pedir no prompt já se provou insuficiente - está lá desde sempre e não aconteceu.
2. **Cobertura do que mudou.** `pytest --cov` e `vitest --coverage` restritos aos arquivos
   tocados: a cobertura deles não pode cair. Impede o truque de acrescentar um teste
   trivial só para satisfazer o item anterior.
3. **Convenção verificada por código.** Nome de branch e formato da mensagem de commit
   conferidos por regex antes do commit da run, não pedidos no prompt.
4. **Smoke de runtime.** `next build` já entrou. Falta o equivalente do backend: subir o app
   e bater em `/health` dentro do clone. Compilar não é o mesmo que iniciar.

### Fase 2 - A tarefa como objeto vivo ✅ **concluída**

1. **`task_dependencies`** substituindo o escalar. Três origens de aresta:
   - `arquivo` - detectada como hoje, por sobreposição de `affected_files`
   - `semantica` - proposta pelo planejamento ("isto depende da API da tarefa #7")
   - `manual` - criada por você no painel
2. **Ações por fase**: replanejar sem reexecutar, reexecutar sem replanejar, **editar o
   Documento de Planejamento antes do despacho**. Hoje o plano é imutável e só resta
   aprovar ou recusar o que veio depois dele.
3. **Editar a tarefa**: título, descrição, módulo, risco, prioridade.
4. **Cancelar em andamento** - hoje uma run só termina sozinha.

### Fase 3 - O painel que mostra o sistema ✅ **concluída**

Depende da Fase 2: sem arestas não há grafo.

1. **Grafo ao vivo.** Nós são tarefas, coloridos por estado; arestas são as dependências.
   Atualiza pelo SSE que já existe. Clicar num nó abre o dossiê: plano, runs, diff,
   transcript, custo. Biblioteca: avaliar `@xyflow/react` (React Flow) - maduro, sem
   servidor, combina com Next.
2. **Tela Sistema.** O motor, não as tarefas: contagem e saúde da memória vetorial por tipo,
   os 13 prompts com suas temperaturas e quando cada um roda, custo acumulado em tokens e em
   dólares, fila e travas, saúde dos cinco serviços.
3. **Glossário.** Toda etiqueta (`risco alto`, `incerteza`, `zona dinâmica`, `duplicata`,
   `budget`, `retries`, `merge_conflict`, cada estado) com o que significa, quem a atribui e
   o que ela muda no comportamento do sistema. Acessível de qualquer lugar - a própria
   etiqueta vira o link.
4. **Reforma visual** do painel, com o mesmo rigor da que o FinTrack recebeu: tokens,
   primitivas, densidade adequada a uma ferramenta de decisão.

### Fase 4 - Contexto conversável ✅ **concluída**

O contexto do produto é a régua que decide o que entra no produto. Hoje o painel só o
mostra.

1. **Editar pelo painel**, com o diff visível antes de salvar e um commit próprio no git -
   toda alteração de escopo continua rastreável.
2. **Propor por conversa.** Você descreve a mudança em linguagem natural; o modelo devolve
   **um diff proposto**, nunca uma escrita direta. Você aprova ou recusa.
3. **Efeito colateral explícito.** Ao salvar, o sistema mostra quais descartes deixariam de
   ser válidos e oferece rodar a Reavaliação Cíclica na hora.

> A regra de que a IA não escreve o próprio contexto **não é violada**: ela propõe, um
> humano aprova, e o commit é do humano. Automatizar a escrita do documento que julga
> coerência criaria um sistema que valida as próprias decisões contra um texto que ele mesmo
> reescreveu.

### Fase 5 - GitHub de verdade ◐ **código pronto, nunca exercitado**

> O caminho está construído e testado contra um transporte de mentira: abrir PR,
> reaproveitar PR existente, ler checks, mergear pelo PR. **Falta o token.** Sem
> `GITHUB_TOKEN` e `GITHUB_REPO` a integração fica inerte e tudo segue local, que é
> o padrão. Nada disto foi exercitado contra o GitHub real - quando o token existir,
> a primeira execução é que vai dizer se está certo.

O remoto já existe (`atharvnuthi/pase-poc`). Falta o resto.

1. **PR real** em vez de merge local: a run abre PR, o painel mostra estado e checks, a
   Homologação vira o merge do PR.
2. **CI no GitHub Actions** rodando exatamente os mesmos gates da Fase 1 - o que o Executor
   verifica no clone é o que o CI verifica no PR.
3. **Multi-branch** conforme §4, com `main` protegida.

Esta fase muda o modelo de confiança (passa a haver segredo de API e escrita em serviço
externo) e por isso fica por último, quando tudo abaixo estiver firme.

---

### Fase 6 - Entrega controlada ✅ **concluída** (8 de outubro de 2026)

O que motivou: uma tarefa de modo escuro passou em todos os gates sem fazer nada; uma de
exportação em CSV gastou 486 mil tokens sem convergir; e aprovar na Homologação já era
publicar. Três respostas:

1. **A entrega precisa fazer o que foi pedido, não só compilar.** Critérios de aceite no
   planejamento, revisão independente por outro modelo com evidência conferida por código,
   modelos de código e de revisão separados (`gpt-5.3-codex` e `gpt-5.5`).
2. **Uma pessoa decide antes de gastar.** Aprovação do plano (`aguardando_plano`), por risco
   ou por escolha; aprovar, devolver com feedback ou editar. Refazer uma tarefa leva o
   porquê da anterior.
3. **Publicar é outra decisão.** O fluxo do [guia de ramos](entrega-no-pase.md): Homologação
   integra na `develop`, aprovação funcional, release, validação final, PR, publicação com
   tag.

Duas falhas do próprio sistema foram achadas e corrigidas no caminho: o inventário de testes
"antes" lido do disco de um clone sujo, e colateral cosmético reprovando a revisão.

**Fica para depois:** proteção de branches no repositório remoto, e um CI de verdade fora do
PASE (GitHub Actions) que substitua a validação local.

---

## 4. Convenções: conflito a resolver

O padrão de vocês e o do repositório **não batem hoje**:

| | Padrão de vocês | Repositório hoje |
|---|---|---|
| Commit | `feature: descrição` | `feat(scope): descrição` |
| Branch de trabalho | `feature/<nome>` | `pase/task-{id}` |
| Principal | `main` | `master` |

Recomendação:

- **Adotar o padrão de vocês** para o tipo (`feature`, `fix`, `refactor`, `docs`, `test`,
  `chore`), porque é o que a equipe combinou e está documentado.
- **Manter o escopo entre parênteses** como opcional - o próprio exemplo de vocês traz
  `feature(login):`, e ele ajuda muito num monorepo.
- **Branch do Executor: `feature/pase-{id}-{slug}`.** Conforma com a convenção, mantém o
  `{id}` que liga a branch à tarefa, e o prefixo `pase-` preserva o sinal de "esta branch é
  do robô, não edite na mão" - que hoje é uma regra do CLAUDE.md e continuaria valendo. O
  tipo vem da tarefa: `fix/pase-12-...` para correção, `chore/pase-13-...` para engenharia.
- **`master` → `main`** junto com a Fase 5, quando houver PR e proteção de branch. Renomear
  antes disso é churn sem ganho.

---

## 5. O que eu deliberadamente não faria

- **Sub-DAGs e replanejamento automático em cascata.** Estão no escopo futuro por um bom
  motivo: a complexidade explode e nenhuma das duas coisas é necessária para a tese.
- **Migrar para LangGraph.** As etapas encadeadas em Python são mais fáceis de depurar e já
  provam o modelo. Trocar por um framework é engenharia, não argumento.
- **Múltiplas zonas dinâmicas antes da Fase 3** (feito depois, de forma contida: seis zonas,
  uma por tela, mesmo contrato e mesmo catálogo, com cooldown de custo).
- **Autenticação.** Continua sendo PoC local. Se a Fase 5 trouxer segredo de API, ele fica em
  variável de ambiente e o sistema **continua não sendo exposto**.

---

## 6. Ordem sugerida e por quê

```
Fase 0  Fundação          ✅ concluída  ← destrava tudo; sem Alembic o resto não tem onde morar
Fase 1  Gates de verdade  ✅ concluída  ← maior ganho por esforço: é o que faz a IA entregar código que presta
Fase 2  Tarefa viva       ✅ concluída  ← cria as arestas que a Fase 3 desenha
Fase 3  Painel do sistema ✅ concluída  ← depende dos dados das fases anteriores
Fase 4  Contexto          ✅ concluída  ← novo caminho de escrita na régua do sistema; exige cuidado
Fase 5  GitHub            ◐ código pronto, inerte sem token  ← dependência externa e mudança no modelo de confiança
```

Se houvesse tempo para só duas: **0 e 1**. São elas que atacam "a IA precisa gerar código
que funciona", que é o problema que mais dói e o que mais fortalece a tese - porque o
argumento do trabalho é justamente que **autonomia só é aceitável na medida da verificação
automática**.
