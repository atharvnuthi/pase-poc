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

    const botaoTema = await screen.findByRole("button", { name: "Usar tema escuro" });
    expect(botaoTema).toBeVisible();
    expect(botaoTema.querySelector('svg[data-icon="moon"]')).toBeInTheDocument();
    expect(botaoTema.textContent?.trim()).toBe("");
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

    const botaoTema = screen.getByRole("button", { name: "Usar tema claro" });
    expect(botaoTema).toBeVisible();
    expect(botaoTema.querySelector('svg[data-icon="sun"]')).toBeInTheDocument();
  });

  it("mantém o tema escuro ao recarregar para a mesma persona", async () => {
    entrarComo(1, "Ana");

    const user = userEvent.setup();
    const { unmount } = renderShell();

    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));

    unmount();
    renderShell();

    const botaoTema = await screen.findByRole("button", { name: "Usar tema claro" });
    expect(botaoTema).toBeVisible();
    expect(botaoTema.querySelector('svg[data-icon="sun"]')).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("isola preferência por persona ao alternar entre usuários", async () => {
    entrarComo(1, "Ana");

    const user = userEvent.setup();
    const primeiraMontagem = renderShell();

    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));

    const botaoTemaAna = screen.getByRole("button", { name: "Usar tema claro" });
    expect(botaoTemaAna.querySelector('svg[data-icon="sun"]')).toBeInTheDocument();

    primeiraMontagem.unmount();

    entrarComo(2, "Bruno");
    const segundaMontagem = renderShell();

    const botaoTemaBruno = await screen.findByRole("button", { name: "Usar tema escuro" });
    expect(botaoTemaBruno).toBeVisible();
    expect(botaoTemaBruno.querySelector('svg[data-icon="moon"]')).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    segundaMontagem.unmount();

    entrarComo(1, "Ana");
    renderShell();

    const botaoTemaAnaRestaurado = await screen.findByRole("button", {
      name: "Usar tema claro",
    });
    expect(botaoTemaAnaRestaurado).toBeVisible();
    expect(botaoTemaAnaRestaurado.querySelector('svg[data-icon="sun"]')).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("volta para claro e persiste a nova escolha da persona ativa", async () => {
    entrarComo(1, "Ana");

    const user = userEvent.setup();
    const { unmount } = renderShell();

    await user.click(await screen.findByRole("button", { name: "Usar tema escuro" }));
    await user.click(screen.getByRole("button", { name: "Usar tema claro" }));

    const botaoTema = screen.getByRole("button", { name: "Usar tema escuro" });
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(botaoTema).toBeVisible();
    expect(botaoTema.querySelector('svg[data-icon="moon"]')).toBeInTheDocument();

    unmount();
    renderShell();

    const botaoTemaPersistido = await screen.findByRole("button", { name: "Usar tema escuro" });
    expect(botaoTemaPersistido).toBeVisible();
    expect(botaoTemaPersistido.querySelector('svg[data-icon="moon"]')).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("mantém o botão de tema sem texto visível em ambos os estados", async () => {
    entrarComo(1, "Ana");

    renderShell();

    const user = userEvent.setup();
    const botaoClaro = await screen.findByRole("button", { name: "Usar tema escuro" });
    expect(botaoClaro.textContent?.trim()).toBe("");
    expect(botaoClaro.querySelector('svg[data-icon="moon"]')).toBeInTheDocument();

    await user.click(botaoClaro);

    const botaoEscuro = screen.getByRole("button", { name: "Usar tema claro" });
    expect(botaoEscuro.textContent?.trim()).toBe("");
    expect(botaoEscuro.querySelector('svg[data-icon="sun"]')).toBeInTheDocument();
  });
});
