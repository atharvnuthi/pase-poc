"""Critérios de aceite do P4: a régua da revisão nasce no planejamento."""

import json
from pathlib import Path

from sqlalchemy import text

from app.execution import planning
from app.execution.planning import criterios_validos
from app.task_layer.models import Task
from tests.conftest import requires_db


def test_mapeamento_de_impacto_traz_a_acao_de_cada_arquivo(tmp_path):
    (tmp_path / "client-frontend" / "app").mkdir(parents=True)
    (tmp_path / "client-frontend" / "app" / "globals.css").write_text("", encoding="utf-8")
    content = {
        "arquivos": [
            {"caminho": "./client-frontend/app/globals.css", "acao": "modificar"},
            {"caminho": "client-frontend/lib/theme.ts", "acao": "criar"},
            {"caminho": "client-frontend/components/ThemeController.tsx", "acao": "excluir"},
            {"caminho": "client-frontend/app/globals.css", "acao": "criar"},  # repetido
        ]
    }

    arquivos, acoes = planning.mapeamento_de_impacto(content, tmp_path)

    assert arquivos == [
        "client-frontend/app/globals.css",
        "client-frontend/lib/theme.ts",
        "client-frontend/components/ThemeController.tsx",
    ]
    assert acoes["client-frontend/lib/theme.ts"] == "criar"
    assert acoes["client-frontend/components/ThemeController.tsx"] == "excluir"
    assert acoes["client-frontend/app/globals.css"] == "modificar"


def test_acao_ausente_ou_invalida_e_deduzida_do_repositorio(tmp_path):
    (tmp_path / "client-backend" / "app").mkdir(parents=True)
    (tmp_path / "client-backend" / "app" / "routes.py").write_text("", encoding="utf-8")

    _, acoes = planning.mapeamento_de_impacto(
        {"arquivos": [{"caminho": "client-backend/app/routes.py", "acao": "mexer"},
                      {"caminho": "client-backend/app/novo.py"}]},
        tmp_path,
    )

    assert acoes == {
        "client-backend/app/routes.py": "modificar",
        "client-backend/app/novo.py": "criar",
    }


def test_formato_antigo_so_com_affected_files_continua_aceito(tmp_path):
    arquivos, acoes = planning.mapeamento_de_impacto(
        {"affected_files": ["client-backend/app/x.py"]}, tmp_path
    )

    assert arquivos == ["client-backend/app/x.py"]
    assert acoes == {"client-backend/app/x.py": "criar"}


def test_risco_tecnico_normalizado():
    assert planning.risco_tecnico(
        {"risco_tecnico": {"nivel": "Médio", "justificativa": "mexe no layout raiz"}}
    ) == ("medio", "mexe no layout raiz")
    assert planning.risco_tecnico({"risco_tecnico": {"nivel": "enorme"}}) == (None, None)
    assert planning.risco_tecnico({}) == (None, None)


@requires_db
def test_planejar_grava_impacto_tempo_risco_e_transcript(
    session, mock_providers, monkeypatch, tmp_path
):
    monkeypatch.setattr(planning.settings, "artifacts_path", str(tmp_path))
    session.execute(text("DELETE FROM planning_documents"))
    task = Task(
        title="Modo escuro",
        description="Tema escuro por persona.",
        module="geral",
        status="em_planejamento",
        impact=3,
        complexity=2,
    )
    session.add(task)
    session.flush()
    mock_providers.responses = [
        json.dumps(
            {
                "acceptance_criteria": [
                    {"id": "C1", "criterio": "O fundo fica escuro", "como_verificar": "teste"}
                ],
                "arquivos": [
                    {"caminho": "client-frontend/app/globals.css", "acao": "modificar"},
                    {"caminho": "client-frontend/lib/theme.ts", "acao": "criar"},
                ],
                "roadmap": "1) tokens escuros",
                "tokens_estimated": 90000,
                "minutos_estimados": 12,
                "risco_tecnico": {"nivel": "medio", "justificativa": "toca o layout raiz"},
            }
        )
    ]

    plano = planning.planejar(session, task)

    assert plano.affected_files == [
        "client-frontend/app/globals.css",
        "client-frontend/lib/theme.ts",
    ]
    assert plano.file_actions["client-frontend/lib/theme.ts"] == "criar"
    assert plano.minutes_estimated == 12
    assert plano.technical_risk == "medio"
    assert plano.technical_risk_reason == "toca o layout raiz"

    linhas = [
        json.loads(linha)
        for linha in Path(plano.transcript_path).read_text(encoding="utf-8").splitlines()
    ]
    assert "Planejamento Técnico" in linhas[0]["content"]  # o prompt do P4, cru
    assert linhas[1]["role"] == "assistant" and linhas[1]["trace_id"]
    session.rollback()


def test_ids_repetidos_viram_ids_distintos():
    """A revisão cita critério por id: dois iguais fariam um veredito valer por dois."""
    limpos = criterios_validos(
        [
            {"id": "C1", "criterio": "a", "como_verificar": "x"},
            {"id": "C1", "criterio": "b"},
        ]
    )

    assert [c["id"] for c in limpos] == ["C1", "C1'"]
    assert limpos[1]["como_verificar"] == ""


def test_criterio_em_branco_e_descartado_e_id_ausente_e_gerado():
    limpos = criterios_validos(
        [{"id": "C1", "criterio": "   "}, {"criterio": "O saldo aparece no topo"}]
    )

    assert limpos == [{"id": "C2", "criterio": "O saldo aparece no topo", "como_verificar": ""}]


def test_sem_criterios_devolve_lista_vazia():
    assert criterios_validos(None) == []
    assert criterios_validos([]) == []


def test_barra_n_literal_do_modelo_vira_quebra_de_linha():
    from app.execution.planning import _com_quebras_de_linha

    assert _com_quebras_de_linha("1) a\n2) b") == "1) a\n2) b"


def test_texto_que_ja_tem_quebra_nao_e_mexido():
    from app.execution.planning import _com_quebras_de_linha

    original = "1) a\n2) usa `\n` no código"
    assert _com_quebras_de_linha(original) == original
