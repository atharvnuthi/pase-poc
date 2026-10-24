/**
 * Persona ativa. Não há autenticação nesta PoC (ver CLAUDE.md): o usuário é
 * escolhido na tela inicial e guardado no localStorage.
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const KEY = "fintrack.userId";
const NAME_KEY = "fintrack.userName";

export function setPersona(id: number, name: string): void {
  localStorage.setItem(KEY, String(id));
  localStorage.setItem(NAME_KEY, name);
}

export function clearPersona(): void {
  localStorage.removeItem(KEY);
  localStorage.removeItem(NAME_KEY);
}

export function readPersona(): { id: number; name: string } | null {
  if (typeof window === "undefined") return null;
  const id = localStorage.getItem(KEY);
  if (!id) return null;
  return { id: Number(id), name: localStorage.getItem(NAME_KEY) ?? "" };
}

/**
 * Persona da sessão. Enquanto `loading` for true nada deve ser renderizado -
 * o localStorage só existe no navegador, então a primeira passagem é sempre vazia.
 * Sem persona, manda de volta para a seleção.
 */
export function usePersona(): {
  persona: { id: number; name: string } | null;
  loading: boolean;
} {
  const router = useRouter();
  const [persona, setPersonaState] = useState<{ id: number; name: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = readPersona();
    if (!stored) {
      router.replace("/");
      return;
    }
    setPersonaState(stored);
    setLoading(false);
  }, [router]);

  return { persona, loading };
}
