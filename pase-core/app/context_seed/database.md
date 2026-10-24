# Banco de Dados do FinTrack

SQLite, arquivo `fintrack.db`, acessado por SQLModel. É um banco de prova de conceito local.

## Tabelas

| Tabela | Colunas |
|---|---|
| `users` | `id`, `name` |
| `categories` | `id`, `name` |
| `transactions` | `id`, `user_id` (FK), `category_id` (FK), `type` (`income` ou `expense`), `amount` (decimal, 2 casas), `date`, `description` |
| `support_tickets` | `id`, `user_id` (FK), `text`, `created_at` |
| `budgets` | `id`, `user_id` (FK), `category_id` (FK), `monthly_limit` (decimal); único por (`user_id`, `category_id`) |
| `goals` | `id`, `user_id` (FK), `name`, `target_amount` (decimal), `saved_amount` (decimal, começa em 0), `deadline` (opcional), `created_at` |

## Regras

- Toda transação pertence a **um** usuário e **uma** categoria.
- `amount` é sempre positivo. O `type` define o sinal no saldo.
- `amount` tem no máximo 12 dígitos e 2 casas decimais.
- Categorias são fixas: o usuário final não cria nem apaga.
- Um orçamento limita só **despesa**; não existe orçamento para a categoria de receita.
- `monthly_limit` e os valores de metas são sempre positivos; passar do alvo de uma meta é permitido.
- O gasto de um orçamento soma só despesas da categoria dentro do mês (fim exclusivo).

## Validações (422 com mensagem por campo)

| Campo | Regra |
|---|---|
| `amount` | positivo |
| `date` | não pode ser futura |
| `category_id` | precisa existir |
| `user_id` | precisa existir |
| `type` | `income` ou `expense` |
| `monthly_limit`, `target_amount`, aporte | positivo |
| `deadline` de meta | não pode estar no passado |
| `month` (filtros) | formato `AAAA-MM` |

Essas validações fazem parte da rede de regressão: enfraquecer uma delas reprova a entrega.

## Cuidados

- SQLite guarda decimal como número de ponto flutuante. **Toda agregação é feita em Python
  com `Decimal`**, nunca com `SUM()` em SQL.
- Mudança de esquema exige atualizar `seed.py` e os testes da API.
- Preferência do usuário (como tema) que precisa sobreviver a reinício **não** pode ficar só em
  memória do processo.

## Dados iniciais

Duas personas (Ana e Clara), as categorias fixas e um conjunto de transações para cada uma.
