/**
 * Primitivas visuais do FinTrack.
 *
 * Cartão, campo, botão e estado vazio moram aqui em vez de repetidos em cinco
 * rotas. Além do óbvio (mudar o visual num lugar só), isto encolhe o diff de
 * quem mexe nas telas depois - inclusive o Executor, que passa a alterar
 * comportamento sem reescrever parágrafos de classe a cada arquivo.
 */

import type React from "react";

/* -------------------------------------------------------------------------- */
/* Superfícies                                                                 */
/* -------------------------------------------------------------------------- */

export const CARTAO = "rounded-xl border border-line bg-surface";

export function Cartao({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <section className={`${CARTAO} ${className}`}>{children}</section>;
}

/** Cabeçalho de cartão: título discreto em cima, conteúdo grande embaixo. */
export function Rotulo({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="sobretitulo">{children}</h2>
  );
}

export function TituloSecao({
  titulo,
  apoio,
  acao,
}: {
  titulo: string;
  apoio?: string;
  acao?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-line px-6 py-5">
      <div className="min-w-0">
        <h2 className="font-display text-[1.625rem] leading-tight tracking-[-0.005em]">{titulo}</h2>
        {apoio && <p className="mt-0.5 text-sm text-ink-muted">{apoio}</p>}
      </div>
      {acao && <div className="ml-auto">{acao}</div>}
    </div>
  );
}

export function Vazio({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="font-display text-xl italic text-ink-subtle">{children}</p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Controles de formulário                                                     */
/* -------------------------------------------------------------------------- */

/**
 * `bg-surface` e `text-ink` são explícitos de propósito: controle nativo sem
 * cor declarada herda a paleta do sistema operacional, e num navegador em tema
 * escuro isso pinta o campo de preto dentro de um cartão branco.
 */
export const CAMPO_BASE =
  "w-full rounded-lg border border-line-strong bg-surface px-3.5 text-sm text-ink " +
  "placeholder:text-ink-subtle transition " +
  "focus:border-brand focus:shadow-focus focus:outline-none " +
  "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted";

export const ENTRADA = `${CAMPO_BASE} h-10`;
export const SELECAO = `${CAMPO_BASE} h-10 appearance-none bg-no-repeat pr-10`;
export const AREA_TEXTO = `${CAMPO_BASE} py-3 leading-relaxed`;

/** Seta do select desenhada em CSS - evita depender de um pacote de ícones. */
export const SETA_SELECT: React.CSSProperties = {
  backgroundImage:
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='none' stroke='%23867f6f' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 8l4 4 4-4'/%3E%3C/svg%3E\")",
  backgroundPosition: "right 0.75rem center",
  backgroundSize: "1.25rem 1.25rem",
};

/**
 * O `<label>` envolve o controle, sem `htmlFor`. A associação implícita é o que
 * faz `getByLabelText("Categoria")` achar o select - e é o que a rede de
 * regressão usa para provar que o formulário continua acessível.
 */
export function Campo({
  label,
  erro,
  dica,
  children,
}: {
  label: string;
  erro?: string;
  dica?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {erro ? (
        <span className="mt-1.5 flex items-center gap-1 text-xs font-medium text-danger">
          {erro}
        </span>
      ) : (
        dica && <span className="mt-1.5 block text-xs text-ink-subtle">{dica}</span>
      )}
    </label>
  );
}

/* -------------------------------------------------------------------------- */
/* Botões                                                                      */
/* -------------------------------------------------------------------------- */

const VARIANTE = {
  primario:
    "bg-ink text-on-ink hover:bg-ink/85 active:translate-y-px disabled:bg-ink-subtle",
  marca:
    "bg-brand-strong text-on-ink hover:bg-brand active:translate-y-px disabled:bg-ink-subtle",
  neutro:
    "border border-line-strong bg-surface text-ink hover:border-ink-subtle hover:bg-sunken " +
    "active:translate-y-px disabled:text-ink-subtle",
  fantasma: "text-ink-muted hover:bg-sunken hover:text-ink",
  perigo: "text-danger hover:bg-danger-soft",
} as const;

const TAMANHO = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-5 text-sm",
} as const;

export function Botao({
  variante = "primario",
  tamanho = "md",
  className = "",
  ...props
}: {
  variante?: keyof typeof VARIANTE;
  tamanho?: keyof typeof TAMANHO;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium " +
        "transition focus-visible:outline-none focus-visible:shadow-focus " +
        "disabled:cursor-not-allowed disabled:opacity-70 " +
        `${VARIANTE[variante]} ${TAMANHO[tamanho]} ${className}`
      }
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Marca                                                                       */
/* -------------------------------------------------------------------------- */

export function Marca({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      {/* Monograma: um F de livro-razão, em itálico serifado, sobre o verde. */}
      <span
        aria-hidden="true"
        className="grid h-8 w-8 place-items-center rounded-lg bg-brand-strong font-display text-[1.5rem] italic leading-none text-on-ink"
      >
        F
      </span>
      <span className="font-display text-[1.625rem] leading-none tracking-[-0.005em]">
        FinTrack
      </span>
    </span>
  );
}
