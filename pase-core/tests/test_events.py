"""Critério SPEC-01 §8.5: publicar um evento e recebê-lo em uma segunda conexão."""

import threading

import pytest

from app.common.events import Event, listen, publish
from tests.conftest import requires_db


@requires_db
def test_evento_publicado_chega_a_um_assinante_em_outra_conexao():
    recebidos: list[Event] = []
    assinando = threading.Event()
    erro: list[Exception] = []

    def assinante():
        try:
            for evento in listen(timeout=10, stop_after=1, on_ready=assinando.set):
                if evento is not None:
                    recebidos.append(evento)
        except Exception as exc:  # pragma: no cover
            erro.append(exc)

    thread = threading.Thread(target=assinante, daemon=True)
    thread.start()
    assert assinando.wait(timeout=10), "o LISTEN não ficou pronto a tempo"

    # publicação sai por uma conexão diferente da que está escutando
    publish("task.updated", {"task_id": 42, "status": "em_execucao"})

    thread.join(timeout=15)
    assert not erro, f"o assinante falhou: {erro}"
    assert len(recebidos) == 1

    evento = recebidos[0]
    assert evento.type == "task.updated"
    assert evento.payload == {"task_id": 42, "status": "em_execucao"}
    assert evento.at  # carimbo de tempo sempre presente


def test_payload_grande_demais_e_recusado():
    with pytest.raises(ValueError, match="grande demais"):
        publish("task.updated", {"diff": "x" * 8000})


def test_serializacao_ida_e_volta():
    original = Event(type="zone.violation", payload={"slot": "resumo_financeiro"}, at="2026-01-01")
    assert Event.from_json(original.to_json()) == original
