"""O contrato da zona (SPEC-05 §6).

A regra do SPEC-00 §6 não tem exceção: qualquer violação do contrato cai no
componente nativo. Estes testes existem para garantir que "violação" está
definida com precisão - um contrato frouxo é um contrato que não protege.
"""

import pytest

from app.upa import contracts

SLOT = contracts.RESUMO_FINANCEIRO

VALIDO_SHORTCUT = {
    "widget": "shortcut_list",
    "label": "Seus atalhos",
    "maxItems": 2,
    "items": [
        {"label": "Relatórios do mês", "href": "/relatorios"},
        {"label": "Transações", "href": "/transacoes"},
    ],
}

VALIDO_ALERTA = {
    "widget": "alert_banner",
    "label": "Seus gastos com transporte subiram",
    "tone": "atencao",
}


def test_payload_valido_passa():
    assert contracts.valido(SLOT, VALIDO_SHORTCUT)
    assert contracts.valido(SLOT, VALIDO_ALERTA)


def test_label_longo_demais_e_recusado():
    """O D4 usa exatamente este caso: label com 500 caracteres."""
    payload = {**VALIDO_ALERTA, "label": "x" * 500}

    erros = contracts.erros_de(SLOT, payload)

    assert erros
    assert any("label" in e for e in erros)


def test_href_externo_e_recusado():
    """A regex do contrato é o que impede a zona de virar vetor de link externo."""
    payload = {
        **VALIDO_SHORTCUT,
        "items": [{"label": "Clique aqui", "href": "https://site-externo.example/phishing"}],
    }

    erros = contracts.erros_de(SLOT, payload)

    assert erros
    assert any("href" in e for e in erros)


def test_widget_fora_do_catalogo_e_recusado():
    payload = {"widget": "iframe_injector", "label": "Um iframe", "tone": "neutral"}

    erros = contracts.erros_de(SLOT, payload)

    assert erros
    assert any("widget" in e for e in erros)


def test_propriedade_a_mais_e_recusada():
    """additionalProperties: false - o payload não pode contrabandear campos."""
    payload = {**VALIDO_ALERTA, "onClick": "alert('xss')"}

    assert contracts.erros_de(SLOT, payload)


def test_mais_de_tres_itens_e_recusado():
    payload = {
        **VALIDO_SHORTCUT,
        "maxItems": 3,
        "items": [{"label": f"Item {i}", "href": "/dashboard"} for i in range(4)],
    }

    assert contracts.erros_de(SLOT, payload)


def test_shortcut_sem_items_e_recusado():
    payload = {"widget": "shortcut_list", "label": "Sem itens", "maxItems": 2}

    assert contracts.erros_de(SLOT, payload)


def test_alerta_sem_tone_e_recusado():
    payload = {"widget": "alert_banner", "label": "Sem tom"}

    assert contracts.erros_de(SLOT, payload)


def test_slot_desconhecido_falha_explicitamente():
    with pytest.raises(KeyError):
        contracts.schema_de("zona_que_nao_existe")


def test_o_contrato_canonico_esta_no_repositorio():
    """O schema é a fonte de verdade e vive em docs/contracts/, não no código."""
    caminho = contracts.caminho_do_contrato(SLOT)

    assert caminho.exists(), f"contrato canônico ausente em {caminho}"
    assert contracts.schema_de(SLOT)["additionalProperties"] is False
