"""Seed do FinTrack (`make seed`) - SPEC-02 §1 e SPEC-06 §6.1.

Idempotente: limpa as tabelas antes de inserir. Isso é necessário porque o
SQLite vive num bind mount e sobrevive ao `docker compose down -v` - sem a
limpeza, cada `make seed` duplicaria as transações.

Determinístico: a mesma semente de random em toda execução, para que uma demo
gravada e uma demo ao vivo mostrem os mesmos números.
"""

import calendar
import random
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Budget, Category, Goal, SupportTicket, Transaction, User

RANDOM_SEED = 20260916

USERS = ["Ana", "Clara"]
CATEGORIES = ["Alimentação", "Transporte", "Lazer", "Moradia", "Salário"]

SALARY = {"Ana": Decimal("5200.00"), "Clara": Decimal("4100.00")}

# (categoria, descrição, valor mínimo, valor máximo)
EXPENSE_TEMPLATES = [
    ("Alimentação", "Supermercado", 120, 390),
    ("Alimentação", "Almoço no trabalho", 25, 60),
    ("Alimentação", "Padaria", 12, 45),
    ("Transporte", "Combustível", 90, 260),
    ("Transporte", "Aplicativo de corrida", 18, 70),
    ("Transporte", "Recarga do transporte público", 40, 120),
    ("Lazer", "Cinema", 30, 80),
    ("Lazer", "Assinatura de streaming", 20, 55),
    ("Lazer", "Restaurante com amigos", 60, 180),
    ("Moradia", "Aluguel", 1200, 1800),
    ("Moradia", "Conta de luz", 80, 210),
    ("Moradia", "Internet", 90, 140),
]

# Os três primeiros compartilham a MESMA dor - "o dashboard não me mostra logo o
# que eu preciso" - mas cada um quer uma saída DIFERENTE: atalho, aviso, destaque.
# Essa divergência é o que caracteriza cauda longa e o que faz o P1b (SPEC-03 §3.3)
# responder `requires_zone=true`, em vez de tratar tudo como uma funcionalidade fixa.
#
# Tickets que pedissem a mesma coisa ("quero ver meus gastos por categoria") seriam
# demanda homogênea e viram código permanente - corretamente. Foi o que a primeira
# versão deste seed produzia, e o P1b recusou a zona com razão.
TICKETS = [
    (
        "Ana",
        "toda vez que abro o app tenho que clicar em três lugares até achar quanto "
        "gastei em transporte, que é a única coisa que eu acompanho de perto",
    ),
    (
        "Clara",
        "o dashboard me mostra um monte de número que eu não uso; o que eu queria "
        "mesmo ali era um aviso quando o gasto de alimentação passar do que costumo "
        "gastar no mês",
    ),
    (
        "Ana",
        "pra mim o que importa é o relatório mensal, mas ele fica escondido num menu; "
        "o dashboard me mostra um monte de coisa que eu não uso",
    ),
    ("Clara", "seria bom poder corrigir a data de uma transação que lancei errado"),
    ("Ana", "o saldo do mês passado some quando eu troco de tela, tenho que entrar de novo"),
]


# Limites mensais por categoria. Escolhidos para as duas pessoas ficarem em estados
# diferentes ao longo do mês (uns confortáveis, outros perto do teto), o que dá ao
# dashboard e à zona de orçamentos algo de verdade para mostrar.
BUDGETS = {
    "Ana": {"Alimentação": "900.00", "Transporte": "450.00", "Lazer": "300.00"},
    "Clara": {"Alimentação": "700.00", "Moradia": "2000.00"},
}

# (nome, alvo, já guardado, meses até o prazo ou None)
GOALS = {
    "Ana": [
        ("Reserva de emergência", "10000.00", "3200.00", None),
        ("Viagem de fim de ano", "4000.00", "1500.00", 6),
    ],
    "Clara": [("Notebook novo", "6000.00", "2100.00", 8)],
}


def _add_months(reference: date, months: int) -> date:
    month = reference.month - 1 + months
    year = reference.year + month // 12
    return date(year, month % 12 + 1, min(reference.day, 28))


def seed_budgets_and_goals(session: Session) -> tuple[int, int]:
    """Orçamentos e metas de exemplo. **Aditivo**: só cria para quem ainda não tem.

    Separado do `run()` para poder ser aplicado a um FinTrack que já está em uso, sem o
    `wipe` que apagaria as transações e tickets que existem agora.
    """
    users = {u.name: u for u in session.exec(select(User)).all()}
    categories = {c.name: c for c in session.exec(select(Category)).all()}
    today = date.today()
    budgets = goals = 0

    for name, limits in BUDGETS.items():
        user = users.get(name)
        if user is None or session.exec(select(Budget).where(Budget.user_id == user.id)).first():
            continue
        for category_name, limit in limits.items():
            category = categories.get(category_name)
            if category is not None:
                session.add(
                    Budget(user_id=user.id, category_id=category.id, monthly_limit=Decimal(limit))
                )
                budgets += 1

    for name, items in GOALS.items():
        user = users.get(name)
        if user is None or session.exec(select(Goal).where(Goal.user_id == user.id)).first():
            continue
        for goal_name, target, saved, months in items:
            session.add(
                Goal(
                    user_id=user.id,
                    name=goal_name,
                    target_amount=Decimal(target),
                    saved_amount=Decimal(saved),
                    deadline=_add_months(today, months) if months else None,
                )
            )
            goals += 1

    session.commit()
    return budgets, goals


def _months_back(reference: date, months: int) -> date:
    """Primeiro dia do mês `months` meses antes de `reference`."""
    month = reference.month - months
    year = reference.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _last_usable_day(month_start: date, today: date) -> int:
    """Último dia do mês - limitado a hoje, para nunca gerar transação no futuro."""
    last = calendar.monthrange(month_start.year, month_start.month)[1]
    if (month_start.year, month_start.month) == (today.year, today.month):
        return min(last, today.day)
    return last


def wipe(session: Session) -> None:
    """Zera as tabelas na ordem inversa das dependências."""
    for model in (Transaction, SupportTicket, Budget, Goal, Category, User):
        for row in session.exec(select(model)).all():
            session.delete(row)
    session.commit()


def run() -> None:
    init_db()
    rng = random.Random(RANDOM_SEED)
    today = date.today()

    with Session(engine) as session:
        wipe(session)

        users = {name: User(name=name) for name in USERS}
        categories = {name: Category(name=name) for name in CATEGORIES}
        for record in (*users.values(), *categories.values()):
            session.add(record)
        session.commit()
        for record in (*users.values(), *categories.values()):
            session.refresh(record)

        transactions: list[Transaction] = []
        for months in (2, 1, 0):  # três meses, do mais antigo ao atual
            month_start = _months_back(today, months)
            last_day = _last_usable_day(month_start, today)

            for user_name, user in users.items():
                # salário do mês, no dia 5 (ou no último dia disponível do mês corrente)
                salary_day = min(5, last_day)
                transactions.append(
                    Transaction(
                        user_id=user.id,
                        category_id=categories["Salário"].id,
                        type="income",
                        amount=SALARY[user_name],
                        date=month_start.replace(day=salary_day),
                        description="Salário mensal",
                    )
                )

                for category_name, description, low, high in rng.sample(EXPENSE_TEMPLATES, 8):
                    cents = rng.randint(low * 100, high * 100)
                    transactions.append(
                        Transaction(
                            user_id=user.id,
                            category_id=categories[category_name].id,
                            type="expense",
                            amount=(Decimal(cents) / 100).quantize(Decimal("0.01")),
                            date=month_start.replace(day=rng.randint(1, last_day)),
                            description=description,
                        )
                    )

        for transaction in transactions:
            session.add(transaction)

        for user_name, text in TICKETS:
            session.add(SupportTicket(user_id=users[user_name].id, text=text))

        session.commit()
        seed_budgets_and_goals(session)

        total = len(session.exec(select(Transaction)).all())
        tickets = len(session.exec(select(SupportTicket)).all())

    print(
        f"[client-backend] seed ok: {len(USERS)} personas, {len(CATEGORIES)} categorias, "
        f"{total} transações, {tickets} tickets."
    )


def run_planning_only() -> None:
    """`python -m app.seed planning`: só orçamentos e metas, sem apagar nada."""
    init_db()
    with Session(engine) as session:
        budgets, goals = seed_budgets_and_goals(session)
    print(f"[client-backend] {budgets} orçamento(s) e {goals} meta(s) criados.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "planning":
        run_planning_only()
    else:
        run()
