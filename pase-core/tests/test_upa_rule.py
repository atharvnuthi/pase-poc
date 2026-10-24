"""A regra de personalização e a defesa em profundidade (SPEC-05 §4)."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.common.models import utcnow
from app.upa import contracts, rule
from app.upa.models import TelemetryEvent, ZonePayload
from tests.conftest import requires_db

SLOT = contracts.RESUMO_FINANCEIRO
ANA = 1

PAYLOAD_VALIDO = {
    "widget": "shortcut_list",
    "label": "Você vive nos relatórios",
    "maxItems": 1,
    "items": [{"label": "Ir para relatórios", "href": "/relatorios"}],
}


@pytest.fixture
def upa_limpo(session):
    def zerar():
        for tabela in ("zone_payloads", "zone_violations", "telemetry_events", "zone_evaluations"):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    yield session
    zerar()


def _acessos(session, quantos: int, *, user_id: int = ANA, path: str = "/relatorios", dias=0):
    for _ in range(quantos):
        session.add(
            TelemetryEvent(
                user_id=user_id,
                event="page_view",
                path=path,
                at=utcnow() - timedelta(days=dias),
            )
        )
    session.commit()


@requires_db
def test_cinco_acessos_disparam_a_avaliacao(upa_limpo):
    _acessos(upa_limpo, 5)

    assert rule.deve_avaliar(upa_limpo, ANA, SLOT) is True


@requires_db
def test_quatro_acessos_nao_disparam(upa_limpo):
    _acessos(upa_limpo, 4)

    assert rule.deve_avaliar(upa_limpo, ANA, SLOT) is False


@requires_db
def test_acessos_fora_da_janela_nao_contam(upa_limpo):
    _acessos(upa_limpo, 5, dias=rule.JANELA_DIAS + 1)

    assert rule.deve_avaliar(upa_limpo, ANA, SLOT) is False


@requires_db
def test_acessos_em_outra_rota_nao_contam(upa_limpo):
    _acessos(upa_limpo, 8, path="/transacoes")

    assert rule.deve_avaliar(upa_limpo, ANA, SLOT) is False


@requires_db
def test_nao_reavalia_quem_ja_tem_payload_ativo(upa_limpo):
    """Sem isto, cada page_view geraria um payload novo e uma chamada de LLM."""
    _acessos(upa_limpo, 10)
    upa_limpo.add(
        ZonePayload(user_id=ANA, slot=SLOT, payload=PAYLOAD_VALIDO, origin="autonoma")
    )
    upa_limpo.commit()

    assert rule.deve_avaliar(upa_limpo, ANA, SLOT) is False


@requires_db
def test_payload_revogado_libera_nova_avaliacao(upa_limpo):
    _acessos(upa_limpo, 5)
    upa_limpo.add(
        ZonePayload(
            user_id=ANA, slot=SLOT, payload=PAYLOAD_VALIDO, origin="autonoma", status="revogado"
        )
    )
    upa_limpo.commit()

    assert rule.deve_avaliar(upa_limpo, ANA, SLOT) is True


@requires_db
def test_geracao_valida_persiste_o_payload(upa_limpo, mock_providers):
    _acessos(upa_limpo, 5)
    mock_providers.responses = [json.dumps({"personalize": True, "payload": PAYLOAD_VALIDO})]

    gerado = rule.gerar_payload(upa_limpo, ANA, SLOT)
    upa_limpo.commit()

    assert gerado == PAYLOAD_VALIDO
    registro = rule.payload_ativo(upa_limpo, ANA, SLOT)
    assert registro is not None
    assert registro.origin == "autonoma"


@requires_db
def test_modelo_pode_decidir_nao_personalizar(upa_limpo, mock_providers):
    """Soft Constraint: personalizar sem benefício polui a tela de quem não pediu."""
    _acessos(upa_limpo, 5)
    mock_providers.responses = [json.dumps({"personalize": False})]

    assert rule.gerar_payload(upa_limpo, ANA, SLOT) is None
    assert rule.payload_ativo(upa_limpo, ANA, SLOT) is None


@requires_db
def test_payload_invalido_do_modelo_nao_e_persistido(upa_limpo, mock_providers):
    """Defesa em profundidade: o core recusa antes de gravar (SPEC-05 §4)."""
    _acessos(upa_limpo, 5)
    fora_do_contrato = {
        "widget": "shortcut_list",
        "label": "x" * 200,
        "maxItems": 9,
        "items": [{"label": "Fora", "href": "https://externo.example"}],
    }
    mock_providers.responses = [json.dumps({"personalize": True, "payload": fora_do_contrato})]

    assert rule.gerar_payload(upa_limpo, ANA, SLOT) is None
    assert rule.payload_ativo(upa_limpo, ANA, SLOT) is None


@requires_db
def test_comportamento_enviado_ao_modelo_resume_as_rotas(upa_limpo, mock_providers):
    _acessos(upa_limpo, 5)
    _acessos(upa_limpo, 2, path="/transacoes")
    mock_providers.responses = [json.dumps({"personalize": False})]

    rule.gerar_payload(upa_limpo, ANA, SLOT)

    enviado = mock_providers.calls[0][0]["content"]
    assert "/relatorios: 5 acesso(s)" in enviado
    assert "/transacoes: 2 acesso(s)" in enviado
