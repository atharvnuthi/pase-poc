"""Endpoints do UPA (SPEC-05 §3)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.upa import contracts
from app.upa.models import ZonePayload, ZoneViolation
from tests.conftest import requires_db

SLOT = contracts.RESUMO_FINANCEIRO
ANA, CLARA = 1, 2

PAYLOAD_VALIDO = {
    "widget": "summary_card",
    "label": "O que você acompanha",
    "maxItems": 1,
    "items": [{"label": "Relatórios", "href": "/relatorios"}],
}


@pytest.fixture
def client(session):
    from app.main import app

    def zerar():
        for tabela in ("zone_payloads", "zone_violations", "telemetry_events", "zone_evaluations"):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    with TestClient(app) as test_client:
        yield test_client
    zerar()


@requires_db
def test_sem_payload_responde_204(client):
    """204 é o caminho normal: quem não tem zona vê o componente nativo."""
    resposta = client.get(f"/api/upa/zones/{SLOT}/payload", params={"user_id": CLARA})

    assert resposta.status_code == 204


@requires_db
def test_slot_desconhecido_responde_404(client):
    assert client.get("/api/upa/zones/inexistente/payload", params={"user_id": ANA}).status_code == 404


@requires_db
def test_simulate_gera_payload_e_isola_por_usuario(client, session, mock_providers):
    """D3: a Ana recebe o widget; a Clara continua no nativo."""
    mock_providers.responses = [json.dumps({"personalize": True, "payload": PAYLOAD_VALIDO})]

    resposta = client.post("/api/upa/simulate", json={"user_id": ANA, "scenario": "ana_relatorios"})

    assert resposta.status_code == 200
    assert resposta.json()["personalizado"] is True

    da_ana = client.get(f"/api/upa/zones/{SLOT}/payload", params={"user_id": ANA})
    assert da_ana.status_code == 200
    assert da_ana.json()["payload"] == PAYLOAD_VALIDO
    assert da_ana.json()["origin"] == "autonoma"

    assert client.get(f"/api/upa/zones/{SLOT}/payload", params={"user_id": CLARA}).status_code == 204


@requires_db
def test_revogar_devolve_o_usuario_ao_nativo(client, session, mock_providers):
    mock_providers.responses = [json.dumps({"personalize": True, "payload": PAYLOAD_VALIDO})]
    client.post("/api/upa/simulate", json={"user_id": ANA})

    payload_id = client.get("/api/upa/payloads").json()[0]["id"]
    resposta = client.post(f"/api/upa/payloads/{payload_id}/revoke")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "revogado"
    assert client.get(f"/api/upa/zones/{SLOT}/payload", params={"user_id": ANA}).status_code == 204


@requires_db
def test_inject_raw_grava_sem_validar_e_avisa_o_que_o_core_recusaria(client, session):
    """D4: contornar a própria validação é o ponto - o cliente ainda recusa."""
    invalido = {"widget": "iframe_injector", "label": "malicioso"}

    resposta = client.post(
        "/api/upa/inject-raw", json={"user_id": ANA, "slot": SLOT, "payload": invalido}
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["core_o_recusaria"] is True
    assert corpo["erros_do_core"]

    gravado = session.get(ZonePayload, corpo["payload_id"])
    assert gravado.origin == "injetado"
    assert gravado.payload == invalido  # gravado como veio, sem sanitizar


@requires_db
def test_inject_raw_bloqueado_sem_demo_mode(client, monkeypatch):
    from app.upa import routes

    monkeypatch.setattr(routes.settings, "demo_mode", False)

    resposta = client.post(
        "/api/upa/inject-raw", json={"user_id": ANA, "slot": SLOT, "payload": {}}
    )

    assert resposta.status_code == 403


@requires_db
def test_simulate_bloqueado_sem_demo_mode(client, monkeypatch):
    from app.upa import routes

    monkeypatch.setattr(routes.settings, "demo_mode", False)

    assert client.post("/api/upa/simulate", json={"user_id": ANA}).status_code == 403


@requires_db
def test_violacao_do_cliente_e_registrada(client, session):
    """Sem este registro, o payload malformado sumiria no fallback sem rastro."""
    resposta = client.post(
        "/api/upa/violations",
        json={
            "user_id": ANA,
            "slot": SLOT,
            "reason": "items.0.href: não confere com o padrão",
            "raw_payload": {"widget": "shortcut_list"},
        },
    )

    assert resposta.status_code == 201
    registrada = session.get(ZoneViolation, resposta.json()["id"])
    assert "href" in registrada.reason
    assert registrada.raw_payload == {"widget": "shortcut_list"}

    listagem = client.get("/api/upa/violations").json()
    assert len(listagem) == 1


@requires_db
def test_telemetria_continua_persistindo(client, session):
    resposta = client.post(
        "/api/upa/telemetry", json={"user_id": ANA, "event": "page_view", "path": "/relatorios"}
    )

    assert resposta.status_code == 201
