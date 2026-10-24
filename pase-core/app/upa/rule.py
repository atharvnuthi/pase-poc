"""Regra de personalização e geração do payload (SPEC-05 §4).

Este é o **loop rápido** do modelo (SPEC-00 §1): segundos, sem gate humano, sem
tocar o repositório. O que substitui a aprovação humana aqui é a validação de
schema - e ela acontece duas vezes, no core e no cliente.

A regra é deliberadamente simples e explicável: um comportamento repetido e
mensurável dispara a avaliação de uma zona. Cada zona observa a sua rota
(`Zona.observa`) e espera um número de visitas (`Zona.acessos_minimos`) numa janela
de sete dias. Nada de modelo preditivo - a decisão de personalizar precisa ser
defensável numa frase.

Há dois caminhos até o mesmo gerador (P6):

1. **Automático**: o uso repetido dispara a regra.
2. **Por pedido**: a pessoa escreveu uma sugestão que uma zona existente já cobre. O
   texto vai ao P6 como dica; ele continua preso ao contrato e pode recusar.

Toda personalização é reversível ao padrão (R3). Quando é a **própria pessoa** que
volta ao padrão, a escolha dela é durável: o caminho automático não personaliza aquela
zona de novo. Só um pedido explícito dela reabre a zona.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import prompts
from app.common.config import settings
from app.common.db import session_scope
from app.common.events import publish
from app.common.llm_client import chat as llm_chat
from app.common.models import utcnow
from app.upa import contracts
from app.upa.models import (
    REVOGADO_PELO_USUARIO,
    SUBSTITUIDO_POR_PEDIDO,
    VIOLACAO_NO_SERVIDOR,
    TelemetryEvent,
    ZoneEvaluation,
    ZonePayload,
    ZoneViolation,
)

logger = logging.getLogger("pase.upa")

JANELA_DIAS = 7

SCHEMA_P6 = {
    "type": "object",
    "properties": {
        "personalize": {"type": "boolean"},
        "payload": {"type": ["object", "null"]},
        "motivo": {"type": "string"},
    },
    "required": ["personalize"],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}


@dataclass
class Resultado:
    """O que o gerador fez, e por quê - o "por quê" é o que se diz à pessoa."""

    payload: dict | None
    motivo: str = ""
    # O que a avaliação registra para auditoria (SPEC-05 §7).
    sinais: str = ""
    #: O `personalize` do modelo; None quando a chamada nem chegou a responder.
    decisao: bool | None = None
    #: O modelo quis personalizar, mas o core recusou o payload.
    fora_do_contrato: bool = False
    payload_id: int | None = None
    violation_id: int | None = None
    trace_id: str | None = None

    @property
    def personalizou(self) -> bool:
        return self.payload is not None

    def rotulo(self, *, por_pedido: bool) -> str:
        """O `resultado` da avaliação, numa palavra."""
        if self.personalizou:
            base = "personalizou"
        elif self.fora_do_contrato:
            base = "fora_do_contrato"
        else:
            base = "recusou"
        if not por_pedido:
            return base
        return {"personalizou": "pedido", "recusou": "pedido_recusado"}.get(
            base, f"pedido_{base}"
        )


def payload_ativo(session: Session, user_id: int, slot: str) -> ZonePayload | None:
    """Payload `ativo` mais recente do par (usuário, slot)."""
    return session.execute(
        select(ZonePayload)
        .where(ZonePayload.user_id == user_id)
        .where(ZonePayload.slot == slot)
        .where(ZonePayload.status == "ativo")
        .order_by(ZonePayload.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def contagem_por_rota(session: Session, user_id: int) -> dict[str, int]:
    """Quantos `page_view` por rota na janela - é o resumo que o P6 recebe."""
    desde = utcnow() - timedelta(days=JANELA_DIAS)
    linhas = session.execute(
        select(TelemetryEvent.path, func.count(TelemetryEvent.id))
        .where(TelemetryEvent.user_id == user_id)
        .where(TelemetryEvent.event == "page_view")
        .where(TelemetryEvent.at >= desde)
        .group_by(TelemetryEvent.path)
        .order_by(func.count(TelemetryEvent.id).desc())
    ).all()
    return dict(linhas)


def avaliou_recentemente(session: Session, user_id: int, slot: str) -> bool:
    """Já houve uma avaliação deste par dentro do intervalo mínimo?

    Sem isto, uma zona que o P6 recusa seria reavaliada a cada visita, e cada
    avaliação é uma chamada ao modelo. Com várias zonas, o custo multiplicaria.

    Uma revogação também conta como decisão sobre a zona: sem isto, o payload que o
    painel acabou de revogar voltaria na visita seguinte, gerado dos mesmos sinais.
    """
    desde = utcnow() - timedelta(hours=settings.zone_reevaluation_hours)
    avaliou = session.execute(
        select(ZoneEvaluation.id)
        .where(ZoneEvaluation.user_id == user_id)
        .where(ZoneEvaluation.slot == slot)
        .where(ZoneEvaluation.at >= desde)
        .limit(1)
    ).first()
    if avaliou is not None:
        return True
    revogou = session.execute(
        select(ZonePayload.id)
        .where(ZonePayload.user_id == user_id)
        .where(ZonePayload.slot == slot)
        .where(ZonePayload.revoked_at >= desde)
        .limit(1)
    ).first()
    return revogou is not None


def pessoa_voltou_ao_padrao(session: Session, user_id: int, slot: str) -> bool:
    """A pessoa já desfez uma personalização desta zona com as próprias mãos?

    Se sim, a inferência automática não volta a personalizá-la - nem depois do
    intervalo. Quem revogou pelo painel foi o operador, julgando um payload; quem
    revogou pela tela foi a pessoa, dizendo o que quer ver. Só a segunda é preferência.
    """
    return (
        session.execute(
            select(ZonePayload.id)
            .where(ZonePayload.user_id == user_id)
            .where(ZonePayload.slot == slot)
            .where(ZonePayload.revoked_by == REVOGADO_PELO_USUARIO)
            .limit(1)
        ).first()
        is not None
    )


def deve_avaliar(session: Session, user_id: int, slot: str) -> bool:
    """A regra do §4, inteira e em um lugar só."""
    zona = contracts.ZONAS[slot]
    if payload_ativo(session, user_id, slot) is not None:
        return False
    if pessoa_voltou_ao_padrao(session, user_id, slot):
        return False
    if contagem_por_rota(session, user_id).get(zona.observa, 0) < zona.acessos_minimos:
        return False
    return not avaliou_recentemente(session, user_id, slot)


def revogar(session: Session, registro: ZonePayload, por: str) -> ZonePayload:
    """Desliga um payload e registra quem desligou. O usuário volta ao componente nativo."""
    if registro.status != "revogado":
        registro.status = "revogado"
        registro.revoked_by = por
        registro.revoked_at = utcnow()
    elif por == REVOGADO_PELO_USUARIO and registro.revoked_by != REVOGADO_PELO_USUARIO:
        # A pessoa reafirmou a escolha num payload que o painel já tinha desligado
        # (a tela dela ainda o mostrava): a escolha dela é o que precisa ficar.
        registro.revoked_by = por
        registro.revoked_at = utcnow()
    session.add(registro)
    return registro


def _bloco_do_pedido(pedido: str | None) -> str:
    if not pedido:
        return ""
    return (
        "## O que a pessoa pediu\n\n"
        f"> {pedido.strip()}\n\n"
        "É uma **dica** do que ela quer ver, não uma ordem: você continua preso ao contrato "
        "e aos widgets disponíveis. Se nada do que o contrato permite atende ao pedido, "
        "responda `personalize: false` e explique em `motivo`, em uma frase."
    )


def _gerar(
    session: Session, user_id: int, slot: str, *, pedido: str | None = None
) -> Resultado:
    """P6 → validação → persistência. O `Resultado` leva tudo o que a auditoria grava."""
    comportamento = contagem_por_rota(session, user_id)
    resumo = "\n".join(f"- {rota}: {total} acesso(s)" for rota, total in comportamento.items())
    sinais = resumo or "(sem acessos registrados)"

    content, usage = llm_chat(
        [
            prompts.system_message(
                "P6",
                comportamento=sinais,
                finalidade=contracts.SLOTS[slot],
                contrato=json.dumps(contracts.schema_de(slot), ensure_ascii=False, indent=2),
                pedido=_bloco_do_pedido(pedido),
            ),
            GO,
        ],
        json_schema=SCHEMA_P6,
        temperature=0.3,
        tags={"user_id": user_id, "prompt_id": "P6", "fase": "personalizacao"},
    )
    trace_id = usage.get("trace_id")
    motivo = str(content.get("motivo") or "").strip()

    if not content.get("personalize"):
        logger.info(
            "P6: sem personalização para o usuário %s em %s (trace=%s)",
            user_id, slot, trace_id,
        )
        return Resultado(None, motivo, sinais=sinais, decisao=False, trace_id=trace_id)

    payload = content.get("payload")
    erros = contracts.erros_de(slot, payload)
    if erros:
        # Defesa em profundidade (SPEC-05 §4): o core recusa antes de persistir. A
        # recusa é uma violação como a do cliente (§4.5.5), e fica registrada como tal -
        # descartar em silêncio seria pior do que não validar.
        violacao = ZoneViolation(
            user_id=user_id,
            slot=slot,
            reason="; ".join(erros),
            raw_payload=payload if isinstance(payload, dict) else {"payload": payload},
            origem=VIOLACAO_NO_SERVIDOR,
        )
        session.add(violacao)
        session.flush()
        logger.warning(
            "P6 devolveu payload fora do contrato para o usuário %s: %s (violação #%s, trace=%s)",
            user_id,
            violacao.reason,
            violacao.id,
            trace_id,
        )
        return Resultado(
            None,
            "a configuração gerada não respeitava o contrato da zona",
            sinais=sinais,
            decisao=True,
            fora_do_contrato=True,
            violation_id=violacao.id,
            trace_id=trace_id,
        )

    registro = ZonePayload(
        user_id=user_id, slot=slot, payload=payload, origin="autonoma", status="ativo"
    )
    session.add(registro)
    session.flush()

    logger.info(
        "zona %s personalizada para o usuário %s: widget=%s (payload #%s)",
        slot,
        user_id,
        payload.get("widget"),
        registro.id,
    )
    publish(
        "zone.payload.created",
        {"payload_id": registro.id, "user_id": user_id, "slot": slot},
        session=session,
    )
    return Resultado(
        payload,
        motivo,
        sinais=sinais,
        decisao=True,
        payload_id=registro.id,
        trace_id=trace_id,
    )


def gerar_payload(session: Session, user_id: int, slot: str) -> dict | None:
    """Caminho automático: devolve o payload persistido, ou None."""
    return _gerar(session, user_id, slot).payload


def _registrar(
    session: Session,
    user_id: int,
    slot: str,
    resultado: Resultado,
    *,
    pedido: str | None = None,
) -> ZoneEvaluation:
    """Grava a avaliação: os sinais, a decisão, o motivo e o que saiu dela."""
    avaliacao = ZoneEvaluation(
        user_id=user_id,
        slot=slot,
        resultado=resultado.rotulo(por_pedido=pedido is not None),
        sinais=resultado.sinais or None,
        pedido=pedido,
        decisao=resultado.decisao,
        motivo=resultado.motivo or None,
        payload_id=resultado.payload_id,
        violation_id=resultado.violation_id,
        trace_id=resultado.trace_id,
    )
    session.add(avaliacao)
    return avaliacao


def avaliar(
    user_id: int, slot: str = contracts.RESUMO_FINANCEIRO, *, ignorar_regra: bool = False
) -> dict | None:
    """Ponto de entrada do fluxo autônomo. Seguro para rodar em background.

    `ignorar_regra` existe para a demonstração: o D4 não pode depender de alguém
    navegar cinco vezes na tela certa, nem esperar o intervalo entre avaliações.
    """
    try:
        with session_scope() as session:
            if not ignorar_regra and not deve_avaliar(session, user_id, slot):
                return None
            resultado = _gerar(session, user_id, slot)
            _registrar(session, user_id, slot, resultado)
            return resultado.payload
    except Exception:  # pragma: no cover - rede de segurança do background
        logger.exception("falha ao avaliar a zona %s do usuário %s", slot, user_id)
        return None


def avaliar_rota(user_id: int, rota: str) -> int:
    """Avalia as zonas que observam esta rota. Devolve quantas personalizou."""
    return sum(
        1 for zona in contracts.zonas_que_observam(rota) if avaliar(user_id, zona.slot) is not None
    )


def gerar_por_pedido(user_id: int, slot: str, pedido: str) -> Resultado:
    """Caminho por pedido: a pessoa escreveu algo que a zona já cobre.

    Pula a regra de visitas (ela pediu explicitamente) e substitui o payload ativo, se
    houver: o pedido novo vale mais do que a inferência anterior. Pula também a volta ao
    padrão que ela tenha feito antes - pedir é o jeito de reabrir a zona.
    """
    if slot not in contracts.ZONAS:
        return Resultado(None, f"zona desconhecida: {slot}")
    try:
        with session_scope() as session:
            resultado = _gerar(session, user_id, slot, pedido=pedido)
            _registrar(session, user_id, slot, resultado, pedido=pedido)
            if resultado.personalizou:
                # O pedido novo substitui o anterior: sobra um só payload ativo por zona.
                ativos = list(
                    session.execute(
                        select(ZonePayload)
                        .where(ZonePayload.user_id == user_id, ZonePayload.slot == slot)
                        .where(ZonePayload.status == "ativo")
                        .order_by(ZonePayload.id.desc())
                    ).scalars()
                )
                for antigo in ativos[1:]:
                    revogar(session, antigo, SUBSTITUIDO_POR_PEDIDO)
            return resultado
    except Exception:
        logger.exception("falha ao personalizar %s por pedido do usuário %s", slot, user_id)
        return Resultado(None, "houve uma falha ao ajustar a área agora")
