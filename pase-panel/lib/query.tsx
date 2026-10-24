"use client";

/**
 * Cache do painel, invalidado por eventos reais (SPEC-06 §1).
 *
 * O painel não pergunta em loop: ele abre uma conexão SSE com o pase-core e
 * invalida o cache quando algo de fato muda. A diferença aparece na demonstração
 * - uma tarefa aprovada caminha pelos estados na tela, sozinha, enquanto você
 * fala; com polling ela andaria aos trancos, no ritmo do intervalo.
 */

import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { Interacoes } from "@/components/interacoes";

import { CORE } from "./api";

const Conexao = createContext(false);

/** `true` enquanto o SSE com o pase-core está aberto. */
export function useConexao(): boolean {
  return useContext(Conexao);
}

/** Mapa evento → chaves de cache a invalidar. */
const INVALIDA: Record<string, string[][]> = {
  "task.created": [["tasks"], ["discards"], ["graph"], ["system-health"]],
  "task.updated": [["tasks"], ["task"], ["discards"], ["graph"], ["system-health"]],
  "proposal.processed": [["tasks"], ["discards"], ["graph"], ["system-health"]],
  "zone.payload.created": [["payloads"]],
};

function ConexaoDeEventos({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const [conectado, setConectado] = useState(false);

  useEffect(() => {
    const fonte = new EventSource(`${CORE}/api/events/stream`);

    fonte.onopen = () => setConectado(true);
    fonte.onerror = () => setConectado(false);

    fonte.addEventListener("pase", (evento) => {
      try {
        const { type } = JSON.parse((evento as MessageEvent).data);
        for (const chave of INVALIDA[type] ?? [["tasks"]]) {
          void client.invalidateQueries({ queryKey: chave });
        }
      } catch {
        void client.invalidateQueries();
      }
    });

    return () => fonte.close();
  }, [client]);

  return <Conexao.Provider value={conectado}>{children}</Conexao.Provider>;
}

export function Provedores({ children }: { children: React.ReactNode }) {
  const client = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          // sem refetch periódico: quem avisa é o SSE
          queries: { refetchOnWindowFocus: false, staleTime: 30_000, retry: 1 },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={client}>
      <ConexaoDeEventos>
        <Interacoes>{children}</Interacoes>
      </ConexaoDeEventos>
    </QueryClientProvider>
  );
}

/** Atalho para as listas do painel. */
export function useLista<T>(
  chave: string[],
  buscar: () => Promise<T>,
  opcoes?: { atualizarACada?: number },
) {
  return useQuery({
    queryKey: chave,
    queryFn: buscar,
    refetchInterval: opcoes?.atualizarACada,
  });
}
