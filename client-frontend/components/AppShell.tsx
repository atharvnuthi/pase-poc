"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Botao, Marca } from "@/components/ui";
import { trackPageView } from "@/lib/telemetry";
import { applyTheme, readThemePreference, saveThemePreference, type Theme } from "@/lib/theme";
import { clearPersona, usePersona } from "@/lib/user";
import SuggestModal from "./SuggestModal";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/transacoes", label: "Transações" },
  { href: "/orcamentos", label: "Orçamentos" },
  { href: "/metas", label: "Metas" },
  { href: "/relatorios", label: "Relatórios" },
  { href: "/suporte", label: "Suporte" },
];

/**
 * Moldura das telas internas: navegação, troca de persona, telemetria a cada
 * mudança de rota e o modal "Sugerir melhoria" em todas as páginas.
 */
export default function AppShell({
  children,
}: {
  children: (persona: { id: number; name: string }) => React.ReactNode;
}) {
  const { persona, loading } = usePersona();
  const pathname = usePathname();
  const router = useRouter();
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    if (persona) trackPageView(persona.id, pathname);
  }, [persona, pathname]);

  useEffect(() => {
    if (!persona) return;

    const savedTheme = readThemePreference(persona.id);
    setTheme(savedTheme);
    applyTheme(savedTheme);
  }, [persona]);

  if (loading || !persona) {
    return (
      <main className="grid min-h-screen place-items-center">
        <p className="text-sm text-ink-muted">Carregando…</p>
      </main>
    );
  }

  const iniciais = persona.name.trim().charAt(0).toUpperCase();
  const themeActionLabel = theme === "light" ? "Usar tema escuro" : "Usar tema claro";

  function toggleTheme() {
    if (!persona) return;

    const nextTheme: Theme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    applyTheme(nextTheme);
    saveThemePreference(persona.id, nextTheme);
  }

  return (
    <div className="min-h-screen">
      {/* Fica no topo ao rolar; o desfoque mantém o conteúdo legível por baixo. */}
      <header className="sticky top-0 z-40 border-b border-line bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-6">
          <Link href="/dashboard" className="shrink-0 rounded-lg focus-visible:outline-none focus-visible:shadow-focus">
            <Marca />
          </Link>

          <nav className="flex items-center overflow-x-auto">
            {LINKS.map((link) => {
              const ativo = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={ativo ? "page" : undefined}
                  className={`flex h-16 items-center whitespace-nowrap px-3 text-sm font-medium transition ${
                    ativo
                      ? "text-ink shadow-[inset_0_-2px_0_rgb(var(--ink))]"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-2.5 sm:flex">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-sunken text-xs font-semibold text-ink">
                {iniciais}
              </span>
              <span className="text-sm font-medium">{persona.name}</span>
            </span>
            <Botao
              variante="neutro"
              tamanho="sm"
              onClick={toggleTheme}
              aria-label={themeActionLabel}
              title={themeActionLabel}
            >
              {theme === "light" ? <MoonIcon /> : <SunIcon />}
            </Botao>
            <Botao
              variante="neutro"
              tamanho="sm"
              onClick={() => {
                clearPersona();
                router.push("/");
              }}
            >
              Trocar persona
            </Botao>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">{children(persona)}</main>

      <SuggestModal userId={persona.id} />
    </div>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      data-icon="moon"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14.5 12.5A5.5 5.5 0 0 1 7.5 5.5a6 6 0 1 0 7 7Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      data-icon="sun"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="10" cy="10" r="3.5" />
      <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" />
    </svg>
  );
}
