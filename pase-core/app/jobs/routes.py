"""Loops de manutenção por acionamento humano (monografia §4.3.5 e §4.4.6).

"Periodicamente, ou por acionamento humano": a Auditoria (P10) e a Reavaliação
Cíclica (P9) rodavam só pela linha de comando, e quem opera o painel não tinha
como dispará-las. Agendamento periódico continua fora do escopo.

Cada job roda em segundo plano - uma rodada faz várias chamadas ao modelo e leva
minutos - e a requisição responde 202 na hora. Duas rodadas do mesmo job ao
mesmo tempo são recusadas: a Reavaliação reinseriria o mesmo descarte duas vezes
antes de qualquer uma marcar que já o reavaliou, e a Auditoria pagaria duas
varreduras para propor provavelmente a mesma coisa.

O estado das rodadas vive na memória do processo. Reiniciar o pase-core o zera, o
que basta: o resultado durável de um job são as propostas que ele criou, e elas
estão no banco.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.common.models import utcnow

logger = logging.getLogger("pase.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _auditoria() -> dict:
    # Import tardio: os módulos dos jobs configuram o logging ao serem importados
    # (são também entradas de linha de comando) e passariam na frente do main.
    from app.jobs import audit

    return audit.executar()


def _reavaliacao() -> dict:
    from app.jobs import reevaluation

    return reevaluation.executar()


JOBS: dict[str, tuple[str, Callable[[], dict]]] = {
    "auditoria": ("Ciclo de Auditoria (P10)", _auditoria),
    "reavaliacao": ("Reavaliação Cíclica (P9)", _reavaliacao),
}

_trava = threading.Lock()
_estado: dict[str, dict] = {}


def _vazio(nome: str) -> dict:
    return {
        "job": nome,
        "nome": JOBS[nome][0],
        "rodando": False,
        "iniciado_em": None,
        "terminado_em": None,
        "resultado": None,
        "erro": None,
    }


def estado(nome: str) -> dict:
    with _trava:
        return dict(_estado.get(nome) or _vazio(nome))


def _rodar(nome: str) -> None:
    resultado, erro = None, None
    try:
        resultado = JOBS[nome][1]()
    except Exception as exc:
        logger.exception("job %s falhou", nome)
        erro = str(exc) or exc.__class__.__name__
    with _trava:
        _estado[nome] = {
            **_estado[nome],
            "rodando": False,
            "terminado_em": utcnow(),
            "resultado": resultado,
            "erro": erro,
        }


def _disparar(nome: str, background: BackgroundTasks) -> dict:
    with _trava:
        atual = _estado.get(nome)
        if atual and atual["rodando"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{JOBS[nome][0]} já está rodando desde {atual['iniciado_em']:%H:%M:%S}",
            )
        _estado[nome] = {**_vazio(nome), "rodando": True, "iniciado_em": utcnow()}

    background.add_task(_rodar, nome)
    return {
        "job": nome,
        "status": "iniciado",
        "detail": f"{JOBS[nome][0]} iniciado em segundo plano",
    }


@router.get("")
def listar_jobs() -> dict:
    """Estado da última rodada de cada job, para o painel acompanhar."""
    return {nome: estado(nome) for nome in JOBS}


@router.post("/auditoria", status_code=status.HTTP_202_ACCEPTED)
def rodar_auditoria(background: BackgroundTasks) -> dict:
    """Varre o código do FinTrack atrás de um ponto que valha virar tarefa."""
    return _disparar("auditoria", background)


@router.post("/reavaliacao", status_code=status.HTTP_202_ACCEPTED)
def rodar_reavaliacao(background: BackgroundTasks) -> dict:
    """Relê os descartes por incoerência contra o contexto de hoje."""
    return _disparar("reavaliacao", background)
