"""Os documentos de contexto do produto, guardados no banco.

Escopo, requisitos, guia de engenharia, design system, decisões... tudo que diz ao
sistema *o que* é o produto e *como* se escreve código nele. Moram no banco e não no
repositório porque:

1. mudam em tempo real: editar no painel vale na próxima chamada, sem commit nem reinício;
2. cada etapa do ciclo lê **só o que precisa** (`LEITURAS`), em vez de todo prompt carregar
   todo documento;
3. são versionados e consultáveis, o que é o que um agente especializado precisará para
   ser treinado ou orientado por eles.

O sistema **lê** estes documentos; quem os escreve é uma pessoa (ou uma sugestão da IA
que uma pessoa aceitou). O Executor não os toca: eles não estão no repositório que ele
clona.

Os arquivos de `app/context_seed/` são só o conteúdo inicial, usado quando o banco ainda
não tem o documento. Depois disso, o banco é a fonte da verdade.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.db import session_scope
from app.common.models import ContextDocument, ContextDocumentVersion

logger = logging.getLogger("pase.contexto")

SEMENTE = Path(__file__).resolve().parents[1] / "context_seed"

#: `slug` válido: segmentos em minúsculas separados por `/`, no máximo uma pasta.
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)?$")

#: O que cada etapa do ciclo lê. `pasta/*` lê todos os documentos da pasta.
#:
#: Pensado para o custo: o planejamento lê quase tudo porque decide o que construir e onde;
#: a execução lê o que diz *como escrever*; a revisão lê o que diz *o que conferir*.
LEITURAS: dict[str, dict] = {
    "funil": {
        "etapa": "Funil de filtragem",
        "descricao": (
            "Decide se uma demanda cabe no produto: Coerência Sistêmica, Geração "
            "Exploratória, Análise de Lacunas e Reavaliação Cíclica."
        ),
        "prompts": ["P2a", "P3", "P3b", "P9"],
        "documentos": ["project-context", "scope-and-constraints", "requirements", "features"],
        "obrigatorios": ["project-context"],
    },
    "planejamento": {
        "etapa": "Planejamento",
        "descricao": "Decide o que mudar e onde, antes de qualquer código.",
        "prompts": ["P4"],
        "documentos": [
            "project-context",
            "scope-and-constraints",
            "requirements",
            "features",
            "architecture-and-design",
            "architecture-principles",
            "database",
            "ui-ux",
            "engineering-guidelines",
            "design-patterns-and-standards",
            "security-and-compliance",
            "adrs/*",
        ],
        "obrigatorios": [],
    },
    "execucao": {
        "etapa": "Execução",
        "descricao": "Escreve o código: lê como se escreve, não o que o produto é.",
        "prompts": ["P5"],
        "documentos": [
            "engineering-guidelines",
            "design-patterns-and-standards",
            "ui-ux",
            "design-systems/*",
            "security-and-compliance",
        ],
        "obrigatorios": [],
    },
    "revisao": {
        "etapa": "Revisão independente",
        "descricao": "Confere se a entrega faz o que foi pedido e segue as regras.",
        "prompts": ["P12"],
        "documentos": [
            "requirements",
            "engineering-guidelines",
            "ui-ux",
            "security-and-compliance",
        ],
        "obrigatorios": [],
    },
    "entrega": {
        "etapa": "Entrega",
        "descricao": (
            "Fluxo de ramos e implantação. Hoje é aplicado por código; os textos ficam "
            "aqui para pessoas e para agentes futuros."
        ),
        "prompts": [],
        "documentos": ["git-guide", "infrastructure-and-deployment"],
        "obrigatorios": [],
    },
}


class ContextoError(RuntimeError):
    """Documento ausente ou operação inválida."""


# --------------------------------------------------------------------------- #
# Semente
# --------------------------------------------------------------------------- #


def _titulo(texto: str, slug: str) -> str:
    for linha in texto.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()[:200]
    return slug


def _pasta(slug: str) -> str | None:
    return slug.split("/", 1)[0] if "/" in slug else None


def _da_semente() -> dict[str, str]:
    """`{slug: conteúdo}` dos arquivos iniciais."""
    if not SEMENTE.exists():
        return {}
    documentos = {}
    for arquivo in sorted(SEMENTE.rglob("*.md")):
        slug = arquivo.relative_to(SEMENTE).with_suffix("").as_posix()
        documentos[slug] = arquivo.read_text(encoding="utf-8")
    return documentos


def bootstrap(session: Session) -> int:
    """Insere os documentos iniciais que ainda não existem. Nunca sobrescreve.

    Chamado ao subir e, por segurança, na primeira leitura de um banco vazio. Como só
    insere o que falta, documentos novos da semente entram sem apagar nenhuma edição.
    """
    existentes = set(session.execute(select(ContextDocument.slug)).scalars().all())
    novos = 0
    for slug, texto in _da_semente().items():
        if slug in existentes:
            continue
        criar(session, slug, texto, author="sistema", note="conteúdo inicial")
        novos += 1
    if novos:
        session.flush()
        logger.info("contexto: %d documento(s) iniciais inseridos", novos)
    return novos


# --------------------------------------------------------------------------- #
# Leitura e escrita
# --------------------------------------------------------------------------- #


def listar(session: Session) -> list[ContextDocument]:
    return list(
        session.execute(
            select(ContextDocument).order_by(
                ContextDocument.folder.nulls_first(), ContextDocument.slug
            )
        ).scalars()
    )


def obter(session: Session, slug: str) -> ContextDocument:
    doc = session.execute(
        select(ContextDocument).where(ContextDocument.slug == slug)
    ).scalar_one_or_none()
    if doc is None:
        raise ContextoError(f"documento de contexto não encontrado: {slug}")
    return doc


def criar(
    session: Session, slug: str, content: str, *, author: str = "humano", note: str = ""
) -> ContextDocument:
    if not SLUG.match(slug):
        raise ContextoError(
            f"nome inválido: {slug!r}. Use letras minúsculas, números e hífen, "
            "com no máximo uma pasta."
        )
    if not content.strip():
        raise ContextoError("o documento não pode ficar vazio")
    existente = session.execute(
        select(ContextDocument.id).where(ContextDocument.slug == slug)
    ).first()
    if existente:
        raise ContextoError(f"já existe um documento com o nome {slug!r}")

    doc = ContextDocument(
        slug=slug,
        folder=_pasta(slug),
        title=_titulo(content, slug),
        content=content,
        version=1,
        updated_by=author,
    )
    session.add(doc)
    session.flush()
    session.add(
        ContextDocumentVersion(
            document_id=doc.id, version=1, content=content, note=note or "criado", author=author
        )
    )
    session.flush()
    return doc


def salvar(
    session: Session, slug: str, content: str, *, note: str, author: str = "humano"
) -> tuple[ContextDocument, bool]:
    """Grava uma versão nova. Devolve `(documento, mudou)`."""
    if not content.strip():
        raise ContextoError("o documento não pode ficar vazio")
    doc = obter(session, slug)
    if doc.content == content:
        return doc, False

    doc.content = content
    doc.title = _titulo(content, slug)
    doc.version += 1
    doc.updated_by = author
    session.add(doc)
    session.add(
        ContextDocumentVersion(
            document_id=doc.id,
            version=doc.version,
            content=content,
            note=note.strip()[:300],
            author=author,
        )
    )
    session.flush()
    logger.info("contexto: %s v%d por %s (%s)", slug, doc.version, author, note)
    return doc, True


def historico(session: Session, slug: str) -> list[ContextDocumentVersion]:
    doc = obter(session, slug)
    return list(
        session.execute(
            select(ContextDocumentVersion)
            .where(ContextDocumentVersion.document_id == doc.id)
            .order_by(ContextDocumentVersion.version.desc())
        ).scalars()
    )


def restaurar(
    session: Session, slug: str, version: int, *, author: str = "humano"
) -> tuple[ContextDocument, bool]:
    """Volta o conteúdo de uma versão antiga **como uma versão nova**.

    O histórico nunca perde linhas: desfazer também fica registrado.
    """
    doc = obter(session, slug)
    antiga = session.execute(
        select(ContextDocumentVersion).where(
            ContextDocumentVersion.document_id == doc.id,
            ContextDocumentVersion.version == version,
        )
    ).scalar_one_or_none()
    if antiga is None:
        raise ContextoError(f"o documento {slug} não tem a versão {version}")
    return salvar(
        session, slug, antiga.content, note=f"restaurada a versão {version}", author=author
    )


# --------------------------------------------------------------------------- #
# Composição para os prompts
# --------------------------------------------------------------------------- #


def expandir(session: Session, referencias: list[str]) -> list[ContextDocument]:
    """Resolve `slug` e `pasta/*` em documentos, na ordem pedida, sem repetir."""
    todos = {d.slug: d for d in listar(session)}
    vistos: set[str] = set()
    resultado: list[ContextDocument] = []
    for ref in referencias:
        if ref.endswith("/*"):
            pasta = ref[:-2]
            candidatos = sorted(s for s in todos if s.startswith(f"{pasta}/"))
        else:
            candidatos = [ref] if ref in todos else []
        for slug in candidatos:
            if slug not in vistos:
                vistos.add(slug)
                resultado.append(todos[slug])
    return resultado


SEPARADOR = "\n\n---\n\n"


def compor(session: Session, etapa: str) -> str:
    """O texto que uma etapa do ciclo recebe: os documentos dela, em ordem."""
    if etapa not in LEITURAS:
        raise ContextoError(f"etapa desconhecida: {etapa}")
    leitura = LEITURAS[etapa]

    if not session.execute(select(ContextDocument.id).limit(1)).first():
        bootstrap(session)

    documentos = expandir(session, leitura["documentos"])
    presentes = {d.slug for d in documentos}
    for obrigatorio in leitura["obrigatorios"]:
        if obrigatorio not in presentes:
            raise ContextoError(
                f"o documento {obrigatorio!r} é insumo obrigatório da etapa "
                f"{leitura['etapa']} e não existe"
            )
    return SEPARADOR.join(d.content.strip() for d in documentos)


def contexto(etapa: str) -> str:
    """`compor` numa sessão própria, para quem monta prompt sem ter uma à mão.

    Sessão separada de propósito: ler um documento não deve entrar na transação (e nos
    locks) de quem está no meio de outro trabalho.
    """
    with session_scope() as session:
        return compor(session, etapa)
