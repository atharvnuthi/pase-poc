/**
 * Sugestões da pessoa ao PASE - a Captação Ativa (SPEC-03 §1).
 *
 * Fala com o pase-core, não com o client-backend: a sugestão entra no funil do
 * PASE, e é dele que volta a decisão tomada sobre ela (§4.3.1).
 */

const CORE_URL = process.env.NEXT_PUBLIC_CORE_URL ?? "http://localhost:8000";

export type Situacao =
  | "em_analise"
  | "descartada"
  | "ja_existe"
  | "personalizada"
  | "aguardando_decisao"
  | "em_desenvolvimento"
  | "recusada"
  | "aprovada"
  | "publicada";

export interface MinhaSugestao {
  id: number;
  texto: string;
  titulo: string | null;
  criada_em: string;
  situacao: Situacao;
  /** Uma frase sobre o que aconteceu com a sugestão. */
  detalhe: string;
}

export type Tom = "neutro" | "andamento" | "positivo" | "negativo";

/** Como cada situação aparece para a pessoa: nome legível e cor do selo. */
export const SITUACOES: Record<Situacao, { rotulo: string; tom: Tom }> = {
  em_analise: { rotulo: "Em análise", tom: "neutro" },
  aguardando_decisao: { rotulo: "Aguardando decisão", tom: "neutro" },
  em_desenvolvimento: { rotulo: "Em desenvolvimento", tom: "andamento" },
  aprovada: { rotulo: "Aprovada", tom: "positivo" },
  publicada: { rotulo: "Publicada", tom: "positivo" },
  personalizada: { rotulo: "Tela ajustada para você", tom: "positivo" },
  ja_existe: { rotulo: "Já existe", tom: "neutro" },
  descartada: { rotulo: "Descartada", tom: "negativo" },
  recusada: { rotulo: "Recusada", tom: "negativo" },
};

/** Situação que o core passar a usar antes desta tela aprender: mostra sem quebrar. */
export function situacaoLegivel(situacao: string): { rotulo: string; tom: Tom } {
  return SITUACOES[situacao as Situacao] ?? { rotulo: situacao.replace(/_/g, " "), tom: "neutro" };
}

/** Envia a sugestão. Devolve a mensagem do funil; erro de rede ou HTTP propaga. */
export async function enviarSugestao(userId: number, texto: string): Promise<string | null> {
  const resposta = await fetch(`${CORE_URL}/api/proposals/external`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, text: texto }),
  });
  if (!resposta.ok) throw new Error(`${resposta.status} ao enviar a sugestão`);
  const corpo = await resposta.json();
  return typeof corpo?.detail === "string" ? corpo.detail : null;
}

/** As sugestões desta pessoa, da mais nova para a mais antiga. */
export async function minhasSugestoes(userId: number): Promise<MinhaSugestao[]> {
  const resposta = await fetch(`${CORE_URL}/api/proposals/mine?user_id=${userId}`, {
    cache: "no-store",
  });
  if (!resposta.ok) throw new Error(`${resposta.status} ao buscar as sugestões`);
  const corpo: unknown = await resposta.json();
  return Array.isArray(corpo) ? (corpo as MinhaSugestao[]) : [];
}

/** `2026-10-24T13:05:00Z` vira `24/10/2026`. */
export function formatarDia(iso: string): string {
  const data = new Date(iso);
  return Number.isNaN(data.getTime()) ? "" : data.toLocaleDateString("pt-BR");
}
