/**
 * "Sugerir melhoria": a pessoa envia e recebe de volta a decisão (§4.3.1).
 *
 * Dois comportamentos que já falharam em silêncio: o envio que falhava dizia
 * "Sugestão registrada", e a pessoa nunca sabia o que tinha acontecido com o que
 * pediu.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SuggestModal from "@/components/SuggestModal";

import { mockarApi } from "./_ajuda";

const MINHAS = [
  {
    id: 12,
    texto: "quero exportar em CSV",
    titulo: "Exportar transações em CSV",
    criada_em: "2026-10-20T13:00:00Z",
    situacao: "em_desenvolvimento",
    detalhe: "Sua sugestão virou uma tarefa e está sendo desenvolvida.",
  },
  {
    id: 9,
    texto: "um atalho para relatórios",
    titulo: null,
    criada_em: "2026-10-18T09:00:00Z",
    situacao: "personalizada",
    detalhe: "Ajustamos a área personalizável da tela /dashboard para você.",
  },
  {
    id: 4,
    texto: "integração com criptomoedas",
    titulo: null,
    criada_em: "2026-10-10T09:00:00Z",
    situacao: "descartada",
    detalhe: "Essa ideia está fora do escopo do FinTrack.",
  },
];

async function abrir() {
  await userEvent.click(screen.getByRole("button", { name: /Sugerir melhoria/ }));
}

describe("enviar uma sugestão", () => {
  it("mostra a resposta do funil e limpa o campo", async () => {
    const chamadas = mockarApi({
      "/api/proposals/external": { detail: "Recebemos sua sugestão e ela está em análise." },
    });
    render(<SuggestModal userId={1} />);
    await abrir();

    await userEvent.type(screen.getByLabelText("Sua sugestão"), "exportar em CSV");
    await userEvent.click(screen.getByRole("button", { name: "Enviar" }));

    expect(await screen.findByText(/está em análise/)).toBeInTheDocument();
    expect(screen.getByLabelText("Sua sugestão")).toHaveValue("");
    const envio = chamadas.find((c) => c.url.includes("/api/proposals/external"));
    expect(JSON.parse(String(envio?.init?.body))).toEqual({ user_id: 1, text: "exportar em CSV" });
  });

  it("quando o envio falha, diz que falhou e mantém o texto", async () => {
    mockarApi({}, { "/api/proposals/external": 503 });
    render(<SuggestModal userId={1} />);
    await abrir();

    await userEvent.type(screen.getByLabelText("Sua sugestão"), "exportar em CSV");
    await userEvent.click(screen.getByRole("button", { name: "Enviar" }));

    expect(await screen.findByText(/Não foi possível enviar sua sugestão/)).toBeInTheDocument();
    expect(screen.queryByText(/registrada/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Sua sugestão")).toHaveValue("exportar em CSV");
  });

  it("com o core fora do ar, também não finge que registrou", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("rede fora"); }));
    render(<SuggestModal userId={1} />);
    await abrir();

    await userEvent.type(screen.getByLabelText("Sua sugestão"), "exportar em CSV");
    await userEvent.click(screen.getByRole("button", { name: "Enviar" }));

    expect(await screen.findByText(/Não foi possível enviar sua sugestão/)).toBeInTheDocument();
  });
});

describe("minhas sugestões", () => {
  it("lista as sugestões da pessoa com a situação legível e o detalhe", async () => {
    const chamadas = mockarApi({ "/api/proposals/mine": MINHAS });
    render(<SuggestModal userId={2} />);
    await abrir();

    await userEvent.click(screen.getByRole("button", { name: "Minhas sugestões" }));

    expect(await screen.findByText("Exportar transações em CSV")).toBeInTheDocument();
    expect(screen.getByText("Em desenvolvimento")).toBeInTheDocument();
    expect(screen.getByText(/está sendo desenvolvida/)).toBeInTheDocument();
    expect(screen.getByText("um atalho para relatórios")).toBeInTheDocument();
    expect(screen.getByText("Tela ajustada para você")).toBeInTheDocument();
    expect(screen.getByText("Descartada")).toBeInTheDocument();
    expect(screen.getByText(/fora do escopo/)).toBeInTheDocument();
    expect(chamadas.some((c) => c.url.includes("/api/proposals/mine?user_id=2"))).toBe(true);
  });

  it("situação desconhecida aparece sem quebrar a lista", async () => {
    mockarApi({
      "/api/proposals/mine": [{ ...MINHAS[0], titulo: null, situacao: "em_quarentena" }],
    });
    render(<SuggestModal userId={1} />);
    await abrir();

    await userEvent.click(screen.getByRole("button", { name: "Minhas sugestões" }));

    expect(await screen.findByText("em quarentena")).toBeInTheDocument();
  });

  it("sem sugestões, diz isso", async () => {
    mockarApi({ "/api/proposals/mine": [] });
    render(<SuggestModal userId={1} />);
    await abrir();

    await userEvent.click(screen.getByRole("button", { name: "Minhas sugestões" }));

    expect(await screen.findByText(/ainda não enviou nenhuma sugestão/)).toBeInTheDocument();
  });

  it("se a lista não carrega, avisa em vez de mostrar vazio", async () => {
    mockarApi({}, { "/api/proposals/mine": 500 });
    render(<SuggestModal userId={1} />);
    await abrir();

    await userEvent.click(screen.getByRole("button", { name: "Minhas sugestões" }));

    expect(await screen.findByText(/Não foi possível carregar suas sugestões/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText(/ainda não enviou/)).not.toBeInTheDocument(),
    );
  });
});
