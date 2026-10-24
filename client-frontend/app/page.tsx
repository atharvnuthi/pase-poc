"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Marca } from "@/components/ui";
import { api, type User } from "@/lib/api";
import { setPersona } from "@/lib/user";

/**
 * Porta de entrada. Divide a tela: à esquerda a marca, à direita a escolha.
 *
 * A persona não é login - é uma seleção. O texto diz isso em vez de imitar uma
 * tela de autenticação que não existe.
 */
export default function SelecionarPersona() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .users()
      .then(setUsers)
      .catch(() => setErro("Não consegui falar com a API do FinTrack."));
  }, []);

  function escolher(user: User) {
    setPersona(user.id, user.name);
    router.push("/dashboard");
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Painel de marca. Some no celular: ali o que importa é escolher. */}
      <section className="papel-pautado relative hidden flex-col justify-between overflow-hidden bg-inverse p-12 text-on-inverse lg:flex">
        <Marca className="relative text-on-inverse" />

        <div className="relative max-w-md">
          <span className="inline-flex items-center rounded-sm border border-on-inverse/25 px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-on-inverse/80">
            Finanças pessoais
          </span>
          <h1 className="mt-7 font-display text-[3.75rem] font-normal leading-[1.02] tracking-[-0.01em]">
            Todo gasto no lugar,
            <br />
            todo mês no controle.
          </h1>
          <p className="mt-6 text-[0.9375rem] leading-relaxed text-on-inverse/65">
            Lance receitas e despesas, acompanhe o saldo e veja para onde o
            dinheiro está indo - sem planilha.
          </p>
        </div>

        <p className="relative text-xs text-on-inverse/45">
          Produto-alvo do PASE · ambiente local de demonstração
        </p>
      </section>

      {/* Escolha da persona. */}
      <section className="flex flex-col justify-center px-6 py-16 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="lg:hidden">
            <Marca />
          </div>

          <p className="sobretitulo mt-8 lg:mt-0">
            Bem-vindo
          </p>
          <h2 className="mt-2 font-display text-[2.75rem] leading-none">Quem está usando?</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            Escolha uma persona para ver as transações e o saldo dela.
          </p>

          {erro && (
            <p className="mt-6 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
              {erro}
            </p>
          )}

          <div className="mt-8 space-y-3">
            {users.map((user) => (
              <button
                key={user.id}
                type="button"
                onClick={() => escolher(user)}
                className="group flex w-full items-center gap-4 rounded-xl border border-line-strong bg-surface p-4 text-left transition hover:border-ink focus-visible:outline-none focus-visible:shadow-focus"
              >
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-sunken font-display text-xl text-ink">
                  {user.name.trim().charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0">
                  <span className="block font-medium tracking-[-0.01em]">{user.name}</span>
                  <span className="block text-sm text-ink-muted">Entrar como {user.name}</span>
                </span>
                <svg
                  viewBox="0 0 20 20"
                  aria-hidden="true"
                  className="ml-auto h-4 w-4 shrink-0 text-ink-subtle transition group-hover:translate-x-0.5 group-hover:text-brand-strong"
                >
                  <path
                    d="M7 4l6 6-6 6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            ))}
          </div>

          <p className="mt-8 text-xs leading-relaxed text-ink-subtle">
            Sem autenticação: esta é uma PoC local e a persona é apenas uma seleção.
          </p>
        </div>
      </section>
    </div>
  );
}
