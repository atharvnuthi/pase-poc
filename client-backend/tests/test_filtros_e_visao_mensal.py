"""Filtros da lista de transações e a visão mensal do dashboard (RF-12 e RF-13)."""

from datetime import date, timedelta
from decimal import Decimal

HOJE = date.today()
MES_PASSADO = (HOJE.replace(day=1) - timedelta(days=1)).replace(day=10)


def _mes(dia: date) -> str:
    return f"{dia.year:04d}-{dia.month:02d}"


def _lanca(client, user_id, category_id, valor, descricao="x", dia=HOJE, tipo="expense"):
    r = client.post(
        "/transactions",
        json={
            "user_id": user_id, "category_id": category_id, "type": tipo, "amount": valor,
            "date": dia.isoformat(), "description": descricao,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _descricoes(client, **params) -> list[str]:
    return [t["description"] for t in client.get("/transactions", params=params).json()]


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #


def test_sem_filtros_devolve_tudo_como_sempre(client, ana, categoria_alimentacao):
    _lanca(client, ana, categoria_alimentacao, "10.00", "a")
    _lanca(client, ana, categoria_alimentacao, "20.00", "b")

    assert sorted(_descricoes(client, user_id=ana)) == ["a", "b"]


def test_busca_por_texto_ignora_caixa_e_acento(client, ana, categoria_alimentacao):
    _lanca(client, ana, categoria_alimentacao, "10.00", "Padaria do Zé")
    _lanca(client, ana, categoria_alimentacao, "20.00", "Supermercado")

    assert _descricoes(client, user_id=ana, q="padaria") == ["Padaria do Zé"]
    assert _descricoes(client, user_id=ana, q="ZE") == ["Padaria do Zé"]
    assert _descricoes(client, user_id=ana, q="  ") != []  # busca em branco não filtra


def test_busca_acha_acentuada_digitando_sem_acento(client, ana, categoria_alimentacao):
    _lanca(client, ana, categoria_alimentacao, "10.00", "Almoço executivo")

    assert _descricoes(client, user_id=ana, q="almoco") == ["Almoço executivo"]


def test_filtra_por_categoria_e_por_tipo(
    client, ana, categoria_alimentacao, categoria_transporte, categoria_salario
):
    _lanca(client, ana, categoria_alimentacao, "10.00", "comida")
    _lanca(client, ana, categoria_transporte, "20.00", "ônibus")
    _lanca(client, ana, categoria_salario, "900.00", "salário", tipo="income")

    assert _descricoes(client, user_id=ana, category_id=categoria_transporte) == ["ônibus"]
    assert _descricoes(client, user_id=ana, type="income") == ["salário"]
    assert sorted(_descricoes(client, user_id=ana, type="expense")) == ["comida", "ônibus"]


def test_filtra_por_mes_incluindo_o_primeiro_e_o_ultimo_dia(client, ana, categoria_alimentacao):
    primeiro = MES_PASSADO.replace(day=1)
    ultimo = HOJE.replace(day=1) - timedelta(days=1)
    _lanca(client, ana, categoria_alimentacao, "1.00", "dia 1", dia=primeiro)
    _lanca(client, ana, categoria_alimentacao, "2.00", "último dia", dia=ultimo)
    _lanca(client, ana, categoria_alimentacao, "3.00", "este mês")

    assert sorted(_descricoes(client, user_id=ana, month=_mes(MES_PASSADO))) == [
        "dia 1", "último dia",
    ]
    assert _descricoes(client, user_id=ana, month=_mes(HOJE)) == ["este mês"]


def test_filtros_se_combinam(client, ana, categoria_alimentacao, categoria_transporte):
    _lanca(client, ana, categoria_alimentacao, "10.00", "padaria")
    _lanca(client, ana, categoria_transporte, "20.00", "padaria do ônibus")
    _lanca(client, ana, categoria_alimentacao, "30.00", "mercado")

    assert _descricoes(
        client, user_id=ana, q="padaria", category_id=categoria_alimentacao
    ) == ["padaria"]


def test_limite_corta_a_lista_mantendo_as_mais_recentes(client, ana, categoria_alimentacao):
    _lanca(client, ana, categoria_alimentacao, "1.00", "antiga", dia=MES_PASSADO)
    _lanca(client, ana, categoria_alimentacao, "2.00", "recente")

    assert _descricoes(client, user_id=ana, limit=1) == ["recente"]


def test_filtro_nunca_mostra_transacao_de_outra_pessoa(client, ana, clara, categoria_alimentacao):
    _lanca(client, clara, categoria_alimentacao, "10.00", "da Clara")

    assert _descricoes(client, user_id=ana, q="clara") == []


def test_mes_invalido_e_422(client, ana):
    r = client.get("/transactions", params={"user_id": ana, "month": "13-2026"})

    assert r.status_code == 422
    assert "month" in {item["loc"][-1] for item in r.json()["detail"]}


# --------------------------------------------------------------------------- #
# Visão mensal
# --------------------------------------------------------------------------- #


def test_visao_mensal_devolve_os_ultimos_meses_do_mais_antigo_ao_mais_novo(client, ana):
    meses = [m["month"] for m in client.get("/summary/monthly", params={"user_id": ana}).json()]

    assert len(meses) == 6 and meses == sorted(meses) and meses[-1] == _mes(HOJE)


def test_mes_sem_movimento_aparece_com_zero(client, ana):
    visao = client.get("/summary/monthly", params={"user_id": ana, "months": 3}).json()

    assert all(Decimal(str(m["income"])) == 0 and Decimal(str(m["expense"])) == 0 for m in visao)


def test_visao_mensal_separa_receita_de_despesa_em_centavos_exatos(
    client, ana, categoria_alimentacao, categoria_salario
):
    _lanca(client, ana, categoria_salario, "3000.00", tipo="income")
    for valor in ("0.10", "0.20"):
        _lanca(client, ana, categoria_alimentacao, valor)
    _lanca(client, ana, categoria_alimentacao, "9.99", dia=MES_PASSADO)

    visao = {m["month"]: m for m in client.get("/summary/monthly", params={"user_id": ana}).json()}

    este = visao[_mes(HOJE)]
    assert Decimal(str(este["income"])) == Decimal("3000.00")
    assert Decimal(str(este["expense"])) == Decimal("0.30")
    assert Decimal(str(visao[_mes(MES_PASSADO)]["expense"])) == Decimal("9.99")


def test_visao_mensal_nao_mistura_pessoas_e_valida_o_intervalo(
    client, ana, clara, categoria_alimentacao
):
    _lanca(client, clara, categoria_alimentacao, "50.00")

    visao = client.get("/summary/monthly", params={"user_id": ana}).json()

    assert all(Decimal(str(m["expense"])) == 0 for m in visao)
    assert client.get("/summary/monthly", params={"user_id": ana, "months": 0}).status_code == 422
    assert client.get("/summary/monthly", params={"user_id": ana, "months": 25}).status_code == 422
