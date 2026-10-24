"""Urgência inicial de uma candidata nova (monografia §4.4.1).

Um incidente eleva a urgência das candidatas do módulo afetado no momento em que é
registrado (`POST /api/incidents`). Sem isto, a candidata criada **depois**, com o
incidente ainda aberto, nascia com urgência zero e ficava atrás das antigas - o
incidente valia para quem chegou antes dele e não para quem chegou durante.

A regra é a mesma do endpoint: soma o peso da severidade de cada incidente aberto
no módulo. Os pesos repetem `PESO_URGENCIA` de `orchestration/routes.py`; ficam
aqui para o Task Layer não importar um módulo de rotas.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orchestration.models import Incident

#: Peso de cada severidade no Fator de Urgência - igual ao do endpoint de incidentes.
PESO_URGENCIA = {"alto": 3.0, "medio": 1.0, "baixo": 0.0}


def urgencia_inicial(session: Session, module: str | None) -> float:
    """Soma dos pesos dos incidentes abertos no módulo da candidata."""
    if not module:
        return 0.0
    severidades = session.execute(
        select(Incident.severity)
        .where(Incident.module == module)
        .where(Incident.resolved.is_(False))
    ).scalars().all()
    return sum(PESO_URGENCIA.get(s, 0.0) for s in severidades)
