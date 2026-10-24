"use client";

import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import PainelDoMes from "@/components/PainelDoMes";
import { Cartao, Rotulo } from "@/components/ui";
import DynamicZone from "@/dynamic-zones/DynamicZone";
import { api, formatMoney, type Summary } from "@/lib/api";

function ResumoNativo({ summary }: { summary: Summary }) {
  const maior = summary.by_category.reduce(
    (acc, item) => Math.max(acc, Number(item.total)),
    0,
  );
  const total = summary.by_category.reduce((acc, item) => acc + Number(item.total), 0);

  return (
    <Cartao className="p-6">
      {/* Só o rótulo: repetir o total aqui duplicaria, na prática, o valor da
          única categoria quando há uma só - dois números iguais na mesma tela
          sem dizer que são coisas diferentes. A proporção de cada linha já
          conta a história. */}
      <Rotulo>Gastos por categoria</Rotulo>

      {summary.by_category.length === 0 ? (
        <p className="mt-6 text-sm text-ink-subtle">Nenhuma despesa registrada ainda.</p>
      ) : (
        <ul className="mt-6 space-y-5">
          {summary.by_category.map((item) => {
            const proporcao = maior ? (Number(item.total) / maior) * 100 : 0;
            const fatia = total ? Math.round((Number(item.total) / total) * 100) : 0;

            return (
              <li key={item.category}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium">{item.category}</span>
                  <span className="flex items-baseline gap-2">
                    <span className="text-xs text-ink-subtle">{fatia}%</span>
                    <span className="tnum font-semibold">{formatMoney(item.total)}</span>
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-sm bg-sunken">
                  <div
                    className="h-full rounded-sm bg-brand-strong transition-[width] duration-500"
                    style={{ width: `${proporcao}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Cartao>
  );
}

export default function Dashboard() {
  return (
    <AppShell>
      {(persona) => <Conteudo userId={persona.id} />}
    </AppShell>
  );
}

function Conteudo({ userId }: { userId: number }) {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    api.summary(userId).then(setSummary).catch(() => setSummary(null));
  }, [userId]);

  if (!summary) return <p className="text-sm text-ink-muted">Carregando…</p>;

  const saldo = Number(summary.balance);
  const negativo = saldo < 0;

  return (
    <div className="space-y-6">
      {/* Painel escuro: o número mais importante da tela ganha o maior contraste. */}
      <section className="papel-pautado relative overflow-hidden rounded-xl bg-inverse p-8 text-on-inverse sm:p-12">
        <div className="relative">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-on-inverse/55">
            Saldo
          </p>
          <p
            className={`tnum mt-4 font-display text-[4.25rem] font-normal leading-none sm:text-[6rem] ${
              negativo ? "text-danger-on-inverse" : "text-on-inverse"
            }`}
          >
            {formatMoney(summary.balance)}
          </p>
          <p className="mt-5 text-sm text-on-inverse/55">
            Receitas menos despesas de todo o período.
          </p>
        </div>
      </section>

      {/*
        A Zona Dinâmica. O ResumoNativo é o fallback e é também o caminho normal:
        quem não tem personalização vê exatamente o que via antes (SPEC-05 §5).
      */}
      <DynamicZone slot="resumo_financeiro" userId={userId}>
        <ResumoNativo summary={summary} />
      </DynamicZone>

      <PainelDoMes userId={userId} />
    </div>
  );
}
