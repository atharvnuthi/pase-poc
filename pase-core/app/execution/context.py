"""Montagem do contexto dos alvos para os prompts de execução (SPEC-04 §4.1, SPEC-11 §3).

Duas leituras, com papéis diferentes:

- **Planejamento (P4)** lê o código **inteiro** dos alvos, sem heurística de
  seleção. É a varredura do repositório: é dela que sai o mapeamento de impacto.
- **Execução (P5)** usa o roteiro como insumo principal e dispensa nova varredura
  completa: recebe o conteúdo dos arquivos que o plano prevê, das importações
  diretas deles (um salto), dos testes que os importam e da infraestrutura de
  teste - e só a **lista de caminhos** do resto. Um arquivo existente que não
  foi mostrado não pode ser reescrito às cegas: o Executor recusa e mostra o
  conteúdo na rodada seguinte (ver `executor._executar`).
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from app.common.config import settings

#: Os alvos do Executor (SPEC-11 §3). Fora daqui ele não escreve.
ALVOS = ("client-backend", "client-frontend")

#: Compatibilidade com o código que ainda fala de um alvo só.
ALVO = ALVOS[0]

#: Fora do alcance do Executor, verificado por código antes de qualquer escrita
#: (SPEC-11 §4). São os componentes que implementam as garantias da própria
#: arquitetura: o SDK que recusa payload malicioso de Zona Dinâmica, os
#: contratos que ele espelha e o motor do PASE. A garantia não pode depender do
#: julgamento do modelo que ela limita. Os dois últimos já estão fora dos alvos;
#: ficam listados para que a recusa diga o motivo certo.
FRONTEIRA = ("client-frontend/dynamic-zones", "docs/contracts", "pase-core")

#: Pastas e arquivos que não são código-fonte dos alvos.
IGNORAR = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "data",
    "node_modules",
    ".git",
    ".next",
    "coverage",
}

EXTENSOES = {".py", ".txt", ".ini", ".toml", ".cfg", ".ts", ".tsx", ".json", ".mjs", ".css"}

#: Estimativa grosseira, boa o bastante para dimensionar o budget e o prompt.
CHARS_POR_TOKEN = 3.5

#: O que a suíte de cada alvo precisa para rodar e para ser imitada: sem isto o
#: executor escreve teste que não sabe montar (mocks, fixtures, setup).
INFRA_DE_TESTE = {
    "client-backend": ("pytest.ini", "requirements.txt", "tests/conftest.py"),
    "client-frontend": (
        "package.json",
        "tsconfig.json",
        "vitest.config.ts",
        "vitest.setup.ts",
        "tests/_*.ts",
        "tests/_*.tsx",
    ),
}

#: Arquivos que andam juntos sem que um importe o outro. CSS do frontend é
#: escrito com os tokens do Tailwind; mudar um sem ver o outro produz classe
#: que não existe - o caso de um modo escuro que define cor que nada usa.
COMPANHEIROS = {
    "client-frontend/tailwind.config.ts": ("client-frontend/app/globals.css",),
    "client-frontend/app/globals.css": (
        "client-frontend/tailwind.config.ts",
        "client-frontend/app/layout.tsx",
    ),
}

#: Importações em TypeScript: `from "x"`, `import "x"`, `import("x")`,
#: `require("x")` e `vi.mock("x")` - o mock também prende o teste ao módulo.
IMPORT_TS = re.compile(
    r"""(?:\bfrom|\bimport|\brequire\(|\bimport\(|\.mock\()\s*["']([^"']+)["']"""
)

#: Importações em Python: `from app.x import y`, `from . import y`, `import app.x`.
FROM_PY = re.compile(
    r"^[ \t]*from[ \t]+([.\w]+)[ \t]+import[ \t]+(\([^)]*\)|[^\n]+)", re.MULTILINE
)
IMPORT_PY = re.compile(r"^[ \t]*import[ \t]+([\w.]+)", re.MULTILINE)

#: Pacotes locais de primeiro nível de cada alvo Python.
PACOTES_LOCAIS = ("app", "tests")

SUFIXOS_TS = ("", ".ts", ".tsx", ".js", ".mjs", ".css", "/index.ts", "/index.tsx")


def _arquivos(raiz: Path) -> list[Path]:
    return [
        caminho
        for caminho in sorted(raiz.rglob("*"))
        if caminho.is_file()
        and caminho.suffix in EXTENSOES
        and not any(parte in IGNORAR for parte in caminho.parts)
    ]


def _alvos(base: Path | None) -> list[Path]:
    raiz = base or Path(settings.repo_path)
    return [raiz / alvo for alvo in ALVOS if (raiz / alvo).exists()]


# --------------------------------------------------------------------------- #
# Fronteira de escrita
# --------------------------------------------------------------------------- #


def normalizar(caminho: str) -> str | None:
    """Caminho relativo à raiz, em forma posix canônica - ou `None` se escapa.

    `./a`, `a//b` e `a/x/../b` viram a forma única que o resto do sistema
    compara. Caminho absoluto (`/etc/x`, `C:\\x`) e caminho que sobe acima da
    raiz (`..`) não têm forma relativa legítima: são recusados, não corrigidos.
    """
    bruto = (caminho or "").strip().replace("\\", "/")
    if not bruto or bruto.startswith("/") or re.match(r"^[A-Za-z]:", bruto):
        return None
    normal = posixpath.normpath(bruto)
    if normal in (".", "..") or normal.startswith("../"):
        return None
    return normal


def motivo_de_bloqueio(caminho: str) -> str | None:
    """Por que o Executor não pode escrever (nem apagar) aqui. `None` se pode.

    A ordem importa só para a mensagem: o primeiro motivo encontrado é o que
    volta para o modelo.
    """
    normal = normalizar(caminho)
    if normal is None:
        return "caminho absoluto ou fora da raiz do repositório"
    partes = normal.split("/")
    if ".git" in partes:
        return "metadado do git"
    for protegida in FRONTEIRA:
        if normal == protegida or normal.startswith(f"{protegida}/"):
            return f"pasta protegida `{protegida}/`"
    if alvo_de(normal) is None:
        return "fora dos alvos (`client-backend/`, `client-frontend/`)"
    return None


def dentro_da_fronteira(caminho_relativo: str) -> bool:
    """O Executor pode escrever neste caminho (SPEC-11 §4)?"""
    return motivo_de_bloqueio(caminho_relativo) is None


def alvo_de(caminho_relativo: str) -> str | None:
    """A qual alvo pertence este caminho, se pertencer a algum."""
    normalizado = caminho_relativo.replace("\\", "/")
    for alvo in ALVOS:
        if normalizado.startswith(f"{alvo}/"):
            return alvo
    return None


def e_arquivo_de_teste(caminho: str) -> bool:
    """Arquivo da rede de regressão de algum alvo, pelo caminho."""
    normalizado = caminho.replace("\\", "/")
    nome = normalizado.rsplit("/", 1)[-1]
    return (
        "/tests/" in normalizado
        or (nome.startswith("test_") and nome.endswith(".py"))
        or nome.endswith((".test.ts", ".test.tsx"))
    )


# --------------------------------------------------------------------------- #
# Contexto do planejamento: o código inteiro
# --------------------------------------------------------------------------- #


def arvore(base: Path | None = None) -> str:
    """Lista dos caminhos dos alvos, relativos à raiz do repositório."""
    linhas = []
    for alvo in _alvos(base):
        for caminho in _arquivos(alvo):
            relativo = caminho.relative_to(alvo.parent).as_posix()
            marca = "" if dentro_da_fronteira(relativo) else "   (somente leitura)"
            linhas.append(f"- {relativo}{marca}")
    return "\n".join(linhas)


def fontes(base: Path | None = None) -> str:
    """Conteúdo integral dos arquivos dos alvos, em blocos identificados."""
    blocos = []
    for alvo in _alvos(base):
        for caminho in _arquivos(alvo):
            rotulo = caminho.relative_to(alvo.parent).as_posix()
            aviso = "" if dentro_da_fronteira(rotulo) else "  [SOMENTE LEITURA - não editar]"
            conteudo = caminho.read_text(encoding="utf-8")
            blocos.append(f"### {rotulo}{aviso}\n```\n{conteudo}\n```")
    return "\n\n".join(blocos)


def source_tree(base: Path | None = None) -> str:
    """Árvore + fontes, no formato que os prompts P4 e P10 esperam."""
    return f"Árvore:\n{arvore(base)}\n\nConteúdo:\n\n{fontes(base)}"


def estimar_tokens(texto: str) -> int:
    return int(len(texto) / CHARS_POR_TOKEN)


def ler_arquivos(base: Path, caminhos: list[str]) -> str:
    """Conteúdo dos caminhos pedidos, relativos à raiz do repositório."""
    blocos = []
    for relativo in caminhos:
        caminho = base / relativo
        if not caminho.exists():
            blocos.append(f"### {relativo}\n(arquivo ainda não existe)")
            continue
        blocos.append(f"### {relativo}\n```\n{caminho.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(blocos)


# --------------------------------------------------------------------------- #
# Contexto da execução: o roteiro manda, o resto é só caminho
# --------------------------------------------------------------------------- #


def _existe(base: Path, relativo: str) -> bool:
    return (base / relativo).is_file()


def _resolver_ts(base: Path, origem: str, especificador: str) -> str | None:
    """`@/lib/user` ou `./SuggestModal`, a partir de `origem`, → caminho real."""
    alvo = alvo_de(origem)
    if alvo is None:
        return None
    if especificador.startswith("@/"):
        bruto = f"{alvo}/{especificador[2:]}"
    elif especificador.startswith("."):
        bruto = posixpath.join(posixpath.dirname(origem), especificador)
    else:
        return None  # pacote do node_modules
    normal = normalizar(bruto)
    if normal is None or alvo_de(normal) != alvo:
        return None
    for sufixo in SUFIXOS_TS:
        if _existe(base, normal + sufixo):
            return normal + sufixo
    return None


def _resolver_py(base: Path, origem: str, modulo: str, nomes: str) -> list[str]:
    """`from app.x import y` → `client-backend/app/x.py` (ou `y.py`, se for módulo)."""
    alvo = alvo_de(origem)
    if alvo is None:
        return []
    if modulo.startswith("."):
        pontos = len(modulo) - len(modulo.lstrip("."))
        pasta = posixpath.dirname(origem)
        for _ in range(pontos - 1):
            pasta = posixpath.dirname(pasta)
        resto = modulo.lstrip(".")
        prefixo = posixpath.join(pasta, *resto.split(".")) if resto else pasta
    else:
        if modulo.split(".")[0] not in PACOTES_LOCAIS:
            return []
        prefixo = posixpath.join(alvo, *modulo.split("."))

    achados = []
    for candidato in (f"{prefixo}.py", f"{prefixo}/__init__.py"):
        if _existe(base, candidato):
            achados.append(candidato)
            break
    # `from app import models` importa o módulo `app/models.py`.
    for nome in re.findall(r"\w+", nomes or ""):
        if _existe(base, f"{prefixo}/{nome}.py"):
            achados.append(f"{prefixo}/{nome}.py")
    return achados


def importacoes_diretas(base: Path, relativo: str) -> list[str]:
    """Arquivos locais que `relativo` importa diretamente - um salto, não o grafo."""
    caminho = base / relativo
    if not caminho.is_file():
        return []
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    achados: list[str] = []

    if relativo.endswith((".ts", ".tsx", ".mjs", ".js")):
        for especificador in IMPORT_TS.findall(texto):
            resolvido = _resolver_ts(base, relativo, especificador)
            if resolvido:
                achados.append(resolvido)
    elif relativo.endswith(".py"):
        for modulo, nomes in FROM_PY.findall(texto):
            achados.extend(_resolver_py(base, relativo, modulo, nomes))
        for modulo in IMPORT_PY.findall(texto):
            achados.extend(_resolver_py(base, relativo, modulo, ""))

    return [a for a in dict.fromkeys(achados) if a != relativo]


def _infra_de_teste(base: Path, alvo: str) -> list[str]:
    achados = []
    for padrao in INFRA_DE_TESTE.get(alvo, ()):
        for caminho in sorted((base / alvo).glob(padrao)):
            if caminho.is_file():
                achados.append(caminho.relative_to(base).as_posix())
    return achados


def _testes_que_importam(base: Path, alvo: str, previstos: set[str]) -> list[str]:
    """Testes do alvo que importam algum arquivo previsto: são eles que vão quebrar."""
    raiz = base / alvo
    if not raiz.exists():
        return []
    achados = []
    for caminho in _arquivos(raiz):
        relativo = caminho.relative_to(base).as_posix()
        if not e_arquivo_de_teste(relativo) or relativo in previstos:
            continue
        if previstos & set(importacoes_diretas(base, relativo)):
            achados.append(relativo)
    return achados


def arquivos_em_foco(base: Path, previstos: list[str], extras: list[str] = ()) -> list[str]:
    """Os caminhos cujo conteúdo integral vai para o P5, em ordem estável.

    Previstos e extras (o que já foi escrito na run, ou o que o modelo pediu
    para ler), suas importações diretas, os companheiros de estilo, os testes
    que importam os previstos e a infraestrutura de teste dos alvos envolvidos.
    """
    nucleo = [n for c in [*previstos, *extras] if (n := normalizar(c)) and alvo_de(n)]
    foco: dict[str, None] = dict.fromkeys(nucleo)

    for caminho in nucleo:
        for importado in importacoes_diretas(base, caminho):
            foco.setdefault(importado)
        for companheiro in COMPANHEIROS.get(caminho, ()):
            if _existe(base, companheiro):
                foco.setdefault(companheiro)

    alvos = sorted({alvo_de(c) for c in nucleo}) or list(ALVOS)
    for alvo in alvos:
        for teste in _testes_que_importam(base, alvo, set(nucleo)):
            foco.setdefault(teste)
        for infra in _infra_de_teste(base, alvo):
            foco.setdefault(infra)

    return list(foco)


def contexto_da_execucao(
    base: Path, previstos: list[str], extras: list[str] = ()
) -> tuple[str, set[str]]:
    """Bloco de código do P5 e o conjunto de arquivos **existentes** que ele mostrou.

    O conjunto volta para o Executor: é a régua de "o modelo viu este arquivo
    antes de reescrevê-lo".
    """
    foco = arquivos_em_foco(base, previstos, extras)
    mostrados: set[str] = set()
    blocos = []
    for relativo in foco:
        aviso = "" if dentro_da_fronteira(relativo) else "  [SOMENTE LEITURA - não editar]"
        caminho = base / relativo
        if not caminho.is_file():
            blocos.append(f"### {relativo}\n(arquivo ainda não existe)")
            continue
        mostrados.add(relativo)
        conteudo = caminho.read_text(encoding="utf-8", errors="replace")
        blocos.append(f"### {relativo}{aviso}\n```\n{conteudo}\n```")

    texto = (
        "Todos os caminhos dos alvos (só o caminho; o conteúdo dos relevantes vem abaixo):\n"
        f"{arvore(base)}\n\n"
        "Conteúdo dos arquivos em foco - os previstos, o que eles importam, os testes "
        "que os exercitam e a infraestrutura de teste:\n\n" + "\n\n".join(blocos)
    )
    return texto, mostrados
