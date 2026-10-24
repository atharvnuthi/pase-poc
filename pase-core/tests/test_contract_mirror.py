"""Zod e JSON Schema não podem divergir (SPEC-05 §6, Apêndice B).

O contrato existe em dois lugares por necessidade: o core valida em Python antes
de persistir, o cliente valida em TypeScript antes de renderizar. O SPEC diz que
divergência entre os dois é bug - e uma regra dessas só vale se algo a verificar.

Uma divergência silenciosa é a pior espécie: o core aceitaria payload que o
cliente recusa (personalização que nunca aparece, violação inexplicável) ou o
contrário (payload chegando à tela sem ter passado pelo core).

Como a comparação é feita: este teste **traduz o `schema.ts` para JSON Schema** e
compara o resultado com o canônico, campo a campo - tipos, enums, limites de
tamanho, limites numéricos, limite de itens, campos obrigatórios nos dois níveis,
`additionalProperties`/`.strict()` nos dois níveis, a regex do `href` e os
condicionais do `allOf`. O tradutor conhece um subconjunto pequeno do Zod, e de
propósito: construção que ele não sabe traduzir faz o teste falhar, em vez de
passar sem ter comparado. A alternativa seria rodar um interpretador de TypeScript
dentro da suíte do Python.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from app.common.config import settings
from app.upa import contracts

ZOD = Path(settings.repo_path) / "client-frontend" / "dynamic-zones" / "schema.ts"
WIDGETS = Path(settings.repo_path) / "client-frontend" / "dynamic-zones" / "widgets.tsx"

#: Palavras do JSON Schema que documentam e não validam.
SO_DOCUMENTACAO = {"description", "title", "$schema", "$id"}


def _zod() -> str:
    assert ZOD.exists(), f"espelho em Zod ausente em {ZOD}"
    return ZOD.read_text(encoding="utf-8")


def _canonico() -> dict:
    return contracts.schema_de(contracts.RESUMO_FINANCEIRO)


# --------------------------------------------------------------------------- #
# Leitura do schema.ts
# --------------------------------------------------------------------------- #

_TOKEN = re.compile(
    r"""
    (?P<espaco>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<texto>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)
  | (?P<numero>\d+(?:\.\d+)?)
  | (?P<nome>[A-Za-z_$][\w$]*)
  | (?P<seta>=>)
  | (?P<simbolo>.)
    """,
    re.VERBOSE | re.DOTALL,
)


class _Leitor:
    """Recursive descent sobre o pedaço do TypeScript que declara um schema."""

    def __init__(self, fonte: str, inicio: int):
        self.fonte = fonte
        self.tokens = [
            (m.lastgroup, m.group(), m.start())
            for m in _TOKEN.finditer(fonte, inicio)
            if m.lastgroup != "espaco"
        ]
        self.i = 0

    def olhar(self) -> str:
        return self.tokens[self.i][1]

    def tipo(self) -> str:
        return self.tokens[self.i][0]

    def comer(self, esperado: str | None = None) -> str:
        valor = self.tokens[self.i][1]
        if esperado is not None:
            assert valor == esperado, (
                f"schema.ts: esperava '{esperado}', encontrei '{valor}' "
                f"perto de: {self.fonte[self.tokens[self.i][2]:][:60]!r}"
            )
        self.i += 1
        return valor

    def balanceado(self) -> str:
        """Pula `( ... )` sem interpretar e devolve o texto de dentro."""
        inicio = self.tokens[self.i][2]
        profundidade = 0
        while True:
            valor = self.comer()
            if valor in "([{":
                profundidade += 1
            elif valor in ")]}":
                profundidade -= 1
                if profundidade == 0:
                    return self.fonte[inicio + 1 : self.tokens[self.i - 1][2]]

    def expressao(self) -> dict:
        """`base(.metodo(args))*` → {"base": ..., "args": ..., "metodos": [...]}"""
        if self.olhar() == "z":
            self.comer("z")
            self.comer(".")
        base = self.comer()
        no = {"base": base, "args": None, "metodos": []}
        if self.olhar() == "(":
            no["args"] = self.argumentos()
        while self.olhar() == ".":
            self.comer(".")
            nome = self.comer()
            if nome in ("superRefine", "refine"):
                no["metodos"].append((nome, [self.balanceado()]))
            else:
                no["metodos"].append((nome, self.argumentos()))
        return no

    def argumentos(self) -> list:
        self.comer("(")
        args = []
        while self.olhar() != ")":
            args.append(self.valor())
            if self.olhar() == ",":
                self.comer(",")
        self.comer(")")
        return args

    def valor(self):
        if self.tipo() == "numero":
            numero = self.comer()
            return float(numero) if "." in numero else int(numero)
        if self.tipo() == "texto":
            return self.comer()[1:-1]
        if self.olhar() == "[":
            self.comer("[")
            itens = []
            while self.olhar() != "]":
                itens.append(self.valor())
                if self.olhar() == ",":
                    self.comer(",")
            self.comer("]")
            return itens
        if self.olhar() == "{":
            self.comer("{")
            campos = {}
            while self.olhar() != "}":
                chave = self.comer()
                self.comer(":")
                campos[chave] = self.valor()
                if self.olhar() == ",":
                    self.comer(",")
            self.comer("}")
            return campos
        return self.expressao()


def _declaracao(fonte: str, nome: str) -> dict:
    achado = re.search(rf"(?:export\s+)?const\s+{nome}\s*=", fonte)
    assert achado, f"schema.ts não declara `{nome}`"
    leitor = _Leitor(fonte, achado.end())
    no = leitor.expressao()
    assert leitor.olhar() == ";", f"`{nome}` termina com algo que o espelho não sabe ler"
    return no


def _constantes(fonte: str) -> dict:
    numeros = {
        nome: int(valor)
        for nome, valor in re.findall(r"(?:export\s+)?const\s+(\w+)\s*=\s*(\d+)\s*;", fonte)
    }
    regexes = {}
    for nome, corpo, flags in re.findall(
        r"(?:export\s+)?const\s+(\w+)\s*=\s*/(.+)/([a-z]*)\s*;", fonte
    ):
        # Flag muda a semântica (`i`, `m`, `s`...) e o JSON Schema não tem como dizê-la.
        assert not flags, f"a regex {nome} tem flags ({flags}): o JSON Schema não as expressa"
        # Em TS a barra é escapada dentro do literal de regex.
        regexes[nome] = corpo.replace("\\/", "/")
    return {**numeros, **regexes}


def _numero(valor, constantes: dict) -> int:
    if isinstance(valor, int):
        return valor
    assert isinstance(valor, dict) and not valor["metodos"] and valor["args"] is None, valor
    assert valor["base"] in constantes, f"constante desconhecida: {valor['base']}"
    return constantes[valor["base"]]


_LIMITES = {
    "string": ("minLength", "maxLength"),
    "number": ("minimum", "maximum"),
    "integer": ("minimum", "maximum"),
    "array": ("minItems", "maxItems"),
}


def _traduzir(no: dict, fonte: str, constantes: dict) -> tuple[dict, bool]:
    """Nó do Zod → (fragmento de JSON Schema, opcional?)."""
    base, args = no["base"], no["args"]

    if base == "string":
        schema: dict = {"type": "string"}
    elif base == "number":
        schema = {"type": "number"}
    elif base == "enum":
        (valores,) = args
        schema = {"type": "string", "enum": sorted(valores)}
    elif base == "array":
        (itens,) = args
        schema = {"type": "array", "items": _traduzir(itens, fonte, constantes)[0]}
    elif base == "object":
        (campos,) = args
        propriedades, obrigatorios = {}, []
        for nome, valor in campos.items():
            propriedades[nome], opcional = _traduzir(valor, fonte, constantes)
            if not opcional:
                obrigatorios.append(nome)
        schema = {"type": "object", "properties": propriedades, "required": sorted(obrigatorios)}
    elif base == "texto":
        # O helper conta code points, que é como o JSON Schema conta (ver schema.ts).
        assert re.search(r"function texto\(min: number, max: number\)", fonte)
        assert "Array.from(valor).length" in fonte, "texto() deixou de contar code points"
        minimo, maximo = (_numero(a, constantes) for a in args)
        schema = {"type": "string", "minLength": minimo, "maxLength": maximo}
    elif args is None and re.search(rf"const\s+{base}\s*=\s*z\b", fonte):
        schema, _ = _traduzir(_declaracao(fonte, base), fonte, constantes)
    else:
        raise AssertionError(f"construção do Zod que o espelho não sabe traduzir: {base}")

    opcional = False
    for metodo, margs in no["metodos"]:
        if metodo == "int":
            assert schema["type"] == "number", ".int() fora de número"
            schema["type"] = "integer"
        elif metodo in ("min", "max"):
            chave = _LIMITES[schema["type"]][0 if metodo == "min" else 1]
            schema[chave] = _numero(margs[0], constantes)
        elif metodo == "regex":
            nome = margs[0]["base"]
            assert nome in constantes, f"regex {nome} não é uma constante de schema.ts"
            schema["pattern"] = constantes[nome]
        elif metodo == "strict":
            assert schema["type"] == "object", ".strict() fora de objeto"
            schema["additionalProperties"] = False
        elif metodo == "optional":
            opcional = True
        elif metodo == "superRefine":
            schema["allOf"] = _condicionais_do_zod(margs[0], fonte)
        else:
            raise AssertionError(f"método do Zod que o espelho não sabe traduzir: .{metodo}()")
    return schema, opcional


def _condicionais_do_zod(corpo: str, fonte: str) -> dict[str, list[str]]:
    """A tabela `OBRIGATORIOS_POR_WIDGET`, conferindo que o superRefine a aplica."""
    assert re.search(
        r"for \(const (\w+) of OBRIGATORIOS_POR_WIDGET\[valor\.widget\]\)", corpo
    ), "o superRefine não percorre OBRIGATORIOS_POR_WIDGET"
    assert re.search(r"valor\[campo\] === undefined", corpo), (
        "o superRefine não confere a ausência do campo obrigatório"
    )
    assert "ctx.addIssue" in corpo
    # Nada além da tabela: um `if` a mais seria uma regra que o espelho não compara.
    assert not re.search(r"\bif\s*\((?!valor\[campo\] === undefined\))", corpo), (
        "o superRefine tem uma condição que o espelho não sabe comparar"
    )

    bloco = re.search(
        r"const OBRIGATORIOS_POR_WIDGET\s*=\s*\{(.*?)\}\s*as const;", fonte, re.DOTALL
    )
    assert bloco, "schema.ts não declara OBRIGATORIOS_POR_WIDGET"
    return {
        widget: sorted(re.findall(r'"(\w+)"', campos))
        for widget, campos in re.findall(r"(\w+):\s*\[([^\]]*)\]", bloco.group(1))
        if re.findall(r'"(\w+)"', campos)
    }


def _condicionais_do_json(all_of: list) -> dict[str, list[str]]:
    """O `allOf` canônico como widget → campos exigidos.

    Só sabe ler a forma "se o widget é X, então exija Y". Condicional de outra forma
    faz o teste falhar: é regra nova, e o espelho precisa aprender a compará-la.
    """
    exigidos: dict[str, set[str]] = {}
    for regra in all_of:
        assert set(regra) == {"if", "then"}, f"condicional que o espelho não lê: {regra}"
        se, entao = regra["if"], regra["then"]
        assert set(se) == {"properties", "required"} and se["required"] == ["widget"], se
        assert set(se["properties"]) == {"widget"}, se
        widget = se["properties"]["widget"]
        assert set(widget) in ({"enum"}, {"const"}), se
        widgets = widget.get("enum") or [widget["const"]]
        assert set(entao) == {"required"}, entao
        for w in widgets:
            exigidos.setdefault(w, set()).update(entao["required"])
    return {w: sorted(campos) for w, campos in exigidos.items()}


def _normalizar(schema):
    """Tira o que é só documentação e põe listas sem ordem semântica em ordem."""
    if isinstance(schema, dict):
        saida = {}
        for chave, valor in schema.items():
            if chave in SO_DOCUMENTACAO:
                continue
            if chave in ("enum", "required"):
                saida[chave] = sorted(valor)
            elif chave == "allOf":
                saida[chave] = _condicionais_do_json(valor)
            else:
                saida[chave] = _normalizar(valor)
        return saida
    if isinstance(schema, list):
        return [_normalizar(v) for v in schema]
    return schema


def _do_zod() -> dict:
    fonte = re.sub(r"/\*.*?\*/", "", _zod(), flags=re.DOTALL)
    constantes = _constantes(fonte)
    schema, opcional = _traduzir(_declaracao(fonte, "zonePayloadSchema"), fonte, constantes)
    assert not opcional
    return schema


def _no(schema: dict, caminho: str) -> dict:
    """`items[].href` → o fragmento daquele campo, sem os filhos (comparados à parte)."""
    no = schema
    for parte in filter(None, caminho.split(".")):
        if parte.endswith("[]"):
            no = no["properties"][parte[:-2]]["items"]
        else:
            no = no["properties"][parte]
    return {k: v for k, v in no.items() if k not in ("properties", "items", "allOf")}


def _caminhos(schema: dict, prefixo: str = "") -> list[str]:
    caminhos = [prefixo]
    for nome, filho in schema.get("properties", {}).items():
        caminho = f"{prefixo}.{nome}" if prefixo else nome
        caminhos.extend(_caminhos(filho, caminho))
        if filho.get("type") == "array" and isinstance(filho.get("items"), dict):
            caminhos.extend(_caminhos(filho["items"], f"{caminho}[]"))
    return caminhos


CAMPOS = _caminhos(_normalizar(_canonico()))


# --------------------------------------------------------------------------- #
# A comparação
# --------------------------------------------------------------------------- #


def test_os_dois_arquivos_existem():
    assert contracts.caminho_do_contrato(contracts.RESUMO_FINANCEIRO).exists()
    assert ZOD.exists()


def test_o_espelho_cobre_todos_os_campos_do_contrato():
    """Os dois níveis, cada propriedade e o item da lista estão na comparação."""
    assert set(CAMPOS) >= {
        "", "widget", "label", "maxItems", "tone", "items",
        "items[]", "items[].label", "items[].href",
    }


@pytest.mark.parametrize("campo", CAMPOS, ids=lambda c: c or "raiz")
def test_campo_a_campo(campo):
    """Tipo, enum, limites, obrigatórios, propriedades extras e regex de cada campo."""
    do_json = _no(_normalizar(_canonico()), campo)
    do_zod = _no(_do_zod(), campo)

    assert do_zod == do_json, f"{campo or 'raiz'}: Zod {do_zod} vs JSON Schema {do_json}"


def test_mesmos_campos_nos_dois_niveis():
    canonico, zod = _normalizar(_canonico()), _do_zod()

    assert set(zod["properties"]) == set(canonico["properties"])
    assert (
        set(zod["properties"]["items"]["items"]["properties"])
        == set(canonico["properties"]["items"]["items"]["properties"])
    )


def test_mesmos_condicionais_por_widget():
    """Qual widget exige quais campos: o `allOf` do JSON e a tabela do Zod."""
    assert _do_zod()["allOf"] == _normalizar(_canonico())["allOf"]


def test_traducao_inteira_e_igual_ao_canonico():
    """Rede final: nenhuma palavra do contrato fica de fora da comparação acima."""
    assert _do_zod() == _normalizar(_canonico())


def test_o_tradutor_recusa_construcao_que_nao_conhece():
    """Sem isto, um `.nullable()` novo passaria pelo espelho sem ser comparado."""
    fonte = _zod().replace(".strict()\n  .superRefine", ".strict()\n  .nullable()\n  .superRefine")
    with pytest.raises(AssertionError, match="nullable"):
        _traduzir(_declaracao(fonte, "zonePayloadSchema"), fonte, _constantes(fonte))


def test_o_tradutor_percebe_um_limite_divergente():
    fonte = _zod().replace("export const LABEL_MAX = 40;", "export const LABEL_MAX = 41;")
    schema, _ = _traduzir(_declaracao(fonte, "zonePayloadSchema"), fonte, _constantes(fonte))

    assert schema != _normalizar(_canonico())


def test_o_tradutor_percebe_um_condicional_divergente():
    canonico = copy.deepcopy(_canonico())
    canonico["allOf"][1]["then"]["required"] = ["tone", "items"]

    assert _do_zod()["allOf"] != _normalizar(canonico)["allOf"]


# --------------------------------------------------------------------------- #
# As duas divergências de semântica que o texto dos schemas não mostra
# --------------------------------------------------------------------------- #


def test_href_com_quebra_de_linha_final_e_recusado_como_no_cliente():
    """No ECMA, `$` só casa no fim; no `re` do Python, também antes de um `\\n` final."""
    payload = {
        "widget": "shortcut_list",
        "label": "Metas",
        "maxItems": 1,
        "items": [{"label": "Metas", "href": "/metas\n"}],
    }

    assert not contracts.valido(contracts.RESUMO_FINANCEIRO, payload)


@pytest.mark.parametrize("quantos, aceito", [(40, True), (41, False)])
def test_tamanho_do_label_conta_caracteres_como_o_cliente(quantos, aceito):
    """Emoji é um caractere para o JSON Schema e para o `texto()` do schema.ts."""
    payload = {"widget": "alert_banner", "label": "💰" * quantos, "tone": "neutral"}

    assert contracts.valido(contracts.RESUMO_FINANCEIRO, payload) is aceito


def test_o_registry_de_widgets_do_cliente_cobre_o_contrato():
    """Widget previsto no contrato mas ausente do registry viraria violação."""
    previstos = set(_canonico()["properties"]["widget"]["enum"])

    registry = WIDGETS.read_text(encoding="utf-8")
    # o corpo do objeto começa no `= {` da declaração, não na primeira chave que
    # aparecer - a anotação de tipo também tem uma
    bloco = re.search(r"export const WIDGETS.*?=\s*\{(.*?)\n\};", registry, re.DOTALL).group(1)
    implementados = set(re.findall(r"^\s*(\w+):", bloco, re.MULTILINE))

    assert previstos == implementados, (
        f"contrato e registry divergem: contrato {previstos}, registry {implementados}"
    )
