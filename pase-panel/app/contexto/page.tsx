"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useAviso, usePergunta } from "@/components/interacoes";
import PanelShell from "@/components/PanelShell";
import {
  AREA_TEXTO,
  Abas,
  BlocoDeCodigo,
  Botao,
  Campo,
  Carregando,
  Diff,
  ENTRADA,
  Secao,
  Tag,
} from "@/components/ui";
import {
  haQuantoTempo,
  milhar,
  pase,
  type DocumentoCompleto,
  type DocumentoResumo,
  type LeituraDeContexto,
  type PropostaDeContexto,
  type SugestaoDeContexto,
  type VersaoDeDocumento,
} from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * Tela Contexto: os documentos que dizem ao sistema o que o produto é e como se escreve
 * código nele.
 *
 * Moram no banco, não no repositório. Editar aqui vale na próxima chamada de qualquer
 * etapa que leia o documento, sem commit nem reinício, e cada edição vira uma versão que
 * dá para consultar e restaurar. O mapa "quem lê o quê" existe para que mudar um texto
 * não seja um ato às cegas: antes de salvar, dá para ver que etapas vão ler a mudança.
 *
 * A IA só propõe, e uma pessoa decide. O Executor não escreve aqui.
 */

const PASTAS: { chave: string | null; rotulo: string }[] = [
  { chave: null, rotulo: "Documentos" },
  { chave: "adrs", rotulo: "Decisões (ADRs)" },
  { chave: "design-systems", rotulo: "Design systems" },
];

type Aba = "editar" | "historico" | "leitores";

export default function Contexto() {
  const lista = useLista(["context"], () => pase.context());
  const [slug, setSlug] = useState<string>("project-context");
  const dados = lista.data;

  const agrupados = useMemo(() => {
    const docs = dados?.documentos ?? [];
    return PASTAS.map((p) => ({
      ...p,
      itens: docs.filter((d) => d.folder === p.chave),
    })).filter((g) => g.itens.length > 0 || g.chave === null);
  }, [dados]);

  return (
    <PanelShell
      titulo="Contexto do projeto"
      descricao="Os documentos que o sistema lê para decidir o que cabe no produto e como se escreve código nele. Editar aqui vale na próxima chamada, sem commit nem reinício."
    >
      {lista.isLoading && <Carregando />}

      {dados && (
        <div className="space-y-10">
          <Sugestoes onAbrir={setSlug} />

          <MapaDeLeituras leituras={dados.leituras} onAbrir={setSlug} />

          <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
            <Indice grupos={agrupados} atual={slug} onEscolher={setSlug} />
            <Documento key={slug} slug={slug} onCriou={setSlug} />
          </div>
        </div>
      )}
    </PanelShell>
  );
}

// --------------------------------------------------------------------------- //
// Sugestões da IA depois de uma aprovação
// --------------------------------------------------------------------------- //

/**
 * O modelo PASE fecha o laço: uma tarefa aprovada pode deixar o contexto desatualizado.
 * A IA sugere o texto novo e mostra o que mudaria; você aceita ou dispensa. Aceitar grava
 * uma versão nova. Ela nunca grava sozinha.
 */
function Sugestoes({ onAbrir }: { onAbrir: (slug: string) => void }) {
  const client = useQueryClient();
  const avisar = useAviso();
  const sugestoes = useLista(["context-suggestions"], () => pase.contextSuggestions(), {
    atualizarACada: 30_000,
  });
  const [aberta, setAberta] = useState<number | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const lista = sugestoes.data ?? [];

  async function decidir(s: SugestaoDeContexto, aceitar: boolean) {
    setOcupado(s.id);
    try {
      if (aceitar) await pase.acceptSuggestion(s.id);
      else await pase.dismissSuggestion(s.id);
      avisar(aceitar ? `Salvo: ${s.slug} ganhou uma versão nova.` : "Sugestão dispensada.");
      await client.invalidateQueries({ queryKey: ["context-suggestions"] });
      await client.invalidateQueries({ queryKey: ["context"] });
      await client.invalidateQueries({ queryKey: ["context-doc", s.slug] });
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(null);
    }
  }

  if (lista.length === 0) return null;

  return (
    <section>
      <h2 className="eyebrow mb-3">Sugestões da IA · {lista.length}</h2>
      <ul className="space-y-3">
        {lista.map((s) => (
          <li key={s.id} className="rounded border border-signal/40 bg-surface">
            <div className="flex flex-wrap items-center gap-2 px-4 py-3">
              <Tag tom="signal" ponto>
                a decidir
              </Tag>
              <button
                type="button"
                onClick={() => onAbrir(s.slug)}
                className="font-mono text-[12px] underline decoration-line-strong underline-offset-4 hover:text-signal"
              >
                {s.slug}
              </button>
              {s.task_id && (
                <span className="font-mono text-[12px] text-ink-3">tarefa #{s.task_id}</span>
              )}
              <span className="ml-auto font-mono text-[11.5px] text-ink-3">
                sobre a v{s.base_version} · {haQuantoTempo(s.created_at)}
              </span>
            </div>
            <p className="px-4 pb-3 text-[13.5px] text-ink">{s.summary}</p>
            {s.reasoning && <p className="px-4 pb-3 text-[12.5px] text-ink-2">{s.reasoning}</p>}

            {aberta === s.id && (
              <div className="mx-4 mb-3 max-h-72 overflow-auto rounded border border-line bg-sunken p-3">
                <Diff texto={s.diff} />
              </div>
            )}

            <div className="flex flex-wrap gap-2 border-t border-line bg-sunken/50 px-4 py-2.5">
              <Botao
                tamanho="sm"
                variante="fantasma"
                onClick={() => setAberta(aberta === s.id ? null : s.id)}
              >
                {aberta === s.id ? "Esconder o que muda" : "Ver o que muda"}
              </Botao>
              <Botao
                className="ml-auto"
                tamanho="sm"
                variante="primario"
                ocupado={ocupado === s.id}
                disabled={ocupado !== null}
                onClick={() => void decidir(s, true)}
              >
                Aceitar
              </Botao>
              <Botao tamanho="sm" disabled={ocupado !== null} onClick={() => void decidir(s, false)}>
                Dispensar
              </Botao>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Quem lê o quê
// --------------------------------------------------------------------------- //

function MapaDeLeituras({
  leituras,
  onAbrir,
}: {
  leituras: LeituraDeContexto[];
  onAbrir: (slug: string) => void;
}) {
  return (
    <section>
      <h2 className="eyebrow mb-3">Quem lê o quê, em cada etapa do ciclo</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {leituras.map((l) => (
          <article key={l.key} className="rounded border border-line bg-surface p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[14px] font-medium">{l.etapa}</h3>
              {l.prompts.map((p) => (
                <Tag key={p} tom="info">
                  {p}
                </Tag>
              ))}
              <span className="tnum ml-auto font-mono text-[11.5px] text-ink-3">
                ~{milhar(Math.round(l.chars / 4))} tokens
              </span>
            </div>
            <p className="mt-1.5 text-[12.5px] text-ink-2">{l.descricao}</p>
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {l.documentos.map((d) => (
                <li key={d}>
                  <button
                    type="button"
                    onClick={() => onAbrir(d)}
                    className="rounded-sm border border-line-strong/70 bg-sunken px-1.5 py-px font-mono text-[11px] text-ink-2 hover:border-ink-3 hover:text-ink"
                  >
                    {d}
                  </button>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Índice
// --------------------------------------------------------------------------- //

function Indice({
  grupos,
  atual,
  onEscolher,
}: {
  grupos: { chave: string | null; rotulo: string; itens: DocumentoResumo[] }[];
  atual: string;
  onEscolher: (slug: string) => void;
}) {
  const client = useQueryClient();
  const avisar = useAviso();
  const perguntar = usePergunta();

  async function novo(pasta: string | null) {
    const nome = await perguntar({
      titulo: pasta === "adrs" ? "Nova decisão" : "Novo documento",
      efeito:
        "O nome identifica o documento e não muda depois. Use minúsculas, números e hífen" +
        (pasta ? `, dentro de ${pasta}/.` : "."),
      rotulo: "Nome",
      dica: pasta === "adrs" ? "Ex.: 0006-cache-de-relatorios" : "Ex.: glossario",
      confirmar: "Criar",
      multilinha: false,
    });
    if (!nome) return;
    const slug = pasta ? `${pasta}/${nome.trim()}` : nome.trim();
    try {
      await pase.createContextDoc(slug, `# ${nome.trim()}\n\nEscreva aqui.\n`);
      await client.invalidateQueries({ queryKey: ["context"] });
      onEscolher(slug);
      avisar(`Documento ${slug} criado.`);
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    }
  }

  return (
    <nav aria-label="Documentos de contexto" className="space-y-6">
      {grupos.map((g) => (
        <div key={g.rotulo}>
          <div className="mb-1.5 flex items-center px-1">
            <p className="eyebrow">{g.rotulo}</p>
            {(g.chave === "adrs" || g.chave === null) && (
              <button
                type="button"
                onClick={() => void novo(g.chave)}
                className="ml-auto font-mono text-[11px] text-ink-3 hover:text-ink"
                title="Criar documento"
              >
                + novo
              </button>
            )}
          </div>
          <ul className="space-y-px">
            {g.itens.map((d) => {
              const ativo = d.slug === atual;
              return (
                <li key={d.slug}>
                  <button
                    type="button"
                    onClick={() => onEscolher(d.slug)}
                    aria-current={ativo ? "true" : undefined}
                    className={`flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[13px] transition-colors ${
                      ativo
                        ? "bg-surface font-medium text-ink shadow-[inset_0_0_0_1px_rgb(var(--line))]"
                        : "text-ink-2 hover:bg-surface/60 hover:text-ink"
                    }`}
                  >
                    <span className="min-w-0 truncate">{d.title}</span>
                    <span className="tnum ml-auto shrink-0 font-mono text-[10.5px] text-ink-3">
                      v{d.version}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

// --------------------------------------------------------------------------- //
// Documento
// --------------------------------------------------------------------------- //

function Documento({ slug, onCriou }: { slug: string; onCriou: (slug: string) => void }) {
  void onCriou;
  const doc = useLista(["context-doc", slug], () => pase.contextDoc(slug));
  const [aba, setAba] = useState<Aba>("editar");

  if (doc.isLoading) return <Carregando />;
  if (!doc.data) {
    return (
      <p className="rounded border border-bad/30 bg-bad/[0.06] p-4 text-[13.5px] text-bad">
        Não consegui abrir o documento {slug}.
      </p>
    );
  }

  return (
    <section className="min-w-0">
      <header className="mb-4">
        <p className="font-mono text-[12px] text-ink-3">{doc.data.slug}</p>
        <h2 className="mt-1 font-display text-[30px] leading-tight">{doc.data.title}</h2>
        <p className="mt-1 font-mono text-[11.5px] text-ink-3">
          v{doc.data.version} · {doc.data.updated_by} · {haQuantoTempo(doc.data.updated_at)} ·{" "}
          {milhar(doc.data.chars)} caracteres
        </p>
      </header>

      <Abas
        atual={aba}
        onTrocar={setAba}
        abas={[
          { id: "editar", rotulo: "Editar" },
          { id: "historico", rotulo: "Histórico", contagem: doc.data.version },
          { id: "leitores", rotulo: "Quem lê", contagem: doc.data.readers.length },
        ]}
      />

      <div className="mt-5">
        {aba === "editar" && <Editor doc={doc.data} />}
        {aba === "historico" && <Historico slug={slug} />}
        {aba === "leitores" && <Leitores doc={doc.data} />}
      </div>
    </section>
  );
}

function Leitores({ doc }: { doc: DocumentoCompleto }) {
  if (doc.readers.length === 0) {
    return (
      <p className="text-[13.5px] text-ink-2">
        Nenhuma etapa lê este documento hoje. Ele serve a pessoas e a agentes futuros.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
      {doc.readers.map((l) => (
        <li key={l.key} className="flex flex-wrap items-center gap-2 px-4 py-3">
          <span className="text-[14px] font-medium">{l.etapa}</span>
          {l.prompts.map((p) => (
            <Tag key={p} tom="info">
              {p}
            </Tag>
          ))}
        </li>
      ))}
    </ul>
  );
}

function Editor({ doc }: { doc: DocumentoCompleto }) {
  const client = useQueryClient();
  const avisar = useAviso();
  const [texto, setTexto] = useState(doc.content);
  const [nota, setNota] = useState("");
  const [pedido, setPedido] = useState("");
  const [proposta, setProposta] = useState<PropostaDeContexto | null>(null);
  const [ocupado, setOcupado] = useState<"salvando" | "propondo" | null>(null);

  useEffect(() => {
    setTexto(doc.content);
  }, [doc.content, doc.version]);

  const sujo = texto !== doc.content;

  async function salvar() {
    setOcupado("salvando");
    try {
      const r = await pase.saveContextDoc(doc.slug, texto, nota);
      avisar(
        r.salvo
          ? `Salvo como v${r.version}. As etapas que leem este documento já usam o texto novo.`
          : "Nada mudou.",
      );
      setNota("");
      setProposta(null);
      await client.invalidateQueries({ queryKey: ["context"] });
      await client.invalidateQueries({ queryKey: ["context-doc", doc.slug] });
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(null);
    }
  }

  async function propor() {
    setOcupado("propondo");
    try {
      const r = await pase.proposeContextDoc(doc.slug, pedido);
      if (!r.aplicavel) avisar(`O modelo não aplicou a mudança: ${r.reasoning}`, "info");
      else {
        setProposta(r);
        setNota(r.summary);
      }
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div className="space-y-6">
      <Secao titulo="Pedir uma proposta à IA">
        <Campo
          rotulo="Descreva a mudança"
          dica="O modelo propõe um texto novo e mostra o que mudaria. Ele nunca grava sozinho."
        >
          <textarea
            value={pedido}
            onChange={(e) => setPedido(e.target.value)}
            rows={2}
            placeholder="Ex.: metas de orçamento por categoria deixam de estar fora de escopo"
            className={AREA_TEXTO}
          />
        </Campo>
        <Botao
          className="mt-3"
          tamanho="sm"
          ocupado={ocupado === "propondo"}
          disabled={ocupado !== null || !pedido.trim()}
          onClick={() => void propor()}
        >
          Propor alteração
        </Botao>

        {proposta && (
          <div className="mt-5">
            <p className="eyebrow mb-2">O que mudaria</p>
            <div className="max-h-72 overflow-auto rounded border border-line bg-sunken p-3">
              <Diff texto={proposta.diff} />
            </div>
            <Botao
              className="mt-3"
              tamanho="sm"
              onClick={() => {
                setTexto(proposta.content);
                setProposta(null);
              }}
            >
              Levar para o editor
            </Botao>
          </div>
        )}
      </Secao>

      <Campo rotulo="Texto (markdown)">
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={Math.min(34, Math.max(14, texto.split("\n").length + 1))}
          className={`${AREA_TEXTO} font-mono text-[12.5px]`}
          spellCheck={false}
        />
      </Campo>

      <Campo rotulo="Motivo da mudança" dica="Fica no histórico, ao lado desta versão.">
        <input
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder="ex.: metas de orçamento entram no escopo"
          className={ENTRADA}
        />
      </Campo>

      <div className="flex flex-wrap items-center gap-2">
        <Botao
          variante="primario"
          ocupado={ocupado === "salvando"}
          disabled={ocupado !== null || !sujo || !nota.trim()}
          onClick={() => void salvar()}
        >
          Salvar nova versão
        </Botao>
        {sujo && (
          <Botao variante="fantasma" onClick={() => setTexto(doc.content)}>
            Descartar edição
          </Botao>
        )}
        {sujo && !nota.trim() && (
          <span className="text-[12.5px] text-ink-3">Diga o motivo para poder salvar.</span>
        )}
      </div>
    </div>
  );
}

function Historico({ slug }: { slug: string }) {
  const client = useQueryClient();
  const avisar = useAviso();
  const perguntar = usePergunta();
  const versoes = useLista(["context-history", slug], () => pase.contextHistory(slug));
  const [aberta, setAberta] = useState<{ version: number; content: string } | null>(null);

  if (versoes.isLoading) return <Carregando />;

  async function ver(v: VersaoDeDocumento) {
    const r = await pase.contextVersion(slug, v.version);
    setAberta({ version: v.version, content: r.content });
  }

  async function restaurar(v: VersaoDeDocumento) {
    const ok = await perguntar({
      titulo: `Restaurar a v${v.version}?`,
      efeito:
        "O texto dessa versão volta como uma versão nova. Nada do histórico é apagado: desfazer também fica registrado.",
      confirmar: "Restaurar",
      pedeTexto: false,
    });
    if (!ok) return;
    try {
      await pase.restoreContextDoc(slug, v.version);
      avisar(`Versão ${v.version} restaurada como a mais recente.`);
      await client.invalidateQueries({ queryKey: ["context"] });
      await client.invalidateQueries({ queryKey: ["context-doc", slug] });
      await client.invalidateQueries({ queryKey: ["context-history", slug] });
    } catch (erro) {
      avisar(`Falhou: ${String(erro)}`);
    }
  }

  return (
    <div className="space-y-4">
      <ol className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
        {(versoes.data ?? []).map((v) => (
          <li key={v.version} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
            <span className="tnum font-mono text-[12.5px] font-medium">v{v.version}</span>
            <span className="min-w-0 flex-1 text-[13.5px] text-ink-2">{v.note || "sem nota"}</span>
            <span className="font-mono text-[11.5px] text-ink-3">
              {v.author} · {haQuantoTempo(v.created_at)}
            </span>
            <Botao tamanho="sm" variante="fantasma" onClick={() => void ver(v)}>
              Ver
            </Botao>
            <Botao tamanho="sm" onClick={() => void restaurar(v)}>
              Restaurar
            </Botao>
          </li>
        ))}
      </ol>
      {aberta && (
        <Secao
          titulo={`Texto da v${aberta.version}`}
          acoes={
            <Botao tamanho="sm" variante="fantasma" onClick={() => setAberta(null)}>
              Fechar
            </Botao>
          }
        >
          <BlocoDeCodigo className="max-h-96 whitespace-pre-wrap">{aberta.content}</BlocoDeCodigo>
        </Secao>
      )}
    </div>
  );
}
