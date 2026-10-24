"""Edita os documentos de contexto pela API, para a demo D8.

    python _contexto.py remover "<frase>" <arquivo-de-backup>
    python _contexto.py restaurar <arquivo-de-backup>

Os documentos moram no banco do PASE, não em arquivo: a demo fazia `sed` no
`project_context.md`, e isso deixou de existir. A restrição pode estar em mais de um
documento (no contexto e no escopo, por exemplo), então a demo remove de todos e guarda o
texto original para devolver no fim.

Num arquivo próprio, e não embutido no shell, pelo mesmo motivo do `_rota.py`.
"""

import json
import os
import sys
import urllib.request

CORE = os.environ.get("CORE_URL", "http://localhost:8000")


def req(metodo, caminho, corpo=None):
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(
        f"{CORE}{caminho}",
        data=dados,
        method=metodo,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(pedido) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def remover(frase, arquivo):
    salvo = {}
    for resumo in req("GET", "/api/context")["documentos"]:
        slug = resumo["slug"]
        conteudo = req("GET", f"/api/context/doc/{slug}")["content"]
        if frase not in conteudo:
            continue
        salvo[slug] = conteudo
        novo = "\n".join(l for l in conteudo.split("\n") if frase not in l)
        req("PUT", f"/api/context/doc/{slug}", {"content": novo, "note": "demo D8: remove a restrição"})
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(salvo, f, ensure_ascii=False)
    print(len(salvo))


def restaurar(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        salvo = json.load(f)
    for slug, conteudo in salvo.items():
        req("PUT", f"/api/context/doc/{slug}", {"content": conteudo, "note": "demo D8: restaura"})
    print(len(salvo))


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "remover":
        remover(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "restaurar":
        restaurar(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
