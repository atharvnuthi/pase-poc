"""Ingestão de telemetria (SPEC-02 §3.3, antecipando o SPEC-05 §2)."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.upa.models import TelemetryEvent
from tests.conftest import requires_db


@requires_db
def test_page_view_e_persistido_em_telemetry_events(session):
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/upa/telemetry",
            json={"user_id": 1, "event": "page_view", "path": "/relatorios"},
        )

    assert response.status_code == 201
    novo_id = response.json()["id"]

    gravado = session.get(TelemetryEvent, novo_id)
    assert gravado is not None
    assert (gravado.user_id, gravado.event, gravado.path) == (1, "page_view", "/relatorios")
    assert gravado.at is not None

    session.execute(text("DELETE FROM telemetry_events WHERE id = :id"), {"id": novo_id})
    session.commit()


@requires_db
def test_payload_invalido_nao_grava(session):
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/upa/telemetry", json={"user_id": 1, "event": "page_view"})

    assert response.status_code == 422
