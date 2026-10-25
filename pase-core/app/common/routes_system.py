"""O motor, visto por dentro.

O painel mostrava tarefas e nada sobre o próprio sistema: quantos vetores há na
memória, quais prompts existem e quando cada um roda, quanto já se gastou. Sem
isso, "por que o PASE decidiu assim?" só tem resposta para quem lê o código.

Tudo aqui é leitura. Nada nesta rota muda estado.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.common import prompts
from app.common.config import settings
from app.common.db import get_session
from app.common.glossary import GLOSSARIO
from app.common.models import LLMCall
from app.common.vector_store import REGISTRY
from app.orchestration.models import ExecutionRun, Incident
from app.task_layer.models import DiscardedProposal, ImplementedItem, Proposal, Task

logger = logging.getLogger("pase.system")

router = APIRouter(prefix="/api/system", tags=["sistema"])

#: Quando cada prompt roda e com que temperatura. Levantado dos módulos que os
#: chamam; o teste `test_prompts` garante que todo arquivo existe.
CATALOGO_DE_PROMPTS = [
    ("P0", "Extração de intenção", "Captação Passiva", 0.1),
    ("P0a", "Agrupamento de tickets", "Captação Passiva", 0.1),
    ("P1", "Normalização", "Task Layer", 0.1),
    ("P1b", "Avaliação de Zona Dinâmica", "Task Layer", 0.1),
    ("P2a", "Coerência Sistêmica", "Task Layer", 0.1),
    ("P2b", "Qualificação", "Task Layer", 0.2),
    ("P3", "Geração Exploratória", "Task Layer", 0.9),
    ("P3b", "Análise de Lacunas", "Task Layer", 0.2),
    ("P4", "Planejamento", "Execução", 0.1),
    ("P5", "Geração e correção de código", "Execução", 0.1),
    ("P6", "Payload de Zona Dinâmica", "UPA", 0.2),
    ("P9", "Análise de Deriva", "Reavaliação Cíclica", 0.1),
    ("P10", "Varredura de Auditoria", "Ciclo de Auditoria", 0.2),
    ("P11", "Proposta de atualização de contexto", "Homologação", 0.1),
    ("P12", "Revisão independente", "Execução", 0.0),
]


@router.get("/glossary")
def ver_glossario() -> dict:
    """O vocabulário do painel, explicado - quem atribui cada etiqueta e o que ela muda."""
    return {"grupos": GLOSSARIO}


@router.get("/prompts")
def ver_prompts() -> dict:
    """Os prompts versionados, com o tamanho de cada um e se está no disco."""
    catalogo = []
    for prompt_id, papel, etapa, temperatura in CATALOGO_DE_PROMPTS:
        caminho = prompts.PROMPTS_DIR / f"{prompt_id}.md"
        existe = caminho.exists()
        catalogo.append(
            {
                "id": prompt_id,
                "papel": papel,
                "etapa": etapa,
                "temperatura": temperatura,
                "existe": existe,
                "linhas": len(caminho.read_text(encoding="utf-8").splitlines()) if existe else 0,
            }
        )
    return {"prompts": catalogo, "pasta": str(prompts.PROMPTS_DIR)}


@router.get("/prompts/{prompt_id}", response_class=PlainTextResponse)
def ver_prompt(prompt_id: str) -> str:
    """O texto integral de um prompt, como ele vai para o modelo.

    Só os que o catálogo conhece: o `prompt_id` vira nome de arquivo, e aceitar
    qualquer string deixaria alguém ler arquivo fora da pasta de prompts.
    """
    conhecidos = {p[0] for p in CATALOGO_DE_PROMPTS}
    if prompt_id not in conhecidos:
        raise HTTPException(status_code=404, detail=f"prompt desconhecido: {prompt_id}")

    caminho = prompts.PROMPTS_DIR / f"{prompt_id}.md"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail=f"{prompt_id}.md não está no disco")

    return caminho.read_text(encoding="utf-8")


@router.get("/memory")
def ver_memoria(session: Session = Depends(get_session)) -> dict:
    """Estado da memória vetorial, por tipo.

    `sem_embedding` importa: uma linha sem vetor existe no banco e é invisível
    para a busca - ela não barra duplicata nenhuma. É o tipo de silêncio que só
    aparece se alguém contar.
    """
    tipos = []
    for kind, spec in REGISTRY.items():
        onde = f" WHERE {spec.where}" if spec.where else ""
        total = session.execute(text(f"SELECT count(*) FROM {spec.table}{onde}")).scalar() or 0
        coluna = spec.embedding_column
        juncao = "AND" if spec.where else "WHERE"
        sem_vetor = (
            session.execute(
                text(f"SELECT count(*) FROM {spec.table}{onde} {juncao} {coluna} IS NULL")
            ).scalar()
            or 0
        )
        tipos.append(
            {
                "kind": kind,
                "tabela": spec.table,
                "total": total,
                "com_embedding": total - sem_vetor,
                "sem_embedding": sem_vetor,
            }
        )

    return {
        "tipos": tipos,
        "modelo": settings.embedding_model,
        "dimensoes": settings.embedding_dim,
        "limiar_de_similaridade": settings.similarity_threshold,
    }


@router.get("/cost")
def ver_custo(session: Session = Depends(get_session)) -> dict:
    """Quanto o sistema já gastou, por fase e por modelo."""
    total_chamadas = session.execute(select(func.count(LLMCall.id))).scalar() or 0
    tokens_in = session.execute(select(func.coalesce(func.sum(LLMCall.tokens_in), 0))).scalar()
    tokens_out = session.execute(select(func.coalesce(func.sum(LLMCall.tokens_out), 0))).scalar()
    custo = session.execute(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0))).scalar()

    por_modelo = [
        {"modelo": modelo, "chamadas": n, "tokens_in": ti, "tokens_out": to}
        for modelo, n, ti, to in session.execute(
            select(
                LLMCall.model,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.tokens_in), 0),
                func.coalesce(func.sum(LLMCall.tokens_out), 0),
            ).group_by(LLMCall.model)
        )
    ]

    return {
        "chamadas": total_chamadas,
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "custo_usd": round(float(custo or 0.0), 4),
        "por_modelo": por_modelo,
        "provider": settings.llm_provider,
        "modelo_padrao": settings.llm_model,
        "modelo_exploratorio": settings.llm_model_exploratory,
        # Quem escreve o código e quem o revisa são modelos diferentes de
        # propósito; o painel mostra os dois para isso não ficar implícito.
        "modelo_de_codigo": settings.modelo_de_codigo,
        "modelo_de_revisao": settings.modelo_de_revisao,
    }


@router.get("/health")
def ver_saude(session: Session = Depends(get_session)) -> dict:
    """Contagens que dizem se o sistema está com trabalho parado em algum lugar."""
    def conta(modelo, *condicoes):
        consulta = select(func.count(modelo.id))
        for condicao in condicoes:
            consulta = consulta.where(condicao)
        return session.execute(consulta).scalar() or 0

    return {
        "propostas": conta(Proposal),
        "tarefas": conta(Task),
        "candidatas": conta(Task, Task.status == "candidata"),
        "em_andamento": conta(Task, Task.status.notin_(["candidata", "finalizada"])),
        "aguardando_humano": conta(
            Task, Task.status.in_(["candidata", "aguardando_plano", "em_homologacao"])
        ),
        "suspensas": conta(Task, Task.status == "suspensa"),
        "implementados": conta(ImplementedItem),
        "descartes": conta(DiscardedProposal),
        "runs": conta(ExecutionRun),
        "incidentes_abertos": conta(Incident, Incident.resolved.is_(False)),
        "guardrails": {
            "similarity_threshold": settings.similarity_threshold,
            "budget_min_tokens": settings.budget_min_tokens,
            "budget_tolerance": settings.budget_tolerance,
            "max_retries": settings.max_retries,
            "max_local_fix": settings.max_local_fix,
        },
    }
