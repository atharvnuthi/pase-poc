"""Rotas do UPA (`/api/upa/*`) - SPEC-05 §3.

Nenhum destes endpoints passa por gate humano, e isso é deliberado: o gate deste
loop é a validação de schema (SPEC-00 §1). O que o humano faz é auditar depois,
pela tela Zonas, e revogar o que não quiser - o operador pelo painel, a pessoa pela
própria zona ("voltar ao padrão").
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.db import get_session
from app.upa import contracts, rule
from app.upa.models import (
    REVOGADO_PELO_PAINEL,
    REVOGADO_PELO_USUARIO,
    TelemetryEvent,
    ZoneEvaluation,
    ZonePayload,
    ZoneViolation,
)

logger = logging.getLogger("pase.upa")

router = APIRouter(prefix="/api/upa", tags=["upa"])


class TelemetryIn(BaseModel):
    user_id: int
    event: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=256)


class ViolationIn(BaseModel):
    user_id: int
    slot: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1)
    raw_payload: dict | None = None


class SimulateIn(BaseModel):
    user_id: int
    scenario: Literal["ana_relatorios"] = "ana_relatorios"
    #: Zona a simular. Sem ela, a do dashboard, que é a da demonstração original.
    slot: str = contracts.RESUMO_FINANCEIRO


class InjectRawIn(BaseModel):
    user_id: int
    slot: str = contracts.RESUMO_FINANCEIRO
    payload: dict


class RevokeIn(BaseModel):
    #: Quem revogou. Sem corpo, é o painel - o chamador que existia antes.
    por: Literal["usuario", "painel"] = REVOGADO_PELO_PAINEL
    #: Obrigatório quando `por=usuario`: a pessoa só desfaz a personalização dela.
    user_id: int | None = None


@router.post("/telemetry", status_code=status.HTTP_201_CREATED)
def ingest_telemetry(
    payload: TelemetryIn,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """Persiste o evento e dispara a avaliação da regra (§3).

    A avaliação vai para background: o frontend chama isto a cada troca de rota,
    em fire-and-forget (SPEC-02 §2), e não pode ficar esperando uma chamada de LLM.
    """
    evento = TelemetryEvent(user_id=payload.user_id, event=payload.event, path=payload.path)
    session.add(evento)
    session.commit()
    session.refresh(evento)

    if payload.event == "page_view":
        background.add_task(rule.avaliar_rota, payload.user_id, payload.path)

    return {"id": evento.id}


@router.get("/zones")
def listar_zonas() -> list[dict]:
    """As zonas que o sistema conhece: onde aparecem, para que servem e o que as dispara."""
    return [
        {
            "slot": z.slot,
            "tela": z.tela,
            "modulo": z.modulo,
            "finalidade": z.finalidade,
            "observa": z.observa,
            "acessos_minimos": z.acessos_minimos,
        }
        for z in contracts.ZONAS.values()
    ]


@router.get("/zones/{slot}/payload")
def obter_payload(
    slot: str,
    user_id: int = Query(...),
    session: Session = Depends(get_session),
):
    """Payload ativo do usuário para o slot: 200 com o payload, ou 204 (§3).

    204 é a resposta normal, não um erro: a maioria dos usuários não tem
    personalização, e o cliente renderiza o componente nativo.
    """
    if slot not in contracts.SLOTS:
        raise HTTPException(status_code=404, detail=f"slot desconhecido: {slot}")

    registro = rule.payload_ativo(session, user_id, slot)
    if registro is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return {"payload": registro.payload, "payload_id": registro.id, "origin": registro.origin}


@router.post("/violations", status_code=status.HTTP_201_CREATED)
def registrar_violacao(
    payload: ViolationIn,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """O cliente recusou um payload e está avisando (§5.4).

    Sem este registro, o payload malformado sumiria no fallback e a defesa em
    profundidade não deixaria rastro nenhum.
    """
    violacao = ZoneViolation(
        user_id=payload.user_id,
        slot=payload.slot,
        reason=payload.reason,
        raw_payload=payload.raw_payload,
    )
    session.add(violacao)
    session.commit()
    session.refresh(violacao)

    logger.warning(
        "zona %s recusada pelo cliente do usuário %s: %s",
        payload.slot,
        payload.user_id,
        payload.reason,
    )
    return {"id": violacao.id}


@router.post("/simulate")
def simular(
    payload: SimulateIn,
    session: Session = Depends(get_session),
) -> dict:
    """Insere os 5 `page_view` do cenário e avalia na hora (§3).

    Existe para a demonstração ser repetível: o D4 não pode depender de alguém
    navegar cinco vezes na tela certa. A avaliação aqui é síncrona, porque quem
    chamou está esperando para ver o resultado.
    """
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE está desligado")

    zona = contracts.ZONAS.get(payload.slot)
    if zona is None:
        raise HTTPException(status_code=404, detail=f"slot desconhecido: {payload.slot}")

    for _ in range(zona.acessos_minimos):
        session.add(
            TelemetryEvent(user_id=payload.user_id, event="page_view", path=zona.observa)
        )
    session.commit()

    gerado = rule.avaliar(payload.user_id, payload.slot, ignorar_regra=True)
    return {
        "user_id": payload.user_id,
        "slot": payload.slot,
        "eventos_inseridos": zona.acessos_minimos,
        "personalizado": gerado is not None,
        "payload": gerado,
    }


@router.post("/inject-raw", status_code=status.HTTP_201_CREATED)
def injetar_bruto(
    payload: InjectRawIn,
    session: Session = Depends(get_session),
) -> dict:
    """Grava um payload **pulando a validação do core** (§3) - instrumento do D5.

    Contornar a própria validação é o ponto: é assim que se demonstra que a
    defesa não depende de uma camada só. O cliente ainda vai recusar, cair no
    componente nativo e registrar a violação (SPEC-00 §6).
    """
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE está desligado")

    registro = ZonePayload(
        user_id=payload.user_id,
        slot=payload.slot,
        payload=payload.payload,
        origin="injetado",
        status="ativo",
    )
    session.add(registro)
    session.commit()
    session.refresh(registro)

    erros = (
        contracts.erros_de(payload.slot, payload.payload)
        if payload.slot in contracts.SLOTS
        else ["slot desconhecido"]
    )
    logger.warning(
        "payload injetado sem validação para o usuário %s (payload #%s); "
        "o core o consideraria inválido por: %s",
        payload.user_id,
        registro.id,
        "; ".join(erros) or "(nada - este payload é válido)",
    )
    return {"payload_id": registro.id, "core_o_recusaria": bool(erros), "erros_do_core": erros}


@router.get("/payloads")
def listar_payloads(session: Session = Depends(get_session)) -> list[dict]:
    registros = session.execute(
        select(ZonePayload).order_by(ZonePayload.id.desc())
    ).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "slot": r.slot,
            "payload": r.payload,
            "origin": r.origin,
            "status": r.status,
            "created_at": r.created_at,
            "revoked_by": r.revoked_by,
            "revoked_at": r.revoked_at,
        }
        for r in registros
    ]


@router.get("/violations")
def listar_violacoes(session: Session = Depends(get_session)) -> list[dict]:
    registros = session.execute(
        select(ZoneViolation).order_by(ZoneViolation.id.desc())
    ).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "slot": r.slot,
            "reason": r.reason,
            "raw_payload": r.raw_payload,
            "origem": r.origem,
            "at": r.at,
        }
        for r in registros
    ]


@router.get("/evaluations")
def listar_avaliacoes(
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    """O que o agente viu, o que decidiu e por quê - uma linha por avaliação (§4.5.4)."""
    registros = session.execute(
        select(ZoneEvaluation).order_by(ZoneEvaluation.id.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "slot": r.slot,
            "resultado": r.resultado,
            "decisao": r.decisao,
            "motivo": r.motivo,
            "sinais": r.sinais,
            "pedido": r.pedido,
            "payload_id": r.payload_id,
            "violation_id": r.violation_id,
            "trace_id": r.trace_id,
            "at": r.at,
        }
        for r in registros
    ]


@router.post("/payloads/{payload_id}/revoke")
def revogar(
    payload_id: int,
    corpo: RevokeIn | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Desliga a personalização. O usuário volta ao componente nativo.

    Pelo painel (`por=painel`, o padrão), é o operador julgando um payload. Pela tela
    (`por=usuario`), é a pessoa dizendo que prefere o padrão - e essa escolha é
    durável: a regra automática não volta a personalizar a zona (ver `rule`).
    """
    corpo = corpo or RevokeIn()
    registro = session.get(ZonePayload, payload_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="payload não encontrado")
    if corpo.por == REVOGADO_PELO_USUARIO and corpo.user_id != registro.user_id:
        # Sem autenticação nesta PoC; isto só impede que uma tela desfaça a zona de outra pessoa
        # por engano (persona trocada com a página aberta).
        raise HTTPException(status_code=403, detail="este payload é de outra pessoa")

    rule.revogar(session, registro, corpo.por)
    session.commit()
    return {
        "payload_id": payload_id,
        "status": registro.status,
        "revoked_by": registro.revoked_by,
    }
