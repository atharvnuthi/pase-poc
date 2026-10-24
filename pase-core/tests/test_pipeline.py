"""O funil do SPEC-03, com provider mock - sem rede e sem gastar crédito.

Cada teste roteiriza as respostas do LLM na ordem em que o funil as consome e
verifica o **desfecho persistido**, não só o retorno: o que não está numa tabela
não é rastreável (SPEC-00 §2).
"""

import json

import pytest
from sqlalchemy import text

from app.common.config import settings
from app.task_layer import pipeline
from app.task_layer.models import (
    OUTCOME_CANDIDATA,
    OUTCOME_DUPLICATA,
    OUTCOME_INCOERENTE,
    DiscardedProposal,
    ImplementedItem,
    Proposal,
    Task,
)
from tests.conftest import requires_db

P1 = json.dumps({"title": "Exportar CSV", "description": "Baixar transações.", "module": "transacoes"})
P1B_NAO = json.dumps({"requires_zone": False, "reasoning": "solução homogênea"})
P1B_SIM = json.dumps({"requires_zone": True, "reasoning": "cauda longa"})
P2A_OK = json.dumps({"coherent": True, "reason": "cabe no escopo", "needs_adjustment": False})
#: O trecho é uma linha literal do `project-context` da semente.
TRECHO_GAMIFICACAO = "Gamificação."
P2A_NAO = json.dumps(
    {
        "coherent": False,
        "reason": "viola o escopo do produto",
        "trecho_violado": TRECHO_GAMIFICACAO,
        "needs_adjustment": False,
    }
)
P2B = json.dumps({"impact": 4, "complexity": 2, "confidence": 0.8, "risk_tier": "medio"})


@pytest.fixture
def limpo(session):
    """Task Layer zerado antes e depois, para um teste não contaminar o outro."""

    def zerar():
        for tabela in (
            "task_state_history",
            "tasks",
            "discarded_proposals",
            "proposals",
            "implemented_items",
        ):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    yield session
    zerar()


def _proposta(session, **campos) -> Proposal:
    proposal = Proposal(origin="external", raw_text="texto qualquer", **campos)
    session.add(proposal)
    session.flush()
    return proposal


@requires_db
def test_proposta_coerente_e_inedita_vira_task_candidata(limpo, mock_providers):
    mock_providers.responses = [P1, P1B_NAO, P2A_OK, P2B]
    proposal = _proposta(limpo)

    envelope = pipeline.run(limpo, proposal)

    assert envelope.outcome == OUTCOME_CANDIDATA
    assert envelope.task_id is not None

    task = limpo.get(Task, envelope.task_id)
    assert task.status == "candidata"
    assert (task.impact, task.complexity, task.risk_tier) == (4, 2, "medio")
    assert task.uncertainty is False  # confidence 0.8 ≥ 0.5
    assert task.output_type == "codigo_permanente"

    limpo.refresh(proposal)
    assert proposal.outcome == OUTCOME_CANDIDATA
    assert proposal.embedding is not None  # entrou na memória


@requires_db
def test_confidence_baixa_marca_incerteza(limpo, mock_providers):
    mock_providers.responses = [
        P1,
        P1B_NAO,
        P2A_OK,
        json.dumps({"impact": 3, "complexity": 3, "confidence": 0.3, "risk_tier": "baixo"}),
    ]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert limpo.get(Task, envelope.task_id).uncertainty is True


@requires_db
def test_duplicata_de_implementada_incrementa_contador_e_nao_entra_na_memoria(
    limpo, mock_providers
):
    """SPEC-03 §3.4: duplicata engorda o contador de quem já estava lá."""
    from app.common.vector_store import save_embedding

    item = ImplementedItem(title="Relatórios mensais", description="Totais por mês.")
    limpo.add(item)
    limpo.flush()
    save_embedding("implemented", item.id, "Relatórios mensais\nTotais por mês.", session=limpo)
    limpo.commit()

    # o texto normalizado é idêntico ao implementado → similaridade 1.0
    mock_providers.responses = [
        json.dumps(
            {"title": "Relatórios mensais", "description": "Totais por mês.", "module": "relatorios"}
        ),
        P1B_NAO,
    ]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == OUTCOME_DUPLICATA
    assert envelope.matched_ref.kind == "implemented"
    assert envelope.matched_ref.similarity == pytest.approx(1.0, abs=1e-4)
    assert envelope.duplicate_count == 2

    limpo.refresh(item)
    assert item.duplicate_count == 2
    assert item.duplicate_refs == [envelope.proposal_id]

    descarte = (
        limpo.query(DiscardedProposal)
        .filter(DiscardedProposal.proposal_id == envelope.proposal_id)
        .one()
    )
    assert descarte.reason_type == "duplicata"
    assert descarte.embedding is None  # nunca polui a busca vetorial


@requires_db
def test_incoerente_vai_para_a_memoria_com_embedding(limpo, mock_providers):
    """Descarte por incoerência entra na memória: é o que barra variações depois."""
    mock_providers.responses = [P1, P1B_NAO, P2A_NAO]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == OUTCOME_INCOERENTE
    assert envelope.detail.startswith("viola o escopo do produto")
    assert TRECHO_GAMIFICACAO in envelope.detail  # o motivo cita o trecho violado

    descarte = (
        limpo.query(DiscardedProposal)
        .filter(DiscardedProposal.proposal_id == envelope.proposal_id)
        .one()
    )
    assert descarte.reason_type == "incoerente"
    assert descarte.cited_excerpt == TRECHO_GAMIFICACAO
    assert descarte.embedding is not None
    assert limpo.query(Task).count() == 0


@requires_db
def test_zona_dinamica_quando_o_padrao_e_de_cauda_longa(limpo, mock_providers, monkeypatch):
    """Sem zona no módulo, a demanda de cauda longa vira tarefa para construí-la."""
    from app.upa import contracts

    sem_zona = {m: z for m, z in contracts.ZONA_DO_MODULO.items() if m != "dashboard"}
    monkeypatch.setattr(contracts, "ZONA_DO_MODULO", sem_zona)
    mock_providers.responses = [
        json.dumps(
            {"title": "Ver gastos do jeito que eu quero", "description": "x", "module": "dashboard"}
        ),
        P1B_SIM,
        P2A_OK,
        json.dumps({"impact": 3, "complexity": 2, "confidence": 0.7, "risk_tier": "baixo"}),
    ]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == OUTCOME_CANDIDATA
    assert limpo.get(Task, envelope.task_id).output_type == "zona_dinamica"


@requires_db
def test_zona_ja_homologada_redireciona_para_o_upa(limpo, mock_providers):
    limpo.add(
        Task(
            title="Zona do dashboard",
            description="já homologada",
            module="dashboard",
            output_type="zona_dinamica",
            status="finalizada",
            final_outcome="aprovada",
        )
    )
    limpo.commit()

    mock_providers.responses = [
        json.dumps({"title": "Outro recorte do resumo", "description": "x", "module": "dashboard"}),
        P1B_SIM,
        P2A_OK,
    ]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == "redirecionada_zona"
    assert limpo.query(Task).filter(Task.status == "candidata").count() == 0


@requires_db
def test_zona_nao_redireciona_pedido_fora_do_escopo(limpo, mock_providers):
    """A coerência vale antes do desvio: o que o escopo exclui é descartado, não redirecionado."""
    limpo.add(
        Task(
            title="Zona do dashboard",
            description="já homologada",
            module="dashboard",
            output_type="zona_dinamica",
            status="finalizada",
            final_outcome="aprovada",
        )
    )
    limpo.commit()

    mock_providers.responses = [
        json.dumps({"title": "Carteira de ações", "description": "x", "module": "dashboard"}),
        P1B_SIM,
        P2A_NAO,
    ]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == OUTCOME_INCOERENTE
    assert limpo.query(Task).filter(Task.status == "candidata").count() == 0


@requires_db
def test_engenharia_pula_memoria_e_coerencia(limpo, mock_providers):
    """SPEC-03 §4: a autorização já transferiu o julgamento a um humano."""
    mock_providers.responses = [P1, P2B]  # sem P1b, sem P2a

    envelope = pipeline.run(limpo, _proposta(limpo, type="engenharia", author="PASE Audit"))

    assert envelope.outcome == OUTCOME_CANDIDATA
    assert len(mock_providers.calls) == 2


@requires_db
def test_engenharia_nunca_fica_com_risco_baixo(limpo, mock_providers):
    mock_providers.responses = [
        P1,
        json.dumps({"impact": 2, "complexity": 1, "confidence": 0.9, "risk_tier": "baixo"}),
    ]

    envelope = pipeline.run(limpo, _proposta(limpo, type="engenharia", author="PASE Audit"))

    assert limpo.get(Task, envelope.task_id).risk_tier == "medio"


@requires_db
def test_ajuste_de_coerencia_tem_teto(limpo, mock_providers):
    """SPEC-00 §4: nenhum loop de correção roda indefinidamente."""
    ajuste = json.dumps(
        {
            "coherent": True,
            "reason": "quase lá",
            "needs_adjustment": True,
            "adjusted_title": "Título ajustado",
            "adjusted_description": "Descrição ajustada.",
        }
    )
    mock_providers.responses = [P1, P1B_NAO] + [ajuste] * 10

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == OUTCOME_INCOERENTE
    descarte = (
        limpo.query(DiscardedProposal)
        .filter(DiscardedProposal.proposal_id == envelope.proposal_id)
        .one()
    )
    assert descarte.reason_text == "ajuste não convergiu"

    # P1 + P1b + (1 + teto) chamadas de coerência
    assert len(mock_providers.calls) == 2 + settings.coherence_max_adjustments + 1


@requires_db
def test_falha_de_llm_descarta_com_motivo_tecnico_em_vez_de_travar(limpo, mock_providers):
    """SPEC-08 §1: quem chamou decide, e a decisão nunca é travar o pipeline."""
    mock_providers.responses = ["isso não é json", "continua não sendo json"]

    envelope = pipeline.run(limpo, _proposta(limpo))

    assert envelope.outcome == OUTCOME_INCOERENTE
    descarte = (
        limpo.query(DiscardedProposal)
        .filter(DiscardedProposal.proposal_id == envelope.proposal_id)
        .one()
    )
    assert "falha técnica" in descarte.reason_text
