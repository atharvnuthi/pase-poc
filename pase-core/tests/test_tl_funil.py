"""Camada de Tarefas: peso das ocorrências, RAG do P1b e do P2a, citação conferida
por código e urgência inicial (monografia §4.2, §4.3 e §4.4.1).

Provider mock: as respostas do LLM são roteirizadas, e o que se confere é o que o
funil **mandou** ao modelo e o que ele **gravou** - não o que o modelo disse.
"""

import json

import pytest
from sqlalchemy import func, select, text

from app.common.vector_store import historico_do_modulo, save_embedding
from app.orchestration.models import Incident
from app.task_layer import citacao, generation, pipeline
from app.task_layer.models import (
    OUTCOME_CANDIDATA,
    OUTCOME_DUPLICATA,
    OUTCOME_INCOERENTE,
    OUTCOME_REDIRECIONADA,
    DiscardedProposal,
    ImplementedItem,
    Proposal,
    Task,
    TaskStateHistory,
)
from tests.conftest import requires_db

P1B_NAO = json.dumps({"requires_zone": False, "reasoning": "solução homogênea"})
P1B_SIM = json.dumps({"requires_zone": True, "reasoning": "cauda longa"})
P2A_OK = json.dumps(
    {"coherent": True, "reason": "cabe", "trecho_violado": None, "needs_adjustment": False}
)
P2B = json.dumps({"impact": 4, "complexity": 2, "confidence": 0.8, "risk_tier": "medio"})

#: Linha literal do `project-context` da semente - o cenário do seed.
LINHA_CAMBIO = "Investimentos, câmbio, múltiplas moedas."


def _p2a_incoerente(trecho, motivo="Minerar criptomoedas é investimento.") -> str:
    return json.dumps(
        {
            "coherent": False,
            "reason": motivo,
            "trecho_violado": trecho,
            "needs_adjustment": False,
        }
    )


@pytest.fixture
def limpo(session):
    def zerar():
        for tabela in (
            "task_state_history",
            "tasks",
            "discarded_proposals",
            "proposals",
            "implemented_items",
            "incidents",
        ):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    yield session
    zerar()


def _proposta(session, title, description, module, **campos) -> Proposal:
    proposal = Proposal(
        origin=campos.pop("origin", "external"),
        raw_text=campos.pop("raw_text", f"{title} {description}"),
        title=title,
        description=description,
        module=module,
        **campos,
    )
    session.add(proposal)
    session.flush()
    return proposal


def _com_embedding(session, kind, proposal) -> Proposal:
    save_embedding(
        kind, proposal.id, f"{proposal.title}\n{proposal.description}", session=session
    )
    return proposal


def _prompt(mock, cabecalho: str) -> str:
    """O system prompt da chamada cujo título começa com `cabecalho` (ex.: "# P1b")."""
    for mensagens in mock.calls:
        if mensagens[0]["content"].startswith(cabecalho):
            return mensagens[0]["content"]
    raise AssertionError(f"nenhuma chamada a {cabecalho}")


def _com_embedding_total(session) -> int:
    total = 0
    for modelo in (Proposal, DiscardedProposal, ImplementedItem):
        total += session.execute(
            select(func.count()).select_from(modelo).where(modelo.embedding.is_not(None))
        ).scalar_one()
    return total


# --------------------------------------------------------------------------- #
# 1. Peso das ocorrências
# --------------------------------------------------------------------------- #


@requires_db
def test_grupo_do_p0a_vira_peso_da_proposta_e_chega_ao_p2b(limpo, mock_providers):
    """Três tickets sobre a mesma dor: uma demanda, com o peso de três."""
    mock_providers.responses = [P1B_NAO, P2A_OK, P2B]
    proposal = _proposta(
        limpo, "Exportar transações em CSV", "baixar planilha", "transacoes", origin="passiva"
    )

    envelope = pipeline.run(limpo, proposal, ja_normalizada=True, recorrencia=3)

    assert envelope.outcome == OUTCOME_CANDIDATA
    assert envelope.occurrences == 3
    limpo.refresh(proposal)
    assert proposal.occurrences == 3
    assert "reúne **3** pedido(s)" in _prompt(mock_providers, "# P2b")
    assert "reúne **3** pedido(s)" in _prompt(mock_providers, "# P1b")
    nota = limpo.execute(
        select(TaskStateHistory.note).where(TaskStateHistory.task_id == envelope.task_id)
    ).scalar_one()
    assert "3 pedidos" in nota


@requires_db
def test_duplicata_de_candidata_soma_o_peso_e_nao_cresce_a_base(limpo, mock_providers):
    original = _com_embedding(
        limpo,
        "candidata",
        _proposta(
            limpo, "Exportar transações em CSV", "baixar planilha", "transacoes",
            outcome=OUTCOME_CANDIDATA, occurrences=2,
        ),
    )
    limpo.commit()
    antes = _com_embedding_total(limpo)

    mock_providers.responses = [P1B_NAO]
    repetida = _proposta(
        limpo, "Exportar transações em CSV", "baixar planilha", "transacoes", origin="passiva"
    )
    envelope = pipeline.run(limpo, repetida, ja_normalizada=True, recorrencia=3)

    assert envelope.outcome == OUTCOME_DUPLICATA
    assert envelope.matched_ref.kind == "candidata"
    assert envelope.duplicate_count == 5  # 2 que já tinha + 3 que chegaram
    limpo.refresh(original)
    assert original.occurrences == 5
    assert _com_embedding_total(limpo) == antes  # a base vetorial não cresceu

    auditoria = limpo.execute(
        select(DiscardedProposal).where(DiscardedProposal.proposal_id == repetida.id)
    ).scalar_one()
    assert auditoria.matched_ref == f"candidata#{original.id}"
    assert auditoria.embedding is None


@requires_db
def test_duplicata_de_implementada_e_de_descarte_soma_o_peso(limpo, mock_providers):
    item = ImplementedItem(title="Relatórios mensais", description="Totais por mês.")
    limpo.add(item)
    limpo.flush()
    save_embedding("implemented", item.id, "Relatórios mensais\nTotais por mês.", session=limpo)

    recusada = _proposta(limpo, "Minerar criptomoedas", "renda extra", "geral")
    descarte = DiscardedProposal(
        proposal_id=recusada.id, reason_type="incoerente", reason_text="fora", duplicate_count=1
    )
    limpo.add(descarte)
    limpo.flush()
    save_embedding("discarded", descarte.id, "Minerar criptomoedas\nrenda extra", session=limpo)
    limpo.commit()
    antes = _com_embedding_total(limpo)

    mock_providers.responses = [P1B_NAO]
    e1 = pipeline.run(
        limpo,
        _proposta(limpo, "Relatórios mensais", "Totais por mês.", "relatorios"),
        ja_normalizada=True,
        recorrencia=3,
    )
    e2 = pipeline.run(
        limpo,
        _proposta(limpo, "Minerar criptomoedas", "renda extra", "geral"),
        ja_normalizada=True,
        recorrencia=2,
    )

    assert (e1.outcome, e1.duplicate_count) == (OUTCOME_DUPLICATA, 4)
    assert (e2.outcome, e2.duplicate_count) == (OUTCOME_DUPLICATA, 3)
    limpo.refresh(item)
    limpo.refresh(descarte)
    assert item.duplicate_count == 4
    assert descarte.duplicate_count == 3
    assert _com_embedding_total(limpo) == antes


# --------------------------------------------------------------------------- #
# 2. RAG: histórico do módulo no P1b, precedentes no P2a
# --------------------------------------------------------------------------- #


@requires_db
def test_p1b_le_os_pedidos_parecidos_do_mesmo_modulo(limpo, mock_providers):
    titulo = "Relatório de gastos por categoria escolhida"
    descricao = "cada um escolhe as categorias do relatório"
    _com_embedding(
        limpo,
        "redirecionada",
        _proposta(limpo, titulo, descricao, "relatorios", outcome=OUTCOME_REDIRECIONADA),
    )
    _com_embedding(
        limpo,
        "candidata",
        _proposta(
            limpo, "Relatório de gastos por semana", "relatório semanal de gastos",
            "relatorios", outcome=OUTCOME_CANDIDATA, occurrences=4,
        ),
    )
    # texto idêntico ao primeiro, mas noutro módulo: não pode aparecer
    _com_embedding(
        limpo,
        "candidata",
        _proposta(limpo, "Outro módulo: " + titulo, descricao, "metas", outcome=OUTCOME_CANDIDATA),
    )
    origem_do_descarte = _proposta(
        limpo, "Relatório de investimentos por categoria", "x", "relatorios",
        outcome=OUTCOME_INCOERENTE,
    )
    descarte = DiscardedProposal(
        proposal_id=origem_do_descarte.id,
        reason_type="incoerente",
        reason_text="Investimentos estão fora do escopo.",
    )
    limpo.add(descarte)
    limpo.flush()
    save_embedding(
        "discarded", descarte.id, "Relatório de gastos por categoria de investimentos",
        session=limpo,
    )
    limpo.commit()

    mock_providers.responses = [P1B_NAO, P2A_OK, P2B]
    nova = _proposta(
        limpo, "Relatório de gastos por categoria do mês", "relatório de gastos", "relatorios"
    )
    pipeline.run(limpo, nova, ja_normalizada=True)

    p1b = _prompt(mock_providers, "# P1b")
    assert titulo in p1b
    assert "encaminhada à Zona Dinâmica" in p1b
    assert "“Relatório de gastos por semana” - candidata ou em andamento; 4 pedido(s)" in p1b
    assert "Relatório de investimentos por categoria" in p1b
    assert "Investimentos estão fora do escopo." in p1b
    assert "Outro módulo" not in p1b


@requires_db
def test_historico_do_modulo_respeita_top_k_e_nao_repete_implementada(limpo):
    for i in range(7):
        _com_embedding(
            limpo,
            "candidata",
            _proposta(limpo, f"Meta de economia {i}", "guardar dinheiro", "metas",
                      outcome=OUTCOME_CANDIDATA),
        )
    # proposta implementada aparece como item implementado, não como proposta
    entregue = _proposta(limpo, "Meta de economia entregue", "guardar dinheiro", "metas",
                         outcome="implementada")
    save_embedding("candidata", entregue.id, "Meta de economia\nguardar dinheiro", session=limpo)
    limpo.commit()

    from app.common.llm_client import embed

    hits = historico_do_modulo(
        "metas", vector=embed("Meta de economia\nguardar dinheiro"), top_k=5, session=limpo
    )

    assert len(hits) == 5
    assert all(h.kind == "proposta" for h in hits)
    assert entregue.id not in {h.ref_id for h in hits}
    assert [h.similarity for h in hits] == sorted((h.similarity for h in hits), reverse=True)


@requires_db
def test_redirecionada_entra_no_historico_mas_nao_na_memoria(limpo, mock_providers):
    """A zona do módulo já existe: o pedido vai ao UPA e fica lembrado para o P1b."""
    mock_providers.responses = [P1B_SIM]
    proposal = _proposta(limpo, "Ver gastos do meu jeito", "recorte pessoal", "dashboard")

    envelope = pipeline.run(limpo, proposal, ja_normalizada=True)

    assert envelope.outcome == OUTCOME_REDIRECIONADA
    limpo.refresh(proposal)
    assert proposal.embedding is not None
    assert proposal.feedback == envelope.detail
    # o L1 não a enxerga: um pedido igual não vira duplicata dela
    assert pipeline.consultar_memoria(limpo, proposal, list(proposal.embedding)) is None


@requires_db
def test_p2a_recebe_os_descartes_parecidos_como_precedente(limpo, mock_providers):
    recusada = _proposta(limpo, "Minerar criptomoedas no app", "renda extra", "geral",
                         outcome=OUTCOME_INCOERENTE)
    descarte = DiscardedProposal(
        proposal_id=recusada.id,
        reason_type="incoerente",
        reason_text="Mineração é geração de receita, fora do acompanhamento de gastos.",
    )
    limpo.add(descarte)
    limpo.flush()
    # 3 palavras em comum com a proposta nova: parecida (> 0.4), mas abaixo do L1
    save_embedding("discarded", descarte.id, "minerar criptomoedas usando computador",
                   session=limpo)
    limpo.commit()

    mock_providers.responses = [P1B_NAO, P2A_OK, P2B]
    nova = _proposta(limpo, "Minerar criptomoedas usando celular", "renda extra agora",
                     "transacoes")
    envelope = pipeline.run(limpo, nova, ja_normalizada=True)

    assert envelope.outcome == OUTCOME_CANDIDATA  # o precedente informa, não decide
    p2a = _prompt(mock_providers, "# P2a")
    assert "Minerar criptomoedas no app" in p2a
    assert "Mineração é geração de receita" in p2a


# --------------------------------------------------------------------------- #
# 3. Geração por IA: listas mais recentes e histórico de descartes no P3b
# --------------------------------------------------------------------------- #


@requires_db
def test_p3_e_p3b_leem_os_itens_mais_recentes_e_os_descartes(limpo, mock_providers):
    for i in range(45):
        limpo.add(ImplementedItem(title=f"Item-{i:02d}", description="d"))
    origem = _proposta(limpo, "Placar de economia", "x", "metas")
    limpo.add(DiscardedProposal(
        proposal_id=origem.id, reason_type="incoerente", reason_text="motivo do escopo"
    ))
    limpo.add(DiscardedProposal(
        proposal_id=origem.id, reason_type="duplicata", reason_text="motivo repetido"
    ))
    limpo.commit()

    mock_providers.responses = [json.dumps({"text": "x"}), json.dumps({"text": None})]
    generation.gerar_exploratoria(limpo)
    generation.gerar_lacunas(limpo)

    for cabecalho in ("# P3 ", "# P3b"):
        prompt = _prompt(mock_providers, cabecalho)
        assert "Item-44" in prompt and "Item-04" not in prompt
        assert prompt.index("Item-44") < prompt.index("Item-05")
        assert "Placar de economia: motivo do escopo" in prompt
        assert "motivo repetido" not in prompt


# --------------------------------------------------------------------------- #
# 4. Citação da Coerência conferida por código
# --------------------------------------------------------------------------- #


def test_trecho_confere_ignora_formatacao_mas_nao_parafrase():
    contexto = "## Fora de escopo\n- Investimentos, câmbio, múltiplas moedas.\n- Gamificação.\n"

    assert citacao.trecho_confere(LINHA_CAMBIO, contexto)
    assert citacao.trecho_confere(f"'{LINHA_CAMBIO}'", contexto)
    assert citacao.trecho_confere("- **Investimentos**, câmbio,\n múltiplas moedas", contexto)
    assert citacao.trecho_confere("“Gamificação.”", contexto)

    assert not citacao.trecho_confere("Investimentos e câmbio", contexto)  # paráfrase
    assert not citacao.trecho_confere("moedas", contexto)  # curto demais
    assert not citacao.trecho_confere(contexto * 5, contexto * 5)  # a seção inteira
    assert not citacao.trecho_confere(None, contexto)


@requires_db
def test_cenario_do_seed_cripto_continua_descartado(limpo, mock_providers):
    """A linha do `project-context` da semente sustenta o descarte, com citação."""
    from app.common import context_store

    semente = (context_store.SEMENTE / "project-context.md").read_text(encoding="utf-8")
    assert LINHA_CAMBIO in semente

    # módulo "geral" não tem zona: não há P1b
    mock_providers.responses = [_p2a_incoerente(f"'{LINHA_CAMBIO}'")]
    proposal = _proposta(
        limpo, "Minerar criptomoedas no app", "usar o computador para minerar", "geral"
    )

    envelope = pipeline.run(limpo, proposal, ja_normalizada=True)

    assert envelope.outcome == OUTCOME_INCOERENTE
    assert LINHA_CAMBIO in envelope.detail
    descarte = limpo.execute(
        select(DiscardedProposal).where(DiscardedProposal.proposal_id == proposal.id)
    ).scalar_one()
    assert descarte.cited_excerpt == f"'{LINHA_CAMBIO}'"
    assert LINHA_CAMBIO in descarte.reason_text
    assert descarte.embedding is not None
    assert limpo.query(Task).count() == 0


@pytest.mark.parametrize(
    ("trecho", "esperado"),
    [
        ("Mineração de criptomoedas é proibida.", "não foi encontrada"),
        (None, "não citou"),
        # citar o motivo de um precedente não vale: o trecho tem que vir do contexto
        ("Mineração é geração de receita, fora do acompanhamento de gastos.", "não foi encontrada"),
    ],
)
@requires_db
def test_violacao_sem_citacao_conferivel_vira_candidata_incerta(
    limpo, mock_providers, trecho, esperado
):
    mock_providers.responses = [_p2a_incoerente(trecho), P2B]
    proposal = _proposta(limpo, "Minerar criptomoedas no app", "renda extra", "geral")

    envelope = pipeline.run(limpo, proposal, ja_normalizada=True)

    assert envelope.outcome == OUTCOME_CANDIDATA
    assert envelope.uncertainty is True
    assert "Uma pessoa vai confirmar" in envelope.detail
    task = limpo.get(Task, envelope.task_id)
    assert task.uncertainty is True  # P2B sozinho não marcaria (confiança 0.8)
    nota = limpo.execute(
        select(TaskStateHistory.note).where(TaskStateHistory.task_id == task.id)
    ).scalar_one()
    assert "filtro de coerência alegou violação" in nota
    assert esperado in nota
    assert limpo.execute(
        select(func.count()).select_from(DiscardedProposal)
        .where(DiscardedProposal.proposal_id == proposal.id)
    ).scalar_one() == 0


@requires_db
def test_marcador_de_incerteza_segue_a_regra_de_valor_e_esforco(limpo, mock_providers):
    """Pouco valor para muito esforço também é incerteza, mesmo com confiança alta."""
    mock_providers.responses = [
        P1B_NAO,
        P2A_OK,
        json.dumps({"impact": 2, "complexity": 4, "confidence": 0.9, "risk_tier": "baixo"}),
    ]
    envelope = pipeline.run(
        limpo, _proposta(limpo, "Trocar fonte", "x", "dashboard"), ja_normalizada=True
    )

    assert limpo.get(Task, envelope.task_id).uncertainty is True


# --------------------------------------------------------------------------- #
# 5. Urgência inicial de candidata nova
# --------------------------------------------------------------------------- #


@requires_db
def test_candidata_nova_nasce_com_a_urgencia_dos_incidentes_abertos(limpo, mock_providers):
    limpo.add_all(
        [
            Incident(title="fora do ar", severity="alto", module="transacoes"),
            Incident(title="lento", severity="medio", module="transacoes"),
            Incident(title="já resolvido", severity="alto", module="transacoes", resolved=True),
            Incident(title="outro módulo", severity="alto", module="metas"),
        ]
    )
    limpo.commit()

    mock_providers.responses = [P1B_NAO, P2A_OK, P2B]
    envelope = pipeline.run(
        limpo,
        _proposta(limpo, "Exportar transações", "csv", "transacoes"),
        ja_normalizada=True,
    )

    task = limpo.get(Task, envelope.task_id)
    assert task.urgency_score == pytest.approx(4.0)  # alto 3 + medio 1
    nota = limpo.execute(
        select(TaskStateHistory.note).where(TaskStateHistory.task_id == task.id)
    ).scalar_one()
    assert "Urgência inicial 4" in nota


@requires_db
def test_sem_incidente_aberto_a_urgencia_comeca_em_zero(limpo, mock_providers):
    mock_providers.responses = [P1B_NAO, P2A_OK, P2B]
    envelope = pipeline.run(
        limpo, _proposta(limpo, "Exportar transações", "csv", "transacoes"), ja_normalizada=True
    )

    assert limpo.get(Task, envelope.task_id).urgency_score == 0.0
