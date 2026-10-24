"""Metas de economia: um valor-alvo, quanto já foi guardado e, se houver, um prazo."""

from datetime import date
from decimal import ROUND_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, select

from app.db import get_session
from app.models import Goal, GoalContribute, GoalCreate, GoalRead, User

router = APIRouter()

ZERO = Decimal("0.00")
CENTAVO = Decimal("0.01")


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


def months_left(deadline: date, today: date) -> int:
    """Meses inteiros até o prazo, no mínimo 1: guardar "em zero meses" não faz sentido."""
    meses = (deadline.year - today.year) * 12 + (deadline.month - today.month)
    return max(meses, 1)


def to_read(goal: Goal, today: date | None = None) -> GoalRead:
    today = today or date.today()
    alvo = Decimal(goal.target_amount)
    guardado = Decimal(goal.saved_amount)
    restante = max(alvo - guardado, ZERO)
    reached = guardado >= alvo
    percent = min(int((guardado * 100) // alvo), 100) if alvo > 0 else 0

    mensal = None
    if goal.deadline is not None and not reached:
        # arredonda para cima: arredondar para baixo faria a pessoa terminar o prazo
        # alguns centavos abaixo do alvo
        mensal = (restante / months_left(goal.deadline, today)).quantize(
            CENTAVO, rounding=ROUND_UP
        )

    return GoalRead(
        id=goal.id,
        user_id=goal.user_id,
        name=goal.name,
        target_amount=alvo,
        saved_amount=guardado,
        remaining=restante,
        percent=percent,
        reached=reached,
        deadline=goal.deadline,
        monthly_needed=mensal,
    )


@router.get("/goals", response_model=list[GoalRead])
def list_goals(
    user_id: int = Query(...), session: Session = Depends(get_session)
) -> list[GoalRead]:
    goals = session.exec(select(Goal).where(Goal.user_id == user_id).order_by(Goal.id)).all()
    return [to_read(g) for g in goals]


@router.post("/goals", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, session: Session = Depends(get_session)) -> GoalRead:
    if session.get(User, payload.user_id) is None:
        raise _field_error("user_id", "usuário inexistente")
    goal = Goal(**payload.model_dump())
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return to_read(goal)


@router.post("/goals/{goal_id}/contribute", response_model=GoalRead)
def contribute(
    goal_id: int, payload: GoalContribute, session: Session = Depends(get_session)
) -> GoalRead:
    """Soma um valor ao que já foi guardado. Passar do alvo é permitido: meta é piso."""
    goal = session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="meta não encontrada")
    goal.saved_amount = Decimal(goal.saved_amount) + payload.amount
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return to_read(goal)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, session: Session = Depends(get_session)) -> Response:
    goal = session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="meta não encontrada")
    session.delete(goal)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
