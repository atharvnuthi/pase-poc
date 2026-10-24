"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import Progresso from "@/components/Progresso";
import {
  Botao,
  Campo,
  Cartao,
  ENTRADA,
  SELECAO,
  SETA_SELECT,
  TituloSecao,
  Vazio,
} from "@/components/ui";
import DynamicZone from "@/dynamic-zones/DynamicZone";
import {
  api,
  currentMonth,
  formatMoney,
  listaOuVazia,
  ValidationError,
  type BudgetState,
  type BudgetStatus,
  type Category,
} from "@/lib/api";

/** Categoria de receita: não há o que limitar nela. */
const CATEGORIA_DE_RECEITA = "Salário";

const AVISO: Record<BudgetState, { texto: string; classe: string } | null> = {
  ok: null,
  atencao: { texto: "perto do limite", classe: "bg-warning-soft text-warning" },
  estourado: { texto: "limite estourado", classe: "bg-danger-soft text-danger" },
};

export default function Orcamentos() {
  return <AppShell>{(persona) => <Conteudo userId={persona.id} />}</AppShell>;
}

function Conteudo({ userId }: { userId: number }) {
  const [mes, setMes] = useState(currentMonth());
  const [status, setStatus] = useState<BudgetStatus[] | null>(null);
  const [categorias, setCategorias] = useState<Category[]>([]);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);

  const [categoryId, setCategoryId] = useState("");
  const [limite, setLimite] = useState("");

  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [novoLimite, setNovoLimite] = useState("");
  const [erroEdicao, setErroEdicao] = useState<string | null>(null);

  const recarregar = useCallback(() => {
    api
      .budgetStatus(userId, mes)
      .then((v) => setStatus(listaOuVazia<BudgetStatus>(v)))
      .catch(() => setStatus([]));
  }, [userId, mes]);

  useEffect(() => {
    recarregar();
  }, [recarregar]);

  useEffect(() => {
    api
      .categories()
      .then((v) => setCategorias(listaOuVazia<Category>(v)))
      .catch(() => setCategorias([]));
  }, []);

  const comOrcamento = new Set((status ?? []).map((s) => s.category_id));
  const disponiveis = categorias.filter(
    (c) => c.name !== CATEGORIA_DE_RECEITA && !comOrcamento.has(c.id),
  );

  async function definir(event: React.FormEvent) {
    event.preventDefault();
    setSalvando(true);
    setErros({});
    try {
      await api.upsertBudget({
        user_id: userId,
        category_id: Number(categoryId),
        monthly_limit: limite,
      });
      setCategoryId("");
      setLimite("");
      recarregar();
    } catch (error) {
      setErros(
        error instanceof ValidationError
          ? error.fields
          : { geral: "Não consegui salvar. Tente de novo." },
      );
    } finally {
      setSalvando(false);
    }
  }

  async function salvarEdicao(item: BudgetStatus) {
    setErroEdicao(null);
    try {
      await api.upsertBudget({
        user_id: userId,
        category_id: item.category_id,
        monthly_limit: novoLimite,
      });
      setEditandoId(null);
      recarregar();
    } catch (error) {
      setErroEdicao(
        error instanceof ValidationError
          ? (error.fields.monthly_limit ?? "Limite inválido.")
          : "Não consegui salvar. Tente de novo.",
      );
    }
  }

  async function remover(item: BudgetStatus) {
    try {
      await api.deleteBudget(item.budget_id);
      recarregar();
    } catch {
      setErroEdicao("Não consegui remover. Tente de novo.");
    }
  }

  return (
    <div className="space-y-6">
      <DynamicZone slot="orcamentos_aviso" userId={userId}>
        {null}
      </DynamicZone>

      <Cartao>
        <TituloSecao
          titulo="Orçamento do mês"
          apoio="O limite de gasto de cada categoria e o quanto dele já foi usado."
          acao={
            <label className="flex items-center gap-2 text-sm">
              <span className="text-ink-muted">Mês</span>
              <input
                type="month"
                value={mes}
                onChange={(e) => e.target.value && setMes(e.target.value)}
                className={`${ENTRADA} tnum h-9 w-auto`}
              />
            </label>
          }
        />

        {erroEdicao && (
          <p className="mx-6 mt-4 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
            {erroEdicao}
          </p>
        )}

        {status === null ? (
          <p className="px-6 py-10 text-sm text-ink-muted">Carregando…</p>
        ) : status.length === 0 ? (
          <Vazio>Você ainda não definiu limites. Escolha uma categoria abaixo.</Vazio>
        ) : (
          <ul className="divide-y divide-line">
            {status.map((item) => {
              const aviso = AVISO[item.state];
              const restante = Number(item.remaining);
              const editando = editandoId === item.budget_id;
              return (
                <li key={item.budget_id} className="px-6 py-5">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h3 className="font-medium">{item.category}</h3>
                    {aviso && (
                      <span
                        className={`rounded-md px-2 py-0.5 text-xs font-medium ${aviso.classe}`}
                      >
                        {aviso.texto}
                      </span>
                    )}
                    <span className="tnum ml-auto text-sm text-ink-muted">
                      {formatMoney(item.spent)} de {formatMoney(item.monthly_limit)}
                    </span>
                  </div>

                  <div className="mt-3">
                    <Progresso
                      percentual={item.percent}
                      estado={item.state}
                      rotulo={`Orçamento de ${item.category}`}
                    />
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
                    <p className="tnum text-sm text-ink-muted">
                      {restante >= 0
                        ? `Restam ${formatMoney(restante)}`
                        : `Passou ${formatMoney(Math.abs(restante))} do limite`}{" "}
                      <span className="text-ink-subtle">({item.percent}%)</span>
                    </p>

                    {editando ? (
                      <form
                        className="ml-auto flex flex-wrap items-center gap-2"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void salvarEdicao(item);
                        }}
                      >
                        <label className="sr-only" htmlFor={`limite-${item.budget_id}`}>
                          {`Novo limite de ${item.category}`}
                        </label>
                        <input
                          id={`limite-${item.budget_id}`}
                          type="number"
                          step="0.01"
                          min="0"
                          value={novoLimite}
                          onChange={(e) => setNovoLimite(e.target.value)}
                          className={`${ENTRADA} tnum h-9 w-32`}
                        />
                        <Botao type="submit" tamanho="sm">
                          Salvar
                        </Botao>
                        <Botao
                          type="button"
                          variante="neutro"
                          tamanho="sm"
                          onClick={() => setEditandoId(null)}
                        >
                          Cancelar
                        </Botao>
                      </form>
                    ) : (
                      <div className="ml-auto flex gap-2">
                        <Botao
                          variante="neutro"
                          tamanho="sm"
                          aria-label={`Alterar limite de ${item.category}`}
                          onClick={() => {
                            setEditandoId(item.budget_id);
                            setNovoLimite(item.monthly_limit);
                            setErroEdicao(null);
                          }}
                        >
                          Alterar limite
                        </Botao>
                        <Botao
                          variante="perigo"
                          tamanho="sm"
                          aria-label={`Remover orçamento de ${item.category}`}
                          onClick={() => void remover(item)}
                        >
                          Remover
                        </Botao>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Cartao>

      <Cartao>
        <TituloSecao
          titulo="Definir um limite"
          apoio="Um limite por categoria de despesa. O mesmo valor vale para todos os meses."
        />
        {disponiveis.length === 0 && status !== null ? (
          <Vazio>Todas as categorias de despesa já têm limite.</Vazio>
        ) : (
          <form onSubmit={definir} className="grid gap-4 p-6 sm:grid-cols-2">
            <Campo label="Categoria do limite" erro={erros.category_id}>
              <select
                required
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className={SELECAO}
                style={SETA_SELECT}
              >
                <option value="">Selecione…</option>
                {disponiveis.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Campo>

            <Campo label="Limite mensal" erro={erros.monthly_limit}>
              <input
                required
                type="number"
                step="0.01"
                min="0"
                value={limite}
                onChange={(e) => setLimite(e.target.value)}
                placeholder="0,00"
                className={`${ENTRADA} tnum`}
              />
            </Campo>

            {erros.geral && (
              <p className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger sm:col-span-2">
                {erros.geral}
              </p>
            )}

            <div className="sm:col-span-2">
              <Botao type="submit" variante="marca" disabled={salvando}>
                {salvando ? "Salvando…" : "Definir limite"}
              </Botao>
            </div>
          </form>
        )}
      </Cartao>
    </div>
  );
}
