"""Motor de Filtragem - o funil do SPEC-03 §3.

    registro → P1 normalização → avaliador de zona (P1b) → L1 memória
             → P2a coerência → P2b qualificação → Tarefa Candidata

Toda saída do funil é um desfecho explícito e persistido: candidata, descartada
por duplicata, descartada por incoerência ou redirecionada para o UPA. Nenhuma
proposta some pelo caminho - rastreabilidade integral é um dos quatro princípios
do modelo (SPEC-00 §2).

Os prompts do funil não recebem a memória inteira: recebem os itens mais parecidos
com a proposta em análise, recuperados por busca vetorial (monografia §4.3.5). O
P1b lê os pedidos parecidos do mesmo módulo; o P2a, os descartes parecidos com o
motivo de cada um.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import prompts
from app.common.config import settings
from app.common.events import publish
from app.common.llm_client import LLMError, embed
from app.common.llm_client import chat as llm_chat
from app.common.vector_store import (
    Lembranca,
    SearchHit,
    find_duplicate,
    historico_do_modulo,
    precedentes_de_descarte,
    save_embedding,
)
from app.task_layer import citacao
from app.task_layer.models import (
    OUTCOME_CANDIDATA,
    OUTCOME_DUPLICATA,
    OUTCOME_INCOERENTE,
    OUTCOME_REDIRECIONADA,
    REASON_DUPLICATA,
    REASON_INCOERENTE,
    DiscardedProposal,
    ImplementedItem,
    Proposal,
    Task,
    TaskStateHistory,
)
from app.task_layer.schemas import MatchedRef, ProposalEnvelope
from app.task_layer.uncertainty import incerteza
from app.task_layer.urgencia import urgencia_inicial
from app.upa import contracts

logger = logging.getLogger("pase.task_layer")

#: Zonas Dinâmicas só fazem sentido onde há superfície de interface para personalizar.
MODULOS_COM_ZONA = tuple(contracts.ZONA_DO_MODULO)

#: Memória consultada pelo L1: implementadas ∪ candidatas ∪ descartadas (SPEC-03 §3.4).
KINDS_MEMORIA = ("implemented", "candidata", "discarded")

#: Recuperação para os prompts (RAG): quantos itens do histórico cada prompt lê, e
#: a similaridade abaixo da qual um item é só vizinho de assunto e fica de fora.
#: O piso é baixo de propósito - quem corta é o top-k; o piso só tira o ruído.
RAG_TOP_K = 5
RAG_SIMILARIDADE_MINIMA = 0.4

#: Como cada desfecho aparece para o modelo no histórico recuperado.
SITUACAO_NO_HISTORICO = {
    "candidata": "candidata ou em andamento",
    "redirecionada_zona": "encaminhada à Zona Dinâmica do módulo",
    "implementada": "já implementada",
    "recusada_pelo_humano": "recusada na homologação",
    "revertida": "implementada e depois revertida",
    "incoerente": "descartada por incoerência",
    "recusa_humana": "recusada por uma pessoa",
}

# --------------------------------------------------------------------------- #
# Schemas de saída dos prompts
# --------------------------------------------------------------------------- #

MODULOS = ["dashboard", "transacoes", "relatorios", "orcamentos", "metas", "suporte", "geral"]

SCHEMA_P1 = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "module": {"type": "string", "enum": MODULOS},
    },
    "required": ["title", "description", "module"],
}

SCHEMA_P1B = {
    "type": "object",
    "properties": {"requires_zone": {"type": "boolean"}, "reasoning": {"type": "string"}},
    "required": ["requires_zone", "reasoning"],
}

SCHEMA_P2A = {
    "type": "object",
    "properties": {
        "coherent": {"type": "boolean"},
        "reason": {"type": "string"},
        # cópia literal do contexto - o código confere antes de descartar
        "trecho_violado": {"type": ["string", "null"]},
        "needs_adjustment": {"type": "boolean"},
        "adjusted_title": {"type": "string"},
        "adjusted_description": {"type": "string"},
    },
    # `trecho_violado` fica fora de `required`: a ausência já tem tratamento -
    # alegação sem citação não descarta.
    "required": ["coherent", "reason", "needs_adjustment"],
}

SCHEMA_P2B = {
    "type": "object",
    "properties": {
        "impact": {"type": "integer"},
        "complexity": {"type": "integer"},
        "confidence": {"type": "number"},
        "risk_tier": {"type": "string", "enum": ["baixo", "medio", "alto"]},
    },
    "required": ["impact", "complexity", "confidence", "risk_tier"],
}


class PipelineError(RuntimeError):
    """Falha técnica do funil. Nunca trava o pipeline: vira descarte com motivo."""


#: O prompt vai como system; o turno do usuário apenas dispara a produção do JSON.
GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}


def _mensagens(prompt_id: str, **variaveis) -> list[dict[str, str]]:
    return [prompts.system_message(prompt_id, **variaveis), GO]


# --------------------------------------------------------------------------- #
# Etapas
# --------------------------------------------------------------------------- #


def normalizar(proposal: Proposal) -> dict:
    """P1 - texto bruto → {title, description, module}."""
    content, usage = llm_chat(
        _mensagens("P1", raw_text=proposal.raw_text),
        json_schema=SCHEMA_P1,
        temperature=0.1,
        tags={"proposal_id": proposal.id, "prompt_id": "P1", "fase": "normalizacao"},
    )
    return {**content, "trace_id": usage["trace_id"]}


def _encurtar(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _formatar_historico(itens: list[Lembranca]) -> str:
    """Pedidos parecidos do módulo, como o P1b os lê."""
    if not itens:
        return "(nenhum pedido parecido neste módulo)"
    linhas = []
    for item in itens:
        situacao = SITUACAO_NO_HISTORICO.get(item.outcome, item.outcome or "registrada")
        linha = (
            f"- “{item.title or '(sem título)'}” - {situacao}; "
            f"{item.occurrences} pedido(s); similaridade {item.similarity:.2f}"
        )
        if item.reason:
            linha += f". Motivo: {_encurtar(item.reason, 240)}"
        linhas.append(linha)
    return "\n".join(linhas)


def _formatar_precedentes(itens: list[Lembranca]) -> str:
    """Descartes parecidos, com o motivo registrado - como o P2a os lê."""
    if not itens:
        return "(nenhum descarte parecido com esta proposta)"
    return "\n".join(
        f"- “{item.title or '(sem título)'}” - "
        f"{SITUACAO_NO_HISTORICO.get(item.outcome, item.outcome)}, "
        f"similaridade {item.similarity:.2f}. Motivo: {_encurtar(item.reason, 400)}"
        for item in itens
    )


def zona_homologada(session: Session, module: str) -> bool:
    """Existe Zona Dinâmica já homologada cobrindo este módulo?

    O SPEC-05 §1 não cria tabela de zonas, então o registro é a própria trilha de
    tarefas: uma zona existe quando uma task de `output_type=zona_dinamica`
    naquele módulo foi aprovada na Homologação (SPEC-04 §5).
    """
    if module in contracts.ZONA_DO_MODULO:
        return True  # a zona já faz parte do produto (registro de zonas do UPA)
    return (
        session.execute(
            select(Task.id)
            .where(Task.module == module)
            .where(Task.output_type == "zona_dinamica")
            .where(Task.status == "finalizada")
            .where(Task.final_outcome == "aprovada")
            .limit(1)
        ).first()
        is not None
    )


def avaliar_zona(session: Session, proposal: Proposal, vetor: list[float]) -> dict:
    """P1b - a demanda é homogênea (código) ou de cauda longa (zona)?

    Confronta a demanda com o histórico recente do mesmo módulo (monografia
    §4.3.3): o modelo recebe os `RAG_TOP_K` pedidos passados mais parecidos -
    candidatas, implementadas, descartadas e pedidos já encaminhados à zona -
    com o peso de cada um, e o peso da própria proposta (`occurrences`). Três
    tickets sobre a mesma dor são três sinais, e é essa frequência, somada à
    divergência entre o que cada um pede, que distingue cauda longa de pedido
    isolado.

    Consulta só de leitura: não descarta nem incrementa nada. O L1, logo
    adiante, é quem age.
    """
    historico = historico_do_modulo(
        proposal.module or "geral",
        vector=vetor,
        top_k=RAG_TOP_K,
        minimo=RAG_SIMILARIDADE_MINIMA,
        excluir_proposta=proposal.id,
        session=session,
    )
    content, usage = llm_chat(
        _mensagens(
            "P1b",
            title=proposal.title,
            description=proposal.description,
            module=proposal.module,
            occurrences=proposal.occurrences or 1,
            historico=_formatar_historico(historico),
        ),
        json_schema=SCHEMA_P1B,
        temperature=0.1,
        tags={"proposal_id": proposal.id, "prompt_id": "P1b", "fase": "avaliacao_zona"},
    )
    logger.info(
        "P1b proposta=%s requires_zone=%s (ocorrencias=%s, historico=%d)",
        proposal.id,
        content["requires_zone"],
        proposal.occurrences,
        len(historico),
    )
    return {**content, "historico": historico, "trace_id": usage["trace_id"]}


def consultar_memoria(
    session: Session, proposal: Proposal, vetor: list[float]
) -> SearchHit | None:
    """L1 - Memória Histórica. Devolve o match acima do limiar, se houver."""
    return find_duplicate("", KINDS_MEMORIA, session=session, vector=vetor)


def avaliar_coerencia(
    session: Session, proposal: Proposal, contexto: str, vetor: list[float]
) -> dict:
    """P2a - a proposta cabe neste produto?

    Além dos documentos de contexto, o modelo lê os `RAG_TOP_K` descartes mais
    parecidos com a proposta, com o motivo de cada um, como precedente. A
    citação que ele devolve (`trecho_violado`) é conferida só contra o contexto,
    nunca contra os precedentes: citar o motivo de um descarte antigo é
    exatamente a confabulação que a conferência existe para barrar.
    """
    precedentes = precedentes_de_descarte(
        vector=vetor, top_k=RAG_TOP_K, minimo=RAG_SIMILARIDADE_MINIMA, session=session
    )
    content, usage = llm_chat(
        _mensagens(
            "P2a",
            project_context=contexto,
            precedentes=_formatar_precedentes(precedentes),
            title=proposal.title,
            description=proposal.description,
            module=proposal.module,
        ),
        json_schema=SCHEMA_P2A,
        temperature=0.1,
        tags={"proposal_id": proposal.id, "prompt_id": "P2a", "fase": "coerencia"},
    )
    return {**content, "precedentes": precedentes, "trace_id": usage["trace_id"]}


def qualificar(proposal: Proposal) -> dict:
    """P2b - metadados de priorização. O peso da proposta entra no impacto."""
    content, usage = llm_chat(
        _mensagens(
            "P2b",
            title=proposal.title,
            description=proposal.description,
            module=proposal.module,
            output_type=proposal.output_type or "codigo_permanente",
            occurrences=proposal.occurrences or 1,
        ),
        json_schema=SCHEMA_P2B,
        temperature=0.2,
        tags={"proposal_id": proposal.id, "prompt_id": "P2b", "fase": "qualificacao"},
    )
    return {**content, "trace_id": usage["trace_id"]}


# --------------------------------------------------------------------------- #
# Desfechos
# --------------------------------------------------------------------------- #


def _registrar_duplicata(
    session: Session, proposal: Proposal, hit: SearchHit
) -> tuple[DiscardedProposal, int]:
    """Soma o peso da duplicata ao item que casou e registra o descarte.

    Monografia §4.3.4: uma duplicata não gera novo registro na base - ela
    incrementa a contagem de ocorrências do item existente. O incremento é o
    **peso** da proposta que chegou (`occurrences`), não 1: um grupo de três
    tickets que bate numa candidata são três pedidos a mais, não um. Vale para
    os três tipos da memória - implementada, descartada e candidata (inclusive a
    que já está em andamento, cuja proposta segue `candidata` até a tarefa
    acabar). Esse número é o sinal de recorrência que o Avaliador de Zonas lê.

    A linha de descarte criada aqui é só auditoria: fica **sem embedding**, então
    a base vetorial não cresce, mas o painel tem o que mostrar em Descartadas.
    """
    peso = proposal.occurrences or 1
    contador = peso
    if hit.kind == "candidata":
        alvo_proposta = session.get(Proposal, hit.ref_id)
        if alvo_proposta is not None:
            alvo_proposta.occurrences = (alvo_proposta.occurrences or 1) + peso
            contador = alvo_proposta.occurrences
            session.add(alvo_proposta)
    else:
        modelo = ImplementedItem if hit.kind == "implemented" else DiscardedProposal
        alvo = session.get(modelo, hit.ref_id)
        if alvo is not None:
            alvo.duplicate_count = (alvo.duplicate_count or 1) + peso
            alvo.duplicate_refs = [*(alvo.duplicate_refs or []), proposal.id]
            contador = alvo.duplicate_count
            session.add(alvo)

    descarte = DiscardedProposal(
        proposal_id=proposal.id,
        reason_type=REASON_DUPLICATA,
        reason_text=f"Já coberto por: {hit.title}",
        matched_ref=f"{hit.kind}#{hit.ref_id}",
        duplicate_count=1,
        embedding=None,  # duplicata nunca entra na memória vetorial
    )
    session.add(descarte)
    return descarte, contador


def _registrar_incoerencia(
    session: Session,
    proposal: Proposal,
    motivo: str,
    vetor: list[float] | None,
    trecho: str | None = None,
) -> DiscardedProposal:
    """Descarte por incoerência entra na memória **com** embedding.

    É o que permite barrar variações da mesma ideia depois (critério 3) e o que
    a Reavaliação Cíclica relê quando o contexto do projeto muda.
    """
    descarte = DiscardedProposal(
        proposal_id=proposal.id,
        reason_type=REASON_INCOERENTE,
        reason_text=motivo,
        cited_excerpt=trecho,
        duplicate_count=proposal.occurrences or 1,
        embedding=vetor,
    )
    session.add(descarte)
    return descarte


def _motivo_com_trecho(motivo: str, trecho: str) -> str:
    """O motivo do descarte cita o trecho violado (monografia §4.3.4).

    Se o modelo já o citou no próprio motivo, não repete.
    """
    if citacao.trecho_confere(trecho, motivo):
        return motivo
    return f"{motivo.rstrip()} Trecho do contexto violado: “{trecho.strip()}”"


def _tipo_de_mudanca(proposal: Proposal) -> str:
    """Tipo no vocabulário de commit (`engineering-guidelines` §3 do contexto).

    Decide o prefixo da branch e da mensagem que o Executor vai escrever.
    Sugestão de engenharia é manutenção de infraestrutura, não funcionalidade
    para o usuário; auditoria é refatoração por definição. O resto começa como
    `feature` e pode ser corrigido no painel.
    """
    if proposal.origin == "auditoria":
        return "refactor"
    if proposal.type == "engenharia":
        return "chore"
    return "feature"


def _criar_task(
    session: Session,
    proposal: Proposal,
    metadados: dict,
    alerta_de_coerencia: str | None = None,
) -> Task:
    """Cria a Tarefa Candidata.

    O marcador de incerteza segue a regra fixa de `uncertainty.incerteza` e é
    forçado quando o filtro de coerência alegou uma violação que o código não
    conseguiu conferir: a decisão fica com uma pessoa, e o histórico diz por quê.
    A urgência nasce com o peso dos incidentes abertos no módulo.
    """
    impact = int(metadados["impact"])
    complexity = int(metadados["complexity"])
    confidence = float(metadados["confidence"])
    urgencia = urgencia_inicial(session, proposal.module)
    task = Task(
        proposal_id=proposal.id,
        title=proposal.title,
        description=proposal.description,
        module=proposal.module,
        output_type=proposal.output_type or "codigo_permanente",
        impact=impact,
        complexity=complexity,
        confidence=confidence,
        uncertainty=incerteza(impact, complexity, confidence) or alerta_de_coerencia is not None,
        risk_tier=metadados["risk_tier"],
        change_type=_tipo_de_mudanca(proposal),
        urgency_score=urgencia,
        status="candidata",
    )
    session.add(task)
    session.flush()

    nota = f"criada pelo Task Layer a partir da proposta #{proposal.id}"
    if (proposal.occurrences or 1) > 1:
        nota += f", que reúne {proposal.occurrences} pedidos"
    if urgencia:
        nota += f". Urgência inicial {urgencia:g} por incidente aberto no módulo"
    if alerta_de_coerencia:
        nota += f". {alerta_de_coerencia}"
    session.add(
        TaskStateHistory(task_id=task.id, from_status=None, to_status="candidata", note=nota)
    )
    return task


def _match_de_outro_tipo(proposal: Proposal, hit: SearchHit) -> bool:
    """O match é contra trabalho de natureza diferente do que a proposta pede?"""
    return proposal.output_type == "zona_dinamica" and hit.kind == "implemented"


def _detalhe_duplicata(hit: SearchHit) -> str:
    """Texto exibido ao usuário. Bater contra implementada e contra descarte são
    situações diferentes e merecem explicações diferentes."""
    if hit.kind == "implemented":
        return f"O FinTrack já faz isso: “{hit.title}”."
    if hit.kind == "discarded":
        return "Essa ideia já foi avaliada antes e não entrou no escopo do produto."
    return "Já existe uma sugestão equivalente em avaliação. Seu pedido foi somado a ela."


def _encaminhar_ao_upa(proposal: Proposal) -> str:
    """Faz o que a mensagem ao usuário promete: o UPA reage ao pedido.

    Antes, a proposta era marcada como redirecionada e o usuário era informado de que
    "foi encaminhada", mas o UPA só lê a navegação: nada consumia aquilo. Agora o texto
    vai ao gerador (P6) como dica para a zona do módulo, e a mensagem diz o que de fato
    aconteceu, inclusive quando não foi possível ajustar a área.
    """
    from app.upa import rule

    slot = contracts.ZONA_DO_MODULO.get(proposal.module or "")
    if slot is None:
        return (
            "Já existe uma área personalizável cobrindo isso, mas ela não aceita pedidos "
            "escritos. Sua sugestão ficou registrada."
        )
    if proposal.user_id is None:
        return (
            "Já existe uma área personalizável cobrindo isso. Como o pedido não veio de uma "
            "pessoa específica, ele ficou registrado, e a área continua se ajustando ao uso "
            "de cada um."
        )

    resultado = rule.gerar_por_pedido(proposal.user_id, slot, proposal.raw_text)
    tela = contracts.ZONAS[slot].tela
    if resultado.personalizou:
        return (
            f"Ajustamos a área personalizável da tela {tela} para você. Ela aparece na "
            "próxima vez que você abrir essa tela."
        )
    motivo = resultado.motivo or "nada do que a área aceita atende ao pedido"
    return (
        "Já existe uma área personalizável cobrindo isso, mas não conseguimos ajustá-la "
        f"agora ({motivo.rstrip('.')}). Seu pedido ficou registrado."
    )


def _envelope(proposal: Proposal, outcome: str, detail: str, **extra) -> ProposalEnvelope:
    return ProposalEnvelope(
        proposal_id=proposal.id,
        outcome=outcome,
        detail=detail,
        module=proposal.module,
        output_type=proposal.output_type,
        occurrences=proposal.occurrences or 1,
        **extra,
    )


def _responder(
    session: Session, proposal: Proposal, outcome: str, detail: str, **extra
) -> ProposalEnvelope:
    """Grava o desfecho e a resposta dada a quem pediu, e avisa o painel.

    A resposta fica na proposta (`feedback`) para o FinTrack mostrá-la de volta
    ao usuário depois, e não só no modal que fecha (`GET /api/proposals/mine`).
    """
    proposal.outcome = outcome
    proposal.feedback = detail
    session.commit()
    evento = {"proposal_id": proposal.id, "outcome": outcome}
    if extra.get("task_id"):
        evento["task_id"] = extra["task_id"]
    publish("proposal.processed", evento)
    return _envelope(proposal, outcome, detail, **extra)


# --------------------------------------------------------------------------- #
# Funil
# --------------------------------------------------------------------------- #


def run(
    session: Session,
    proposal: Proposal,
    *,
    ja_normalizada: bool = False,
    recorrencia: int | None = None,
) -> ProposalEnvelope:
    """Roda o funil inteiro sobre uma proposta já registrada.

    `ja_normalizada=True` para a Captação Passiva, cujo P0 já produziu
    title/description/module. `recorrencia` é o número de observações correlatas
    que originaram a proposta - o tamanho do grupo do P0a - e vira o peso dela
    (`occurrences`): três pessoas relatando a mesma dor geram uma única demanda,
    com o peso de três ocorrências (monografia §4.3.1).
    """
    if recorrencia is not None:
        proposal.occurrences = max(1, int(recorrencia))
    try:
        return _run(session, proposal, ja_normalizada=ja_normalizada)
    except LLMError as exc:
        # SPEC-08 §1: falha de LLM descarta a proposta com motivo técnico,
        # nunca trava o pipeline.
        logger.warning("proposta %s descartada por falha técnica: %s", proposal.id, exc)
        _registrar_incoerencia(session, proposal, f"falha técnica no funil: {exc}", None)
        return _responder(
            session,
            proposal,
            OUTCOME_INCOERENTE,
            "Não consegui avaliar sua sugestão agora. Ela ficou registrada para revisão.",
        )


def _run(session: Session, proposal: Proposal, *, ja_normalizada: bool) -> ProposalEnvelope:
    # --- 1. Normalização (P1) --------------------------------------------- #
    if not ja_normalizada:
        normalizada = normalizar(proposal)
        proposal.title = normalizada["title"][:200]
        proposal.description = normalizada["description"]
        proposal.module = normalizada["module"]
        session.flush()

    bypass = proposal.type == "engenharia"
    vetor = embed(f"{proposal.title}\n{proposal.description}")

    # --- 2. Avaliador de Zonas Dinâmicas (P1b) ---------------------------- #
    proposal.output_type = "codigo_permanente"
    if not bypass and proposal.module in MODULOS_COM_ZONA:
        zona = avaliar_zona(session, proposal, vetor)
        if zona["requires_zone"]:
            if zona_homologada(session, proposal.module):
                # Pedido fora do escopo não vira sinal para o UPA: a zona só personaliza
                # o que já existe, então a coerência vale antes de qualquer desvio. Só
                # descarta com a citação conferida por código, como no filtro normal.
                contexto = prompts.load_project_context()
                coerencia = avaliar_coerencia(session, proposal, contexto, vetor)
                trecho = (coerencia.get("trecho_violado") or "").strip()
                if not coerencia["coherent"] and citacao.trecho_confere(trecho, contexto):
                    motivo = _motivo_com_trecho(coerencia["reason"], trecho)
                    _registrar_incoerencia(session, proposal, motivo, vetor, trecho)
                    return _responder(session, proposal, OUTCOME_INCOERENTE, motivo)
                # Vira sinal para o UPA avaliar, não tarefa de código (SPEC-03 §3.3).
                # O pedido entra no histórico do módulo com embedding: o próximo
                # P1b sobre o mesmo assunto vê que demandas assim já foram para a zona.
                proposal.outcome = OUTCOME_REDIRECIONADA
                session.flush()
                save_embedding("redirecionada", proposal.id, "", session=session, vector=vetor)
                session.commit()
                return _responder(
                    session, proposal, OUTCOME_REDIRECIONADA, _encaminhar_ao_upa(proposal)
                )
            proposal.output_type = "zona_dinamica"
        session.flush()

    # --- 3 e 4. Memória (L1) e Coerência (P2a), com revalidação ----------- #
    #: Preenchido quando o P2a alegou violação sem citação conferível.
    alerta_de_coerencia: str | None = None
    if not bypass:
        contexto = prompts.load_project_context()
        ajustes = 0

        while True:
            hit = consultar_memoria(session, proposal, vetor)

            if hit is not None and _match_de_outro_tipo(proposal, hit):
                # Uma Zona Dinâmica não duplica a funcionalidade sobre a qual ela
                # se apoia: ela personaliza o que já existe. Comparar as duas é
                # comparar trabalhos de natureza diferente - e, se valesse, nenhuma
                # zona jamais passaria pelo L1, já que toda zona nasce em cima de
                # algo implementado (a `resumo_financeiro` do SPEC-05 senta sobre o
                # resumo do dashboard). A recorrência já foi contabilizada no P1b.
                logger.info(
                    "L1: match %s#%s ignorado - proposta %s é zona dinâmica sobre "
                    "funcionalidade existente",
                    hit.kind,
                    hit.ref_id,
                    proposal.id,
                )
                hit = None

            if hit is not None:
                _, contador = _registrar_duplicata(session, proposal, hit)
                return _responder(
                    session,
                    proposal,
                    OUTCOME_DUPLICATA,
                    _detalhe_duplicata(hit),
                    matched_ref=MatchedRef(
                        kind=hit.kind,
                        ref_id=hit.ref_id,
                        title=hit.title,
                        similarity=round(hit.similarity, 4),
                    ),
                    duplicate_count=contador,
                )

            coerencia = avaliar_coerencia(session, proposal, contexto, vetor)

            if not coerencia["coherent"]:
                trecho = (coerencia.get("trecho_violado") or "").strip()
                if citacao.trecho_confere(trecho, contexto):
                    # O modelo apontou a regra; o código conferiu que ela existe.
                    motivo = _motivo_com_trecho(coerencia["reason"], trecho)
                    _registrar_incoerencia(session, proposal, motivo, vetor, trecho)
                    return _responder(session, proposal, OUTCOME_INCOERENTE, motivo)

                # Alegação sem evidência conferível: descartar seria confiar no
                # veredito do modelo sobre o próprio texto. A proposta segue, com o
                # marcador de incerteza, e uma pessoa decide (monografia §4.2).
                logger.warning(
                    "P2a: proposta %s alegada incoerente, mas o trecho citado não "
                    "existe no contexto: %r",
                    proposal.id,
                    trecho,
                )
                if trecho:
                    falha = (
                        f"a citação “{_encurtar(trecho, 200)}” não foi encontrada nos "
                        "documentos de contexto"
                    )
                else:
                    falha = "ele não citou trecho nenhum do contexto"
                alerta_de_coerencia = (
                    "O filtro de coerência alegou violação do contexto "
                    f"(“{_encurtar(coerencia['reason'], 300)}”), mas {falha}. "
                    "Uma pessoa decide se a proposta cabe no produto."
                )
                break

            if not coerencia["needs_adjustment"]:
                break

            if ajustes >= settings.coherence_max_adjustments:
                # Teto de tentativas: nenhum loop de correção roda indefinidamente
                # (SPEC-00 §4).
                _registrar_incoerencia(session, proposal, "ajuste não convergiu", vetor)
                return _responder(
                    session,
                    proposal,
                    OUTCOME_INCOERENTE,
                    "Não consegui encaixar a sugestão no escopo do produto.",
                )

            ajustes += 1
            proposal.title = (coerencia.get("adjusted_title") or proposal.title)[:200]
            proposal.description = coerencia.get("adjusted_description") or proposal.description
            # o ajuste mudou o texto: o embedding e a checagem de memória valem de novo
            vetor = embed(f"{proposal.title}\n{proposal.description}")
            session.flush()

    # --- 5. Qualificação (P2b) -------------------------------------------- #
    metadados = qualificar(proposal)

    if bypass and metadados["risk_tier"] == "baixo":
        # Engenharia mexe em infraestrutura por definição (SPEC-03 §4).
        metadados["risk_tier"] = "medio"

    proposal.outcome = OUTCOME_CANDIDATA
    session.flush()
    # a proposta entra na memória como candidata (kind "candidata" → tabela proposals)
    save_embedding("candidata", proposal.id, "", session=session, vector=vetor)

    task = _criar_task(session, proposal, metadados, alerta_de_coerencia)
    session.flush()

    detalhe = f"Sugestão aceita e registrada como tarefa candidata #{task.id}."
    if alerta_de_coerencia:
        detalhe = (
            f"Sugestão registrada como tarefa candidata #{task.id}. Uma pessoa vai "
            "confirmar se ela cabe no produto."
        )
    envelope = _responder(
        session,
        proposal,
        OUTCOME_CANDIDATA,
        detalhe,
        task_id=task.id,
        risk_tier=task.risk_tier,
        uncertainty=task.uncertainty,
    )
    publish("task.created", {"task_id": task.id, "title": task.title})
    return envelope
