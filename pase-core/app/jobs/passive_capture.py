"""Captação Passiva - a origem de demanda que ninguém digitou (SPEC-03 §2).

    docker compose exec pase-core python -m app.jobs.passive_capture

Lê os tickets de suporte do FinTrack e roda o P0 para converter reclamação
informal em proposta estruturada. Tickets que falam da mesma dor são tratados
como um único sinal - é isso que permite ao P1b enxergar recorrência e decidir
por Zona Dinâmica em vez de código fixo.

Deliberadamente distinto da telemetria de interface (SPEC-05), que nunca passa
por aqui: tickets alimentam evolução de código, cliques alimentam personalização.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

import httpx
from sqlalchemy import select

from app.common import prompts
from app.common.config import settings
from app.common.db import session_scope
from app.common.llm_client import chat as llm_chat
from app.task_layer import pipeline
from app.task_layer.models import Proposal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pase.jobs.passive")

SCHEMA_P0 = {
    "type": "object",
    "properties": {
        "title": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "module": {"type": ["string", "null"]},
    },
    "required": ["title", "description", "module"],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}

SCHEMA_P0A = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string"},
                    "ticket_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["theme", "ticket_ids"],
            },
        }
    },
    "required": ["groups"],
}


def agrupar_correlacionados(tickets: list[dict]) -> list[tuple[str, list[dict]]]:
    """Separa os tickets por dor relatada (SPEC-03 §2.2, "lote de correlacionados").

    O agrupamento é feito pelo modelo, não por similaridade vetorial. A medição
    com os tickets reais do seed mostrou por quê: reclamações sobre a mesma dor,
    escritas de formas diferentes, ficaram entre 0.47 e 0.61 de cosseno - abaixo
    de pares de temas distintos. Em texto curto e coloquial, o embedding não
    separa tema, e nenhum limiar resolveria isso.

    Sem agrupamento correto, o P0 recebe temas misturados e produz uma proposta
    que não corresponde a dor nenhuma.
    """
    por_id = {t["id"]: t for t in tickets}
    listagem = "\n".join(f"- id {t['id']}: {t['text']}" for t in tickets)

    content, usage = llm_chat(
        [prompts.system_message("P0a", tickets=listagem), GO],
        json_schema=SCHEMA_P0A,
        temperature=0.1,
        tags={"prompt_id": "P0a", "fase": "captacao_passiva"},
    )
    logger.info("P0a agrupou %d tickets (trace=%s)", len(tickets), usage["trace_id"])

    grupos: list[tuple[str, list[dict]]] = []
    vistos: set[int] = set()
    for grupo in content["groups"]:
        membros = [por_id[i] for i in grupo["ticket_ids"] if i in por_id and i not in vistos]
        if membros:
            vistos.update(t["id"] for t in membros)
            grupos.append((grupo["theme"], membros))

    # rede de segurança: ticket que o modelo esqueceu vira grupo próprio
    for ticket in tickets:
        if ticket["id"] not in vistos:
            grupos.append(("(sem tema atribuído)", [ticket]))

    return grupos


def buscar_tickets() -> list[dict]:
    url = f"{settings.client_api_url}/tickets"
    with httpx.Client(timeout=15) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _ja_processado(session, ticket_id: int) -> bool:
    """Marcamos a origem do ticket no raw_text para não reprocessar em nova execução."""
    marcador = f"[ticket#{ticket_id}]"
    return (
        session.execute(
            select(Proposal.id).where(Proposal.raw_text.contains(marcador)).limit(1)
        ).first()
        is not None
    )


def extrair_intencao(tickets: list[dict]) -> dict:
    """P0 - reclamações informais → proposta estruturada (ou nada)."""
    texto = "\n".join(f"- {t['text']}" for t in tickets)
    content, usage = llm_chat(
        [prompts.system_message("P0", tickets=texto), GO],
        json_schema=SCHEMA_P0,
        temperature=0.1,
        tags={"prompt_id": "P0", "fase": "captacao_passiva"},
    )
    logger.info("P0 sobre %d ticket(s) (trace=%s)", len(tickets), usage["trace_id"])
    return content


def run() -> int:
    tickets = buscar_tickets()
    logger.info("%d tickets lidos de %s", len(tickets), settings.client_api_url)

    if not tickets:
        print("[captação passiva] nenhum ticket para ler.")
        return 0

    processadas = 0
    with session_scope() as session:
        pendentes = [t for t in tickets if not _ja_processado(session, t["id"])]
        if not pendentes:
            print("[captação passiva] todos os tickets já foram processados.")
            return 0

        grupos = agrupar_correlacionados(pendentes)
        print(f"[captação passiva] {len(pendentes)} tickets → {len(grupos)} tema(s)\n")

        for tema, grupo in grupos:
            ids_legiveis = ", ".join(f"#{t['id']}" for t in grupo)
            print(f"  tema: {tema}  (tickets {ids_legiveis})")
            intencao = extrair_intencao(grupo)

            if not intencao.get("title"):
                print("     sem sinal acionável de melhoria neste tema.\n")
                continue

            marcadores = " ".join(f"[ticket#{t['id']}]" for t in grupo)
            proposal = Proposal(
                origin="passiva",
                raw_text=f"{marcadores} {' | '.join(t['text'] for t in grupo)}",
                title=intencao["title"][:200],
                description=intencao["description"],
                module=intencao["module"],
                author="PASE Captação Passiva",
            )
            session.add(proposal)
            session.flush()

            # três tickets sobre a mesma dor são três sinais, não um: é essa
            # frequência que o P1b usa para distinguir cauda longa de pedido isolado
            envelope = pipeline.run(
                session, proposal, ja_normalizada=True, recorrencia=len(grupo)
            )
            processadas += 1

            print(f"     proposta ....: #{proposal.id}")
            print(f"     título ......: {proposal.title}")
            print(f"     módulo ......: {proposal.module}")
            print(f"     desfecho ....: {envelope.outcome}")
            print(f"     output_type .: {envelope.output_type}")
            if envelope.task_id:
                print(f"     task ........: #{envelope.task_id}")
            print(f"     detalhe .....: {envelope.detail}")
            print()

    logger.info("job concluído em %s", datetime.now().isoformat(timespec="seconds"))
    return processadas


if __name__ == "__main__":
    sys.exit(0 if run() >= 0 else 1)
