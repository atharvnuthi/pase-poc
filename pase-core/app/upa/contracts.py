"""Registro de zonas e validação do contrato (SPEC-05 §1 e §6).

Uma Zona Dinâmica é um **contrato**, não um espaço livre: um componente nativo
pré-testado que aceita propriedades validadas. O LLM preenche as propriedades
dentro do schema e nunca escreve o componente (SPEC-00 §6).

O schema canônico vive em `docs/contracts/`, não aqui. O Python carrega o arquivo
e o cliente o espelha em Zod - redigitar o contrato em Python dobraria a chance
de as duas validações divergirem, e o SPEC-05 §6 diz que divergência é bug.

Todas as zonas compartilham **um** contrato (`zona.schema.json`): o que muda de uma
zona para outra é onde ela aparece, para que serve e o que dispara a avaliação dela, não
a forma do payload. Zona nova é uma entrada em `ZONAS` e um `<DynamicZone>` na tela.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError, validators

from app.common.config import settings


@dataclass(frozen=True)
class Zona:
    slot: str
    #: Rota do FinTrack onde a zona aparece.
    tela: str
    #: Módulo do funil que ela cobre: é por ele que uma sugestão de usuário chega a ela.
    modulo: str
    #: O que o P6 recebe para decidir o que faz sentido ali.
    finalidade: str
    #: Rota cujo uso repetido dispara a avaliação, e quantas visitas na janela bastam.
    observa: str
    acessos_minimos: int


RESUMO_FINANCEIRO = "resumo_financeiro"
TRANSACOES_ATALHOS = "transacoes_atalhos"
RELATORIOS_DESTAQUE = "relatorios_destaque"
ORCAMENTOS_AVISO = "orcamentos_aviso"
METAS_INCENTIVO = "metas_incentivo"
SUPORTE_AJUDA = "suporte_ajuda"

ZONAS: dict[str, Zona] = {
    z.slot: z
    for z in (
        Zona(
            slot=RESUMO_FINANCEIRO,
            tela="/dashboard",
            modulo="dashboard",
            finalidade=(
                "Área de destaque no topo do dashboard do FinTrack, logo abaixo do saldo. "
                "Serve para dar ao usuário acesso rápido àquilo que ele mais consulta, ou "
                "um aviso curto e pertinente sobre suas finanças. É complemento do resumo "
                "nativo de gastos por categoria, que continua exibido abaixo dela."
            ),
            observa="/relatorios",
            acessos_minimos=5,
        ),
        Zona(
            slot=TRANSACOES_ATALHOS,
            tela="/transacoes",
            modulo="transacoes",
            finalidade=(
                "Faixa no topo da tela de Transações, acima do formulário de lançamento. "
                "Serve para atalhos ao que a pessoa mais faz fora daqui (consultar "
                "relatórios, acompanhar o orçamento) ou um aviso curto sobre os lançamentos "
                "dela. Não repete o formulário nem a lista que aparecem logo abaixo."
            ),
            observa="/transacoes",
            acessos_minimos=5,
        ),
        Zona(
            slot=RELATORIOS_DESTAQUE,
            tela="/relatorios",
            modulo="relatorios",
            finalidade=(
                "Área no topo da tela de Relatórios, acima da tabela mensal. Destaca um "
                "ponto que a pessoa acompanha nos totais (um atalho para o orçamento ou "
                "para as transações) ou um aviso curto. Não repete a tabela."
            ),
            observa="/relatorios",
            acessos_minimos=3,
        ),
        Zona(
            slot=ORCAMENTOS_AVISO,
            tela="/orcamentos",
            modulo="orcamentos",
            finalidade=(
                "Faixa no topo da tela de Orçamentos. Aviso curto sobre limites (categorias "
                "perto do teto) ou atalhos para as transações e relatórios da categoria que "
                "a pessoa mais acompanha. Não repete os limites listados logo abaixo."
            ),
            observa="/orcamentos",
            acessos_minimos=3,
        ),
        Zona(
            slot=METAS_INCENTIVO,
            tela="/metas",
            modulo="metas",
            finalidade=(
                "Faixa no topo da tela de Metas. Incentivo curto e realista sobre as metas "
                "da pessoa, ou atalhos para o orçamento e as transações. Sem exclamação e "
                "sem prometer resultado."
            ),
            observa="/metas",
            acessos_minimos=3,
        ),
        Zona(
            slot=SUPORTE_AJUDA,
            tela="/suporte",
            modulo="suporte",
            finalidade=(
                "Faixa no topo da tela de Suporte. Atalhos para as telas que costumam "
                "responder as dúvidas comuns (transações, relatórios, orçamentos), conforme "
                "o uso da pessoa."
            ),
            observa="/suporte",
            acessos_minimos=2,
        ),
    )
}

#: Slot → finalidade. Mantido porque é o que as rotas e o P6 consultam.
SLOTS: dict[str, str] = {slot: z.finalidade for slot, z in ZONAS.items()}

#: Módulo do funil → slot da zona que o cobre.
ZONA_DO_MODULO: dict[str, str] = {z.modulo: z.slot for z in ZONAS.values()}

#: Todas as zonas compartilham este contrato.
ARQUIVO_DO_CONTRATO = "zona.schema.json"


def zonas_que_observam(rota: str) -> list[Zona]:
    return [z for z in ZONAS.values() if z.observa == rota]


def caminho_do_contrato(slot: str | None = None) -> Path:
    return Path(settings.repo_path) / "docs" / "contracts" / ARQUIVO_DO_CONTRATO


@cache
def schema_de(slot: str) -> dict:
    """Carrega o contrato canônico (o mesmo para todas as zonas)."""
    if slot not in SLOTS:
        raise KeyError(f"slot desconhecido: {slot}")

    caminho = caminho_do_contrato(slot)
    if not caminho.exists():
        raise FileNotFoundError(
            f"contrato canônico ausente em {caminho}. É a fonte de verdade da zona "
            "e sem ele o core não pode validar payload nenhum."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def _padrao_ecma(padrao: str) -> str:
    """Traduz a âncora final de um `pattern` para a semântica do ECMA-262.

    O JSON Schema define `pattern` como regex ECMA-262, e é assim que o Zod a aplica.
    No ECMA, `$` sem a flag `m` só casa no fim do texto; no `re` do Python ele casa
    também antes de uma quebra de linha final. Sem esta tradução, `"/metas\\n"` passava
    no core e era recusado no cliente: exatamente a divergência que o espelho proíbe.
    """
    if padrao.endswith("$") and not padrao.endswith("\\$"):
        return padrao[:-1] + r"\Z"
    return padrao


def _pattern(validador, padrao, instancia, schema):
    if validador.is_type(instancia, "string") and not re.search(_padrao_ecma(padrao), instancia):
        yield ValidationError(f"{instancia!r} does not match {padrao!r}")


#: O validador do Draft 2020-12, com `pattern` na semântica do ECMA-262 (a do cliente).
Validador = validators.extend(Draft202012Validator, {"pattern": _pattern})


def erros_de(slot: str, payload: object) -> list[str]:
    """Todos os motivos pelos quais o payload não respeita o contrato.

    Lista vazia significa válido. Devolver todos os erros, e não só o primeiro,
    é o que permite ao motivo registrado na violação ser específico.
    """
    validador = Validador(schema_de(slot))
    return [
        f"{'/'.join(str(p) for p in erro.absolute_path) or 'payload'}: {erro.message}"
        for erro in sorted(validador.iter_errors(payload), key=lambda e: list(e.absolute_path))
    ]


def valido(slot: str, payload: object) -> bool:
    return not erros_de(slot, payload)
