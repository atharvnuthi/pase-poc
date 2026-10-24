"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Risco } from "@/components/estados";
import { useAviso, usePergunta } from "@/components/interacoes";
import PanelShell from "@/components/PanelShell";
import {
  AREA_TEXTO,
  BlocoDeCodigo,
  Botao,
  Carregando,
  Medida,
  Ponto,
  Secao,
  Tag,
  Vazio,
  type Tom,
} from "@/components/ui";
import {
  haQuantoTempo,
  pase,
  type Entrega,
  type EntregaTarefa,
  type EventoDePipeline,
  type ReleaseRow,
} from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * Tela Entrega - do código aprovado à produção.
 *
 * Segue o guia de fluxo de ramos:
 *
 *   feature/hotfix ──▶ develop (testes) ──▶ release/x.x.x ──PR──▶ principal ──▶ tag
 *
 * Aprovar na Homologação leva a tarefa à develop, e só. Daqui, uma pessoa a aprova
 * funcionalmente, escolhe em que release ela vai, valida a release inteira, lê o
 * Pull Request e publica. Cada passo que o guia reserva a uma pessoa pede o texto de
 * quem decidiu.
 */

const STATUS_DA_RELEASE: Record<ReleaseRow["status"], { rotulo: string; tom: Tom }> = {
  aberta: { rotulo: "aberta", tom: "info" },
  validando: { rotulo: "validando", tom: "warn" },
  validada: { rotulo: "validada", tom: "ok" },
  pr_aberto: { rotulo: "PR aberto", tom: "signal" },
  publicada: { rotulo: "publicada", tom: "ok" },
  cancelada: { rotulo: "cancelada", tom: "neutro" },
};

const TOM_DO_EVENTO: Record<string, Tom> = {
  integracao: "info",
  ci: "neutro",
  reversao: "warn",
  release: "zone",
  publicacao: "ok",
  aprovacao: "ok",
};

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

export default function EntregaPage() {
  const entrega = useLista(["delivery"], () => pase.delivery());
  const d = entrega.data;

  return (
    <PanelShell
      titulo="Entrega"
      descricao="Do código aprovado à produção. A Homologação leva a tarefa à develop; daqui, só uma release chega à principal, por um Pull Request que você libera."
    >
      {entrega.isLoading && <Carregando />}
      {entrega.error && (
        <p className="rounded border border-bad/30 bg-bad/[0.06] p-4 text-[13.5px] text-bad">
          Não consegui ler o fluxo: {String(entrega.error)}
        </p>
      )}

      {d && (
        <div className="space-y-10">
          <Fluxo d={d} />
          <Develop d={d} />
          <Releases d={d} />
          <Rastro eventos={d.eventos} />
          <Regras d={d} />
        </div>
      )}
    </PanelShell>
  );
}

// --------------------------------------------------------------------------- //
// Visão do fluxo
// --------------------------------------------------------------------------- //

function Fluxo({ d }: { d: Entrega }) {
  const abertas = d.releases.filter((r) => !["publicada", "cancelada"].includes(r.status));
  const noPr = abertas.filter((r) => r.status === "pr_aberto").length;

  return (
    <ol className="grid overflow-hidden rounded border border-line bg-surface md:grid-cols-4">
      <Etapa
        n="01"
        titulo="Tarefa"
        valor="feature · hotfix"
        detalhe="nasce da principal; vai à develop por merge direto"
      />
      <Etapa
        n="02"
        titulo="Develop"
        valor={String(d.develop.tarefas.length)}
        detalhe={
          d.develop.ultimo_ci
            ? `último CI ${d.develop.ultimo_ci.ok ? "passou" : "reprovou"} · ${haQuantoTempo(d.develop.ultimo_ci.at)}`
            : "ambiente de testes"
        }
        tom={d.develop.ultimo_ci && !d.develop.ultimo_ci.ok ? "bad" : undefined}
      />
      <Etapa
        n="03"
        titulo="Releases abertas"
        valor={String(abertas.length)}
        detalhe={noPr > 0 ? `${noPr} esperando a sua aprovação` : "composição e validação final"}
        tom={noPr > 0 ? "signal" : undefined}
      />
      <Etapa
        n="04"
        titulo={`Produção · ${d.principal}`}
        valor={d.versao_atual ?? "-"}
        detalhe={d.versao_atual ? "última tag publicada" : "nenhuma versão publicada"}
      />
    </ol>
  );
}

function Etapa({
  n,
  titulo,
  valor,
  detalhe,
  tom,
}: {
  n: string;
  titulo: string;
  valor: string;
  detalhe: string;
  tom?: Tom;
}) {
  return (
    <li className="border-b border-line px-4 pb-4 pt-3 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0">
      <p className="flex items-center gap-2">
        <span className="font-mono text-[11px] text-ink-3">{n}</span>
        <span className="eyebrow">{titulo}</span>
      </p>
      <p
        className={`mt-3 font-display text-[36px] leading-none ${tom === "signal" ? "text-signal" : tom === "bad" ? "text-bad" : "text-ink"}`}
      >
        {valor}
      </p>
      <p className="mt-2 text-[12px] text-ink-3">{detalhe}</p>
    </li>
  );
}

// --------------------------------------------------------------------------- //
// Develop
// --------------------------------------------------------------------------- //

function Develop({ d }: { d: Entrega }) {
  const { ocupado, agir } = useAcao();
  const perguntar = usePergunta();
  const abertas = d.releases.filter((r) => ["aberta", "validada"].includes(r.status));

  async function aprovar(t: EntregaTarefa) {
    const nota = await perguntar({
      titulo: `Aprovar #${t.id} nos testes`,
      efeito:
        "É a aprovação funcional: você usou a funcionalidade na develop e ela faz o que foi pedido. Só tarefa aprovada aqui pode entrar numa release.",
      rotulo: "O que você conferiu",
      dica: "Ex.: abri Transações, exportei o CSV e o arquivo trouxe só as minhas linhas.",
      confirmar: "Aprovar nos testes",
    });
    if (nota) {
      void agir(`testar-${t.id}`, () => pase.testApprove(t.id, nota), `#${t.id} aprovada nos testes.`);
    }
  }

  return (
    <section>
      <h2 className="eyebrow mb-3">Develop · ambiente de testes</h2>
      {d.develop.tarefas.length === 0 ? (
        <Vazio titulo="Nada na develop">
          Tarefas aprovadas na Homologação aparecem aqui, esperando a aprovação nos testes.
        </Vazio>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
          {d.develop.tarefas.map((t) => (
            <li key={t.id} className="px-4 py-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="tnum font-mono text-[12.5px] text-ink-3">#{t.id}</span>
                <Link href={`/tarefas/${t.id}`} className="font-medium hover:underline">
                  {t.title}
                </Link>
                <Tag>{t.branch}</Tag>
                <Risco tier={t.risk_tier} />
                {t.tested_ok ? (
                  <Tag tom="ok" ponto>
                    aprovada nos testes
                  </Tag>
                ) : (
                  <Tag tom="signal" ponto>
                    aguarda teste
                  </Tag>
                )}
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  {!t.tested_ok && (
                    <Botao
                      tamanho="sm"
                      variante="primario"
                      ocupado={ocupado === `testar-${t.id}`}
                      disabled={ocupado !== null}
                      onClick={() => void aprovar(t)}
                    >
                      Aprovar nos testes
                    </Botao>
                  )}
                  {t.tested_ok &&
                    abertas.map((r) => (
                      <Botao
                        key={r.id}
                        tamanho="sm"
                        ocupado={ocupado === `incluir-${t.id}-${r.id}`}
                        disabled={ocupado !== null}
                        onClick={() =>
                          agir(
                            `incluir-${t.id}-${r.id}`,
                            async () => {
                              const res = await pase.includeInRelease(r.id, t.id);
                              if (!res.incluida) throw new Error(res.detail ?? "conflito");
                            },
                            `#${t.id} entrou na release ${r.version}.`,
                          )
                        }
                      >
                        Incluir na {r.version}
                      </Botao>
                    ))}
                </div>
              </div>
              {t.tested_note && <p className="mt-1.5 text-[13px] text-ink-2">“{t.tested_note}”</p>}
              {t.tested_ok && abertas.length === 0 && (
                <p className="mt-1.5 text-[12.5px] text-ink-3">
                  Abra uma release abaixo para incluí-la.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Releases
// --------------------------------------------------------------------------- //

function Releases({ d }: { d: Entrega }) {
  const { ocupado, agir } = useAcao();
  const perguntar = usePergunta();

  async function nova() {
    const versao = await perguntar({
      titulo: "Abrir release",
      efeito: (
        <>
          Cria <code>release/x.x.x</code> a partir da <strong className="font-medium text-ink">{d.principal}</strong>
          , nunca da develop. A versão segue o versionamento semântico: MAJOR para quebra,
          MINOR para funcionalidade, PATCH para correção.
        </>
      ),
      rotulo: "Versão",
      dica: d.versao_atual ? `A última publicada é a ${d.versao_atual}.` : "Nenhuma versão publicada ainda.",
      confirmar: "Abrir release",
      pedeTexto: true,
      multilinha: false,
      valorInicial: d.versao_sugerida,
    });
    if (versao) {
      void agir("nova", () => pase.createRelease(versao), `Release ${versao} aberta.`);
    }
  }

  const abertas = d.releases.filter((r) => !["publicada", "cancelada"].includes(r.status));
  const encerradas = d.releases.filter((r) => ["publicada", "cancelada"].includes(r.status));

  return (
    <section>
      <div className="mb-3 flex items-center">
        <h2 className="eyebrow">Releases</h2>
        <Botao
          className="ml-auto"
          tamanho="sm"
          ocupado={ocupado === "nova"}
          disabled={ocupado !== null}
          onClick={() => void nova()}
        >
          Nova release
        </Botao>
      </div>

      {d.releases.length === 0 ? (
        <Vazio titulo="Nenhuma release">
          Abra uma para reunir as tarefas aprovadas nos testes e publicá-las juntas.
        </Vazio>
      ) : (
        <div className="space-y-6">
          {abertas.map((r) => (
            <CartaoDaRelease key={r.id} r={r} github={d.github} />
          ))}
          {encerradas.length > 0 && (
            <details>
              <summary className="cursor-pointer font-mono text-[12.5px] text-ink-3 hover:text-ink">
                {encerradas.length} encerrada(s)
              </summary>
              <div className="mt-4 space-y-4">
                {encerradas.map((r) => (
                  <CartaoDaRelease key={r.id} r={r} github={d.github} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </section>
  );
}

function CartaoDaRelease({ r, github }: { r: ReleaseRow; github: boolean }) {
  const { ocupado, agir } = useAcao();
  const perguntar = usePergunta();
  const [changelog, setChangelog] = useState(r.changelog);
  const [verPr, setVerPr] = useState(false);
  const s = STATUS_DA_RELEASE[r.status];
  const editavel = r.status === "aberta" || r.status === "validada";
  const sujo = changelog !== r.changelog;

  async function publicar() {
    const nota = await perguntar({
      titulo: `Publicar ${r.version}`,
      efeito: (
        <>
          A <code>{r.branch}</code> entra na principal, a tag <code>{r.version}</code> é criada e as{" "}
          {r.tasks.length} tarefa(s) passam a estar em produção.{" "}
          <strong className="font-medium text-ink">Não há botão de desfazer:</strong> depois disto, o
          caminho é uma release de correção.
          {!github && " (Sem GitHub configurado, o merge na principal é feito localmente.)"}
        </>
      ),
      rotulo: "Sua aprovação",
      dica: "Fica registrada com a release. Ex.: li o PR, a validação passou, aprovo.",
      confirmar: `Publicar ${r.version}`,
      perigo: true,
    });
    if (nota) {
      void agir(
        `publicar-${r.id}`,
        async () => {
          const res = await pase.publishRelease(r.id, nota);
          if (!res.publicada) throw new Error(res.detail ?? "a publicação falhou");
        },
        `Release ${r.version} publicada.`,
      );
    }
  }

  async function cancelar() {
    const motivo = await perguntar({
      titulo: `Cancelar ${r.version}?`,
      efeito:
        "As tarefas voltam à develop, aprovadas nos testes, prontas para outra release. A branch fica para auditoria.",
      confirmar: "Cancelar release",
      perigo: true,
    });
    if (motivo) {
      void agir(`cancelar-${r.id}`, () => pase.cancelRelease(r.id, motivo), `Release ${r.version} cancelada.`);
    }
  }

  return (
    <article className={`rounded border bg-surface ${r.status === "pr_aberto" ? "border-signal/50" : "border-line"}`}>
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <h3 className="font-mono text-[18px] font-medium">{r.version}</h3>
        <Tag tom={s.tom} ponto>
          {s.rotulo}
        </Tag>
        {r.validation_ok === true && <Tag tom="ok">validação passou</Tag>}
        {r.validation_ok === false && <Tag tom="bad">validação reprovou</Tag>}
        {r.pr_url && (
          <a href={r.pr_url} target="_blank" rel="noreferrer" className="font-mono text-[12px] underline">
            PR #{r.pr_number}
          </a>
        )}
        <span className="ml-auto font-mono text-[11.5px] text-ink-3">{r.branch}</span>
      </header>

      <div className="grid gap-6 p-4 lg:grid-cols-2">
        <div>
          <p className="eyebrow mb-2">Tarefas · {r.tasks.length}</p>
          {r.tasks.length === 0 ? (
            <p className="text-[13px] text-ink-3">
              Vazia. Inclua tarefas aprovadas nos testes, na seção Develop.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {r.tasks.map((t) => (
                <li key={t.id} className="flex items-center gap-2 text-[13.5px]">
                  <span className="font-mono text-[12px] text-ink-3">#{t.id}</span>
                  <Link href={`/tarefas/${t.id}`} className="min-w-0 truncate hover:underline">
                    {t.title}
                  </Link>
                  <Risco tier={t.risk_tier} />
                  {editavel && (
                    <Botao
                      className="ml-auto"
                      tamanho="sm"
                      variante="fantasma"
                      disabled={ocupado !== null}
                      onClick={() =>
                        agir(
                          `tirar-${t.id}`,
                          () => pase.removeFromRelease(r.id, t.id),
                          `#${t.id} saiu da release ${r.version}.`,
                        )
                      }
                    >
                      Tirar
                    </Botao>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className="eyebrow mb-2">Changelog</p>
          <textarea
            aria-label={`Changelog da ${r.version}`}
            value={changelog}
            readOnly={!editavel}
            rows={Math.max(4, changelog.split("\n").length + 1)}
            onChange={(e) => setChangelog(e.target.value)}
            className={`${AREA_TEXTO} ${!editavel ? "bg-sunken" : ""}`}
          />
          {sujo && (
            <Botao
              className="mt-2"
              tamanho="sm"
              ocupado={ocupado === `changelog-${r.id}`}
              disabled={ocupado !== null}
              onClick={() =>
                agir(`changelog-${r.id}`, () => pase.editChangelog(r.id, changelog), "Changelog salvo.")
              }
            >
              Salvar changelog
            </Botao>
          )}
        </div>
      </div>

      {r.pr_body && (
        <div className="border-t border-line px-4 py-3">
          <button
            type="button"
            onClick={() => setVerPr((v) => !v)}
            aria-expanded={verPr}
            className="font-mono text-[12.5px] text-ink-2 hover:text-ink"
          >
            {verPr ? "− " : "+ "}descrição do Pull Request
          </button>
          {verPr && <BlocoDeCodigo className="mt-3 max-h-80 whitespace-pre-wrap">{r.pr_body}</BlocoDeCodigo>}
        </div>
      )}

      {r.status === "publicada" && r.approval_note && (
        <p className="border-t border-line px-4 py-3 text-[13px] text-ink-2">
          <span className="font-mono text-[12px] text-ink-3">aprovação:</span> “{r.approval_note}” ·{" "}
          {r.published_at && haQuantoTempo(r.published_at)}
        </p>
      )}

      {!["publicada", "cancelada"].includes(r.status) && (
        <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-sunken/50 px-4 py-3">
          <Botao
            ocupado={ocupado === `validar-${r.id}` || r.status === "validando"}
            disabled={ocupado !== null || r.tasks.length === 0 || !editavel}
            title="Roda lint, tipos, testes e build na branch da release, com tudo integrado"
            onClick={() =>
              agir(`validar-${r.id}`, () => pase.validateRelease(r.id), "Validação final iniciada.")
            }
          >
            {r.status === "validando" ? "Validando" : "Validar release"}
          </Botao>
          <Botao
            ocupado={ocupado === `pr-${r.id}`}
            disabled={ocupado !== null || r.status !== "validada"}
            title="Só abre depois da validação final"
            onClick={() => agir(`pr-${r.id}`, () => pase.openPullRequest(r.id), "Pull Request aberto.")}
          >
            Abrir Pull Request
          </Botao>
          <Botao
            variante="sinal"
            ocupado={ocupado === `publicar-${r.id}`}
            disabled={ocupado !== null || r.status !== "pr_aberto"}
            onClick={() => void publicar()}
          >
            Publicar
          </Botao>
          <Botao
            className="ml-auto"
            variante="fantasma"
            disabled={ocupado !== null}
            onClick={() => void cancelar()}
          >
            Cancelar release
          </Botao>
        </footer>
      )}
    </article>
  );
}

// --------------------------------------------------------------------------- //
// Rastro e regras
// --------------------------------------------------------------------------- //

function Rastro({ eventos }: { eventos: EventoDePipeline[] }) {
  return (
    <section>
      <h2 className="eyebrow mb-3">Rastro do pipeline</h2>
      {eventos.length === 0 ? (
        <Vazio titulo="Sem eventos ainda" />
      ) : (
        <ol className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
          {eventos.map((e) => (
            <li key={e.id} className="grid gap-x-3 gap-y-1 px-4 py-2.5 sm:grid-cols-[1.25rem_10rem_6rem_1fr_5rem] sm:items-center">
              <Ponto tom={e.ok ? "ok" : "bad"} />
              <span className="font-mono text-[12px] text-ink-2">{e.branch}</span>
              <Tag tom={TOM_DO_EVENTO[e.kind] ?? "neutro"}>{e.kind}</Tag>
              <span className="min-w-0 text-[13px] text-ink-2">
                {e.task_id && (
                  <Link href={`/tarefas/${e.task_id}`} className="mr-2 font-mono text-[12px] text-ink-3 hover:text-ink">
                    #{e.task_id}
                  </Link>
                )}
                {e.detail}
              </span>
              <span className="font-mono text-[11.5px] text-ink-3 sm:text-right">{haQuantoTempo(e.at)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Regras({ d }: { d: Entrega }) {
  return (
    <Secao titulo="Regras do fluxo, aplicadas por código">
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <table className="w-full text-[13px]">
          <thead className="eyebrow text-left">
            <tr className="border-b border-line">
              <th className="py-2 font-medium">origem</th>
              <th className="py-2 font-medium">destino</th>
              <th className="py-2 font-medium">método</th>
            </tr>
          </thead>
          <tbody>
            {d.regras.map((r) => (
              <tr key={`${r.origem}-${r.destino}`} className="border-b border-line last:border-0">
                <td className="py-2 font-mono text-[12.5px]">{r.origem}/*</td>
                <td className="py-2 font-mono text-[12.5px]">{r.destino === "release" ? "release/x.x.x" : r.destino}</td>
                <td className="py-2 text-ink-2">{r.metodo}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="space-y-1.5 text-[13px] text-ink-2">
          <li>
            <span className="font-medium text-ink">Proibido:</span> feature ou hotfix direto na{" "}
            {d.principal}; develop em qualquer outra branch; criar branch de trabalho a partir da develop.
          </li>
          <li>Branch que incorporou a develop é recusada antes do merge.</li>
          <li>Falha de CI na develop desfaz a integração.</li>
          <li>Só o que foi aprovado nos testes entra numa release.</li>
          <li>Publicar exige PR aberto, validação verde e a sua aprovação por escrito.</li>
        </ul>
      </div>
      <div className="mt-5 grid grid-cols-3 gap-4 border-t border-line pt-4">
        <Medida rotulo="principal" valor={d.principal} />
        <Medida rotulo="versão atual" valor={d.versao_atual ?? "-"} />
        <Medida rotulo="GitHub" valor={d.github ? "ligado" : "local"} />
      </div>
    </Secao>
  );
}
