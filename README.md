# PASE - Personalized Adaptive Software Ecosystem

**Atharv Nuthi** · **Felipe Vahia Malliagros**

Prova de conceito do Trabalho de Conclusão de Curso *Arquitetura PASE: autonomia
supervisionada com agentes de IA no ciclo de vida de software, a partir de uma análise
multidimensional do ecossistema* (Universidade Federal Fluminense, Instituto de Computação,
2026; orientador: Prof. Troy Costa Kohwalter).

A ideia: deixar agentes de IA fazerem o máximo do ciclo de vida de um software, com uma
pessoa decidindo onde a decisão tem consequência, e com tudo que dá para conferir por código
conferido por código.

O repositório tem dois sistemas, e é importante não confundi-los:

- **PASE** é o motor. Recebe demandas de várias origens, filtra com IA, prioriza, executa
  mudanças de código sob aprovação humana, entrega a versão por *pull request* e personaliza a
  interface em tempo de execução.
- **FinTrack** é o produto de exemplo que o PASE evolui: um painel financeiro pessoal com seis
  telas e duas personas fictícias, Ana e Clara, com dados sintéticos.

## Como o PASE está organizado

| Camada | O que faz | Código |
|---|---|---|
| Tarefas | transforma texto bruto em tarefa candidata: normalização, avaliação de zona, memória histórica, coerência com o contexto e qualificação | `pase-core/app/task_layer` |
| Orquestração | prioriza, monta o grafo de dependências, aplica as decisões humanas, trata falhas e custo, e entrega em estágios | `pase-core/app/orchestration`, `pase-core/app/jobs` |
| Execução | planeja e depois escreve o código em clone isolado, verifica e passa por revisão independente | `pase-core/app/execution` |
| UPA e Zonas Dinâmicas | personaliza preenchendo propriedades de componentes que já existem, sem gerar código | `pase-core/app/upa`, `client-frontend/dynamic-zones` |

O painel de quem decide está em `pase-panel`; o FinTrack, em `client-backend` e
`client-frontend`. O contrato das Zonas Dinâmicas é um único JSON Schema, em
`docs/contracts/zona.schema.json`, e os quinze *prompts* ficam um por arquivo em
`pase-core/app/prompts`.

A regra que atravessa o projeto: garantia que depende só de instrução ao modelo não é
garantia. O modelo aponta a evidência e o código confere. Por isso a citação da Coerência
Sistêmica, a preservação dos testes existentes, a fronteira de escrita do Executor, a trava
de custo e a validação das zonas são código.

## Comece por aqui

```bash
git clone https://github.com/atharvnuthi/pase-poc.git && cd pase-poc
cp .env.example .env          # coloque a sua chave da OpenAI em LLM_API_KEY
docker compose up -d --build --wait
docker compose exec -T client-backend python -m app.seed
docker compose exec -T pase-core python -m app.seed
```

Painel em http://localhost:3000, FinTrack em http://localhost:3001. O **[SETUP.md](SETUP.md)**
tem o passo a passo completo: rodar sem chave, usar só o painel com o seu software, pôr
Zonas Dinâmicas no seu app, rodar os testes e adaptar o Executor ao seu produto.

## Evidência da validação

O histórico do repositório guarda a cadeia descrita no Capítulo 6 da monografia:

| Commit | O que é |
|---|---|
| `19968db` | estado inicial: FinTrack e PASE prontos, com 15 funcionalidades implementadas e 4 propostas recusadas na memória |
| `340d910` | modo escuro do FinTrack, escrito pelo Executor do PASE (tarefa nº 1) |
| `f61cded` | integração da tarefa no ramo `develop`, após homologação |
| `8b783b5` | versão 1.0.0, publicada pelo *merge* do pull request nº 3 |

Os commits `340d910` e `f61cded` têm como autor o próprio sistema (`PASE Bot` e `PASE`), e o
`8b783b5` é o *merge* feito no GitHub. O commit seguinte prepara o repositório para
publicação e reúne duas correções feitas depois da release (o catálogo de *prompts* da tela
Sistema passou a listar os quinze, e uma violação recusada pelo cliente passou a ser
registrada uma vez só). Os pull requests nº 1 e nº 2 foram abertos por uma execução da suíte
de testes contra o GitHub real, antes de ela ser isolada (hoje o token é zerado em todo
teste), e não fazem parte da validação. Por isso o `#1` no corpo do PR nº 3 aparece como
link para eles: ali ele significa a tarefa nº 1 do PASE.

## O que fica fora desta prova de conceito

Prospecção competitiva e recompensa por contribuição; pesos e limiares automáticos no grafo
de dependências, subgrafos, replanejamento automático e resolução automática de conflitos de
integração; contêiner efêmero com rede bloqueada (o isolamento atual é clone, ramo exclusivo
e ambiente sem credenciais, não isolamento de rede) e ambiente temporário de visualização;
gatilhos de frustração, zonas sob demanda conversacionais, barramento de eventos entre
zonas e fluxos de múltiplas etapas. Também não há autenticação, múltiplos papéis nem
*multi-tenancy*.

## Para quem vai mexer no código

- Código e identificadores em inglês; interface, *prompts* e commits em português.
- Commits no formato `<tipo>(<escopo>): descrição`, com tipo em `feature`, `fix`,
  `refactor`, `docs`, `test` ou `chore`.
- Toda chamada a modelo passa por `pase-core/app/common/llm_client.py`, e todo SQL vetorial
  fica em `pase-core/app/common/vector_store.py`. *Prompts* nunca ficam embutidos no código.
- No `pase-core`, toda mudança de esquema é uma migração Alembic, e `create_all` só existe na
  suíte de testes. O `client-backend` cria suas tabelas com SQLModel no boot.
- As branches `feature/pase-{id}-{slug}` e `hotfix/...` são do Executor e nunca são editadas à
  mão; só `release/x.x.x` chega à principal, por pull request e aprovação humana.
- Comentários que citam `SPEC-nn` apontam para as especificações originais, escritas antes do
  código. Elas descrevem o que foi planejado, não o que existe, e ficam no histórico:
  `git show 19968db:docs/historico-specs/SPEC-05-upa-zonas.md`.

## Licença

MIT. Veja o arquivo `LICENSE`.
