/**
 * A garantia do SPEC-00 §6, agora verificada a cada execução (SPEC-11 §5).
 *
 * Até aqui, "uma Zona Dinâmica nunca executa código arbitrário" era demonstrado
 * à mão pelo D4. Como o Executor passou a escrever no frontend, a garantia
 * precisa ser um teste: é ela que protege o usuário de um payload malicioso, e
 * ninguém deve poder enfraquecê-la sem a suíte ficar vermelha.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DynamicZone from "@/dynamic-zones/DynamicZone";

function Nativo() {
  return <p>resumo nativo de gastos</p>;
}

/** Responde o payload pedido em GET e registra as violações reportadas. */
function servirPayload(payload: unknown | null, status = 200) {
  const violacoes: Record<string, unknown>[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes("/violations")) {
        violacoes.push(JSON.parse(String(init?.body)));
        return { ok: true, status: 201, json: async () => ({ id: 1 }) } as Response;
      }
      if (status === 204) {
        return { ok: true, status: 204, json: async () => ({}) } as Response;
      }
      return { ok: true, status, json: async () => ({ payload }) } as Response;
    }),
  );

  return violacoes;
}

const VALIDO = {
  widget: "shortcut_list",
  label: "Acesso rápido",
  maxItems: 1,
  items: [{ label: "Relatórios", href: "/relatorios" }],
};

describe("<DynamicZone>", () => {
  it("renderiza o componente nativo quando não há personalização (204)", async () => {
    servirPayload(null, 204);

    render(
      <DynamicZone slot="resumo_financeiro" userId={2}>
        <Nativo />
      </DynamicZone>,
    );

    expect(await screen.findByText("resumo nativo de gastos")).toBeInTheDocument();
  });

  it("renderiza o widget quando o payload respeita o contrato", async () => {
    servirPayload(VALIDO);

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    expect(await screen.findByText("Acesso rápido")).toBeInTheDocument();
    expect(screen.queryByText("resumo nativo de gastos")).not.toBeInTheDocument();
  });

  it.each([
    ["label longo demais", { widget: "alert_banner", label: "x".repeat(500), tone: "atencao" }],
    [
      "href externo",
      {
        widget: "shortcut_list",
        label: "Oferta",
        maxItems: 1,
        items: [{ label: "Clique", href: "https://site-externo.example/phishing" }],
      },
    ],
    ["widget fora do catálogo", { widget: "iframe_injector", label: "iframe", tone: "neutral" }],
    ["propriedade a mais", { widget: "alert_banner", label: "ok", tone: "neutral", onClick: "alert(1)" }],
  ])("recusa payload inválido (%s), mantém o nativo e reporta a violação", async (_nome, payload) => {
    const violacoes = servirPayload(payload);

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    expect(await screen.findByText("resumo nativo de gastos")).toBeInTheDocument();
    await waitFor(() => expect(violacoes).toHaveLength(1));
    expect(violacoes[0].reason).toBeTruthy();
    expect(violacoes[0].slot).toBe("resumo_financeiro");
  });

  it("cai no nativo quando o core está fora do ar", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("rede fora"); }));

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    expect(await screen.findByText("resumo nativo de gastos")).toBeInTheDocument();
  });

  it("recusa href com quebra de linha no fim, como o core", async () => {
    const violacoes = servirPayload({
      ...VALIDO,
      items: [{ label: "Metas", href: "/metas\n" }],
    });

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    expect(await screen.findByText("resumo nativo de gastos")).toBeInTheDocument();
    await waitFor(() => expect(violacoes).toHaveLength(1));
  });

  it("no modo estrito, uma recusa vira um único registro", async () => {
    const violacoes = servirPayload({ widget: "iframe_injector", label: "Conteúdo externo" });

    render(
      <StrictMode>
        <DynamicZone slot="resumo_financeiro" userId={2}>
          <Nativo />
        </DynamicZone>
      </StrictMode>,
    );

    expect(await screen.findByText("resumo nativo de gastos")).toBeInTheDocument();
    await waitFor(() => expect(violacoes).toHaveLength(1));
    await new Promise((resolver) => setTimeout(resolver, 50));
    expect(violacoes).toHaveLength(1);
  });

  it.each([
    [40, true],
    [41, false],
  ])("conta o tamanho do label em caracteres, como o core (%i emojis)", async (quantos, aceito) => {
    const label = "💰".repeat(quantos);
    const violacoes = servirPayload({ widget: "alert_banner", label, tone: "neutral" });

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    if (aceito) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    } else {
      await waitFor(() => expect(violacoes).toHaveLength(1));
      expect(screen.getByText("resumo nativo de gastos")).toBeInTheDocument();
    }
  });
});

/** Payload ativo com id, e a revogação respondendo com o status pedido. */
function servirPayloadRevogavel(payloadId: number | undefined, statusDaRevogacao = 200) {
  const revogacoes: { url: string; corpo: Record<string, unknown> }[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes("/revoke")) {
        revogacoes.push({ url: String(url), corpo: JSON.parse(String(init?.body)) });
        return {
          ok: statusDaRevogacao < 400,
          status: statusDaRevogacao,
          json: async () => ({}),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ payload: VALIDO, payload_id: payloadId, origin: "autonoma" }),
      } as Response;
    }),
  );

  return revogacoes;
}

describe("voltar ao padrão", () => {
  it("revoga em nome da pessoa e devolve o componente nativo", async () => {
    const revogacoes = servirPayloadRevogavel(7);

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "voltar ao padrão" }));

    expect(await screen.findByText("resumo nativo de gastos")).toBeInTheDocument();
    expect(screen.queryByText("Acesso rápido")).not.toBeInTheDocument();
    expect(revogacoes).toHaveLength(1);
    expect(revogacoes[0].url).toContain("/api/upa/payloads/7/revoke");
    expect(revogacoes[0].corpo).toEqual({ por: "usuario", user_id: 1 });
  });

  it("se o core não confirma, mantém a zona e avisa", async () => {
    servirPayloadRevogavel(7, 500);

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "voltar ao padrão" }));

    expect(await screen.findByText(/Não foi possível voltar ao padrão/)).toBeInTheDocument();
    expect(screen.getByText("Acesso rápido")).toBeInTheDocument();
  });

  it("sem o id do payload, não oferece a ação", async () => {
    servirPayloadRevogavel(undefined);

    render(
      <DynamicZone slot="resumo_financeiro" userId={1}>
        <Nativo />
      </DynamicZone>,
    );

    expect(await screen.findByText("Acesso rápido")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "voltar ao padrão" })).not.toBeInTheDocument();
  });
});
