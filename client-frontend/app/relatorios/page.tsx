"use client";

import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import { Cartao, TituloSecao, Vazio } from "@/components/ui";
import DynamicZone from "@/dynamic-zones/DynamicZone";
import { api, formatMoney, type Transaction } from "@/lib/api";

/**
 * Totais por mês.
 *
 * A agregação acontece aqui, no cliente, a partir de GET /transactions: a API do
 * client-backend é contrato congelado (SPEC-02) e não ganha endpoints que o SPEC
 * não pediu. Com ~50 transações o custo é irrelevante.
 */

interface LinhaMes {
  chave: string;
  mes: string;
  receitas: number;
  despesas: number;
  saldo: number;
}

const NOMES_MES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

function rotulo(chave: string): string {
  const [ano, mes] = chave.split("-");
  return `${NOMES_MES[Number(mes) - 1]} de ${ano}`;
}

function agregarPorMes(transactions: Transaction[]): LinhaMes[] {
  const mapa = new Map<string, { receitas: number; despesas: number }>();

  for (const transaction of transactions) {
    const chave = transaction.date.slice(0, 7); // YYYY-MM
    const atual = mapa.get(chave) ?? { receitas: 0, despesas: 0 };
    const valor = Number(transaction.amount);
    if (transaction.type === "income") atual.receitas += valor;
    else atual.despesas += valor;
    mapa.set(chave, atual);
  }

  return [...mapa.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([chave, totais]) => ({
      chave,
      mes: rotulo(chave),
      receitas: totais.receitas,
      despesas: totais.despesas,
      saldo: totais.receitas - totais.despesas,
    }));
}

/** O mês imediatamente anterior a `AAAA-MM`. */
function mesAnterior(chave: string): string {
  const [ano, mes] = chave.split("-").map(Number);
  return mes === 1 ? `${ano - 1}-12` : `${ano}-${String(mes - 1).padStart(2, "0")}`;
}

/** Variação das despesas em relação ao mês anterior, ou `null` sem base de comparação. */
function variacaoDeDespesas(linha: LinhaMes, todas: LinhaMes[]): number | null {
  const anterior = todas.find((l) => l.chave === mesAnterior(linha.chave));
  if (!anterior || anterior.despesas === 0) return null;
  return Math.round(((linha.despesas - anterior.despesas) / anterior.despesas) * 100);
}

export default function Relatorios() {
  return <AppShell>{(persona) => <Conteudo userId={persona.id} />}</AppShell>;
}

function Conteudo({ userId }: { userId: number }) {
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);

  useEffect(() => {
    api.transactions(userId).then(setTransactions).catch(() => setTransactions([]));
  }, [userId]);

  const linhas = useMemo(() => agregarPorMes(transactions ?? []), [transactions]);

  if (transactions === null) return <p className="text-sm text-ink-muted">Carregando…</p>;

  return (
    <div className="space-y-6">
    <DynamicZone slot="relatorios_destaque" userId={userId}>
      {null}
    </DynamicZone>
    <Cartao>
      <TituloSecao titulo="Totais por mês" apoio="Receitas, despesas e saldo de cada mês." />

      {linhas.length === 0 ? (
        <Vazio>Nenhuma transação para somar ainda.</Vazio>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[0.6875rem] uppercase tracking-[0.08em] text-ink-subtle">
                <th className="px-6 py-3 font-semibold">Mês</th>
                <th className="px-6 py-3 text-right font-semibold">Receitas</th>
                <th className="px-6 py-3 text-right font-semibold">Despesas</th>
                <th className="px-6 py-3 text-right font-semibold">Vs. mês anterior</th>
                <th className="px-6 py-3 text-right font-semibold">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((linha) => (
                <tr
                  key={linha.mes}
                  className="border-t border-line/70 transition hover:bg-sunken/60"
                >
                  <td className="whitespace-nowrap px-6 py-3.5 font-medium capitalize">
                    {linha.mes}
                  </td>
                  <td className="tnum whitespace-nowrap px-6 py-3.5 text-right text-brand-strong">
                    {formatMoney(linha.receitas)}
                  </td>
                  <td className="tnum whitespace-nowrap px-6 py-3.5 text-right text-ink-muted">
                    {formatMoney(linha.despesas)}
                  </td>
                  <td className="tnum whitespace-nowrap px-6 py-3.5 text-right text-xs">
                    {(() => {
                      const variacao = variacaoDeDespesas(linha, linhas);
                      if (variacao === null) return <span className="text-ink-subtle">-</span>;
                      // gastar mais que no mês anterior é o que merece atenção
                      return (
                        <span className={variacao > 0 ? "text-danger" : "text-brand-strong"}>
                          {variacao > 0 ? "+" : ""}
                          {variacao}%
                        </span>
                      );
                    })()}
                  </td>
                  <td
                    className={`tnum whitespace-nowrap px-6 py-3.5 text-right font-semibold ${
                      linha.saldo < 0 ? "text-danger" : "text-ink"
                    }`}
                  >
                    {formatMoney(linha.saldo)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Cartao>
    </div>
  );
}
