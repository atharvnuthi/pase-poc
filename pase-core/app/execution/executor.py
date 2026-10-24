"""O Executor: uma run de escrita de código (SPEC-04 §6).

Garantias estruturais que este módulo implementa:

- **Isolamento** (SPEC-00 §7): todo trabalho acontece num clone em `/tmp`, numa
  branch `pase/task-{id}`. Nada entra na branch principal aqui - só a
  Homologação faz merge, e só com aprovação humana explícita.
- **Verificação antes do humano** (SPEC-00 §5): lint e testes rodam sobre o
  código gerado. O humano revisa o que já passou pela máquina.
- **Contenção** (SPEC-00 §4): teto de tokens verificado antes de cada chamada e
  teto de tentativas no ciclo de correção. Nenhum loop roda indefinidamente.
- **Rastreabilidade** (SPEC-00 §2): diff, log de lint/teste e transcript viram
  arquivos, e a run guarda o caminho de cada um. O transcript traz a conversa
  inteira: o planejamento (P4), cada rodada do P5 e a revisão (P12) crua.
- **Fronteira de escrita** (SPEC-11 §4): todo caminho pedido pelo modelo é
  normalizado e conferido antes de qualquer escrita ou exclusão.
- **Ambiente sem credenciais** (SPEC-04 §4.5.2): todo subprocesso que roda código
  gerado recebe um ambiente limpo - ver `ambiente_isolado`.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import conventions, git_service, prompts
from app.common.config import settings
from app.common.llm_client import chat as llm_chat
from app.execution import context, review
from app.execution.budget import BudgetExcedidoError, BudgetGuard, gasto_da_task, teto_de
from app.orchestration.models import ExecutionRun, PlanningDocument
from app.task_layer.models import Task

logger = logging.getLogger("pase.execution")

SCHEMA_P5 = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
        # Opcionais: arquivos a apagar (o plano os marca `excluir`) e arquivos
        # existentes cujo conteúdo o modelo precisa ver antes de reescrever.
        "excluir": {"type": "array", "items": {"type": "string"}},
        "ler": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["files"],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}

#: Tempo máximo para lint e testes do alvo. Suíte pequena; mais que isto é travamento.
TIMEOUT_VERIFICACAO = 180

#: `next build` compila o app inteiro e é legitimamente mais lento que o resto.
TIMEOUT_BUILD = 420

#: Nomes de caso de teste, para inventariar a rede de regressão de cada alvo.
NOME_DE_TESTE = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.MULTILINE)
NOME_DE_CASO_TS = re.compile(
    r"""^\s*(?:it|test)(?:\.each\([\s\S]*?\))?\(\s*["'`](.+?)["'`]""", re.MULTILINE
)

#: Asserções, para medir se a rede foi enfraquecida sem que um teste sumisse.
ASSERCAO_PY = re.compile(r"\bassert\b|\.raises\s*\(")
ASSERCAO_TS = re.compile(r"\bexpect\s*\(")

#: Endereço para onde vai todo proxy do ambiente isolado: porta 9 (discard) no
#: loopback, onde nada escuta. Cliente HTTP que respeita proxy falha na hora.
BURACO_NEGRO = "http://127.0.0.1:9"

#: Variáveis que nunca chegam ao código gerado, por nome. Credencial e endereço
#: de serviço: o que o Executor escreve roda sem saber onde está o banco do
#: PASE, o repositório de verdade ou a chave do provedor.
SEGREDO = re.compile(r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE", re.IGNORECASE)
PREFIXOS_PROIBIDOS = (
    "LLM_",
    "OPENAI",
    "ANTHROPIC",
    "EMBEDDING_",
    "GITHUB_",
    "GH_",
    "GIT_",
    "DATABASE",
    "POSTGRES",
    "PG",
    "AWS_",
    "AZURE_",
    "GOOGLE_",
)
SUFIXOS_PROIBIDOS = ("_URL", "_URI", "_DSN", "_HOST", "_PROXY")
NOMES_PROIBIDOS = {"REPO_PATH", "FRONTEND_NODE_MODULES"}

#: O que o ambiente isolado acrescenta: rede só pelo buraco negro, npm sem
#: registro, pip sem índice, Next sem telemetria.
AMBIENTE_FECHADO = {
    **dict.fromkeys(("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"), BURACO_NEGRO),
    **dict.fromkeys(("http_proxy", "https_proxy", "all_proxy"), BURACO_NEGRO),
    "NO_PROXY": "",
    "no_proxy": "",
    # O Node da imagem passa a respeitar os proxies acima também no `fetch`
    # nativo. O recurso é experimental e imprime um aviso por processo - dezenas
    # por `next build` -, que soterraria o log que volta para o modelo.
    "NODE_USE_ENV_PROXY": "1",
    "NODE_NO_WARNINGS": "1",
    "npm_config_offline": "true",
    "NEXT_TELEMETRY_DISABLED": "1",
    "PIP_NO_INDEX": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


class FalhaControladaError(RuntimeError):
    """Falha injetada pelo modo demo (`demo_force_fail_runs`), para o D6(a)."""


@dataclass
class Resultado:
    status: str  # sucesso | falha | interrompida_budget
    failure_reason: str | None = None
    deviation_files: list[str] = field(default_factory=list)
    tokens_real: int = 0
    duration_ms: int = 0
    diff_path: str | None = None
    log_path: str | None = None
    transcript_path: str | None = None
    review_path: str | None = None


class Transcript:
    """Registro de tudo que a run trocou com o modelo, em JSONL.

    Cada linha carrega o `trace_id` da chamada, que liga o transcript à linha
    correspondente em `llm_calls` - com modelo, tokens e custo.
    """

    def __init__(self, destino: Path) -> None:
        self.destino = destino
        self.linhas: list[dict] = []

    def registrar(self, papel: str, conteudo: str, **extra) -> None:
        self.linhas.append({"role": papel, "content": conteudo, **extra})

    def incorporar(self, origem: str | None, **marca) -> None:
        """Traz para o início deste transcript as linhas de outro (o do plano).

        O pacote de homologação promete o histórico completo da interação com o
        modelo. O planejamento acontece antes e uma vez só; cada run o carrega
        junto, para que quem homologa leia numa peça só do P4 ao P12.
        """
        if not origem or not Path(origem).is_file():
            return
        for bruta in Path(origem).read_text(encoding="utf-8").splitlines():
            if not bruta.strip():
                continue
            try:
                linha = json.loads(bruta)
            except json.JSONDecodeError:
                continue
            self.linhas.append({**linha, **marca})

    def salvar(self) -> str:
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        with self.destino.open("w", encoding="utf-8") as arquivo:
            for linha in self.linhas:
                arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
        return str(self.destino)


def pasta_de_artefatos(task_id: int, attempt: int) -> Path:
    return Path(settings.artifacts_path) / f"task-{task_id}" / f"run-{attempt}"


def ambiente_isolado(origem: dict[str, str] | None = None) -> dict[str, str]:
    """O ambiente de todo subprocesso que roda código gerado (SPEC-04 §4.5.2).

    Parte do ambiente do pase-core e **tira** o que não é dele: chaves do
    provedor, token do GitHub, URL do banco, caminho do repositório real e
    qualquer variável com cara de credencial. Depois **fecha** a saída de rede
    que as ferramentas respeitam: todo proxy aponta para um buraco negro, npm
    roda offline, pip sem índice, Next sem telemetria.

    O que isto **não** garante: um processo que abre socket direto, sem passar
    por proxy, ainda alcança a rede do container. Isolamento de rede de verdade
    é um container efêmero sem rede, fora do escopo desta PoC. O que isto
    garante é que o código gerado não herda credencial nenhuma - não há o que
    vazar - e que as ferramentas da verificação não baixam nada.
    """
    base = dict(os.environ if origem is None else origem)
    limpo = {
        nome: valor
        for nome, valor in base.items()
        if nome not in NOMES_PROIBIDOS
        and not SEGREDO.search(nome)
        and not nome.upper().startswith(PREFIXOS_PROIBIDOS)
        and not nome.upper().endswith(SUFIXOS_PROIBIDOS)
    }
    return {**limpo, **AMBIENTE_FECHADO}


def _rodar(comando: list[str], cwd: Path, *, timeout: int = TIMEOUT_VERIFICACAO) -> tuple[int, str]:
    """Roda um comando de verificação e devolve (código de saída, saída combinada).

    Sempre com `ambiente_isolado()`: todo comando daqui executa ou analisa código
    que o modelo escreveu.
    """
    try:
        processo = subprocess.run(
            comando,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=ambiente_isolado(),
        )
        return processo.returncode, (processo.stdout or "") + (processo.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT: {' '.join(comando)} passou de {timeout}s"
    except FileNotFoundError as exc:
        return 1, f"comando não encontrado: {exc}"


def _linguagem_de_teste(caminho: str) -> str | None:
    """`py` ou `ts` se o caminho é um arquivo de casos de teste; senão `None`."""
    nome = caminho.replace("\\", "/").rsplit("/", 1)[-1]
    if nome.startswith("test_") and nome.endswith(".py"):
        return "py"
    if nome.endswith((".test.tsx", ".test.ts")):
        return "ts"
    return None


def _nomes_no_texto(alvo: str, caminho: str, texto: str) -> set[str]:
    """Nomes de teste de um arquivo, ou nada se o caminho não é arquivo de teste."""
    linguagem = _linguagem_de_teste(caminho)
    if linguagem == "py":
        return {f"{alvo}:{n}" for n in NOME_DE_TESTE.findall(texto)}
    if linguagem == "ts":
        return {f"{alvo}:{n}" for n in NOME_DE_CASO_TS.findall(texto)}
    return set()


def _textos_de_teste_no_disco(workspace_path: Path) -> list[tuple[str, str, str]]:
    """(alvo, caminho, texto) de cada arquivo de teste dos alvos, lido do disco."""
    achados = []
    for alvo in context.ALVOS:
        raiz = workspace_path / alvo
        if not raiz.exists():
            continue
        for arquivo in sorted(raiz.rglob("*")):
            relativo = arquivo.relative_to(workspace_path).as_posix()
            if (
                not arquivo.is_file()
                or any(parte in context.IGNORAR for parte in arquivo.parts)
                or not _linguagem_de_teste(relativo)
            ):
                continue
            achados.append((alvo, relativo, arquivo.read_text(encoding="utf-8", errors="replace")))
    return achados


def _textos_de_teste_da_base(workspace: git_service.Workspace) -> list[tuple[str, str, str]]:
    """(alvo, caminho, texto) de cada arquivo de teste dos alvos na branch principal."""
    repo = workspace.repo
    base = f"origin/{git_service.main_branch(repo)}"
    achados = []
    for caminho in repo.git.ls_tree("-r", "--name-only", base).splitlines():
        alvo = context.alvo_de(caminho)
        if not alvo or not _linguagem_de_teste(caminho):
            continue
        achados.append((alvo, caminho, repo.git.show(f"{base}:{caminho}")))
    return achados


def inventario_de_testes(workspace_path: Path) -> set[str]:
    """Nomes de todos os testes dos alvos neste momento, lidos do disco.

    Cobre Python (`def test_*`) e TypeScript (`it(...)` / `test(...)`, em
    `.test.tsx` e `.test.ts`): a rede de regressão do frontend entrou no SPEC-11
    e precisa da mesma proteção que a do backend.
    """
    nomes: set[str] = set()
    for alvo, caminho, texto in _textos_de_teste_no_disco(workspace_path):
        nomes |= _nomes_no_texto(alvo, caminho, texto)
    return nomes


def inventario_da_base(workspace: git_service.Workspace) -> set[str]:
    """O "antes" dos testes: o que está na branch principal, lido do git.

    Ler do disco do clone não serve. Numa segunda tentativa o clone é reaproveitado
    e ainda carrega os testes escritos pela tentativa que falhou; o inventário
    "antes" já os continha e nenhum teste novo podia contar como novo. Foi o que
    reprovou, quatro rodadas seguidas, uma entrega que trazia três testes novos.
    A régua é o que está na principal - nunca o que sobrou no disco.
    """
    nomes: set[str] = set()
    for alvo, caminho, texto in _textos_de_teste_da_base(workspace):
        nomes |= _nomes_no_texto(alvo, caminho, texto)
    return nomes


# --------------------------------------------------------------------------- #
# Asserções: a rede pode ser enfraquecida sem perder um único nome
# --------------------------------------------------------------------------- #


def _e_assercao(no: ast.AST) -> bool:
    """`assert`, `pytest.raises(...)` ou chamada `assert*` (estilo unittest)."""
    if isinstance(no, ast.Assert):
        return True
    if isinstance(no, ast.Call):
        funcao = no.func
        nome = (
            funcao.attr
            if isinstance(funcao, ast.Attribute)
            else funcao.id
            if isinstance(funcao, ast.Name)
            else ""
        )
        return nome == "raises" or nome.startswith("assert")
    return False


def _por_trecho(texto: str, inicio: re.Pattern, assercao: re.Pattern) -> dict[str, int]:
    """Asserções por caso, cortando o texto no começo de cada caso.

    Aproximação de propósito: sem um parser de TypeScript, o corpo de um caso é
    tudo até o caso seguinte. A régua é a mesma antes e depois, que é o que
    importa para comparar.
    """
    marcas = list(inicio.finditer(texto))
    contagem: dict[str, int] = {}
    for i, marca in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        nome = marca.group(1)
        contagem[nome] = contagem.get(nome, 0) + len(assercao.findall(texto[marca.start() : fim]))
    return contagem


def _assercoes_do_arquivo(caminho: str, texto: str) -> tuple[dict[str, int], int]:
    """(asserções por caso, total do arquivo - helpers incluídos)."""
    if _linguagem_de_teste(caminho) == "ts":
        return _por_trecho(texto, NOME_DE_CASO_TS, ASSERCAO_TS), len(ASSERCAO_TS.findall(texto))

    try:
        modulo = ast.parse(texto)
    except SyntaxError:
        # Arquivo que nem compila: o pytest vai reprovar de qualquer jeito, e a
        # contagem por texto mantém a comparação possível até lá.
        return _por_trecho(texto, NOME_DE_TESTE, ASSERCAO_PY), len(ASSERCAO_PY.findall(texto))

    por_caso: dict[str, int] = {}
    for no in ast.walk(modulo):
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef) and no.name.startswith("test_"):
            n = sum(1 for filho in ast.walk(no) if _e_assercao(filho))
            por_caso[no.name] = por_caso.get(no.name, 0) + n
    total = sum(1 for no in ast.walk(modulo) if _e_assercao(no))
    return por_caso, total


def _contar_assercoes(textos: list[tuple[str, str, str]]) -> dict[str, int]:
    """`alvo:caso` → asserções, e `alvo:*` → total do alvo.

    A chave por caso ignora o arquivo, como o inventário de nomes: mover um teste
    de arquivo não é enfraquecê-lo. O total do alvo pega o que a chave por caso
    não vê - a asserção apagada de dentro de um helper que vários testes usam.
    """
    contagem: dict[str, int] = {}
    for alvo, caminho, texto in textos:
        por_caso, total = _assercoes_do_arquivo(caminho, texto)
        for nome, n in por_caso.items():
            chave = f"{alvo}:{nome}"
            contagem[chave] = contagem.get(chave, 0) + n
        contagem[f"{alvo}:*"] = contagem.get(f"{alvo}:*", 0) + total
    return contagem


def assercoes_no_disco(workspace_path: Path) -> dict[str, int]:
    return _contar_assercoes(_textos_de_teste_no_disco(workspace_path))


def assercoes_da_base(workspace: git_service.Workspace) -> dict[str, int]:
    """O "antes" das asserções, da branch principal - pelo mesmo motivo do inventário."""
    return _contar_assercoes(_textos_de_teste_da_base(workspace))


#: Começo das mensagens de recusa determinística: o feedback ao modelo as
#: apresenta como recusa, não como saída de lint ou de teste.
RECUSA_REDE = "Você removeu ou renomeou testes"
RECUSA_ASSERCOES = "Você reduziu as asserções"
RECUSA_FRONTEIRA = "Você escreveu em arquivos que estão fora do seu alcance"
RECUSA_AS_CEGAS = "Você reescreveu arquivos cujo conteúdo não recebeu"


def assercoes_preservadas(antes: dict[str, int], depois: dict[str, int]) -> tuple[bool, str]:
    """Nenhum teste que já existia afirma menos do que afirmava? (SPEC-04 §4.5.2)

    O inventário de nomes não vê um teste esvaziado: `def test_somar(): pass`
    mantém o nome e deixa de proteger qualquer coisa. Contar asserções por caso e
    por alvo fecha essa porta. É contagem, não semântica: trocar `== 6` por
    `is not None` mantém o número - esse caso fica com a revisão independente,
    que é instruída a reprovar asserção existente que passa a afirmar outra coisa.

    Caso que sumiu não é tratado aqui - `rede_de_regressao_intacta` já o recusa.
    """
    quedas = []
    for chave, anterior in sorted(antes.items()):
        atual = depois.get(chave)
        if atual is None or atual >= anterior:
            continue
        alvo, _, caso = chave.partition(":")
        rotulo = f"total de asserções de {alvo}" if caso == "*" else chave
        quedas.append(f"{rotulo} ({anterior} → {atual})")

    if not quedas:
        return True, ""
    return False, (
        f"{RECUSA_ASSERCOES} de testes que já existiam: "
        + "; ".join(quedas)
        + ". Uma asserção removida enfraquece a rede de regressão tanto quanto um teste "
        "apagado. Restaure as asserções que existiam - se o comportamento mudou, ajuste "
        "o que elas afirmam sem reduzir quantas são - e acrescente as suas em casos novos."
    )


def rede_de_regressao_intacta(antes: set[str], depois: set[str]) -> tuple[bool, str]:
    """A suíte que já existia continua de pé?

    Isto é um hook determinístico, não um pedido ao modelo - e a diferença foi
    medida: mesmo com o P5 dizendo em letras maiúsculas para não alterar os
    testes existentes, a primeira execução real **sobrescreveu** o teste de
    tickets com um teste de CSV. A verificação passou, porque rodou a suíte já
    adulterada.

    Uma rede de regressão que o Executor pode reescrever não é uma rede de
    regressão: ela deixa de ser a régua e vira parte do que está sendo medido.
    """
    sumidos = sorted(antes - depois)
    if not sumidos:
        return True, ""
    return False, (
        "Você removeu ou renomeou testes que já existiam: "
        + ", ".join(sumidos)
        + ". Esses testes são a rede de regressão do projeto e precisam continuar "
        "existindo com o mesmo nome. Restaure-os exatamente como estavam e "
        "acrescente os seus testes novos em funções separadas."
    )


#: Extensões que contam como código de produção para o gate de testes. CSS, JSON
#: e markdown mudam sem que exista comportamento novo a testar.
EXTENSOES_DE_CODIGO = {".py", ".ts", ".tsx"}


_e_arquivo_de_teste = context.e_arquivo_de_teste


def testes_cresceram(
    tocados: list[str], antes: set[str], depois: set[str]
) -> tuple[bool, str]:
    """Comportamento novo veio com teste novo?

    O P5 pede isto por escrito desde sempre - *"acrescente testes novos para o
    comportamento novo"* - e nada verificava. Pedir ao modelo já se provou
    insuficiente cinco vezes neste projeto; o que funciona é conferir por código.

    A regra: se a entrega mexeu em código de produção, o inventário de testes tem
    de crescer. Mudança só em CSS, markdown ou configuração não exige teste, por
    isso o filtro por extensão.
    """
    producao = [
        c
        for c in tocados
        if not _e_arquivo_de_teste(c)
        and any(c.endswith(ext) for ext in EXTENSOES_DE_CODIGO)
    ]
    if not producao:
        return True, ""

    novos = depois - antes
    if novos:
        return True, ""

    return False, (
        "Você mudou código de produção sem acrescentar nenhum teste: "
        + ", ".join(sorted(producao))
        + ". Todo comportamento novo precisa de um teste que o exercite - é o que "
        "permite que a próxima mudança seja feita com segurança, e é o que esta "
        "verificação exige antes de deixar a entrega seguir. Acrescente pelo menos "
        "um caso de teste novo, em função separada, sem alterar os que já existem."
    )


#: Queda de cobertura tolerada, em pontos percentuais. Não é zero porque o
#: relatório oscila em uma linha ou outra entre execuções (ordem de importação,
#: branch de tratamento de erro que só roda às vezes) e reprovar por meio ponto
#: transformaria o gate em ruído.
TOLERANCIA_DE_COBERTURA = 2.0


@contextmanager
def _node_modules_emprestado(raiz: Path) -> Iterator[None]:
    """`node_modules` da imagem ligado por symlink enquanto durar o bloco.

    Instalar no clone somaria cerca de 40s e uma dependência de rede a cada
    execução. O symlink é **desfeito no fim**, sempre: o `.gitignore` já trouxe
    `node_modules/`, com barra, que casa só com diretório - um symlink é um blob
    (modo 120000), escapa do padrão, e o link entrou num diff que foi para a
    Homologação. Ferramenta da verificação não pode virar entrega.
    """
    modulos = raiz / "node_modules"
    origem = Path(os.getenv("FRONTEND_NODE_MODULES", "/opt/frontend/node_modules"))
    emprestado = False
    if not modulos.exists() and origem.exists():
        modulos.symlink_to(origem, target_is_directory=True)
        emprestado = True
    try:
        yield
    finally:
        if emprestado:
            modulos.unlink(missing_ok=True)


def cobertura_do_frontend(raiz: Path) -> dict[str, float]:
    """Cobertura por arquivo do alvo TypeScript, via `vitest --coverage`.

    Mesma regra do backend: devolve vazio quando não dá para medir, porque um
    gate que não conseguiu medir não pode reprovar ninguém.

    Precisa do `node_modules` emprestado tanto quanto o gate. Sem ele - era o
    caso: a medição do "antes" roda num clone recém-feito, antes de o gate criar
    o symlink - o vitest nem sobe, a medição volta vazia e o gate de cobertura
    do frontend se calava em toda execução.
    """
    destino = raiz / "coverage" / "coverage-final.json"
    try:
        with _node_modules_emprestado(raiz):
            codigo, _ = _rodar(
                [
                    "npx",
                    "vitest",
                    "run",
                    "--coverage",
                    "--coverage.reporter=json",
                    "--reporter=basic",
                ],
                raiz,
            )
        if codigo != 0 or not destino.exists():
            return {}
        try:
            dados = json.loads(destino.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    finally:
        # Artefato de verificação não vira entrega - a lição do `.coverage` e do
        # symlink de `node_modules`.
        shutil.rmtree(raiz / "coverage", ignore_errors=True)

    # Formato do istanbul: caminho absoluto e contagem por instrução (`s`).
    medido: dict[str, float] = {}
    base = f"{raiz}/"
    for caminho, info in dados.items():
        contagens = list((info.get("s") or {}).values())
        if not contagens:
            continue
        relativo = caminho.replace("\\", "/").removeprefix(base)
        medido[relativo] = 100.0 * sum(1 for n in contagens if n > 0) / len(contagens)
    return medido


def cobertura_por_arquivo(raiz: Path) -> dict[str, float]:
    """Percentual de linhas cobertas por arquivo do alvo.

    Devolve vazio quando não dá para medir - alvo sem pytest, suíte que não roda,
    relatório ilegível. Um gate que não conseguiu medir não pode reprovar
    ninguém: ele se cala e deixa os outros trabalharem.
    """
    destino = raiz / ".coverage.json"
    try:
        codigo, _ = _rodar(
            [
                "pytest",
                "-q",
                "--no-header",
                "--cov=app",
                f"--cov-report=json:{destino.name}",
                "--cov-report=",
            ],
            raiz,
        )
        if not destino.exists():
            return {}
        try:
            dados = json.loads(destino.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    finally:
        # Os dois arquivos que o pytest-cov deixa para trás. Sem esta limpeza
        # eles entram no commit da run e aparecem como desvio do plano -
        # ferramenta da verificação não pode virar entrega (a mesma lição do
        # symlink de `node_modules`).
        destino.unlink(missing_ok=True)
        (raiz / ".coverage").unlink(missing_ok=True)

    if codigo != 0:
        # Suíte vermelha mede cobertura de um código que nem passa; o gate de
        # testes já reprova esse caso, e comparar números aqui seria enganoso.
        return {}

    return {
        arquivo: float(info["summary"]["percent_covered"])
        for arquivo, info in dados.get("files", {}).items()
    }


def cobertura_nao_caiu(
    alvo: str, tocados: list[str], antes: dict[str, float], depois: dict[str, float]
) -> tuple[bool, str]:
    """Os arquivos que a entrega mexeu continuam tão cobertos quanto eram?

    Este gate existe por causa do anterior. Exigir "acrescente um teste" sem
    olhar o que o teste exercita convida à resposta mais barata: um caso trivial
    que passa sempre e não toca no código novo. Comparar a cobertura de cada
    arquivo alterado com a de antes fecha essa saída.

    A comparação é por arquivo, e só dos arquivos tocados. Cobertura global
    subiria ou cairia por motivos alheios à entrega, e cobrar o total faria a
    tarefa de hoje pagar pela dívida de ontem.
    """
    prefixo = f"{alvo}/"
    quedas = []

    for caminho in tocados:
        if not caminho.startswith(prefixo) or _e_arquivo_de_teste(caminho):
            continue
        relativo = caminho[len(prefixo) :]
        if relativo not in depois:
            continue

        anterior = antes.get(relativo)
        if anterior is None:
            continue  # arquivo novo: não há com o que comparar

        atual = depois[relativo]
        if atual < anterior - TOLERANCIA_DE_COBERTURA:
            quedas.append(f"{caminho} ({anterior:.0f}% → {atual:.0f}%)")

    if not quedas:
        return True, ""

    return False, (
        "A cobertura de testes caiu nos arquivos que você alterou: "
        + "; ".join(quedas)
        + ". O código novo precisa ser exercitado pelos testes, não apenas "
        "acompanhado por eles. Acrescente casos que passem pelos caminhos que "
        "você escreveu."
    )


def foi_cancelada(task_id: int) -> bool:
    """Alguém pediu para parar esta run enquanto ela rodava?

    Lido numa **conexão própria**, não na sessão da run: a transição para
    `suspensa` é commitada por outra requisição, e a sessão longa da execução
    continuaria enxergando o estado de quando começou.

    O cancelamento é cooperativo por escolha. Matar o processo no meio deixaria
    o clone pela metade e um custo de LLM já gasto sem registro; parar antes da
    próxima chamada custa, no pior caso, a chamada que já estava em curso.
    """
    from app.common.db import session_scope

    try:
        with session_scope() as sessao:
            status = sessao.execute(
                select(Task.status).where(Task.id == task_id)
            ).scalar_one_or_none()
    except Exception as exc:  # banco fora do ar não pode derrubar a run
        logger.warning("não consegui checar cancelamento da task #%s: %s", task_id, exc)
        return False

    return status is not None and status != "em_execucao"


def fronteira_respeitada(tocados: list[str]) -> tuple[bool, str]:
    """Todo caminho pedido está dentro do alcance do Executor? (SPEC-11 §4)

    Hook determinístico, não recomendação, conferido **antes** de qualquer
    escrita ou exclusão. Cada caminho é normalizado primeiro: `./`, `..` e
    caminho absoluto não driblam a régua - um caminho absoluto chegou a escrever
    fora do clone antes desta normalização. Só os dois alvos são graváveis, e
    dentro deles `dynamic-zones/`, que contém a validação que recusa payload
    malicioso de Zona Dinâmica - a garantia do SPEC-00 §6, declarada sem exceção.
    Ela não pode depender do julgamento do modelo que ela limita, nem de o modelo
    ter lido o aviso no prompt.
    """
    invadidos = sorted(
        f"{c} ({motivo})" for c in tocados if (motivo := context.motivo_de_bloqueio(c))
    )
    if not invadidos:
        return True, ""
    return False, (
        f"{RECUSA_FRONTEIRA}: "
        + ", ".join(invadidos)
        + ". Você só escreve dentro de `client-backend/` e `client-frontend/`, com caminhos "
        "relativos à raiz do repositório. A pasta `client-frontend/dynamic-zones/` é "
        "somente leitura: ela contém a validação que protege o usuário de payloads "
        "maliciosos, e só um humano a altera. Refaça a entrega sem tocar nesses arquivos."
    )


def aviso_as_cegas(caminhos: list[str]) -> str:
    return (
        f"{RECUSA_AS_CEGAS}: "
        + ", ".join(caminhos)
        + ". Cada arquivo devolvido substitui o existente por inteiro, e reescrever um "
        "arquivo sem tê-lo lido apaga o que estava lá. O conteúdo atual deles agora está "
        "no contexto acima: devolva a entrega de novo a partir dele."
    )


#: Sobe a aplicação em memória e bate na rota de saúde. Sem servidor e sem porta:
#: o TestClient exercita o mesmo caminho de inicialização do uvicorn.
SMOKE_DO_BACKEND = (
    "from fastapi.testclient import TestClient; "
    "from app.main import app; "
    "r = TestClient(app).get('/health'); "
    "assert r.status_code == 200, f'/health respondeu {r.status_code}'; "
    "print('smoke ok:', r.status_code)"
)


def _resumir_build(saida: str) -> str:
    """O essencial do `next build`, para o log da run continuar legível.

    Numa compilação bem-sucedida o Next imprime a tabela de todas as rotas com
    seus tamanhos - dezenas de linhas que não dizem nada a quem revisa. Numa
    falha, o que importa está nas linhas de erro. Guardamos o fim da saída, que
    é onde os dois casos se resolvem.
    """
    linhas = [linha for linha in saida.splitlines() if linha.strip()]
    if len(linhas) <= 40:
        return "\n".join(linhas)
    return "[…]\n" + "\n".join(linhas[-40:])


def _gate_do_backend(raiz: Path) -> tuple[bool, str]:
    partes = []

    # Corrigível pelo formatador é corrigido pelo formatador (ver CLAUDE.md).
    codigo_fix, saida_fix = _rodar(["ruff", "check", "--fix", "."], raiz)
    partes.append(f"$ ruff check --fix .\n{saida_fix}\n(exit {codigo_fix})")

    codigo_lint, saida_lint = _rodar(["ruff", "check", "."], raiz)
    partes.append(f"\n$ ruff check .\n{saida_lint}\n(exit {codigo_lint})")

    codigo_teste, saida_teste = _rodar(["pytest", "-q", "--no-header"], raiz)
    partes.append(f"\n$ pytest -q\n{saida_teste}\n(exit {codigo_teste})")

    # Compilar não é o mesmo que iniciar: uma rota com import quebrado passa no
    # lint, passa nos testes que não a importam, e derruba o app no boot.
    #
    # Só roda onde há um app para subir. Reprovar por ausência de `app/main.py`
    # seria falso negativo - e um alvo que perdesse o seu `main` já quebraria nos
    # testes que o importam, bem antes de chegar aqui.
    codigo_smoke = 0
    if (raiz / "app" / "main.py").exists():
        codigo_smoke, saida_smoke = _rodar(["python", "-c", SMOKE_DO_BACKEND], raiz)
        partes.append(
            f"\n$ smoke (sobe o app e chama /health)\n{saida_smoke}\n(exit {codigo_smoke})"
        )

    return (codigo_lint == 0 and codigo_teste == 0 and codigo_smoke == 0), "\n".join(partes)


def _gate_do_frontend(raiz: Path) -> tuple[bool, str]:
    """Compilação, checagem de tipos e testes de comportamento (SPEC-11 §3).

    **`next build` é o gate que importa aqui**, e entrou depois de uma falha
    real. O `tsc` não conhece React Server Components - a fronteira
    `"use client"` é regra do compilador do Next, não do TypeScript - e o
    `vitest` renderiza as páginas direto no jsdom, sem passar pelo App Router,
    então nunca chega a renderizar `app/layout.tsx`. Uma entrega que punha
    `useState` no layout raiz passou por tsc e pelos 14 testes com exit 0 e
    quebrou o app inteiro na primeira vez que alguém o abriu. O `next dev` só
    compila a rota quando alguém a pede; o `next build` compila tudo de uma vez,
    e é o único dos três que reprova isso.

    O `node_modules` vem da imagem do pase-core, emprestado por symlink e
    devolvido no fim (ver `_node_modules_emprestado`).
    """
    partes = []
    try:
        with _node_modules_emprestado(raiz):
            codigo_tipos, saida_tipos = _rodar(["npx", "tsc", "--noEmit"], raiz)
            partes.append(f"$ tsc --noEmit\n{saida_tipos}\n(exit {codigo_tipos})")

            codigo_teste, saida_teste = _rodar(["npx", "vitest", "run", "--reporter=basic"], raiz)
            partes.append(f"\n$ vitest run\n{saida_teste}\n(exit {codigo_teste})")

            codigo_build, saida_build = _rodar(
                ["npx", "next", "build"], raiz, timeout=TIMEOUT_BUILD
            )
            partes.append(
                f"\n$ next build\n{_resumir_build(saida_build)}\n(exit {codigo_build})"
            )
    finally:
        # `.next/` é artefato de build, não entrega: sem isto ele entraria no
        # commit da run - o `.gitignore` traz `.next/`, mas o diretório de build
        # dentro do clone não tem por que sobreviver à verificação.
        shutil.rmtree(raiz / ".next", ignore_errors=True)

    passou = codigo_tipos == 0 and codigo_teste == 0 and codigo_build == 0
    return passou, "\n".join(partes)


#: Como se mede cobertura em cada alvo. Mesma ideia dos gates: a ferramenta
#: muda, a regra ("não pode cair no que você tocou") não.
MEDIDORES_DE_COBERTURA = {
    "client-backend": cobertura_por_arquivo,
    "client-frontend": cobertura_do_frontend,
}


#: Cada alvo tem o seu gate. Só o que mudou precisa ser verificado.
GATES = {
    "client-backend": _gate_do_backend,
    "client-frontend": _gate_do_frontend,
}


def verificar(workspace_path: Path, alvos: list[str] | None = None) -> tuple[bool, str]:
    """Roda o gate de cada alvo tocado, no clone (SPEC-00 §5, SPEC-11 §3).

    Sem `alvos`, verifica todos - é o que vale quando não se sabe o que mudou.
    """
    escolhidos = [a for a in (alvos or context.ALVOS) if a in GATES]
    passou_tudo = True
    partes = []

    for alvo in escolhidos:
        raiz = workspace_path / alvo
        if not raiz.exists():
            continue
        passou, log = GATES[alvo](raiz)
        passou_tudo = passou_tudo and passou
        partes.append(f"───── {alvo} ─────\n{log}")

    return passou_tudo, "\n\n".join(partes)


def _criterios_para_o_executor(plano: PlanningDocument) -> str:
    """Os critérios de aceite como o executor os lê.

    Ele recebe a mesma régua que o revisor vai aplicar. Esconder dele o critério
    e depois reprovar por não cumpri-lo seria gastar uma rodada à toa.
    """
    criterios = plano.acceptance_criteria or []
    return "\n".join(
        f"- **{c['id']}** - {c['criterio']}\n"
        f"  prove com: {c.get('como_verificar') or 'um teste que falharia sem isto'}"
        for c in criterios
    )


def _mensagem_de_feedback(
    log: str, comentario: str | None, refazer: str | None = None
) -> str:
    """Bloco `{{feedback}}` do P5: nada na primeira geração, saída do erro na correção.

    Cada origem tem o seu título. O modelo lê "a verificação falhou" como "procure
    no log do lint"; mandar um parecer de revisão com esse título faria ele caçar
    um erro de teste que não existe.
    """
    if comentario:
        return (
            "## Pedido do gestor\n\n"
            f"{comentario}\n\n"
            "Ajuste o código conforme o pedido acima."
        )
    if refazer:
        return (
            "## Por que a tentativa anterior desta tarefa não serviu\n\n"
            "Uma versão desta mesma tarefa já foi entregue e depois revertida. "
            "Quem a usou disse:\n\n"
            f"> {refazer}\n\n"
            "Você parte da branch principal, sem o código antigo. Não repita o erro."
        )
    if log.startswith(review.TITULO_DO_FEEDBACK):
        return f"## {log}"
    if log.startswith((RECUSA_REDE, RECUSA_ASSERCOES, RECUSA_FRONTEIRA, RECUSA_AS_CEGAS)):
        return f"## A entrega anterior foi recusada\n\n{log}"
    if log:
        return (
            "## A verificação anterior falhou\n\n"
            "Saída do lint e dos testes:\n\n"
            f"```\n{log[-6000:]}\n```\n\n"
            "Corrija o que está quebrado. Não altere testes que já passavam."
        )
    return ""


def _previstos_para_o_executor(plano: PlanningDocument) -> str:
    """O mapeamento de impacto do plano: cada caminho com a sua ação."""
    acoes = plano.file_actions or {}
    return "\n".join(
        f"- `{c}` - {acoes.get(c, 'modificar')}" for c in plano.affected_files or []
    )


#: Por que um plano sem critério de aceite não vira entrega (SPEC-04 §4.5.3).
SEM_CRITERIOS = (
    "o plano não tem critérios de aceite: sem eles a revisão independente não tem contra "
    "o que conferir a entrega, e nada segue para a Homologação sem essa revisão. "
    "Replaneje a tarefa, ou edite o plano acrescentando critérios, e execute de novo."
)


def executar(
    session: Session,
    task: Task,
    plano: PlanningDocument,
    *,
    attempt: int,
    trigger: str = "inicial",
    comentario: str | None = None,
) -> ExecutionRun:
    """Roda uma tentativa completa e persiste a `execution_runs` correspondente."""
    inicio = time.perf_counter()
    artefatos = pasta_de_artefatos(task.id, attempt)
    transcript = Transcript(artefatos / "transcript.jsonl")
    transcript.incorporar(plano.transcript_path, fase="planejamento")
    guard = BudgetGuard(
        teto=teto_de(task, plano.tokens_estimated),
        ja_gasto=gasto_da_task(session, task.id),
    )

    resultado = _executar(
        session,
        task,
        plano,
        guard,
        transcript,
        artefatos,
        comentario=comentario,
        # Replanejar significa recomeçar também o workspace a partir da branch
        # principal; retry e ajuste continuam reaproveitando o trabalho anterior.
        primeira=(attempt == 1 or trigger == "replanejamento"),
    )
    resultado.duration_ms = int((time.perf_counter() - inicio) * 1000)
    resultado.tokens_real = guard.gasto_na_run
    resultado.transcript_path = transcript.salvar()

    run = ExecutionRun(
        task_id=task.id,
        attempt=attempt,
        trigger=trigger,
        status=resultado.status,
        failure_reason=resultado.failure_reason,
        deviation_files=resultado.deviation_files,
        tokens_real=resultado.tokens_real,
        duration_ms=resultado.duration_ms,
        diff_path=resultado.diff_path,
        log_path=resultado.log_path,
        transcript_path=resultado.transcript_path,
        review_path=resultado.review_path,
    )
    session.add(run)
    session.flush()

    logger.info(
        "run #%s (task #%s, tentativa %s): %s em %dms, %d tokens",
        run.id,
        task.id,
        attempt,
        run.status,
        run.duration_ms,
        run.tokens_real,
    )
    return run


def _executar(
    session: Session,
    task: Task,
    plano: PlanningDocument,
    guard: BudgetGuard,
    transcript: Transcript,
    artefatos: Path,
    *,
    comentario: str | None,
    primeira: bool = True,
) -> Resultado:
    # Sem critério, a revisão independente não teria o que conferir e a entrega
    # passaria só pelos gates mecânicos - foi assim que um modo escuro sem cor
    # escura chegou a uma pessoa. Recusa antes de gastar o primeiro token.
    if not plano.acceptance_criteria:
        transcript.registrar("system", SEM_CRITERIOS, evento="plano_sem_criterios")
        return Resultado(status="falha", failure_reason=SEM_CRITERIOS)

    try:
        workspace = git_service.prepare_workspace(
            task.id, nova=primeira, titulo=task.title, tipo=task.change_type
        )
    except Exception as exc:
        return Resultado(status="falha", failure_reason=f"não consegui preparar o workspace: {exc}")

    task.branch_name = workspace.branch
    session.add(task)
    session.flush()

    log_verificacao = ""
    tocados: list[str] = []
    # Inventário e cobertura tirados do clone **intacto**, antes de qualquer
    # escrita: é a única leitura confiável do "antes", e é o que impede que a
    # régua seja medida já adulterada.
    testes_originais = inventario_da_base(workspace)
    assercoes_originais = assercoes_da_base(workspace)
    # Arquivos existentes cujo conteúdo o modelo pediu, ou tentou reescrever sem
    # ter recebido: entram no contexto das rodadas seguintes.
    extras: set[str] = set()
    cobertura_original = {
        alvo: medir(workspace.path / alvo)
        for alvo, medir in MEDIDORES_DE_COBERTURA.items()
        if (workspace.path / alvo).exists()
    }

    # O que uma pessoa pediu: ajuste na Homologação, ou o porquê de refazer uma
    # tarefa que não serviu. Vai para o executor na primeira rodada e para o
    # revisor em todas - senão o pedido seria ouvido uma vez e esquecido.
    pedido_humano = comentario or task.redo_feedback
    parecer: review.Parecer | None = None
    # Log dos gates da rodada que a revisão reprovou. O feedback ao modelo passa a
    # ser o parecer, mas o artefato salvo continua sendo o log de lint e teste,
    # que é o que o nome dele promete.
    log_dos_gates = ""

    # 1 geração + até MAX_LOCAL_FIX correções locais (SPEC-04 §6.6)
    for rodada in range(settings.max_local_fix + 1):
        feedback = _mensagem_de_feedback(
            log_verificacao,
            comentario if rodada == 0 else None,
            task.redo_feedback if rodada == 0 and not comentario else None,
        )
        # O roteiro é o insumo principal: o P5 recebe o conteúdo do que o plano
        # prevê (e do que já foi escrito nesta run), não uma nova varredura do
        # repositório (SPEC-04 §4.5.2). `mostrados` é a régua do "você viu este
        # arquivo antes de reescrevê-lo".
        codigo, mostrados = context.contexto_da_execucao(
            workspace.path, list(plano.affected_files or []), sorted(set(tocados) | extras)
        )
        mensagem = prompts.render(
            "P5",
            criterios=_criterios_para_o_executor(plano),
            roadmap=plano.roadmap,
            affected_files=_previstos_para_o_executor(plano),
            documentacao=prompts.load_documentacao("execucao"),
            codigo=codigo,
            feedback=feedback,
        )

        # Ponto de checagem do cancelamento: antes de gastar a próxima chamada.
        if foi_cancelada(task.id):
            transcript.registrar("system", "cancelada por decisão humana", evento="cancelada")
            return Resultado(
                status="falha",
                failure_reason="cancelada por decisão humana durante a execução",
                deviation_files=_desvios(plano, tocados),
            )

        # O teto é conferido com o custo da chamada já conhecido, antes de enviá-la.
        try:
            guard.checar(context.estimar_tokens(mensagem))
        except BudgetExcedidoError as exc:
            transcript.registrar("system", str(exc), evento="budget_excedido")
            return Resultado(
                status="interrompida_budget",
                failure_reason=str(exc),
                deviation_files=_desvios(plano, tocados),
            )

        transcript.registrar("system", mensagem, rodada=rodada, fase="execucao")

        try:
            content, usage = llm_chat(
                [{"role": "system", "content": mensagem}, GO],
                json_schema=SCHEMA_P5,
                temperature=0.1,
                model=settings.modelo_de_codigo,
                reasoning_effort=settings.reasoning_effort_code,
                tags={"task_id": task.id, "prompt_id": "P5", "fase": "execucao"},
            )
        except Exception as exc:
            transcript.registrar("system", str(exc), evento="falha_llm")
            return Resultado(
                status="falha",
                failure_reason=f"falha na geração: {exc}",
                deviation_files=_desvios(plano, tocados),
            )

        guard.registrar(usage)
        transcript.registrar(
            "assistant",
            json.dumps(content, ensure_ascii=False),
            fase="execucao",
            modelo=usage.get("model"),
            trace_id=usage["trace_id"],
            tokens_in=usage["tokens_in"],
            tokens_out=usage["tokens_out"],
        )

        arquivos = [
            {"path": str(item.get("path") or ""), "content": str(item.get("content") or "")}
            for item in content.get("files") or []
            if isinstance(item, dict)
        ]
        apagar = [str(c) for c in content.get("excluir") or []]
        pedidos = [item["path"] for item in arquivos] + apagar

        # A fronteira é conferida **antes** de escrever ou apagar: um arquivo
        # protegido nem chega ao disco do clone (SPEC-11 §4).
        respeitada, aviso_fronteira = fronteira_respeitada(pedidos)
        if not respeitada:
            log_verificacao = aviso_fronteira
            transcript.registrar("system", aviso_fronteira, evento="fronteira_violada")
            logger.warning("task #%s: %s", task.id, aviso_fronteira)
            continue

        # Daqui em diante todo caminho está na forma canônica, a mesma do plano.
        for item in arquivos:
            item["path"] = context.normalizar(item["path"])
        escritos = {item["path"] for item in arquivos}
        apagar = [c for c in dict.fromkeys(map(context.normalizar, apagar)) if c not in escritos]
        pedidos_de_leitura = {
            c
            for bruto in content.get("ler") or []
            if (c := context.normalizar(str(bruto)))
            and context.alvo_de(c)
            and (workspace.path / c).is_file()
            and c not in mostrados
        }
        extras |= pedidos_de_leitura

        # Cada arquivo devolvido substitui o existente por inteiro. Reescrever um
        # que o modelo nunca recebeu é apagar o que estava lá: recusa, e o
        # conteúdo entra no contexto da próxima rodada.
        as_cegas = sorted(
            c for c in escritos if (workspace.path / c).is_file() and c not in mostrados
        )
        if as_cegas:
            extras |= set(as_cegas)
            log_verificacao = aviso_as_cegas(as_cegas)
            transcript.registrar("system", log_verificacao, evento="escrita_as_cegas")
            logger.warning("task #%s: %s", task.id, log_verificacao)
            continue
        if pedidos_de_leitura and not arquivos and not apagar:
            log_verificacao = ""
            transcript.registrar(
                "system",
                "leitura pedida: " + ", ".join(sorted(pedidos_de_leitura)),
                evento="leitura_pedida",
            )
            continue

        try:
            tocados = sorted(
                set(tocados)
                | set(git_service.write_files(workspace, arquivos))
                | set(git_service.delete_files(workspace, apagar))
            )
        except git_service.GitServiceError as exc:
            # Última trava (symlink saindo do clone): a mesma recusa da fronteira.
            log_verificacao = f"{RECUSA_FRONTEIRA}: {exc}"
            transcript.registrar("system", log_verificacao, evento="fronteira_violada")
            logger.warning("task #%s: %s", task.id, log_verificacao)
            continue

        # Falha controlada do modo demo: acontece **depois** da geração, para que a
        # run tenha custo e transcript reais, como uma falha de verdade teria.
        if task.demo_force_fail_runs and task.demo_force_fail_runs > 0:
            task.demo_force_fail_runs -= 1
            session.add(task)
            session.flush()
            transcript.registrar("system", "falha controlada (DEMO_MODE)", evento="demo_fail")
            return Resultado(
                status="falha",
                failure_reason="falha controlada injetada pelo modo demo",
                deviation_files=_desvios(plano, tocados),
            )

        testes_agora = inventario_de_testes(workspace.path)

        intacta, aviso = rede_de_regressao_intacta(testes_originais, testes_agora)
        if not intacta:
            log_verificacao = aviso
            transcript.registrar("system", aviso, evento="rede_de_regressao_violada")
            logger.warning("task #%s: %s", task.id, aviso)
            continue

        preservadas, aviso = assercoes_preservadas(
            assercoes_originais, assercoes_no_disco(workspace.path)
        )
        if not preservadas:
            log_verificacao = aviso
            transcript.registrar("system", aviso, evento="rede_de_regressao_enfraquecida")
            logger.warning("task #%s: %s", task.id, aviso)
            continue

        # Arquivo apagado não traz comportamento novo a testar.
        existentes = [c for c in tocados if (workspace.path / c).exists()]
        cresceu, aviso = testes_cresceram(existentes, testes_originais, testes_agora)
        if not cresceu:
            log_verificacao = aviso
            transcript.registrar("system", aviso, evento="sem_teste_novo")
            logger.warning("task #%s: %s", task.id, aviso)
            continue

        alvos_tocados = sorted({a for c in tocados if (a := context.alvo_de(c))})
        passou, log_verificacao = verificar(workspace.path, alvos_tocados or None)
        transcript.registrar("system", log_verificacao, evento="verificacao", passou=passou)

        # A cobertura só é comparada depois de a suíte passar: medir o quanto um
        # código quebrado é exercitado não diz nada.
        if passou:
            caiu = None
            for alvo in alvos_tocados:
                antes = cobertura_original.get(alvo) or {}
                if not antes:
                    continue
                manteve, aviso = cobertura_nao_caiu(
                    alvo, tocados, antes, MEDIDORES_DE_COBERTURA[alvo](workspace.path / alvo)
                )
                if not manteve:
                    caiu = aviso
                    break

            if caiu:
                log_verificacao = f"{log_verificacao}\n\n{caiu}"
                transcript.registrar("system", caiu, evento="cobertura_caiu")
                logger.warning("task #%s: %s", task.id, caiu)
                continue

        if passou:
            # A máquina não achou nada. Agora outro modelo confere se a entrega
            # faz o que foi pedido - e o código confere a evidência que ele citar.
            diff_revisado = git_service.diff_em_andamento(workspace)
            try:
                guard.checar(context.estimar_tokens(diff_revisado))
            except BudgetExcedidoError as exc:
                transcript.registrar("system", str(exc), evento="budget_excedido")
                return Resultado(
                    status="interrompida_budget",
                    failure_reason=f"{exc} (antes da revisão independente)",
                    deviation_files=_desvios(plano, tocados),
                )

            try:
                parecer = review.revisar(
                    task_id=task.id,
                    titulo=task.title,
                    descricao=task.description,
                    criterios=plano.acceptance_criteria or [],
                    workspace=workspace.path,
                    tocados=tocados,
                    diff=diff_revisado,
                    feedback_humano=pedido_humano,
                )
            except Exception as exc:
                transcript.registrar("system", str(exc), evento="falha_revisao")
                return Resultado(
                    status="falha",
                    failure_reason=f"falha na revisão independente: {exc}",
                    deviation_files=_desvios(plano, tocados),
                )

            if parecer is not None:
                # A revisão também gasta, e conta contra o mesmo teto: um parecer
                # caro não pode ser o caminho para furar o guardrail.
                if parecer.usage:
                    guard.registrar(parecer.usage)
                # A troca crua com o revisor entra no transcript ao lado do parecer
                # conferido: quem homologa vê o que o modelo disse e o que o código
                # aceitou dele.
                if parecer.troca:
                    transcript.registrar(
                        "system", parecer.troca.get("prompt", ""), fase="revisao", rodada=rodada
                    )
                    transcript.registrar(
                        "assistant",
                        json.dumps(parecer.troca.get("resposta"), ensure_ascii=False),
                        fase="revisao",
                        modelo=parecer.modelo,
                        trace_id=parecer.usage.get("trace_id"),
                        tokens_in=parecer.usage.get("tokens_in"),
                        tokens_out=parecer.usage.get("tokens_out"),
                    )
                transcript.registrar(
                    "system",
                    json.dumps(parecer.como_dict(), ensure_ascii=False),
                    evento="revisao",
                    fase="revisao",
                    aprovado=parecer.aprovado,
                )
                if not parecer.aprovado:
                    log_dos_gates = log_verificacao
                    log_verificacao = parecer.feedback()
                    logger.warning(
                        "task #%s: revisão reprovou (%d critério(s) pendente(s))",
                        task.id,
                        sum(1 for c in parecer.criterios if not c.atendido),
                    )
                    continue
            break
    else:
        # esgotou o ciclo de correção local sem passar
        reprovou_na_revisao = parecer is not None and not parecer.aprovado
        _salvar_log(artefatos, log_dos_gates if reprovou_na_revisao else log_verificacao)
        # O motivo diz **qual** régua reprovou: "lint/teste falharam" sobre uma
        # entrega que passou nos gates e caiu na revisão mandaria quem lê
        # procurar o problema no lugar errado.
        if reprovou_na_revisao:
            motivo = f"a revisão independente reprovou após {settings.max_local_fix} correções"
        elif log_verificacao.startswith(
            (RECUSA_REDE, RECUSA_ASSERCOES, RECUSA_FRONTEIRA, RECUSA_AS_CEGAS)
        ):
            motivo = (
                f"entrega recusada pelas verificações do Executor após "
                f"{settings.max_local_fix} correções: {log_verificacao.split(':', 1)[0]}"
            )
        else:
            motivo = f"lint/teste falharam após {settings.max_local_fix} correções"
        return Resultado(
            status="falha",
            failure_reason=motivo,
            deviation_files=_desvios(plano, tocados),
            log_path=str(artefatos / "lint_test.log"),
            review_path=review.salvar(parecer, artefatos / "review.json") if parecer else None,
        )

    # 2. sucesso: commit, push e artefatos
    try:
        git_service.commit_all(
            workspace,
            conventions.commit_de(task.id, task.title, task.module, task.change_type),
        )
        git_service.push(workspace, forcar=primeira)
        diff = git_service.diff_against_main(workspace)
        alterados = git_service.changed_files(workspace)
    except Exception as exc:
        return Resultado(
            status="falha",
            failure_reason=f"falha ao registrar o trabalho no git: {exc}",
            deviation_files=_desvios(plano, tocados),
        )

    artefatos.mkdir(parents=True, exist_ok=True)
    (artefatos / "diff.patch").write_text(diff, encoding="utf-8")
    _salvar_log(artefatos, log_verificacao)

    return Resultado(
        status="sucesso",
        deviation_files=_desvios(plano, alterados),
        diff_path=str(artefatos / "diff.patch"),
        log_path=str(artefatos / "lint_test.log"),
        review_path=review.salvar(parecer, artefatos / "review.json") if parecer else None,
    )


def _salvar_log(artefatos: Path, log: str) -> None:
    artefatos.mkdir(parents=True, exist_ok=True)
    (artefatos / "lint_test.log").write_text(log, encoding="utf-8")


def _desvios(plano: PlanningDocument, tocados: list[str]) -> list[str]:
    """Arquivos tocados fora do que o planejamento previa (SPEC-04 §6.4).

    Não bloqueiam: o Executor tem liberdade para mexer em arquivos correlacionados
    (SPEC-00 §7). Mas o desvio entre planejado e executado é justamente o que o
    humano precisa ver destacado na Homologação.

    **Arquivo de teste nunca é desvio.** Acrescentar teste passou a ser
    obrigatório - o gate reprova quem não o faz -, e marcar como "fora do plano"
    aquilo que o próprio sistema exige encheria a Homologação de um aviso que
    aparece em toda entrega. Sinal que sempre acende deixa de ser sinal. O caso
    perigoso, que é apagar ou renomear teste existente, já tem hook próprio em
    `rede_de_regressao_intacta`.
    """
    # O plano pode trazer `./client-backend/...`; a comparação é na forma canônica.
    previstos = {context.normalizar(c) or c for c in plano.affected_files or []}
    fora = set(tocados) - previstos
    return sorted(c for c in fora if not _e_arquivo_de_teste(c))
