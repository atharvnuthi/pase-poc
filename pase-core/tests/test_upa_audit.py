"""Personalização revogável e auditável (§4.5.4, §4.5.5, R3).

Três garantias:
- a pessoa volta ao padrão pela própria zona, e a escolha dela é durável;
- cada avaliação guarda os sinais, a decisão do agente, o motivo e o que saiu dela;
- payload que o core recusa é violação registrada, com a origem `servidor`.
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common.config import settings
from app.common.models import utcnow
from app.upa import contracts, rule
from app.upa.models import TelemetryEvent, ZoneEvaluation, ZonePayload, ZoneViolation
from tests.conftest import requires_db

SLOT = contracts.RESUMO_FINANCEIRO
ANA, CLARA = 1, 2

PAYLOAD = {
    "widget": "shortcut_list",
    "label": "Você vive nos relatórios",
    "maxItems": 1,
    "items": [{"label": "Ir para relatórios", "href": "/relatorios"}],
}
P6_SIM = json.dumps({"personalize": True, "payload": PAYLOAD, "motivo": "abre relatórios todo dia"})
P6_NAO = json.dumps({"personalize": False, "payload": None, "motivo": "o uso não sugere nada"})
FORA = {**PAYLOAD, "items": [{"label": "Oferta", "href": "https://externo.example"}]}
P6_FORA = json.dumps({"personalize": True, "payload": FORA})


@pytest.fixture
def limpo(session):
    def zerar():
        for t in ("zone_payloads", "zone_violations", "telemetry_events", "zone_evaluations"):
            session.execute(text(f"DELETE FROM {t}"))
        session.commit()

    zerar()
    yield session
    zerar()


@pytest.fixture
def client(limpo):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _acessos(session, quantos: int = 5, rota: str = "/relatorios"):
    for _ in range(quantos):
        session.add(TelemetryEvent(user_id=ANA, event="page_view", path=rota, at=utcnow()))
    session.commit()


def _payload(session, **campos) -> ZonePayload:
    registro = ZonePayload(user_id=ANA, slot=SLOT, payload=PAYLOAD, origin="autonoma", **campos)
    session.add(registro)
    session.commit()
    return registro


def _passado_o_intervalo() -> datetime:
    return utcnow() - timedelta(hours=settings.zone_reevaluation_hours + 1)


# --------------------------------------------------------------------------- #
# Voltar ao padrão
# --------------------------------------------------------------------------- #


@requires_db
def test_a_pessoa_volta_ao_padrao_pela_propria_zona(client, limpo):
    registro = _payload(limpo)

    r = client.post(
        f"/api/upa/payloads/{registro.id}/revoke", json={"por": "usuario", "user_id": ANA}
    )

    assert r.status_code == 200
    assert r.json() == {"payload_id": registro.id, "status": "revogado", "revoked_by": "usuario"}
    assert client.get(f"/api/upa/zones/{SLOT}/payload", params={"user_id": ANA}).status_code == 204
    limpo.expire_all()
    assert limpo.get(ZonePayload, registro.id).revoked_at is not None


@requires_db
def test_uma_tela_nao_desfaz_a_zona_de_outra_pessoa(client, limpo):
    registro = _payload(limpo)

    r = client.post(
        f"/api/upa/payloads/{registro.id}/revoke", json={"por": "usuario", "user_id": CLARA}
    )

    assert r.status_code == 403
    limpo.expire_all()
    assert limpo.get(ZonePayload, registro.id).status == "ativo"


@requires_db
def test_revogar_sem_corpo_continua_sendo_o_painel(client, limpo):
    registro = _payload(limpo)

    r = client.post(f"/api/upa/payloads/{registro.id}/revoke")

    assert r.status_code == 200 and r.json()["revoked_by"] == "painel"


@requires_db
def test_volta_ao_padrao_pela_pessoa_e_duravel(limpo):
    """Passado o intervalo, a regra automática não personaliza de novo (R3)."""
    _acessos(limpo, 10)
    _payload(limpo, status="revogado", revoked_by="usuario", revoked_at=_passado_o_intervalo())
    limpo.add(ZoneEvaluation(user_id=ANA, slot=SLOT, resultado="personalizou",
                             at=_passado_o_intervalo()))
    limpo.commit()

    assert rule.deve_avaliar(limpo, ANA, SLOT) is False


@requires_db
def test_volta_ao_padrao_vale_so_para_aquela_zona(limpo):
    _acessos(limpo, 5, rota="/metas")
    _payload(limpo, status="revogado", revoked_by="usuario", revoked_at=utcnow())

    assert rule.deve_avaliar(limpo, ANA, contracts.METAS_INCENTIVO) is True


@requires_db
def test_revogacao_pelo_painel_espera_o_intervalo_e_libera(limpo):
    """O operador julgou um payload, não a preferência da pessoa."""
    _acessos(limpo, 5)
    registro = _payload(limpo, status="revogado", revoked_by="painel", revoked_at=utcnow())

    assert rule.deve_avaliar(limpo, ANA, SLOT) is False  # não volta na visita seguinte

    registro.revoked_at = _passado_o_intervalo()
    limpo.commit()
    assert rule.deve_avaliar(limpo, ANA, SLOT) is True


@requires_db
def test_pedido_explicito_reabre_a_zona_que_a_pessoa_desligou(limpo, mock_providers):
    _payload(limpo, status="revogado", revoked_by="usuario", revoked_at=utcnow())
    mock_providers.responses = [P6_SIM]

    r = rule.gerar_por_pedido(ANA, SLOT, "quero um atalho para os relatórios")

    assert r.personalizou
    assert rule.payload_ativo(limpo, ANA, SLOT) is not None


@requires_db
def test_pedido_novo_registra_que_substituiu_o_anterior(limpo, mock_providers):
    mock_providers.responses = [P6_SIM, P6_SIM]
    rule.gerar_por_pedido(ANA, SLOT, "primeiro")
    rule.gerar_por_pedido(ANA, SLOT, "segundo")

    limpo.expire_all()
    antigo = limpo.query(ZonePayload).order_by(ZonePayload.id).first()
    assert (antigo.status, antigo.revoked_by) == ("revogado", "pedido")


# --------------------------------------------------------------------------- #
# Avaliações registradas
# --------------------------------------------------------------------------- #


@requires_db
def test_avaliacao_que_personaliza_guarda_sinais_decisao_motivo_e_payload(limpo, mock_providers):
    _acessos(limpo, 5)
    mock_providers.responses = [P6_SIM]

    rule.avaliar(ANA, SLOT)

    avaliacao = limpo.query(ZoneEvaluation).one()
    assert avaliacao.resultado == "personalizou"
    assert avaliacao.decisao is True
    assert avaliacao.motivo == "abre relatórios todo dia"
    assert "/relatorios: 5 acesso(s)" in avaliacao.sinais
    assert avaliacao.payload_id == rule.payload_ativo(limpo, ANA, SLOT).id
    assert avaliacao.trace_id
    assert avaliacao.pedido is None


@requires_db
def test_avaliacao_que_recusa_guarda_o_motivo_do_agente(limpo, mock_providers):
    _acessos(limpo, 5)
    mock_providers.responses = [P6_NAO]

    rule.avaliar(ANA, SLOT)

    avaliacao = limpo.query(ZoneEvaluation).one()
    assert (avaliacao.resultado, avaliacao.decisao) == ("recusou", False)
    assert avaliacao.motivo == "o uso não sugere nada"
    assert avaliacao.payload_id is None


@requires_db
def test_avaliacao_por_pedido_guarda_o_texto_da_pessoa(limpo, mock_providers):
    mock_providers.responses = [P6_NAO]

    rule.gerar_por_pedido(ANA, SLOT, "uma tabela comparando bancos")

    avaliacao = limpo.query(ZoneEvaluation).one()
    assert avaliacao.resultado == "pedido_recusado"
    assert avaliacao.pedido == "uma tabela comparando bancos"


@requires_db
def test_api_lista_as_avaliacoes(client, limpo, mock_providers):
    _acessos(limpo, 5)
    mock_providers.responses = [P6_NAO]
    rule.avaliar(ANA, SLOT)

    linhas = client.get("/api/upa/evaluations").json()

    assert len(linhas) == 1
    assert linhas[0]["slot"] == SLOT and linhas[0]["decisao"] is False
    assert linhas[0]["motivo"] == "o uso não sugere nada"
    assert "/relatorios" in linhas[0]["sinais"]


# --------------------------------------------------------------------------- #
# Recusa do servidor é violação
# --------------------------------------------------------------------------- #


@requires_db
def test_payload_recusado_pelo_core_vira_violacao_do_servidor(limpo, mock_providers):
    _acessos(limpo, 5)
    mock_providers.responses = [P6_FORA]

    assert rule.avaliar(ANA, SLOT) is None

    violacao = limpo.query(ZoneViolation).one()
    assert violacao.origem == "servidor"
    assert "href" in violacao.reason
    assert violacao.raw_payload == FORA
    assert limpo.query(ZonePayload).count() == 0

    avaliacao = limpo.query(ZoneEvaluation).one()
    assert (avaliacao.resultado, avaliacao.decisao) == ("fora_do_contrato", True)
    assert avaliacao.violation_id == violacao.id


@requires_db
def test_recusa_do_core_num_pedido_tambem_e_registrada(limpo, mock_providers):
    mock_providers.responses = [P6_FORA]

    rule.gerar_por_pedido(ANA, SLOT, "um link para o meu banco")

    assert limpo.query(ZoneViolation).one().origem == "servidor"
    assert limpo.query(ZoneEvaluation).one().resultado == "pedido_fora_do_contrato"


@requires_db
def test_payload_que_nem_e_objeto_tambem_fica_registrado(limpo, mock_providers):
    mock_providers.responses = [json.dumps({"personalize": True, "payload": None})]

    rule.gerar_por_pedido(ANA, SLOT, "qualquer")

    assert limpo.query(ZoneViolation).one().raw_payload == {"payload": None}


@requires_db
def test_violacao_do_cliente_continua_com_origem_cliente(client, limpo):
    client.post(
        "/api/upa/violations",
        json={"user_id": ANA, "slot": SLOT, "reason": "label: longo demais", "raw_payload": {}},
    )

    assert [v["origem"] for v in client.get("/api/upa/violations").json()] == ["cliente"]
