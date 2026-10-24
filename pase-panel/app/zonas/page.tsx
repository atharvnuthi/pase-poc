"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/interacoes";
import PanelShell from "@/components/PanelShell";
import { AREA_TEXTO, BlocoDeCodigo, Botao, Campo, ENTRADA, Secao, Tag, Vazio } from "@/components/ui";
import {
  core,
  haQuantoTempo,
  type ZoneEvaluationRow,
  type ZoneInfo,
  type ZonePayloadRow,
  type ZoneViolationRow,
} from "@/lib/api";
import type { Tom } from "@/components/ui";

/**
 * Tela Zonas (SPEC-05 §7).
 *
 * É onde o humano audita o loop rápido. A personalização acontece sem gate
 * humano - o gate é a validação de schema - mas tudo que ela produziu fica aqui
 * para inspeção: cada avaliação com os sinais, a decisão e o motivo do agente;
 * cada payload, com quem o revogou; cada violação, com a camada que a barrou.
 */

/** Quem revogou: a pessoa (durável), o painel ou um pedido novo dela. */
type PayloadRow = ZonePayloadRow & { revoked_by?: "usuario" | "painel" | "pedido" | null };
/** Qual das duas validações barrou o payload. */
type ViolacaoRow = ZoneViolationRow & { origem?: "cliente" | "servidor" };

const REVOGADO_POR: Record<string, string> = {
  usuario: "pela pessoa",
  painel: "pelo painel",
  pedido: "por pedido novo",
};

const RESULTADOS: Record<string, { rotulo: string; tom: Tom }> = {
  personalizou: { rotulo: "personalizou", tom: "ok" },
  recusou: { rotulo: "não personalizou", tom: "neutro" },
  fora_do_contrato: { rotulo: "barrado pelo contrato", tom: "bad" },
  pedido: { rotulo: "pedido atendido", tom: "ok" },
  pedido_recusado: { rotulo: "pedido não atendido", tom: "neutro" },
  pedido_fora_do_contrato: { rotulo: "pedido barrado pelo contrato", tom: "bad" },
};

const PERSONAS = [
  { id: 1, nome: "Ana" },
  { id: 2, nome: "Clara" },
];

const nomeDe = (id: number) => PERSONAS.find((p) => p.id === id)?.nome ?? `user ${id}`;

const EXEMPLO_INJECAO = JSON.stringify(
  { widget: "alert_banner", label: "Aviso injetado sem validação", tone: "atencao" },
  null,
  2,
);

type ComAviso = (acao: () => Promise<string>) => Promise<void>;

export default function Zonas() {
  const avisar = useAviso();
  const [payloads, setPayloads] = useState<PayloadRow[]>([]);
  const [violacoes, setViolacoes] = useState<ViolacaoRow[]>([]);
  const [avaliacoes, setAvaliacoes] = useState<ZoneEvaluationRow[]>([]);
  const [zonas, setZonas] = useState<ZoneInfo[]>([]);
  const [ocupado, setOcupado] = useState(false);

  const recarregar = useCallback(async () => {
    const [p, v, a, z] = await Promise.all([
      core.payloads(),
      core.violations(),
      core.evaluations(),
      core.zones(),
    ]);
    setPayloads(p);
    setViolacoes(v);
    setAvaliacoes(a);
    setZonas(z);
  }, []);

  useEffect(() => {
    void recarregar().catch(() => avisar("Falhou: não consegui falar com o pase-core."));
  }, [recarregar, avisar]);

  const comAviso: ComAviso = async (acao) => {
    setOcupado(true);
    try {
      avisar(await acao());
      await recarregar();
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <PanelShell
      titulo="Zonas dinâmicas"
      descricao="Personalização em runtime. O gate aqui é a validação de contrato, não uma aprovação humana - mas tudo que foi gerado fica auditável e revogável."
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <Simulador zonas={zonas} ocupado={ocupado} comAviso={comAviso} />
        <Injetor zonas={zonas} ocupado={ocupado} comAviso={comAviso} />
      </div>

      <section className="mt-10">
        <h2 className="eyebrow mb-3">Avaliações · {avaliacoes.length}</h2>
        <Avaliacoes avaliacoes={avaliacoes} />
      </section>

      <section className="mt-10">
        <h2 className="eyebrow mb-3">Payloads · {payloads.length}</h2>
        <Payloads payloads={payloads} ocupado={ocupado} comAviso={comAviso} />
      </section>

      <section className="mt-10">
        <h2 className="eyebrow mb-3">Violações · {violacoes.length}</h2>
        <Violacoes violacoes={violacoes} />
      </section>
    </PanelShell>
  );
}

function SeletorDePersona({ valor, onChange }: { valor: number; onChange: (id: number) => void }) {
  return (
    <div className="grid grid-cols-2 rounded border border-line-strong p-0.5 sm:w-48">
      {PERSONAS.map((p) => (
        <button
          key={p.id}
          type="button"
          aria-pressed={valor === p.id}
          onClick={() => onChange(p.id)}
          className={`h-7 rounded-sm text-[12.5px] ${valor === p.id ? "bg-ink text-bg" : "text-ink-2 hover:text-ink"}`}
        >
          {p.nome}
        </button>
      ))}
    </div>
  );
}

function SeletorDeZona({
  zonas,
  valor,
  onChange,
}: {
  zonas: ZoneInfo[];
  valor: string;
  onChange: (slot: string) => void;
}) {
  return (
    <Campo rotulo="Zona">
      <select value={valor} onChange={(e) => onChange(e.target.value)} className={ENTRADA}>
        {zonas.map((z) => (
          <option key={z.slot} value={z.slot}>
            {z.slot} ({z.tela})
          </option>
        ))}
      </select>
    </Campo>
  );
}

function Simulador({
  zonas,
  ocupado,
  comAviso,
}: {
  zonas: ZoneInfo[];
  ocupado: boolean;
  comAviso: ComAviso;
}) {
  const [userId, setUserId] = useState(1);
  const [slot, setSlot] = useState("resumo_financeiro");
  const zona = zonas.find((z) => z.slot === slot);

  return (
    <Secao titulo="Simulador">
      <p className="text-[13px] text-ink-2">
        Insere {zona?.acessos_minimos ?? 5} acessos a <code>{zona?.observa ?? "/relatorios"}</code> e avalia a regra da zona na hora.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <SeletorDeZona zonas={zonas} valor={slot} onChange={setSlot} />
        <SeletorDePersona valor={userId} onChange={setUserId} />
        <Botao
          variante="primario"
          disabled={ocupado}
          onClick={() =>
            comAviso(async () => {
              const r = await core.simulate(userId, slot);
              return r.personalizado
                ? `Zona personalizada para ${nomeDe(userId)}.`
                : "A regra rodou e o modelo decidiu não personalizar.";
            })
          }
        >
          Simular uso intenso
        </Botao>
      </div>
    </Secao>
  );
}

function Injetor({
  zonas,
  ocupado,
  comAviso,
}: {
  zonas: ZoneInfo[];
  ocupado: boolean;
  comAviso: ComAviso;
}) {
  const [userId, setUserId] = useState(1);
  const [slot, setSlot] = useState("resumo_financeiro");
  const [texto, setTexto] = useState(EXEMPLO_INJECAO);

  return (
    <Secao titulo="Injetor">
      <p className="text-[13px] text-ink-2">
        Grava um payload <strong className="font-medium text-ink">pulando a validação do core</strong>.
        Serve para mostrar que o cliente recusa sozinho.
      </p>
      <div className="mt-4 space-y-3">
        <SeletorDeZona zonas={zonas} valor={slot} onChange={setSlot} />
        <SeletorDePersona valor={userId} onChange={setUserId} />
        <Campo rotulo="Payload">
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={6}
            className={`${AREA_TEXTO} font-mono text-[12px]`}
          />
        </Campo>
        <Botao
          disabled={ocupado}
          onClick={() =>
            comAviso(async () => {
              const r = await core.injectRaw(userId, slot, JSON.parse(texto));
              return r.core_o_recusaria
                ? `Injetado (payload #${r.payload_id}). O core o recusaria por: ${r.erros_do_core.join("; ")}`
                : `Injetado (payload #${r.payload_id}). Este payload é válido pelo contrato.`;
            })
          }
        >
          Injetar sem validar
        </Botao>
      </div>
    </Secao>
  );
}

function Avaliacoes({ avaliacoes }: { avaliacoes: ZoneEvaluationRow[] }) {
  if (avaliacoes.length === 0) return <Vazio titulo="Nenhuma zona foi avaliada ainda" />;

  return (
    <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
      {avaliacoes.map((a) => {
        const resultado = RESULTADOS[a.resultado] ?? { rotulo: a.resultado, tom: "neutro" as Tom };
        return (
          <li key={a.id} className="px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13.5px] font-medium">{nomeDe(a.user_id)}</span>
              <Tag>{a.slot}</Tag>
              <Tag tom={resultado.tom} ponto>
                {resultado.rotulo}
              </Tag>
              {a.payload_id !== null && (
                <span className="font-mono text-[11.5px] text-ink-3">payload #{a.payload_id}</span>
              )}
              {a.violation_id !== null && (
                <span className="font-mono text-[11.5px] text-ink-3">violação #{a.violation_id}</span>
              )}
              <span className="ml-auto font-mono text-[11.5px] text-ink-3">{haQuantoTempo(a.at)}</span>
            </div>
            {a.pedido && <p className="mt-1 text-[13px] text-ink-2">Pedido: “{a.pedido}”</p>}
            {a.motivo && <p className="mt-1 text-[13px] text-ink-2">{a.motivo}</p>}
            {a.sinais && (
              <details className="mt-1.5">
                <summary className="cursor-pointer font-mono text-[12px] text-ink-3 hover:text-ink">
                  sinais enviados ao agente{a.trace_id ? ` · trace ${a.trace_id.slice(0, 8)}` : ""}
                </summary>
                <BlocoDeCodigo className="mt-2">{a.sinais}</BlocoDeCodigo>
              </details>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Payloads({
  payloads,
  ocupado,
  comAviso,
}: {
  payloads: PayloadRow[];
  ocupado: boolean;
  comAviso: ComAviso;
}) {
  if (payloads.length === 0) return <Vazio titulo="Nenhuma zona configurada ainda" />;

  return (
    <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
      {payloads.map((p) => (
        <li key={p.id} className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="tnum font-mono text-[12.5px] text-ink-3">#{p.id}</span>
            <span className="text-[13.5px] font-medium">{nomeDe(p.user_id)}</span>
            <Tag>{p.slot}</Tag>
            <Tag tom={p.origin === "autonoma" ? "zone" : "warn"}>{p.origin}</Tag>
            <Tag tom={p.status === "ativo" ? "ok" : "neutro"} ponto>
              {p.status}
              {p.revoked_by ? ` ${REVOGADO_POR[p.revoked_by] ?? p.revoked_by}` : ""}
            </Tag>
            <span className="ml-auto font-mono text-[11.5px] text-ink-3">{haQuantoTempo(p.created_at)}</span>
            {p.status === "ativo" && (
              <Botao
                tamanho="sm"
                variante="perigo"
                disabled={ocupado}
                onClick={() =>
                  comAviso(async () => {
                    await core.revoke(p.id);
                    return `Payload #${p.id} revogado. O usuário volta ao componente nativo.`;
                  })
                }
              >
                Revogar
              </Botao>
            )}
          </div>
          <details className="mt-2">
            <summary className="cursor-pointer font-mono text-[12px] text-ink-3 hover:text-ink">ver JSON</summary>
            <BlocoDeCodigo className="mt-2">{JSON.stringify(p.payload, null, 2)}</BlocoDeCodigo>
          </details>
        </li>
      ))}
    </ul>
  );
}

function Violacoes({ violacoes }: { violacoes: ViolacaoRow[] }) {
  if (violacoes.length === 0) return <Vazio titulo="Nenhum payload foi recusado" />;

  return (
    <ul className="divide-y divide-line overflow-hidden rounded border border-bad/25 bg-surface">
      {violacoes.map((v) => (
        <li key={v.id} className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="tnum font-mono text-[12.5px] text-ink-3">#{v.id}</span>
            <span className="text-[13.5px] font-medium">{nomeDe(v.user_id)}</span>
            <Tag>{v.slot}</Tag>
            <Tag
              tom={v.origem === "servidor" ? "info" : "warn"}
              title={
                v.origem === "servidor"
                  ? "O core recusou o payload do agente antes de gravá-lo."
                  : "O cliente recusou o payload antes de renderizá-lo."
              }
            >
              {v.origem === "servidor" ? "recusado no servidor" : "recusado no cliente"}
            </Tag>
            <span className="ml-auto font-mono text-[11.5px] text-ink-3">{haQuantoTempo(v.at)}</span>
          </div>
          <p className="mt-1.5 text-[13px] text-bad">{v.reason}</p>
          {v.raw_payload && (
            <details className="mt-2">
              <summary className="cursor-pointer font-mono text-[12px] text-ink-3 hover:text-ink">
                payload recusado
              </summary>
              <BlocoDeCodigo className="mt-2">{JSON.stringify(v.raw_payload, null, 2)}</BlocoDeCodigo>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}
