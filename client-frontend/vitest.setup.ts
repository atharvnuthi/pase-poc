import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, vi } from "vitest";

import { navegou, roteador, substituiu } from "./tests/_mocks";

// O App Router não existe em jsdom: o roteador é dublado e cada teste verifica
// para onde a navegação foi pedida.
vi.mock("next/navigation", () => ({
  useRouter: () => roteador,
  usePathname: () => "/dashboard",
  redirect: (destino: string) => navegou(destino),
}));

// `createElement` importado no topo: `require` não existe em contexto ESM e um
// throw dentro da fábrica do mock trava o runner em silêncio.
vi.mock("next/link", () => ({
  default: ({ children, href, ...resto }: { children: ReactNode; href: string }) =>
    createElement("a", { href, ...resto }, children),
}));

afterEach(() => {
  cleanup();
  navegou.mockClear();
  substituiu.mockClear();
  localStorage.clear();
  vi.restoreAllMocks();
});
