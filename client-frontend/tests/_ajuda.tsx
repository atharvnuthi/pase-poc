import { vi } from "vitest";

/** Respostas do client-backend, roteadas por URL. */
export function mockarApi(rotas: Record<string, unknown>, opcoes: Record<string, number> = {}) {
  const chamadas: { url: string; init?: RequestInit }[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const endereco = String(url);
      chamadas.push({ url: endereco, init });

      const chave = Object.keys(rotas).find((r) => endereco.includes(r));
      const status = Object.keys(opcoes).find((r) => endereco.includes(r));

      if (status) {
        const codigo = opcoes[status];
        return {
          ok: codigo < 400,
          status: codigo,
          json: async () => rotas[chave ?? ""] ?? {},
          text: async () => "",
        } as Response;
      }

      if (chave === undefined) {
        return { ok: true, status: 204, json: async () => ({}) } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => rotas[chave],
        text: async () => JSON.stringify(rotas[chave]),
      } as Response;
    }),
  );

  return chamadas;
}

/** Deixa uma persona escolhida, como se o usuário já tivesse entrado. */
export function entrarComo(id: number, nome: string) {
  localStorage.setItem("fintrack.userId", String(id));
  localStorage.setItem("fintrack.userName", nome);
}

export const TRANSACOES = [
  {
    id: 1,
    user_id: 1,
    category_id: 1,
    category: "Alimentação",
    type: "expense",
    amount: "150.00",
    date: "2026-09-10",
    description: "Supermercado",
  },
  {
    id: 2,
    user_id: 1,
    category_id: 5,
    category: "Salário",
    type: "income",
    amount: "5200.00",
    date: "2026-08-05",
    description: "Salário mensal",
  },
];

export const CATEGORIAS = [
  { id: 1, name: "Alimentação" },
  { id: 2, name: "Transporte" },
];

export const RESUMO = {
  balance: "5050.00",
  by_category: [{ category: "Alimentação", total: "150.00" }],
};
