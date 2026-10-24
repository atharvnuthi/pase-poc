"""Rede de regressão do FinTrack (SPEC-02 §1).

Estes 9 testes são o que impede o Executor do PASE de entregar uma mudança que
quebra o app: eles rodam dentro do container do Executor, antes de qualquer
artefato chegar ao humano (SPEC-00 §5). Congelados ao fim da F1 - mudar um
destes testes é mudar o contrato, e exige aviso explícito.
"""

from datetime import date, timedelta
from decimal import Decimal

HOJE = date.today().isoformat()
AMANHA = (date.today() + timedelta(days=1)).isoformat()


def _campos_com_erro(response) -> set[str]:
    """Nomes de campo citados num 422, no formato nativo do FastAPI."""
    return {item["loc"][-1] for item in response.json()["detail"]}


# 1
def test_criar_transacao_valida_retorna_201(client, ana, categoria_alimentacao):
    response = client.post(
        "/transactions",
        json={
            "user_id": ana,
            "category_id": categoria_alimentacao,
            "type": "expense",
            "amount": "45.90",
            "date": HOJE,
            "description": "Padaria",
        },
    )

    assert response.status_code == 201
    corpo = response.json()
    assert corpo["id"] > 0
    assert Decimal(str(corpo["amount"])) == Decimal("45.90")
    assert corpo["category"] == "Alimentação"


# 2
def test_amount_nao_positivo_retorna_422(client, ana, categoria_alimentacao):
    for valor in ("0", "-10.00"):
        response = client.post(
            "/transactions",
            json={
                "user_id": ana,
                "category_id": categoria_alimentacao,
                "type": "expense",
                "amount": valor,
                "date": HOJE,
                "description": "inválida",
            },
        )

        assert response.status_code == 422, valor
        assert "amount" in _campos_com_erro(response)


# 3
def test_data_futura_retorna_422(client, ana, categoria_alimentacao):
    response = client.post(
        "/transactions",
        json={
            "user_id": ana,
            "category_id": categoria_alimentacao,
            "type": "expense",
            "amount": "10.00",
            "date": AMANHA,
            "description": "viagem no tempo",
        },
    )

    assert response.status_code == 422
    assert "date" in _campos_com_erro(response)


# 4
def test_categoria_inexistente_retorna_422(client, ana):
    response = client.post(
        "/transactions",
        json={
            "user_id": ana,
            "category_id": 9999,
            "type": "expense",
            "amount": "10.00",
            "date": HOJE,
            "description": "categoria fantasma",
        },
    )

    assert response.status_code == 422
    assert "category_id" in _campos_com_erro(response)


# 5
def test_listagem_filtra_por_usuario(client, ana, clara, categoria_alimentacao, nova_transacao):
    nova_transacao(ana, categoria_alimentacao, "10.00", "da Ana")
    nova_transacao(ana, categoria_alimentacao, "20.00", "também da Ana")
    nova_transacao(clara, categoria_alimentacao, "30.00", "da Clara")

    da_ana = client.get("/transactions", params={"user_id": ana}).json()
    da_clara = client.get("/transactions", params={"user_id": clara}).json()

    assert len(da_ana) == 2
    assert len(da_clara) == 1
    assert {t["description"] for t in da_ana} == {"da Ana", "também da Ana"}
    assert all(t["user_id"] == ana for t in da_ana)


# 6
def test_update_altera_valor(client, ana, categoria_alimentacao, nova_transacao):
    criada = nova_transacao(ana, categoria_alimentacao, "10.00", "antes")

    response = client.put(
        f"/transactions/{criada['id']}",
        json={
            "user_id": ana,
            "category_id": categoria_alimentacao,
            "type": "expense",
            "amount": "99.99",
            "date": HOJE,
            "description": "depois",
        },
    )

    assert response.status_code == 200
    assert Decimal(str(response.json()["amount"])) == Decimal("99.99")

    relida = client.get("/transactions", params={"user_id": ana}).json()[0]
    assert Decimal(str(relida["amount"])) == Decimal("99.99")
    assert relida["description"] == "depois"


# 7
def test_delete_remove(client, ana, categoria_alimentacao, nova_transacao):
    criada = nova_transacao(ana, categoria_alimentacao, "10.00", "some daqui")

    response = client.delete(f"/transactions/{criada['id']}")

    assert response.status_code == 204
    assert client.get("/transactions", params={"user_id": ana}).json() == []


# 8
def test_summary_calcula_balance_e_agrupamento(
    client, ana, clara, categoria_alimentacao, categoria_transporte, categoria_salario, nova_transacao
):
    nova_transacao(ana, categoria_salario, "5000.00", "Salário", tipo="income")
    nova_transacao(ana, categoria_alimentacao, "150.00", "Mercado")
    nova_transacao(ana, categoria_alimentacao, "50.00", "Padaria")
    nova_transacao(ana, categoria_transporte, "300.00", "Combustível")
    nova_transacao(clara, categoria_alimentacao, "999.00", "não entra na conta da Ana")

    corpo = client.get("/summary", params={"user_id": ana}).json()

    # 5000 de receita − 500 de despesa
    assert Decimal(str(corpo["balance"])) == Decimal("4500.00")

    por_categoria = {item["category"]: Decimal(str(item["total"])) for item in corpo["by_category"]}
    assert por_categoria == {"Alimentação": Decimal("200.00"), "Transporte": Decimal("300.00")}
    assert "Salário" not in por_categoria  # by_category agrupa só despesas
    assert corpo["by_category"][0]["category"] == "Transporte"  # ordenado por total desc


# 9
def test_criar_ticket_e_aparecer_na_listagem(client, ana):
    texto = "não encontro onde ver quanto gastei em transporte esse mês"

    criacao = client.post("/tickets", json={"user_id": ana, "text": texto})

    assert criacao.status_code == 201
    assert criacao.json()["text"] == texto

    listagem = client.get("/tickets")
    assert listagem.status_code == 200
    assert texto in [ticket["text"] for ticket in listagem.json()]


# 10

def test_export_transactions_csv(client, ana, categoria_alimentacao, categoria_transporte, nova_transacao):
    # Cria transações para o usuário Ana
    t1 = nova_transacao(ana, categoria_alimentacao, "10.50", "Padaria")
    t2 = nova_transacao(ana, categoria_transporte, "20.75", "Uber")

    response = client.get("/transactions/export", params={"user_id": ana})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f"attachment; filename=transactions_user_{ana}.csv" in response.headers["content-disposition"]

    content = response.content.decode("utf-8")
    lines = content.strip().splitlines()

    # Cabeçalho esperado
    expected_header = [
        "id",
        "user_id",
        "category_id",
        "category",
        "type",
        "amount",
        "date",
        "description",
    ]
    assert lines[0].split(",") == expected_header

    # Verifica que as transações aparecem no CSV
    # Como a ordem é por data desc e id desc, a ordem é t2, t1
    assert str(t2["id"]) in lines[1]
    assert str(t1["id"]) in lines[2]

    # Verifica campos específicos na linha
    for line in lines[1:]:
        fields = line.split(",")
        assert fields[1] == str(ana)  # user_id
        assert fields[3] in ["Alimentação", "Transporte"]  # category name
        assert fields[5].replace('"', '') in ["10.50", "20.75"]  # amount


def test_update_altera_data(client, ana, categoria_alimentacao, nova_transacao):
    criada = nova_transacao(ana, categoria_alimentacao, "10.00", "antes")

    nova_data = (date.today() - timedelta(days=1)).isoformat()

    response = client.put(
        f"/transactions/{criada['id']}",
        json={
            "user_id": ana,
            "category_id": categoria_alimentacao,
            "type": "expense",
            "amount": "10.00",
            "date": nova_data,
            "description": "data corrigida",
        },
    )

    assert response.status_code == 200
    assert response.json()["date"] == nova_data

    relida = client.get("/transactions", params={"user_id": ana}).json()[0]
    assert relida["date"] == nova_data


def test_update_data_futura_retorna_422(client, ana, categoria_alimentacao, nova_transacao):
    criada = nova_transacao(ana, categoria_alimentacao, "10.00", "antes")

    data_futura = (date.today() + timedelta(days=1)).isoformat()

    response = client.put(
        f"/transactions/{criada['id']}",
        json={
            "user_id": ana,
            "category_id": categoria_alimentacao,
            "type": "expense",
            "amount": "10.00",
            "date": data_futura,
            "description": "data futura",
        },
    )

    assert response.status_code == 422
    assert "date" in _campos_com_erro(response)
