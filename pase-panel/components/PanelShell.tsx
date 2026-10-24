"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { pase } from "@/lib/api";
import { useConexao, useLista } from "@/lib/query";

import { Ponto } from "./ui";

/**
 * Moldura do painel de controle humano (SPEC-06 §1).
 *
 * É aqui que toda decisão crítica acontece - e nenhuma acontece automaticamente.
 * A barra lateral responde a uma pergunta antes de qualquer clique: **tem alguma
 * coisa esperando por mim?** O número laranja ao lado de Tarefas é isso.
 */

const GRUPOS = [
  {
    nome: "Fluxo",
    telas: [
      { href: "/tarefas", label: "Tarefas", contador: "espera" as const },
      { href: "/entrega", label: "Entrega" },
      { href: "/grafo", label: "Dependências" },
    ],
  },
  {
    nome: "Produto",
    telas: [
      { href: "/zonas", label: "Zonas dinâmicas" },
      { href: "/incidentes", label: "Incidentes", contador: "incidentes" as const },
    ],
  },
  {
    nome: "Motor",
    telas: [
      { href: "/contexto", label: "Contexto", contador: "sugestoes" as const },
      { href: "/sistema", label: "Sistema" },
    ],
  },
];

type Tema = "sistema" | "claro" | "escuro";
const PROXIMO: Record<Tema, Tema> = { sistema: "claro", claro: "escuro", escuro: "sistema" };

function aplicarTema(tema: Tema) {
  const raiz = document.documentElement;
  if (tema === "sistema") delete raiz.dataset.theme;
  else raiz.dataset.theme = tema === "claro" ? "light" : "dark";
}

function useTema(): [Tema, () => void] {
  const [tema, setTema] = useState<Tema>("sistema");

  useEffect(() => {
    let salvo: Tema = "sistema";
    try {
      salvo = (localStorage.getItem("pase.tema") as Tema | null) ?? "sistema";
    } catch {
      // armazenamento bloqueado: segue o sistema
    }
    setTema(salvo);
    aplicarTema(salvo);
  }, []);

  function alternar() {
    const novo = PROXIMO[tema];
    setTema(novo);
    aplicarTema(novo);
    try {
      localStorage.setItem("pase.tema", novo);
    } catch {
      // sem persistência, mas o tema muda na sessão
    }
  }

  return [tema, alternar];
}

/** Três barras de comprimentos diferentes: demandas entrando, sendo filtradas, saindo. */
function Marca() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden className="shrink-0">
      <rect x="1" y="3" width="20" height="3.5" rx="1" className="fill-ink" />
      <rect x="1" y="9.25" width="13" height="3.5" rx="1" className="fill-ink" />
      <rect x="1" y="15.5" width="7" height="3.5" rx="1" className="fill-signal" />
    </svg>
  );
}

function Navegacao({ onNavegar }: { onNavegar?: () => void }) {
  const pathname = usePathname();
  const saude = useLista(["system-health"], () => pase.systemHealth());
  const s = saude.data as Record<string, number> | undefined;
  // Sugestões nascem em segundo plano, depois de uma aprovação: sem evento para avisar.
  const sugestoes = useLista(["context-suggestions"], () => pase.contextSuggestions(), {
    atualizarACada: 30_000,
  });

  return (
    <nav className="flex flex-col gap-6">
      {GRUPOS.map((grupo) => (
        <div key={grupo.nome}>
          <p className="eyebrow mb-1.5 px-2.5">{grupo.nome}</p>
          <ul className="space-y-px">
            {grupo.telas.map((tela) => {
              const ativa = pathname.startsWith(tela.href);
              const valor =
                tela.contador === "espera"
                  ? s?.aguardando_humano
                  : tela.contador === "incidentes"
                    ? s?.incidentes_abertos
                    : tela.contador === "sugestoes"
                      ? sugestoes.data?.length
                      : undefined;
              return (
                <li key={tela.href}>
                  <Link
                    href={tela.href}
                    onClick={onNavegar}
                    aria-current={ativa ? "page" : undefined}
                    className={`flex h-8 items-center gap-2 rounded px-2.5 text-[13.5px] transition-colors ${
                      ativa
                        ? "bg-surface font-medium text-ink shadow-[inset_0_0_0_1px_rgb(var(--line))]"
                        : "text-ink-2 hover:bg-surface/60 hover:text-ink"
                    }`}
                  >
                    {tela.label}
                    {valor !== undefined && valor > 0 && (
                      <span
                        title={
                          tela.contador === "espera"
                            ? "Tarefas esperando uma decisão sua"
                            : tela.contador === "sugestoes"
                              ? "Sugestões da IA para atualizar o contexto"
                              : "Incidentes abertos"
                        }
                        className={`tnum ml-auto rounded-sm px-1.5 font-mono text-[11px] leading-[18px] ${
                          tela.contador === "incidentes"
                            ? "bg-bad/15 text-bad"
                            : "bg-signal text-white"
                        }`}
                      >
                        {valor}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Rodape() {
  const conectado = useConexao();
  const [tema, alternarTema] = useTema();
  const custo = useLista(["system-cost"], () => pase.systemCost());
  const c = custo.data as Record<string, string> | undefined;

  return (
    <div className="space-y-3 border-t border-line pt-4 text-[12px]">
      <p
        className="flex items-center gap-2 px-2.5 text-ink-2"
        title="Conexão de eventos com o pase-core: a tela se atualiza sozinha quando algo muda"
      >
        <Ponto tom={conectado ? "ok" : "neutro"} pulsando={conectado} />
        {conectado ? "ao vivo" : "sem eventos"}
        <span className="ml-auto font-mono text-[11px] text-ink-3">:8000</span>
      </p>

      {c && (
        <dl className="space-y-1 px-2.5 font-mono text-[11px] leading-snug">
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-ink-3">funil</dt>
            <dd className="truncate text-ink-2">{c.modelo_padrao}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-ink-3">código</dt>
            <dd className="truncate text-ink-2">{c.modelo_de_codigo ?? "-"}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-ink-3">revisão</dt>
            <dd className="truncate text-ink-2">{c.modelo_de_revisao ?? "-"}</dd>
          </div>
        </dl>
      )}

      <button
        type="button"
        onClick={alternarTema}
        className="flex h-7 w-full items-center gap-2 rounded px-2.5 text-ink-2 hover:bg-surface/60 hover:text-ink"
      >
        <span className="text-ink-3">tema</span>
        <span className="ml-auto font-mono text-[11px]">{tema}</span>
      </button>
    </div>
  );
}

export default function PanelShell({
  titulo,
  descricao,
  sobretitulo,
  acoes,
  children,
}: {
  titulo: React.ReactNode;
  descricao?: React.ReactNode;
  sobretitulo?: React.ReactNode;
  acoes?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [menuAberto, setMenuAberto] = useState(false);
  const pathname = usePathname();
  const grupo = GRUPOS.find((g) => g.telas.some((t) => pathname.startsWith(t.href)));

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      {/* Barra lateral: fixa no desktop, gaveta no celular. */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[236px] flex-col gap-7 border-r border-line bg-sunken px-3 pb-4 pt-5 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${
          menuAberto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Link href="/tarefas" className="flex items-center gap-2.5 px-2.5">
          <Marca />
          <span className="leading-none">
            <span className="block font-mono text-[15px] font-semibold tracking-[0.12em]">PASE</span>
            <span className="mt-1 block text-[11px] text-ink-3">painel de controle</span>
          </span>
        </Link>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <Navegacao onNavegar={() => setMenuAberto(false)} />
        </div>

        <Rodape />
      </aside>

      {menuAberto && (
        <button
          type="button"
          aria-label="Fechar menu"
          onClick={() => setMenuAberto(false)}
          className="fixed inset-0 z-30 bg-ink/30 lg:hidden"
        />
      )}

      <div className="min-w-0">
        <div className="sticky top-0 z-20 flex h-12 items-center gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setMenuAberto(true)}
            aria-label="Abrir menu"
            className="-ml-1 rounded p-1.5 text-ink-2 hover:bg-sunken"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
              <path d="M2 4.5h14M2 9h14M2 13.5h14" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
          <Marca />
          <span className="font-mono text-[13px] font-semibold tracking-[0.12em]">PASE</span>
        </div>

        <main className="mx-auto max-w-[1180px] px-4 pb-24 pt-8 sm:px-8 lg:pt-12">
          <header className="mb-8 flex flex-wrap items-end gap-x-8 gap-y-4">
            <div className="min-w-0 max-w-3xl flex-1">
              <p className="eyebrow">{sobretitulo ?? grupo?.nome}</p>
              <h1 className="mt-2 font-display text-[40px] leading-[1.05] tracking-[-0.01em] sm:text-[46px]">
                {titulo}
              </h1>
              {descricao && (
                <p className="mt-3 max-w-2xl text-[14.5px] leading-relaxed text-ink-2">{descricao}</p>
              )}
            </div>
            {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
          </header>

          {children}
        </main>
      </div>
    </div>
  );
}
