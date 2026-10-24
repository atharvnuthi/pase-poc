"""O contexto do produto: documentos versionados no banco (SPEC-07, evoluído).

Os documentos dizem ao sistema o que o produto é e como se escreve código nele. O painel os
lista, edita, versiona e mostra **quem lê cada um** em cada etapa do ciclo, para que mudar
um texto não seja um ato às cegas.

Duas regras valem aqui:

1. **A IA propõe, uma pessoa decide.** `/propose` devolve um diff e não grava nada. Deixar o
   modelo reescrever sozinho o documento que o julga criaria um sistema validando as
   próprias decisões contra um texto que ele mesmo mudou.
2. **Nada se perde.** Toda gravação é uma versão nova, inclusive a restauração de uma antiga.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common import context_ai, context_store, context_suggestions
from app.common.db import get_session

logger = logging.getLogger("pase.contexto")

router = APIRouter(prefix="/api/context", tags=["contexto"])


def _resumo(doc) -> dict:
    return {
        "slug": doc.slug,
        "folder": doc.folder,
        "title": doc.title,
        "version": doc.version,
        "updated_by": doc.updated_by,
        "updated_at": doc.updated_at,
        "chars": len(doc.content),
    }


def _leituras(session: Session) -> list[dict]:
    """Quem lê o quê, com os curingas já expandidos em documentos reais."""
    saida = []
    for chave, leitura in context_store.LEITURAS.items():
        docs = context_store.expandir(session, leitura["documentos"])
        saida.append(
            {
                "key": chave,
                "etapa": leitura["etapa"],
                "descricao": leitura["descricao"],
                "prompts": leitura["prompts"],
                "documentos": [d.slug for d in docs],
                "chars": sum(len(d.content) for d in docs),
            }
        )
    return saida


def _erro(exc: Exception) -> HTTPException:
    texto = str(exc)
    codigo = 404 if "não encontrado" in texto else 422
    return HTTPException(status_code=codigo, detail=texto)


@router.get("")
def listar(session: Session = Depends(get_session)) -> dict:
    """Todos os documentos (sem o texto) e o mapa de quem lê cada um."""
    if not context_store.listar(session):
        context_store.bootstrap(session)
        session.commit()
    return {
        "documentos": [_resumo(d) for d in context_store.listar(session)],
        "leituras": _leituras(session),
    }


class NovoIn(BaseModel):
    slug: str = Field(min_length=1)
    content: str = Field(min_length=1)


@router.post("", status_code=201)
def criar(payload: NovoIn, session: Session = Depends(get_session)) -> dict:
    """Cria um documento novo, por exemplo mais uma decisão em `adrs/`."""
    try:
        doc = context_store.criar(session, payload.slug.strip(), payload.content)
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _resumo(doc)


# As rotas com sufixo vêm antes da genérica: o conversor `path` engole o que sobrar.


@router.get("/doc/{slug:path}/history")
def historico(slug: str, session: Session = Depends(get_session)) -> list[dict]:
    try:
        versoes = context_store.historico(session, slug)
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    return [
        {
            "version": v.version,
            "note": v.note,
            "author": v.author,
            "created_at": v.created_at,
            "chars": len(v.content),
        }
        for v in versoes
    ]


@router.get("/doc/{slug:path}/version/{version}")
def versao(slug: str, version: int, session: Session = Depends(get_session)) -> dict:
    try:
        for v in context_store.historico(session, slug):
            if v.version == version:
                return {"version": v.version, "content": v.content, "note": v.note}
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    raise HTTPException(status_code=404, detail="versão não encontrada")


class RestaurarIn(BaseModel):
    version: int


@router.post("/doc/{slug:path}/restore")
def restaurar(
    slug: str, payload: RestaurarIn, session: Session = Depends(get_session)
) -> dict:
    try:
        doc, mudou = context_store.restaurar(session, slug, payload.version)
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    session.commit()
    return {**_resumo(doc), "mudou": mudou}


class PropostaIn(BaseModel):
    request: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Sugestões nascidas de tarefas aprovadas
# --------------------------------------------------------------------------- #


@router.get("/suggestions")
def listar_sugestoes(session: Session = Depends(get_session)) -> list[dict]:
    """As sugestões pendentes: o que a IA acha que ficou desatualizado depois de uma entrega."""
    return [
        {
            "id": s.id,
            "task_id": s.task_id,
            "slug": s.slug,
            "base_version": s.base_version,
            "summary": s.summary,
            "reasoning": s.reasoning,
            "diff": s.diff,
            "created_at": s.created_at,
        }
        for s in context_suggestions.pendentes(session)
    ]


@router.post("/suggestions/{suggestion_id}/accept")
def aceitar_sugestao(suggestion_id: int, session: Session = Depends(get_session)) -> dict:
    """Grava a sugestão como versão nova do documento."""
    try:
        doc = context_suggestions.aceitar(session, suggestion_id)
    except context_store.ContextoError as exc:
        codigo = 404 if "não encontrada" in str(exc) else 409
        raise HTTPException(status_code=codigo, detail=str(exc)) from exc
    session.commit()
    return _resumo(doc)


@router.post("/suggestions/{suggestion_id}/dismiss")
def dispensar_sugestao(suggestion_id: int, session: Session = Depends(get_session)) -> dict:
    try:
        context_suggestions.dispensar(session, suggestion_id)
    except context_store.ContextoError as exc:
        codigo = 404 if "não encontrada" in str(exc) else 409
        raise HTTPException(status_code=codigo, detail=str(exc)) from exc
    session.commit()
    return {"id": suggestion_id, "status": "dispensada"}


@router.post("/doc/{slug:path}/propose")
def propor_alteracao(
    slug: str, payload: PropostaIn, session: Session = Depends(get_session)
) -> dict:
    """Pede ao modelo uma versão do documento com a mudança aplicada.

    Propõe, não escreve: a resposta é um diff para uma pessoa aprovar.
    """
    try:
        doc = context_store.obter(session, slug)
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    return context_ai.propor(slug, doc.content, payload.request)


class EdicaoIn(BaseModel):
    content: str = Field(min_length=1)
    note: str = Field(min_length=1)


@router.put("/doc/{slug:path}")
def salvar(slug: str, payload: EdicaoIn, session: Session = Depends(get_session)) -> dict:
    """Grava uma versão nova. Vale na próxima chamada de qualquer etapa que leia o documento."""
    try:
        anterior = context_store.obter(session, slug).content
        doc, mudou = context_store.salvar(session, slug, payload.content, note=payload.note)
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    session.commit()
    return {
        **_resumo(doc),
        "salvo": mudou,
        "diff": context_ai.diff_de(slug, anterior, payload.content) if mudou else "",
    }


@router.get("/doc/{slug:path}")
def ler(slug: str, session: Session = Depends(get_session)) -> dict:
    try:
        doc = context_store.obter(session, slug)
    except context_store.ContextoError as exc:
        raise _erro(exc) from exc
    leitores = [
        {"key": k, "etapa": v["etapa"], "prompts": v["prompts"]}
        for k, v in context_store.LEITURAS.items()
        if doc in context_store.expandir(session, v["documentos"])
    ]
    return {**_resumo(doc), "content": doc.content, "readers": leitores}
