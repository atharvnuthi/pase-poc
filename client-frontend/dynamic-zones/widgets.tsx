/**
 * Registry de widgets nativos (SPEC-05 §5.3).
 *
 * São três componentes escritos à mão, revisados e testados. O LLM só escolhe
 * qual deles usar e com que propriedades - ele nunca escreve nada disto.
 *
 * Nada aqui usa `dangerouslySetInnerHTML`, monta HTML a partir de string ou
 * aceita `href` que não tenha passado pela regex do contrato. É o que garante
 * que uma Zona Dinâmica não executa código arbitrário (SPEC-00 §6).
 */

import Link from "next/link";

import type { ZonePayload } from "./schema";

/**
 * O que todo widget recebe. `voltarAoPadrao` é o lado da pessoa na revogação
 * (R3): ausente, o widget não oferece a ação - nunca a simula.
 */
export interface WidgetProps {
  payload: ZonePayload;
  voltarAoPadrao?: () => void;
}

/** Fica ao lado da etiqueta: quem vê que algo foi escolhido para si pode desfazer. */
function VoltarAoPadrao({ onClick, className }: { onClick?: () => void; className: string }) {
  if (!onClick) return null;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shrink-0 text-[0.6875rem] font-medium underline underline-offset-2 transition focus-visible:outline-none focus-visible:shadow-focus ${className}`}
    >
      voltar ao padrão
    </button>
  );
}

function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <section className="papel-pautado relative overflow-hidden rounded-xl bg-inverse p-6 text-on-inverse">
      <div className="relative">{children}</div>
    </section>
  );
}

/**
 * A etiqueta não é enfeite: é o aviso de que aquele bloco foi escolhido para
 * este usuário e não é igual ao de todo mundo.
 */
function Etiqueta() {
  return (
    <span className="shrink-0 rounded-sm border border-on-inverse/25 px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-on-inverse/80">
      personalizado
    </span>
  );
}

function Cabecalho({ label, voltarAoPadrao }: { label?: string; voltarAoPadrao?: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <h2 className="font-display text-[1.375rem] leading-tight">{label}</h2>
      <div className="flex shrink-0 items-center gap-3">
        <VoltarAoPadrao
          onClick={voltarAoPadrao}
          className="text-on-inverse/70 hover:text-on-inverse"
        />
        <Etiqueta />
      </div>
    </div>
  );
}

function ShortcutList({ payload, voltarAoPadrao }: WidgetProps) {
  const itens = (payload.items ?? []).slice(0, payload.maxItems ?? 3);

  return (
    <Moldura>
      <Cabecalho label={payload.label} voltarAoPadrao={voltarAoPadrao} />
      <ul className="mt-5 flex flex-wrap gap-2">
        {itens.map((item) => (
          <li key={`${item.href}-${item.label}`}>
            <Link
              href={item.href}
              className="inline-flex items-center gap-2 rounded-lg border border-on-inverse/15 bg-on-inverse/5 px-3.5 py-2 text-sm font-medium transition hover:border-on-inverse/35 hover:bg-on-inverse/10"
            >
              {item.label}
              <svg viewBox="0 0 20 20" aria-hidden="true" className="h-3.5 w-3.5 opacity-60">
                <path
                  d="M7 4l6 6-6 6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </Link>
          </li>
        ))}
      </ul>
    </Moldura>
  );
}

function SummaryCard({ payload, voltarAoPadrao }: WidgetProps) {
  const itens = (payload.items ?? []).slice(0, payload.maxItems ?? 3);

  return (
    <Moldura>
      <Cabecalho label={payload.label} voltarAoPadrao={voltarAoPadrao} />
      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        {itens.map((item) => (
          <div
            key={`${item.href}-${item.label}`}
            className="rounded-lg border border-on-inverse/15 bg-on-inverse/5 p-4"
          >
            <dt className="text-sm font-medium">{item.label}</dt>
            <dd className="mt-2">
              <Link
                href={item.href}
                className="text-xs font-medium text-on-inverse underline underline-offset-4 hover:text-on-inverse/70"
              >
                abrir
              </Link>
            </dd>
          </div>
        ))}
      </dl>
    </Moldura>
  );
}

const TONS = {
  neutral: "border-line bg-surface text-ink",
  atencao: "border-warning/40 bg-warning-soft text-warning",
} as const;

function AlertBanner({ payload, voltarAoPadrao }: WidgetProps) {
  const tom = TONS[payload.tone ?? "neutral"];

  return (
    <section
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-5 py-4 ${tom}`}
    >
      <p className="text-sm font-medium">{payload.label}</p>
      <div className="flex items-center gap-3">
        <VoltarAoPadrao onClick={voltarAoPadrao} className="opacity-70 hover:opacity-100" />
        <span className="text-[0.625rem] font-semibold uppercase tracking-[0.08em] opacity-60">
          personalizado
        </span>
      </div>
    </section>
  );
}

/**
 * Registry local. Widget que não estiver aqui é violação, mesmo que o payload
 * tenha passado pelo schema - o contrato e o registry precisam concordar.
 */
export const WIDGETS: Record<string, (props: WidgetProps) => React.ReactElement> = {
  shortcut_list: ShortcutList,
  summary_card: SummaryCard,
  alert_banner: AlertBanner,
};
