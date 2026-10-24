/**
 * Orçamentos, metas, filtros, variação mensal e as zonas das telas novas.
 *
 * Cada teste afirma o que a pessoa vê e consegue fazer. Uma barra que "tem a classe
 * certa" não prova nada: o que importa é o texto que ela lê e o dado que sai quando ela
 * confirma.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import Dashboard from "@/app/dashboard/page";
import Metas from "@/app/metas/page";
import Orcamentos from "@/app/orcamentos/page";
import Relatorios from "@/app/relatorios/page";
import Suporte from "@/app/suporte/page";
import Transacoes from "@/app/transacoes/page";

import { CATEGORIAS, RESUMO, TRANSACOES, entrarComo, mockarApi } from "./_ajuda";

const CATEGORIAS_COM_RECEITA = [
  ...CATEGORIAS,
  { id: 3, name: "Lazer" },
  { id: 5, name: "Salário" },
];

const STATUS = [
  {
    budget_id: 2, category_id: 2, category: "Transporte", monthly_limit: "100.00",
    spent: "130.00", remaining: "-30.00", percent: 130, state: "estourado",
  },
  {
    budget_id: 1, category_id: 1, category: "Alimentação", monthly_limit: "500.00",
    spent: "460.00", remaining: "40.00", percent: 92, state: "atencao",
  },
];

const METAS = [
  {
    id: 1, user_id: 1, name: "Viagem", target_amount: "4000.00", saved_amount: "1500.00",
    remaining: "2500.00", percent: 37, reached: false, deadline: "2027-04-10",
    monthly_needed: "416.67",
  },
  {
    id: 2, user_id: 1, name: "Reserva", target_amount: "1000.00", saved_amount: "1200.00",
    remaining: "0.00", percent: 100, reached: true, deadline: null, monthly_needed: null,
  },
];

function bodyDe(chamadas: { url: string; init?: RequestInit }[], metodo: string, trecho: string) {
  const c = chamadas.find((x) => x.init?.method === metodo && x.url.includes(trecho));
  return c ? JSON.parse(String(c.init?.body)) : undefined;
}

/** Responde 422 a toda escrita que o teste escolher, sem mexer nas leituras. */
function falharEscritaCom(metodo: string, campo: string, mensagem: string) {
  const original = globalThis.fetch as unknown as (u: string, i?: RequestInit) => Promise<Response>;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === metodo) {
        return {
          ok: false,
          status: 422,
          json: async () => ({ detail: [{ loc: ["body", campo], msg: mensagem, type: "value_error" }] }),
        } as Response;
      }
      return original(url, init);
    }),
  );
}

// --------------------------------------------------------------------------- //
// Orçamentos
// --------------------------------------------------------------------------- //

describe("orçamentos", () => {
  it("mostra quanto de cada limite já foi usado, e o que pede atenção", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/budgets/status": STATUS, "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);

    expect(await screen.findByText("limite estourado")).toBeInTheDocument();
    expect(screen.getByText("perto do limite")).toBeInTheDocument();
    expect(screen.getByText(/Passou R\$\s*30,00 do limite/)).toBeInTheDocument();
    expect(screen.getByText(/Restam R\$\s*40,00/)).toBeInTheDocument();
  });

  it("a barra nunca passa de 100%, mesmo com o limite estourado", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/budgets/status": STATUS, "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);

    const barra = await screen.findByRole("progressbar", { name: "Orçamento de Transporte" });

    expect(barra).toHaveAttribute("aria-valuenow", "100");
  });

  it("só oferece categorias de despesa que ainda não têm limite", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/budgets/status": STATUS, "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);
    await screen.findByText("limite estourado");

    const campo = screen.getByLabelText("Categoria do limite");
    const opcoes = within(campo).getAllByRole("option").map((o) => o.textContent);

    expect(opcoes).toContain("Lazer");
    expect(opcoes).not.toContain("Alimentação"); // já tem limite
    expect(opcoes).not.toContain("Salário"); // receita não tem o que limitar
  });

  it("define um limite novo e envia os dados certos", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({
      "/budgets/status": STATUS,
      "/budgets": { id: 9 },
      "/categories": CATEGORIAS_COM_RECEITA,
    });
    render(<Orcamentos />);
    await screen.findByText("limite estourado");

    await userEvent.selectOptions(screen.getByLabelText("Categoria do limite"), "3");
    await userEvent.type(screen.getByLabelText("Limite mensal"), "300");
    await userEvent.click(screen.getByRole("button", { name: "Definir limite" }));

    await waitFor(() =>
      expect(bodyDe(chamadas, "PUT", "/budgets")).toEqual({
        user_id: 1, category_id: 3, monthly_limit: "300",
      }),
    );
  });

  it("mostra o erro de validação no campo que o causou", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/budgets/status": STATUS, "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);
    await screen.findByText("limite estourado");
    falharEscritaCom("PUT", "monthly_limit", "o limite precisa ser positivo");

    await userEvent.selectOptions(screen.getByLabelText("Categoria do limite"), "3");
    await userEvent.type(screen.getByLabelText("Limite mensal"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Definir limite" }));

    expect(await screen.findByText("o limite precisa ser positivo")).toBeInTheDocument();
  });

  it("altera o limite de uma categoria sem criar um segundo", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({
      "/budgets/status": STATUS,
      "/budgets": { id: 1 },
      "/categories": CATEGORIAS_COM_RECEITA,
    });
    render(<Orcamentos />);

    await userEvent.click(await screen.findByRole("button", { name: "Alterar limite de Alimentação" }));
    const campo = screen.getByLabelText("Novo limite de Alimentação");
    await userEvent.clear(campo);
    await userEvent.type(campo, "650");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(bodyDe(chamadas, "PUT", "/budgets")).toEqual({
        user_id: 1, category_id: 1, monthly_limit: "650",
      }),
    );
  });

  it("remove o orçamento escolhido", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/budgets/status": STATUS, "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);

    await userEvent.click(await screen.findByRole("button", { name: "Remover orçamento de Transporte" }));

    await waitFor(() =>
      expect(chamadas.some((c) => c.init?.method === "DELETE" && c.url.endsWith("/budgets/2"))).toBe(true),
    );
  });

  it("trocar o mês busca os números daquele mês", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/budgets/status": STATUS, "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);
    await screen.findByText("limite estourado");

    fireEvent.change(screen.getByLabelText("Mês"), { target: { value: "2026-08" } });

    await waitFor(() =>
      expect(chamadas.some((c) => c.url.includes("/budgets/status?user_id=1&month=2026-08"))).toBe(true),
    );
  });

  it("sem limites, convida a definir o primeiro", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/budgets/status": [], "/categories": CATEGORIAS_COM_RECEITA });
    render(<Orcamentos />);

    expect(await screen.findByText(/ainda não definiu limites/i)).toBeInTheDocument();
  });

  it("mostra o aviso personalizado da zona quando há payload", async () => {
    entrarComo(1, "Ana");
    mockarApi({
      "/api/upa/zones/orcamentos_aviso/payload": {
        payload: { widget: "alert_banner", label: "Transporte passou do limite", tone: "atencao" },
      },
      "/budgets/status": STATUS,
      "/categories": CATEGORIAS_COM_RECEITA,
    });
    render(<Orcamentos />);

    expect(await screen.findByText("Transporte passou do limite")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- //
// Metas
// --------------------------------------------------------------------------- //

describe("metas", () => {
  it("mostra o progresso, o que falta e o ritmo para chegar no prazo", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/goals": METAS });
    render(<Metas />);

    expect(await screen.findByText(/Faltam R\$\s*2\.500,00 \(37% guardado\)/)).toBeInTheDocument();
    expect(screen.getByText(/Guardando R\$\s*416,67 por mês você chega lá até 10\/04\/2027/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Progresso de Viagem" })).toHaveAttribute(
      "aria-valuenow", "37",
    );
  });

  it("meta atingida diz que chegou lá e não cobra ritmo", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/goals": METAS });
    render(<Metas />);

    expect(await screen.findByText("meta atingida")).toBeInTheDocument();
    expect(screen.getByText("Você chegou lá.")).toBeInTheDocument();
  });

  it("guarda um valor na meta certa", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/goals": METAS });
    render(<Metas />);

    await userEvent.type(await screen.findByLabelText("Valor a guardar em Viagem"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Guardar em Viagem" }));

    await waitFor(() =>
      expect(bodyDe(chamadas, "POST", "/goals/1/contribute")).toEqual({ amount: "100" }),
    );
  });

  it("o botão de guardar só vale com um valor digitado", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/goals": METAS });
    render(<Metas />);

    expect(await screen.findByRole("button", { name: "Guardar em Viagem" })).toBeDisabled();
  });

  it("cria uma meta sem prazo mandando o prazo como nulo", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/goals": [] });
    render(<Metas />);

    await userEvent.type(await screen.findByLabelText("Nome da meta"), "Bicicleta");
    await userEvent.type(screen.getByLabelText("Valor da meta"), "2500");
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    await waitFor(() =>
      expect(bodyDe(chamadas, "POST", "/goals")).toEqual({
        user_id: 1, name: "Bicicleta", target_amount: "2500", deadline: null,
      }),
    );
  });

  it("mostra o erro do prazo no campo do prazo", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/goals": [] });
    render(<Metas />);
    await screen.findByText(/ainda não tem metas/i);
    falharEscritaCom("POST", "deadline", "o prazo não pode estar no passado");

    await userEvent.type(screen.getByLabelText("Nome da meta"), "X");
    await userEvent.type(screen.getByLabelText("Valor da meta"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    expect(await screen.findByText("o prazo não pode estar no passado")).toBeInTheDocument();
  });

  it("exclui a meta escolhida", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/goals": METAS });
    render(<Metas />);

    await userEvent.click(await screen.findByRole("button", { name: "Excluir meta Viagem" }));

    await waitFor(() =>
      expect(chamadas.some((c) => c.init?.method === "DELETE" && c.url.endsWith("/goals/1"))).toBe(true),
    );
  });

  it("a moldura leva às duas telas novas", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/goals": [] });
    render(<Metas />);

    expect(await screen.findByRole("link", { name: "Orçamentos" })).toHaveAttribute("href", "/orcamentos");
    expect(screen.getByRole("link", { name: "Metas" })).toHaveAttribute("href", "/metas");
  });
});

// --------------------------------------------------------------------------- //
// Filtros de transação
// --------------------------------------------------------------------------- //

describe("filtros de transação", () => {
  it("a busca por texto vai para a API depois de a pessoa parar de digitar", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/transactions": TRANSACOES, "/categories": CATEGORIAS });
    render(<Transacoes />);
    await screen.findByText("Supermercado");

    await userEvent.type(screen.getByLabelText("Buscar nas descrições"), "pad");

    await waitFor(() => expect(chamadas.some((c) => c.url.includes("q=pad"))).toBe(true));
  });

  it("filtra por categoria, por tipo e por mês", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/transactions": TRANSACOES, "/categories": CATEGORIAS });
    render(<Transacoes />);
    await screen.findByText("Supermercado");

    await userEvent.selectOptions(screen.getByLabelText("Somente em"), "2");
    await userEvent.selectOptions(screen.getByLabelText("Mostrar"), "expense");
    fireEvent.change(screen.getByLabelText("Mês"), { target: { value: "2026-09" } });

    await waitFor(() =>
      expect(
        chamadas.some(
          (c) =>
            c.url.includes("category_id=2") && c.url.includes("type=expense") && c.url.includes("month=2026-09"),
        ),
      ).toBe(true),
    );
  });

  it("Limpar volta à lista inteira", async () => {
    entrarComo(1, "Ana");
    const chamadas = mockarApi({ "/transactions": TRANSACOES, "/categories": CATEGORIAS });
    render(<Transacoes />);
    await screen.findByText("Supermercado");
    await userEvent.selectOptions(screen.getByLabelText("Mostrar"), "income");
    expect(await screen.findByRole("button", { name: "Limpar" })).toBeInTheDocument();
    chamadas.length = 0;

    await userEvent.click(screen.getByRole("button", { name: "Limpar" }));

    await waitFor(() =>
      expect(chamadas.some((c) => c.url.endsWith("/transactions?user_id=1"))).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "Limpar" })).not.toBeInTheDocument();
  });

  it("a zona de atalhos da tela aparece quando há payload", async () => {
    entrarComo(1, "Ana");
    mockarApi({
      "/api/upa/zones/transacoes_atalhos/payload": {
        payload: {
          widget: "shortcut_list", label: "Você olha muito os relatórios", maxItems: 1,
          items: [{ label: "Ver relatórios", href: "/relatorios" }],
        },
      },
      "/transactions": TRANSACOES,
      "/categories": CATEGORIAS,
    });
    render(<Transacoes />);

    expect(await screen.findByText("Você olha muito os relatórios")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver relatórios/ })).toHaveAttribute("href", "/relatorios");
  });
});

// --------------------------------------------------------------------------- //
// Relatórios
// --------------------------------------------------------------------------- //

describe("relatórios: variação das despesas", () => {
  const DESPESAS = [
    { id: 1, user_id: 1, category_id: 1, category: "Alimentação", type: "expense", amount: "150.00", date: "2026-09-10", description: "a" },
    { id: 2, user_id: 1, category_id: 1, category: "Alimentação", type: "expense", amount: "100.00", date: "2026-08-10", description: "b" },
  ];

  it("compara cada mês com o anterior e não inventa base onde não há", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/transactions": DESPESAS });
    render(<Relatorios />);

    const setembro = (await screen.findByText(/setembro de 2026/i)).closest("tr")!;
    const agosto = (await screen.findByText(/agosto de 2026/i)).closest("tr")!;

    expect(within(setembro).getByText("+50%")).toBeInTheDocument();
    expect(within(agosto).queryByText(/%/)).not.toBeInTheDocument(); // sem julho, sem comparação
  });

  it("virada de ano compara dezembro com janeiro", async () => {
    entrarComo(1, "Ana");
    mockarApi({
      "/transactions": [
        { id: 1, user_id: 1, category_id: 1, category: "Alimentação", type: "expense", amount: "80.00", date: "2027-01-05", description: "a" },
        { id: 2, user_id: 1, category_id: 1, category: "Alimentação", type: "expense", amount: "100.00", date: "2026-12-05", description: "b" },
      ],
    });
    render(<Relatorios />);

    const janeiro = (await screen.findByText(/janeiro de 2027/i)).closest("tr")!;

    expect(within(janeiro).getByText("-20%")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- //
// Dashboard: o que acompanha o saldo
// --------------------------------------------------------------------------- //

describe("dashboard: painel do mês", () => {
  const MESES = [
    { month: "2026-08", income: "5200.00", expense: "2100.00" },
    { month: "2026-09", income: "5200.00", expense: "2600.00" },
  ];

  it("mostra o orçamento do mês, as últimas transações e a evolução mensal", async () => {
    entrarComo(1, "Ana");
    mockarApi({
      "/summary/monthly": MESES,
      "/summary": RESUMO,
      "/budgets/status": STATUS,
      "/transactions": TRANSACOES,
    });
    render(<Dashboard />);

    expect(await screen.findByText("Orçamento do mês")).toBeInTheDocument();
    expect(await screen.findByText("Últimas transações")).toBeInTheDocument();
    expect(await screen.findByText("Receitas e despesas por mês")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Receitas e despesas dos últimos 2 meses/ })).toBeInTheDocument();
    expect(screen.getByText("Supermercado")).toBeInTheDocument();
  });

  it("o saldo continua aparecendo quando nada do painel carrega", async () => {
    entrarComo(1, "Ana");
    mockarApi({ "/summary": RESUMO });
    render(<Dashboard />);

    expect(await screen.findByText(/5\.050,00/)).toBeInTheDocument();
    expect(screen.queryByText("Orçamento do mês")).not.toBeInTheDocument();
  });

  it("dado opcional torto não derruba a tela", async () => {
    entrarComo(1, "Ana");
    // a visão mensal e o orçamento chegam como objeto, não como lista
    mockarApi({ "/budgets/status": { erro: true }, "/summary/monthly": { erro: true }, "/summary": RESUMO });
    render(<Dashboard />);

    expect(await screen.findByText(/5\.050,00/)).toBeInTheDocument();
    expect(await screen.findByText("Alimentação")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- //
// Suporte
// --------------------------------------------------------------------------- //

describe("suporte com zona", () => {
  it("o canal de suporte segue funcionando e a zona aparece quando há payload", async () => {
    entrarComo(1, "Ana");
    mockarApi({
      "/api/upa/zones/suporte_ajuda/payload": {
        payload: { widget: "alert_banner", label: "Dúvida sobre orçamento?", tone: "neutral" },
      },
    });
    render(<Suporte />);

    expect(await screen.findByText("Dúvida sobre orçamento?")).toBeInTheDocument();
    expect(screen.getByText("Precisa de ajuda?")).toBeInTheDocument();
  });
});
