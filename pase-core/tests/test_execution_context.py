"""Contexto do P5 e fronteira de escrita (SPEC-04 §4.5.2, SPEC-11 §4).

O P5 parte do roteiro: recebe os arquivos do plano, as importações diretas deles,
os testes que os importam e a infraestrutura de teste - e só os caminhos do resto.
A fronteira normaliza todo caminho antes de decidir se o Executor pode tocá-lo.
"""

import pytest

from app.execution import context

ARQUIVOS = {
    # frontend: a forma de uma tarefa de modo escuro
    "client-frontend/app/layout.tsx": (
        'import type { Metadata } from "next";\n'
        'import "./globals.css";\n'
        'import AppShell from "@/components/AppShell";\n'
    ),
    "client-frontend/app/globals.css": ":root { --surface: #fff; }\n",
    "client-frontend/app/page.tsx": "export default function Inicio() { return 'MARCA_DA_PAGINA'; }\n",
    "client-frontend/components/AppShell.tsx": (
        'import Link from "next/link";\n'
        'import { Botao } from "@/components/ui";\n'
        'import { usePersona } from "@/lib/user";\n'
        'import SuggestModal from "./SuggestModal";\n'
    ),
    "client-frontend/components/ui.tsx": "export const Botao = 1;\n",
    "client-frontend/components/SuggestModal.tsx": "export default 1;\n",
    "client-frontend/lib/user.ts": "export const usePersona = 1;\n",
    "client-frontend/dynamic-zones/schema.ts": "export const z = 1;\n",
    "client-frontend/tailwind.config.ts": "export default { theme: {} };\n",
    "client-frontend/package.json": "{}\n",
    "client-frontend/vitest.config.ts": "export default {};\n",
    "client-frontend/vitest.setup.ts": "import './tests/_mocks';\n",
    "client-frontend/tests/_mocks.ts": "export const espiao = 1;\n",
    "client-frontend/tests/rotas.test.tsx": (
        'import AppShell from "@/components/AppShell";\n'
        'it("mostra o menu", () => { expect(1).toBe(1); });\n'
    ),
    "client-frontend/tests/inicio.test.tsx": (
        'import Inicio from "@/app/page";\nit("abre", () => { expect(1).toBe(1); });\n'
    ),
    # backend
    "client-backend/app/__init__.py": "",
    "client-backend/app/models.py": "class Goal: ...\n",
    "client-backend/app/db.py": "engine = None\n",
    "client-backend/app/routes.py": (
        "from app.models import Goal\nfrom . import db\n\nrouter = None\n"
    ),
    "client-backend/app/insights.py": "MARCA_DOS_INSIGHTS = 1\n",
    "client-backend/tests/conftest.py": "import pytest\n",
    "client-backend/tests/test_api.py": "from app.routes import router\n\n\ndef test_x():\n    assert router is None\n",
    "client-backend/tests/test_insights.py": "from app.insights import MARCA_DOS_INSIGHTS\n",
    "client-backend/pytest.ini": "[pytest]\n",
}


@pytest.fixture
def repo(tmp_path):
    for relativo, texto in ARQUIVOS.items():
        caminho = tmp_path / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# O que entra no P5
# --------------------------------------------------------------------------- #


def test_modo_escuro_recebe_o_que_precisa(repo):
    """CSS traz o Tailwind e o layout; AppShell traz o que importa; testes e infra vêm junto."""
    foco = context.arquivos_em_foco(
        repo,
        [
            "client-frontend/app/globals.css",
            "client-frontend/components/AppShell.tsx",
            "client-frontend/lib/theme.ts",  # a criar
        ],
    )

    for esperado in (
        "client-frontend/tailwind.config.ts",
        "client-frontend/app/layout.tsx",
        "client-frontend/components/ui.tsx",
        "client-frontend/lib/user.ts",
        "client-frontend/components/SuggestModal.tsx",
        "client-frontend/tests/rotas.test.tsx",
        "client-frontend/tests/_mocks.ts",
        "client-frontend/vitest.config.ts",
        "client-frontend/vitest.setup.ts",
        "client-frontend/package.json",
    ):
        assert esperado in foco, esperado

    assert "client-frontend/app/page.tsx" not in foco
    assert "client-frontend/tests/inicio.test.tsx" not in foco
    # nenhum arquivo do outro alvo, que o plano não toca
    assert not any(c.startswith("client-backend/") for c in foco)


def test_conteudo_so_dos_arquivos_em_foco_mas_todos_os_caminhos(repo):
    texto, mostrados = context.contexto_da_execucao(
        repo, ["client-frontend/components/AppShell.tsx"]
    )

    assert "client-frontend/app/page.tsx" in texto  # o caminho aparece na lista
    assert "MARCA_DA_PAGINA" not in texto  # o conteúdo não
    assert "client-frontend/components/AppShell.tsx" in mostrados
    assert "client-frontend/app/page.tsx" not in mostrados


def test_arquivo_previsto_que_ainda_nao_existe_e_sinalizado(repo):
    texto, mostrados = context.contexto_da_execucao(repo, ["client-frontend/lib/theme.ts"])

    assert "### client-frontend/lib/theme.ts\n(arquivo ainda não existe)" in texto
    assert "client-frontend/lib/theme.ts" not in mostrados


def test_importacoes_python_de_um_salto(repo):
    importados = context.importacoes_diretas(repo, "client-backend/app/routes.py")

    assert "client-backend/app/models.py" in importados
    assert "client-backend/app/db.py" in importados
    assert "client-backend/app/insights.py" not in importados


def test_backend_traz_teste_que_importa_e_a_infra(repo):
    foco = context.arquivos_em_foco(repo, ["client-backend/app/routes.py"])

    assert "client-backend/tests/test_api.py" in foco
    assert "client-backend/tests/conftest.py" in foco
    assert "client-backend/pytest.ini" in foco
    assert "client-backend/tests/test_insights.py" not in foco
    assert "client-backend/app/insights.py" not in foco


def test_extras_entram_no_foco(repo):
    """O que já foi escrito na run, ou o modelo pediu para ler, vai junto."""
    foco = context.arquivos_em_foco(
        repo, ["client-backend/app/routes.py"], ["client-backend/app/insights.py"]
    )

    assert "client-backend/app/insights.py" in foco


def test_arquivo_protegido_importado_aparece_como_somente_leitura(repo):
    (repo / "client-frontend/components/Zona.tsx").write_text(
        'import { z } from "@/dynamic-zones/schema";\n', encoding="utf-8"
    )

    texto, _ = context.contexto_da_execucao(repo, ["client-frontend/components/Zona.tsx"])

    assert "### client-frontend/dynamic-zones/schema.ts  [SOMENTE LEITURA" in texto


# --------------------------------------------------------------------------- #
# Fronteira de escrita
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("client-backend/app/x.py", "client-backend/app/x.py"),
        ("./client-backend/app/x.py", "client-backend/app/x.py"),
        ("client-backend//app/./x.py", "client-backend/app/x.py"),
        ("client-backend\\app\\x.py", "client-backend/app/x.py"),
        ("client-backend/tests/../app/x.py", "client-backend/app/x.py"),
        ("/etc/passwd", None),
        ("C:\\Windows\\x", None),
        ("../fora.txt", None),
        ("client-backend/../../fora.txt", None),
        ("", None),
        (".", None),
    ],
)
def test_normalizar(bruto, esperado):
    assert context.normalizar(bruto) == esperado


@pytest.mark.parametrize(
    ("caminho", "trecho_do_motivo"),
    [
        ("client-frontend/dynamic-zones/schema.ts", "dynamic-zones"),
        ("client-frontend/./dynamic-zones/schema.ts", "dynamic-zones"),
        ("client-frontend/app/../dynamic-zones/x.ts", "dynamic-zones"),
        ("client-backend/../pase-core/app/main.py", "pase-core"),
        ("docs/contracts/zona.json", "docs/contracts"),
        ("README.md", "fora dos alvos"),
        ("pase-panel/app/page.tsx", "fora dos alvos"),
        ("client-backend/.git/config", "git"),
        ("/tmp/pase/task-1/client-backend/app/x.py", "absoluto"),
        ("../../etc/passwd", "fora da raiz"),
    ],
)
def test_fronteira_recusa_com_o_motivo(caminho, trecho_do_motivo):
    motivo = context.motivo_de_bloqueio(caminho)

    assert motivo is not None
    assert trecho_do_motivo in motivo


@pytest.mark.parametrize(
    "caminho",
    [
        "client-backend/app/routes.py",
        "./client-frontend/components/AppShell.tsx",
        "client-frontend/dynamic-zones-docs/leia.md",
    ],
)
def test_fronteira_libera_o_que_esta_nos_alvos(caminho):
    assert context.motivo_de_bloqueio(caminho) is None


def test_reconhece_arquivos_de_teste():
    assert context.e_arquivo_de_teste("client-frontend/tests/tema.test.tsx")
    assert context.e_arquivo_de_teste("client-frontend/lib/theme.test.ts")
    assert context.e_arquivo_de_teste("client-backend/tests/test_api.py")
    assert not context.e_arquivo_de_teste("client-frontend/app/page.tsx")
    assert not context.e_arquivo_de_teste("client-backend/app/testing.py")
