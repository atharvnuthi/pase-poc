"""Reavaliação Cíclica - o loop de manutenção sobre o que já foi recusado (SPEC-03 §5).

    docker compose exec pase-core python -m app.jobs.reevaluation

Ou, por acionamento humano, `POST /api/jobs/reavaliacao` (botão na tela Sistema).

Relê os descartes por incoerência e pergunta ao P9 se o motivo original ainda
vale diante do contexto de hoje (documentos do banco). Um "não" reinsere a proposta no
funil, com referência ao descarte que a originou.

Só lê descartes `incoerente`: reavaliar duplicata não faz sentido, porque a
implementação que causou o descarte continua existindo (SPEC-03 §5.1).

Distinto do Ciclo de Auditoria (SPEC-04 §8), que lê **código-fonte**. Este lê
**histórico de decisões**. São dois insumos diferentes e não podem ser fundidos
sem perder a distinção que o modelo estabelece.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from app.common import prompts
from app.common.db import session_scope
from app.common.llm_client import chat as llm_chat
from app.task_layer import pipeline
from app.task_layer.models import DiscardedProposal, Proposal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pase.jobs.reevaluation")

SCHEMA_P9 = {
    "type": "object",
    "properties": {
        "evidence": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["evidence", "reasoning"],
}

#: Uma restrição do contexto cabe numa linha. Bloco grande é o modelo colando a
#: seção inteira para "provar" qualquer coisa.
EVIDENCIA_MAX_CHARS = 250


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().split())


def evidencia_confere(evidence: str | None, contexto: str) -> bool:
    """A citação do modelo é uma linha real do contexto atual?

    Verificação determinística sobre a saída do LLM, no espírito do SPEC-00 §5: a
    máquina confere antes de qualquer humano olhar. O veredito não vem do modelo -
    ele aponta a linha, o código decide. Sem isto o P9 confabulava de dois jeitos:
    lia a restrição citada entre aspas dentro do próprio motivo do descarte e
    dizia tê-la encontrado no contexto; ou colava a seção inteira do documento,
    verdadeira mas sem relação com a proposta.
    """
    if not evidence:
        return False

    citacao = evidence.strip()
    if not citacao or "\n" in citacao or len(citacao) > EVIDENCIA_MAX_CHARS:
        return False

    return _normalizar(citacao) in _normalizar(contexto)

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}


def analisar_deriva(titulo: str, descricao: str, motivo: str, contexto: str) -> dict:
    """P9 - o motivo do descarte ainda se sustenta no contexto atual?"""
    content, usage = llm_chat(
        [
            prompts.system_message(
                "P9",
                title=titulo,
                description=descricao,
                reason=motivo,
                project_context=contexto,
            ),
            GO,
        ],
        json_schema=SCHEMA_P9,
        temperature=0.1,
        tags={"prompt_id": "P9", "fase": "reavaliacao_ciclica"},
    )
    return {**content, "trace_id": usage["trace_id"]}


def run() -> int:
    """Entrada da linha de comando: quantas propostas voltaram ao funil."""
    return executar()["reinseridas"]


def executar() -> dict:
    """Uma rodada de reavaliação. Devolve o resumo que o painel mostra."""
    contexto = prompts.load_project_context()
    reinseridas = 0
    analisados = 0
    propostas: list[dict] = []

    with session_scope() as session:
        # Descarte já reavaliado não volta à fila: a proposta reinserida aponta
        # para ele em `source_discard_id`, e reavaliar de novo faria o job
        # oscilar para sempre entre reinserir e redescartar.
        ja_reavaliados = set(
            session.execute(
                select(Proposal.source_discard_id).where(
                    Proposal.source_discard_id.is_not(None)
                )
            )
            .scalars()
            .all()
        )

        descartes = [
            d
            for d in session.execute(
                select(DiscardedProposal)
                .where(DiscardedProposal.reason_type == "incoerente")
                .order_by(DiscardedProposal.id)
            )
            .scalars()
            .all()
            if d.id not in ja_reavaliados
        ]

        if not descartes:
            print("[reavaliação] nenhum descarte por incoerência no histórico.")
            return {
                "analisados": 0,
                "reinseridas": 0,
                "propostas": [],
                "resumo": "nenhum descarte por incoerência a reavaliar",
            }

        print(f"[reavaliação] analisando {len(descartes)} descarte(s) por incoerência\n")

        for descarte in descartes:
            analisados += 1
            original = (
                session.get(Proposal, descarte.proposal_id) if descarte.proposal_id else None
            )
            titulo = original.title if original else descarte.reason_text[:80]
            descricao = original.description if original else descarte.reason_text

            veredito = analisar_deriva(titulo, descricao, descarte.reason_text, contexto)
            evidencia = veredito.get("evidence")
            # o veredito é do código, não do modelo: a recusa só se mantém se a
            # linha apontada existir mesmo no contexto de hoje
            ainda_vale = evidencia_confere(evidencia, contexto)

            print(f"  #{descarte.id} {titulo}")
            print(f"     recusa ainda válida: {ainda_vale}")
            print(f"     evidência .........: {evidencia if evidencia else '(nenhuma)'}")
            print(f"     razão .............: {veredito['reasoning']}")

            if ainda_vale:
                continue

            # A recusa caiu: o descarte deixa de valer como memória, senão a
            # proposta reinserida bateria como duplicata contra ele mesmo no L1.
            # A linha permanece para a trilha de auditoria - só sai da busca vetorial.
            descarte.embedding = None
            session.add(descarte)
            session.flush()

            nova = Proposal(
                origin="reavaliacao",
                raw_text=f"{titulo}. {descricao}",
                source_discard_id=descarte.id,
                author="PASE Reavaliação Cíclica",
            )
            session.add(nova)
            session.flush()

            envelope = pipeline.run(session, nova)
            reinseridas += 1
            propostas.append(
                {
                    "descarte_id": descarte.id,
                    "proposta_id": nova.id,
                    "titulo": titulo,
                    "desfecho": envelope.outcome,
                    "task_id": envelope.task_id,
                }
            )
            print(f"     reinserida ........: proposta #{nova.id} → {envelope.outcome}")
            if envelope.task_id:
                print(f"     task ..............: #{envelope.task_id}")
            print()

    print(f"[reavaliação] {reinseridas} proposta(s) reinserida(s) no funil.")
    return {
        "analisados": analisados,
        "reinseridas": reinseridas,
        "propostas": propostas,
        "resumo": f"{analisados} descarte(s) reavaliado(s), {reinseridas} reinserido(s) no funil",
    }


if __name__ == "__main__":
    sys.exit(0 if run() >= 0 else 1)
