"""Memória vetorial do PASE (SPEC-01 §6).

Todo SQL vetorial do projeto vive aqui - nenhum outro módulo escreve `<=>`,
`::vector` ou toca a extensão pgvector diretamente (convenção do README.md).

As colunas `embedding` ficam nas próprias tabelas de domínio (`proposals`,
`discarded_proposals`, `implemented_items` - ver SPEC-03 §7), e não numa tabela
de índice separada. O registry abaixo é o mapa entre o `kind` lógico usado pelo
Motor de Filtragem e a tabela física correspondente.

Contrato do SPEC-01 §6:

    save_embedding(kind, ref_id, text)
    search(text, kinds, top_k=5) -> [(kind, ref_id, similarity, title)]

`session` é opcional em ambos: sem ela, a função abre e fecha a sua própria
transação; com ela, participa da transação de quem chamou.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import NamedTuple

from pgvector.sqlalchemy import Vector
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.llm_client import embed

#: Tipo de coluna a ser usado pelos modelos de domínio que guardam embedding.
EmbeddingVector = Vector(settings.embedding_dim)


@dataclass(frozen=True)
class KindSpec:
    """Onde mora o embedding de um `kind` e como formar seu título."""

    table: str
    id_column: str = "id"
    embedding_column: str = "embedding"
    title_expression: str = "title"
    where: str | None = None


# Kinds canônicos usados pela Memória Histórica (SPEC-03 L1).
# As tabelas são criadas pelos SPECs 03/04; até lá, `search` simplesmente as ignora.
REGISTRY: dict[str, KindSpec] = {
    "implemented": KindSpec(table="implemented_items"),
    "candidata": KindSpec(table="proposals", where="outcome = 'candidata'"),
    "discarded": KindSpec(
        table="discarded_proposals",
        title_expression="coalesce(reason_text, '')",
    ),
    # Pedido que o Avaliador de Zonas encaminhou ao UPA. Fica fora da Memória
    # Histórica (não é trabalho a fazer nem trabalho recusado), mas entra no
    # histórico do módulo que o P1b lê: é recorrência de cauda longa já observada.
    "redirecionada": KindSpec(table="proposals", where="outcome = 'redirecionada_zona'"),
}


class SearchHit(NamedTuple):
    kind: str
    ref_id: int
    similarity: float
    title: str


class UnknownKindError(KeyError):
    pass


def register_kind(kind: str, spec: KindSpec) -> None:
    """Registra um novo kind (usado pelos SPECs seguintes e pelos testes)."""
    REGISTRY[kind] = spec


def _spec(kind: str) -> KindSpec:
    try:
        return REGISTRY[kind]
    except KeyError as exc:
        raise UnknownKindError(f"kind não registrado no vector_store: {kind}") from exc


def _to_literal(vector: list[float]) -> str:
    """Formato textual aceito pelo cast ::vector do pgvector."""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


@contextmanager
def _session(session: Session | None) -> Iterator[Session]:
    """Usa a sessão recebida ou abre uma própria, com commit no fim."""
    if session is not None:
        with nullcontext(session) as own:
            yield own
        return
    from app.common.db import session_scope

    with session_scope() as own:
        yield own


def _table_exists(session: Session, table: str) -> bool:
    return (
        session.execute(sql_text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}).scalar()
        is not None
    )


def save_embedding(
    kind: str,
    ref_id: int,
    text: str,
    *,
    session: Session | None = None,
    vector: list[float] | None = None,
) -> list[float]:
    """Gera e grava o embedding de `text` na linha `ref_id` da tabela do kind.

    Devolve o vetor gravado. `vector` reaproveita um embedding já calculado.
    """
    spec = _spec(kind)
    vector = vector if vector is not None else embed(text)
    with _session(session) as sess:
        result = sess.execute(
            sql_text(
                f"UPDATE {spec.table} "  # nomes de tabela vêm do REGISTRY, nunca do usuário
                f"SET {spec.embedding_column} = CAST(:vec AS vector) "
                f"WHERE {spec.id_column} = :ref_id"
            ),
            {"vec": _to_literal(vector), "ref_id": ref_id},
        )
        if result.rowcount == 0:
            raise LookupError(f"{spec.table}#{ref_id} não existe - embedding não gravado")
    return vector


def search(
    text: str,
    kinds: list[str] | tuple[str, ...] | None = None,
    top_k: int = 5,
    *,
    session: Session | None = None,
    vector: list[float] | None = None,
) -> list[SearchHit]:
    """Busca por similaridade de cosseno nos kinds pedidos.

    Devolve até `top_k` ocorrências ordenadas da mais similar para a menos, como
    tuplas `(kind, ref_id, similarity, title)`, com `similarity` em [0, 1] - 1 é
    idêntico.

    `vector` permite reaproveitar um embedding já calculado: o funil do SPEC-03
    consulta a memória duas vezes (antes do P1b e no L1) e não faz sentido pagar
    a chamada de embedding nas duas.
    """
    kinds = tuple(kinds) if kinds else tuple(REGISTRY)
    literal = _to_literal(vector if vector is not None else embed(text))

    with _session(session) as sess:
        blocks: list[str] = []
        for kind in kinds:
            spec = _spec(kind)
            if not _table_exists(sess, spec.table):
                continue  # tabela ainda não criada pelo SPEC que a introduz
            where = f"{spec.embedding_column} IS NOT NULL"
            if spec.where:
                where += f" AND ({spec.where})"
            blocks.append(
                f"SELECT '{kind}' AS kind, "  # nomes de tabela vêm do REGISTRY
                f"{spec.id_column} AS ref_id, "
                f"1 - ({spec.embedding_column} <=> CAST(:vec AS vector)) AS similarity, "
                f"{spec.title_expression} AS title "
                f"FROM {spec.table} WHERE {where}"
            )

        if not blocks:
            return []

        sql = " UNION ALL ".join(blocks) + " ORDER BY similarity DESC LIMIT :top_k"
        rows = sess.execute(sql_text(sql), {"vec": literal, "top_k": top_k}).all()

    return [SearchHit(r.kind, r.ref_id, float(r.similarity), r.title or "") for r in rows]


def find_duplicate(
    text: str,
    kinds: list[str] | tuple[str, ...] | None = None,
    *,
    session: Session | None = None,
    vector: list[float] | None = None,
) -> SearchHit | None:
    """Melhor match acima de SIMILARITY_THRESHOLD, ou None (SPEC-03 L1)."""
    hits = search(text, kinds, top_k=1, session=session, vector=vector)
    if hits and hits[0].similarity >= settings.similarity_threshold:
        return hits[0]
    return None


# --------------------------------------------------------------------------- #
# Recuperação para os prompts do funil (RAG)
# --------------------------------------------------------------------------- #


class Lembranca(NamedTuple):
    """Item do histórico recuperado para dar contexto a um prompt.

    `occurrences` é o peso do item: quantos pedidos ele já reúne. `outcome` diz o
    que aconteceu com ele (candidata, implementada, o tipo do descarte...) e
    `reason` traz o motivo, quando o item é um descarte.
    """

    kind: str
    ref_id: int
    similarity: float
    title: str
    occurrences: int
    outcome: str
    reason: str


def historico_do_modulo(
    module: str,
    *,
    vector: list[float],
    top_k: int = 5,
    minimo: float = 0.0,
    excluir_proposta: int | None = None,
    session: Session | None = None,
) -> list[Lembranca]:
    """Os pedidos passados mais parecidos com este, no mesmo módulo (P1b).

    Junta as três memórias e os pedidos já encaminhados a uma zona:

    - propostas com embedding: candidatas, em andamento, encaminhadas ao UPA,
      recusadas ou revertidas. As implementadas ficam de fora deste bloco porque
      já aparecem como item implementado;
    - descartes com embedding, pelo módulo da proposta que os originou;
    - itens implementados, pelo módulo da tarefa que os entregou. O baseline do
      seed não tem tarefa, e portanto não tem módulo: entra em qualquer módulo,
      ordenado pela similaridade como o resto.
    """
    sql = """
        SELECT * FROM (
            SELECT 'proposta' AS kind, p.id AS ref_id,
                   1 - (p.embedding <=> CAST(:vec AS vector)) AS similarity,
                   coalesce(p.title, '') AS title, coalesce(p.occurrences, 1) AS occurrences,
                   coalesce(p.outcome, '') AS outcome, '' AS reason
              FROM proposals p
             WHERE p.embedding IS NOT NULL AND p.module = :module AND p.id <> :excluir
               AND coalesce(p.outcome, '') <> 'implementada'
            UNION ALL
            SELECT 'discarded', d.id, 1 - (d.embedding <=> CAST(:vec AS vector)),
                   coalesce(p.title, ''), coalesce(d.duplicate_count, 1),
                   d.reason_type, coalesce(d.reason_text, '')
              FROM discarded_proposals d JOIN proposals p ON p.id = d.proposal_id
             WHERE d.embedding IS NOT NULL AND p.module = :module
            UNION ALL
            SELECT 'implemented', i.id, 1 - (i.embedding <=> CAST(:vec AS vector)),
                   i.title, coalesce(i.duplicate_count, 1), 'implementada', ''
              FROM implemented_items i LEFT JOIN tasks t ON t.id = i.task_id
             WHERE i.embedding IS NOT NULL AND (t.module IS NULL OR t.module = :module)
        ) h
        WHERE h.similarity >= :minimo
        ORDER BY h.similarity DESC
        LIMIT :top_k
    """
    with _session(session) as sess:
        rows = sess.execute(
            sql_text(sql),
            {
                "vec": _to_literal(vector),
                "module": module,
                "excluir": excluir_proposta if excluir_proposta is not None else -1,
                "minimo": minimo,
                "top_k": top_k,
            },
        ).all()
    return [_lembranca(r) for r in rows]


def precedentes_de_descarte(
    *,
    vector: list[float],
    top_k: int = 5,
    minimo: float = 0.0,
    session: Session | None = None,
) -> list[Lembranca]:
    """Os descartes passados mais parecidos com a proposta, com o motivo (P2a).

    Só descartes com embedding: incoerências e recusas humanas. Duplicata nunca
    tem embedding, e não é precedente de escopo - é só uma repetição.
    """
    sql = """
        SELECT * FROM (
            SELECT 'discarded' AS kind, d.id AS ref_id,
                   1 - (d.embedding <=> CAST(:vec AS vector)) AS similarity,
                   coalesce(p.title, '') AS title, coalesce(d.duplicate_count, 1) AS occurrences,
                   d.reason_type AS outcome, coalesce(d.reason_text, '') AS reason
              FROM discarded_proposals d LEFT JOIN proposals p ON p.id = d.proposal_id
             WHERE d.embedding IS NOT NULL
        ) h
        WHERE h.similarity >= :minimo
        ORDER BY h.similarity DESC
        LIMIT :top_k
    """
    with _session(session) as sess:
        rows = sess.execute(
            sql_text(sql),
            {"vec": _to_literal(vector), "minimo": minimo, "top_k": top_k},
        ).all()
    return [_lembranca(r) for r in rows]


def _lembranca(r) -> Lembranca:
    return Lembranca(
        r.kind,
        r.ref_id,
        float(r.similarity),
        r.title or "",
        int(r.occurrences or 1),
        r.outcome or "",
        r.reason or "",
    )
