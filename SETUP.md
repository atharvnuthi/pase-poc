# Como usar o PASE

Tudo roda em Docker. Escolha o que você quer fazer:

1. [Ver funcionando, sem chave](#1-ver-funcionando-sem-chave)
2. [Usar com um modelo de verdade](#2-usar-com-um-modelo-de-verdade)
3. [Alimentar o painel com qualquer software](#3-alimentar-o-painel-com-qualquer-software)
4. [Zonas Dinâmicas no seu app](#4-zonas-dinâmicas-no-seu-app)
5. [Evolução de código no seu produto](#5-evolução-de-código-no-seu-produto)
6. [Testes e roteiros](#6-testes-e-roteiros)
7. [Se algo der errado](#7-se-algo-der-errado)

Requisito único: **Docker com Compose v2** (Docker Desktop no Windows e no Mac). Não precisa
de `make`: todo comando abaixo é um `docker compose` simples.

## 1. Ver funcionando, sem chave

```bash
git clone https://github.com/atharvnuthi/pase-poc.git
cd pase-poc
cp .env.example .env
```

Abra o `.env` e troque `LLM_PROVIDER=openai` por `LLM_PROVIDER=mock` e
`EMBEDDING_PROVIDER=openai` por `EMBEDDING_PROVIDER=mock`. Depois:

```bash
docker compose up -d --build --wait      # a primeira vez demora: ele constrói as imagens
docker compose exec -T client-backend python -m app.seed
docker compose exec -T pase-core python -m app.seed
```

| Abra | O que é |
|---|---|
| http://localhost:3000 | o painel do PASE (quem decide) |
| http://localhost:3001 | o FinTrack, o app de exemplo (escolha a Ana ou a Clara) |
| http://localhost:8000/docs | a API do motor, documentada |

O modo `mock` serve para ver as telas e rodar os testes. As decisões do funil e do
Executor só fazem sentido com um modelo de verdade.

## 2. Usar com um modelo de verdade

No `.env`, volte para `LLM_PROVIDER=openai` e `EMBEDDING_PROVIDER=openai` e preencha
`LLM_API_KEY` com a sua chave da OpenAI. Aplique a mudança (`restart` não relê o `.env`):

```bash
docker compose up -d --force-recreate pase-core
```

Para ver o ciclo inteiro: no FinTrack, clique em **Sugerir melhoria** e escreva um pedido; no
painel, ele aparece em **Tarefas > Candidatas**. Aprove, aprove o plano e acompanhe até a
**Homologação** e a tela **Entrega**.

Isso gasta tokens de verdade (a tarefa da validação usou cerca de 66 mil). Há um teto de
custo por tarefa, ajustável pelo gestor.

## 3. Alimentar o painel com qualquer software

O painel é só a tela do motor (`pase-core`). Para usá-los sem o FinTrack:

```bash
docker compose up -d --build --wait db pase-core pase-panel
docker compose exec -T pase-core python -m app.seed
```

Qualquer software manda sugestões por HTTP e pergunta depois o que aconteceu com elas:

```bash
curl -X POST http://localhost:8000/api/proposals/external \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "text": "quero exportar meus relatórios em PDF"}'

curl "http://localhost:8000/api/proposals/mine?user_id=1"
```

Duas coisas para trocar pelas do **seu** produto, senão o funil julga pelo FinTrack:

- **O contexto** (escopo, requisitos, guia de engenharia): edite na tela **Contexto** do painel.
- **A memória inicial** (o que já existe e o que já foi recusado): está em `pase-core/app/seed.py`.

Para rodar o painel fora do Docker, apontando para um motor que já esteja no ar:

```bash
cd pase-panel
npm install
NEXT_PUBLIC_CORE_URL=http://localhost:8000 npm run dev      # Node 22
```

## 4. Zonas Dinâmicas no seu app

Uma zona é uma área da tela que o PASE personaliza por pessoa, preenchendo propriedades de
três componentes prontos. Ele nunca gera código. Para um app React/Next:

1. Copie `client-frontend/dynamic-zones/` para o seu app e instale o `zod`. O
   `widgets.tsx` usa `next/link`; em outro framework, troque esse link.
2. Aponte `NEXT_PUBLIC_CORE_URL` para o motor.
3. Envolva a área, com o seu componente de sempre dentro (ele é o plano B):
   ```tsx
   <DynamicZone slot="meu_slot" userId={userId}>
     <SeuComponente />
   </DynamicZone>
   ```
4. Avise o motor do uso, a cada página vista:
   `POST /api/upa/telemetry` com `{"user_id": 1, "event": "page_view", "path": "/sua-rota"}`
   (veja `client-frontend/lib/telemetry.ts`).
5. Registre a zona em `ZONAS`, em `pase-core/app/upa/contracts.py` (slot, tela, módulo,
   finalidade e quantos acessos disparam a avaliação), e o módulo em `MODULOS`, em
   `pase-core/app/task_layer/models.py`.
6. O contrato só aceita links para as rotas do FinTrack. Troque o padrão do campo `href` em
   `docs/contracts/zona.schema.json` pelo das suas rotas e repita a mudança em
   `dynamic-zones/schema.ts`: um teste confere que os dois dizem a mesma coisa.
7. Se o seu app não roda em `localhost:3000` ou `3001`, acrescente a origem em
   `cors_origins`, em `pase-core/app/common/config.py`.

## 5. Evolução de código no seu produto

Esta é a parte que **não é plug-and-play**. Hoje o Executor só escreve em duas pastas e as
verifica com as ferramentas de cada uma:

| Pasta | Verificação |
|---|---|
| `client-backend/` (Python) | `ruff` e `pytest` |
| `client-frontend/` (Next.js, TypeScript) | `tsc`, `vitest` e `next build` |

Há dois caminhos:

- **Mesma estrutura.** Coloque o seu back em `client-backend/` e o seu front em
  `client-frontend/`, numa cópia deste repositório, com `pytest` e `vitest` configurados.
- **Outra estrutura.** Edite `ALVOS`, em `pase-core/app/execution/context.py`, e as
  verificações em `pase-core/app/execution/executor.py`.

O repositório que o Executor clona é o que o `docker-compose.yml` monta em
`/workspace/repo` (volume `.:/workspace/repo`, variável `REPO_PATH`). Ele precisa ser um
repositório git com uma branch principal e o trabalho commitado: o Executor parte dela.

Para publicar de verdade, preencha `GITHUB_TOKEN` e `GITHUB_REPO` no `.env`: a versão passa a
sair por um pull request. Sem eles, tudo fica local.

## 6. Testes e roteiros

São 703 testes. Rode **um de cada vez** (eles recriam o banco de teste e se derrubam):

```bash
docker compose exec -T pase-core pytest -q               # 589
docker compose exec -T client-backend pytest -q          # 53
docker compose exec -T client-frontend npm test          # 61
```

Os sete roteiros de `scripts/demo` (`d1` a `d7`) narram uma capacidade cada, em ordem de
leitura. Com `make`, `make demos` roda todos; sem, `bash scripts/demo/d1.sh`. Fazem chamadas
reais a modelos e mexem no banco.

| Roteiro | O que mostra |
|---|---|
| d1 | memória histórica: duplicata barrada, fora de escopo recusado com citação |
| d2 | geração exploratória e análise de lacunas passando pelo mesmo funil |
| d3 | cinco acessos disparam a regra da zona; Ana personalizada, Clara no nativo |
| d4 | três conteúdos maliciosos recusados pelo cliente, com violação registrada |
| d5 | duas falhas suspendem a tarefa; um teto de custo baixo interrompe a execução |
| d6 | tickets de suporte sobre a mesma dor viram uma tarefa de zona dinâmica |
| d7 | a auditoria propõe uma melhoria e a reavaliação reintroduz descartes |

Comandos úteis, com `make`: `up`, `down`, `logs`, `seed`, `reset` (recria o banco e preserva
o contexto editado), `reset-all` (volta ao contexto inicial), `lint`, `metrics`.

## 7. Se algo der errado

- **Porta ocupada** (3000, 3001, 8000, 8001 ou 5432): feche o que a usa, ou mude a porta no
  `docker-compose.yml`.
- **Ver o que houve:** `docker compose logs pase-core` (troque pelo serviço que falhou).
- **Recomeçar do zero:** `docker compose down -v` apaga o banco; depois suba e rode as
  duas `seed` de novo.
- **Mudou o `.env`:** use `docker compose up -d --force-recreate <serviço>`.

## O que saber antes de usar

- **É uma prova de conceito local.** Não há autenticação: o `user_id` vem do cliente, e o
  CORS é restrito a `localhost`. Não exponha na internet.
- **O sistema fala português.** Os *prompts* (`pase-core/app/prompts`), a interface e os
  documentos de contexto estão em pt-BR. Para outro idioma, traduza esses três.
- **As chaves ficam no `.env`**, que não é versionado.
