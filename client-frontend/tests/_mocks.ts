import { vi } from "vitest";

/**
 * Dublê do roteador, num módulo próprio.
 *
 * Dois cuidados, ambos aprendidos quebrando:
 *
 * 1. Não pode morar no `vitest.setup.ts`. O setup já é carregado pelo runner, e
 *    um teste importando o mesmo arquivo o avalia outra vez - o que, com o
 *    hoisting do `vi.mock`, trava o runner antes de coletar os testes.
 * 2. `useRouter()` precisa devolver **sempre o mesmo objeto**. O Next devolve uma
 *    referência estável, e componentes põem `router` na lista de dependências do
 *    `useEffect` (ver `lib/user.ts`). Devolver um objeto novo a cada render faz o
 *    efeito rodar de novo a cada render: loop infinito, sem erro, sem timeout.
 */
export const navegou = vi.fn();
export const substituiu = vi.fn();

export const roteador = { push: navegou, replace: substituiu, prefetch: vi.fn(), back: vi.fn() };
