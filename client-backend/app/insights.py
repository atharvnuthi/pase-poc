"""Visão mensal: receitas e despesas dos últimos meses, para o gráfico do dashboard."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.models import MonthlyTotal, Transaction
from app.months import month_key

router = APIRouter()

ZERO = Decimal("0.00")


def last_months(today: date, count: int) -> list[str]:
    """Os `count` meses terminando no corrente, do mais antigo ao mais novo."""
    chaves: list[str] = []
    ano, mes = today.year, today.month
    for _ in range(count):
        chaves.append(f"{ano:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return list(reversed(chaves))


@router.get("/summary/monthly", response_model=list[MonthlyTotal])
def monthly_summary(
    user_id: int = Query(...),
    months: int = Query(default=6, ge=1, le=24),
    session: Session = Depends(get_session),
) -> list[MonthlyTotal]:
    """Receita e despesa de cada um dos últimos meses, **inclusive os sem movimento**.

    Mês sem transação aparece com zero em vez de sumir: um gráfico que pula um mês
    esconde justamente o mês em que nada foi gasto ou recebido.
    """
    meses = last_months(date.today(), months)
    receitas: dict[str, Decimal] = defaultdict(lambda: ZERO)
    despesas: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for t in session.exec(select(Transaction).where(Transaction.user_id == user_id)).all():
        chave = month_key(t.date)
        if chave not in meses:
            continue
        valor = Decimal(t.amount)
        if t.type == "income":
            receitas[chave] += valor
        else:
            despesas[chave] += valor

    return [
        MonthlyTotal(month=m, income=receitas.get(m, ZERO), expense=despesas.get(m, ZERO))
        for m in meses
    ]
