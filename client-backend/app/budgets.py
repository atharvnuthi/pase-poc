"""Orçamentos: um limite mensal de gasto por categoria, e o quanto dele já foi usado."""

from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    Budget,
    BudgetRead,
    BudgetState,
    BudgetStatus,
    BudgetUpsert,
    Category,
    Transaction,
    User,
)
from app.months import current_month, parse_month

router = APIRouter()

ZERO = Decimal("0.00")
LIMITE_DE_ATENCAO = 80


def _field_error(field: str, message: str) -> HTTPException:
    """422 no mesmo formato do FastAPI, para o frontend ter um só parser."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


def _names(session: Session) -> dict[int, str]:
    return {c.id: c.name for c in session.exec(select(Category)).all()}


def _read(budget: Budget, names: dict[int, str]) -> BudgetRead:
    return BudgetRead(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        category=names.get(budget.category_id, ""),
        monthly_limit=budget.monthly_limit,
    )


def state_of(spent: Decimal, limit: Decimal) -> BudgetState:
    """O estado vem dos **valores**, não do percentual arredondado.

    R$ 100,01 contra um limite de R$ 100,00 dá 100% depois de arredondar para baixo, e
    chamar isso de "atenção" esconderia que o limite estourou.
    """
    if spent > limit:
        return "estourado"
    if spent * 100 >= limit * LIMITE_DE_ATENCAO:
        return "atencao"
    return "ok"


@router.get("/budgets", response_model=list[BudgetRead])
def list_budgets(
    user_id: int = Query(...), session: Session = Depends(get_session)
) -> list[BudgetRead]:
    names = _names(session)
    budgets = session.exec(
        select(Budget).where(Budget.user_id == user_id).order_by(Budget.category_id)
    ).all()
    return [_read(b, names) for b in budgets]


@router.put("/budgets", response_model=BudgetRead)
def upsert_budget(
    payload: BudgetUpsert, session: Session = Depends(get_session)
) -> BudgetRead:
    """Cria o orçamento da categoria ou troca o limite do que já existe."""
    if session.get(User, payload.user_id) is None:
        raise _field_error("user_id", "usuário inexistente")
    category = session.get(Category, payload.category_id)
    if category is None:
        raise _field_error("category_id", "categoria inexistente")
    if category.name == "Salário":
        # Orçamento limita gasto; a categoria de entrada não tem o que limitar.
        raise _field_error("category_id", "não há orçamento para uma categoria de receita")

    budget = session.exec(
        select(Budget).where(
            Budget.user_id == payload.user_id, Budget.category_id == payload.category_id
        )
    ).first()
    if budget is None:
        budget = Budget(**payload.model_dump())
    else:
        budget.monthly_limit = payload.monthly_limit
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return _read(budget, {category.id: category.name})


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: int, session: Session = Depends(get_session)) -> Response:
    budget = session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="orçamento não encontrado")
    session.delete(budget)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/budgets/status", response_model=list[BudgetStatus])
def budget_status(
    user_id: int = Query(...),
    month: str | None = Query(default=None, description="AAAA-MM; o mês corrente se omitido"),
    session: Session = Depends(get_session),
) -> list[BudgetStatus]:
    """Quanto de cada limite já foi gasto no mês.

    A soma roda em Python com `Decimal`: o SQLite guarda NUMERIC como float, e agregar
    em SQL faria o total derivar em centavos.
    """
    try:
        inicio, fim = parse_month(month or current_month())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["query", "month"], "msg": str(exc), "type": "value_error"}],
        ) from exc

    gastos: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for t in session.exec(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.type == "expense",
            Transaction.date >= inicio,
            Transaction.date < fim,
        )
    ).all():
        gastos[t.category_id] += Decimal(t.amount)

    names = _names(session)
    resultado: list[BudgetStatus] = []
    for b in session.exec(
        select(Budget).where(Budget.user_id == user_id).order_by(Budget.category_id)
    ).all():
        limite = Decimal(b.monthly_limit)
        gasto = gastos.get(b.category_id, ZERO)
        percent = int((gasto * 100) // limite) if limite > 0 else 0
        if gasto > limite and percent <= 100:
            percent = 101  # passou do limite por menos de 1%: nunca mostre "100%"
        resultado.append(
            BudgetStatus(
                budget_id=b.id,
                category_id=b.category_id,
                category=names.get(b.category_id, ""),
                monthly_limit=limite,
                spent=gasto,
                remaining=limite - gasto,
                percent=percent,
                state=state_of(gasto, limite),
            )
        )
    # o que mais pede atenção primeiro
    return sorted(resultado, key=lambda s: s.percent, reverse=True)
