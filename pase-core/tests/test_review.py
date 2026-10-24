"""Revisão independente (P12): o código confere a evidência que o revisor cita.

O prompt pede evidência; quem decide se ela vale é `review.conferir`. Por isso os
testes daqui não chamam modelo nenhum - a garantia não pode depender dele.
"""

import json

import pytest

from app.execution import review

CRITERIOS = [
    {"id": "C1", "criterio": "O fundo fica escuro ao ativar o tema", "como_verificar": "..."},
    {"id": "C2", "criterio": "A escolha sobrevive a recarregar", "como_verificar": "..."},
]

CSS = ".dark {\n  --surface: #0f1115;\n  --ink: #e6e6e6;\n}\n"
TESTE = (
    'it("mantém o tema depois de recarregar", () => {\n'
    '  expect(screen.getByRole("button", { name: "Usar tema claro" })).toBeVisible();\n'
    "});\n"
)
DIFF = (
    "--- a/client-frontend/app/globals.css\n"
    "+++ b/client-frontend/app/globals.css\n"
    "+.dark {\n"
    "+  --surface: #0f1115;\n"
    "-// Almoço e jantar\n"
    "+// Almé e jantar\n"
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "client-frontend" / "app").mkdir(parents=True)
    (tmp_path / "client-frontend" / "tests").mkdir(parents=True)
    (tmp_path / "client-frontend" / "app" / "globals.css").write_text(CSS, encoding="utf-8")
    (tmp_path / "client-frontend" / "tests" / "tema.test.tsx").write_text(TESTE, encoding="utf-8")
    return tmp_path


def _evidencia(trecho: str, arquivo: str = "client-frontend/app/globals.css") -> dict:
    return {"arquivo": arquivo, "trecho": trecho}


def _teste(trecho: str = 'name: "Usar tema claro"') -> dict:
    return {"arquivo": "client-frontend/tests/tema.test.tsx", "trecho": trecho}


def _atendido(cid: str, **extra) -> dict:
    return {
        "id": cid,
        "atendido": True,
        "explicacao": "ok",
        "evidencia": _evidencia("--surface: #0f1115;"),
        "teste": _teste(),
        **extra,
    }


def test_evidencia_e_teste_conferidos_aprovam(workspace):
    bruto = {"criterios": [_atendido("C1"), _atendido("C2")], "colaterais": [], "resumo": "r"}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert parecer.aprovado
    assert all(c.anulado_por is None for c in parecer.criterios)


def test_trecho_inventado_anula_o_criterio(workspace):
    """O caso da tarefa #4: o revisor "lembra" de uma cor que ninguém escreveu."""
    inventado = _atendido("C1", evidencia=_evidencia("--surface: #000000;"))
    bruto = {"criterios": [inventado, _atendido("C2")], "colaterais": []}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert not parecer.aprovado
    c1 = parecer.criterios[0]
    assert not c1.atendido
    assert "não está em" in c1.anulado_por


def test_reindentar_a_citacao_nao_a_invalida(workspace):
    bruto = {
        "criterios": [
            _atendido("C1", evidencia=_evidencia(".dark {   --surface: #0f1115;")),
            _atendido("C2"),
        ],
        "colaterais": [],
    }

    assert review.conferir(bruto, CRITERIOS, workspace, DIFF).aprovado


def test_teste_citado_que_nao_existe_anula(workspace):
    bruto = {
        "criterios": [_atendido("C1", teste=_teste("expect(body).toHaveClass('dark')")),
                      _atendido("C2")],
        "colaterais": [],
    }

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert not parecer.aprovado
    assert "teste citado não confere" in parecer.criterios[0].anulado_por


def test_sem_teste_e_sem_verificacao_manual_nao_vale(workspace):
    bruto = {"criterios": [_atendido("C1", teste=None), _atendido("C2")], "colaterais": []}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert not parecer.criterios[0].atendido
    assert "sem teste" in parecer.criterios[0].anulado_por


def test_verificacao_manual_substitui_teste_quando_justificada(workspace):
    manual = _atendido(
        "C1", teste=None, verificacao_manual="Abrir /dashboard, clicar em Usar tema escuro"
    )
    bruto = {"criterios": [manual, _atendido("C2")], "colaterais": []}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert parecer.aprovado
    assert parecer.criterios[0].verificacao_manual.startswith("Abrir /dashboard")


def test_criterio_que_o_revisor_pulou_conta_como_nao_atendido(workspace):
    bruto = {"criterios": [_atendido("C1")], "colaterais": []}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert not parecer.aprovado
    assert parecer.criterios[1].anulado_por == "o revisor não avaliou este critério"


def test_criterio_inventado_pelo_revisor_e_ignorado(workspace):
    """Só os critérios do plano contam - o revisor não acrescenta régua nova."""
    bruto = {
        "criterios": [_atendido("C1"), _atendido("C2"), {"id": "C9", "atendido": False}],
        "colaterais": [],
    }

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert parecer.aprovado
    assert [c.id for c in parecer.criterios] == ["C1", "C2"]


@pytest.mark.parametrize(
    "arquivo",
    ["../segredo.txt", "client-frontend/../../etc/passwd", "client-frontend/app/nao-existe.css"],
)
def test_caminho_fora_do_clone_ou_inexistente_nao_e_evidencia(workspace, arquivo):
    citacao = _evidencia("--surface: #0f1115;", arquivo=arquivo)
    ok, _ = review._trecho_existe(workspace, citacao)
    assert not ok


def test_trecho_curto_demais_nao_prova_nada(workspace):
    ok, porque = review._trecho_existe(workspace, _evidencia("dark"))
    assert not ok
    assert "curto" in porque


def test_colateral_confirmado_no_diff_reprova(workspace):
    bruto = {
        "criterios": [_atendido("C1"), _atendido("C2")],
        "colaterais": [
            {
                "arquivo": "client-frontend/app/globals.css",
                "trecho": "+// Almé e jantar",
                "motivo": "comentário alterado",
            }
        ],
    }

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert not parecer.aprovado
    assert len(parecer.colaterais) == 1


def test_colateral_que_nao_esta_no_diff_e_descartado(workspace):
    """Um colateral imaginado não pode reprovar uma entrega boa."""
    bruto = {
        "criterios": [_atendido("C1"), _atendido("C2")],
        "colaterais": [{"arquivo": "x", "trecho": "classe text-sm removida", "motivo": "?"}],
    }

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert parecer.aprovado
    assert parecer.colaterais == []


def test_feedback_lista_so_o_que_falta(workspace):
    bruto = {
        "criterios": [_atendido("C1"), {"id": "C2", "atendido": False, "explicacao": "some"}],
        "colaterais": [],
    }

    texto = review.conferir(bruto, CRITERIOS, workspace, DIFF).feedback()

    assert "[C2]" in texto and "some" in texto
    assert "[C1]" not in texto


def test_sem_criterios_a_revisao_se_cala(workspace, mock_providers):
    parecer = review.revisar(
        task_id=1, titulo="t", descricao="d", criterios=[], workspace=workspace,
        tocados=[], diff="",
    )

    assert parecer is None
    assert mock_providers.calls == []


def test_revisar_usa_o_modelo_de_revisao_e_devolve_o_consumo(
    workspace, mock_providers, monkeypatch
):
    monkeypatch.setattr(review.settings, "llm_model_review", "modelo-revisor")
    mock_providers.responses = [
        json.dumps({"criterios": [_atendido("C1"), _atendido("C2")], "colaterais": [],
                    "resumo": "ok"})
    ]

    parecer = review.revisar(
        task_id=1,
        titulo="Modo escuro",
        descricao="d",
        criterios=CRITERIOS,
        workspace=workspace,
        tocados=["client-frontend/app/globals.css"],
        diff=DIFF,
        feedback_humano="o botão não mudava nada",
    )

    assert parecer.aprovado
    assert mock_providers.models == ["modelo-revisor"]
    assert parecer.usage["tokens_in"] > 0
    prompt = mock_providers.calls[0][0]["content"]
    assert "o botão não mudava nada" in prompt
    assert "--surface: #0f1115;" in prompt  # o revisor recebe o arquivo inteiro


def test_salvar_nao_grava_o_consumo(workspace, tmp_path):
    parecer = review.Parecer(aprovado=True, usage={"trace_id": "x"})

    caminho = review.salvar(parecer, tmp_path / "out" / "review.json")

    dados = json.loads(open(caminho, encoding="utf-8").read())
    assert dados["aprovado"] is True
    assert "usage" not in dados


def test_colateral_cosmetico_vira_aviso_e_nao_reprova(workspace):
    """Aspas e docstring custaram quatro rodadas numa tarefa que cumpria os critérios."""
    bruto = {
        "criterios": [_atendido("C1"), _atendido("C2")],
        "colaterais": [
            {
                "arquivo": "client-frontend/app/globals.css",
                "trecho": "+// Almé e jantar",
                "motivo": "comentário alterado",
                "gravidade": "aviso",
            }
        ],
    }

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert parecer.aprovado
    assert parecer.colaterais == []
    assert len(parecer.avisos) == 1


def test_trecho_de_producao_citado_como_teste_anula(workspace):
    """Citar o próprio CSS como "teste" prova que o código existe, não que é exercitado."""
    falso_teste = _atendido(
        "C1", teste={"arquivo": "client-frontend/app/globals.css", "trecho": "--surface: #0f1115;"}
    )
    bruto = {"criterios": [falso_teste, _atendido("C2")], "colaterais": []}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert not parecer.aprovado
    assert "não é arquivo de teste" in parecer.criterios[0].anulado_por


def test_parecer_marca_quando_o_revisor_e_o_mesmo_modelo(workspace, monkeypatch):
    monkeypatch.setattr(review.settings, "llm_model_code", "o-mesmo")
    monkeypatch.setattr(review.settings, "llm_model_review", "o-mesmo")
    bruto = {"criterios": [_atendido("C1"), _atendido("C2")], "colaterais": []}

    parecer = review.conferir(bruto, CRITERIOS, workspace, DIFF)

    assert parecer.mesmo_modelo is True
    assert parecer.como_dict()["modelo"] == parecer.como_dict()["modelo_do_codigo"] == "o-mesmo"


def test_revisor_igual_ao_autor_gera_aviso_no_log(workspace, mock_providers, monkeypatch):
    monkeypatch.setattr(review.settings, "llm_model_code", "o-mesmo")
    monkeypatch.setattr(review.settings, "llm_model_review", "")
    avisos = []
    monkeypatch.setattr(
        review.logger, "warning", lambda msg, *args: avisos.append(msg % args)
    )
    mock_providers.responses = [
        json.dumps({"criterios": [_atendido("C1"), _atendido("C2")], "colaterais": [],
                    "resumo": "ok"})
    ]

    parecer = review.revisar(
        task_id=1, titulo="t", descricao="d", criterios=CRITERIOS, workspace=workspace,
        tocados=[], diff=DIFF,
    )

    assert parecer.mesmo_modelo is True
    assert any("mesmo modelo" in a and "o-mesmo" in a for a in avisos)


def test_revisar_guarda_a_troca_crua_fora_do_parecer_salvo(workspace, mock_providers, tmp_path):
    resposta = {"criterios": [_atendido("C1"), _atendido("C2")], "colaterais": [], "resumo": "r"}
    mock_providers.responses = [json.dumps(resposta)]

    parecer = review.revisar(
        task_id=1, titulo="Modo escuro", descricao="d", criterios=CRITERIOS,
        workspace=workspace, tocados=[], diff=DIFF,
    )

    assert "Modo escuro" in parecer.troca["prompt"]
    assert parecer.troca["resposta"] == resposta
    salvo = json.loads(open(review.salvar(parecer, tmp_path / "r.json"), encoding="utf-8").read())
    assert "troca" not in salvo


def test_colateral_que_muda_comportamento_continua_reprovando(workspace):
    bruto = {
        "criterios": [_atendido("C1"), _atendido("C2")],
        "colaterais": [
            {
                "arquivo": "client-frontend/app/globals.css",
                "trecho": "+// Almé e jantar",
                "motivo": "muda o texto exibido",
                "gravidade": "bloqueia",
            }
        ],
    }

    assert not review.conferir(bruto, CRITERIOS, workspace, DIFF).aprovado
