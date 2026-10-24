/**
 * Como cada estado aparece no painel: rótulo legível e tom.
 *
 * O laranja de sinal só aparece onde uma pessoa é esperada - candidata (aprovar
 * ou recusar) e homologação (integrar ou devolver). Execução e planejamento são
 * a máquina trabalhando; olhar para eles é opcional.
 */

import { Ponto, Tag, type Tom } from "./ui";

// Os rótulos são os nomes dos estados no ciclo de vida da arquitetura (monografia §4.4.5).
export const ESTADO: Record<string, { rotulo: string; tom: Tom; espera?: boolean; vivo?: boolean }> = {
  candidata: { rotulo: "candidata", tom: "signal", espera: true },
  em_planejamento: { rotulo: "em planejamento", tom: "info", vivo: true },
  aguardando_plano: { rotulo: "aguardando aprovação do plano", tom: "signal", espera: true },
  pronta_para_despacho: { rotulo: "pronta para despacho", tom: "info" },
  em_execucao: { rotulo: "em execução", tom: "ok", vivo: true },
  em_homologacao: { rotulo: "em homologação", tom: "signal", espera: true },
  suspensa: { rotulo: "suspensa", tom: "bad" },
  finalizada: { rotulo: "finalizada", tom: "neutro" },
};

export const DESFECHO: Record<string, { rotulo: string; tom: Tom }> = {
  aprovada: { rotulo: "aprovada", tom: "ok" },
  recusada: { rotulo: "recusada", tom: "neutro" },
  revertida: { rotulo: "revertida", tom: "warn" },
  cancelada: { rotulo: "cancelada", tom: "neutro" },
};

export const RUN: Record<string, { rotulo: string; tom: Tom }> = {
  sucesso: { rotulo: "sucesso", tom: "ok" },
  falha: { rotulo: "falha", tom: "bad" },
  interrompida_budget: { rotulo: "sem orçamento", tom: "warn" },
};

export const RISCO: Record<string, Tom> = { baixo: "neutro", medio: "warn", alto: "bad" };

export const ALERTA: Record<string, { rotulo: string; tom: Tom }> = {
  retries: { rotulo: "tentativas esgotadas", tom: "bad" },
  budget: { rotulo: "teto de tokens", tom: "warn" },
  merge_conflict: { rotulo: "conflito de merge", tom: "bad" },
  ci_develop: { rotulo: "CI da develop reprovou", tom: "bad" },
};

/** Onde a entrega está no fluxo de branches. */
export const ESTAGIO: Record<string, { rotulo: string; tom: Tom }> = {
  develop: { rotulo: "na develop", tom: "info" },
  release: { rotulo: "numa release", tom: "zone" },
  producao: { rotulo: "em produção", tom: "ok" },
};

/** Ordem do ciclo de vida, para o trilho da tarefa. */
export const CICLO = [
  "candidata",
  "em_planejamento",
  "aguardando_plano",
  "pronta_para_despacho",
  "em_execucao",
  "em_homologacao",
  "finalizada",
] as const;

/** Rótulo de um estado para texto corrido, como o histórico de transições. */
export function rotuloDoEstado(status: string): string {
  return ESTADO[status]?.rotulo ?? status.replace(/_/g, " ");
}

export function Estado({ status }: { status: string }) {
  const e = ESTADO[status] ?? { rotulo: status.replace(/_/g, " "), tom: "neutro" as Tom };
  return (
    <Tag tom={e.tom} ponto>
      {e.rotulo}
    </Tag>
  );
}

export function Desfecho({ outcome }: { outcome: string | null }) {
  if (!outcome) return null;
  const d = DESFECHO[outcome] ?? { rotulo: outcome, tom: "neutro" as Tom };
  return <Tag tom={d.tom}>{d.rotulo}</Tag>;
}

export function Risco({ tier }: { tier: string }) {
  return <Tag tom={RISCO[tier] ?? "neutro"}>risco {tier}</Tag>;
}

export function Alerta({ alert }: { alert: string }) {
  const a = ALERTA[alert];
  if (!a) return null;
  return <Tag tom={a.tom}>{a.rotulo}</Tag>;
}

/** Estado compacto para linhas de tabela: ponto + rótulo, sem caixa. */
export function EstadoEmLinha({ status, outcome }: { status: string; outcome?: string | null }) {
  if (status === "finalizada" && outcome) {
    const d = DESFECHO[outcome] ?? { rotulo: outcome, tom: "neutro" as Tom };
    return (
      <span className="inline-flex items-center gap-2 text-[12.5px] text-ink-2">
        <Ponto tom={d.tom} />
        {d.rotulo}
      </span>
    );
  }
  const e = ESTADO[status] ?? { rotulo: status, tom: "neutro" as Tom };
  return (
    <span className="inline-flex items-center gap-2 text-[12.5px] text-ink-2">
      <Ponto tom={e.tom} pulsando={e.vivo} />
      {e.rotulo}
    </span>
  );
}
