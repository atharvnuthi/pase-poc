"use client";

import { useCallback, useEffect, useState } from "react";

import { AREA_TEXTO, Botao } from "@/components/ui";
import {
  enviarSugestao,
  formatarDia,
  minhasSugestoes,
  situacaoLegivel,
  type MinhaSugestao,
  type Tom,
} from "@/lib/sugestoes";

/**
 * Modal "Sugerir melhoria" - a Captação Ativa do PASE (SPEC-03 §1).
 *
 * Duas vistas: escrever uma sugestão nova, e acompanhar as que a pessoa já
 * mandou, com a decisão que o PASE tomou sobre cada uma (§4.3.1). Se o pase-core
 * estiver fora do ar, o envio diz que falhou e mantém o texto - nunca finge que
 * registrou - e o resto do app continua funcionando (SPEC-02 §2).
 */

type Vista = "nova" | "minhas";

type Retorno = { tipo: "ok" | "erro"; texto: string };

const SELO: Record<Tom, string> = {
  neutro: "border-line-strong text-ink-muted",
  andamento: "border-brand/30 bg-brand/5 text-brand-ink",
  positivo: "border-brand/40 bg-brand/10 text-brand-ink",
  negativo: "border-danger/30 bg-danger-soft text-danger",
};

export default function SuggestModal({ userId }: { userId: number }) {
  const [open, setOpen] = useState(false);
  const [vista, setVista] = useState<Vista>("nova");
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<Retorno | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;

    setSending(true);
    setFeedback(null);
    try {
      const detalhe = await enviarSugestao(userId, text);
      setFeedback({ tipo: "ok", texto: detalhe ?? "Sugestão recebida." });
      setText("");
    } catch {
      // O texto fica no campo: a pessoa tenta de novo sem reescrever.
      setFeedback({
        tipo: "erro",
        texto: "Não foi possível enviar sua sugestão agora. Tente de novo em instantes.",
      });
    } finally {
      setSending(false);
    }
  }

  function fechar() {
    setOpen(false);
    setFeedback(null);
    setVista("nova");
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-3 text-sm font-medium text-on-ink shadow-lift transition hover:bg-ink/85 focus-visible:outline-none focus-visible:shadow-focus"
      >
        <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4">
          <path
            d="M10 3v14M3 10h14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
          />
        </svg>
        Sugerir melhoria
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse/50 p-4 backdrop-blur-[2px]">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Sugerir melhoria"
            className="w-full max-w-md rounded-xl border border-line-strong bg-surface p-6 shadow-lift"
          >
            <h2 className="font-display text-[1.75rem] leading-tight">Sugerir melhoria</h2>

            <div className="mt-4 grid grid-cols-2 rounded-lg border border-line p-0.5 text-sm">
              {(
                [
                  ["nova", "Nova sugestão"],
                  ["minhas", "Minhas sugestões"],
                ] as const
              ).map(([valor, rotulo]) => (
                <button
                  key={valor}
                  type="button"
                  aria-pressed={vista === valor}
                  onClick={() => setVista(valor)}
                  className={`h-8 rounded-md font-medium transition ${
                    vista === valor ? "bg-ink text-on-ink" : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {rotulo}
                </button>
              ))}
            </div>

            {vista === "nova" ? (
              <form onSubmit={submit} className="mt-5 space-y-4">
                <p className="text-sm text-ink-muted">
                  O que você gostaria que o FinTrack fizesse?
                </p>
                <textarea
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  rows={4}
                  aria-label="Sua sugestão"
                  placeholder="Ex.: exportar minhas transações em CSV"
                  className={AREA_TEXTO}
                />

                {feedback && (
                  <p
                    role="status"
                    className={`rounded-lg border px-4 py-3 text-sm ${
                      feedback.tipo === "ok"
                        ? "border-brand/25 bg-brand/5 text-brand-ink"
                        : "border-danger/30 bg-danger-soft text-danger"
                    }`}
                  >
                    {feedback.texto}
                  </p>
                )}

                <div className="flex justify-end gap-2">
                  <Botao type="button" variante="neutro" onClick={fechar}>
                    Fechar
                  </Botao>
                  <Botao type="submit" variante="marca" disabled={sending || !text.trim()}>
                    {sending ? "Enviando…" : "Enviar"}
                  </Botao>
                </div>
              </form>
            ) : (
              <div className="mt-5 space-y-4">
                <MinhasSugestoes userId={userId} />
                <div className="flex justify-end">
                  <Botao type="button" variante="neutro" onClick={fechar}>
                    Fechar
                  </Botao>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

/** A lista é buscada a cada vez que a vista abre: a decisão pode ter mudado. */
function MinhasSugestoes({ userId }: { userId: number }) {
  const [sugestoes, setSugestoes] = useState<MinhaSugestao[] | null>(null);
  const [falhou, setFalhou] = useState(false);

  const carregar = useCallback(async () => {
    setFalhou(false);
    try {
      setSugestoes(await minhasSugestoes(userId));
    } catch {
      setFalhou(true);
    }
  }, [userId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (falhou) {
    return (
      <p role="status" className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
        Não foi possível carregar suas sugestões agora.
      </p>
    );
  }
  if (sugestoes === null) {
    return <p className="text-sm text-ink-muted">Carregando…</p>;
  }
  if (sugestoes.length === 0) {
    return <p className="text-sm text-ink-muted">Você ainda não enviou nenhuma sugestão.</p>;
  }

  return (
    <ul className="max-h-[22rem] divide-y divide-line overflow-y-auto rounded-lg border border-line">
      {sugestoes.map((s) => {
        const situacao = situacaoLegivel(s.situacao);
        return (
          <li key={s.id} className="px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <p className="min-w-0 text-sm font-medium text-ink">{s.titulo || s.texto}</p>
              <span
                className={`shrink-0 rounded-sm border px-2 py-0.5 text-[0.6875rem] font-semibold ${SELO[situacao.tom]}`}
              >
                {situacao.rotulo}
              </span>
            </div>
            {s.titulo && <p className="mt-0.5 text-xs text-ink-subtle">“{s.texto}”</p>}
            <p className="mt-1.5 text-sm text-ink-muted">{s.detalhe}</p>
            <p className="mt-1 text-xs text-ink-subtle">{formatarDia(s.criada_em)}</p>
          </li>
        );
      })}
    </ul>
  );
}
