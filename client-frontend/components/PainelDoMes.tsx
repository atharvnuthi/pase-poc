"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import GraficoMensal from "@/components/GraficoMensal";
import Progresso from "@/components/Progresso";
import { Cartao, Rotulo } from "@/components/ui";
import {
  api,
  formatDate,
  formatMoney,
  listaOuVazia,
  type BudgetStatus,
  type MonthlyTotal,
  type Transaction,
} from "@/lib/api";

/**
 * O que acompanha o saldo no dashboard: orçamento do mês, últimas transações e a
 * evolução dos últimos meses.
 *
 * Tudo aqui é **opcional**. Cada bloco busca o próprio dado e, se falhar ou vier
 * torto, simplesmente não aparece: o saldo e o resumo por categoria, que são o
 * dashboard de verdade, não podem depender de nada disto.
 */
export default function PainelDoMes({ userId }: { userId: number }) {
  const [orcamentos, setOrcamentos] = useState<BudgetStatus[]>([]);
  const [recentes, setRecentes] = useState<Transaction[]>([]);
  const [meses, setMeses] = useState<MonthlyTotal[]>([]);

  useEffect(() => {
    let cancelado = false;
    const aplicar = <T,>(promessa: Promise<unknown>, guardar: (v: T[]) => void) =>
      promessa
        .then((valor) => {
          if (!cancelado) guardar(listaOuVazia<T>(valor));
        })
        .catch(() => {
          /* dado opcional: sem ele, o bloco some */
        });

    void aplicar<BudgetStatus>(api.budgetStatus(userId), setOrcamentos);
    void aplicar<Transaction>(api.transactions(userId, { limit: 5 }), setRecentes);
    void aplicar<MonthlyTotal>(api.monthlySummary(userId, 6), setMeses);

    return () => {
      cancelado = true;
    };
  }, [userId]);

  const maisProximos = orcamentos.slice(0, 3);
  const temMeses = meses.some((m) => Number(m.income) > 0 || Number(m.expense) > 0);

  if (maisProximos.length === 0 && recentes.length === 0 && !temMeses) return null;

  return (
    <div className="space-y-6">
      {(maisProximos.length > 0 || recentes.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {maisProximos.length > 0 && (
            <Cartao className="p-6">
              <div className="flex items-baseline justify-between gap-3">
                <Rotulo>Orçamento do mês</Rotulo>
                <Link href="/orcamentos" className="text-xs font-medium text-brand-strong underline-offset-4 hover:underline">
                  ver todos
                </Link>
              </div>
              <ul className="mt-5 space-y-4">
                {maisProximos.map((b) => (
                  <li key={b.budget_id}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="font-medium">{b.category}</span>
                      <span className="tnum text-ink-muted">
                        {formatMoney(b.spent)} de {formatMoney(b.monthly_limit)}
                      </span>
                    </div>
                    <div className="mt-2">
                      <Progresso
                        percentual={b.percent}
                        estado={b.state}
                        rotulo={`Orçamento de ${b.category}`}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </Cartao>
          )}

          {recentes.length > 0 && (
            <Cartao className="p-6">
              <div className="flex items-baseline justify-between gap-3">
                <Rotulo>Últimas transações</Rotulo>
                <Link href="/transacoes" className="text-xs font-medium text-brand-strong underline-offset-4 hover:underline">
                  ver todas
                </Link>
              </div>
              <ul className="mt-5 divide-y divide-line">
                {recentes.map((t) => (
                  <li key={t.id} className="flex items-baseline justify-between gap-3 py-2.5 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{t.description || t.category}</span>
                      <span className="tnum text-xs text-ink-subtle">
                        {formatDate(t.date)} · {t.category}
                      </span>
                    </span>
                    <span
                      className={`tnum shrink-0 font-semibold ${
                        t.type === "income" ? "text-brand-strong" : "text-ink"
                      }`}
                    >
                      {t.type === "income" ? "+" : "−"}
                      {formatMoney(t.amount)}
                    </span>
                  </li>
                ))}
              </ul>
            </Cartao>
          )}
        </div>
      )}

      {temMeses && (
        <Cartao className="p-6">
          <Rotulo>Receitas e despesas por mês</Rotulo>
          <div className="mt-5">
            <GraficoMensal dados={meses} />
          </div>
        </Cartao>
      )}
    </div>
  );
}
