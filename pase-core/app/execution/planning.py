"""Fase de Planejamento (SPEC-04 §4.1).

Separada da execução de propósito: é o "plan mode antes de código" do playbook
(SPEC-08 §3). O plano vira artefato versionado - `planning_documents` - que o
humano pode ler na Homologação e comparar com o que de fato foi executado.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.common import prompts
from app.common.config import settings
from app.common.llm_client import chat as llm_chat
from app.execution import context
from app.orchestration.models import PlanningDocument
from app.task_layer.models import Task

logger = logging.getLogger("pase.execution")

SCHEMA_P4 = {
    "type": "object",
    "properties": {
        "acceptance_criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "criterio": {"type": "string"},
                    "como_verificar": {"type": "string"},
                },
                "required": ["id", "criterio", "como_verificar"],
            },
        },
        # Mapeamento de impacto: cada arquivo com o que acontece com ele.
        "arquivos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                    "acao": {"type": "string", "enum": ["modificar", "criar", "excluir"]},
                },
                "required": ["caminho", "acao"],
            },
        },
        "roadmap": {"type": "string"},
        "tokens_estimated": {"type": "integer"},
        "minutos_estimados": {"type": "integer"},
        "risco_tecnico": {
            "type": "object",
            "properties": {
                "nivel": {"type": "string", "enum": ["baixo", "medio", "alto"]},
                "justificativa": {"type": "string"},
            },
            "required": ["nivel", "justificativa"],
        },
    },
    "required": [
        "acceptance_criteria",
        "arquivos",
        "roadmap",
        "tokens_estimated",
        "minutos_estimados",
        "risco_tecnico",
    ],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}

ACOES = ("modificar", "criar", "excluir")
NIVEIS_DE_RISCO = ("baixo", "medio", "alto")


def mapeamento_de_impacto(content: dict, base: Path | None = None) -> tuple[list[str], dict]:
    """(`affected_files`, `file_actions`) a partir da resposta do P4.

    Caminho normalizado e sem repetição. Ação que o modelo não declarou, ou
    declarou fora das três, é deduzida do repositório: o arquivo existe →
    `modificar`; não existe → `criar`. A resposta no formato antigo, só com
    `affected_files`, continua aceita pelo mesmo caminho.
    """
    raiz = base or Path(settings.repo_path)
    brutos = content.get("arquivos")
    if not isinstance(brutos, list):
        brutos = [{"caminho": c} for c in content.get("affected_files") or []]

    acoes: dict[str, str] = {}
    for bruto in brutos:
        if isinstance(bruto, str):
            bruto = {"caminho": bruto}
        if not isinstance(bruto, dict):
            continue
        caminho = context.normalizar(str(bruto.get("caminho") or bruto.get("path") or ""))
        if not caminho or caminho in acoes:
            continue
        acao = str(bruto.get("acao") or "").strip().lower()
        if acao not in ACOES:
            acao = "modificar" if (raiz / caminho).is_file() else "criar"
        acoes[caminho] = acao
    return list(acoes), acoes


def risco_tecnico(content: dict) -> tuple[str | None, str | None]:
    bruto = content.get("risco_tecnico")
    if not isinstance(bruto, dict):
        return None, None
    nivel = str(bruto.get("nivel") or "").strip().lower().replace("é", "e")
    justificativa = str(bruto.get("justificativa") or "").strip() or None
    return (nivel if nivel in NIVEIS_DE_RISCO else None), justificativa


def _inteiro(valor) -> int | None:
    try:
        return max(int(valor), 0)
    except (TypeError, ValueError):
        return None


def _com_quebras_de_linha(texto: str) -> str:
    """Modelos de raciocínio às vezes devolvem `\\n` literal dentro da string JSON.

    O roadmap é lido por uma pessoa na tela; barra-n visível no meio do texto o
    deixa ilegível. Só converte quando não há nenhuma quebra de verdade, para não
    mexer num texto que já veio certo.
    """
    if "\\n" in texto and "\n" not in texto:
        return texto.replace("\\n", "\n")
    return texto


def criterios_validos(brutos: list) -> list[dict]:
    """Normaliza os critérios: id único, texto não vazio.

    O modelo às vezes repete id ou devolve critério em branco. A revisão cita
    critério por id, então ids repetidos fariam um veredito valer por dois.
    """
    vistos: set[str] = set()
    limpos = []
    for i, bruto in enumerate(brutos or [], start=1):
        texto = str(bruto.get("criterio", "")).strip()
        if not texto:
            continue
        cid = str(bruto.get("id") or f"C{i}").strip() or f"C{i}"
        while cid in vistos:
            cid = f"{cid}'"
        vistos.add(cid)
        limpos.append(
            {
                "id": cid,
                "criterio": texto,
                "como_verificar": str(bruto.get("como_verificar", "")).strip(),
            }
        )
    return limpos


def planejar(session: Session, task: Task, historico: str = "") -> PlanningDocument:
    """P4 → `planning_documents`.

    `historico` descreve tentativas anteriores da mesma demanda e por que não
    serviram. Sem ele, refazer uma tarefa é pedir o mesmo erro de novo.
    """
    # A varredura do repositório acontece aqui, uma vez: o P4 lê o código
    # inteiro dos alvos. A execução parte do roteiro que sai daqui.
    fonte = context.source_tree()
    contexto_tokens = context.estimar_tokens(fonte)

    mensagem = prompts.system_message(
        "P4",
        title=task.title,
        description=task.description,
        module=task.module,
        output_type=task.output_type,
        documentacao=prompts.load_documentacao("planejamento"),
        source_tree=fonte,
        context_tokens=contexto_tokens,
        historico=historico,
    )
    content, usage = llm_chat(
        [mensagem, GO],
        json_schema=SCHEMA_P4,
        temperature=0.1,
        model=settings.modelo_de_codigo,
        reasoning_effort=settings.reasoning_effort_planning,
        tags={"task_id": task.id, "prompt_id": "P4", "fase": "planejamento"},
    )

    affected_files, file_actions = mapeamento_de_impacto(content)
    nivel, justificativa = risco_tecnico(content)
    plano = PlanningDocument(
        task_id=task.id,
        acceptance_criteria=criterios_validos(content.get("acceptance_criteria", [])),
        affected_files=affected_files,
        file_actions=file_actions,
        roadmap=_com_quebras_de_linha(content["roadmap"]),
        tokens_estimated=_inteiro(content.get("tokens_estimated")) or 0,
        minutes_estimated=_inteiro(content.get("minutos_estimados")),
        technical_risk=nivel,
        technical_risk_reason=justificativa,
    )
    session.add(plano)
    session.flush()

    plano.transcript_path = _salvar_transcript(task.id, plano.id, mensagem, content, usage)
    session.flush()

    logger.info(
        "P4 task #%s: %d critério(s), %d arquivo(s), estimativa %d tokens / %s min, "
        "risco %s (contexto lido: %d) trace=%s",
        task.id,
        len(plano.acceptance_criteria),
        len(plano.affected_files),
        plano.tokens_estimated,
        plano.minutes_estimated,
        plano.technical_risk,
        contexto_tokens,
        usage["trace_id"],
    )
    return plano


def _salvar_transcript(
    task_id: int, plano_id: int, mensagem: dict, content: dict, usage: dict
) -> str | None:
    """A troca do P4 em JSONL, no formato do transcript das runs.

    Cada execução a incorpora no início do próprio transcript: é a primeira
    parte do histórico completo da interação com o modelo que vai à Homologação.
    Falha ao gravar não derruba o plano - o plano é o artefato, o transcript é
    o rastro dele.
    """
    destino = (
        Path(settings.artifacts_path) / f"task-{task_id}" / f"plano-{plano_id}" / "transcript.jsonl"
    )
    linhas = [
        {"role": "system", "content": mensagem["content"]},
        {
            "role": "assistant",
            "content": json.dumps(content, ensure_ascii=False),
            "modelo": usage.get("model"),
            "trace_id": usage.get("trace_id"),
            "tokens_in": usage.get("tokens_in"),
            "tokens_out": usage.get("tokens_out"),
        },
    ]
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            "".join(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("não consegui gravar o transcript do plano #%s: %s", plano_id, exc)
        return None
    return str(destino)
