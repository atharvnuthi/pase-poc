"""Metas de economia (RF-11)."""

from datetime import date, timedelta
from decimal import Decimal

from app.goals import months_left, to_read
from app.models import Goal

HOJE = date.today()


def _campos_com_erro(response) -> set[str]:
    return {item["loc"][-1] for item in response.json()["detail"]}


def _cria(client, user_id, nome="Viagem", alvo="1000.00", prazo=None):
    corpo = {"user_id": user_id, "name": nome, "target_amount": alvo}
    if prazo:
        corpo["deadline"] = prazo.isoformat()
    return client.post("/goals", json=corpo)


def test_cria_meta_sem_progresso_e_sem_prazo(client, ana):
    r = _cria(client, ana)

    assert r.status_code == 201
    g = r.json()
    assert Decimal(str(g["saved_amount"])) == Decimal("0.00")
    assert g["percent"] == 0 and g["reached"] is False
    assert g["monthly_needed"] is None  # sem prazo, sem valor mensal


def test_guardar_dinheiro_avanca_o_progresso(client, ana):
    goal_id = _cria(client, ana, alvo="1000.00").json()["id"]

    r = client.post(f"/goals/{goal_id}/contribute", json={"amount": "250.00"})

    g = r.json()
    assert Decimal(str(g["saved_amount"])) == Decimal("250.00")
    assert Decimal(str(g["remaining"])) == Decimal("750.00")
    assert g["percent"] == 25


def test_aportes_somam_em_centavos_exatos(client, ana):
    goal_id = _cria(client, ana, alvo="100.00").json()["id"]
    for _ in range(3):
        r = client.post(f"/goals/{goal_id}/contribute", json={"amount": "0.10"})

    assert Decimal(str(r.json()["saved_amount"])) == Decimal("0.30")  # 0.1 + 0.1 + 0.1 != 0.3 em float


def test_meta_atingida_e_passar_do_alvo_e_permitido(client, ana):
    goal_id = _cria(client, ana, alvo="100.00").json()["id"]

    g = client.post(f"/goals/{goal_id}/contribute", json={"amount": "130.00"}).json()

    assert g["reached"] is True and g["percent"] == 100
    assert Decimal(str(g["remaining"])) == Decimal("0.00")
    assert g["monthly_needed"] is None


def test_valor_mensal_necessario_arredonda_para_cima(client, ana):
    prazo = HOJE + timedelta(days=95)
    goal = Goal(
        user_id=ana, name="x", target_amount=Decimal("1000.00"),
        saved_amount=Decimal("0.00"), deadline=prazo, id=1,
    )

    lido = to_read(goal, today=HOJE)

    meses = months_left(prazo, HOJE)
    assert lido.monthly_needed * meses >= Decimal("1000.00")  # nunca termina abaixo do alvo
    assert lido.monthly_needed * (meses - 1) < Decimal("1000.00") or meses == 1


def test_prazo_dentro_do_mes_conta_como_um_mes(client, ana):
    assert months_left(HOJE + timedelta(days=3), HOJE) >= 1
    assert months_left(HOJE, HOJE) == 1


def test_meta_com_prazo_devolve_o_quanto_guardar_por_mes(client, ana):
    prazo = HOJE.replace(year=HOJE.year + 1)
    g = _cria(client, ana, alvo="1200.00", prazo=prazo).json()

    assert Decimal(str(g["monthly_needed"])) == Decimal("100.00")


def test_valida_o_formulario_por_campo(client, ana):
    r = client.post("/goals", json={"user_id": ana, "name": "", "target_amount": "0"})
    assert r.status_code == 422
    assert {"name", "target_amount"} <= _campos_com_erro(r)

    passado = (HOJE - timedelta(days=1)).isoformat()
    r = client.post(
        "/goals", json={"user_id": ana, "name": "x", "target_amount": "10", "deadline": passado}
    )
    assert r.status_code == 422 and "deadline" in _campos_com_erro(r)

    assert client.post(
        "/goals", json={"user_id": 9999, "name": "x", "target_amount": "10"}
    ).status_code == 422


def test_aporte_precisa_ser_positivo(client, ana):
    goal_id = _cria(client, ana).json()["id"]

    r = client.post(f"/goals/{goal_id}/contribute", json={"amount": "-5.00"})

    assert r.status_code == 422 and "amount" in _campos_com_erro(r)


def test_cada_pessoa_ve_so_as_proprias_metas(client, ana, clara):
    _cria(client, ana, nome="Da Ana")
    _cria(client, clara, nome="Da Clara")

    nomes = [g["name"] for g in client.get("/goals", params={"user_id": ana}).json()]

    assert nomes == ["Da Ana"]


def test_remove_a_meta_e_meta_inexistente_da_404(client, ana):
    goal_id = _cria(client, ana).json()["id"]

    assert client.delete(f"/goals/{goal_id}").status_code == 204

    assert client.get("/goals", params={"user_id": ana}).json() == []
    assert client.delete(f"/goals/{goal_id}").status_code == 404
    assert client.post(f"/goals/{goal_id}/contribute", json={"amount": "1"}).status_code == 404
