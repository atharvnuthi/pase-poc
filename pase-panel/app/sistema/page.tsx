"use client";

import { useEffect, useState } from "react";

import PanelShell from "@/components/PanelShell";
import { BlocoDeCodigo, Botao, Carregando, Medida, Secao, Tag } from "@/components/ui";
import { formatarData, milhar, pase, type MemoriaTipo, type Verbete } from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * O motor, e o vocabulário dele.
 *
 * O painel mostrava tarefas e nada sobre o próprio sistema. Faltavam duas
 * coisas: saber como o motor está (memória, prompts, custo, fila) e saber o que
 * as etiquetas significam. A segunda é a mais importante - uma decisão tomada
 * sem entender o selo `risco alto` é uma decisão tomada no escuro, que é
 * exatamente o que o gate humano existe para evitar.
 *
 * O glossário vem do servidor, não do front: é lá que os valores nascem, e um
 * texto escrito deste lado da API vira ficção no dia em que alguém acrescenta um
 * estado.
 */

type Job = "auditoria" | "reavaliacao";

const JOBS: { job: Job; botao: string; explica: string }[] = [
  {
    job: "auditoria",
    botao: "Rodar auditoria do código",
    explica:
      "Lê o código do FinTrack atrás de um ponto de refatoração ou inconsistência. O achado entra no funil como proposta de engenharia.",
  },
  {
    job: "reavaliacao",
    botao: "Reavaliar descartes",
    explica:
      "Relê os descartes por incoerência contra o contexto de hoje. O que não se sustenta mais volta ao funil.",
  },
];

/** O que a última rodada produziu, em uma linha. */
function resumoDoJob(job: Job, resultado: Record<string, unknown>): string {
  if (job === "auditoria") {
    const n = Number(resultado.propostas_geradas ?? 0);
    return n > 0
      ? `${n} proposta gerada: #${String(resultado.proposta_id)} ${String(resultado.titulo ?? "")} (${String(resultado.desfecho ?? "")})`
      : "nenhuma proposta: nada relevante para propor agora";
  }
  const analisados = Number(resultado.analisados ?? 0);
  const reinseridas = Number(resultado.reinseridas ?? 0);
  return `${analisados} descarte(s) reavaliado(s), ${reinseridas} reinserido(s) no funil`;
}

/**
 * Os dois loops de manutenção, por acionamento humano (§4.3.5 e §4.4.6).
 *
 * Rodam em segundo plano no servidor e levam minutos. Enquanto um roda, a seção
 * pergunta o estado a cada poucos segundos - é o único lugar do painel com
 * polling, porque o job não publica evento de tarefa enquanto trabalha.
 */
function Manutencao() {
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState<Job | null>(null);
  const [rodandoAgora, setRodandoAgora] = useState(false);
  const jobs = useLista(["jobs"], () => pase.jobs(), { atualizarACada: rodandoAgora ? 3000 : undefined });

  const algumRodando = Object.values(jobs.data ?? {}).some((j) => j.rodando);
  useEffect(() => setRodandoAgora(algumRodando), [algumRodando]);

  async function disparar(job: Job) {
    setFalha(null);
    setEnviando(job);
    try {
      await pase.runJob(job);
      const atual = await jobs.refetch();
      // Um job rápido pode já ter terminado aqui; só pergunta de novo se não terminou.
      setRodandoAgora(Object.values(atual.data ?? {}).some((j) => j.rodando));
    } catch (erro) {
      setFalha(String(erro).replace(/^Error: \d+: /, ""));
    } finally {
      setEnviando(null);
    }
  }

  return (
    <Secao titulo="Manutenção">
      <div className="grid gap-6 lg:grid-cols-2">
        {JOBS.map(({ job, botao, explica }) => {
          const estado = jobs.data?.[job];
          return (
            <div key={job} className="space-y-3">
              <p className="text-[13px] text-ink-2">{explica}</p>
              <Botao
                variante="secundario"
                ocupado={enviando === job || estado?.rodando}
                onClick={() => void disparar(job)}
              >
                {estado?.rodando ? "Rodando…" : botao}
              </Botao>
              {estado?.rodando && estado.iniciado_em && (
                <p className="text-[12.5px] text-ink-3">
                  Em andamento desde {formatarData(estado.iniciado_em)}. Pode sair desta tela: o resultado
                  fica aqui.
                </p>
              )}
              {!estado?.rodando && estado?.erro && (
                <p className="text-[12.5px] text-bad">Falhou: {estado.erro}</p>
              )}
              {!estado?.rodando && estado?.resultado && (
                <p className="text-[12.5px] text-ink-2">
                  <Tag tom="ok">última rodada</Tag>{" "}
                  {resumoDoJob(job, estado.resultado)}
                  {estado.terminado_em ? ` · ${formatarData(estado.terminado_em)}` : ""}
                </p>
              )}
            </div>
          );
        })}
      </div>
      {falha && <p className="mt-4 text-[12.5px] text-bad">{falha}</p>}
      <p className="mt-5 text-[12.5px] text-ink-3">
        Toda proposta gerada aqui passa pelo mesmo funil e pelo mesmo gate humano que qualquer outra: o
        loop de manutenção sugere, quem decide é você.
      </p>
    </Secao>
  );
}

export default function Sistema() {
  const [promptAberto, setPromptAberto] = useState<{ id: string; texto: string } | null>(null);
  const saude = useLista(["system-health"], () => pase.systemHealth());
  const memoria = useLista(["system-memory"], () => pase.systemMemory());
  const custo = useLista(["system-cost"], () => pase.systemCost());
  const promptsDoSistema = useLista(["system-prompts"], () => pase.systemPrompts());
  const glossario = useLista(["glossary"], () => pase.glossary());

  useEffect(() => {
    if (!promptAberto) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setPromptAberto(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [promptAberto]);

  async function abrirPrompt(id: string) {
    try {
      setPromptAberto({ id, texto: await pase.promptSource(id) });
    } catch (erro) {
      setPromptAberto({ id, texto: `Não consegui ler: ${String(erro)}` });
    }
  }

  const s = saude.data as Record<string, number> | undefined;
  const c = custo.data as Record<string, unknown> | undefined;
  const guardrails = (saude.data?.guardrails ?? {}) as Record<string, number>;

  return (
    <PanelShell
      titulo="Sistema"
      descricao="Como o motor está agora, e o que cada etiqueta do painel significa."
    >
      <div className="space-y-8">
        <Secao titulo="Fila">
          {s ? (
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6">
              <Medida rotulo="candidatas" valor={s.candidatas} />
              <Medida rotulo="em andamento" valor={s.em_andamento} />
              <Medida rotulo="esperando você" valor={s.aguardando_humano} tom={s.aguardando_humano > 0 ? "signal" : undefined} />
              <Medida rotulo="suspensas" valor={s.suspensas} tom={s.suspensas > 0 ? "bad" : undefined} />
              <Medida rotulo="execuções" valor={s.runs} />
              <Medida rotulo="incidentes" valor={s.incidentes_abertos} tom={s.incidentes_abertos > 0 ? "bad" : undefined} />
            </div>
          ) : (
            <Carregando />
          )}
        </Secao>

        <div className="grid gap-6 lg:grid-cols-2">
          <Secao titulo="Memória vetorial" semRecuo>
            {memoria.data ? (
              <>
                <table className="w-full text-[13px]">
                  <thead className="eyebrow text-left">
                    <tr className="border-b border-line">
                      <th className="px-4 py-2 font-medium">tipo</th>
                      <th className="px-4 py-2 text-right font-medium">linhas</th>
                      <th className="px-4 py-2 text-right font-medium">com vetor</th>
                      <th className="px-4 py-2 text-right font-medium">sem vetor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memoria.data.tipos.map((t: MemoriaTipo) => (
                      <tr key={t.kind} className="border-b border-line last:border-0">
                        <td className="px-4 py-2 font-mono text-[12.5px]">{t.kind}</td>
                        <td className="tnum px-4 py-2 text-right font-mono">{t.total}</td>
                        <td className="tnum px-4 py-2 text-right font-mono text-ok">{t.com_embedding}</td>
                        <td
                          className={`tnum px-4 py-2 text-right font-mono ${t.sem_embedding > 0 ? "text-warn" : "text-ink-3"}`}
                        >
                          {t.sem_embedding}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="border-t border-line px-4 py-3 text-[12px] text-ink-3">
                  {memoria.data.modelo} · {memoria.data.dimensoes} dimensões · limiar{" "}
                  {memoria.data.limiar_de_similaridade}. Linha <strong className="font-medium">sem vetor</strong>{" "}
                  existe no banco mas é invisível para a busca - ela não barra duplicata nenhuma.
                </p>
              </>
            ) : (
              <div className="px-4">
                <Carregando />
              </div>
            )}
          </Secao>

          <Secao titulo="Modelos e custo">
            {c ? (
              <>
                <dl className="space-y-2 font-mono text-[12.5px]">
                  {[
                    ["funil", c.modelo_padrao],
                    ["exploratório", c.modelo_exploratorio],
                    ["código", c.modelo_de_codigo],
                    ["revisão", c.modelo_de_revisao],
                  ].map(([rotulo, modelo]) => (
                    <div key={String(rotulo)} className="flex gap-3">
                      <dt className="w-24 shrink-0 text-ink-3">{String(rotulo)}</dt>
                      <dd className="text-ink">{String(modelo ?? "-")}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-3 text-[12px] text-ink-3">
                  Quem escreve o código e quem o revisa são modelos diferentes de propósito: quem
                  escreve tende a aprovar o próprio ponto cego.
                </p>
                <div className="mt-5 grid grid-cols-3 gap-4 border-t border-line pt-5">
                  <Medida rotulo="chamadas" valor={milhar(Number(c.chamadas))} />
                  <Medida rotulo="tokens in" valor={milhar(Number(c.tokens_in))} />
                  <Medida rotulo="tokens out" valor={milhar(Number(c.tokens_out))} />
                </div>
              </>
            ) : (
              <Carregando />
            )}
          </Secao>
        </div>

        <Manutencao />

        <Secao titulo="Guardrails em vigor">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-5">
            {Object.entries(guardrails).map(([nome, valor]) => (
              <Medida key={nome} rotulo={nome.replace(/_/g, " ")} valor={milhar(Number(valor))} />
            ))}
          </div>
          <p className="mt-5 text-[12.5px] text-ink-3">
            São código que impede a ação, não recomendação ao modelo - é o que o modelo PASE chama de
            contenção da generatividade.
          </p>
        </Secao>

        <Secao titulo="Prompts versionados" semRecuo>
          {promptsDoSistema.data ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="eyebrow text-left">
                  <tr className="border-b border-line">
                    <th className="px-4 py-2 font-medium">id</th>
                    <th className="px-4 py-2 font-medium">papel</th>
                    <th className="px-4 py-2 font-medium">etapa</th>
                    <th className="px-4 py-2 text-right font-medium">temperatura</th>
                    <th className="px-4 py-2 text-right font-medium">linhas</th>
                  </tr>
                </thead>
                <tbody>
                  {promptsDoSistema.data.prompts.map((p: Record<string, unknown>) => (
                    <tr key={String(p.id)} className="border-b border-line last:border-0">
                      <td className="px-4 py-2">
                        <button
                          type="button"
                          onClick={() => void abrirPrompt(String(p.id))}
                          className="font-mono text-[12.5px] underline decoration-line-strong underline-offset-4 hover:text-signal"
                          title="Ver o texto que vai para o modelo"
                        >
                          {String(p.id)}
                        </button>
                      </td>
                      <td className="px-4 py-2">{String(p.papel)}</td>
                      <td className="px-4 py-2 text-ink-3">{String(p.etapa)}</td>
                      <td
                        className={`tnum px-4 py-2 text-right font-mono ${Number(p.temperatura) >= 0.9 ? "text-warn" : ""}`}
                      >
                        {String(p.temperatura)}
                      </td>
                      <td className="tnum px-4 py-2 text-right font-mono text-ink-3">{String(p.linhas)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="border-t border-line px-4 py-3 text-[12px] text-ink-3">
                Uma única chamada do sistema roda com temperatura alta: a Geração Exploratória. Todo o
                resto é decisão, e decisão pede previsibilidade.
              </p>
            </div>
          ) : (
            <div className="px-4">
              <Carregando />
            </div>
          )}
        </Secao>

        <section id="glossario" className="scroll-mt-6">
          <h2 className="font-display text-[30px] leading-tight">Glossário</h2>
          <p className="mb-6 mt-1 text-[13.5px] text-ink-2">
            O que cada etiqueta significa, quem a atribui e o que ela muda no comportamento do sistema.
          </p>

          {glossario.data ? (
            <div className="space-y-8">
              {Object.entries(glossario.data.grupos).map(([grupo, verbetes]) => (
                <div key={grupo}>
                  <h3 className="eyebrow mb-3">{grupo}</h3>
                  <ul className="grid gap-3 lg:grid-cols-2">
                    {(verbetes as Verbete[]).map((v) => (
                      <li key={v.termo} className="rounded border border-line bg-surface p-4">
                        <Tag>{v.termo.replace(/_/g, " ")}</Tag>
                        <p className="mt-2.5 text-[13.5px]">{v.significado}</p>
                        <p className="mt-2 text-[12.5px] text-ink-3">
                          <strong className="font-medium text-ink-2">quem atribui:</strong> {v.quem_atribui}
                        </p>
                        <p className="mt-1 text-[12.5px] text-ink-3">
                          <strong className="font-medium text-ink-2">efeito:</strong> {v.efeito}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <Carregando />
          )}
        </section>
      </div>

      {promptAberto && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="prompt-titulo"
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-[2px]"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setPromptAberto(null);
          }}
        >
          {/*
            O texto cru, exatamente como vai para o modelo. Os `{{...}}` aparecem
            sem preencher de propósito: quem revisa precisa ver onde cada insumo
            entra, não o resultado de uma chamada específica.
          */}
          <section className="flex max-h-[88vh] w-full max-w-4xl flex-col rounded border border-line-strong bg-surface shadow-[0_24px_60px_-20px_rgb(0_0_0/0.45)]">
            <header className="flex items-center gap-3 border-b border-line px-5 py-3">
              <div>
                <p className="eyebrow">Prompt em vigor</p>
                <h2 id="prompt-titulo" className="font-mono text-[14px] font-medium">
                  {promptAberto.id}.md
                </h2>
              </div>
              <Botao className="ml-auto" tamanho="sm" onClick={() => setPromptAberto(null)}>
                Fechar
              </Botao>
            </header>
            <BlocoDeCodigo className="m-0 whitespace-pre-wrap rounded-none border-0 p-5">
              {promptAberto.texto}
            </BlocoDeCodigo>
          </section>
        </div>
      )}
    </PanelShell>
  );
}
