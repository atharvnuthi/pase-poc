"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useEffect, useState } from "react";

import {
  Alerta,
  CICLO,
  ESTADO,
  ESTAGIO,
  Estado,
  Desfecho,
  RUN,
  Risco,
  rotuloDoEstado,
} from "@/components/estados";
import { useAviso, usePergunta, usePerguntaComOpcao } from "@/components/interacoes";
import PanelShell from "@/components/PanelShell";
import {
  AREA_TEXTO,
  Abas,
  Botao,
  BlocoDeCodigo,
  Campo,
  Carregando,
  Diff,
  ENTRADA,
  Secao,
  Tag,
  Vazio,
} from "@/components/ui";
import {
  formatarData,
  milhar,
  pase,
  type AcaoNoArquivo,
  type CriterioRevisado,
  type Orcamento,
  type Parecer,
  type Plano,
  type RunRow,
  type TaskRow,
  type Transicao,
} from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * Tela Tarefa[id] (SPEC-06 §3).
 *
 * É a tela da decisão mais cara do sistema: aprovar o merge de código que
 * ninguém escreveu à mão. Por isso ela mostra o planejado, o executado, o que a
 * revisão independente concluiu critério a critério e a conversa inteira que
 * produziu o resultado - o humano revisa o que já passou pela máquina, mas
 * revisa com tudo à vista.
 */

type Aba = "planejamento" | "execucoes" | "homologacao";

const RISCOS = ["baixo", "medio", "alto"];
const TIPOS = ["feature", "fix", "refactor", "docs", "test", "chore"];

/** Risco técnico do plano (P4): o que pode quebrar no que já funciona. */
const TOM_DO_RISCO = { baixo: "ok", medio: "warn", alto: "bad" } as const;

/** Ação de cada arquivo no mapeamento de impacto. */
const COR_DA_ACAO: Record<AcaoNoArquivo, string> = {
  modificar: "text-ink-3",
  criar: "text-ok",
  excluir: "text-bad",
};

// --------------------------------------------------------------------------- //
// Trilho do ciclo de vida
// --------------------------------------------------------------------------- //

function Trilho({ status, history }: { status: string; history: Transicao[] }) {
  const atual = CICLO.indexOf(status as (typeof CICLO)[number]);
  const suspensa = status === "suspensa";
  // A aprovação do plano só é exigida por risco ou por escolha do gestor: quem
  // passou direto vê a etapa riscada, não como cumprida.
  const passouPeloPlano = history.some((h) => h.to === "aguardando_plano");
  return (
    <ol className="grid grid-cols-3 gap-y-3 sm:grid-cols-7">
      {CICLO.map((etapa, i) => {
        const pulada = etapa === "aguardando_plano" && !passouPeloPlano && atual > i;
        const feita = !suspensa && atual > i && !pulada;
        const ativa = !suspensa && atual === i;
        const espera = ESTADO[status]?.espera && ativa;
        return (
          <li key={etapa} className="relative pr-3">
            <div className="flex items-center">
              <span
                className={`h-2.5 w-2.5 shrink-0 rounded-full border-2 ${
                  ativa
                    ? espera
                      ? "border-signal bg-signal"
                      : "border-ink bg-ink"
                    : feita
                      ? "border-ink bg-ink"
                      : "border-line-strong bg-surface"
                }`}
              />
              {i < CICLO.length - 1 && (
                <span className={`ml-1 h-px flex-1 ${feita ? "bg-ink" : "bg-line-strong/70"}`} />
              )}
            </div>
            <p
              className={`mt-2 text-[12px] ${
                ativa ? "font-medium text-ink" : feita ? "text-ink-2" : "text-ink-3"
              }`}
            >
              {ESTADO[etapa]?.rotulo}
              {pulada && <span className="block text-ink-3">não exigida</span>}
            </p>
          </li>
        );
      })}
      {suspensa && (
        <li className="col-span-full">
          <p className="text-[12.5px] text-bad">Suspensa - o trabalho parou e espera você.</p>
        </li>
      )}
    </ol>
  );
}

// --------------------------------------------------------------------------- //
// Controles
// --------------------------------------------------------------------------- //

/**
 * Onde a tarefa deixa de ser um trilho.
 *
 * Antes daqui, uma tarefa suspensa por budget não tinha saída: "Retomar" criava
 * uma execução que morria antes da primeira chamada, porque o gasto já passara
 * do teto. O problema não era a execução: era não haver como mexer no teto.
 */
function Controles({ task, orcamento }: { task: TaskRow; orcamento: Orcamento }) {
  const client = useQueryClient();
  const avisar = useAviso();
  const perguntar = usePergunta();
  const perguntarComOpcao = usePerguntaComOpcao();
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [campos, setCampos] = useState({
    title: task.title,
    risk_tier: task.risk_tier as string,
    change_type: task.change_type,
    impact: task.impact,
    complexity: task.complexity,
  });

  const terminada = task.status === "finalizada";
  const semFolga = orcamento.restante <= 0;
  const podeReplanejar = ["suspensa", "em_homologacao"].includes(task.status);
  const pct = Math.min(100, Math.round((orcamento.gasto / Math.max(orcamento.teto, 1)) * 100));

  async function agir(nome: string, acao: () => Promise<unknown>, mensagem: string) {
    setOcupado(nome);
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

  async function ajustarOrcamento() {
    const valor = await perguntar({
      titulo: "Teto de tokens",
      efeito: (
        <>
          Gasto até agora: <strong className="tnum">{milhar(orcamento.gasto)}</strong>. Teto atual:{" "}
          <strong className="tnum">{milhar(orcamento.teto)}</strong>. Uma chamada de geração custa
          dezenas de milhares de tokens: o teto precisa deixar folga para pelo menos uma, senão a
          execução para antes de começar. Digite 0 para voltar ao cálculo automático.
        </>
      ),
      rotulo: "Novo teto",
      confirmar: "Salvar teto",
      numerico: true,
      valorInicial: String(Math.max(orcamento.gasto * 2, orcamento.teto * 2)),
    });
    if (valor === null) return;

    const numero = Number(valor.replace(/\D/g, ""));
    if (Number.isNaN(numero)) {
      avisar("Falhou: teto inválido.");
      return;
    }
    void agir(
      "teto",
      () => pase.editTask(task.id, { budget_cap_tokens: numero }),
      numero === 0
        ? "Teto manual removido: volta a valer o cálculo automático."
        : `Teto agora é ${milhar(numero)} tokens.`,
    );
  }

  async function retomar() {
    const r = await perguntarComOpcao({
      titulo: `Retomar #${task.id}`,
      efeito:
        "Diga o que o Executor deve mudar, se quiser. Sem instrução, a tarefa tenta de novo com o mesmo plano.",
      rotulo: "O que mudar (opcional)",
      dica: "Ex.: o endpoint já existe, falta só a tela.",
      confirmar: "Retomar",
      opcional: true,
      opcao: {
        rotulo: "Atualizar o plano com esta instrução",
        padrao: true,
        dica: "Marcado, o plano é reescrito antes de executar. Desmarque para manter o plano e só orientar a execução.",
      },
    });
    if (!r) return;
    const instrucao = r.texto === "ok" ? "" : r.texto;
    void agir(
      "retomar",
      () => pase.resume(task.id, instrucao, r.opcao),
      !instrucao
        ? `Tarefa #${task.id} retomada.`
        : r.opcao
          ? `Tarefa #${task.id} retomada com o plano reescrito.`
          : `Tarefa #${task.id} retomada com a sua instrução.`,
    );
  }

  async function cancelar() {
    const r = await perguntarComOpcao({
      titulo: `Cancelar #${task.id}?`,
      efeito:
        "A tarefa é interrompida. Em execução, o Executor para no próximo ponto de checagem, antes de gastar a próxima chamada.",
      confirmar: "Cancelar tarefa",
      perigo: true,
      opcao: {
        rotulo: "Lembrar como descartada",
        padrao: true,
        dica: "A memória passa a barrar o mesmo pedido, com este motivo. Desmarque se for refazer a tarefa.",
      },
    });
    if (r) {
      void agir(
        "cancelar",
        () => pase.cancelTask(task.id, r.texto, r.opcao),
        r.opcao
          ? `Tarefa #${task.id} cancelada e registrada nas descartadas.`
          : `Tarefa #${task.id} cancelada.`,
      );
    }
  }

  return (
    <Secao
      titulo="Controles"
      acoes={
        <div className="flex items-center gap-3 font-mono text-[11.5px] text-ink-3">
          {orcamento.manual && <span>teto manual</span>}
          {semFolga && <span className="text-warn">sem folga para outra chamada</span>}
        </div>
      }
    >
      <div className="mb-4">
        <div className="flex items-baseline justify-between font-mono text-[12px] text-ink-2">
          <span>orçamento de tokens</span>
          <span className="tnum">
            {milhar(orcamento.gasto)} / {milhar(orcamento.teto)}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken">
          <div
            className={`h-full rounded-full ${semFolga ? "bg-warn" : "bg-ink"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Botao
          ocupado={ocupado === "retomar"}
          disabled={task.status !== "suspensa" || semFolga || ocupado !== null}
          title={semFolga ? "Sem folga no teto: ajuste o orçamento antes" : "Nova execução, com o mesmo plano"}
          onClick={() => void retomar()}
        >
          Retomar
        </Botao>
        <Botao disabled={terminada || ocupado !== null} onClick={() => void ajustarOrcamento()}>
          Ajustar orçamento
        </Botao>
        <Botao
          ocupado={ocupado === "replan"}
          disabled={!podeReplanejar || ocupado !== null}
          title="Joga o plano fora e planeja de novo, do zero"
          onClick={() => agir("replan", () => pase.replan(task.id), `Tarefa #${task.id} vai replanejar.`)}
        >
          Replanejar
        </Botao>
        <Botao disabled={terminada} onClick={() => setEditando((v) => !v)}>
          {editando ? "Fechar edição" : "Editar"}
        </Botao>
        <Botao
          variante="perigo"
          className="ml-auto"
          disabled={terminada || ocupado !== null}
          onClick={() => void cancelar()}
        >
          Cancelar
        </Botao>
      </div>

      {editando && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void agir("salvar", () => pase.editTask(task.id, campos), `Tarefa #${task.id} atualizada.`).then(
              () => setEditando(false),
            );
          }}
          className="mt-5 grid gap-4 border-t border-line pt-5 sm:grid-cols-2"
        >
          <Campo rotulo="Título" className="sm:col-span-2">
            <input
              value={campos.title}
              onChange={(e) => setCampos({ ...campos, title: e.target.value })}
              className={ENTRADA}
            />
          </Campo>
          <Campo rotulo="Risco">
            <select
              value={campos.risk_tier}
              onChange={(e) => setCampos({ ...campos, risk_tier: e.target.value })}
              className={ENTRADA}
            >
              {RISCOS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Tipo de mudança">
            <select
              value={campos.change_type}
              onChange={(e) => setCampos({ ...campos, change_type: e.target.value })}
              className={ENTRADA}
            >
              {TIPOS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Impacto (1–5)">
            <input
              type="number"
              min={1}
              max={5}
              value={campos.impact}
              onChange={(e) => setCampos({ ...campos, impact: Number(e.target.value) })}
              className={ENTRADA}
            />
          </Campo>
          <Campo rotulo="Complexidade (1–5)">
            <input
              type="number"
              min={1}
              max={5}
              value={campos.complexity}
              onChange={(e) => setCampos({ ...campos, complexity: Number(e.target.value) })}
              className={ENTRADA}
            />
          </Campo>
          <div className="sm:col-span-2">
            <Botao type="submit" variante="primario" disabled={ocupado !== null}>
              Salvar alterações
            </Botao>
            <p className="mt-2 text-[12px] text-ink-3">
              A edição fica registrada no histórico: mudar a prioridade ou o risco é uma decisão, e
              decisão sem registro não é rastreável.
            </p>
          </div>
        </form>
      )}
    </Secao>
  );
}

// --------------------------------------------------------------------------- //
// Página
// --------------------------------------------------------------------------- //

export default function TarefaDetalhe({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const taskId = Number(id);
  const [aba, setAba] = useState<Aba>("planejamento");

  const detalhe = useLista(["task", id], () => pase.task(taskId));

  useEffect(() => {
    if (detalhe.data?.task.status === "em_homologacao") setAba("homologacao");
    else if (detalhe.data?.task.status === "aguardando_plano") setAba("planejamento");
    else if ((detalhe.data?.runs.length ?? 0) > 0) setAba("execucoes");
  }, [detalhe.data?.task.status, detalhe.data?.runs.length]);

  if (detalhe.isLoading) {
    return (
      <PanelShell titulo="Carregando…" sobretitulo="Tarefa">
        <Carregando texto="Buscando a tarefa" />
      </PanelShell>
    );
  }

  if (!detalhe.data) {
    return (
      <PanelShell titulo="Tarefa não encontrada" sobretitulo="Tarefa">
        <Link href="/tarefas" className="text-[13.5px] underline underline-offset-4">
          voltar para a lista
        </Link>
      </PanelShell>
    );
  }

  const { task, description, branch_name, history, planning, runs, orcamento, redo_feedback } =
    detalhe.data;
  const ultimaRevisao = [...runs].reverse().find((r) => r.review)?.review ?? null;

  return (
    <PanelShell
      sobretitulo={
        <span className="flex items-center gap-3">
          <Link href="/tarefas" className="hover:text-ink">
            ← Tarefas
          </Link>
          <span>#{task.id}</span>
        </span>
      }
      titulo={task.title}
      descricao={description}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Estado status={task.status} />
        <Desfecho outcome={task.final_outcome} />
        <Tag>{task.module}</Tag>
        <Tag>{task.change_type}</Tag>
        {task.output_type === "zona_dinamica" && <Tag tom="zone">zona dinâmica</Tag>}
        <Risco tier={task.risk_tier} />
        {task.uncertainty && <Tag tom="info">incerteza</Tag>}
        <Alerta alert={task.alert} />
        {task.stage && (
          <Link href="/entrega">
            <Tag tom={ESTAGIO[task.stage].tom} ponto>
              {ESTAGIO[task.stage].rotulo}
            </Tag>
          </Link>
        )}
        {task.stage === "develop" && task.tested_ok && <Tag tom="ok">aprovada nos testes</Tag>}
        {task.plan_approval_required && <Tag tom="info">plano exige aprovação</Tag>}
        {task.archived_at && (
          <Tag tom="neutro" title={detalhe.data.archive_note ?? undefined}>
            arquivada
          </Tag>
        )}
        {branch_name && <Tag title="Branch do Executor">{branch_name}</Tag>}
      </div>

      {task.parent_task_id && (
        <div className="mt-5 rounded border border-info/25 bg-info/[0.06] px-4 py-3 text-[13.5px]">
          <p className="text-ink">
            Esta tarefa <strong className="font-medium">refaz a </strong>
            <Link href={`/tarefas/${task.parent_task_id}`} className="font-medium underline underline-offset-4">
              #{task.parent_task_id}
            </Link>
            .
          </p>
          {redo_feedback && <p className="mt-1 text-ink-2">“{redo_feedback}”</p>}
        </div>
      )}

      <div className="mt-8">
        <Trilho status={task.status} history={history} />
      </div>

      <div className="mt-8">
        <Controles key={`${task.id}-${task.updated_at}`} task={task} orcamento={orcamento} />
      </div>

      <div className="mt-10">
        <Abas
          atual={aba}
          onTrocar={setAba}
          abas={[
            { id: "planejamento", rotulo: "Planejamento" },
            { id: "execucoes", rotulo: "Execuções", contagem: runs.length },
            {
              id: "homologacao",
              rotulo: "Homologação",
              desabilitada: task.status !== "em_homologacao",
              sinal: true,
              contagem: task.status === "em_homologacao" ? 1 : undefined,
            },
          ]}
        />

        <div className="mt-6">
          {aba === "planejamento" && (
            <Planejamento
              taskId={task.id}
              status={task.status}
              planning={planning}
              history={history}
            />
          )}
          {aba === "execucoes" && <Execucoes runs={runs} />}
          {aba === "homologacao" && (
            <Homologacao
              taskId={task.id}
              riscoAlto={task.risk_tier === "alto"}
              parecer={ultimaRevisao}
            />
          )}
        </div>
      </div>
    </PanelShell>
  );
}

// --------------------------------------------------------------------------- //
// Planejamento
// --------------------------------------------------------------------------- //

function Planejamento({
  taskId,
  status,
  planning,
  history,
}: {
  taskId: number;
  status: string;
  planning: Plano | null;
  history: Transicao[];
}) {
  return (
    <div className="space-y-6">
      {status === "aguardando_plano" && planning && (
        <DecisaoDoPlano taskId={taskId} planning={planning} />
      )}
      {planning ? (
        <>
          <Secao
            titulo="Critérios de aceite"
            acoes={<span className="font-mono text-[11.5px] text-ink-3">definidos antes do código</span>}
            semRecuo
          >
            {planning.acceptance_criteria.length === 0 ? (
              <p className="p-4 text-[13px] text-ink-3">
                Este plano não tem critérios de aceite: a revisão independente não teria contra o
                que conferir, e por isso o Executor recusa executá-lo. Replaneje, ou edite o plano
                acrescentando critérios.
              </p>
            ) : (
              <ol className="divide-y divide-line">
                {planning.acceptance_criteria.map((c) => (
                  <li key={c.id} className="grid grid-cols-[2.5rem_1fr] gap-x-3 px-4 py-3">
                    <span className="pt-px font-mono text-[12px] text-ink-3">{c.id}</span>
                    <div>
                      <p className="text-[14px] text-ink">{c.criterio}</p>
                      {c.como_verificar && (
                        <p className="mt-1 text-[12.5px] text-ink-3">
                          <span className="font-mono">verificar:</span> {c.como_verificar}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Secao>

          <Secao
            titulo="Documento de planejamento"
            acoes={
              <div className="flex flex-wrap items-center gap-1.5">
                <Tag title="O P4 erra por ordem de grandeza: é artefato de planejamento, não teto">
                  ~{milhar(planning.tokens_estimated)} tokens
                </Tag>
                {planning.minutes_estimated != null && (
                  <Tag title="Estimativa do planejamento: geração, verificação e revisão">
                    ~{planning.minutes_estimated} min
                  </Tag>
                )}
                {planning.technical_risk && (
                  <Tag tom={TOM_DO_RISCO[planning.technical_risk]} ponto>
                    risco técnico {planning.technical_risk === "medio" ? "médio" : planning.technical_risk}
                  </Tag>
                )}
              </div>
            }
          >
            {planning.technical_risk_reason && (
              <p className="mb-5 text-[13px] text-ink-2">
                <span className="font-mono text-ink-3">risco:</span> {planning.technical_risk_reason}
              </p>
            )}
            <p className="eyebrow">Mapeamento de impacto</p>
            <ul className="mt-2 space-y-1">
              {planning.affected_files.map((f) => {
                const acao = planning.file_actions?.[f] ?? "modificar";
                return (
                  <li key={f} className="flex items-baseline gap-2">
                    <span
                      className={`w-[4.5rem] shrink-0 font-mono text-[11px] ${COR_DA_ACAO[acao]}`}
                    >
                      {acao}
                    </span>
                    <span className="font-mono text-[12.5px] text-ink-2">{f}</span>
                  </li>
                );
              })}
            </ul>
            <p className="eyebrow mt-5">Roadmap</p>
            <p className="mt-2 whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">
              {planning.roadmap}
            </p>
          </Secao>
        </>
      ) : (
        <Vazio titulo="Ainda sem plano">Esta tarefa ainda não foi planejada.</Vazio>
      )}

      <Secao titulo="Histórico de estados" semRecuo>
        <ol className="divide-y divide-line">
          {[...history].reverse().map((h, i) => (
            <li key={i} className="grid gap-x-4 gap-y-1 px-4 py-2.5 sm:grid-cols-[9rem_11rem_1fr]">
              <span className="font-mono text-[12px] text-ink-3">{formatarData(h.at)}</span>
              <span className="text-[13px] text-ink-2">
                {h.from && h.from !== h.to ? `${rotuloDoEstado(h.from)} → ` : ""}
                <strong className="font-medium text-ink">{rotuloDoEstado(h.to)}</strong>
              </span>
              <span className="text-[13px] text-ink-3">{h.note}</span>
            </li>
          ))}
        </ol>
      </Secao>
    </div>
  );
}

/**
 * O gate entre planejar e gastar uma execução.
 *
 * O plano é o ponto mais barato para discordar: nenhum token de código foi gasto
 * ainda. Aqui a pessoa pode aprovar, devolver dizendo o que está errado (o
 * planejamento recomeça lendo o motivo) ou editar à mão o que ela já sabe.
 */
function DecisaoDoPlano({ taskId, planning }: { taskId: number; planning: Plano }) {
  const client = useQueryClient();
  const avisar = useAviso();
  const perguntar = usePergunta();
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [criterios, setCriterios] = useState(planning.acceptance_criteria);
  const [arquivos, setArquivos] = useState(planning.affected_files.join("\n"));
  const [roadmap, setRoadmap] = useState(planning.roadmap);

  async function agir(nome: string, acao: () => Promise<unknown>, mensagem: string) {
    setOcupado(nome);
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

  async function devolver() {
    const feedback = await perguntar({
      titulo: "Devolver o plano",
      efeito:
        "O planejamento recomeça lendo o plano atual e o que você escrever aqui. Nenhum código foi escrito ainda: devolver não custa execução.",
      rotulo: "O que está errado no plano",
      dica: "Ex.: o backend já tem o endpoint, só falta a tela. Seja concreto.",
      confirmar: "Devolver ao planejamento",
    });
    if (feedback) {
      void agir(
        "devolver",
        () => pase.revisePlan(taskId, feedback),
        "Plano devolvido. O planejamento recomeçou.",
      );
    }
  }

  return (
    <Secao
      titulo="Decisão sobre o plano"
      acoes={
        <Tag tom="signal" ponto>
          esperando você
        </Tag>
      }
      className="border-signal/40"
    >
      <p className="text-[13.5px] text-ink-2">
        Nenhum código foi escrito. Aprovar libera o Executor a seguir{" "}
        <strong className="font-medium text-ink">exatamente este plano</strong>: os critérios de
        aceite abaixo são o que a revisão independente vai cobrar depois.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <Botao
          variante="primario"
          ocupado={ocupado === "aprovar"}
          disabled={ocupado !== null || editando}
          onClick={() =>
            agir("aprovar", () => pase.approvePlan(taskId), "Plano aprovado. A execução começou.")
          }
        >
          Aprovar plano
        </Botao>
        <Botao disabled={ocupado !== null || editando} onClick={() => void devolver()}>
          Devolver com feedback
        </Botao>
        <Botao onClick={() => setEditando((v) => !v)} disabled={ocupado !== null}>
          {editando ? "Fechar edição" : "Editar o plano"}
        </Botao>
      </div>

      {editando && (
        <div className="mt-5 space-y-5 border-t border-line pt-5">
          <div>
            <p className="eyebrow mb-2">Critérios de aceite</p>
            <ul className="space-y-3">
              {criterios.map((c, i) => (
                <li key={c.id} className="grid gap-2 sm:grid-cols-[2.5rem_1fr_auto]">
                  <span className="pt-2 font-mono text-[12px] text-ink-3">{c.id}</span>
                  <div className="space-y-2">
                    <textarea
                      aria-label={`Critério ${c.id}`}
                      rows={2}
                      value={c.criterio}
                      onChange={(e) =>
                        setCriterios(
                          criterios.map((x, j) => (j === i ? { ...x, criterio: e.target.value } : x)),
                        )
                      }
                      className={AREA_TEXTO}
                    />
                    <input
                      aria-label={`Como verificar ${c.id}`}
                      value={c.como_verificar}
                      placeholder="como verificar"
                      onChange={(e) =>
                        setCriterios(
                          criterios.map((x, j) =>
                            j === i ? { ...x, como_verificar: e.target.value } : x,
                          ),
                        )
                      }
                      className={ENTRADA}
                    />
                  </div>
                  <Botao
                    tamanho="sm"
                    variante="fantasma"
                    onClick={() => setCriterios(criterios.filter((_, j) => j !== i))}
                  >
                    Remover
                  </Botao>
                </li>
              ))}
            </ul>
            <Botao
              className="mt-3"
              tamanho="sm"
              onClick={() =>
                setCriterios([
                  ...criterios,
                  { id: `C${criterios.length + 1}`, criterio: "", como_verificar: "" },
                ])
              }
            >
              Acrescentar critério
            </Botao>
          </div>

          <Campo rotulo="Arquivos previstos" dica="Um por linha.">
            <textarea
              rows={4}
              value={arquivos}
              onChange={(e) => setArquivos(e.target.value)}
              className={`${AREA_TEXTO} font-mono text-[12.5px]`}
            />
          </Campo>

          <Campo rotulo="Roadmap">
            <textarea
              rows={6}
              value={roadmap}
              onChange={(e) => setRoadmap(e.target.value)}
              className={AREA_TEXTO}
            />
          </Campo>

          <Botao
            variante="primario"
            ocupado={ocupado === "salvar"}
            disabled={ocupado !== null}
            onClick={() =>
              agir(
                "salvar",
                () =>
                  pase.editPlan(taskId, {
                    acceptance_criteria: criterios.filter((c) => c.criterio.trim()),
                    affected_files: arquivos.split("\n"),
                    roadmap,
                  }),
                "Plano editado. Revise e aprove.",
              ).then(() => setEditando(false))
            }
          >
            Salvar edição
          </Botao>
        </div>
      )}
    </Secao>
  );
}

// --------------------------------------------------------------------------- //
// Execuções
// --------------------------------------------------------------------------- //

function Execucoes({ runs }: { runs: RunRow[] }) {
  const [selecionada, setSelecionada] = useState<number | null>(runs.at(-1)?.id ?? null);

  if (runs.length === 0) {
    return <Vazio titulo="Nenhuma execução ainda">O Executor ainda não rodou para esta tarefa.</Vazio>;
  }

  const run = runs.find((r) => r.id === selecionada);

  return (
    <div className="space-y-6">
      <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
        {runs.map((r) => {
          const s = RUN[r.status] ?? { rotulo: r.status, tom: "neutro" as const };
          const ativa = selecionada === r.id;
          return (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => setSelecionada(r.id)}
                aria-pressed={ativa}
                className={`block w-full px-4 py-3 text-left transition-colors ${
                  ativa ? "bg-sunken" : "hover:bg-sunken/50"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12.5px] text-ink-3">tentativa {r.attempt}</span>
                  <Tag tom={s.tom} ponto>
                    {s.rotulo}
                  </Tag>
                  <Tag>{r.trigger}</Tag>
                  {r.review && (
                    <Tag tom={r.review.aprovado ? "ok" : "bad"} title={`Revisor: ${r.review.modelo}`}>
                      revisão {r.review.aprovado ? "aprovou" : "reprovou"}
                    </Tag>
                  )}
                  {r.deviation_files.length > 0 && (
                    <Tag tom="warn">{r.deviation_files.length} fora do planejado</Tag>
                  )}
                  <span className="tnum ml-auto font-mono text-[12px] text-ink-3">
                    {milhar(r.tokens_real)} tokens · {Math.round(r.duration_ms / 1000)}s ·{" "}
                    {formatarData(r.created_at)}
                  </span>
                </div>
                {r.failure_reason && <p className="mt-1.5 text-[13px] text-bad">{r.failure_reason}</p>}
                {r.deviation_files.length > 0 && (
                  <p className="mt-1.5 font-mono text-[12px] text-warn">{r.deviation_files.join(", ")}</p>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {run?.review && <ParecerDaRevisao parecer={run.review} />}
      {selecionada && <Artefatos runId={selecionada} />}
    </div>
  );
}

type TipoArtefato = "diff" | "logs" | "transcript";

function Artefatos({ runId }: { runId: number }) {
  const [tipo, setTipo] = useState<TipoArtefato>("diff");
  const [conteudo, setConteudo] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setConteudo(null);
    setErro(null);
    pase
      .artifact(runId, tipo)
      .then(setConteudo)
      .catch(() => setErro("Esta execução não produziu este artefato."));
  }, [runId, tipo]);

  return (
    <Secao
      titulo="Artefatos"
      acoes={
        <div className="flex gap-1">
          {(["diff", "logs", "transcript"] as const).map((t) => (
            <button
              key={t}
              type="button"
              aria-pressed={tipo === t}
              onClick={() => setTipo(t)}
              className={`h-6 rounded-sm px-2 font-mono text-[11.5px] ${
                tipo === t ? "bg-ink text-bg" : "text-ink-3 hover:text-ink"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      }
      semRecuo
    >
      <div className="max-h-[32rem] overflow-auto p-3">
        {erro && <p className="p-1 text-[13px] text-ink-3">{erro}</p>}
        {!erro && conteudo === null && <Carregando />}
        {conteudo !== null && tipo === "diff" && <Diff texto={conteudo} />}
        {conteudo !== null && tipo === "logs" && (
          <pre className="whitespace-pre-wrap font-mono text-[12px] text-ink-2">{conteudo}</pre>
        )}
        {conteudo !== null && tipo === "transcript" && <Transcript jsonl={conteudo} />}
      </div>
    </Secao>
  );
}

function Transcript({ jsonl }: { jsonl: string }) {
  const linhas = jsonl
    .split("\n")
    .filter(Boolean)
    .map((l) => {
      try {
        return JSON.parse(l) as Record<string, unknown>;
      } catch {
        return { role: "?", content: l };
      }
    });

  return (
    <div className="space-y-2">
      {linhas.map((linha, i) => (
        <div key={i} className="rounded border border-line">
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-sunken/60 px-3 py-1.5 font-mono text-[11px] text-ink-3">
            <span className="uppercase">{String(linha.role)}</span>
            {linha.fase ? <Tag tom="info">{String(linha.fase)}</Tag> : null}
            {linha.evento ? <Tag>{String(linha.evento)}</Tag> : null}
            {linha.modelo ? <span>{String(linha.modelo)}</span> : null}
            {linha.tokens_in ? (
              <span className="tnum">
                {String(linha.tokens_in)} in / {String(linha.tokens_out)} out
              </span>
            ) : null}
            {linha.trace_id ? <span className="ml-auto">{String(linha.trace_id)}</span> : null}
          </div>
          <pre className="max-h-52 overflow-auto whitespace-pre-wrap p-3 font-mono text-[12px] text-ink-2">
            {String(linha.content).slice(0, 4000)}
          </pre>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Revisão independente
// --------------------------------------------------------------------------- //

function Citado({ rotulo, c }: { rotulo: string; c: { arquivo: string; trecho: string } }) {
  return (
    <div>
      <p className="font-mono text-[11.5px] text-ink-3">
        {rotulo} · {c.arquivo}
      </p>
      <BlocoDeCodigo className="mt-1 max-h-32">{c.trecho}</BlocoDeCodigo>
    </div>
  );
}

function Criterio({ c }: { c: CriterioRevisado }) {
  const [aberto, setAberto] = useState(!c.atendido);
  return (
    <li className="px-4 py-3">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        className="grid w-full grid-cols-[1.25rem_2.5rem_1fr] items-start gap-x-2 text-left"
      >
        <span
          className={`mt-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] text-white ${
            c.atendido ? "bg-ok" : "bg-bad"
          }`}
        >
          {c.atendido ? "✓" : "✕"}
        </span>
        <span className="font-mono text-[12px] text-ink-3">{c.id}</span>
        <span className="text-[14px] text-ink">{c.criterio}</span>
      </button>

      {aberto && (
        <div className="mt-3 space-y-3 pl-[3.75rem]">
          {c.anulado_por && (
            <p className="rounded border border-bad/25 bg-bad/[0.06] px-3 py-2 text-[12.5px] text-ink-2">
              <strong className="font-medium text-bad">Anulado pelo código:</strong> {c.anulado_por}
            </p>
          )}
          {c.explicacao && <p className="text-[13px] text-ink-2">{c.explicacao}</p>}
          {c.evidencia && <Citado rotulo="evidência" c={c.evidencia} />}
          {c.teste && <Citado rotulo="teste que prova" c={c.teste} />}
          {c.verificacao_manual && (
            <p className="rounded border border-signal/30 bg-signal/[0.07] px-3 py-2 text-[13px] text-ink">
              <strong className="font-medium text-signal">Confira você:</strong> {c.verificacao_manual}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function ParecerDaRevisao({ parecer }: { parecer: Parecer }) {
  const atendidos = parecer.criterios.filter((c) => c.atendido).length;
  return (
    <Secao
      titulo="Revisão independente"
      acoes={
        <>
          <Tag tom={parecer.aprovado ? "ok" : "bad"} ponto>
            {atendidos}/{parecer.criterios.length} critérios
          </Tag>
          {parecer.mesmo_modelo && (
            <Tag
              tom="warn"
              title="LLM_MODEL_REVIEW não está configurado com outro modelo: a revisão é outra chamada, mas do mesmo modelo que escreveu o código."
            >
              revisor = autor
            </Tag>
          )}
          <span
            className="font-mono text-[11.5px] text-ink-3"
            title={parecer.modelo_do_codigo ? `Código escrito por ${parecer.modelo_do_codigo}` : undefined}
          >
            revisado por {parecer.modelo}
          </span>
        </>
      }
      semRecuo
    >
      {parecer.resumo && (
        <p className="border-b border-line px-4 py-3 text-[13.5px] leading-relaxed text-ink-2">
          {parecer.resumo}
        </p>
      )}
      <ul className="divide-y divide-line">
        {parecer.criterios.map((c) => (
          <Criterio key={c.id} c={c} />
        ))}
      </ul>
      {parecer.colaterais.length > 0 && (
        <div className="border-t border-line px-4 py-3">
          <p className="eyebrow text-bad">Mudanças colaterais</p>
          <ul className="mt-2 space-y-1 text-[13px] text-ink-2">
            {parecer.colaterais.map((col, i) => (
              <li key={i}>
                <code className="text-ink">{col.arquivo}</code> - {col.motivo}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(parecer.avisos?.length ?? 0) > 0 && (
        <div className="border-t border-line px-4 py-3">
          <p className="eyebrow text-warn">Avisos do revisor</p>
          <p className="mt-1 text-[12.5px] text-ink-3">
            Mudanças fora do pedido que não alteram comportamento. Não reprovaram a entrega - estão
            aqui para você decidir se aceita.
          </p>
          <ul className="mt-2 space-y-2 text-[13px] text-ink-2">
            {parecer.avisos!.map((aviso, i) => (
              <li key={i}>
                <code className="text-ink">{aviso.arquivo}</code> - {aviso.motivo}
                {aviso.trecho && <BlocoDeCodigo className="mt-1 max-h-24">{aviso.trecho}</BlocoDeCodigo>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Secao>
  );
}

// --------------------------------------------------------------------------- //
// Homologação
// --------------------------------------------------------------------------- //

function Homologacao({
  taskId,
  riscoAlto,
  parecer,
}: {
  taskId: number;
  riscoAlto: boolean;
  parecer: Parecer | null;
}) {
  const client = useQueryClient();
  const avisar = useAviso();
  const [comentario, setComentario] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);

  const manuais = (parecer?.criterios ?? []).filter((c) => c.verificacao_manual);

  async function decidir(decision: "aprovar" | "ajustar" | "recusar") {
    setOcupado(decision);
    try {
      await pase.homologate(taskId, decision, comentario || null);
      avisar(
        decision === "aprovar"
          ? "Aprovado e integrado na develop. Chega à principal com a próxima release."
          : decision === "ajustar"
            ? "Devolvido ao Executor com o seu comentário."
            : "Recusado e registrado no Histórico de Descartes.",
      );
      setComentario("");
      await client.invalidateQueries();
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div className="space-y-6">
      {parecer && <ParecerDaRevisao parecer={parecer} />}

      {manuais.length > 0 && (
        <Secao titulo="Antes de aprovar, confira na tela">
          <p className="mb-3 text-[13px] text-ink-3">
            A máquina não consegue verificar isto. É o que a revisão independente deixou para você.
          </p>
          <ol className="list-decimal space-y-1.5 pl-5 text-[13.5px] text-ink">
            {manuais.map((c) => (
              <li key={c.id}>{c.verificacao_manual}</li>
            ))}
          </ol>
        </Secao>
      )}

      <Secao titulo="Decisão">
        <p className="text-[13.5px] text-ink-2">
          Lint, tipos, testes, build e a revisão independente já passaram - você revisa o que a
          máquina já verificou. Aprovar integra a branch da tarefa na{" "}
          <code className="text-ink">develop</code>; a branch principal só recebe código por uma
          release, com PR e aprovação humana própria.{" "}
          <strong className="font-medium text-ink">Ajustar</strong> devolve ao Executor com o seu
          comentário.
        </p>

        {riscoAlto && (
          <p className="mt-3 rounded border border-bad/30 bg-bad/[0.06] px-3 py-2 text-[13px] text-ink">
            Risco alto: a justificativa por escrito é obrigatória, inclusive para aprovar.
          </p>
        )}

        <Campo
          rotulo={riscoAlto ? "Justificativa (obrigatória)" : "Comentário"}
          dica="Obrigatório para ajustar e recusar. Para ajustar, diga o que viu na tela."
          className="mt-4"
        >
          <textarea
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            rows={3}
            className={AREA_TEXTO}
          />
        </Campo>

        <div className="mt-4 flex flex-wrap gap-2">
          <Botao
            variante="primario"
            ocupado={ocupado === "aprovar"}
            disabled={ocupado !== null || (riscoAlto && !comentario.trim())}
            onClick={() => decidir("aprovar")}
          >
            Aprovar e integrar
          </Botao>
          <Botao
            ocupado={ocupado === "ajustar"}
            disabled={ocupado !== null || !comentario.trim()}
            onClick={() => decidir("ajustar")}
          >
            Ajustar
          </Botao>
          <Botao
            variante="perigo"
            ocupado={ocupado === "recusar"}
            disabled={ocupado !== null || !comentario.trim()}
            onClick={() => decidir("recusar")}
          >
            Recusar
          </Botao>
        </div>
      </Secao>
    </div>
  );
}
