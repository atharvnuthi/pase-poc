/**
 * Rede de regressão das cinco rotas do FinTrack (SPEC-11 §5).
 *
 * É o que o Executor não pode quebrar. Cada teste cobre um comportamento que,
 * se sumir, deixa o usuário sem conseguir fazer algo - não detalhe visual.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import Dashboard from "@/app/dashboard/page";
import SelecionarPersona from "@/app/page";
import Relatorios from "@/app/relatorios/page";
import Suporte from "@/app/suporte/page";
import Transacoes from "@/app/transacoes/page";

import { navegou } from "./_mocks";
import { CATEGORIAS, RESUMO, TRANSACOES, entrarComo, mockarApi } from "./_ajuda";

describe("seleção de persona", () => {
  it("guarda o usuário escolhido e leva ao dashboard", async () => {
    mockarApi({ "/users": [{ id: 1, name: "Ana" }, { id: 2, name: "Clara" }] });
    render(<SelecionarPersona />);

    await userEvent.click(await screen.findByRole("button", { name: /Entrar como Ana/i }));

    expect(localStorage.getItem("fintrack.userId")).toBe("1");
    expect(navegou).toHaveBeenCalledWith("/dashboard");
  });
});

describe("dashboard", () => {
  it("mostra o saldo e os gastos por categoria vindos do resumo", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/summary": RESUMO });
    render(<Dashboard />);

    expect(await screen.findByText(/5\.050,00/)).toBeInTheDocument();
    expect(await screen.findByText("Alimentação")).toBeInTheDocument();
    expect(await screen.findByText(/150,00/)).toBeInTheDocument();
  });
});

describe("transações", () => {
  it("lista as transações do usuário", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/transactions": TRANSACOES, "/categories": CATEGORIAS });
    render(<Transacoes />);

    expect(await screen.findByText("Supermercado")).toBeInTheDocument();
    expect(await screen.findByText("Salário mensal")).toBeInTheDocument();
  });

  it("mostra o erro 422 no campo que o causou", async () => {
    entrarComo(1, "Ana");
    mockarApi(
      {
        "/transactions": TRANSACOES,
        "/categories": CATEGORIAS,
      },
      {},
    );
    render(<Transacoes />);
    await screen.findByText("Supermercado");

    // a criação responde 422 apontando o campo `amount`
    const original = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          return {
            ok: false,
            status: 422,
            json: async () => ({
              detail: [{ loc: ["body", "amount"], msg: "o valor precisa ser positivo" }],
            }),
          } as Response;
        }
        return original(url, init);
      }),
    );

    await userEvent.selectOptions(screen.getByLabelText(/Categoria/i), "1");
    await userEvent.type(screen.getByLabelText(/Valor/i), "10");
    await userEvent.click(screen.getByRole("button", { name: /Adicionar/i }));

    expect(await screen.findByText("o valor precisa ser positivo")).toBeInTheDocument();
  });

  it("remove a transação excluída da listagem", async () => {
    entrarComo(1, "Ana");
    let listagem = [...TRANSACOES];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const endereco = String(url);
        if (init?.method === "DELETE") {
          listagem = listagem.filter((t) => !endereco.endsWith(String(t.id)));
          return { ok: true, status: 204, json: async () => ({}) } as Response;
        }
        if (endereco.includes("/categories")) {
          return { ok: true, status: 200, json: async () => CATEGORIAS } as Response;
        }
        return { ok: true, status: 200, json: async () => listagem } as Response;
      }),
    );

    render(<Transacoes />);
    await screen.findByText("Supermercado");

    await userEvent.click(screen.getAllByRole("button", { name: /Excluir/i })[0]);

    await waitFor(() => expect(screen.queryByText("Supermercado")).not.toBeInTheDocument());
  });
});

describe("relatórios", () => {
  it("agrega os totais por mês, um mês por linha", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/transactions": TRANSACOES });
    render(<Relatorios />);

    const setembro = (await screen.findByText(/setembro de 2026/i)).closest("tr");
    const agosto = (await screen.findByText(/agosto de 2026/i)).closest("tr");

    // setembro teve só a despesa de 150 → saldo negativo
    expect(setembro).toHaveTextContent("R$ 150,00");
    expect(setembro).toHaveTextContent("-R$ 150,00");

    // agosto teve só a receita de 5200 → saldo igual à receita
    expect(agosto).toHaveTextContent("R$ 5.200,00");
    expect(agosto).toHaveTextContent("R$ 0,00");
  });
});

describe("suporte", () => {
  it("envia o ticket e confirma para o usuário", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/tickets": { id: 9 } });
    render(<Suporte />);

    await userEvent.type(
      await screen.findByRole("textbox"),
      "não acho onde corrigir a data",
    );
    await userEvent.click(screen.getByRole("button", { name: /Enviar/i }));

    expect(await screen.findByText(/Recebemos sua mensagem/i)).toBeInTheDocument();
    expect(chamadas.some((c) => c.url.includes("/tickets") && c.init?.method === "POST")).toBe(true);
  });
});
