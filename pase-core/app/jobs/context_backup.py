"""Salva e restaura os documentos de contexto, com todo o histórico de versões.

    docker compose exec pase-core python -m app.jobs.context_backup export
    docker compose exec pase-core python -m app.jobs.context_backup import

Existe por causa do `make reset`: ele apaga o volume do Postgres para voltar ao estado
inicial, e os documentos de contexto são **edição de uma pessoa**, não dado de teste. O
reset exporta antes e importa depois; `make reset-all` pula esse passo e volta também o
contexto ao conteúdo inicial.

O arquivo fica em `.pase-local/` (fora do git): é cópia local, não parte do repositório.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import delete, select

from app.common.config import settings
from app.common.db import session_scope
from app.common.models import ContextDocument, ContextDocumentVersion, utcnow

DESTINO = Path(settings.repo_path) / ".pase-local" / "context-backup.json"


def exportar(destino: Path = DESTINO) -> int:
    with session_scope() as session:
        saida = []
        documentos = session.execute(
            select(ContextDocument).order_by(ContextDocument.slug)
        ).scalars()
        for doc in documentos:
            versoes = session.execute(
                select(ContextDocumentVersion)
                .where(ContextDocumentVersion.document_id == doc.id)
                .order_by(ContextDocumentVersion.version)
            ).scalars()
            saida.append(
                {
                    "slug": doc.slug,
                    "folder": doc.folder,
                    "title": doc.title,
                    "content": doc.content,
                    "version": doc.version,
                    "updated_by": doc.updated_by,
                    "versions": [
                        {
                            "version": v.version,
                            "content": v.content,
                            "note": v.note,
                            "author": v.author,
                            "created_at": v.created_at.isoformat(),
                        }
                        for v in versoes
                    ],
                }
            )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[contexto] {len(saida)} documento(s) exportados para {destino}")
    return len(saida)


def importar(origem: Path = DESTINO) -> int:
    """Restaura o backup por cima do que existe, documento a documento."""
    from datetime import datetime

    if not origem.exists():
        print("[contexto] sem backup para restaurar; ficam os documentos iniciais")
        return 0

    dados = json.loads(origem.read_text(encoding="utf-8"))
    with session_scope() as session:
        for item in dados:
            existente = session.execute(
                select(ContextDocument).where(ContextDocument.slug == item["slug"])
            ).scalar_one_or_none()
            if existente is not None:
                session.execute(
                    delete(ContextDocumentVersion).where(
                        ContextDocumentVersion.document_id == existente.id
                    )
                )
                session.delete(existente)
                session.flush()

            doc = ContextDocument(
                slug=item["slug"],
                folder=item["folder"],
                title=item["title"],
                content=item["content"],
                version=item["version"],
                updated_by=item["updated_by"],
            )
            session.add(doc)
            session.flush()
            for v in item["versions"]:
                session.add(
                    ContextDocumentVersion(
                        document_id=doc.id,
                        version=v["version"],
                        content=v["content"],
                        note=v["note"],
                        author=v["author"],
                        created_at=datetime.fromisoformat(v["created_at"]),
                    )
                )
            doc.updated_at = utcnow()
    print(f"[contexto] {len(dados)} documento(s) restaurados de {origem}")
    return len(dados)


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "export":
        exportar()
    elif comando == "import":
        importar()
    else:
        print("uso: python -m app.jobs.context_backup export|import")
        sys.exit(2)
