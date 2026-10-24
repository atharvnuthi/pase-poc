"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
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
  formatDate,
  formatMoney,
  ValidationError,
  type Category,
  type Transaction,
  type TransactionFilters,
  type TransactionType,
} from "@/lib/api";

const HOJE = new Date().toISOString().slice(0, 10);

export default function Transacoes() {
  return <AppShell>{(persona) => <Conteudo userId={persona.id} />}</AppShell>;
}

function Conteudo({ userId }: { userId: number }) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [filtros, setFiltros] = useState<TransactionFilters>({});
  const [categories, setCategories] = useState<Category[]>([]);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);

  const [tipo, setTipo] = useState<TransactionType>("expense");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [data, setData] = useState(HOJE);
  const [descricao, setDescricao] = useState("");

  // Edição da data direto na lista.
  const [editandoDataId, setEditandoDataId] = useState<number | null>(null);
  const [novaData, setNovaData] = useState<string>("");
  const [erroData, setErroData] = useState<string | null>(null);
  const [salvandoData, setSalvandoData] = useState(false);

  const filtrando = Boolean(
    filtros.q?.trim() || filtros.categoryId || filtros.type || filtros.month,
  );

  const recarregar = useCallback(() => {
    api.transactions(userId, filtros).then(setTransactions).catch(() => setTransactions([]));
  }, [userId, filtros]);

  useEffect(() => {
    // A busca por texto espera a pessoa parar de digitar; sem filtro, carrega na hora.
    const espera = setTimeout(recarregar, filtrando ? 250 : 0);
    return () => clearTimeout(espera);
  }, [recarregar, filtrando]);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  async function criar(event: React.FormEvent) {
    event.preventDefault();
    setSalvando(true);
    setErros({});
    try {
      await api.createTransaction({
        user_id: userId,
        category_id: Number(categoryId),
        type: tipo,
        amount,
        date: data,
        description: descricao,
      });
      setAmount("");
      setDescricao("");
      recarregar();
    } catch (error) {
      if (error instanceof ValidationError) {
        setErros(error.fields);
      } else {
        setErros({ geral: "Não consegui salvar. Tente de novo." });
      }
    } finally {
      setSalvando(false);
    }
  }

  async function excluir(id: number) {
    await api.deleteTransaction(id);
    recarregar();
  }

  function iniciarEdicaoData(transaction: Transaction) {
    setEditandoDataId(transaction.id);
    setNovaData(transaction.date);
    setErroData(null);
  }

  function cancelarEdicaoData() {
    setEditandoDataId(null);
    setNovaData("");
    setErroData(null);
  }

  async function salvarData(transaction: Transaction) {
    setSalvandoData(true);
    setErroData(null);
    try {
      // Reenvia todos os campos, alterando só a data.
      await api.updateTransaction(transaction.id, {
        user_id: transaction.user_id,
        category_id: transaction.category_id,
        type: transaction.type,
        amount: transaction.amount,
        date: novaData,
        description: transaction.description,
      });

      const atualizadas = transactions.map((t) =>
        t.id === transaction.id ? { ...t, date: novaData } : t,
      );

      atualizadas.sort((a, b) => {
        if (a.date > b.date) return -1;
        if (a.date < b.date) return 1;
        return b.id - a.id;
      });

      setTransactions(atualizadas);
      cancelarEdicaoData();
    } catch (error) {
      if (error instanceof ValidationError && error.fields.date) {
        setErroData(error.fields.date);
      } else {
        setErroData("Não consegui salvar a data. Tente de novo.");
      }
    } finally {
      setSalvandoData(false);
    }
  }

  return (
    <div className="space-y-6">
      <DynamicZone slot="transacoes_atalhos" userId={userId}>
        {null}
      </DynamicZone>

      <Cartao>
        <TituloSecao titulo="Nova transação" apoio="Registre uma receita ou uma despesa." />

        <form onSubmit={criar} className="grid gap-5 p-6 sm:grid-cols-2">
          <Campo label="Tipo" erro={erros.type}>
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value as TransactionType)}
              className={SELECAO}
              style={SETA_SELECT}
            >
              <option value="expense">Despesa</option>
              <option value="income">Receita</option>
            </select>
          </Campo>

          <Campo label="Categoria" erro={erros.category_id}>
            <select
              required
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className={SELECAO}
              style={SETA_SELECT}
            >
              <option value="">Selecione…</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </Campo>

          <Campo label="Valor" erro={erros.amount}>
            <input
              required
              type="number"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0,00"
              className={`${ENTRADA} tnum`}
            />
          </Campo>

          <Campo label="Data" erro={erros.date}>
            <input
              required
              type="date"
              value={data}
              onChange={(e) => setData(e.target.value)}
              className={`${ENTRADA} tnum`}
            />
          </Campo>

          <div className="sm:col-span-2">
            <Campo label="Descrição" erro={erros.description}>
              <input
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                placeholder="Ex.: Supermercado"
                className={ENTRADA}
              />
            </Campo>
          </div>

          {erros.geral && (
            <p className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger sm:col-span-2">
              {erros.geral}
            </p>
          )}

          <div className="sm:col-span-2">
            <Botao type="submit" variante="marca" disabled={salvando}>
              {salvando ? "Salvando…" : "Adicionar"}
            </Botao>
          </div>
        </form>
      </Cartao>

      <Cartao>
        <TituloSecao
          titulo="Transações"
          apoio="Clique na data para corrigi-la."
          acao={
            <span className="tnum rounded-md bg-sunken px-2.5 py-1 text-xs font-semibold text-ink-muted">
              {transactions.length}
            </span>
          }
        />

        <div className="grid gap-3 border-b border-line px-6 py-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-muted">Buscar nas descrições</span>
            <input
              type="search"
              value={filtros.q ?? ""}
              onChange={(e) => setFiltros({ ...filtros, q: e.target.value })}
              placeholder="Ex.: padaria"
              className={`${ENTRADA} h-9`}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-muted">Somente em</span>
            <select
              value={filtros.categoryId ?? ""}
              onChange={(e) =>
                setFiltros({ ...filtros, categoryId: e.target.value ? Number(e.target.value) : undefined })
              }
              className={`${SELECAO} h-9`}
              style={SETA_SELECT}
            >
              <option value="">Todas as categorias</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-muted">Mostrar</span>
            <select
              value={filtros.type ?? ""}
              onChange={(e) =>
                setFiltros({ ...filtros, type: (e.target.value || undefined) as TransactionType | undefined })
              }
              className={`${SELECAO} h-9`}
              style={SETA_SELECT}
            >
              <option value="">Receitas e despesas</option>
              <option value="expense">Só despesas</option>
              <option value="income">Só receitas</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-muted">Mês</span>
            <div className="flex gap-2">
              <input
                type="month"
                value={filtros.month ?? ""}
                onChange={(e) => setFiltros({ ...filtros, month: e.target.value || undefined })}
                className={`${ENTRADA} tnum h-9`}
              />
              {filtrando && (
                <Botao variante="neutro" tamanho="sm" className="h-9" onClick={() => setFiltros({})}>
                  Limpar
                </Botao>
              )}
            </div>
          </label>
        </div>

        {transactions.length === 0 ? (
          <Vazio>{filtrando ? "Nenhuma transação com esses filtros." : "Nenhuma transação ainda."}</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[0.6875rem] uppercase tracking-[0.08em] text-ink-subtle">
                  <th className="px-6 py-3 font-semibold">Data</th>
                  <th className="px-6 py-3 font-semibold">Descrição</th>
                  <th className="px-6 py-3 font-semibold">Categoria</th>
                  <th className="px-6 py-3 text-right font-semibold">Valor</th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody>
                {transactions.map((transaction) => {
                  const receita = transaction.type === "income";

                  return (
                    <tr
                      key={transaction.id}
                      className="group border-t border-line/70 transition hover:bg-sunken/60"
                    >
                      <td className="whitespace-nowrap px-6 py-3.5 align-top">
                        {editandoDataId === transaction.id ? (
                          <div className="space-y-2">
                            <input
                              type="date"
                              value={novaData}
                              onChange={(e) => setNovaData(e.target.value)}
                              disabled={salvandoData}
                              className={`${ENTRADA} tnum h-9 w-auto`}
                              max={HOJE}
                            />
                            {erroData && (
                              <p className="text-xs font-medium text-danger">{erroData}</p>
                            )}
                            <div className="flex gap-2">
                              <Botao
                                tamanho="sm"
                                onClick={() => salvarData(transaction)}
                                disabled={salvandoData}
                              >
                                {salvandoData ? "Salvando…" : "Salvar"}
                              </Botao>
                              <Botao
                                variante="neutro"
                                tamanho="sm"
                                onClick={cancelarEdicaoData}
                                disabled={salvandoData}
                              >
                                Cancelar
                              </Botao>
                            </div>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={() => iniciarEdicaoData(transaction)}
                            className="tnum -mx-2 rounded-lg px-2 py-1 font-medium text-ink underline-offset-4 transition hover:bg-brand/10 hover:text-brand-ink hover:underline focus-visible:outline-none focus-visible:shadow-focus"
                            aria-label={`Editar data da transação ${formatDate(transaction.date)}`}
                          >
                            {formatDate(transaction.date)}
                          </button>
                        )}
                      </td>
                      <td className="px-6 py-3.5 align-top font-medium">
                        {transaction.description}
                      </td>
                      <td className="px-6 py-3.5 align-top">
                        <span className="rounded-md bg-sunken px-2 py-0.5 text-xs font-medium text-ink-muted">
                          {transaction.category}
                        </span>
                      </td>
                      <td
                        className={`tnum whitespace-nowrap px-6 py-3.5 text-right align-top font-semibold ${
                          receita ? "text-brand-strong" : "text-ink"
                        }`}
                      >
                        {receita ? "+" : "−"}
                        {formatMoney(transaction.amount)}
                      </td>
                      <td className="px-6 py-3.5 text-right align-top">
                        {/* Discreto, nunca escondido: ação destrutiva atrás de
                            hover some no celular e some para o teclado. */}
                        <Botao
                          variante="perigo"
                          tamanho="sm"
                          onClick={() => excluir(transaction.id)}
                          className="text-ink-subtle transition group-hover:text-danger"
                        >
                          Excluir
                        </Botao>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
