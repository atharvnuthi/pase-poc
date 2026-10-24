"""Corpos de requisição e o envelope de resposta do Task Layer.

O SPEC-03 §1 diz que todo endpoint de ingestão responde "o envelope da Seção 6",
mas a Seção 6 do SPEC descreve as tabelas - o envelope nunca chega a ser
definido. O formato abaixo preenche essa lacuna com o que os consumidores já
declarados precisam: `detail` é o texto que o modal do FinTrack exibe
(SPEC-02 §2) e os campos de match são o que o painel mostra na aba Descartadas
(SPEC-06 §2).
"""

from typing import Literal

from pydantic import BaseModel, Field


class ExternalProposalIn(BaseModel):
    """Captação Ativa - modal do FinTrack."""

    user_id: int | None = None
    text: str = Field(min_length=3)


class InternalProposalIn(BaseModel):
    """Sugestão Interna - formulário do painel."""

    type: Literal["funcional", "engenharia"]
    author: str = Field(min_length=1)
    text: str = Field(min_length=3)


class AIGenerateIn(BaseModel):
    """Geração Exploratória (temperatura alta) ou Análise de Lacunas."""

    mode: Literal["exploratoria", "lacunas"]


class MatchedRef(BaseModel):
    """O item da memória contra o qual a proposta bateu."""

    kind: str
    ref_id: int
    title: str
    similarity: float


class ProposalEnvelope(BaseModel):
    """Resposta síncrona de todo endpoint de ingestão."""

    proposal_id: int | None
    outcome: str
    detail: str
    task_id: int | None = None
    matched_ref: MatchedRef | None = None
    duplicate_count: int | None = None
    #: Quantos pedidos esta proposta representa (grupo do P0a; 1 para pedido avulso).
    occurrences: int | None = None
    module: str | None = None
    output_type: str | None = None
    risk_tier: str | None = None
    uncertainty: bool | None = None
    trace_id: str | None = None
