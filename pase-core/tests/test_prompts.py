"""Os prompts versionados (README.md: um arquivo por prompt, nunca inline)."""

import pytest

from app.common import prompts

#: P0a preenche uma lacuna do SPEC-03 §2.2, que fala em "lote de tickets
#: correlacionados" sem dizer como a correlação é determinada.
ESPERADOS = ["P0", "P0a", "P1", "P1b", "P2a", "P2b", "P3", "P3b", "P9"]


def test_todos_os_prompts_do_spec_existem():
    assert set(ESPERADOS).issubset(set(prompts.available()))


@pytest.mark.parametrize("prompt_id", ESPERADOS)
def test_prompt_pede_json_e_esta_em_portugues(prompt_id):
    texto = prompts._read(prompt_id)

    assert "JSON" in texto, f"{prompt_id} não declara que a saída é JSON"
    assert "## Saída" in texto, f"{prompt_id} não tem seção de saída"


def test_interpolacao_substitui_todas_as_variaveis():
    rendered = prompts.render(
        "P1b",
        title="Exportar CSV",
        description="Baixar as transações em arquivo.",
        module="transacoes",
        occurrences=3,
        historico="- “Baixar em planilha” - já implementada; 2 pedido(s)",
    )

    assert "Exportar CSV" in rendered
    assert "**3**" in rendered
    assert "Baixar em planilha" in rendered
    assert "{{" not in rendered


def test_variavel_faltando_e_erro_explicito():
    """Prompt incompleto chegando ao modelo é bug silencioso caro."""
    with pytest.raises(prompts.PromptError, match="falta a variável"):
        prompts.render("P1b", title="x", description="y", module="dashboard")


def test_chaves_de_json_no_corpo_do_prompt_sobrevivem(tmp_path, monkeypatch):
    """O loader usa {{var}} justamente porque prompts carregam exemplos com {}.

    Com `str.format`, um exemplo de JSON no corpo do prompt levantaria KeyError.
    """
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    prompts._read.cache_clear()
    (tmp_path / "PX.md").write_text(
        'Devolva {"text": null} quando não houver nada. Assunto: {{assunto}}.',
        encoding="utf-8",
    )

    rendered = prompts.render("PX", assunto="teste")

    assert '{"text": null}' in rendered
    assert "Assunto: teste." in rendered
    prompts._read.cache_clear()


def test_exemplo_de_json_real_num_prompt_do_projeto():
    """P3b traz um exemplo literal de saída; ele precisa sobreviver intacto."""
    rendered = prompts.render(
        "P3b", project_context="ctx", implemented="- item", discarded="- descarte"
    )

    assert '{"text": null}' in rendered


def test_prompt_inexistente_falha():
    with pytest.raises(prompts.PromptError, match="não encontrado"):
        prompts.render("P99")


def test_catalogo_do_painel_cobre_todos_os_prompts_do_disco():
    """Prompt que existe e roda tem que aparecer na tela de Sistema."""
    from app.common.routes_system import CATALOGO_DE_PROMPTS

    no_disco = {p.stem for p in prompts.PROMPTS_DIR.glob("*.md")}
    assert {p[0] for p in CATALOGO_DE_PROMPTS} == no_disco
