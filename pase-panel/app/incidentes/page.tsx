"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAviso } from "@/components/interacoes";
import PanelShell from "@/components/PanelShell";
import { AREA_TEXTO, Botao, Campo, Carregando, ENTRADA, Secao, Tag, Vazio, type Tom } from "@/components/ui";
import { haQuantoTempo, pase } from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * Tela Incidentes (SPEC-06 §4).
 *
 * Existe para dar ao Fator de Urgência algo real para ler: um incidente `alto`
 * num módulo empurra para cima toda tarefa candidata daquele módulo. Sem isso, a
 * priorização seria só impacto menos complexidade, sem contato com a operação.
 */

const SEVERIDADES = [
  { valor: "alto", peso: "+3 de urgência" },
  { valor: "medio", peso: "+1 de urgência" },
  { valor: "baixo", peso: "sem efeito na urgência" },
];

const MODULOS = ["dashboard", "transacoes", "orcamentos", "metas", "relatorios", "suporte", "geral"];

const TOM: Record<string, Tom> = { alto: "bad", medio: "warn", baixo: "neutro" };

export default function Incidentes() {
  const client = useQueryClient();
  const avisar = useAviso();
  const incidentes = useLista(["incidents"], () => pase.incidents());

  const [titulo, setTitulo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [severidade, setSeveridade] = useState("alto");
  const [modulo, setModulo] = useState("transacoes");
  const [ocupado, setOcupado] = useState(false);

  async function criar(evento: React.FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    try {
      await pase.createIncident({ title: titulo, description: descricao, severity: severidade, module: modulo });
      avisar(`Incidente registrado. A urgência das candidatas de "${modulo}" foi recalculada.`);
      setTitulo("");
      setDescricao("");
      await client.invalidateQueries();
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(false);
    }
  }

  const lista = incidentes.data ?? [];

  return (
    <PanelShell
      titulo="Incidentes"
      descricao="Problemas em operação. Um incidente eleva a urgência das tarefas candidatas do módulo afetado, mudando a ordem do backlog."
    >
      <div className="grid gap-8 lg:grid-cols-[380px_1fr]">
        <Secao titulo="Registrar">
          <form onSubmit={criar} className="space-y-4">
            <Campo rotulo="O que está acontecendo">
              <input required value={titulo} onChange={(e) => setTitulo(e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="Detalhes" dica="Opcional.">
              <textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={3} className={AREA_TEXTO} />
            </Campo>
            <div className="grid grid-cols-2 gap-3">
              <Campo rotulo="Severidade">
                <select value={severidade} onChange={(e) => setSeveridade(e.target.value)} className={ENTRADA}>
                  {SEVERIDADES.map((s) => (
                    <option key={s.valor} value={s.valor}>
                      {s.valor}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo rotulo="Módulo">
                <select value={modulo} onChange={(e) => setModulo(e.target.value)} className={ENTRADA}>
                  {MODULOS.map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
              </Campo>
            </div>
            <p className="font-mono text-[11.5px] text-ink-3">
              {SEVERIDADES.find((s) => s.valor === severidade)?.peso}
            </p>
            <Botao type="submit" variante="primario" ocupado={ocupado}>
              Registrar incidente
            </Botao>
          </form>
        </Secao>

        <section>
          <h2 className="eyebrow mb-3">Registrados · {lista.length}</h2>
          {incidentes.isLoading ? (
            <Carregando />
          ) : lista.length === 0 ? (
            <Vazio titulo="Nenhum incidente">Tudo calmo em produção, ou ninguém registrou ainda.</Vazio>
          ) : (
            <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
              {lista.map((i) => (
                <li key={i.id} className="px-4 py-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag tom={TOM[i.severity]} ponto>
                      {i.severity}
                    </Tag>
                    <span className="font-medium">{i.title}</span>
                    {i.module && <Tag>{i.module}</Tag>}
                    {i.source === "sentry_stub" && <Tag>sentry</Tag>}
                    <span className="ml-auto font-mono text-[11.5px] text-ink-3">{haQuantoTempo(i.created_at)}</span>
                  </div>
                  {i.description && <p className="mt-1.5 text-[13px] text-ink-2">{i.description}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </PanelShell>
  );
}
