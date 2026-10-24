"""Smoke test do SPEC-01 §8.2: uma chamada `chat` e uma `embed`, com tokens logados.

    docker compose exec pase-core python -m app.smoke
"""

import logging
import sys

from app.common.config import settings
from app.common.llm_client import LLMError, chat, embed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def main() -> int:
    print(f"provider de chat .......: {settings.llm_provider} ({settings.llm_model})")
    print(
        f"provider de embedding ..: {settings.embedding_provider} "
        f"({settings.embedding_model}, dim {settings.embedding_dim})"
    )

    try:
        content, usage = chat(
            [
                {
                    "role": "system",
                    "content": "Você responde em pt-BR, de forma objetiva.",
                },
                {
                    "role": "user",
                    "content": "Em uma frase: para que serve um dashboard financeiro pessoal?",
                },
            ],
            json_schema={
                "type": "object",
                "properties": {"resposta": {"type": "string"}},
                "required": ["resposta"],
            },
            temperature=0.2,
            tags={"fase": "smoke", "prompt_id": "smoke-chat"},
        )
    except LLMError as exc:
        print(f"\nFALHA no chat: {exc}")
        return 1

    print("\n[chat] ok")
    print(f"  resposta ..: {content['resposta']}")
    print(f"  trace_id ..: {usage['trace_id']}")
    print(f"  tokens ....: in={usage['tokens_in']} out={usage['tokens_out']}")
    print(f"  duração ...: {usage['duration_ms']} ms")

    try:
        vector = embed("gasto por categoria no mês")
    except LLMError as exc:
        print(f"\nFALHA no embed: {exc}")
        return 1

    print("\n[embed] ok")
    print(f"  dimensão ..: {len(vector)}")
    print(f"  amostra ...: {[round(v, 4) for v in vector[:5]]}")

    print("\nSmoke OK - as chamadas ficaram registradas em llm_calls (SELECT * FROM llm_calls).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
