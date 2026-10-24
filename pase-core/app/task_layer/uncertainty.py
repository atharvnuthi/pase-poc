"""Marcador de incerteza da priorização (monografia §4.4.1).

A tarefa candidata pede atenção redobrada de quem decide quando o próprio modelo
duvida das estimativas (confiança baixa) ou quando a conta não fecha: pouco valor
para muito esforço. As duas condições são regra fixa, não julgamento do modelo -
e por isso o marcador é recalculado sempre que impacto, complexidade ou confiança
mudam, inclusive por edição humana.
"""

#: Abaixo disto, o modelo não confia nas próprias estimativas.
CONFIANCA_MINIMA = 0.5
#: Impacto e complexidade vão de 1 a 5 (P2b).
IMPACTO_BAIXO = 2
COMPLEXIDADE_ALTA = 4


def incerteza(impact: int, complexity: int, confidence: float) -> bool:
    """True quando a tarefa merece o marcador de incerteza."""
    return confidence < CONFIANCA_MINIMA or (
        impact <= IMPACTO_BAIXO and complexity >= COMPLEXIDADE_ALTA
    )
