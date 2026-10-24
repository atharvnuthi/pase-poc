"""Os 9 endpoints do FinTrack (SPEC-02 §1).

ATENÇÃO: esta superfície é contrato congelado a partir da F1. O Executor do PASE
edita este arquivo de forma autônoma e usa `tests/test_api.py` como rede de
regressão - acrescentar ou mudar um endpoint aqui muda o que o Executor pode
quebrar sem ninguém perceber. Ver SPEC-02 §Papel.
"""

import csv
import io
import unicodedata
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    Category,
    CategoryTotal,
    Summary,
    SupportTicket,
    TicketCreate,
    TicketRead,
    Transaction,
    TransactionCreate,
    TransactionRead,
    TransactionType,
    TransactionUpdate,
    User,
)
from app.months import parse_month

router = APIRouter()

ZERO = Decimal("0.00")


# Armazenamento em memória para preferências de tema por user_id
_theme_preferences: dict[int, str] = {}


class ThemePreference(BaseModel):
    user_id: int
    theme: str  # 'light' ou 'dark'


def _field_error(field: str, message: str) -> HTTPException:
    """422 no mesmo formato do FastAPI, para o frontend ter um só parser."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


def _require_category(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise _field_error("category_id", "categoria inexistente")
    return category


def _to_read(transaction: Transaction, category_name: str) -> TransactionRead:
    return TransactionRead(
        id=transaction.id,
        user_id=transaction.user_id,
        category_id=transaction.category_id,
        category=category_name,
        type=transaction.type,
        amount=transaction.amount,
        date=transaction.date,
        description=transaction.description,
    )


def _sem_acento(texto: str) -> str:
    """Minúsculas e sem acento, para a busca por texto achar "padaria" em "Padaria"."""
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _category_names(session: Session) -> dict[int, str]:
    return {category.id: category.name for category in session.exec(select(Category)).all()}


@router.get("/users", response_model=list[User])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return session.exec(select(User).order_by(User.id)).all()


@router.get("/categories", response_model=list[Category])
def list_categories(session: Session = Depends(get_session)) -> list[Category]:
    return session.exec(select(Category).order_by(Category.id)).all()


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions(
    user_id: int = Query(...),
    q: str | None = Query(default=None, description="texto contido na descrição"),
    category_id: int | None = Query(default=None),
    type: TransactionType | None = Query(default=None),
    month: str | None = Query(default=None, description="AAAA-MM"),
    limit: int | None = Query(default=None, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[TransactionRead]:
    """Transações do usuário, da mais recente para a mais antiga.

    Os filtros são opcionais e se combinam (E). Sem nenhum, devolve tudo, como sempre
    devolveu: quem já chamava este endpoint não percebe diferença.
    """
    consulta = select(Transaction).where(Transaction.user_id == user_id)
    if category_id is not None:
        consulta = consulta.where(Transaction.category_id == category_id)
    if type is not None:
        consulta = consulta.where(Transaction.type == type)
    if month:
        try:
            inicio, fim = parse_month(month)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[{"loc": ["query", "month"], "msg": str(exc), "type": "value_error"}],
            ) from exc
        consulta = consulta.where(Transaction.date >= inicio, Transaction.date < fim)
    consulta = consulta.order_by(Transaction.date.desc(), Transaction.id.desc())

    transactions = session.exec(consulta).all()
    if q and q.strip():
        # filtrado em Python: `LIKE` do SQLite ignora acento só para ASCII, e quem
        # procura "alimentacao" espera achar "Alimentação"
        termo = _sem_acento(q.strip())
        transactions = [t for t in transactions if termo in _sem_acento(t.description)]
    if limit is not None:
        transactions = transactions[:limit]

    names = _category_names(session)
    return [_to_read(t, names.get(t.category_id, "")) for t in transactions]


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    session: Session = Depends(get_session),
) -> TransactionRead:
    category = _require_category(session, payload.category_id)
    transaction = Transaction(**payload.model_dump())
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return _to_read(transaction, category.name)


@router.put("/transactions/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    session: Session = Depends(get_session),
) -> TransactionRead:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="transação não encontrada"
        )

    category = _require_category(session, payload.category_id)
    for field, value in payload.model_dump().items():
        setattr(transaction, field, value)
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return _to_read(transaction, category.name)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: int,
    session: Session = Depends(get_session),
) -> None:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="transação não encontrada"
        )
    session.delete(transaction)
    session.commit()


@router.get("/summary", response_model=Summary)
def summary(
    user_id: int = Query(...),
    session: Session = Depends(get_session),
) -> Summary:
    """Saldo do usuário e total de **despesas** por categoria.

    A soma roda em Python com Decimal: o SQLite guarda NUMERIC como float e
    agregar em SQL faria o saldo derivar em centavos.
    """
    transactions = session.exec(
        select(Transaction).where(Transaction.user_id == user_id)
    ).all()
    names = _category_names(session)

    balance = ZERO
    expenses: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for transaction in transactions:
        amount = Decimal(transaction.amount)
        if transaction.type == "income":
            balance += amount
        else:
            balance -= amount
            expenses[names.get(transaction.category_id, "")] += amount

    by_category = [
        CategoryTotal(category=name, total=total)
        for name, total in sorted(expenses.items(), key=lambda item: item[1], reverse=True)
    ]
    return Summary(balance=balance, by_category=by_category)


@router.get("/tickets", response_model=list[TicketRead])
def list_tickets(session: Session = Depends(get_session)) -> list[SupportTicket]:
    """Todos os tickets, de todos os usuários - a Captação Passiva do PASE lê daqui."""
    return session.exec(select(SupportTicket).order_by(SupportTicket.created_at)).all()


@router.post("/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    session: Session = Depends(get_session),
) -> SupportTicket:
    if session.get(User, payload.user_id) is None:
        raise _field_error("user_id", "usuário inexistente")
    ticket = SupportTicket(user_id=payload.user_id, text=payload.text)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


@router.get("/transactions/export")
def export_transactions_csv(
    user_id: int = Query(...),
    session: Session = Depends(get_session),
) -> Response:
    """Exporta as transações do usuário em CSV para download."""
    transactions = session.exec(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    ).all()
    names = _category_names(session)

    output = io.StringIO()
    writer = csv.writer(output)

    # Cabeçalho
    writer.writerow([
        "id",
        "user_id",
        "category_id",
        "category",
        "type",
        "amount",
        "date",
        "description",
    ])

    # Linhas
    for t in transactions:
        writer.writerow([
            t.id,
            t.user_id,
            t.category_id,
            names.get(t.category_id, ""),
            t.type,
            f"{t.amount:.2f}",
            t.date.isoformat(),
            t.description,
        ])

    csv_content = output.getvalue()
    output.close()

    headers = {
        "Content-Disposition": f"attachment; filename=transactions_user_{user_id}.csv",
        "Content-Type": "text/csv; charset=utf-8",
    }

    return Response(content=csv_content, media_type="text/csv", headers=headers)


# Novos endpoints para preferência de tema

@router.get("/theme", response_model=ThemePreference)
def get_theme_preference(user_id: int = Query(...)) -> ThemePreference:
    """Retorna a preferência de tema do usuário, ou 'light' se não definida."""
    theme = _theme_preferences.get(user_id, "light")
    return ThemePreference(user_id=user_id, theme=theme)


@router.post("/theme", response_model=ThemePreference)
def set_theme_preference(payload: ThemePreference) -> ThemePreference:
    """Define a preferência de tema do usuário."""
    if payload.theme not in ("light", "dark"):
        raise _field_error("theme", "tema deve ser 'light' ou 'dark'")
    _theme_preferences[payload.user_id] = payload.theme
    return payload
