"""Modelos e schemas do FinTrack (SPEC-02 §1).

Regras de negócio centrais (ver o documento project-context, no contexto do PASE):
- toda transação pertence a exatamente um usuário e uma categoria;
- valores são sempre positivos - o `type` determina o sinal no cálculo de saldo;
- categorias são fixas (não há CRUD de categoria pelo usuário final).
"""

from datetime import UTC, datetime
from datetime import date as Date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator
from pydantic import Field as PydField
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

TransactionType = Literal["income", "expense"]

# Duas casas decimais bastam para dinheiro; SQLite guarda NUMERIC como float,
# então toda agregação é feita em Python com Decimal (nunca com SUM() em SQL).
MONEY_DIGITS = 12
MONEY_PLACES = 2


def utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Tabelas
# --------------------------------------------------------------------------- #


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    # `str` na tabela porque o SQLModel não mapeia Literal para coluna; quem
    # garante o domínio income|expense é o schema de entrada (TransactionBase).
    type: str
    amount: Decimal = Field(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    date: Date
    description: str = ""


class SupportTicket(SQLModel, table=True):
    """Canal de suporte - é o que alimenta a Captação Passiva do PASE (SPEC-03 §2)."""

    __tablename__ = "support_tickets"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    text: str
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Schemas de entrada e saída
# --------------------------------------------------------------------------- #


class TransactionBase(BaseModel):
    user_id: int
    category_id: int
    type: TransactionType
    amount: Decimal = PydField(gt=0, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    date: Date
    description: str = ""

    @field_validator("date")
    @classmethod
    def nao_pode_ser_futura(cls, value: Date) -> Date:
        if value > Date.today():
            raise ValueError("a data não pode ser futura")
        return value


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(TransactionBase):
    pass


class TransactionRead(BaseModel):
    id: int
    user_id: int
    category_id: int
    category: str  # nome da categoria, para a tabela do frontend não precisar cruzar
    type: TransactionType
    amount: Decimal
    date: Date
    description: str


class CategoryTotal(BaseModel):
    category: str
    total: Decimal


class Summary(BaseModel):
    """`balance` = receitas − despesas; `by_category` agrupa apenas despesas."""

    balance: Decimal
    by_category: list[CategoryTotal]


class TicketCreate(BaseModel):
    user_id: int
    text: str = PydField(min_length=1)


class TicketRead(BaseModel):
    id: int
    user_id: int
    text: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# Orçamentos e metas
# --------------------------------------------------------------------------- #


class Budget(SQLModel, table=True):
    """Limite mensal de gasto de uma pessoa em uma categoria."""

    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category_id", name="uq_budget_user_category"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    monthly_limit: Decimal = Field(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)


class Goal(SQLModel, table=True):
    """Meta de economia: um valor-alvo, quanto já foi guardado e um prazo opcional."""

    __tablename__ = "goals"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    target_amount: Decimal = Field(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    saved_amount: Decimal = Field(
        default=Decimal("0.00"), max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    deadline: Date | None = None
    created_at: datetime = Field(default_factory=utcnow)


BudgetState = Literal["ok", "atencao", "estourado"]


class BudgetUpsert(BaseModel):
    user_id: int
    category_id: int
    monthly_limit: Decimal = PydField(gt=0, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)


class BudgetRead(BaseModel):
    id: int
    user_id: int
    category_id: int
    category: str
    monthly_limit: Decimal


class BudgetStatus(BaseModel):
    """Quanto do limite do mês já foi consumido.

    `state`: `ok` até 79%, `atencao` de 80% a 100%, `estourado` acima de 100%.
    """

    budget_id: int
    category_id: int
    category: str
    monthly_limit: Decimal
    spent: Decimal
    remaining: Decimal  # negativo quando estourou
    percent: int
    state: BudgetState


class GoalCreate(BaseModel):
    user_id: int
    name: str = PydField(min_length=1, max_length=80)
    target_amount: Decimal = PydField(gt=0, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    deadline: Date | None = None

    @field_validator("deadline")
    @classmethod
    def nao_pode_estar_no_passado(cls, value: Date | None) -> Date | None:
        if value is not None and value < Date.today():
            raise ValueError("o prazo não pode estar no passado")
        return value


class GoalContribute(BaseModel):
    amount: Decimal = PydField(gt=0, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)


class GoalRead(BaseModel):
    id: int
    user_id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    remaining: Decimal  # zero quando a meta foi atingida
    percent: int
    reached: bool
    deadline: Date | None
    #: Quanto guardar por mês para chegar no prazo; `None` sem prazo ou com meta atingida.
    monthly_needed: Decimal | None


class MonthlyTotal(BaseModel):
    month: str  # YYYY-MM
    income: Decimal
    expense: Decimal

