"""O glossário não pode envelhecer em silêncio.

Um verbete desatualizado é pior que verbete nenhum: ele afirma com confiança
algo que deixou de ser verdade. Estes testes falham quando alguém acrescenta um
estado, um alerta ou um tipo de mudança sem explicar o que ele significa.
"""

import pytest

from app.common import glossary


@pytest.mark.parametrize("vocabulario", sorted(glossary.VOCABULARIOS))
def test_todo_termo_do_codigo_tem_verbete(vocabulario):
    faltando = glossary.VOCABULARIOS[vocabulario] - glossary.termos_cobertos()

    assert not faltando, (
        f"sem verbete no glossário ({vocabulario}): {sorted(faltando)}. "
        "Acrescente em app/common/glossary.py."
    )


def test_todo_verbete_esta_completo():
    """Verbete sem 'quem atribui' ou sem 'efeito' não explica nada."""
    incompletos = [
        verbete["termo"]
        for grupo in glossary.GLOSSARIO.values()
        for verbete in grupo
        if not verbete["significado"].strip()
        or not verbete["quem_atribui"].strip()
        or not verbete["efeito"].strip()
    ]

    assert incompletos == []


def test_nao_ha_termo_repetido_entre_grupos():
    vistos = [v["termo"] for g in glossary.GLOSSARIO.values() for v in g]

    assert len(vistos) == len(set(vistos)), "o mesmo termo explicado em dois lugares diverge"
