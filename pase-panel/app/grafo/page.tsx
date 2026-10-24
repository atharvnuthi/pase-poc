"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import PanelShell from "@/components/PanelShell";
import { Carregando, Vazio } from "@/components/ui";
import { type GraphEdge, type GraphNode, pase } from "@/lib/api";
import { useLista } from "@/lib/query";

/**
 * O pipeline como grafo, ao vivo.
 *
 * Desenhado em SVG à mão, sem biblioteca de grafos. Não é teimosia: o layout
 * que interessa aqui é **por profundidade de dependência** - quem não espera
 * ninguém fica na primeira coluna, quem espera fica à direita de quem o
 * bloqueia. Um layout de força genérico esconderia exatamente essa leitura, e
 * traria um pacote grande para desenhar meia dúzia de nós.
 *
 * Atualiza pelo SSE que já existe: o cache `graph` é invalidado a cada evento
 * de tarefa.
 */

/** Cores por estado, como tokens do tema: o grafo acompanha claro e escuro. */
const v = (nome: string, alfa?: number) => `rgb(var(--${nome})${alfa !== undefined ? ` / ${alfa}` : ""})`;

const COR_DO_ESTADO: Record<string, { fundo: string; borda: string; texto: string }> = {
  candidata: { fundo: v("surface"), borda: v("signal"), texto: v("ink") },
  em_planejamento: { fundo: v("info", 0.08), borda: v("info"), texto: v("ink") },
  pronta_para_despacho: { fundo: v("info", 0.05), borda: v("info", 0.6), texto: v("ink") },
  em_execucao: { fundo: v("ok", 0.09), borda: v("ok"), texto: v("ink") },
  em_homologacao: { fundo: v("signal", 0.1), borda: v("signal"), texto: v("ink") },
  suspensa: { fundo: v("bad", 0.08), borda: v("bad"), texto: v("ink") },
  finalizada: { fundo: v("sunken"), borda: v("line-strong"), texto: v("ink-2") },
};

const TRACO_DA_ARESTA: Record<string, string> = {
  arquivo: "4 3",
  // Pontilhada e fina: a aresta semântica informa, não segura ninguém.
  semantica: "1 4",
  manual: "1 0",
};

/** Só arquivo e manual seguram o despacho; a semântica fica de fora do layout. */
const bloqueia = (aresta: GraphEdge) => aresta.kind !== "semantica";

const COR_DA_ARESTA: Record<string, string> = {
  arquivo: v("ink-3"),
  semantica: v("zone"),
  manual: v("info"),
};

const LARGURA = 230;
const ALTURA = 76;
const VAO_X = 110;
const VAO_Y = 26;

interface Posicionado extends GraphNode {
  x: number;
  y: number;
  camada: number;
}

/**
 * Profundidade = maior caminho até um nó que não depende de ninguém.
 *
 * Calculado com memória e marcação de "em visita": um ciclo no grafo faria a
 * recursão não terminar. O servidor recusa ciclos, mas a tela não pode contar
 * com isso para não travar o navegador.
 */
function profundidades(nodes: GraphNode[], edges: GraphEdge[]): Map<number, number> {
  const dependenciasDe = new Map<number, number[]>();
  for (const no of nodes) dependenciasDe.set(no.id, []);
  // A coluna diz quem espera por quem; uma aresta semântica não faz ninguém esperar.
  for (const aresta of edges.filter(bloqueia)) dependenciasDe.get(aresta.from)?.push(aresta.to);

  const resultado = new Map<number, number>();
  const visitando = new Set<number>();

  function calcular(id: number): number {
    const pronto = resultado.get(id);
    if (pronto !== undefined) return pronto;
    if (visitando.has(id)) return 0; // ciclo: corta aqui

    visitando.add(id);
    const alvos = dependenciasDe.get(id) ?? [];
    const profundidade = alvos.length === 0 ? 0 : Math.max(...alvos.map(calcular)) + 1;
    visitando.delete(id);

    resultado.set(id, profundidade);
    return profundidade;
  }

  for (const no of nodes) calcular(no.id);
  return resultado;
}

function posicionar(nodes: GraphNode[], edges: GraphEdge[]): Posicionado[] {
  const profundidade = profundidades(nodes, edges);
  const porCamada = new Map<number, GraphNode[]>();

  for (const no of nodes) {
    const camada = profundidade.get(no.id) ?? 0;
    if (!porCamada.has(camada)) porCamada.set(camada, []);
    porCamada.get(camada)!.push(no);
  }

  const posicionados: Posicionado[] = [];
  for (const [camada, daCamada] of [...porCamada.entries()].sort((a, b) => a[0] - b[0])) {
    daCamada.sort((a, b) => b.priority_score - a.priority_score || a.id - b.id);
    daCamada.forEach((no, i) => {
      posicionados.push({
        ...no,
        camada,
        x: camada * (LARGURA + VAO_X),
        y: i * (ALTURA + VAO_Y),
      });
    });
  }
  return posicionados;
}

export default function Grafo() {
  const grafo = useLista(["graph"], () => pase.graph());
  const [focado, setFocado] = useState<number | null>(null);

  const nos = useMemo(
    () => posicionar(grafo.data?.nodes ?? [], grafo.data?.edges ?? []),
    [grafo.data],
  );
  const porId = useMemo(() => new Map(nos.map((n) => [n.id, n])), [nos]);
  const arestas = grafo.data?.edges ?? [];

  const largura = Math.max(...nos.map((n) => n.x + LARGURA), 600) + 40;
  const altura = Math.max(...nos.map((n) => n.y + ALTURA), 240) + 40;

  const vizinhos = useMemo(() => {
    if (focado === null) return null;
    const ligados = new Set<number>([focado]);
    for (const a of arestas) {
      if (a.from === focado) ligados.add(a.to);
      if (a.to === focado) ligados.add(a.from);
    }
    return ligados;
  }, [focado, arestas]);

  return (
    <PanelShell
      titulo="Dependências"
      descricao="Cada tarefa é um nó; cada seta é uma dependência. Quem está à direita espera por quem está à esquerda."
    >
      {grafo.isLoading && <Carregando />}

      {grafo.data && nos.length === 0 && (
        <Vazio titulo="Nenhuma tarefa ainda">O grafo aparece quando houver tarefas com dependências.</Vazio>
      )}

      {nos.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-4 font-mono text-[11.5px] text-ink-3">
            <span className="flex items-center gap-2">
              <svg width="30" height="8">
                <line x1="0" y1="4" x2="30" y2="4" stroke={COR_DA_ARESTA.arquivo} strokeWidth="2" strokeDasharray="4 3" />
              </svg>
              arquivos em comum
            </span>
            <span className="flex items-center gap-2">
              <svg width="30" height="8">
                <line
                  x1="0"
                  y1="4"
                  x2="30"
                  y2="4"
                  stroke={COR_DA_ARESTA.semantica}
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeDasharray={TRACO_DA_ARESTA.semantica}
                />
              </svg>
              tema parecido (não bloqueia)
            </span>
            <span className="flex items-center gap-2">
              <svg width="30" height="8">
                <line x1="0" y1="4" x2="30" y2="4" stroke={COR_DA_ARESTA.manual} strokeWidth="2" />
              </svg>
              manual
            </span>
            <Link href="/sistema#glossario" className="ml-auto underline underline-offset-4 hover:text-ink">
              O que cada etiqueta significa
            </Link>
          </div>

          <div className="overflow-auto rounded border border-line bg-sunken p-6">
            <svg width={largura} height={altura} role="img" aria-label="Grafo de dependências entre tarefas">
              <defs>
                <marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={v("ink-3")} />
                </marker>
              </defs>

              {arestas.map((a) => {
                const origem = porId.get(a.from);
                const destino = porId.get(a.to);
                if (!origem || !destino) return null;

                // A seta sai da esquerda de quem depende e chega na direita de
                // quem bloqueia: o sentido da leitura é "espera por".
                const x1 = origem.x;
                const y1 = origem.y + ALTURA / 2;
                const x2 = destino.x + LARGURA;
                const y2 = destino.y + ALTURA / 2;
                const meio = (x1 + x2) / 2;
                const apagada = vizinhos !== null && !(vizinhos.has(a.from) && vizinhos.has(a.to));

                return (
                  <path
                    key={`${a.from}-${a.to}`}
                    d={`M ${x1} ${y1} C ${meio} ${y1}, ${meio} ${y2}, ${x2} ${y2}`}
                    fill="none"
                    stroke={COR_DA_ARESTA[a.kind] ?? v("ink-3")}
                    strokeWidth="2"
                    strokeLinecap={bloqueia(a) ? undefined : "round"}
                    strokeDasharray={TRACO_DA_ARESTA[a.kind] ?? "1 0"}
                    markerEnd={bloqueia(a) ? "url(#seta)" : undefined}
                    opacity={apagada ? 0.15 : bloqueia(a) ? 0.9 : 0.7}
                  >
                    <title>
                      {a.reason ?? `dependência ${a.kind}`}
                      {bloqueia(a) ? "" : " - informativa, não segura o despacho"}
                    </title>
                  </path>
                );
              })}

              {nos.map((no) => {
                const cor = COR_DO_ESTADO[no.status] ?? COR_DO_ESTADO.candidata;
                const apagado = vizinhos !== null && !vizinhos.has(no.id);

                return (
                  <g
                    key={no.id}
                    transform={`translate(${no.x}, ${no.y})`}
                    opacity={apagado ? 0.25 : 1}
                    onMouseEnter={() => setFocado(no.id)}
                    onMouseLeave={() => setFocado(null)}
                    style={{ cursor: "pointer" }}
                  >
                    <a href={`/tarefas/${no.id}`}>
                      <rect
                        width={LARGURA}
                        height={ALTURA}
                        rx="4"
                        fill={cor.fundo}
                        stroke={no.alert !== "none" ? v("bad") : cor.borda}
                        strokeWidth={no.alert !== "none" ? 2 : 1.5}
                      />
                      <text x="14" y="25" fill={cor.texto} fontSize="13" fontWeight="600" fontFamily="IBM Plex Sans, sans-serif">
                        #{no.id} {no.title.length > 24 ? `${no.title.slice(0, 24)}…` : no.title}
                      </text>
                      <text x="14" y="45" fill={cor.texto} fontSize="11" opacity="0.75" fontFamily="IBM Plex Mono, monospace">
                        {no.status.replace(/_/g, " ")}
                        {no.final_outcome ? ` · ${no.final_outcome}` : ""}
                      </text>
                      <text x="14" y="63" fill={cor.texto} fontSize="10" opacity="0.6" fontFamily="IBM Plex Mono, monospace">
                        {no.module} · {no.change_type} · risco {no.risk_tier}
                        {no.uncertainty ? " · incerteza" : ""}
                      </text>
                      <title>{no.title}</title>
                    </a>
                  </g>
                );
              })}
            </svg>
          </div>

          <p className="mt-3 text-[12px] text-ink-3">
            Passe o mouse num nó para isolar as ligações dele. Clique para abrir a tarefa. Só as
            ligações por arquivo e manuais seguram o despacho e arrastam a suspensão; tarefas sem
            nada que as segure rodam em paralelo.
          </p>
        </>
      )}
    </PanelShell>
  );
}
