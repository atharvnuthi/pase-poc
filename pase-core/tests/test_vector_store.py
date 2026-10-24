"""Critério SPEC-01 §8.3: save_embedding + search gravam e recuperam com similaridade correta."""

import pytest
from sqlalchemy import text

from app.common import vector_store
from app.common.config import settings
from app.common.vector_store import KindSpec, find_duplicate, save_embedding, search
from tests.conftest import requires_db

KIND = "teste_memoria"
TABLE = "teste_memoria_items"


@pytest.fixture
def memoria(session):
    """Tabela descartável com coluna vector, registrada como um kind próprio."""
    session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
    session.execute(
        text(
            f"CREATE TABLE {TABLE} ("
            "id serial PRIMARY KEY, "
            "title text NOT NULL, "
            f"embedding vector({settings.embedding_dim})"
            ")"
        )
    )
    vector_store.register_kind(KIND, KindSpec(table=TABLE))
    session.commit()
    yield session
    session.rollback()
    session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
    session.commit()
    vector_store.REGISTRY.pop(KIND, None)


def _insert(session, title: str) -> int:
    return session.execute(
        text(f"INSERT INTO {TABLE} (title) VALUES (:t) RETURNING id"), {"t": title}
    ).scalar_one()


@requires_db
def test_grava_e_recupera_com_similaridade_correta(memoria):
    session = memoria
    csv_id = _insert(session, "exportar minhas transações em csv")
    cripto_id = _insert(session, "minerar criptomoedas dentro do aplicativo")

    save_embedding(KIND, csv_id, "exportar minhas transações em csv", session=session)
    save_embedding(KIND, cripto_id, "minerar criptomoedas dentro do aplicativo", session=session)
    session.commit()

    hits = search("exportar minhas transações em csv", [KIND], top_k=5, session=session)

    assert [h.ref_id for h in hits] == [csv_id, cripto_id]  # o idêntico vem primeiro
    assert hits[0].kind == KIND
    assert hits[0].title == "exportar minhas transações em csv"
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-5)
    assert hits[1].similarity < hits[0].similarity


@requires_db
def test_find_duplicate_respeita_o_limiar(memoria):
    session = memoria
    ref = _insert(session, "exportar minhas transações em csv")
    save_embedding(KIND, ref, "exportar minhas transações em csv", session=session)
    session.commit()

    igual = find_duplicate("exportar minhas transações em csv", [KIND], session=session)
    assert igual is not None and igual.ref_id == ref
    assert igual.similarity >= settings.similarity_threshold

    outro = find_duplicate("integrar editor de vídeo no dashboard", [KIND], session=session)
    assert outro is None


@requires_db
def test_linha_inexistente_nao_grava_silenciosamente(memoria):
    with pytest.raises(LookupError):
        save_embedding(KIND, 99999, "qualquer coisa", session=memoria)


@requires_db
def test_kinds_de_tabelas_ainda_inexistentes_sao_ignorados(session):
    """Em F0 as tabelas do SPEC-03 ainda não existem; search não pode quebrar."""
    assert search("qualquer coisa", ["implemented", "discarded"], session=session) == []


def test_kind_desconhecido_e_erro_explicito():
    with pytest.raises(vector_store.UnknownKindError):
        vector_store._spec("kind_que_nao_existe")
