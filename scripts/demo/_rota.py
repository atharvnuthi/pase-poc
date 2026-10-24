"""Extrai a primeira rota GET que o diff ADICIONOU.

Num arquivo próprio, e não embutido no shell: o Python inline dentro de heredoc
acumula três níveis de escape (bash, heredoc, regex) e quebra em silêncio.
"""

import re
import sys

adicionadas = [
    linha[1:]
    for linha in sys.stdin.read().splitlines()
    if linha.startswith("+") and not linha.startswith("+++")
]
rotas = re.findall(r'@router\.get\(\s*"([^"]+)"', "\n".join(adicionadas))
print(rotas[0] if rotas else "")
