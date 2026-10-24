"""Várias zonas, o intervalo entre avaliações e o UPA reagindo ao pedido do usuário."""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common.models import utcnow
from app.task_layer import pipeline
from app.task_layer.models import Proposal
from app.upa import contracts, rule
from app.upa.models import TelemetryEvent, ZoneEvaluation, ZonePayload
from tests.conftest import requires_db

ANA = 1

PAYLOAD = {
    "widget": "shortcut_list",
    "label": "Seus orçamentos",
    "maxItems": 1,
    "items": [{"label": "Ver orçamentos", "href": "/orcamentos"}],
}
P6_SIM = json.dumps({"personalize": True, "payload": PAYLOAD})
P6_NAO = json.dumps({"personalize": False, "payload": None, "motivo": "pede uma tabela nova"})


@pytest.fixture
def limpo(session):
    def zerar():
        for t in (
            "zone_payloads", "zone_violations", "telemetry_events", "zone_evaluations",
            "tasks", "proposals",
        ):
            session.execute(text(f"DELETE FROM {t}"))
        session.commit()

    zerar()
    yield session
    zerar()


def _visitas(session, rota: str, quantas: int, user_id: int = ANA):
    for _ in range(quantas):
        session.add(TelemetryEvent(user_id=user_id, event="page_view", path=rota, at=utcnow()))
    session.commit()


# --------------------------------------------------------------------------- #
# O registro
# --------------------------------------------------------------------------- #


def test_todas_as_zonas_compartilham_um_contrato_e_o_slot_e_valido():
    assert len(contracts.ZONAS) >= 6
    for slot in contracts.ZONAS:
        assert contracts.valido(slot, PAYLOAD)


@pytest.mark.parametrize("href", ["/orcamentos", "/metas", "/suporte", "/dashboard"])
def test_contrato_aceita_as_rotas_novas(href):
    p = {**PAYLOAD, "items": [{"label": "x", "href": href}]}
    assert contracts.valido(contracts.ORCAMENTOS_AVISO, p)


@pytest.mark.parametrize("href", ["https://evil.example", "/admin", "//evil.com", "/metas/1"])
def test_contrato_continua_recusando_o_que_nao_e_rota_interna_conhecida(href):
    p = {**PAYLOAD, "items": [{"label": "x", "href": href}]}
    assert not contracts.valido(contracts.ORCAMENTOS_AVISO, p)


def test_cada_modulo_tem_uma_zona_e_cada_zona_um_modulo_do_funil():
    from app.task_layer.models import MODULOS

    for modulo, slot in contracts.ZONA_DO_MODULO.items():
        assert modulo in MODULOS
        assert contracts.ZONAS[slot].modulo == modulo


# --------------------------------------------------------------------------- #
# Regra por zona
# --------------------------------------------------------------------------- #


@requires_db
def test_cada_zona_observa_a_sua_rota_e_o_seu_minimo(limpo):
    _visitas(limpo, "/orcamentos", 2)
    assert not rule.deve_avaliar(limpo, ANA, contracts.ORCAMENTOS_AVISO)  # mínimo é 3

    _visitas(limpo, "/orcamentos", 1)
    assert rule.deve_avaliar(limpo, ANA, contracts.ORCAMENTOS_AVISO)
    # visitar uma rota não dispara a zona de outra
    assert not rule.deve_avaliar(limpo, ANA, contracts.METAS_INCENTIVO)


@requires_db
def test_avaliar_rota_so_acorda_as_zonas_que_observam_aquela_rota(limpo, mock_providers):
    _visitas(limpo, "/metas", 3)
    mock_providers.responses = [P6_SIM]

    assert rule.avaliar_rota(ANA, "/metas") == 1

    zonas = {z.slot for z in limpo.query(ZonePayload).all()}
    assert zonas == {contracts.METAS_INCENTIVO}
    assert rule.avaliar_rota(ANA, "/rota-sem-zona") == 0


@requires_db
def test_zona_recusada_nao_e_reavaliada_a_cada_visita(limpo, mock_providers):
    """Cada avaliação é uma chamada ao modelo: o intervalo impede pagar de novo."""
    _visitas(limpo, "/metas", 3)
    mock_providers.responses = [P6_NAO]

    assert rule.avaliar(ANA, contracts.METAS_INCENTIVO) is None
    chamadas_antes = len(mock_providers.calls)

    _visitas(limpo, "/metas", 1)
    assert rule.avaliar(ANA, contracts.METAS_INCENTIVO) is None

    assert len(mock_providers.calls) == chamadas_antes  # nenhuma chamada nova
    assert limpo.query(ZoneEvaluation).filter_by(resultado="recusou").count() == 1


@requires_db
def test_passado_o_intervalo_a_zona_pode_ser_avaliada_de_novo(limpo, mock_providers):
    _visitas(limpo, "/metas", 3)
    limpo.add(
        ZoneEvaluation(
            user_id=ANA, slot=contracts.METAS_INCENTIVO, resultado="recusou",
            at=utcnow() - timedelta(hours=25),
        )
    )
    limpo.commit()

    assert rule.deve_avaliar(limpo, ANA, contracts.METAS_INCENTIVO)


@requires_db
def test_ignorar_a_regra_serve_a_demonstracao(limpo, mock_providers):
    mock_providers.responses = [P6_SIM]

    assert rule.avaliar(ANA, contracts.METAS_INCENTIVO, ignorar_regra=True) == PAYLOAD


# --------------------------------------------------------------------------- #
# Por pedido
# --------------------------------------------------------------------------- #


@requires_db
def test_o_pedido_vai_ao_p6_como_dica_e_ele_pode_atender(limpo, mock_providers):
    mock_providers.responses = [P6_SIM]

    r = rule.gerar_por_pedido(ANA, contracts.ORCAMENTOS_AVISO, "quero ver meus limites rápido")

    assert r.personalizou
    prompt = mock_providers.calls[0][0]["content"]
    assert "quero ver meus limites rápido" in prompt and "dica" in prompt
    assert limpo.query(ZonePayload).filter_by(slot=contracts.ORCAMENTOS_AVISO).count() == 1


@requires_db
def test_pedido_que_o_contrato_nao_permite_volta_com_o_motivo(limpo, mock_providers):
    mock_providers.responses = [P6_NAO]

    r = rule.gerar_por_pedido(ANA, contracts.ORCAMENTOS_AVISO, "uma tabela comparando bancos")

    assert not r.personalizou and r.motivo == "pede uma tabela nova"
    assert limpo.query(ZonePayload).count() == 0


@requires_db
def test_pedido_novo_substitui_o_payload_anterior(limpo, mock_providers):
    mock_providers.responses = [P6_SIM, P6_SIM]
    rule.gerar_por_pedido(ANA, contracts.ORCAMENTOS_AVISO, "primeiro")
    rule.gerar_por_pedido(ANA, contracts.ORCAMENTOS_AVISO, "segundo")

    limpo.expire_all()
    status = [p.status for p in limpo.query(ZonePayload).order_by(ZonePayload.id)]
    assert status == ["revogado", "ativo"]


@requires_db
def test_payload_invalido_do_modelo_nao_e_gravado_nem_no_pedido(limpo, mock_providers):
    externo = {**PAYLOAD, "items": [{"label": "x", "href": "https://e.com"}]}
    mock_providers.responses = [json.dumps({"personalize": True, "payload": externo})]

    r = rule.gerar_por_pedido(ANA, contracts.ORCAMENTOS_AVISO, "qualquer")

    assert not r.personalizou and "contrato" in r.motivo
    assert limpo.query(ZonePayload).count() == 0


# --------------------------------------------------------------------------- #
# O funil: "redirecionada ao UPA" agora faz o que diz
# --------------------------------------------------------------------------- #

P1 = json.dumps(
    {"title": "Ver meus limites do jeito que eu quero", "description": "x", "module": "orcamentos"}
)
P1B_SIM = json.dumps({"requires_zone": True, "reasoning": "cauda longa"})
P2A_OK = json.dumps({"coherent": True, "reason": "cabe no escopo", "needs_adjustment": False})


@requires_db
def test_redirecionar_personaliza_a_zona_do_usuario_que_pediu(limpo, mock_providers):
    proposta = Proposal(origin="external", raw_text="quero meus limites no topo", user_id=ANA)
    limpo.add(proposta)
    limpo.flush()
    mock_providers.responses = [P1, P1B_SIM, P2A_OK, P6_SIM]

    envelope = pipeline.run(limpo, proposta)

    assert envelope.outcome == "redirecionada_zona"
    assert "Ajustamos a área" in envelope.detail and "/orcamentos" in envelope.detail
    zona = limpo.query(ZonePayload).one()
    assert zona.slot == contracts.ORCAMENTOS_AVISO and zona.user_id == ANA
    # a dica foi o texto que a pessoa escreveu
    assert "quero meus limites no topo" in mock_providers.calls[-1][0]["content"]


@requires_db
def test_redirecionar_sem_conseguir_nao_promete_o_que_nao_aconteceu(limpo, mock_providers):
    proposta = Proposal(origin="external", raw_text="uma tabela de bancos", user_id=ANA)
    limpo.add(proposta)
    limpo.flush()
    mock_providers.responses = [P1, P1B_SIM, P2A_OK, P6_NAO]

    envelope = pipeline.run(limpo, proposta)

    assert envelope.outcome == "redirecionada_zona"
    assert "não conseguimos ajustá-la" in envelope.detail
    assert "pede uma tabela nova" in envelope.detail
    assert "Ajustamos" not in envelope.detail
    assert limpo.query(ZonePayload).count() == 0


@requires_db
def test_redirecionar_pedido_sem_usuario_so_registra(limpo, mock_providers):
    proposta = Proposal(origin="internal", type="funcional", raw_text="limites rápidos")
    limpo.add(proposta)
    limpo.flush()
    mock_providers.responses = [P1, P1B_SIM, P2A_OK]

    envelope = pipeline.run(limpo, proposta)

    assert envelope.outcome == "redirecionada_zona"
    assert "não veio de uma pessoa específica" in envelope.detail
    assert limpo.query(ZonePayload).count() == 0


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(limpo):
    from app.main import app

    with TestClient(app) as c:
        yield c


@requires_db
def test_api_lista_as_zonas(client):
    zonas = client.get("/api/upa/zones").json()

    assert {z["slot"] for z in zonas} >= {
        "resumo_financeiro", "transacoes_atalhos", "relatorios_destaque",
        "orcamentos_aviso", "metas_incentivo", "suporte_ajuda",
    }
    assert all(z["tela"].startswith("/") for z in zonas)


@requires_db
def test_api_serve_o_payload_de_qualquer_zona(client, limpo):
    limpo.add(ZonePayload(user_id=ANA, slot="metas_incentivo", payload=PAYLOAD))
    limpo.commit()

    r = client.get("/api/upa/zones/metas_incentivo/payload", params={"user_id": ANA})

    assert r.status_code == 200 and r.json()["payload"]["label"] == "Seus orçamentos"


@requires_db
def test_telemetria_dispara_so_as_zonas_da_rota(client, limpo, mock_providers):
    _visitas(limpo, "/suporte", 1)
    mock_providers.responses = [P6_SIM]

    client.post(
        "/api/upa/telemetry", json={"user_id": ANA, "event": "page_view", "path": "/suporte"}
    )

    slots = {z.slot for z in limpo.query(ZonePayload).all()}
    assert slots == {"suporte_ajuda"}  # mínimo de 2 visitas, e esta foi a segunda


@requires_db
def test_simulate_aceita_qualquer_zona(client, mock_providers, monkeypatch):
    from app.upa import routes

    monkeypatch.setattr(routes.settings, "demo_mode", True)
    mock_providers.responses = [P6_SIM]

    r = client.post("/api/upa/simulate", json={"user_id": ANA, "slot": "metas_incentivo"})

    assert r.status_code == 200 and r.json()["personalizado"]
    assert r.json()["eventos_inseridos"] == 3
    desconhecida = client.post("/api/upa/simulate", json={"user_id": ANA, "slot": "nao-existe"})
    assert desconhecida.status_code == 404
