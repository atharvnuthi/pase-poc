"""Revisão independente (P12): a entrega cumpre o que foi pedido?

Os gates mecânicos - lint, tipos, testes, build, cobertura - respondem "o código
está quebrado?". Eles não respondem "o código faz o que a pessoa pediu?". A tarefa
#4 mostrou a distância entre as duas perguntas: um modo escuro que pôs a classe
`dark` no `body`, testou que a classe estava lá, passou em tudo, e não tinha uma
única cor escura definida.

Três decisões de desenho, cada uma com motivo medido:

1. **Outro modelo revisa.** Quem escreveu tende a aprovar o próprio ponto cego -
   os testes da tarefa #4 foram escritos pelo mesmo agente que errou.
2. **O revisor aponta evidência; o código confere.** Pedir veredito booleano a um
   LLM produz confabulação (medido no P9). Aqui o revisor precisa citar o trecho
   que cumpre cada critério, e um critério só vale se o trecho existir de fato no
   arquivo.
3. **Reprovação volta para o ciclo de correção**, com o parecer como feedback.
   Revisão que só informa o humano no fim chegaria tarde demais: a pessoa veria um
   diff aprovado pela máquina e confiaria nele.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.common import prompts
from app.common.config import settings
from app.common.llm_client import chat as llm_chat
from app.execution.context import e_arquivo_de_teste

logger = logging.getLogger("pase.execution")

SCHEMA_P12 = {
    "type": "object",
    "properties": {
        "criterios": {"type": "array"},
        "colaterais": {"type": "array"},
        "resumo": {"type": "string"},
    },
    "required": ["criterios", "colaterais", "resumo"],
}

GO = {"role": "user", "content": "Produza agora o objeto JSON pedido."}

#: Primeira linha do feedback de reprovação - o executor a reconhece para não
#: apresentar o parecer ao modelo como se fosse saída de teste.
TITULO_DO_FEEDBACK = "A revisão independente reprovou a entrega"

#: Teto do conteúdo de arquivos mandado ao revisor. Os alvos são pequenos; isto
#: só protege contra um arquivo gerado gigante estourar o contexto.
MAX_CHARS_POR_ARQUIVO = 40_000


@dataclass
class CriterioRevisado:
    id: str
    criterio: str
    atendido: bool
    explicacao: str
    evidencia: dict | None = None
    teste: dict | None = None
    verificacao_manual: str | None = None
    #: Por que o código anulou o "atendido" do revisor, quando anulou.
    anulado_por: str | None = None


@dataclass
class Parecer:
    aprovado: bool
    criterios: list[CriterioRevisado] = field(default_factory=list)
    #: Colaterais que **reprovam**: mudam comportamento fora do escopo da tarefa.
    colaterais: list[dict] = field(default_factory=list)
    #: Colaterais cosméticos - vão para quem homologa, não reprovam a entrega.
    avisos: list[dict] = field(default_factory=list)
    resumo: str = ""
    #: Quem revisou e quem escreveu. Ficam no parecer para a Homologação mostrar
    #: se a revisão foi de fato de outro agente.
    modelo: str = ""
    modelo_do_codigo: str = ""
    mesmo_modelo: bool = False
    #: Consumo da chamada de revisão, para o guardrail de budget contabilizar.
    usage: dict = field(default_factory=dict)
    #: A troca crua com o revisor (`prompt`, `resposta`), para o transcript da
    #: run. Não vai para o `review.json`: o parecer é o que o código conferiu.
    troca: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        dados = asdict(self)
        dados.pop("usage", None)
        dados.pop("troca", None)
        return dados

    def feedback(self) -> str:
        """O que volta para o executor quando a revisão reprova."""
        partes = [
            f"{TITULO_DO_FEEDBACK}\n\n"
            "Lint, tipos, testes e build passaram. Mas a entrega não cumpre o que foi "
            "pedido:"
        ]
        for c in self.criterios:
            if c.atendido:
                continue
            motivo = c.anulado_por or c.explicacao
            partes.append(f"- [{c.id}] {c.criterio}\n  → {motivo}")
        for col in self.colaterais:
            partes.append(
                f"- Mudança colateral em {col.get('arquivo')}: {col.get('motivo')}. "
                "Desfaça - a tarefa não pede isto."
            )
        partes.append(
            "Corrija o código e os testes. Um teste só vale se falharia caso o critério "
            "não fosse cumprido."
        )
        return "\n".join(partes)


def _normalizar(texto: str) -> str:
    """Compara ignorando espaço em branco: o revisor pode reindentar ao citar."""
    return re.sub(r"\s+", " ", texto or "").strip()


def _trecho_existe(workspace: Path, citacao: dict | None) -> tuple[bool, str]:
    """A citação aponta para algo que existe de fato no arquivo?

    Só arquivos dentro do clone, por caminho relativo - uma citação com `..` ou
    caminho absoluto não é aceita como evidência.
    """
    if not citacao:
        return False, "sem citação"

    arquivo = str(citacao.get("arquivo") or "").replace("\\", "/").lstrip("/")
    trecho = _normalizar(str(citacao.get("trecho") or ""))
    if not arquivo or ".." in arquivo.split("/"):
        return False, f"caminho inválido: {arquivo!r}"
    if len(trecho) < 8:
        return False, "trecho curto demais para servir de evidência"

    caminho = workspace / arquivo
    if not caminho.is_file():
        return False, f"o arquivo {arquivo} não existe"

    conteudo = _normalizar(caminho.read_text(encoding="utf-8", errors="replace"))
    if trecho not in conteudo:
        return False, f"o trecho citado não está em {arquivo}"
    return True, ""


def _colateral_confirmado(diff: str, citacao: dict) -> bool:
    """O trecho apontado como colateral aparece mesmo entre as linhas alteradas?"""
    trecho = _normalizar(str(citacao.get("trecho") or "").lstrip("+-"))
    if len(trecho) < 4:
        return False
    alteradas = " ".join(
        linha[1:]
        for linha in diff.splitlines()
        if linha[:1] in "+-" and not linha.startswith(("+++", "---"))
    )
    return trecho in _normalizar(alteradas)


def _arquivos_para_revisao(workspace: Path, tocados: list[str]) -> str:
    blocos = []
    for relativo in sorted(set(tocados)):
        caminho = workspace / relativo
        if not caminho.is_file():
            blocos.append(f"### {relativo}\n(removido)")
            continue
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        if len(texto) > MAX_CHARS_POR_ARQUIVO:
            texto = texto[:MAX_CHARS_POR_ARQUIVO] + "\n[…truncado]"
        blocos.append(f"### {relativo}\n```\n{texto}\n```")
    return "\n\n".join(blocos)


def _criterios_em_texto(criterios: list[dict]) -> str:
    return "\n".join(
        f"- **{c['id']}** - {c['criterio']}\n"
        f"  verificação planejada: {c.get('como_verificar') or '-'}"
        for c in criterios
    )


def conferir(bruto: dict, criterios: list[dict], workspace: Path, diff: str) -> Parecer:
    """Transforma o parecer do modelo num parecer **verificado**.

    Separado de `revisar` para poder ser testado sem chamar modelo nenhum: é aqui
    que mora a garantia, não no prompt.
    """
    respostas = {
        str(r.get("id")): r for r in (bruto.get("criterios") or []) if isinstance(r, dict)
    }
    revisados: list[CriterioRevisado] = []

    for c in criterios:
        r = respostas.get(c["id"])
        if r is None:
            revisados.append(
                CriterioRevisado(
                    id=c["id"],
                    criterio=c["criterio"],
                    atendido=False,
                    explicacao="",
                    anulado_por="o revisor não avaliou este critério",
                )
            )
            continue

        item = CriterioRevisado(
            id=c["id"],
            criterio=c["criterio"],
            atendido=bool(r.get("atendido")),
            explicacao=str(r.get("explicacao") or ""),
            evidencia=r.get("evidencia") if isinstance(r.get("evidencia"), dict) else None,
            teste=r.get("teste") if isinstance(r.get("teste"), dict) else None,
            verificacao_manual=(str(r["verificacao_manual"]).strip() or None)
            if r.get("verificacao_manual")
            else None,
        )

        if item.atendido:
            ok, porque = _trecho_existe(workspace, item.evidencia)
            if not ok:
                item.atendido = False
                item.anulado_por = f"evidência não confere - {porque}"
            elif item.teste is not None:
                ok, porque = _trecho_existe(workspace, item.teste)
                if ok and not e_arquivo_de_teste(str(item.teste.get("arquivo") or "")):
                    # Um trecho de código de produção citado como "teste" prova
                    # que o código existe, não que alguém o exercita.
                    ok, porque = False, f"{item.teste.get('arquivo')} não é arquivo de teste"
                if not ok:
                    item.atendido = False
                    item.anulado_por = f"o teste citado não confere - {porque}"
            elif not item.verificacao_manual:
                item.atendido = False
                item.anulado_por = (
                    "sem teste que o prove e sem justificativa para verificação manual"
                )

        revisados.append(item)

    confirmados = [
        col
        for col in (bruto.get("colaterais") or [])
        if isinstance(col, dict) and _colateral_confirmado(diff, col)
    ]
    # Sem gravidade declarada vale o lado conservador. Cosmético só deixa de
    # bloquear quando o revisor diz que é cosmético: numa entrega real, aspas
    # reformatadas e uma docstring consumiram quatro rodadas de correção (~270 mil
    # tokens) numa tarefa que cumpria todos os critérios.
    colaterais = [c for c in confirmados if c.get("gravidade") != "aviso"]
    avisos = [c for c in confirmados if c.get("gravidade") == "aviso"]

    aprovado = bool(revisados) and all(c.atendido for c in revisados) and not colaterais
    return Parecer(
        aprovado=aprovado,
        criterios=revisados,
        colaterais=colaterais,
        avisos=avisos,
        resumo=str(bruto.get("resumo") or ""),
        modelo=settings.modelo_de_revisao,
        modelo_do_codigo=settings.modelo_de_codigo,
        mesmo_modelo=settings.modelo_de_revisao == settings.modelo_de_codigo,
    )


def revisar(
    *,
    task_id: int,
    titulo: str,
    descricao: str,
    criterios: list[dict],
    workspace: Path,
    tocados: list[str],
    diff: str,
    feedback_humano: str | None = None,
) -> Parecer | None:
    """P12 → parecer verificado. `None` quando não há critério para revisar.

    Sem critério não há revisão - e o Executor não deixa uma entrega dessas
    seguir: ele recusa o plano sem critérios antes de escrever código
    (`executor.SEM_CRITERIOS`). O `None` daqui é só a proteção de quem chamar
    esta função por outro caminho.

    O revisor é outro agente: outra chamada, com outro prompt, sem nada da
    conversa do executor. Se o modelo configurado para revisar for o mesmo que
    escreveu, a independência fica só no papel - o sistema avisa no log e o
    parecer registra, para a Homologação mostrar.
    """
    if not criterios:
        return None

    if settings.modelo_de_revisao == settings.modelo_de_codigo:
        logger.warning(
            "P12 task #%s: o revisor é o mesmo modelo que escreveu o código (%s). "
            "Configure LLM_MODEL_REVIEW com outro modelo para uma revisão independente.",
            task_id,
            settings.modelo_de_revisao,
        )

    bloco_humano = ""
    if feedback_humano:
        bloco_humano = (
            "## O que a pessoa pediu para corrigir\n\n"
            f"{feedback_humano}\n\n"
            "Confira também se isto foi resolvido."
        )

    mensagem = prompts.system_message(
        "P12",
        title=titulo,
        description=descricao,
        feedback_humano=bloco_humano,
        criterios=_criterios_em_texto(criterios),
        documentacao=prompts.load_documentacao("revisao"),
        diff=diff or "(diff vazio)",
        arquivos=_arquivos_para_revisao(workspace, tocados),
    )
    conteudo, usage = llm_chat(
        [mensagem, GO],
        json_schema=SCHEMA_P12,
        temperature=0.0,
        model=settings.modelo_de_revisao,
        reasoning_effort=settings.reasoning_effort_review,
        tags={"task_id": task_id, "prompt_id": "P12", "fase": "revisao"},
    )

    parecer = conferir(conteudo, criterios, workspace, diff)
    parecer.usage = usage
    parecer.troca = {"prompt": mensagem["content"], "resposta": conteudo}
    logger.info(
        "P12 task #%s: %s (%d/%d critérios, %d colaterais) trace=%s",
        task_id,
        "aprovado" if parecer.aprovado else "reprovado",
        sum(1 for c in parecer.criterios if c.atendido),
        len(parecer.criterios),
        len(parecer.colaterais),
        usage["trace_id"],
    )
    return parecer


def salvar(parecer: Parecer, destino: Path) -> str:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(parecer.como_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(destino)
