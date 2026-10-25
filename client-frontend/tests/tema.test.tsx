import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import AppShell from "@/components/AppShell";
import { entrarComo } from "./_ajuda";

vi.mock("@/components/SuggestModal", () => ({
  default: () => null,
}));

vi.mock("@/lib/telemetry", () => ({
  trackPageView: vi.fn(),
}));

function renderShell() {
  return render(<AppShell>{(persona) => <p>Olá, {persona.name}</p>}</AppShell>);
}

describe("tema por persona", () => {
  it("inicia em claro sem preferência salva e mostra ação para escuro", async () => {
    entrarComo(1, "Ana");

    renderShell();

    expect(
      await screen.findByRole("button", { name: "Usar tema escuro" }),
    ).toBeVisible();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("alterna para escuro e troca o rótulo para a ação oposta", async () => {
    entrarComo(1, "Ana");

    renderShell();

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(screen.getByRole("button", { name: "Usar tema claro" })).toBeVisible();
  });

  it("mantém o tema escuro ao recarregar para a mesma persona", async () => {
    entrarComo(1, "Ana");

    const user = userEvent.setup();
    const { unmount } = renderShell();

    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));

    unmount();
    renderShell();

    expect(await screen.findByRole("button", { name: "Usar tema claro" })).toBeVisible();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("isola preferência por persona ao alternar entre usuários", async () => {
    entrarComo(1, "Ana");

    const user = userEvent.setup();
    const primeiraMontagem = renderShell();

    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));
    primeiraMontagem.unmount();

    entrarComo(2, "Bruno");
    const segundaMontagem = renderShell();

    expect(
      await screen.findByRole("button", { name: "Usar tema escuro" }),
    ).toBeVisible();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    segundaMontagem.unmount();

    entrarComo(1, "Ana");
    renderShell();

    expect(await screen.findByRole("button", { name: "Usar tema claro" })).toBeVisible();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("volta para claro e persiste a nova escolha da persona ativa", async () => {
    entrarComo(1, "Ana");

    const user = userEvent.setup();
    const { unmount } = renderShell();

    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));
    await user.click(screen.getByRole("button", { name: "Usar tema claro" }));

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(screen.getByRole("button", { name: "Usar tema escuro" })).toBeVisible();

    unmount();
    renderShell();

    expect(
      await screen.findByRole("button", { name: "Usar tema escuro" }),
    ).toBeVisible();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });
});
