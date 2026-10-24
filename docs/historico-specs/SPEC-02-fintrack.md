# SPEC-02 - FinTrack (client-backend + client-frontend)

**Fase:** F1 · **Depende de:** SPEC-01
**Papel:** produto-alvo, usável de verdade e ao mesmo tempo o alvo do Executor. Ao fim da F1, a API e a suíte de testes do client-backend ficam **congeladas** - mudanças posteriores exigem aviso explícito (o Executor depende delas como rede de regressão).

## 1. client-backend (FastAPI + SQLModel + SQLite)

**Estrutura:** `app/main.py` · `app/models.py` · `app/routes.py` · `app/seed.py` · `tests/test_api.py` · `data/fintrack.db`.

**Modelos:**
- `User(id, name)`
- `Category(id, name)`
- `Transaction(id, user_id FK, category_id FK, type: "income"|"expense", amount: Decimal, date: date, description: str)`
- `SupportTicket(id, user_id FK, text: str, created_at)` - necessário para a Captação Passiva (SPEC-03). Sem isso, o modelo do PASE fica sem uma das quatro origens de demanda descritas na monografia.

**Validações (retornam 422 com mensagem por campo):** `amount > 0` · `date` não futura · `category_id` existente.

**Endpoints:**

| Método/rota | Comportamento |
|---|---|
| `GET /users` | lista personas |
| `GET /categories` | lista categorias |
| `GET /transactions?user_id=` | lista do usuário, ordenada por data desc |
| `POST /transactions` | cria (validações acima) |
| `PUT /transactions/{id}` · `DELETE /transactions/{id}` | atualiza / remove |
| `GET /summary?user_id=` | `{ balance, by_category: [{category, total}] }` (balance = receitas − despesas) |
| `GET /tickets` | lista tickets de suporte (todos os usuários, para o job de captação passiva ler) |
| `POST /tickets` | cria ticket - usado pelo seed e por um formulário simples "Falar com suporte" |
| `GET /health` | ok |

**Testes pytest (9 - rede de regressão do Executor):**
1. criar transação válida → 201; 2. `amount <= 0` → 422; 3. data futura → 422; 4. categoria inexistente → 422; 5. listagem filtra por usuário; 6. update altera valor; 7. delete remove; 8. `summary` calcula balance e agrupamento corretamente; 9. criar ticket → 201 e aparece em `GET /tickets`.

**Seed:** Ana e Clara; categorias Alimentação, Transporte, Lazer, Moradia, Salário; ~50 transações em 3 meses (incluindo salários mensais); 4–5 tickets de suporte com texto realista (ex: "não encontro onde ver quanto gastei em transporte esse mês", ver SPEC-03 para os textos exatos usados nas demos).

## 2. client-frontend (Next.js App Router + Tailwind)

**Estrutura:** `app/` (rotas) · `components/` · `lib/api.ts` (client-backend) · `lib/telemetry.ts` · `dynamic-zones/` (SPEC-05).

**Rotas:**
- `/` - seletor de persona (cards Ana/Clara); guarda `userId` (localStorage) e redireciona a `/dashboard`.
- `/dashboard` - card de saldo + gastos por categoria (`/summary`) + área reservada onde `<DynamicZone slot="resumo_financeiro">` será montada (SPEC-05); por ora renderiza só o conteúdo nativo.
- `/transacoes` - tabela + formulário de criação (exibe erros 422 por campo) + excluir.
- `/relatorios` - totais por mês; é a rota que a persona Ana "usa muito" (dispara a regra do UPA, SPEC-05).
- `/suporte` - formulário simples "Precisa de ajuda?" → `POST /tickets`. Alimenta a Captação Passiva.

**Telemetria (`lib/telemetry.ts`):** a cada mudança de rota, `POST {NEXT_PUBLIC_CORE_URL}/api/upa/telemetry` com `{ user_id, event: "page_view", path }`. Fire-and-forget; falha silenciosa.

**Modal "Sugerir melhoria":** botão flutuante em todas as páginas → textarea → `POST /api/proposals/external {user_id, text}` → exibe o `detail` do envelope de resposta. Enquanto o endpoint não existir (F1), try/catch com toast genérico.

## 3. Critérios de aceite

1. `make test-client` 100% verde.
2. App usável nas 5 rotas com as 2 personas.
3. `page_view` chegando na tabela `telemetry_events` do pase-core.
4. Modal envia e exibe o retorno do funil (integrado de verdade na F2).
5. Ticket criado em `/suporte` aparece em `GET /tickets`.
