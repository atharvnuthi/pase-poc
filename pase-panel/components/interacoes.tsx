"use client";

/**
 * Diálogos e avisos do painel.
 *
 * Antes eram `window.prompt` e uma faixa de texto no topo da página. O prompt
 * do navegador não diz o que vai acontecer, não aceita texto longo e parece um
 * erro; a faixa ficava lá depois de lida, competindo com a próxima. Uma decisão
 * que vira registro - recusar, reverter, refazer - merece um lugar para dizer
 * o porquê com calma, e saber o efeito antes de confirmar.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { AREA_TEXTO, Botao, Campo, ENTRADA } from "./ui";

// --------------------------------------------------------------------------- //
// Avisos
// --------------------------------------------------------------------------- //

type TipoAviso = "ok" | "erro" | "info";
interface Aviso {
  id: number;
  texto: string;
  tipo: TipoAviso;
}

type Avisar = (texto: string, tipo?: TipoAviso) => void;

// --------------------------------------------------------------------------- //
// Pergunta
// --------------------------------------------------------------------------- //

export interface Pergunta {
  titulo: string;
  /** O que acontece se a pessoa confirmar. Aparece antes do campo. */
  efeito?: React.ReactNode;
  rotulo?: string;
  dica?: string;
  confirmar: string;
  perigo?: boolean;
  /** `true` exige texto; `false` vira só uma confirmação. */
  pedeTexto?: boolean;
  /** Mostra o campo de texto, mas deixa confirmar sem preencher. */
  opcional?: boolean;
  valorInicial?: string;
  numerico?: boolean;
  multilinha?: boolean;
  /** Caixa de seleção extra, para uma escolha que acompanha o texto. */
  opcao?: { rotulo: string; padrao: boolean; dica?: string };
}

export interface Resposta {
  texto: string;
  opcao: boolean;
}

type Perguntar = (p: Pergunta) => Promise<string | null>;
type PerguntarComOpcao = (p: Pergunta) => Promise<Resposta | null>;

const Contexto = createContext<{
  avisar: Avisar;
  perguntar: Perguntar;
  perguntarComOpcao: PerguntarComOpcao;
} | null>(null);

export function usePerguntaComOpcao(): PerguntarComOpcao {
  const c = useContext(Contexto);
  if (!c) throw new Error("usePerguntaComOpcao fora de <Interacoes>");
  return c.perguntarComOpcao;
}

export function useAviso(): Avisar {
  const c = useContext(Contexto);
  if (!c) throw new Error("useAviso fora de <Interacoes>");
  return c.avisar;
}

export function usePergunta(): Perguntar {
  const c = useContext(Contexto);
  if (!c) throw new Error("usePergunta fora de <Interacoes>");
  return c.perguntar;
}

export function Interacoes({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const [pergunta, setPergunta] = useState<Pergunta | null>(null);
  const resolver = useRef<((v: Resposta | null) => void) | null>(null);
  const proximo = useRef(1);

  const avisar = useCallback<Avisar>((texto, tipo) => {
    const id = proximo.current++;
    const t: TipoAviso = tipo ?? (/^(falhou|erro|não consegui)/i.test(texto) ? "erro" : "ok");
    setAvisos((atual) => [...atual.slice(-3), { id, texto, tipo: t }]);
    // Erro fica até alguém fechar: some sozinho só o que não exige ação.
    if (t !== "erro") {
      setTimeout(() => setAvisos((atual) => atual.filter((a) => a.id !== id)), 6000);
    }
  }, []);

  const perguntarComOpcao = useCallback<PerguntarComOpcao>((p) => {
    setPergunta(p);
    return new Promise((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const perguntar = useCallback<Perguntar>(
    (p) => perguntarComOpcao(p).then((r) => (r ? r.texto : null)),
    [perguntarComOpcao],
  );

  function responder(valor: Resposta | null) {
    resolver.current?.(valor);
    resolver.current = null;
    setPergunta(null);
  }

  return (
    <Contexto.Provider value={{ avisar, perguntar, perguntarComOpcao }}>
      {children}

      {pergunta && <Dialogo pergunta={pergunta} onResponder={responder} />}

      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(420px,calc(100vw-2rem))] flex-col gap-2"
      >
        {avisos.map((a) => (
          <div
            key={a.id}
            role="status"
            className="pointer-events-auto flex items-start gap-3 rounded border border-line-strong bg-surface p-3 text-[13px] shadow-[0_8px_24px_-12px_rgb(0_0_0/0.35)]"
          >
            <span
              className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                a.tipo === "erro" ? "bg-bad" : a.tipo === "info" ? "bg-info" : "bg-ok"
              }`}
            />
            <p className="min-w-0 flex-1 break-words text-ink">{a.texto}</p>
            <button
              type="button"
              aria-label="Fechar aviso"
              onClick={() => setAvisos((atual) => atual.filter((x) => x.id !== a.id))}
              className="-mr-1 -mt-0.5 rounded px-1 text-ink-3 hover:text-ink"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Contexto.Provider>
  );
}

function Dialogo({
  pergunta,
  onResponder,
}: {
  pergunta: Pergunta;
  onResponder: (v: Resposta | null) => void;
}) {
  const [valor, setValor] = useState(pergunta.valorInicial ?? "");
  const [marcada, setMarcada] = useState(pergunta.opcao?.padrao ?? false);
  const campo = useRef<HTMLTextAreaElement & HTMLInputElement>(null);
  const pedeTexto = pergunta.pedeTexto ?? true;

  useEffect(() => {
    campo.current?.focus();
    function esc(e: KeyboardEvent) {
      if (e.key === "Escape") onResponder(null);
    }
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onResponder]);

  const podeConfirmar = !pedeTexto || pergunta.opcional === true || valor.trim().length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-4 backdrop-blur-[2px] sm:items-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onResponder(null);
      }}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialogo-titulo"
        onSubmit={(e) => {
          e.preventDefault();
          if (podeConfirmar) onResponder({ texto: pedeTexto ? valor.trim() : "ok", opcao: marcada });
        }}
        className="w-full max-w-lg rounded border border-line-strong bg-surface shadow-[0_24px_60px_-20px_rgb(0_0_0/0.45)]"
      >
        <div className="p-5">
          <h2 id="dialogo-titulo" className="font-display text-[26px] leading-tight">
            {pergunta.titulo}
          </h2>
          {pergunta.efeito && (
            <div className="mt-2 text-[13.5px] leading-relaxed text-ink-2">{pergunta.efeito}</div>
          )}

          {pedeTexto && (
            <Campo rotulo={pergunta.rotulo ?? "Motivo"} dica={pergunta.dica} className="mt-4">
              {pergunta.multilinha === false || pergunta.numerico ? (
                <input
                  ref={campo}
                  value={valor}
                  inputMode={pergunta.numerico ? "numeric" : undefined}
                  onChange={(e) => setValor(e.target.value)}
                  className={`${ENTRADA} ${pergunta.numerico ? "tnum font-mono" : ""}`}
                />
              ) : (
                <textarea
                  ref={campo}
                  value={valor}
                  rows={4}
                  onChange={(e) => setValor(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && podeConfirmar) {
                      onResponder({ texto: valor.trim(), opcao: marcada });
                    }
                  }}
                  className={AREA_TEXTO}
                />
              )}
            </Campo>
          )}

          {pergunta.opcao && (
            <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-[13.5px]">
              <input
                type="checkbox"
                checked={marcada}
                onChange={(e) => setMarcada(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[rgb(var(--ink))]"
              />
              <span>
                <span className="text-ink">{pergunta.opcao.rotulo}</span>
                {pergunta.opcao.dica && (
                  <span className="mt-0.5 block text-[12px] text-ink-3">{pergunta.opcao.dica}</span>
                )}
              </span>
            </label>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-line bg-sunken/60 px-5 py-3">
          {pedeTexto && pergunta.multilinha !== false && !pergunta.numerico && (
            <span className="mr-auto hidden font-mono text-[11px] text-ink-3 sm:inline">
              ctrl + enter confirma
            </span>
          )}
          <Botao variante="fantasma" onClick={() => onResponder(null)}>
            Voltar
          </Botao>
          <Botao
            type="submit"
            variante={pergunta.perigo ? "perigo" : "primario"}
            disabled={!podeConfirmar}
          >
            {pergunta.confirmar}
          </Botao>
        </footer>
      </form>
    </div>
  );
}
