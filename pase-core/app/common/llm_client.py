"""Contrato único de chamada a LLM (SPEC-01 §6, SPEC-08 §1).

Nenhum outro módulo do pase-core pode falar com um provider diretamente.

    chat(messages, *, json_schema=None, temperature=0.2, model=None, tags={}) -> (content, usage)
    embed(text) -> list[float]

Regras que este módulo garante:
- todo chamada tem um `trace_id` próprio e é registrada (tabela `llm_calls` + log
  estruturado), com `model`, `tokens_in`, `tokens_out` e `tags`;
- saída JSON tem parse estrito e **uma** retentativa automática com mensagem de
  correção; se a segunda também falhar, levanta `LLMJSONError` - quem chamou decide
  o que fazer, nunca travar o pipeline (SPEC-08 §1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.common.config import settings

logger = logging.getLogger("pase.llm")

JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class LLMError(RuntimeError):
    """Falha de comunicação ou de configuração do provider."""


class LLMJSONError(LLMError):
    """O modelo não devolveu JSON válido nem após a retentativa."""


@dataclass
class Usage:
    trace_id: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: int = 0
    attempts: int = 1
    tags: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "provider": self.provider,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "tags": self.tags,
        }


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #


class Provider(Protocol):
    name: str

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        model: str,
        reasoning_effort: str | None = None,
    ) -> tuple[str, int, int]:
        """Devolve (texto, tokens_in, tokens_out).

        `reasoning_effort` só tem efeito em modelos de raciocínio; os demais o
        ignoram, assim como os de raciocínio ignoram `temperature`.
        """

    def embed(self, text: str, *, model: str) -> tuple[list[float], int]:
        """Devolve (vetor, tokens_in)."""


#: Prefixos dos modelos de raciocínio da OpenAI. Eles **não** aceitam
#: `temperature` (recusam com 400) e os `-codex` nem existem no endpoint de chat
#: (404) - só na Responses API. Medido em outubro de 2026, contra a chave do
#: projeto, antes de trocar o modelo do Executor.
PREFIXOS_DE_RACIOCINIO = ("gpt-5", "o1", "o3", "o4")


def e_modelo_de_raciocinio(model: str) -> bool:
    return model.startswith(PREFIXOS_DE_RACIOCINIO)


class OpenAIProvider:
    name = "openai"

    #: Raciocínio em esforço alto sobre um prompt de dezenas de milhares de
    #: tokens leva minutos. O padrão do SDK cortaria uma chamada legítima.
    TIMEOUT_S = 900

    def __init__(self, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=self.TIMEOUT_S)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        model: str,
        reasoning_effort: str | None = None,
    ) -> tuple[str, int, int]:
        if e_modelo_de_raciocinio(model):
            # Na Responses API o "pensar" é pago em tokens de saída - por isso
            # `output_tokens` já inclui o raciocínio e o guardrail de budget o
            # enxerga sem nenhum ajuste.
            resp = self._client.responses.create(
                model=model,
                input=messages,
                reasoning={"effort": reasoning_effort or "medium"},
            )
            usage = resp.usage
            return (
                resp.output_text or "",
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            )

        resp = self._client.chat.completions.create(
            model=model, messages=messages, temperature=temperature
        )
        usage = resp.usage
        return (
            resp.choices[0].message.content or "",
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def embed(self, text: str, *, model: str) -> tuple[list[float], int]:
        resp = self._client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding, getattr(resp.usage, "prompt_tokens", 0) or 0


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        model: str,
        reasoning_effort: str | None = None,
    ) -> tuple[str, int, int]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        resp = self._client.messages.create(
            model=model,
            max_tokens=8192,
            temperature=temperature,
            system=system or None,
            messages=convo,
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return text, resp.usage.input_tokens, resp.usage.output_tokens

    def embed(self, text: str, *, model: str) -> tuple[list[float], int]:
        raise LLMError(
            "A Anthropic não expõe endpoint de embeddings. "
            "Configure EMBEDDING_PROVIDER=openai (ou mock)."
        )


class MockProvider:
    """Provider determinístico para testes e para rodar sem chave.

    `responses` é uma fila consumida por `complete`; esgotada, o mock sintetiza
    uma resposta que satisfaz o schema pedido (ou um eco, se não houver schema).
    O embedding é um hashing de palavras normalizado, o que preserva a noção de
    similaridade (textos parecidos → cosseno alto) sem rede.
    """

    name = "mock"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses: list[str] = list(responses or [])
        self.calls: list[list[dict[str, str]]] = []
        #: Modelo pedido em cada chamada - permite testar que cada etapa usa o seu.
        self.models: list[str] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        model: str,
        reasoning_effort: str | None = None,
    ) -> tuple[str, int, int]:
        self.calls.append(messages)
        self.models.append(model)
        if self.responses:
            text = self.responses.pop(0)
        else:
            schema = _extract_schema(messages)
            text = json.dumps(_stub_for(schema), ensure_ascii=False) if schema else "resposta mock"
        tokens_in = max(1, sum(len(m["content"]) for m in messages) // 4)
        return text, tokens_in, max(1, len(text) // 4)

    def embed(self, text: str, *, model: str) -> tuple[list[float], int]:
        dim = settings.embedding_dim
        vec = [0.0] * dim
        for word in re.findall(r"\w+", text.lower()):
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm:
            vec = [v / norm for v in vec]
        else:
            vec[0] = 1.0
        return vec, max(1, len(text) // 4)


SCHEMA_MARKER = "obedecer a este schema:"


def _extract_schema(messages: list[dict[str, str]]) -> dict[str, Any] | None:
    """Recupera o schema embutido pela `chat()` na mensagem de instrução."""
    for message in reversed(messages):
        marker = message["content"].find(SCHEMA_MARKER)
        if marker == -1:
            continue
        try:
            return json.loads(message["content"][marker + len(SCHEMA_MARKER) :])
        except json.JSONDecodeError:
            return None
    return None


def _stub_for(schema: dict[str, Any]) -> Any:
    """Menor valor que satisfaz o schema - só o suficiente para o mock."""
    kind = schema.get("type", "object")
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required") or list(properties)
        return {key: _stub_for(properties.get(key, {})) for key in required}
    if kind == "array":
        return []
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True
    if "enum" in schema:
        return schema["enum"][0]
    return "mock"


_chat_provider: Provider | None = None
_embed_provider: Provider | None = None


def _build(provider_name: str, api_key: str) -> Provider:
    if provider_name == "mock":
        return MockProvider()
    if not api_key:
        raise LLMError(
            f"Provider '{provider_name}' selecionado sem chave de API. "
            "Preencha LLM_API_KEY/EMBEDDING_API_KEY no .env ou use o provider 'mock'."
        )
    if provider_name == "openai":
        return OpenAIProvider(api_key)
    if provider_name == "anthropic":
        return AnthropicProvider(api_key)
    raise LLMError(f"Provider desconhecido: {provider_name}")


def chat_provider() -> Provider:
    global _chat_provider
    if _chat_provider is None:
        _chat_provider = _build(settings.llm_provider, settings.llm_api_key)
    return _chat_provider


def embed_provider() -> Provider:
    global _embed_provider
    if _embed_provider is None:
        if settings.embedding_provider == settings.llm_provider:
            _embed_provider = chat_provider()
        else:
            _embed_provider = _build(settings.embedding_provider, settings.embedding_key)
    return _embed_provider


def set_providers(chat: Provider | None = None, embed: Provider | None = None) -> None:
    """Injeta providers - usado pelos testes e pelo modo demo."""
    global _chat_provider, _embed_provider
    if chat is not None:
        _chat_provider = chat
    if embed is not None:
        _embed_provider = embed


def reset_providers() -> None:
    global _chat_provider, _embed_provider
    _chat_provider = None
    _embed_provider = None


# --------------------------------------------------------------------------- #
# Registro das chamadas
# --------------------------------------------------------------------------- #


def _record(kind: str, usage: Usage, temperature: float | None, error: str | None) -> None:
    payload = {"event": "llm_call", "kind": kind, "error": error, **usage.as_dict()}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))

    # O log estrutura; a tabela é o que torna a decisão rastreável (SPEC-00 §2).
    # Um banco indisponível nunca pode derrubar a chamada de LLM.
    try:
        from app.common.db import session_scope
        from app.common.models import LLMCall

        with session_scope() as session:
            session.add(
                LLMCall(
                    trace_id=usage.trace_id,
                    kind=kind,
                    provider=usage.provider,
                    model=usage.model,
                    temperature=temperature,
                    tokens_in=usage.tokens_in,
                    tokens_out=usage.tokens_out,
                    duration_ms=usage.duration_ms,
                    attempts=usage.attempts,
                    tags=usage.tags,
                    error=error,
                )
            )
    except Exception as exc:  # pragma: no cover - depende de infra externa
        logger.warning("não foi possível persistir llm_calls (%s): %s", usage.trace_id, exc)


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #


def _strip_fences(text: str) -> str:
    return JSON_FENCE.sub("", text.strip())


def _schema_instruction(json_schema: dict[str, Any]) -> str:
    return (
        "Responda EXCLUSIVAMENTE com um objeto JSON válido, sem texto antes ou depois "
        "e sem blocos de código markdown. O JSON deve obedecer a este schema:\n"
        f"{json.dumps(json_schema, ensure_ascii=False, indent=2)}"
    )


def _missing_required(data: Any, json_schema: dict[str, Any]) -> list[str]:
    required = json_schema.get("required") or []
    if not required or not isinstance(data, dict):
        return []
    return [key for key in required if key not in data]


def chat(
    messages: list[dict[str, str]],
    *,
    json_schema: dict[str, Any] | None = None,
    temperature: float = 0.2,
    model: str | None = None,
    reasoning_effort: str | None = None,
    tags: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Uma chamada de conversa. Devolve (conteúdo, usage).

    Com `json_schema`, o conteúdo devolvido já é o objeto Python parseado.

    Em modelo de raciocínio, `temperature` não vale e `reasoning_effort` vale; o
    registro em `llm_calls` guarda o que de fato foi usado, para que ninguém leia
    uma temperatura que nunca chegou ao provider.
    """
    provider = chat_provider()
    model_name = model or settings.llm_model
    tags = dict(tags or {})
    raciocinio = e_modelo_de_raciocinio(model_name)
    if raciocinio:
        tags["reasoning_effort"] = reasoning_effort or "medium"
    temperatura_registrada = None if raciocinio else temperature
    usage = Usage(
        trace_id=str(uuid.uuid4()),
        provider=provider.name,
        model=model_name,
        tags=tags,
    )

    convo = list(messages)
    if json_schema is not None:
        convo.append({"role": "system", "content": _schema_instruction(json_schema)})

    started = time.perf_counter()
    last_error: str | None = None
    content: Any = None

    # tentativa 1 + 1 retentativa de correção, nunca mais que isso (SPEC-00 §4)
    for attempt in (1, 2):
        usage.attempts = attempt
        try:
            raw, tokens_in, tokens_out = provider.complete(
                convo,
                temperature=temperature,
                model=model_name,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:
            usage.duration_ms = int((time.perf_counter() - started) * 1000)
            _record("chat", usage, temperatura_registrada, str(exc))
            raise LLMError(f"falha na chamada ao provider {provider.name}: {exc}") from exc

        usage.tokens_in += tokens_in
        usage.tokens_out += tokens_out

        if json_schema is None:
            content = raw
            last_error = None
            break

        try:
            parsed = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            last_error = f"JSON inválido: {exc}"
        else:
            missing = _missing_required(parsed, json_schema)
            if missing:
                last_error = f"faltam as chaves obrigatórias: {', '.join(missing)}"
            else:
                content = parsed
                last_error = None
                break

        if attempt == 2:
            break

        convo = convo + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"Sua resposta anterior não pôde ser usada ({last_error}). "
                    "Responda de novo apenas com o objeto JSON válido, "
                    "sem markdown e sem comentários."
                ),
            },
        ]

    usage.duration_ms = int((time.perf_counter() - started) * 1000)
    _record("chat", usage, temperatura_registrada, last_error)

    if last_error is not None:
        raise LLMJSONError(
            f"resposta JSON inválida após retentativa (trace_id={usage.trace_id}): {last_error}"
        )

    return content, usage.as_dict()


def embed(text: str) -> list[float]:
    """Vetor de dimensão EMBEDDING_DIM para o texto dado."""
    provider = embed_provider()
    usage = Usage(
        trace_id=str(uuid.uuid4()),
        provider=provider.name,
        model=settings.embedding_model,
        tags={"fase": "embedding"},
    )
    started = time.perf_counter()
    try:
        vector, tokens_in = provider.embed(text, model=settings.embedding_model)
    except Exception as exc:
        usage.duration_ms = int((time.perf_counter() - started) * 1000)
        _record("embed", usage, None, str(exc))
        raise LLMError(f"falha ao gerar embedding em {provider.name}: {exc}") from exc

    usage.tokens_in = tokens_in
    usage.duration_ms = int((time.perf_counter() - started) * 1000)
    _record("embed", usage, None, None)

    if len(vector) != settings.embedding_dim:
        raise LLMError(
            f"embedding com dimensão {len(vector)}, esperado {settings.embedding_dim}. "
            "Ajuste EMBEDDING_DIM/EMBEDDING_MODEL."
        )
    return vector
