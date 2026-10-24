/**
 * Primitivas do painel.
 *
 * Toda tela compõe estas peças em vez de repetir classes. O motivo é menos
 * estético do que parece: um botão de perigo que tem a mesma cara em todo lugar
 * é um botão que a pessoa reconhece antes de ler - e é numa tela de decisão
 * que reconhecer rápido importa.
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

// --------------------------------------------------------------------------- //
// Tons
// --------------------------------------------------------------------------- //

export type Tom = "neutro" | "ok" | "warn" | "bad" | "info" | "zone" | "signal";

const TEXTO_DO_TOM: Record<Tom, string> = {
  neutro: "text-ink-2 border-line-strong/70 bg-sunken",
  ok: "text-ok border-ok/25 bg-ok/[0.07]",
  warn: "text-warn border-warn/30 bg-warn/[0.08]",
  bad: "text-bad border-bad/25 bg-bad/[0.07]",
  info: "text-info border-info/25 bg-info/[0.07]",
  zone: "text-zone border-zone/25 bg-zone/[0.07]",
  signal: "text-signal border-signal/30 bg-signal/[0.08]",
};

const PONTO_DO_TOM: Record<Tom, string> = {
  neutro: "bg-ink-3",
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  info: "bg-info",
  zone: "bg-zone",
  signal: "bg-signal",
};

/** Etiqueta curta: estado, risco, módulo. Mono e pequena, para não competir com o título. */
export function Tag({
  children,
  tom = "neutro",
  ponto,
  title,
}: {
  children: ReactNode;
  tom?: Tom;
  ponto?: boolean;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border px-1.5 py-px font-mono text-[11px] leading-[18px] ${TEXTO_DO_TOM[tom]}`}
    >
      {ponto && <span className={`h-1.5 w-1.5 rounded-full ${PONTO_DO_TOM[tom]}`} />}
      {children}
    </span>
  );
}

/** Ponto de estado, para listas densas onde a etiqueta inteira seria ruído. */
export function Ponto({ tom, pulsando }: { tom: Tom; pulsando?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      {pulsando && (
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-50 ${PONTO_DO_TOM[tom]}`}
        />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${PONTO_DO_TOM[tom]}`} />
    </span>
  );
}

// --------------------------------------------------------------------------- //
// Botões
// --------------------------------------------------------------------------- //

type Variante = "primario" | "secundario" | "fantasma" | "perigo" | "sinal";

const VARIANTE: Record<Variante, string> = {
  primario: "bg-ink text-bg border-ink hover:bg-ink/85",
  secundario: "bg-surface text-ink border-line-strong hover:border-ink-3 hover:bg-sunken",
  fantasma: "bg-transparent text-ink-2 border-transparent hover:bg-sunken hover:text-ink",
  perigo: "bg-surface text-bad border-bad/35 hover:bg-bad/[0.06] hover:border-bad/60",
  sinal: "bg-signal text-white border-signal hover:bg-signal/90",
};

export function Botao({
  variante = "secundario",
  tamanho = "md",
  ocupado,
  children,
  className = "",
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: Variante;
  tamanho?: "sm" | "md";
  ocupado?: boolean;
}) {
  const medida = tamanho === "sm" ? "h-7 px-2.5 text-[12.5px]" : "h-9 px-3.5 text-[13.5px]";
  return (
    <button
      type="button"
      {...resto}
      disabled={resto.disabled || ocupado}
      aria-busy={ocupado || undefined}
      className={`inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${medida} ${VARIANTE[variante]} ${className}`}
    >
      {ocupado && <Girando />}
      {children}
    </button>
  );
}

export function Girando() {
  return (
    <span
      aria-hidden
      className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-current border-r-transparent"
    />
  );
}

// --------------------------------------------------------------------------- //
// Superfícies
// --------------------------------------------------------------------------- //

/** Bloco com borda. `titulo` vira sobretítulo; `acoes` ficam à direita dele. */
export function Secao({
  titulo,
  acoes,
  children,
  className = "",
  semRecuo,
  id,
}: {
  titulo?: ReactNode;
  acoes?: ReactNode;
  children: ReactNode;
  className?: string;
  semRecuo?: boolean;
  id?: string;
}) {
  return (
    <section id={id} className={`rounded border border-line bg-surface ${className}`}>
      {(titulo || acoes) && (
        <header className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2">
          {titulo && <h2 className="eyebrow">{titulo}</h2>}
          {acoes && <div className="ml-auto flex flex-wrap items-center gap-2">{acoes}</div>}
        </header>
      )}
      <div className={semRecuo ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function Vazio({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-line-strong/80 px-6 py-10 text-center">
      <p className="font-display text-[22px] leading-tight text-ink-2">{titulo}</p>
      {children && <p className="mx-auto mt-2 max-w-md text-[13px] text-ink-3">{children}</p>}
    </div>
  );
}

export function Carregando({ texto = "Carregando" }: { texto?: string }) {
  return (
    <p className="flex items-center gap-2 py-6 text-[13px] text-ink-3">
      <Girando /> {texto}…
    </p>
  );
}

/** Número com rótulo - contadores e medidas. */
export function Medida({
  rotulo,
  valor,
  tom,
  detalhe,
}: {
  rotulo: string;
  valor: ReactNode;
  tom?: Tom;
  detalhe?: ReactNode;
}) {
  const cor = tom === "signal" ? "text-signal" : tom === "bad" ? "text-bad" : "text-ink";
  return (
    <div className="min-w-0">
      <p className="eyebrow truncate">{rotulo}</p>
      <p className={`tnum mt-1 font-mono text-[22px] font-medium leading-none ${cor}`}>{valor}</p>
      {detalhe && <p className="mt-1.5 text-[12px] text-ink-3">{detalhe}</p>}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Formulários
// --------------------------------------------------------------------------- //

export const ENTRADA =
  "w-full rounded border border-line-strong bg-surface px-2.5 py-[7px] text-[13.5px] text-ink placeholder:text-ink-3 transition-colors hover:border-ink-3 focus:border-ink focus:outline-none";

export const AREA_TEXTO = `${ENTRADA} leading-relaxed`;

export function Campo({
  rotulo,
  dica,
  children,
  className = "",
}: {
  rotulo: string;
  dica?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">{rotulo}</span>
      {children}
      {dica && <span className="mt-1.5 block text-[12px] text-ink-3">{dica}</span>}
    </label>
  );
}

// --------------------------------------------------------------------------- //
// Abas
// --------------------------------------------------------------------------- //

export function Abas<T extends string>({
  abas,
  atual,
  onTrocar,
}: {
  abas: { id: T; rotulo: string; contagem?: number; desabilitada?: boolean; sinal?: boolean }[];
  atual: T;
  onTrocar: (id: T) => void;
}) {
  return (
    <div role="tablist" className="flex gap-5 overflow-x-auto border-b border-line">
      {abas.map((aba) => {
        const ativa = aba.id === atual;
        return (
          <button
            key={aba.id}
            role="tab"
            type="button"
            aria-selected={ativa}
            disabled={aba.desabilitada}
            onClick={() => onTrocar(aba.id)}
            className={`-mb-px flex shrink-0 items-center gap-2 border-b-2 pb-2.5 pt-1 text-[13.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
              ativa
                ? "border-ink font-medium text-ink"
                : "border-transparent text-ink-3 hover:text-ink"
            }`}
          >
            {aba.rotulo}
            {aba.contagem !== undefined && (
              <span
                className={`tnum rounded-sm px-1 font-mono text-[11px] ${
                  aba.sinal && aba.contagem > 0
                    ? "bg-signal text-white"
                    : ativa
                      ? "bg-ink text-bg"
                      : "bg-sunken text-ink-3"
                }`}
              >
                {aba.contagem}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Código
// --------------------------------------------------------------------------- //

export function BlocoDeCodigo({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <pre
      className={`overflow-auto rounded border border-line bg-sunken p-3 font-mono text-[12px] leading-relaxed text-ink-2 ${className}`}
    >
      {children}
    </pre>
  );
}

/** Diff unificado com as linhas coloridas pelo sinal. */
export function Diff({ texto }: { texto: string }) {
  return (
    <pre className="font-mono text-[12px] leading-[1.6]">
      {texto.split("\n").map((linha, i) => {
        const cabecalho = linha.startsWith("+++") || linha.startsWith("---");
        const estilo = cabecalho
          ? "text-ink font-medium"
          : linha.startsWith("+")
            ? "bg-ok/[0.09] text-ok"
            : linha.startsWith("-")
              ? "bg-bad/[0.08] text-bad"
              : linha.startsWith("@@")
                ? "text-info"
                : linha.startsWith("diff ")
                  ? "mt-3 border-t border-line pt-3 text-ink font-medium"
                  : "text-ink-3";
        return (
          <div key={i} className={`-mx-3 px-3 ${estilo}`}>
            {linha || " "}
          </div>
        );
      })}
    </pre>
  );
}
