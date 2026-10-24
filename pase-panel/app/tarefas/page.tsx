"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alerta, DESFECHO, ESTADO, ESTAGIO, EstadoEmLinha, Risco } from "@/components/estados";
import { useAviso, usePergunta, usePerguntaComOpcao } from "@/components/interacoes";
import PanelShell from "@/components/PanelShell";
import {
  AREA_TEXTO,
  Abas,
  Botao,
  Campo,
  Carregando,
  ENTRADA,
  Secao,
  Tag,
  Vazio,
} from "@/components/ui";
import { haQuantoTempo, pase, type DiscardRow, type TaskRow } from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * Tela Tarefas (SPEC-06 §2).
 *
 * Toda decisão crítica acontece aqui, e nenhuma acontece automaticamente: o que
 * o sistema faz sozinho é preparar o trabalho e parar, esperando alguém.
 */

type Aba = "candidatas" | "andamento" | "finalizadas" | "descartadas" | "arquivo";

const EM_ANDAMENTO = [
  "aguardando_plano",
  "em_homologacao",
  "suspensa",
  "em_execucao",
  "pronta_para_despacho",
  "em_planejamento",
];

/** As etapas da esteira, na ordem em que uma tarefa as atravessa. */
const ESTEIRA: { rotulo: string; estados: string[]; aba: Aba; espera?: boolean }[] = [
  { rotulo: "Candidatas", estados: ["candidata"], aba: "candidatas", espera: true },
  { rotulo: "Plano", estados: ["em_planejamento", "aguardando_plano", "pronta_para_despacho"], aba: "andamento", espera: false },
  { rotulo: "Execução", estados: ["em_execucao"], aba: "andamento" },
  { rotulo: "Homologação", estados: ["em_homologacao"], aba: "andamento", espera: true },
  { rotulo: "Suspensas", estados: ["suspensa"], aba: "andamento" },
  { rotulo: "Finalizadas", estados: ["finalizada"], aba: "finalizadas" },
];

export default function Tarefas() {
  const [aba, setAba] = useState<Aba>("candidatas");
  const [ingestaoAberta, setIngestaoAberta] = useState(false);

  const tarefas = useLista(["tasks"], () => pase.tasks());
  const descartes = useLista(["discards"], () => pase.discards());
  const arquivadas = useLista(["tasks", "archived"], () => pase.archivedTasks());
  // Peso de cada candidata: quantos pedidos a proposta dela reúne (P0a + duplicatas).
  const ocorrencias = useLista(["tasks", "occurrences"], () => pase.occurrences());

  const todas = tarefas.data ?? [];
  const candidatas = todas.filter((t) => t.status === "candidata");
  const andamento = todas.filter((t) => EM_ANDAMENTO.includes(t.status));
  // Mais recente primeiro: aqui o que importa é histórico, não prioridade de fila.
  const finalizadas = todas
    .filter((t) => t.status === "finalizada")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  return (
    <PanelShell
      titulo="Tarefas"
      descricao="Demandas qualificadas esperando aprovação, o trabalho em curso e o que já saiu do fluxo. Aprovar libera o trabalho autônomo; homologar libera o merge."
      acoes={
        <Botao variante="primario" onClick={() => setIngestaoAberta((v) => !v)}>
          {ingestaoAberta ? "Fechar" : "Nova demanda"}
        </Botao>
      }
    >
      {ingestaoAberta && <Ingestao onEnviada={() => setAba("candidatas")} />}

      <Esteira tarefas={todas} onEscolher={setAba} />

      <div className="mt-10">
        <Abas
          atual={aba}
          onTrocar={setAba}
          abas={[
            { id: "candidatas", rotulo: "Candidatas", contagem: candidatas.length, sinal: true },
            { id: "andamento", rotulo: "Em andamento", contagem: andamento.length },
            { id: "finalizadas", rotulo: "Finalizadas", contagem: finalizadas.length },
            { id: "descartadas", rotulo: "Descartadas", contagem: (descartes.data ?? []).length },
            { id: "arquivo", rotulo: "Arquivo", contagem: (arquivadas.data ?? []).length },
          ]}
        />

        <div className="mt-5">
          {tarefas.isLoading ? (
            <Carregando texto="Buscando as tarefas" />
          ) : (
            <>
              {aba === "candidatas" && (
                <Candidatas tarefas={candidatas} pedidos={ocorrencias.data ?? {}} />
              )}
              {aba === "andamento" && <Andamento tarefas={andamento} />}
              {aba === "finalizadas" && <Finalizadas tarefas={finalizadas} />}
              {aba === "descartadas" && <Descartadas descartes={descartes.data ?? []} />}
              {aba === "arquivo" && <Arquivo tarefas={arquivadas.data ?? []} />}
            </>
          )}
        </div>
      </div>
    </PanelShell>
  );
}

// --------------------------------------------------------------------------- //
// Esteira
// --------------------------------------------------------------------------- //

function Esteira({ tarefas, onEscolher }: { tarefas: TaskRow[]; onEscolher: (a: Aba) => void }) {
  return (
    <ol className="grid grid-cols-2 overflow-hidden rounded border border-line bg-surface sm:grid-cols-3 lg:grid-cols-6">
      {ESTEIRA.map((etapa, i) => {
        const n = tarefas.filter((t) => etapa.estados.includes(t.status)).length;
        const esperando = etapa.espera && n > 0;
        return (
          <li key={etapa.rotulo} className="border-b border-r border-line last:border-r-0 lg:border-b-0">
            <button
              type="button"
              onClick={() => onEscolher(etapa.aba)}
              className="group flex h-full w-full flex-col items-start px-4 pb-4 pt-3 text-left transition-colors hover:bg-sunken/70"
            >
              <span className="flex w-full items-center gap-2">
                <span className="font-mono text-[11px] text-ink-3">0{i + 1}</span>
                <span className="eyebrow">{etapa.rotulo}</span>
              </span>
              <span
                className={`tnum mt-3 font-display text-[44px] leading-none ${
                  esperando ? "text-signal" : n === 0 ? "text-ink-3/60" : "text-ink"
                }`}
              >
                {n}
              </span>
              <span className="mt-2 h-4 text-[12px] text-signal">
                {esperando ? "esperando você" : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// --------------------------------------------------------------------------- //
// Ingestão
// --------------------------------------------------------------------------- //

function Ingestao({ onEnviada }: { onEnviada: () => void }) {
  const client = useQueryClient();
  const avisar = useAviso();
  const [tipo, setTipo] = useState<"funcional" | "engenharia">("funcional");
  const [autor, setAutor] = useState("Atharv");
  const [texto, setTexto] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);

  async function executar(nome: string, acao: () => Promise<{ outcome: string; detail: string }>) {
    setOcupado(nome);
    try {
      const r = await acao();
      avisar(`${r.outcome.replace(/_/g, " ")} - ${r.detail}`, "info");
      setTexto("");
      onEnviada();
      await client.invalidateQueries();
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(null);
    }
  }

  return (
    <Secao titulo="Nova demanda" className="mb-8">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void executar("enviar", () => pase.proposeInternal(tipo, autor, texto));
        }}
        className="grid gap-4 lg:grid-cols-[1fr_260px]"
      >
        <Campo
          rotulo="O que o produto deveria passar a fazer"
          dica="Ela passa pelo funil inteiro: normalização, memória, coerência e qualificação."
        >
          <textarea
            required
            rows={3}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Ex.: permitir corrigir a data de uma transação já lançada"
            className={AREA_TEXTO}
          />
        </Campo>

        <div className="space-y-4">
          <div>
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Origem</span>
            <div className="grid grid-cols-2 rounded border border-line-strong p-0.5">
              {(["funcional", "engenharia"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={tipo === t}
                  onClick={() => setTipo(t)}
                  className={`h-7 rounded-sm text-[12.5px] transition-colors ${
                    tipo === t ? "bg-ink text-bg" : "text-ink-2 hover:text-ink"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <Campo rotulo="Autor">
            <input value={autor} onChange={(e) => setAutor(e.target.value)} className={ENTRADA} />
          </Campo>
        </div>

        {tipo === "engenharia" && (
          <p className="rounded border border-warn/30 bg-warn/[0.07] px-3 py-2 text-[12.5px] text-ink-2 lg:col-span-2">
            Sugestão de engenharia exige autor autorizado (<code>ENGINEERING_AUTHORS</code>) e pula
            a Memória e a Coerência, indo direto à Qualificação.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4 lg:col-span-2">
          <Botao type="submit" variante="primario" ocupado={ocupado === "enviar"} disabled={!!ocupado}>
            Enviar ao funil
          </Botao>
          <span className="mx-2 hidden h-5 w-px bg-line sm:block" />
          <span className="text-[12.5px] text-ink-3">ou deixe a IA propor:</span>
          <Botao
            tamanho="sm"
            ocupado={ocupado === "exploratoria"}
            disabled={!!ocupado}
            onClick={() => executar("exploratoria", () => pase.proposeAI("exploratoria"))}
          >
            Proposta exploratória
          </Botao>
          <Botao
            tamanho="sm"
            ocupado={ocupado === "lacunas"}
            disabled={!!ocupado}
            onClick={() => executar("lacunas", () => pase.proposeAI("lacunas"))}
          >
            Análise de lacunas
          </Botao>
        </div>
      </form>
    </Secao>
  );
}

// --------------------------------------------------------------------------- //
// Linhas
// --------------------------------------------------------------------------- //

function Linha({
  task,
  lateral,
  pedidos,
  children,
}: {
  task: TaskRow;
  lateral?: React.ReactNode;
  /** Quantos pedidos a proposta da tarefa reúne. Só aparece acima de um. */
  pedidos?: number;
  children?: React.ReactNode;
}) {
  return (
    <li className="grid grid-cols-[3rem_1fr] gap-x-3 gap-y-3 px-4 py-3.5 transition-colors hover:bg-sunken/50 md:grid-cols-[3rem_1fr_auto_auto] md:items-center">
      <span className="tnum pt-px font-mono text-[12.5px] text-ink-3">#{task.id}</span>

      <div className="min-w-0">
        <Link
          href={`/tarefas/${task.id}`}
          className="font-medium text-ink decoration-line-strong underline-offset-4 hover:underline"
        >
          {task.title}
        </Link>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <Tag>{task.module}</Tag>
          <Tag>{task.change_type}</Tag>
          {task.output_type === "zona_dinamica" && <Tag tom="zone">zona dinâmica</Tag>}
          <Risco tier={task.risk_tier} />
          {pedidos !== undefined && pedidos > 1 && (
            <Tag tom="info" title="Pedidos sobre a mesma necessidade que esta tarefa reúne">
              {pedidos} pedidos
            </Tag>
          )}
          {task.uncertainty && (
            <Tag
              tom="info"
              title="Confiança abaixo de 0.5, pouco impacto para muita complexidade, ou violação de escopo alegada sem citação conferível - veja o histórico"
            >
              incerteza
            </Tag>
          )}
          <Alerta alert={task.alert} />
          {task.waiting_on_task_id && <Tag tom="warn">aguarda #{task.waiting_on_task_id}</Tag>}
          {task.parent_task_id && (
            <Link href={`/tarefas/${task.parent_task_id}`}>
              <Tag tom="info">refaz #{task.parent_task_id}</Tag>
            </Link>
          )}
        </div>
      </div>

      <div className="col-start-2 md:col-start-auto md:min-w-[150px] md:text-right">{lateral}</div>

      {children && (
        <div className="col-start-2 flex flex-wrap gap-2 md:col-start-auto md:justify-end">
          {children}
        </div>
      )}
    </li>
  );
}

function Lista({ children }: { children: React.ReactNode }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
      {children}
    </ul>
  );
}

function Prioridade({ task }: { task: TaskRow }) {
  return (
    <div
      className="font-mono text-[12px] text-ink-3"
      title={`impacto ${task.impact} − complexidade ${task.complexity} + urgência ${task.urgency_score}`}
    >
      <span className="tnum text-[15px] font-medium text-ink">
        {task.priority_score > 0 ? "+" : ""}
        {task.priority_score}
      </span>{" "}
      prioridade
      <div className="tnum mt-0.5 text-[11px]">
        {task.impact}i · {task.complexity}c · conf {task.confidence.toFixed(2)}
      </div>
    </div>
  );
}

/** Ações que mudam estado: chamam a API, avisam e invalidam o cache. */
function useAcao() {
  const client = useQueryClient();
  const avisar = useAviso();
  const [ocupado, setOcupado] = useState<string | null>(null);

  async function agir(chave: string, acao: () => Promise<unknown>, mensagem: string) {
    setOcupado(chave);
    try {
      await acao();
      avisar(mensagem);
      await client.invalidateQueries();
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(null);
    }
  }

  return { ocupado, agir };
}

// --------------------------------------------------------------------------- //
// Abas
// --------------------------------------------------------------------------- //

/** Riscos que, por padrão, param no plano - o mesmo padrão do servidor. */
const RISCOS_COM_PLANO = ["medio", "alto"];

function Candidatas({
  tarefas,
  pedidos,
}: {
  tarefas: TaskRow[];
  pedidos: Record<string, number>;
}) {
  const { ocupado, agir } = useAcao();
  const perguntar = usePergunta();
  // Escolha por tarefa; sem escolha vale o padrão do risco.
  const [revisarPlano, setRevisarPlano] = useState<Record<number, boolean>>({});
  const querRevisar = (t: TaskRow) => revisarPlano[t.id] ?? RISCOS_COM_PLANO.includes(t.risk_tier);

  if (tarefas.length === 0) {
    return (
      <Vazio titulo="Nenhuma candidata no backlog">
        Demandas que passam pelo funil aparecem aqui, ordenadas por prioridade, esperando a sua
        aprovação.
      </Vazio>
    );
  }

  return (
    <>
      <p className="mb-3 font-mono text-[11.5px] text-ink-3">
        ordenadas por impacto − complexidade + urgência
      </p>
      <Lista>
        {tarefas.map((task) => (
          <Linha
            key={task.id}
            task={task}
            lateral={<Prioridade task={task} />}
            pedidos={pedidos[String(task.id)]}
          >
            <label
              className="mr-1 flex cursor-pointer items-center gap-2 text-[12.5px] text-ink-2"
              title="Para depois do planejamento e espera você aprovar o plano, antes de gastar uma execução"
            >
              <input
                type="checkbox"
                checked={querRevisar(task)}
                onChange={(e) => setRevisarPlano({ ...revisarPlano, [task.id]: e.target.checked })}
                className="h-3.5 w-3.5 accent-[rgb(var(--ink))]"
              />
              revisar o plano
            </label>
            <Botao
              tamanho="sm"
              variante="primario"
              ocupado={ocupado === `aprovar-${task.id}`}
              disabled={ocupado !== null}
              onClick={() =>
                agir(
                  `aprovar-${task.id}`,
                  () => pase.approve(task.id, querRevisar(task)),
                  querRevisar(task)
                    ? `Tarefa #${task.id} aprovada. Você aprova o plano quando ele sair.`
                    : `Tarefa #${task.id} aprovada. O planejamento começou.`,
                )
              }
            >
              Aprovar
            </Botao>
            <Botao
              tamanho="sm"
              disabled={ocupado !== null}
              onClick={async () => {
                const motivo = await perguntar({
                  titulo: `Recusar #${task.id}?`,
                  efeito:
                    "A demanda entra no Histórico de Descartes, com embedding: pedir a mesma coisa de novo passa a ser barrado com este motivo.",
                  rotulo: "Por que não",
                  confirmar: "Recusar",
                  perigo: true,
                });
                if (motivo) {
                  void agir(
                    `recusar-${task.id}`,
                    () => pase.reject(task.id, motivo),
                    `Tarefa #${task.id} recusada.`,
                  );
                }
              }}
            >
              Recusar
            </Botao>
          </Linha>
        ))}
      </Lista>
    </>
  );
}

function Andamento({ tarefas }: { tarefas: TaskRow[] }) {
  const { ocupado, agir } = useAcao();
  const perguntarComOpcao = usePerguntaComOpcao();

  async function retomar(task: TaskRow) {
    const r = await perguntarComOpcao({
      titulo: `Retomar #${task.id}`,
      efeito:
        "Diga o que o Executor deve mudar, se quiser. Sem instrução, a tarefa tenta de novo com o mesmo plano.",
      rotulo: "O que mudar (opcional)",
      confirmar: "Retomar",
      opcional: true,
      opcao: {
        rotulo: "Atualizar o plano com esta instrução",
        padrao: true,
        dica: "Marcado, o plano é reescrito antes de executar.",
      },
    });
    if (!r) return;
    const instrucao = r.texto === "ok" ? "" : r.texto;
    void agir(
      `retomar-${task.id}`,
      () => pase.resume(task.id, instrucao, r.opcao),
      `Tarefa #${task.id} retomada.`,
    );
  }

  if (tarefas.length === 0) {
    return (
      <Vazio titulo="Nada em andamento">
        Quando você aprova uma candidata, ela passa por aqui: planejamento, execução e
        homologação.
      </Vazio>
    );
  }

  const grupos = EM_ANDAMENTO.map((estado) => ({
    estado,
    itens: tarefas.filter((t) => t.status === estado),
  })).filter((g) => g.itens.length > 0);

  return (
    <div className="space-y-8">
      {grupos.map((grupo) => (
        <section key={grupo.estado}>
          <h3 className="mb-2 flex items-center gap-2">
            <EstadoEmLinha status={grupo.estado} />
            <span className="tnum font-mono text-[11px] text-ink-3">{grupo.itens.length}</span>
            {ESTADO[grupo.estado]?.espera && (
              <span className="text-[12px] text-signal">- esperando a sua decisão</span>
            )}
          </h3>
          <Lista>
            {grupo.itens.map((task) => (
              <Linha
                key={task.id}
                task={task}
                lateral={
                  <span className="font-mono text-[11.5px] text-ink-3">
                    {haQuantoTempo(task.updated_at)}
                  </span>
                }
              >
                {task.status === "aguardando_plano" && (
                  <Link
                    href={`/tarefas/${task.id}`}
                    className="inline-flex h-7 items-center rounded border border-signal bg-signal px-2.5 text-[12.5px] font-medium text-white hover:bg-signal/90"
                  >
                    Revisar plano
                  </Link>
                )}
                {task.status === "em_homologacao" && (
                  <Link
                    href={`/tarefas/${task.id}`}
                    className="inline-flex h-7 items-center rounded border border-signal bg-signal px-2.5 text-[12.5px] font-medium text-white hover:bg-signal/90"
                  >
                    Homologar
                  </Link>
                )}
                {task.status === "suspensa" && (
                  <>
                    <Botao
                      tamanho="sm"
                      variante="primario"
                      ocupado={ocupado === `retomar-${task.id}`}
                      disabled={ocupado !== null}
                      onClick={() => void retomar(task)}
                    >
                      Retomar
                    </Botao>
                    <Link
                      href={`/tarefas/${task.id}`}
                      className="inline-flex h-7 items-center rounded border border-line-strong bg-surface px-2.5 text-[12.5px] font-medium hover:bg-sunken"
                    >
                      Ver execuções
                    </Link>
                  </>
                )}
              </Linha>
            ))}
          </Lista>
        </section>
      ))}
    </div>
  );
}

/**
 * Histórico do que já saiu do fluxo.
 *
 * Daqui sai a segunda chance: refazer cria uma tentativa nova da mesma demanda,
 * que leva junto o motivo - sem ele, tentar de novo é pedir o mesmo erro.
 */
function Finalizadas({ tarefas }: { tarefas: TaskRow[] }) {
  const { ocupado, agir } = useAcao();
  const perguntar = usePergunta();

  if (tarefas.length === 0) {
    return <Vazio titulo="Nenhuma tarefa finalizada ainda" />;
  }

  async function reverter(task: TaskRow) {
    const motivo = await perguntar({
      titulo: `Reverter #${task.id}?`,
      efeito: (
        <>
          O merge é desfeito com um commit de <code>revert</code>
          {task.stage === "release"
            ? " na release e na develop"
            : task.stage === "develop"
              ? " na develop"
              : " na branch principal"}{" "}
          - o histórico passa a contar que o código entrou <em>e</em> que saiu. A tarefa sai de{" "}
          <code>implemented_items</code>, então pedir o mesmo de novo volta a ser legítimo.
        </>
      ),
      rotulo: "O que estava errado",
      confirmar: "Reverter merge",
      perigo: true,
    });
    if (motivo) {
      void agir(
        `reverter-${task.id}`,
        () => pase.revert(task.id, motivo),
        `Tarefa #${task.id} revertida. O código saiu da branch principal.`,
      );
    }
  }

  async function arquivar(task: TaskRow) {
    const motivo = await perguntar({
      titulo: `Arquivar #${task.id}?`,
      efeito:
        "A tarefa sai das listas e vai para o Arquivo. Nada é apagado: o histórico, as execuções, os pareceres e os logs continuam, e você pode restaurá-la quando quiser.",
      rotulo: "Motivo (opcional)",
      confirmar: "Arquivar",
      pedeTexto: false,
    });
    if (motivo) {
      void agir(`arquivar-${task.id}`, () => pase.archive(task.id), `Tarefa #${task.id} arquivada.`);
    }
  }

  async function refazer(task: TaskRow) {
    const integrada = task.final_outcome === "aprovada" && task.stage !== "producao";
    const emProducao = task.stage === "producao";
    const feedback = await perguntar({
      titulo: `Refazer #${task.id}`,
      efeito: (
        <>
          {integrada && (
            <>
              <strong className="font-medium text-ink">O merge atual será revertido primeiro.</strong>{" "}
            </>
          )}
          {emProducao && (
            <>
              <strong className="font-medium text-ink">
                Já está em produção: nada é revertido, e a nova tarefa vira um hotfix
              </strong>{" "}
              que nasce da principal e entra por uma release nova.{" "}
            </>
          )}
          Uma tarefa nova é criada, ligada a esta, e vai direto ao planejamento. O plano anterior,
          o parecer da revisão e o que você escrever aqui vão junto - o planejamento escreve os
          critérios de aceite para cobrir exatamente o que faltou.
        </>
      ),
      rotulo: "O que não ficou certo",
      dica: "Seja concreto sobre o que você viu na tela: é isso que vira critério de aceite.",
      confirmar: integrada ? "Reverter e refazer" : "Refazer",
    });
    if (feedback) {
      void agir(
        `refazer-${task.id}`,
        async () => {
          const r = await pase.redo(task.id, feedback);
          return r;
        },
        `Tentativa nova criada a partir da #${task.id}. O planejamento começou.`,
      );
    }
  }

  return (
    <Lista>
      {tarefas.map((task) => {
        const d = task.final_outcome ? DESFECHO[task.final_outcome] : null;
        return (
          <Linha
            key={task.id}
            task={task}
            lateral={
              <div className="flex items-center gap-3 md:justify-end">
                <EstadoEmLinha status={task.status} outcome={task.final_outcome} />
                {task.stage && task.final_outcome === "aprovada" && (
                  <Link href="/entrega">
                    <Tag tom={ESTAGIO[task.stage].tom}>{ESTAGIO[task.stage].rotulo}</Tag>
                  </Link>
                )}
                <span className="font-mono text-[11.5px] text-ink-3">
                  {haQuantoTempo(task.updated_at)}
                </span>
              </div>
            }
          >
            {d && task.final_outcome !== null && (
              <Botao
                tamanho="sm"
                ocupado={ocupado === `refazer-${task.id}`}
                disabled={ocupado !== null}
                onClick={() => void refazer(task)}
              >
                Refazer
              </Botao>
            )}
            {/* Só o que entrou pode ser desfeito: recusada nunca chegou à principal. */}
            {task.stage !== "develop" && task.stage !== "release" && (
              <Botao
                tamanho="sm"
                variante="fantasma"
                ocupado={ocupado === `arquivar-${task.id}`}
                disabled={ocupado !== null}
                title="Tira da lista sem apagar nada: o histórico e os logs continuam no Arquivo"
                onClick={() => void arquivar(task)}
              >
                Arquivar
              </Botao>
            )}
            {/* Em produção a principal só muda por release: corrige-se com hotfix (Refazer). */}
            {task.final_outcome === "aprovada" && task.stage !== "producao" && (
              <Botao
                tamanho="sm"
                variante="perigo"
                ocupado={ocupado === `reverter-${task.id}`}
                disabled={ocupado !== null}
                onClick={() => void reverter(task)}
              >
                Reverter
              </Botao>
            )}
          </Linha>
        );
      })}
    </Lista>
  );
}

/**
 * O Arquivo: tarefas que saíram das listas, com tudo preservado.
 *
 * Existe porque apagar uma tarefa destruiria o rastro de uma decisão. Aqui ela
 * deixa de atrapalhar a fila, e continua inteira: a página dela abre, o histórico
 * e os logs estão lá, e as métricas ainda a contam.
 */
function Arquivo({ tarefas }: { tarefas: TaskRow[] }) {
  const { ocupado, agir } = useAcao();

  if (tarefas.length === 0) {
    return (
      <Vazio titulo="O arquivo está vazio">
        Tarefas finalizadas que você arquivar aparecem aqui, com histórico e logs intactos.
      </Vazio>
    );
  }

  return (
    <Lista>
      {tarefas.map((task) => (
        <Linha
          key={task.id}
          task={task}
          lateral={
            <div className="flex items-center gap-3 md:justify-end">
              <EstadoEmLinha status={task.status} outcome={task.final_outcome} />
              {task.archived_at && (
                <span className="font-mono text-[11.5px] text-ink-3">
                  arquivada {haQuantoTempo(task.archived_at)}
                </span>
              )}
            </div>
          }
        >
          <Botao
            tamanho="sm"
            ocupado={ocupado === `restaurar-${task.id}`}
            disabled={ocupado !== null}
            onClick={() =>
              agir(
                `restaurar-${task.id}`,
                () => pase.unarchive(task.id),
                `Tarefa #${task.id} restaurada.`,
              )
            }
          >
            Restaurar
          </Botao>
        </Linha>
      ))}
    </Lista>
  );
}

const MOTIVO = {
  duplicata: { rotulo: "duplicata", tom: "info" as const },
  incoerente: { rotulo: "fora do escopo", tom: "warn" as const },
  recusa_humana: { rotulo: "recusa humana", tom: "neutro" as const },
};

function Descartadas({ descartes }: { descartes: DiscardRow[] }) {
  if (descartes.length === 0) {
    return (
      <Vazio titulo="Nada foi descartado ainda">
        Duplicatas, demandas fora do escopo e recusas humanas ficam aqui - e na memória, para não
        voltarem com outro nome.
      </Vazio>
    );
  }

  return (
    <Lista>
      {descartes.map((d) => (
        <li
          key={d.id}
          className="grid grid-cols-[3rem_1fr] gap-x-3 gap-y-2 px-4 py-3.5 md:grid-cols-[3rem_1fr_auto]"
        >
          <span className="tnum pt-px font-mono text-[12.5px] text-ink-3">d{d.id}</span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Tag tom={MOTIVO[d.reason_type].tom}>{MOTIVO[d.reason_type].rotulo}</Tag>
              <span className="font-medium">{d.title ?? `descarte #${d.id}`}</span>
              {d.origin && <Tag>{d.origin}</Tag>}
              {d.task_id && (
                <Link href={`/tarefas/${d.task_id}`} className="font-mono text-[12px] text-ink-3 hover:text-ink">
                  #{d.task_id}
                </Link>
              )}
            </div>
            <p className="mt-1.5 text-[13px] text-ink-2">
              {d.reason_type === "duplicata" ? (
                <>
                  Bateu com <code className="text-ink">{d.matched_ref}</code>
                  {d.duplicate_count > 1 && ` · visto ${d.duplicate_count}×`}
                </>
              ) : (
                d.reason_text
              )}
            </p>
          </div>
          <span className="col-start-2 font-mono text-[11.5px] text-ink-3 md:col-start-auto">
            {haQuantoTempo(d.created_at)}
          </span>
        </li>
      ))}
    </Lista>
  );
}
