/**
 * Cliente da API do FinTrack (client-backend).
 *
 * Os 9 endpoints originais (SPEC-02 §1) são contrato congelado. Orçamentos, metas, a
 * visão mensal e os filtros de transação entraram depois, como extensão: nada do que já
 * existia mudou de forma, e quem chama sem filtro recebe exatamente o que sempre recebeu.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_CLIENT_API_URL ?? "http://localhost:8001";

export type TransactionType = "income" | "expense";

export interface User {
  id: number;
  name: string;
}

export interface Category {
  id: number;
  name: string;
}

export interface Transaction {
  id: number;
  user_id: number;
  category_id: number;
  category: string;
  type: TransactionType;
  amount: string;
  date: string;
  description: string;
}

export interface Summary {
  balance: string;
  by_category: { category: string; total: string }[];
}

export interface Ticket {
  id: number;
  user_id: number;
  text: string;
  created_at: string;
}

export interface TransactionInput {
  user_id: number;
  category_id: number;
  type: TransactionType;
  amount: string;
  date: string;
  description: string;
}

export interface TransactionFilters {
  /** Texto contido na descrição; ignora caixa e acento. */
  q?: string;
  categoryId?: number;
  type?: TransactionType;
  /** AAAA-MM */
  month?: string;
  limit?: number;
}

export type BudgetState = "ok" | "atencao" | "estourado";

export interface BudgetStatus {
  budget_id: number;
  category_id: number;
  category: string;
  monthly_limit: string;
  spent: string;
  /** Negativo quando o limite estourou. */
  remaining: string;
  percent: number;
  state: BudgetState;
}

export interface Budget {
  id: number;
  user_id: number;
  category_id: number;
  category: string;
  monthly_limit: string;
}

export interface Goal {
  id: number;
  user_id: number;
  name: string;
  target_amount: string;
  saved_amount: string;
  remaining: string;
  percent: number;
  reached: boolean;
  deadline: string | null;
  monthly_needed: string | null;
}

export interface GoalInput {
  user_id: number;
  name: string;
  target_amount: string;
  deadline?: string | null;
}

export interface MonthlyTotal {
  month: string;
  income: string;
  expense: string;
}

/** Erro de validação com as mensagens já separadas por campo. */
export class ValidationError extends Error {
  constructor(public readonly fields: Record<string, string>) {
    super("dados inválidos");
    this.name = "ValidationError";
  }
}

interface FastApiError {
  loc: (string | number)[];
  msg: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });

  if (response.status === 422) {
    const body = await response.json();
    const detail: FastApiError[] = Array.isArray(body?.detail) ? body.detail : [];
    const fields: Record<string, string> = {};
    for (const item of detail) {
      const field = String(item.loc[item.loc.length - 1]);
      fields[field] = item.msg;
    }
    throw new ValidationError(fields);
  }

  if (!response.ok) {
    throw new Error(`${response.status} em ${path}`);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  users: () => request<User[]>("/users"),
  categories: () => request<Category[]>("/categories"),

  transactions: (userId: number, filters?: TransactionFilters) => {
    const params = new URLSearchParams({ user_id: String(userId) });
    if (filters?.q?.trim()) params.set("q", filters.q.trim());
    if (filters?.categoryId) params.set("category_id", String(filters.categoryId));
    if (filters?.type) params.set("type", filters.type);
    if (filters?.month) params.set("month", filters.month);
    if (filters?.limit) params.set("limit", String(filters.limit));
    return request<Transaction[]>(`/transactions?${params.toString()}`);
  },

  createTransaction: (payload: TransactionInput) =>
    request<Transaction>("/transactions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateTransaction: (id: number, payload: TransactionInput) =>
    request<Transaction>(`/transactions/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deleteTransaction: (id: number) =>
    request<void>(`/transactions/${id}`, { method: "DELETE" }),

  summary: (userId: number) => request<Summary>(`/summary?user_id=${userId}`),

  budgetStatus: (userId: number, month?: string) =>
    request<BudgetStatus[]>(
      `/budgets/status?user_id=${userId}${month ? `&month=${month}` : ""}`,
    ),

  upsertBudget: (payload: { user_id: number; category_id: number; monthly_limit: string }) =>
    request<Budget>("/budgets", { method: "PUT", body: JSON.stringify(payload) }),

  deleteBudget: (id: number) => request<void>(`/budgets/${id}`, { method: "DELETE" }),

  goals: (userId: number) => request<Goal[]>(`/goals?user_id=${userId}`),

  createGoal: (payload: GoalInput) =>
    request<Goal>("/goals", { method: "POST", body: JSON.stringify(payload) }),

  contributeToGoal: (id: number, amount: string) =>
    request<Goal>(`/goals/${id}/contribute`, {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),

  deleteGoal: (id: number) => request<void>(`/goals/${id}`, { method: "DELETE" }),

  monthlySummary: (userId: number, months = 6) =>
    request<MonthlyTotal[]>(`/summary/monthly?user_id=${userId}&months=${months}`),

  tickets: () => request<Ticket[]>("/tickets"),

  createTicket: (userId: number, text: string) =>
    request<Ticket>("/tickets", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, text }),
    }),
};

/** Formata um valor monetário vindo da API (string decimal) em pt-BR. */
export function formatMoney(value: string | number): string {
  return Number(value).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

const MESES_CURTOS = [
  "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez",
];

/** `2026-09` vira `set/26`. */
export function formatMonth(key: string): string {
  const [year, month] = key.split("-");
  return `${MESES_CURTOS[Number(month) - 1] ?? month}/${year.slice(2)}`;
}

/** O mês corrente, no formato AAAA-MM que a API usa. */
export function currentMonth(): string {
  const hoje = new Date();
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
}

/** Só aceita o que veio como lista: dado opcional que chegou torto some, não quebra a tela. */
export function listaOuVazia<T>(valor: unknown): T[] {
  return Array.isArray(valor) ? (valor as T[]) : [];
}

/** Formata uma data ISO (YYYY-MM-DD) sem passar por fuso horário. */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}
