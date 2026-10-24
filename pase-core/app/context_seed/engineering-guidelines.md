# Guia de Engenharia do FinTrack

Este documento é lido por pessoas e **injetado nos prompts de planejamento, execução e revisão**.
É o contrato de como se escreve código no FinTrack.

> **Regra de ouro:** antes de escrever algo novo, procure se já existe. Helper, primitiva de
> UI, validação, formatador. Reusar o que existe é sempre preferível a criar um paralelo.

## 1. Stack

Versões são fixas de propósito. Não atualize nada sem pedido explícito.

| Camada | Stack |
|---|---|
| `client-backend` | Python 3.12 · FastAPI · SQLModel · SQLite |
| `client-frontend` | TypeScript 5.7 · Next.js 15 (App Router) · React 19 · Tailwind 3 |
| Testes | `pytest` no backend · `vitest` + Testing Library no frontend |
| Lint | `ruff` no Python · `tsc --noEmit` e `next build` no TypeScript |

## 2. Bibliotecas

**Não acrescente dependência.** Se parece que falta uma, quase sempre falta ler o que já
existe. Dependência nova exige pedido explícito de uma pessoa.

| Em vez de | Use |
|---|---|
| `axios`, `fetch` cru no frontend | o cliente de `lib/api.ts` (`api.*`), que já trata 422 por campo |
| `moment`, `date-fns` | `Intl.DateTimeFormat` e os helpers `formatDate` / `formatMoney` |
| `float` para dinheiro | `Decimal` no Python; string no trânsito JSON |
| biblioteca de ícones | SVG inline |

## 3. Convenções de commit e branch

Formato: `<tipo>(<escopo opcional>): <descrição>`, com tipo em `feature`, `fix`, `refactor`,
`docs`, `test`, `chore`. Descrição em português, minúscula, no imperativo, sem ponto final.
Escopo é a pasta ou o módulo: `feature(transacoes): ...`.

Branches: `feature/<nome>` e `hotfix/<nome>`, sempre a partir da principal. O fluxo completo
está no documento `git-guide`.

## 4. Backend (Python)

- **Tipagem em toda assinatura pública.** `from __future__ import annotations` no topo.
- **Docstring que explica o porquê**, não o quê.
- **Dinheiro é `Decimal`.** Nunca `float`. Em JSON trafega como string.
- **Erro de validação é 422 com mensagem por campo**, no formato que o frontend já lê
  (`_field_error` em `app/routes.py`).
- **Nada de `except: pass`.** Ou trata, ou deixa subir.
- **Estado do usuário nunca mora na memória do processo.** Um dicionário global some no
  reinício do servidor. Preferência, sessão, rascunho: vão para o banco.
- Mudança de esquema atualiza `seed.py` e os testes da API.
- Identificadores em inglês; comentários, docstrings e mensagens em pt-BR.

## 5. Frontend (TypeScript e React)

- **`"use client"` em todo arquivo que usa hook, estado, evento ou API de browser.**
  `app/layout.tsx` é Server Component e continua sendo. Precisa de estado no layout? Crie um
  componente cliente e use-o lá dentro.
- **Sempre as primitivas de `components/ui.tsx`**: `Cartao`, `Campo`, `Botao`, `TituloSecao`,
  `Vazio`, e as constantes `ENTRADA`, `SELECAO`, `AREA_TEXTO`.
- **Cores só pelos tokens semânticos** (`bg-surface`, `text-ink`, `border-line`, `text-brand`).
  Nada de cor cravada.
- **Sempre o cliente de `lib/api.ts`.**
- **Valor monetário leva `tnum`.**
- **Rótulo envolve o controle** (`<label><span>Nome</span><input/></label>`).
- **Ação destrutiva nunca escondida atrás de `hover`.**
- **Classe aplicada precisa de CSS que a use.** Um tema novo é uma paleta nova dos tokens, não
  uma classe solta no `body`.
- **Estado que depende da persona reage à troca de persona.** Ler o `localStorage` uma vez no
  layout raiz deixa o componente preso ao primeiro acesso.
- **O rótulo de um controle descreve a ação**, não o estado: "Usar tema escuro".
- Componentes em `PascalCase`, hooks em `camelCase` com prefixo `use`.

## 6. Testes

**Comportamento novo exige teste novo.** Uma entrega que muda código de produção sem
acrescentar teste é reprovada.

- Testes existentes são a rede de regressão. Se a sua mudança quebra um, **a mudança está
  errada, não o teste.** Nunca altere ou remova um teste existente.
- Teste comportamento observável: o que a pessoa vê e faz. Busque por rótulo e nome acessível,
  nunca por classe CSS.
- **Um teste só vale se falharia sem o critério que ele prova.**
- **Cubra o caminho inteiro**: primeiro acesso, depois de escolher a persona, depois de
  recarregar, depois de trocar de persona.
- Nome de teste descreve a expectativa: `test_valor_negativo_retorna_422`.

## 7. O que é somente leitura

| Caminho | Por quê |
|---|---|
| `client-frontend/dynamic-zones/` | contém a validação que recusa payload malicioso. **Verificado por código**: tocar aqui reprova a entrega |
| `pase-core/` | é outro sistema; o FinTrack não o modifica |
| qualquer `tests/` existente | ver seção 6 |

## 8. Segurança e limites

- Sem chamada de rede de dentro do ambiente de execução além do provedor de LLM.
- Sem segredo em código; tudo por variável de ambiente.
- Sem `dangerouslySetInnerHTML`, sem montar HTML a partir de string, sem `eval`.
- Sem autenticação: é prova de conceito local.
- `href` de zona dinâmica restrito por expressão regular a rotas internas.

## 9. Antes de considerar pronto

1. O comportamento novo tem teste, e os que já existiam continuam passando.
2. `ruff check` limpo; `tsc --noEmit` e `next build` limpos.
3. Nenhuma dependência nova e nenhum arquivo da seção 7 tocado.
4. A mensagem de commit segue a seção 3.
5. Cada critério de aceite tem um trecho de código que o cumpre e um teste que o prova.
6. Nenhuma mudança colateral: nada de reformatar ou renomear fora do que a tarefa pede.
