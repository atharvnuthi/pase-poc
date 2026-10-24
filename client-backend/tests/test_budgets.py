"""Orçamentos: limite mensal por categoria e o quanto já foi gasto (RF-10)."""

from datetime import date, timedelta
from decimal import Decimal

HOJE = date.today()


def _mes(dia: date) -> str:
    return f"{dia.year:04d}-{dia.month:02d}"


def _define(client, user_id, category_id, limite="500.00"):
    return client.put(
        "/budgets", json={"user_id": user_id, "category_id": category_id, "monthly_limit": limite}
    )


def _lanca(client, user_id, category_id, valor, dia=HOJE, tipo="expense"):
    r = client.post(
        "/transactions",
        json={
            "user_id": user_id, "category_id": category_id, "type": tipo, "amount": valor,
            "date": dia.isoformat(), "description": "x",
        },
    )
    assert r.status_code == 201, r.text


def _campos_com_erro(response) -> set[str]:
    return {item["loc"][-1] for item in response.json()["detail"]}


def test_define_e_lista_o_orcamento_com_o_nome_da_categoria(client, ana, categoria_alimentacao):
    r = _define(client, ana, categoria_alimentacao, "800.50")

    assert r.status_code == 200
    assert r.json()["category"] == "Alimentação"
    assert Decimal(str(r.json()["monthly_limit"])) == Decimal("800.50")
    lista = client.get("/budgets", params={"user_id": ana}).json()
    assert [b["category"] for b in lista] == ["Alimentação"]


def test_definir_de_novo_troca_o_limite_em_vez_de_duplicar(client, ana, categoria_alimentacao):
    _define(client, ana, categoria_alimentacao, "500.00")
    _define(client, ana, categoria_alimentacao, "650.00")

    lista = client.get("/budgets", params={"user_id": ana}).json()

    assert len(lista) == 1 and Decimal(str(lista[0]["monthly_limit"])) == Decimal("650.00")


def test_orcamentos_de_cada_pessoa_sao_separados(client, ana, clara, categoria_alimentacao):
    _define(client, ana, categoria_alimentacao, "500.00")

    assert client.get("/budgets", params={"user_id": clara}).json() == []


def test_limite_precisa_ser_positivo(client, ana, categoria_alimentacao):
    for ruim in ("0", "-10.00"):
        r = _define(client, ana, categoria_alimentacao, ruim)
        assert r.status_code == 422 and "monthly_limit" in _campos_com_erro(r)


def test_categoria_e_usuario_precisam_existir(client, ana, categoria_alimentacao):
    r = _define(client, ana, 9999)
    assert r.status_code == 422 and "category_id" in _campos_com_erro(r)

    r = _define(client, 9999, categoria_alimentacao)
    assert r.status_code == 422 and "user_id" in _campos_com_erro(r)


def test_nao_ha_orcamento_para_categoria_de_receita(client, ana, categoria_salario):
    r = _define(client, ana, categoria_salario)

    assert r.status_code == 422 and "category_id" in _campos_com_erro(r)


def test_remove_o_orcamento(client, ana, categoria_alimentacao):
    budget_id = _define(client, ana, categoria_alimentacao).json()["id"]

    assert client.delete(f"/budgets/{budget_id}").status_code == 204

    assert client.get("/budgets", params={"user_id": ana}).json() == []
    assert client.delete(f"/budgets/{budget_id}").status_code == 404


# --------------------------------------------------------------------------- #
# Quanto do limite já foi usado
# --------------------------------------------------------------------------- #


def test_status_soma_so_as_despesas_da_categoria_no_mes(
    client, ana, categoria_alimentacao, categoria_transporte
):
    _define(client, ana, categoria_alimentacao, "500.00")
    _lanca(client, ana, categoria_alimentacao, "100.10")
    _lanca(client, ana, categoria_alimentacao, "50.20")
    _lanca(client, ana, categoria_transporte, "999.00")  # outra categoria: não conta

    [s] = client.get("/budgets/status", params={"user_id": ana}).json()

    assert Decimal(str(s["spent"])) == Decimal("150.30")  # centavos exatos, sem float
    assert Decimal(str(s["remaining"])) == Decimal("349.70")
    assert s["percent"] == 30 and s["state"] == "ok"


def test_receita_na_mesma_categoria_nao_abate_o_gasto(client, ana, categoria_alimentacao):
    _define(client, ana, categoria_alimentacao, "100.00")
    _lanca(client, ana, categoria_alimentacao, "40.00")
    _lanca(client, ana, categoria_alimentacao, "500.00", tipo="income")

    [s] = client.get("/budgets/status", params={"user_id": ana}).json()

    assert Decimal(str(s["spent"])) == Decimal("40.00")


def test_estados_atencao_e_estourado(client, ana, categoria_alimentacao, categoria_transporte):
    _define(client, ana, categoria_alimentacao, "100.00")
    _define(client, ana, categoria_transporte, "100.00")
    _lanca(client, ana, categoria_alimentacao, "80.00")   # 80%: atenção
    _lanca(client, ana, categoria_transporte, "100.01")   # passou de 100%: estourado

    estados = {
        s["category"]: s for s in client.get("/budgets/status", params={"user_id": ana}).json()
    }

    assert estados["Alimentação"]["state"] == "atencao"
    assert estados["Transporte"]["state"] == "estourado"
    assert Decimal(str(estados["Transporte"]["remaining"])) == Decimal("-0.01")


def test_gastar_exatamente_o_limite_ainda_e_atencao_nao_estouro(
    client, ana, categoria_alimentacao
):
    _define(client, ana, categoria_alimentacao, "100.00")
    _lanca(client, ana, categoria_alimentacao, "100.00")

    [s] = client.get("/budgets/status", params={"user_id": ana}).json()

    assert s["percent"] == 100 and s["state"] == "atencao"


def test_status_ordena_pelo_que_mais_pede_atencao(
    client, ana, categoria_alimentacao, categoria_transporte
):
    _define(client, ana, categoria_alimentacao, "1000.00")
    _define(client, ana, categoria_transporte, "100.00")
    _lanca(client, ana, categoria_alimentacao, "100.00")
    _lanca(client, ana, categoria_transporte, "90.00")

    ordem = [s["category"] for s in client.get("/budgets/status", params={"user_id": ana}).json()]

    assert ordem == ["Transporte", "Alimentação"]


def test_status_de_outro_mes_so_conta_aquele_mes(client, ana, categoria_alimentacao):
    _define(client, ana, categoria_alimentacao, "100.00")
    antigo = (HOJE.replace(day=1) - timedelta(days=1)).replace(day=15)  # mês passado
    _lanca(client, ana, categoria_alimentacao, "70.00", dia=antigo)
    _lanca(client, ana, categoria_alimentacao, "10.00")

    este = client.get("/budgets/status", params={"user_id": ana}).json()[0]
    passado = client.get(
        "/budgets/status", params={"user_id": ana, "month": _mes(antigo)}
    ).json()[0]

    assert Decimal(str(este["spent"])) == Decimal("10.00")
    assert Decimal(str(passado["spent"])) == Decimal("70.00")


def test_ultimo_dia_do_mes_entra_na_conta(client, ana, categoria_alimentacao):
    _define(client, ana, categoria_alimentacao, "100.00")
    ultimo_dia = HOJE.replace(day=1) - timedelta(days=1)  # último dia do mês passado
    _lanca(client, ana, categoria_alimentacao, "33.00", dia=ultimo_dia)

    [s] = client.get(
        "/budgets/status", params={"user_id": ana, "month": _mes(ultimo_dia)}
    ).json()

    assert Decimal(str(s["spent"])) == Decimal("33.00")


def test_mes_em_formato_errado_e_422(client, ana):
    r = client.get("/budgets/status", params={"user_id": ana, "month": "setembro"})

    assert r.status_code == 422 and "month" in _campos_com_erro(r)


def test_sem_orcamentos_o_status_e_lista_vazia(client, ana):
    assert client.get("/budgets/status", params={"user_id": ana}).json() == []
