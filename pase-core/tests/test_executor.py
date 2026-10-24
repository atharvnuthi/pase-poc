"""O Executor, sobre um repositório de mentira (SPEC-04 §6).

O alvo real é o client-backend; aqui montamos um alvo mínimo com o mesmo formato
(pacote `client-backend/` com código e testes) para exercitar o ciclo completo
sem depender do projeto de verdade nem gastar minutos de pytest.
"""

import json

import pytest
from git import Repo
from sqlalchemy import text

from app.common import git_service
from app.execution import context, executor, review
from app.orchestration.models import PlanningDocument
from app.task_layer.models import Task
from tests.conftest import requires_db

#: A revisão de verdade, guardada antes de `task_com_plano` trocá-la por um dublê.
REVISAR_REAL = review.revisar

#: Todo plano executável tem critério: sem ele a entrega é recusada antes de começar.
CRITERIO_GERAL = {
    "id": "C1",
    "criterio": "A soma continua correta",
    "como_verificar": "teste unitário",
}

CODIGO_BOM = 'def somar(a, b):\n    return a + b\n'
TESTE = 'from app.calc import somar\n\n\ndef test_somar():\n    assert somar(1, 2) == 3\n'

CASO_SOMAR_TRES = (
    'def test_somar_tres():\n'
    '    from app.calc import somar_tres\n\n'
    '    assert somar_tres(1, 2, 3) == 6\n'
)
CASO_SOMAR_NEGATIVOS = 'def test_somar_negativos():\n    assert somar(-1, -2) == -3\n'

#: App mínimo com a rota de saúde, para o smoke do gate ter o que subir.
APP_MINIMO = (
    'from fastapi import FastAPI\n\n'
    'app = FastAPI()\n\n\n'
    '@app.get("/health")\n'
    'def health():\n'
    '    return {"status": "ok"}\n'
)
CASO_VALOR_EXTRA = (
    'def test_valor_extra():\n'
    '    from app.extra import VALOR\n\n'
    '    assert VALOR == 1\n'
)


def _suite_com(*casos: str) -> str:
    """Arquivo de teste com o caso original **mais** os novos.

    Toda entrega que mexe em código de produção precisa acrescentar teste, e
    nenhuma pode remover os que já existiam. É o que estas fixtures simulam: o
    `TESTE` original continua no arquivo e os casos novos vêm depois - que é
    exatamente a forma de uma entrega conforme.
    """
    return TESTE + '\n\n' + '\n\n'.join(casos)


@pytest.fixture
def alvo(tmp_path, monkeypatch):
    """Repositório com a mesma forma do client-backend."""
    origem = tmp_path / "repo"
    (origem / "client-backend" / "app").mkdir(parents=True)
    (origem / "client-backend" / "tests").mkdir(parents=True)

    (origem / "client-backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (origem / "client-backend" / "app" / "calc.py").write_text(CODIGO_BOM, encoding="utf-8")
    # `main.py` de verdade: é o que faz o gate exercitar o smoke em vez de pulá-lo.
    (origem / "client-backend" / "app" / "main.py").write_text(APP_MINIMO, encoding="utf-8")
    (origem / "client-backend" / "tests" / "test_calc.py").write_text(TESTE, encoding="utf-8")
    (origem / "client-backend" / "pytest.ini").write_text(
        "[pytest]\ntestpaths = tests\npythonpath = .\n", encoding="utf-8"
    )

    repo = Repo.init(origem, initial_branch="main")
    repo.config_writer().set_value("user", "name", "Teste").release()
    repo.config_writer().set_value("user", "email", "teste@local").release()
    repo.git.add("--all")
    repo.index.commit("inicial")

    monkeypatch.setattr(git_service.settings, "repo_path", str(origem))
    monkeypatch.setattr(git_service, "WORKSPACE_ROOT", tmp_path / "workspaces")
    monkeypatch.setattr(executor.settings, "repo_path", str(origem))
    monkeypatch.setattr(executor.settings, "artifacts_path", str(tmp_path / "artifacts"))
    return origem


@pytest.fixture
def task_com_plano(session, alvo, monkeypatch):
    """Tarefa com plano de um critério, e um revisor dublê que aprova.

    Os testes daqui exercitam o ciclo do executor; a revisão de verdade tem os
    seus próprios testes (ver `com_criterios` e `test_review.py`).
    """
    monkeypatch.setattr(
        executor.review,
        "revisar",
        lambda **kwargs: review.Parecer(aprovado=True, modelo="revisor-dublê"),
    )

    def zerar():
        for tabela in ("task_state_history", "execution_runs", "planning_documents", "tasks"):
            session.execute(text(f"DELETE FROM {tabela}"))
        session.commit()

    zerar()
    task = Task(
        title="Somar três números",
        description="Acrescentar uma função que soma três números.",
        module="geral",
        status="em_execucao",
        impact=3,
        complexity=1,
    )
    session.add(task)
    session.flush()
    plano = PlanningDocument(
        task_id=task.id,
        acceptance_criteria=[CRITERIO_GERAL],
        affected_files=["client-backend/app/calc.py"],
        roadmap="Acrescentar somar_tres em app/calc.py.",
        tokens_estimated=50_000,
    )
    session.add(plano)
    session.commit()
    yield task, plano
    zerar()


def _resposta(arquivos: dict[str, str]) -> str:
    return json.dumps({"files": [{"path": p, "content": c} for p, c in arquivos.items()]})


@requires_db
def test_run_de_sucesso_produz_diff_log_e_transcript(session, task_com_plano, mock_providers):
    task, plano = task_com_plano
    mock_providers.responses = [
        _resposta(
            {
                "client-backend/app/calc.py": CODIGO_BOM
                + "\n\ndef somar_tres(a, b, c):\n    return a + b + c\n",
                "client-backend/tests/test_calc.py": _suite_com(CASO_SOMAR_TRES),
            }
        )
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert run.tokens_real > 0
    assert run.deviation_files == []

    from pathlib import Path

    assert "somar_tres" in Path(run.diff_path).read_text(encoding="utf-8")
    assert "ruff check" in Path(run.log_path).read_text(encoding="utf-8")

    linhas = [
        json.loads(linha)
        for linha in Path(run.transcript_path).read_text(encoding="utf-8").splitlines()
    ]
    assert any(linha["role"] == "assistant" and linha.get("trace_id") for linha in linhas)
    assert any(linha.get("evento") == "verificacao" for linha in linhas)


@requires_db
def test_codigo_quebrado_dispara_ciclo_de_correcao(session, task_com_plano, mock_providers):
    """A verificação roda antes do humano: teste vermelho volta para o modelo."""
    task, plano = task_com_plano
    quebrado = "def somar(a, b):\n    return a - b\n"  # quebra o teste existente
    mock_providers.responses = [
        _resposta(
            {
                "client-backend/app/calc.py": quebrado,
                "client-backend/tests/test_calc.py": _suite_com(CASO_SOMAR_NEGATIVOS),
            }
        ),
        _resposta(
            {
                "client-backend/app/calc.py": CODIGO_BOM,
                "client-backend/tests/test_calc.py": _suite_com(CASO_SOMAR_NEGATIVOS),
            }
        ),
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert len(mock_providers.calls) == 2  # gerou, falhou, corrigiu

    segunda = mock_providers.calls[1][0]["content"]
    assert "A verificação anterior falhou" in segunda


@requires_db
def test_desiste_apos_o_teto_de_correcoes(session, task_com_plano, mock_providers):
    """SPEC-00 §4: nenhum ciclo de correção roda indefinidamente."""
    task, plano = task_com_plano
    quebrado = _resposta(
        {
            "client-backend/app/calc.py": "def somar(a, b):\n    return a * b\n",
            "client-backend/tests/test_calc.py": _suite_com(CASO_SOMAR_NEGATIVOS),
        }
    )
    mock_providers.responses = [quebrado] * 10

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    assert "após" in run.failure_reason
    # 1 geração + MAX_LOCAL_FIX correções
    assert len(mock_providers.calls) == executor.settings.max_local_fix + 1


@requires_db
def test_arquivo_fora_do_previsto_vira_desvio(session, task_com_plano, mock_providers):
    """Não bloqueia (SPEC-00 §7), mas fica destacado para o humano."""
    task, plano = task_com_plano
    mock_providers.responses = [
        _resposta(
            {
                "client-backend/app/calc.py": CODIGO_BOM,
                "client-backend/app/extra.py": "VALOR = 1\n",
                "client-backend/tests/test_calc.py": _suite_com(CASO_VALOR_EXTRA),
            }
        )
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert run.deviation_files == ["client-backend/app/extra.py"]


@requires_db
def test_falha_controlada_do_modo_demo(session, task_com_plano, mock_providers):
    """Instrumento do D6(a): falha depois da geração, com custo e transcript reais."""
    task, plano = task_com_plano
    task.demo_force_fail_runs = 2
    session.add(task)
    session.flush()
    mock_providers.responses = [_resposta({"client-backend/app/calc.py": CODIGO_BOM})] * 3

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    assert "modo demo" in run.failure_reason
    assert run.tokens_real > 0  # a run custou de verdade
    assert task.demo_force_fail_runs == 1  # contador decrementado


@requires_db
def test_budget_interrompe_antes_de_gerar(session, task_com_plano, mock_providers):
    task, plano = task_com_plano
    task.demo_budget_cap_tokens = 100
    session.add(task)
    session.flush()
    mock_providers.responses = [_resposta({"client-backend/app/calc.py": CODIGO_BOM})]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "interrompida_budget"
    assert mock_providers.calls == []  # cortou antes de chamar o modelo


@requires_db
def test_sobrescrever_teste_existente_e_recusado(session, task_com_plano, mock_providers):
    """A rede de regressão não pode ser reescrita por quem ela mede.

    Achado de uma execução real: mesmo com o P5 mandando preservar os testes, o
    modelo substituiu o teste que existia pelo seu. A verificação passou, porque
    rodou a suíte já adulterada. O hook determinístico é o que fecha essa porta.
    """
    task, plano = task_com_plano
    substituindo = "from app.calc import somar\n\n\ndef test_outra_coisa():\n    assert somar(1, 1) == 2\n"
    restaurando = TESTE + "\n\ndef test_outra_coisa():\n    assert somar(1, 1) == 2\n"

    mock_providers.responses = [
        _resposta({"client-backend/tests/test_calc.py": substituindo}),
        _resposta({"client-backend/tests/test_calc.py": restaurando}),
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert len(mock_providers.calls) == 2

    # a segunda chamada levou o aviso de qual teste havia sumido
    segunda = mock_providers.calls[1][0]["content"]
    assert "test_somar" in segunda
    assert "rede de regressão" in segunda


@requires_db
def test_apagar_teste_ate_o_fim_reprova_a_run(session, task_com_plano, mock_providers):
    task, plano = task_com_plano
    sem_o_teste = "def test_outra_coisa():\n    assert True\n"
    mock_providers.responses = [_resposta({"client-backend/tests/test_calc.py": sem_o_teste})] * 5

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"


def test_inventario_detecta_teste_removido():
    intacta, aviso = executor.rede_de_regressao_intacta(
        {"test_a", "test_b"}, {"test_a", "test_novo"}
    )

    assert intacta is False
    assert "test_b" in aviso


def test_acrescentar_testes_e_permitido():
    intacta, _ = executor.rede_de_regressao_intacta({"test_a"}, {"test_a", "test_novo"})

    assert intacta is True


# --------------------------------------------------------------------------- #
# SPEC-11: dois alvos, com fronteira
# --------------------------------------------------------------------------- #


def test_fronteira_barra_escrita_no_sdk_das_zonas():
    """A garantia do SPEC-00 §6 não pode depender do julgamento do modelo."""
    intacta, aviso = executor.fronteira_respeitada(
        ["client-frontend/app/transacoes/page.tsx", "client-frontend/dynamic-zones/schema.ts"]
    )

    assert intacta is False
    assert "dynamic-zones/schema.ts" in aviso
    assert "somente leitura" in aviso


def test_fronteira_deixa_passar_o_resto_do_frontend():
    intacta, _ = executor.fronteira_respeitada(
        [
            "client-frontend/app/transacoes/page.tsx",
            "client-frontend/components/AppShell.tsx",
            "client-backend/app/routes.py",
        ]
    )

    assert intacta is True


def test_nome_parecido_nao_e_confundido_com_a_pasta_protegida():
    intacta, _ = executor.fronteira_respeitada(["client-frontend/dynamic-zones-docs/leia.md"])

    assert intacta is True


def test_alvo_de_reconhece_os_dois_e_ignora_o_resto():
    assert context.alvo_de("client-backend/app/routes.py") == "client-backend"
    assert context.alvo_de("client-frontend/app/page.tsx") == "client-frontend"
    assert context.alvo_de("pase-core/app/main.py") is None


def test_inventario_cobre_testes_em_typescript(tmp_path):
    """A rede do frontend precisa da mesma proteção que a do backend."""
    pasta = tmp_path / "client-frontend" / "tests"
    pasta.mkdir(parents=True)
    (pasta / "rotas.test.tsx").write_text(
        'describe("x", () => {\n'
        '  it("guarda a persona", () => {});\n'
        '  test("envia o ticket", () => {});\n'
        "});\n",
        encoding="utf-8",
    )

    nomes = executor.inventario_de_testes(tmp_path)

    assert "client-frontend:guarda a persona" in nomes
    assert "client-frontend:envia o ticket" in nomes


def test_remover_teste_de_typescript_e_detectado(tmp_path):
    antes = {"client-frontend:recusa payload inválido", "client-frontend:mostra o saldo"}
    depois = {"client-frontend:mostra o saldo"}

    intacta, aviso = executor.rede_de_regressao_intacta(antes, depois)

    assert intacta is False
    assert "recusa payload inválido" in aviso


@requires_db
def test_escrever_na_pasta_protegida_reprova_a_run(session, task_com_plano, mock_providers):
    """Ponta a ponta: o arquivo protegido nem chega ao disco do clone."""
    task, plano = task_com_plano
    mock_providers.responses = [
        _resposta({"client-frontend/dynamic-zones/schema.ts": "export const nada = 1;\n"})
    ] * 5

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    assert not (
        executor.git_service.WORKSPACE_ROOT / f"task-{task.id}" / "client-frontend"
    ).exists()


def test_symlink_de_node_modules_nao_sobrevive_ao_gate(tmp_path, monkeypatch):
    """Ferramenta da verificação não pode virar entrega.

    Medido na primeira execução real no frontend: o `.gitignore` traz
    `node_modules/`, com barra, que casa só com diretório. O symlink é um blob
    (modo 120000), escapa do padrão, e o link para `/opt/frontend/node_modules`
    entrou no diff que foi para a Homologação.
    """
    origem = tmp_path / "modulos_da_imagem"
    origem.mkdir()
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()

    monkeypatch.setenv("FRONTEND_NODE_MODULES", str(origem))
    monkeypatch.setattr(executor, "_rodar", lambda comando, cwd, **kwargs: (0, "ok"))

    passou, _ = executor._gate_do_frontend(raiz)

    assert passou is True
    assert not (raiz / "node_modules").is_symlink()


def test_node_modules_emprestado_some_mesmo_se_o_gate_explodir(tmp_path, monkeypatch):
    origem = tmp_path / "modulos_da_imagem"
    origem.mkdir()
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()

    def estourar(comando, cwd, **kwargs):
        raise RuntimeError("tsc morreu")

    monkeypatch.setenv("FRONTEND_NODE_MODULES", str(origem))
    monkeypatch.setattr(executor, "_rodar", estourar)

    with pytest.raises(RuntimeError):
        executor._gate_do_frontend(raiz)

    assert not (raiz / "node_modules").is_symlink()


def test_node_modules_ja_existente_no_clone_e_preservado(tmp_path, monkeypatch):
    """Só se apaga o que foi emprestado - nunca o que já estava lá."""
    origem = tmp_path / "modulos_da_imagem"
    origem.mkdir()
    raiz = tmp_path / "client-frontend"
    (raiz / "node_modules").mkdir(parents=True)

    monkeypatch.setenv("FRONTEND_NODE_MODULES", str(origem))
    monkeypatch.setattr(executor, "_rodar", lambda comando, cwd, **kwargs: (0, "ok"))

    executor._gate_do_frontend(raiz)

    assert (raiz / "node_modules").is_dir()


def test_cobertura_do_frontend_empresta_node_modules_e_devolve(tmp_path, monkeypatch):
    """Sem o empréstimo, a medição do "antes" num clone novo voltava sempre vazia."""
    origem = tmp_path / "modulos_da_imagem"
    origem.mkdir()
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()
    viu_modulos = []

    def registrar(comando, cwd, **kwargs):
        viu_modulos.append((raiz / "node_modules").is_symlink())
        return 1, "sem relatório"

    monkeypatch.setenv("FRONTEND_NODE_MODULES", str(origem))
    monkeypatch.setattr(executor, "_rodar", registrar)

    executor.cobertura_do_frontend(raiz)

    assert viu_modulos == [True]
    assert not (raiz / "node_modules").is_symlink()


def test_gate_do_frontend_compila_o_app(tmp_path, monkeypatch):
    """`next build` faz parte do gate - foi ele que faltou numa falha real.

    Uma entrega pôs `useState` no layout raiz. `tsc` não conhece a fronteira
    `"use client"` (é regra do compilador do Next, não do TypeScript) e o
    `vitest` renderiza páginas no jsdom sem passar pelo App Router, então nunca
    renderiza o layout. Os dois passaram com exit 0 e o app quebrou inteiro.
    """
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()
    executados = []

    def registrar(comando, cwd, **kwargs):
        executados.append(" ".join(comando))
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", registrar)

    passou, log = executor._gate_do_frontend(raiz)

    assert passou is True
    assert "npx next build" in executados
    assert "next build" in log


def test_build_reprovado_reprova_a_run(tmp_path, monkeypatch):
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()

    def so_o_build_falha(comando, cwd, **kwargs):
        if "build" in comando:
            return 1, "Failed to compile.\nYou're importing a component that needs useState."
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", so_o_build_falha)

    passou, log = executor._gate_do_frontend(raiz)

    assert passou is False
    assert "Failed to compile" in log


def test_next_nao_fica_no_clone_depois_do_gate(tmp_path, monkeypatch):
    """`.next/` é artefato de verificação, não entrega."""
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()

    def cria_build(comando, cwd, **kwargs):
        if "build" in comando:
            (raiz / ".next").mkdir(exist_ok=True)
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", cria_build)

    executor._gate_do_frontend(raiz)

    assert not (raiz / ".next").exists()


# --------------------------------------------------------------------------- #
# Fase 1: comportamento novo exige teste novo
# --------------------------------------------------------------------------- #


def test_mudar_producao_sem_teste_novo_reprova():
    """O P5 pede isto desde sempre; agora o código confere."""
    cresceu, aviso = executor.testes_cresceram(
        ["client-backend/app/routes.py"],
        antes={"client-backend:test_a"},
        depois={"client-backend:test_a"},
    )

    assert cresceu is False
    assert "routes.py" in aviso
    assert "teste" in aviso


def test_teste_novo_libera_a_entrega():
    cresceu, _ = executor.testes_cresceram(
        ["client-backend/app/routes.py", "client-backend/tests/test_api.py"],
        antes={"client-backend:test_a"},
        depois={"client-backend:test_a", "client-backend:test_b"},
    )

    assert cresceu is True


def test_mudanca_so_de_estilo_nao_exige_teste():
    """CSS e markdown não têm comportamento a exercitar."""
    cresceu, _ = executor.testes_cresceram(
        ["client-frontend/app/globals.css", "docs/algo.md"],
        antes={"x:test_a"},
        depois={"x:test_a"},
    )

    assert cresceu is True


def test_mexer_so_em_teste_nao_exige_outro_teste():
    cresceu, _ = executor.testes_cresceram(
        ["client-frontend/tests/rotas.test.tsx"],
        antes={"x:test_a"},
        depois={"x:test_a"},
    )

    assert cresceu is True


def test_reconhece_teste_de_typescript_pelo_nome():
    assert executor._e_arquivo_de_teste("client-frontend/tests/zona.test.tsx")
    assert executor._e_arquivo_de_teste("client-backend/tests/test_api.py")
    assert not executor._e_arquivo_de_teste("client-frontend/app/page.tsx")


def test_gate_do_backend_sobe_o_app(tmp_path, monkeypatch):
    """Compilar não é iniciar: o smoke importa o app e chama /health."""
    raiz = tmp_path / "client-backend"
    (raiz / "app").mkdir(parents=True)
    (raiz / "app" / "main.py").write_text(APP_MINIMO, encoding="utf-8")
    executados = []

    def registrar(comando, cwd, **kwargs):
        executados.append(" ".join(comando))
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", registrar)

    passou, log = executor._gate_do_backend(raiz)

    assert passou is True
    assert any("app.main" in c for c in executados)
    assert "smoke" in log


def test_smoke_reprovado_reprova_a_run(tmp_path, monkeypatch):
    raiz = tmp_path / "client-backend"
    (raiz / "app").mkdir(parents=True)
    (raiz / "app" / "main.py").write_text(APP_MINIMO, encoding="utf-8")

    def so_o_smoke_falha(comando, cwd, **kwargs):
        if any("app.main" in parte for parte in comando):
            return 1, "ImportError: cannot import name 'algo'"
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", so_o_smoke_falha)

    passou, log = executor._gate_do_backend(raiz)

    assert passou is False
    assert "ImportError" in log


def test_smoke_e_pulado_onde_nao_ha_app(tmp_path, monkeypatch):
    """Reprovar por ausência de `app/main.py` seria falso negativo."""
    raiz = tmp_path / "client-backend"
    raiz.mkdir()
    executados = []

    def registrar(comando, cwd, **kwargs):
        executados.append(" ".join(comando))
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", registrar)

    passou, _ = executor._gate_do_backend(raiz)

    assert passou is True
    assert not any("app.main" in c for c in executados)


def test_teste_novo_nao_conta_como_desvio():
    """O gate exige teste; marcá-lo como fora do plano acenderia sempre."""
    plano = PlanningDocument(
        task_id=1, affected_files=["client-backend/app/calc.py"], roadmap="", tokens_estimated=0
    )

    desvios = executor._desvios(
        plano,
        [
            "client-backend/app/calc.py",
            "client-backend/tests/test_calc.py",
            "client-backend/app/extra.py",
        ],
    )

    assert desvios == ["client-backend/app/extra.py"]


# --------------------------------------------------------------------------- #
# Fase 1: a cobertura dos arquivos alterados não pode cair
# --------------------------------------------------------------------------- #


def test_queda_de_cobertura_no_arquivo_alterado_reprova():
    """Fecha a saída fácil do gate anterior: teste trivial que não exercita nada."""
    manteve, aviso = executor.cobertura_nao_caiu(
        "client-backend",
        ["client-backend/app/calc.py"],
        antes={"app/calc.py": 90.0},
        depois={"app/calc.py": 50.0},
    )

    assert manteve is False
    assert "calc.py" in aviso
    assert "90% → 50%" in aviso


def test_oscilacao_pequena_nao_reprova():
    """Reprovar por meio ponto transformaria o gate em ruído."""
    manteve, _ = executor.cobertura_nao_caiu(
        "client-backend",
        ["client-backend/app/calc.py"],
        antes={"app/calc.py": 90.0},
        depois={"app/calc.py": 89.0},
    )

    assert manteve is True


def test_arquivo_novo_nao_tem_com_o_que_comparar():
    manteve, _ = executor.cobertura_nao_caiu(
        "client-backend",
        ["client-backend/app/novo.py"],
        antes={},
        depois={"app/novo.py": 10.0},
    )

    assert manteve is True


def test_cobertura_ignora_arquivo_de_teste_e_outro_alvo():
    manteve, _ = executor.cobertura_nao_caiu(
        "client-backend",
        ["client-backend/tests/test_calc.py", "client-frontend/app/page.tsx"],
        antes={"tests/test_calc.py": 100.0},
        depois={"tests/test_calc.py": 10.0},
    )

    assert manteve is True


def test_sem_medicao_o_gate_se_cala(tmp_path, monkeypatch):
    """Quem não conseguiu medir não pode reprovar ninguém."""
    monkeypatch.setattr(executor, "_rodar", lambda comando, cwd, **kwargs: (1, "sem pytest"))

    assert executor.cobertura_por_arquivo(tmp_path) == {}


def test_medicao_de_cobertura_nao_deixa_rastro(tmp_path, monkeypatch):
    """Ferramenta da verificação não vira entrega - a lição do symlink, de novo."""
    raiz = tmp_path / "client-backend"
    raiz.mkdir()

    def suja_o_clone(comando, cwd, **kwargs):
        (raiz / ".coverage").write_text("dados binários", encoding="utf-8")
        (raiz / ".coverage.json").write_text('{"files": {}}', encoding="utf-8")
        return 0, "ok"

    monkeypatch.setattr(executor, "_rodar", suja_o_clone)

    executor.cobertura_por_arquivo(raiz)

    assert not (raiz / ".coverage").exists()
    assert not (raiz / ".coverage.json").exists()


def test_cobertura_do_frontend_le_o_formato_do_istanbul(tmp_path, monkeypatch):
    raiz = tmp_path / "client-frontend"
    (raiz / "coverage").mkdir(parents=True)
    relatorio = {
        f"{raiz}/app/page.tsx": {"s": {"0": 1, "1": 1, "2": 0, "3": 0}},
        f"{raiz}/lib/api.ts": {"s": {"0": 1, "1": 1}},
        f"{raiz}/vazio.ts": {"s": {}},
    }
    (raiz / "coverage" / "coverage-final.json").write_text(
        json.dumps(relatorio), encoding="utf-8"
    )

    monkeypatch.setattr(executor, "_rodar", lambda comando, cwd, **kwargs: (0, "ok"))

    medido = executor.cobertura_do_frontend(raiz)

    assert medido["app/page.tsx"] == 50.0
    assert medido["lib/api.ts"] == 100.0
    assert "vazio.ts" not in medido
    assert not (raiz / "coverage").exists(), "artefato de verificação não pode sobrar"


def test_frontend_sem_medicao_devolve_vazio(tmp_path, monkeypatch):
    raiz = tmp_path / "client-frontend"
    raiz.mkdir()
    monkeypatch.setattr(executor, "_rodar", lambda comando, cwd, **kwargs: (1, "falhou"))

    assert executor.cobertura_do_frontend(raiz) == {}


def test_cada_alvo_tem_medidor_de_cobertura():
    """Alvo novo sem medidor passaria a escapar do gate em silêncio."""
    assert set(executor.MEDIDORES_DE_COBERTURA) == set(context.ALVOS)


# --------------------------------------------------------------------------- #
# Critérios de aceite e revisão independente
# --------------------------------------------------------------------------- #

CRITERIO_SOMAR_TRES = {
    "id": "C1",
    "criterio": "somar_tres(1, 2, 3) devolve 6",
    "como_verificar": "teste unitário",
}
ENTREGA_SOMAR_TRES = {
    "client-backend/app/calc.py": CODIGO_BOM + "\n\ndef somar_tres(a, b, c):\n    return a + b + c\n",
    "client-backend/tests/test_calc.py": _suite_com(CASO_SOMAR_TRES),
}


def _parecer(atendido: bool, explicacao: str = "ok") -> str:
    return json.dumps(
        {
            "criterios": [
                {
                    "id": "C1",
                    "atendido": atendido,
                    "explicacao": explicacao,
                    "evidencia": {
                        "arquivo": "client-backend/app/calc.py",
                        "trecho": "return a + b + c",
                    },
                    "teste": {
                        "arquivo": "client-backend/tests/test_calc.py",
                        "trecho": "assert somar_tres(1, 2, 3) == 6",
                    },
                    "verificacao_manual": None,
                }
            ],
            "colaterais": [],
            "resumo": "r",
        }
    )


@pytest.fixture
def com_criterios(session, task_com_plano, monkeypatch):
    task, plano = task_com_plano
    plano.acceptance_criteria = [CRITERIO_SOMAR_TRES]
    session.add(plano)
    session.commit()
    monkeypatch.setattr(executor.review, "revisar", REVISAR_REAL)
    monkeypatch.setattr(executor.settings, "llm_model_code", "modelo-codigo")
    monkeypatch.setattr(executor.settings, "llm_model_review", "modelo-revisor")
    return task, plano


@requires_db
def test_revisao_aprovada_vira_artefato_da_run(session, com_criterios, mock_providers):
    task, plano = com_criterios
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES), _parecer(True)]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    # o código é escrito por um modelo e revisado por outro
    assert mock_providers.models == ["modelo-codigo", "modelo-revisor"]
    from pathlib import Path

    parecer = json.loads(Path(run.review_path).read_text(encoding="utf-8"))
    assert parecer["aprovado"] is True
    assert parecer["criterios"][0]["id"] == "C1"


@requires_db
def test_revisao_reprovada_volta_para_o_ciclo_de_correcao(
    session, com_criterios, mock_providers
):
    """Gates verdes não bastam: o parecer reprovado vira feedback da próxima rodada."""
    task, plano = com_criterios
    mock_providers.responses = [
        _resposta(ENTREGA_SOMAR_TRES),
        _parecer(False, "o teste não cobre números negativos"),
        _resposta(ENTREGA_SOMAR_TRES),
        _parecer(True),
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert len(mock_providers.calls) == 4
    correcao = mock_providers.calls[2][0]["content"]
    assert "revisão independente reprovou" in correcao
    assert "o teste não cobre números negativos" in correcao


@requires_db
def test_evidencia_inventada_nao_aprova_mesmo_com_o_revisor_dizendo_sim(
    session, com_criterios, mock_providers
):
    task, plano = com_criterios
    falso = json.loads(_parecer(True))
    falso["criterios"][0]["evidencia"]["trecho"] = "return sum([a, b, c])"
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES), json.dumps(falso)] * 10

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    assert "revisão independente reprovou" in run.failure_reason
    parecer = json.loads(open(run.review_path, encoding="utf-8").read())
    assert "evidência não confere" in parecer["criterios"][0]["anulado_por"]


@requires_db
def test_criterios_chegam_ao_prompt_do_executor(session, com_criterios, mock_providers):
    task, plano = com_criterios
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES), _parecer(True)]

    executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert "somar_tres(1, 2, 3) devolve 6" in mock_providers.calls[0][0]["content"]


@requires_db
def test_pedido_de_refazer_chega_ao_executor_e_ao_revisor(
    session, com_criterios, mock_providers
):
    task, plano = com_criterios
    task.redo_feedback = "da última vez o botão não fazia nada"
    session.add(task)
    session.commit()
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES), _parecer(True)]

    executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert "da última vez o botão não fazia nada" in mock_providers.calls[0][0]["content"]
    assert "da última vez o botão não fazia nada" in mock_providers.calls[1][0]["content"]


@requires_db
def test_segunda_tentativa_nao_herda_os_testes_da_que_falhou(
    session, task_com_plano, mock_providers
):
    """Reaproveitar o clone não pode esconder testes novos: o "antes" é a principal.

    Reproduz a run que reprovou quatro vezes uma entrega com três testes novos -
    o clone ainda tinha os testes da tentativa anterior e o inventário "antes" já
    os continha.
    """
    task, plano = task_com_plano
    entrega = {
        "client-backend/app/calc.py": CODIGO_BOM
        + "\n\ndef somar_tres(a, b, c):\n    return a + b + c\n",
        "client-backend/tests/test_calc.py": _suite_com(CASO_SOMAR_TRES),
    }
    # tentativa 1 escreve o código e os testes, mas cai na verificação
    quebrada = dict(entrega)
    quebrada["client-backend/app/calc.py"] = "def somar(a, b):\n    return a * b\n"
    mock_providers.responses = [_resposta(quebrada)] * 10
    primeira = executor.executar(session, task, plano, attempt=1)
    session.commit()
    assert primeira.status == "falha"

    mock_providers.responses = [_resposta(entrega)]
    mock_providers.calls.clear()
    segunda = executor.executar(session, task, plano, attempt=2, trigger="retry")
    session.commit()

    assert segunda.status == "sucesso"


def test_inventario_da_base_ignora_o_que_sobrou_no_disco(alvo):
    """O "antes" vem do git: teste escrito por tentativa falha não entra na régua."""
    workspace = git_service.prepare_workspace(7, nova=True, titulo="x")
    (workspace.path / "client-backend" / "tests" / "test_sobra.py").write_text(
        "def test_que_ficou_no_disco():\n    pass\n", encoding="utf-8"
    )

    no_disco = executor.inventario_de_testes(workspace.path)
    da_base = executor.inventario_da_base(workspace)

    assert "client-backend:test_que_ficou_no_disco" in no_disco
    assert "client-backend:test_que_ficou_no_disco" not in da_base
    assert "client-backend:test_somar" in da_base


def test_reaproveitar_o_clone_descarta_o_que_nao_foi_commitado(alvo):
    primeira = git_service.prepare_workspace(8, nova=True, titulo="x")
    resto = primeira.path / "client-backend" / "app" / "resto.py"
    resto.write_text("X = 1\n", encoding="utf-8")

    segunda = git_service.prepare_workspace(8, nova=False, titulo="x")

    assert not (segunda.path / "client-backend" / "app" / "resto.py").exists()


# --------------------------------------------------------------------------- #
# Garantias do capítulo 4: plano, contexto, ambiente, fronteira, rede, revisão
# --------------------------------------------------------------------------- #


def _commitar_na_origem(origem, arquivos: dict[str, str]) -> None:
    """Acrescenta arquivos à branch principal do repositório de mentira."""
    for relativo, texto in arquivos.items():
        caminho = origem / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    repo = Repo(origem)
    repo.git.add("--all")
    repo.index.commit("mais arquivos")


def _transcript(run) -> list[dict]:
    from pathlib import Path

    return [
        json.loads(linha)
        for linha in Path(run.transcript_path).read_text(encoding="utf-8").splitlines()
    ]


@requires_db
def test_plano_sem_criterios_e_recusado_antes_de_gastar(session, task_com_plano, mock_providers):
    """Sem critério a revisão não teria o que conferir: a entrega não pode seguir."""
    task, plano = task_com_plano
    plano.acceptance_criteria = []
    session.add(plano)
    session.commit()

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    assert "critérios de aceite" in run.failure_reason
    assert "Replaneje" in run.failure_reason
    assert mock_providers.calls == []


@requires_db
def test_arquivo_marcado_excluir_e_apagado(session, task_com_plano, alvo, mock_providers):
    task, plano = task_com_plano
    _commitar_na_origem(alvo, {"client-backend/app/velho.py": "OBSOLETO = 1\n"})
    plano.affected_files = ["client-backend/app/velho.py"]
    plano.file_actions = {"client-backend/app/velho.py": "excluir"}
    session.add(plano)
    session.commit()
    mock_providers.responses = [
        json.dumps({"files": [], "excluir": ["client-backend/app/velho.py"]})
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso", run.failure_reason
    assert run.deviation_files == []
    from pathlib import Path

    assert "deleted file" in Path(run.diff_path).read_text(encoding="utf-8")
    clone = executor.git_service.WORKSPACE_ROOT / f"task-{task.id}"
    assert not (clone / "client-backend" / "app" / "velho.py").exists()
    # a ação chega ao executor junto do caminho
    assert "`client-backend/app/velho.py` - excluir" in mock_providers.calls[0][0]["content"]


@requires_db
def test_excluir_na_pasta_protegida_e_recusado(session, task_com_plano, alvo, mock_providers):
    task, plano = task_com_plano
    _commitar_na_origem(alvo, {"client-frontend/dynamic-zones/schema.ts": "export const z = 1;\n"})
    mock_providers.responses = [
        json.dumps({"files": [], "excluir": ["client-frontend/dynamic-zones/schema.ts"]})
    ] * 5

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    clone = executor.git_service.WORKSPACE_ROOT / f"task-{task.id}"
    assert (clone / "client-frontend" / "dynamic-zones" / "schema.ts").exists()


@requires_db
def test_caminho_absoluto_nao_escreve_fora_do_clone(
    session, task_com_plano, tmp_path, mock_providers
):
    task, plano = task_com_plano
    fora = tmp_path / "fora_do_clone.py"
    mock_providers.responses = [_resposta({str(fora): "x = 1\n"})] * 5

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "falha"
    assert "fora do seu alcance" in run.failure_reason
    assert not fora.exists()


@requires_db
def test_subir_com_ponto_ponto_para_o_pase_core_e_recusado(
    session, task_com_plano, mock_providers
):
    task, plano = task_com_plano
    mock_providers.responses = [
        _resposta({"client-backend/../pase-core/app/main.py": "# sequestrado\n"}),
        _resposta(ENTREGA_SOMAR_TRES),
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    segunda = mock_providers.calls[1][0]["content"]
    assert "A entrega anterior foi recusada" in segunda
    assert "pase-core" in segunda
    clone = executor.git_service.WORKSPACE_ROOT / f"task-{task.id}"
    assert not (clone / "pase-core").exists()


@requires_db
def test_caminho_com_ponto_barra_nao_vira_desvio(session, task_com_plano, mock_providers):
    task, plano = task_com_plano
    mock_providers.responses = [
        _resposta({f"./{c}": t for c, t in ENTREGA_SOMAR_TRES.items()})
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert run.deviation_files == []


def test_escrita_fora_do_clone_e_recusada_no_ponto_da_escrita(alvo):
    """Última trava: mesmo sem passar pela fronteira, nada sai do clone."""
    workspace = git_service.prepare_workspace(9, nova=True, titulo="x")

    with pytest.raises(git_service.GitServiceError):
        git_service.write_files(workspace, [{"path": "../escapou.txt", "content": "x"}])
    with pytest.raises(git_service.GitServiceError):
        git_service.delete_files(workspace, ["../repo/client-backend/app/calc.py"])

    assert not (workspace.path.parent / "escapou.txt").exists()


def test_push_para_remoto_de_rede_e_recusado(alvo):
    """Daqui nenhum push sai para a rede: publicar no GitHub é papel do `github`."""
    workspace = git_service.prepare_workspace(10, nova=True, titulo="x")
    workspace.repo.remotes.origin.set_url("https://github.com/alguem/repo.git")

    with pytest.raises(git_service.GitServiceError, match="remoto de rede"):
        git_service.push(workspace)

    workspace.repo.remotes.origin.set_url("git@github.com:alguem/repo.git")
    with pytest.raises(git_service.GitServiceError, match="remoto de rede"):
        git_service.push(workspace)


@requires_db
def test_p5_recebe_o_roteiro_e_nao_o_repositorio_inteiro(
    session, task_com_plano, alvo, mock_providers
):
    task, plano = task_com_plano
    _commitar_na_origem(alvo, {"client-backend/app/outro.py": "MARCA_QUE_NAO_DEVE_IR = 1\n"})
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES)]

    executor.executar(session, task, plano, attempt=1)
    session.commit()

    prompt = mock_providers.calls[0][0]["content"]
    assert "client-backend/app/outro.py" in prompt  # o caminho está na lista
    assert "MARCA_QUE_NAO_DEVE_IR" not in prompt  # o conteúdo não
    assert "def somar(a, b)" in prompt  # o arquivo previsto vai inteiro
    assert "def test_somar" in prompt  # e o teste que o importa
    assert "[pytest]" in prompt  # e a infraestrutura de teste


@requires_db
def test_reescrever_arquivo_nao_mostrado_e_recusado_e_ele_passa_a_ser_mostrado(
    session, task_com_plano, alvo, mock_providers
):
    task, plano = task_com_plano
    _commitar_na_origem(alvo, {"client-backend/app/outro.py": "MARCA_ORIGINAL = 1\n"})
    as_cegas = dict(ENTREGA_SOMAR_TRES)
    as_cegas["client-backend/app/outro.py"] = "INVENTADO = 2\n"
    mock_providers.responses = [_resposta(as_cegas), _resposta(ENTREGA_SOMAR_TRES)]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    segunda = mock_providers.calls[1][0]["content"]
    assert "cujo conteúdo não recebeu" in segunda
    assert "MARCA_ORIGINAL = 1" in segunda
    clone = executor.git_service.WORKSPACE_ROOT / f"task-{task.id}"
    assert "MARCA_ORIGINAL" in (clone / "client-backend/app/outro.py").read_text(encoding="utf-8")


@requires_db
def test_pedido_de_leitura_traz_o_arquivo_na_rodada_seguinte(
    session, task_com_plano, alvo, mock_providers
):
    task, plano = task_com_plano
    _commitar_na_origem(alvo, {"client-backend/app/outro.py": "MARCA_PEDIDA = 1\n"})
    mock_providers.responses = [
        json.dumps({"files": [], "ler": ["client-backend/app/outro.py"]}),
        _resposta(ENTREGA_SOMAR_TRES),
    ]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    assert "MARCA_PEDIDA" not in mock_providers.calls[0][0]["content"]
    assert "MARCA_PEDIDA" in mock_providers.calls[1][0]["content"]


# ----- ambiente isolado ----------------------------------------------------- #


def test_ambiente_isolado_tira_credenciais_e_enderecos():
    origem = {
        "PATH": "/usr/bin",
        "HOME": "/root",
        "LANG": "C.UTF-8",
        "LLM_API_KEY": "sk-x",
        "OPENAI_API_KEY": "sk-y",
        "ANTHROPIC_API_KEY": "sk-z",
        "EMBEDDING_API_KEY": "sk-w",
        "GITHUB_TOKEN": "ghp",
        "DATABASE_URL": "postgresql://pase:pase@db/pase",
        "CLIENT_API_URL": "http://client-backend:8001",
        "REPO_PATH": "/workspace/repo",
        "MEU_SEGREDO_SECRET": "s",
        "HTTPS_PROXY": "http://proxy-de-verdade:3128",
    }

    env = executor.ambiente_isolado(origem)

    for proibido in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "EMBEDDING_API_KEY",
        "GITHUB_TOKEN",
        "DATABASE_URL",
        "CLIENT_API_URL",
        "REPO_PATH",
        "MEU_SEGREDO_SECRET",
    ):
        assert proibido not in env, proibido
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/root"
    assert env["HTTPS_PROXY"] == executor.BURACO_NEGRO
    assert env["http_proxy"] == executor.BURACO_NEGRO
    assert env["NO_PROXY"] == ""
    assert env["npm_config_offline"] == "true"
    assert env["NEXT_TELEMETRY_DISABLED"] == "1"
    assert env["PIP_NO_INDEX"] == "1"


def test_subprocesso_da_verificacao_nao_ve_o_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_segredo")
    monkeypatch.setenv("LLM_API_KEY", "sk-segredo")

    codigo, saida = executor._rodar(
        [
            "python",
            "-c",
            "import os; print(os.getenv('GITHUB_TOKEN'), os.getenv('LLM_API_KEY'), "
            "os.getenv('HTTPS_PROXY'))",
        ],
        tmp_path,
    )

    assert codigo == 0
    assert "segredo" not in saida
    assert f"None None {executor.BURACO_NEGRO}" in saida


def test_cliente_http_que_respeita_proxy_nao_sai(tmp_path):
    """O que o isolamento garante: HTTP via proxy cai no buraco negro na hora."""
    codigo, saida = executor._rodar(
        [
            "python",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://example.com', timeout=5)",
        ],
        tmp_path,
        timeout=30,
    )

    assert codigo != 0
    assert "refused" in saida.lower() or "urlopen error" in saida.lower()


# ----- rede de regressão: asserções ---------------------------------------- #


def test_teste_esvaziado_e_detectado():
    antes = executor._contar_assercoes([("client-backend", "tests/test_calc.py", TESTE)])
    esvaziado = "from app.calc import somar\n\n\ndef test_somar():\n    pass\n"
    depois = executor._contar_assercoes([("client-backend", "tests/test_calc.py", esvaziado)])

    intacta, aviso = executor.assercoes_preservadas(antes, depois)

    assert intacta is False
    assert "client-backend:test_somar (1 → 0)" in aviso


def test_assercao_apagada_de_helper_e_detectada_pelo_total():
    com_helper = (
        "def _confere(x):\n    assert x == 3\n    assert x > 0\n\n\n"
        "def test_a():\n    _confere(3)\n"
    )
    sem = "def _confere(x):\n    assert x == 3\n\n\ndef test_a():\n    _confere(3)\n"
    antes = executor._contar_assercoes([("client-backend", "tests/test_a.py", com_helper)])
    depois = executor._contar_assercoes([("client-backend", "tests/test_a.py", sem)])

    intacta, aviso = executor.assercoes_preservadas(antes, depois)

    assert intacta is False
    assert "total de asserções de client-backend (2 → 1)" in aviso


def test_mover_teste_de_arquivo_e_acrescentar_casos_e_permitido():
    antes = executor._contar_assercoes([("client-backend", "tests/test_calc.py", TESTE)])
    depois = executor._contar_assercoes(
        [
            ("client-backend", "tests/test_calc.py", "import x\n"),
            ("client-backend", "tests/test_soma.py", _suite_com(CASO_SOMAR_TRES)),
        ]
    )

    intacta, _ = executor.assercoes_preservadas(antes, depois)

    assert intacta is True


def test_pytest_raises_conta_como_assercao():
    texto = (
        "import pytest\n\n\ndef test_x():\n    with pytest.raises(ValueError):\n"
        "        int('a')\n"
    )
    por_caso, total = executor._assercoes_do_arquivo("tests/test_x.py", texto)

    assert por_caso == {"test_x": 1}
    assert total == 1


def test_arquivo_que_nao_compila_ainda_e_contado():
    texto = "def test_x():\n    assert 1 ==\n"
    por_caso, _ = executor._assercoes_do_arquivo("tests/test_x.py", texto)

    assert por_caso == {"test_x": 1}


def test_assercoes_de_typescript_por_caso():
    texto = (
        'describe("tema", () => {\n'
        '  it("aplica o tema", () => {\n'
        "    expect(a).toBe(1);\n"
        "    expect(b).toBe(2);\n"
        "  });\n"
        '  test("lembra a escolha", () => {\n'
        "    expect(c).toBe(3);\n"
        "  });\n"
        "});\n"
    )
    por_caso, total = executor._assercoes_do_arquivo("tests/tema.test.tsx", texto)

    assert por_caso == {"aplica o tema": 2, "lembra a escolha": 1}
    assert total == 3


def test_expect_removido_de_caso_typescript_e_detectado():
    antes_txt = 'it("mostra o saldo", () => {\n  expect(a).toBe(1);\n  expect(b).toBe(2);\n});\n'
    depois_txt = 'it("mostra o saldo", () => {\n  expect(a).toBe(1);\n});\n'
    antes = executor._contar_assercoes([("client-frontend", "tests/s.test.tsx", antes_txt)])
    depois = executor._contar_assercoes([("client-frontend", "tests/s.test.tsx", depois_txt)])

    intacta, aviso = executor.assercoes_preservadas(antes, depois)

    assert intacta is False
    assert "client-frontend:mostra o saldo (2 → 1)" in aviso


def test_inventario_cobre_test_ts_fora_da_pasta_tests(tmp_path):
    pasta = tmp_path / "client-frontend" / "lib"
    pasta.mkdir(parents=True)
    (pasta / "theme.test.ts").write_text(
        'it("lê a preferência", () => { expect(1).toBe(1); });\n', encoding="utf-8"
    )
    (tmp_path / "client-frontend" / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "client-frontend" / "node_modules" / "x" / "y.test.ts").write_text(
        'it("de terceiros", () => {});\n', encoding="utf-8"
    )

    nomes = executor.inventario_de_testes(tmp_path)

    assert "client-frontend:lê a preferência" in nomes
    assert "client-frontend:de terceiros" not in nomes


@requires_db
def test_esvaziar_teste_existente_e_recusado_ponta_a_ponta(
    session, task_com_plano, mock_providers
):
    task, plano = task_com_plano
    esvaziada = dict(ENTREGA_SOMAR_TRES)
    esvaziada["client-backend/tests/test_calc.py"] = (
        "from app.calc import somar\n\n\ndef test_somar():\n    somar(1, 2)\n\n\n" + CASO_SOMAR_TRES
    )
    mock_providers.responses = [_resposta(esvaziada), _resposta(ENTREGA_SOMAR_TRES)]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    assert run.status == "sucesso"
    segunda = mock_providers.calls[1][0]["content"]
    assert "Você reduziu as asserções" in segunda
    assert "client-backend:test_somar (1 → 0)" in segunda
    assert any(
        linha.get("evento") == "rede_de_regressao_enfraquecida" for linha in _transcript(run)
    )


# ----- pacote de homologação: transcript completo -------------------------- #


@requires_db
def test_transcript_traz_planejamento_execucao_e_revisao_crua(
    session, com_criterios, tmp_path, mock_providers
):
    task, plano = com_criterios
    do_plano = tmp_path / "plano.jsonl"
    do_plano.write_text(
        json.dumps({"role": "system", "content": "PROMPT_DO_P4"})
        + "\n"
        + json.dumps({"role": "assistant", "content": "RESPOSTA_DO_P4", "trace_id": "t4"})
        + "\n",
        encoding="utf-8",
    )
    plano.transcript_path = str(do_plano)
    session.add(plano)
    session.commit()
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES), _parecer(True)]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    linhas = _transcript(run)
    assert linhas[0]["content"] == "PROMPT_DO_P4"
    assert linhas[0]["fase"] == "planejamento"
    assert linhas[1]["trace_id"] == "t4"
    revisao = [linha for linha in linhas if linha.get("fase") == "revisao"]
    assert "Revisão Independente" in revisao[0]["content"]  # o prompt do P12, cru
    assert revisao[1]["role"] == "assistant" and revisao[1]["modelo"] == "modelo-revisor"
    assert json.loads(revisao[1]["content"])["criterios"][0]["id"] == "C1"
    assert revisao[2]["evento"] == "revisao"


@requires_db
def test_parecer_registra_quem_revisou_e_quem_escreveu(session, com_criterios, mock_providers):
    task, plano = com_criterios
    mock_providers.responses = [_resposta(ENTREGA_SOMAR_TRES), _parecer(True)]

    run = executor.executar(session, task, plano, attempt=1)
    session.commit()

    from pathlib import Path

    parecer = json.loads(Path(run.review_path).read_text(encoding="utf-8"))
    assert parecer["modelo"] == "modelo-revisor"
    assert parecer["modelo_do_codigo"] == "modelo-codigo"
    assert parecer["mesmo_modelo"] is False
    assert "troca" not in parecer
