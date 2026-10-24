# Arquitetura e Design do FinTrack

## 1. Visão geral

O FinTrack são dois serviços que conversam por HTTP.

| Serviço | Tecnologia | Porta | Papel |
|---|---|---|---|
| `client-frontend` | Next.js 15 (App Router) · React 19 · Tailwind 3 · TypeScript | 3001 | Interface |
| `client-backend` | FastAPI · SQLModel · SQLite | 8001 | API de dados |

O navegador fala com os dois: a API do FinTrack para os dados, e o serviço do sistema que
evolui o produto para telemetria, sugestões e zonas dinâmicas.

## 2. Estrutura do frontend

| Pasta | Conteúdo |
|---|---|
| `app/` | Rotas: `/`, `/dashboard`, `/transacoes`, `/orcamentos`, `/metas`, `/relatorios`, `/suporte` |
| `components/` | `AppShell` (moldura), `SuggestModal`, `ui.tsx` (primitivas), `Progresso`, `GraficoMensal`, `PainelDoMes` |
| `lib/` | `api.ts` (cliente HTTP), `user.ts` (persona), `telemetry.ts` |
| `dynamic-zones/` | O SDK das zonas dinâmicas: schema, registry de widgets e a validação. **Somente leitura** para agentes |
| `tests/` | Rede de regressão (vitest + Testing Library) |

## 3. Estrutura do backend

| Arquivo | Conteúdo |
|---|---|
| `app/models.py` | Tabelas e schemas de entrada e saída |
| `app/routes.py` | Endpoints originais (superfície congelada); erro de validação é 422 com mensagem por campo |
| `app/budgets.py`, `app/goals.py`, `app/insights.py` | Orçamentos, metas e visão mensal, em módulos próprios para não mexer na superfície congelada |
| `app/months.py` | Único lugar que converte `AAAA-MM` em intervalo de datas |
| `app/db.py` | Engine SQLite e sessão |
| `app/seed.py` | Dados iniciais: duas personas, categorias e transações |

## 4. Fluxo de dados

1. A pessoa escolhe uma persona; o `id` fica no navegador.
2. Cada tela busca os dados dela na API, sempre com o `user_id`.
3. O dashboard agrega saldo e gastos por categoria no servidor, com `Decimal`.
4. Os relatórios mensais são agregados no cliente a partir da lista de transações.
5. A cada troca de rota, o app envia um evento de navegação para o sistema de personalização.

## 5. Zonas dinâmicas

Uma zona é um espaço da tela com um nome (`slot`). Há seis, uma por tela, e todas compartilham
o mesmo contrato. O componente `DynamicZone`:
1. busca o payload ativo da pessoa para aquele espaço;
2. valida o payload contra o schema (Zod);
3. renderiza o widget do catálogo, ou **o componente nativo** em qualquer falha.

Contrato e fallback são o que garante que a personalização nunca quebra a tela nem executa
código arbitrário.

## 6. Decisões de design

- Persona em vez de autenticação, por ser prova de conceito local.
- Dinheiro em `Decimal`, nunca `float`.
- Cores só por tokens semânticos; o tema é um conjunto de valores para esses tokens.
- Um cliente HTTP único (`lib/api.ts`), que já trata o 422 por campo.

As decisões com contexto e alternativas estão registradas em `adrs/`.
