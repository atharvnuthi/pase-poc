"""Ciclo de Auditoria - o loop de manutenção sobre o código (SPEC-04 §8).

    docker compose exec pase-core python -m app.jobs.audit

Ou, por acionamento humano, `POST /api/jobs/auditoria` (botão na tela Sistema).

Lê o código-fonte do client-backend e procura um ponto de refatoração ou
inconsistência que valha virar tarefa. O achado entra como proposta de
engenharia, com autor fixo `PASE Audit` - sempre autorizado, porque a
autorização aqui é do próprio sistema.

Distinto da Reavaliação Cíclica (SPEC-03 §5), que lê o **histórico de decisões**.
Este lê **código**. São dois insumos diferentes e não podem ser fundidos num job
só sem perder a distinção que o modelo estabelece.
"""

from __future__ import annotations

import logging
import sys

from app.common import prompts
from app.common.db import session_scope
from app.common.llm_client import chat as llm_chat
from app.execution import context
from app.task_layer import pipeline
from app.task_layer.models import Proposal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pase.jobs.audit")

AUTOR = "PASE Audit"

SCHEMA_P10 = {
    "type": "object",
    "properties": {"finding": {"type": ["string", "null"]}},
    "required": ["finding"],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}


def varrer() -> str | None:
    """P10 - um achado acionável, ou nada."""
    content, usage = llm_chat(
        [prompts.system_message("P10", source_tree=context.source_tree()), GO],
        json_schema=SCHEMA_P10,
        temperature=0.2,
        tags={"prompt_id": "P10", "fase": "auditoria"},
    )
    logger.info("P10 concluído (trace=%s)", usage["trace_id"])
    return content.get("finding")


def executar() -> dict:
    """Uma rodada de auditoria. Devolve o resumo que o painel mostra."""
    achado = varrer()

    if not achado:
        print("[auditoria] nada relevante para propor agora.")
        return {
            "propostas_geradas": 0,
            "achado": None,
            "resumo": "nada relevante para propor agora",
        }

    print(f"[auditoria] achado: {achado}\n")

    with session_scope() as session:
        # `type=engenharia` com autor autorizado: segue o bypass do SPEC-03 §4,
        # pulando Memória e Coerência e indo direto à Qualificação.
        proposta = Proposal(
            origin="auditoria",
            type="engenharia",
            author=AUTOR,
            raw_text=achado,
        )
        session.add(proposta)
        session.flush()

        envelope = pipeline.run(session, proposta)

        print(f"  proposta ....: #{proposta.id} (origin=auditoria)")
        print(f"  título ......: {proposta.title}")
        print(f"  desfecho ....: {envelope.outcome}")
        if envelope.task_id:
            print(f"  task ........: #{envelope.task_id} risco={envelope.risk_tier}")
        print(f"  detalhe .....: {envelope.detail}")

        resultado = {
            "propostas_geradas": 1,
            "achado": achado,
            "proposta_id": proposta.id,
            "titulo": proposta.title,
            "desfecho": envelope.outcome,
            "task_id": envelope.task_id,
            "resumo": f"proposta #{proposta.id} gerada ({envelope.outcome})",
        }

    return resultado


def run() -> int:
    """Entrada da linha de comando: quantas propostas a rodada gerou."""
    return executar()["propostas_geradas"]


if __name__ == "__main__":
    sys.exit(0 if run() >= 0 else 1)
