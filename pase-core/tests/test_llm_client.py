"""Contrato do llm_client (SPEC-08 §1 e §4)."""

import math

import pytest

from app.common import llm_client
from app.common.config import settings
from app.common.llm_client import LLMJSONError, chat, embed

SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}, "impacto": {"type": "integer"}},
    "required": ["titulo", "impacto"],
}


def test_chat_texto_simples_devolve_conteudo_e_usage(mock_providers):
    mock_providers.responses = ["um resumo qualquer"]

    content, usage = chat([{"role": "user", "content": "oi"}], tags={"fase": "teste"})

    assert content == "um resumo qualquer"
    assert usage["trace_id"]
    assert usage["tokens_in"] > 0 and usage["tokens_out"] > 0
    assert usage["tags"] == {"fase": "teste"}
    assert usage["attempts"] == 1


def test_json_invalido_na_primeira_chamada_e_valido_na_segunda(mock_providers):
    """Critério SPEC-08 §4.2: uma retentativa automática, transparente ao chamador."""
    mock_providers.responses = [
        "{isso não é json",
        '{"titulo": "Exportar CSV", "impacto": 4}',
    ]

    content, usage = chat(
        [{"role": "user", "content": "qualifique a proposta"}], json_schema=SCHEMA
    )

    assert content == {"titulo": "Exportar CSV", "impacto": 4}
    assert usage["attempts"] == 2
    assert len(mock_providers.calls) == 2

    # a segunda chamada levou a mensagem de correção junto do histórico
    segunda = mock_providers.calls[1]
    assert any("não pôde ser usada" in m["content"] for m in segunda)


def test_json_quebrado_nas_duas_tentativas_levanta(mock_providers):
    mock_providers.responses = ["quebrado", "também quebrado"]

    with pytest.raises(LLMJSONError):
        chat([{"role": "user", "content": "x"}], json_schema=SCHEMA)

    assert len(mock_providers.calls) == 2  # nunca mais que uma retentativa


def test_json_sem_chave_obrigatoria_dispara_correcao(mock_providers):
    mock_providers.responses = ['{"titulo": "sem impacto"}', '{"titulo": "ok", "impacto": 2}']

    content, usage = chat([{"role": "user", "content": "x"}], json_schema=SCHEMA)

    assert content["impacto"] == 2
    assert usage["attempts"] == 2


def test_cercas_de_markdown_sao_toleradas(mock_providers):
    mock_providers.responses = ['```json\n{"titulo": "a", "impacto": 1}\n```']

    content, usage = chat([{"role": "user", "content": "x"}], json_schema=SCHEMA)

    assert content == {"titulo": "a", "impacto": 1}
    assert usage["attempts"] == 1


def test_modelo_exploratorio_e_registrado_no_usage(mock_providers):
    mock_providers.responses = ["ideia solta"]

    _, usage = chat(
        [{"role": "user", "content": "gere uma ideia"}],
        temperature=0.9,
        model=settings.llm_model_exploratory,
    )

    assert usage["model"] == settings.llm_model_exploratory


def test_embed_respeita_dimensao_configurada():
    vector = embed("gastos por categoria")

    assert len(vector) == settings.embedding_dim
    assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-6)


def test_embed_aproxima_textos_parecidos():
    def cos(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    base = embed("exportar minhas transações em csv")
    parecido = embed("exportar transações em csv")
    diferente = embed("minerar criptomoedas dentro do aplicativo")

    assert cos(base, parecido) > cos(base, diferente)


def test_provider_sem_chave_recusa_a_subir():
    with pytest.raises(llm_client.LLMError, match="sem chave de API"):
        llm_client._build("openai", "")


def test_mock_sintetiza_resposta_conforme_o_schema(mock_providers):
    """Sem fila de respostas, o mock devolve algo que satisfaz o schema pedido.

    É o que permite rodar o projeto inteiro com LLM_PROVIDER=mock, sem chave.
    """
    content, usage = chat(
        [{"role": "user", "content": "qualifique"}],
        json_schema={
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "impacto": {"type": "integer"},
                "risk_tier": {"type": "string", "enum": ["baixo", "medio", "alto"]},
                "arquivos": {"type": "array"},
            },
            "required": ["titulo", "impacto", "risk_tier", "arquivos"],
        },
    )

    assert usage["attempts"] == 1
    assert isinstance(content["titulo"], str)
    assert isinstance(content["impacto"], int)
    assert content["risk_tier"] == "baixo"
    assert content["arquivos"] == []


class _RespostaFalsa:
    def __init__(self, texto: str) -> None:
        self.output_text = texto
        self.usage = type("U", (), {"input_tokens": 120, "output_tokens": 45})()


class _ClienteFalso:
    """Faz as vezes do SDK da OpenAI e registra o que cada endpoint recebeu."""

    def __init__(self) -> None:
        self.pedidos: dict[str, dict] = {}
        cliente = self

        class _Responses:
            def create(self, **kwargs):
                cliente.pedidos["responses"] = kwargs
                return _RespostaFalsa("feito")

        class _Completions:
            def create(self, **kwargs):
                cliente.pedidos["chat"] = kwargs
                msg = type("M", (), {"content": "feito"})()
                escolha = type("C", (), {"message": msg})()
                uso = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()
                return type("R", (), {"choices": [escolha], "usage": uso})()

        self.responses = _Responses()
        self.chat = type("Chat", (), {"completions": _Completions()})()


def _provider_com(cliente: _ClienteFalso) -> llm_client.OpenAIProvider:
    provider = object.__new__(llm_client.OpenAIProvider)
    provider._client = cliente
    return provider


@pytest.mark.parametrize("modelo", ["gpt-5.3-codex", "gpt-5.5", "o3-mini"])
def test_modelo_de_raciocinio_vai_pela_responses_api_sem_temperatura(modelo):
    """Os `-codex` só existem na Responses API, e nenhum deles aceita temperature."""
    cliente = _ClienteFalso()

    texto, tin, tout = _provider_com(cliente).complete(
        [{"role": "user", "content": "x"}], temperature=0.1, model=modelo,
        reasoning_effort="high",
    )

    assert (texto, tin, tout) == ("feito", 120, 45)
    assert "chat" not in cliente.pedidos
    pedido = cliente.pedidos["responses"]
    assert "temperature" not in pedido
    assert pedido["reasoning"] == {"effort": "high"}


def test_modelo_comum_continua_no_chat_com_temperatura():
    cliente = _ClienteFalso()

    _provider_com(cliente).complete(
        [{"role": "user", "content": "x"}], temperature=0.9, model="gpt-4.1-mini"
    )

    assert "responses" not in cliente.pedidos
    assert cliente.pedidos["chat"]["temperature"] == 0.9


def test_chat_registra_o_esforco_de_raciocinio(mock_providers):
    _, usage = chat(
        [{"role": "user", "content": "oi"}], model="gpt-5.5", reasoning_effort="high"
    )

    assert usage["tags"]["reasoning_effort"] == "high"


def test_modelo_de_codigo_e_de_revisao_caem_no_padrao(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "base")
    monkeypatch.setattr(settings, "llm_model_code", "")
    monkeypatch.setattr(settings, "llm_model_review", "")
    assert settings.modelo_de_codigo == "base"
    assert settings.modelo_de_revisao == "base"

    monkeypatch.setattr(settings, "llm_model_code", "codex")
    assert settings.modelo_de_revisao == "codex"  # sem revisor próprio, herda o de código

    monkeypatch.setattr(settings, "llm_model_review", "revisor")
    assert settings.modelo_de_revisao == "revisor"
