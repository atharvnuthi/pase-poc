"""Conferência da citação do filtro de Coerência (monografia §4.2 e §4.3.4).

O P2a, ao dizer que uma proposta viola o contexto, aponta o trecho violado. Quem
decide se o trecho existe é este código, não o modelo: a mesma divisão de trabalho
da Reavaliação Cíclica (`reevaluation.evidencia_confere`). Pedir ao modelo que
confirme a própria citação produz confabulação - ele cola a seção inteira, ou cita
de memória uma regra que o documento não tem.

A comparação é literal depois de normalizar o que não muda o sentido: caixa,
espaços e quebras de linha, ênfase de markdown e aspas. Não é por similaridade: um
trecho parecido com o documento não é um trecho do documento.
"""

from __future__ import annotations

import re

#: Abaixo disto a "citação" é uma palavra solta, que casa com qualquer documento.
TRECHO_MIN_CHARS = 8
#: Uma regra do contexto cabe em uma ou duas linhas. Bloco grande é o modelo colando
#: a seção inteira para provar qualquer coisa.
TRECHO_MAX_CHARS = 300

_ENFASE = re.compile(r"[*_`]+")
_ASPAS = re.compile(r"[\"'“”‘’«»]")
_MARCADOR_DE_LISTA = re.compile(r"^[\s\-•*+>]+")


def _normalizar(texto: str) -> str:
    texto = _ENFASE.sub("", texto.lower())
    texto = _ASPAS.sub("", texto)
    return " ".join(texto.split())


def trecho_confere(trecho: str | None, documentos: str) -> bool:
    """O trecho citado existe, literalmente, nos documentos que o P2a recebeu?"""
    if not trecho:
        return False
    # o ponto final e o marcador de lista são da formatação, não da regra
    citacao = _normalizar(_MARCADOR_DE_LISTA.sub("", trecho.strip())).rstrip(" .;:,")
    if not (TRECHO_MIN_CHARS <= len(citacao) <= TRECHO_MAX_CHARS):
        return False
    return citacao in _normalizar(documentos)
