/** Cliente do pase-core usado pelo painel. */

const CORE_URL = process.env.NEXT_PUBLIC_CORE_URL ?? "http://localhost:8000";

export interface ZonePayloadRow {
  id: number;
  user_id: number;
  slot: string;
  payload: Record<string, unknown>;
  origin: "autonoma" | "injetado";
  status: "ativo" | "revogado";
  created_at: string;
}

export interface ZoneViolationRow {
  id: number;
  user_id: number;
  slot: string;
  reason: string;
  raw_payload: Record<string, unknown> | null;
  at: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(`${CORE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!resposta.ok) {
    const corpo = await resposta.text();
    throw new Error(`${resposta.status}: ${corpo}`);
  }
  return resposta.status === 204 ? (undefined as T) : ((await resposta.json()) as T);
}

export interface ZoneInfo {
  slot: string;
  tela: string;
  modulo: string;
  finalidade: string;
  observa: string;
  acessos_minimos: number;
}

/** Uma avaliação de zona: o que o agente viu, o que decidiu e por quê. */
export interface ZoneEvaluationRow {
  id: number;
  user_id: number;
  slot: string;
  resultado: string;
  decisao: boolean | null;
  motivo: string | null;
  sinais: string | null;
  pedido: string | null;
  payload_id: number | null;
  violation_id: number | null;
  trace_id: string | null;
  at: string;
}

export const core = {
  payloads: () => request<ZonePayloadRow[]>("/api/upa/payloads"),
  violations: () => request<ZoneViolationRow[]>("/api/upa/violations"),

  revoke: (id: number) => request<unknown>(`/api/upa/payloads/${id}/revoke`, { method: "POST" }),

  zones: () => request<ZoneInfo[]>("/api/upa/zones"),

  evaluations: () => request<ZoneEvaluationRow[]>("/api/upa/evaluations"),

  simulate: (userId: number, slot: string) =>
    request<{ personalizado: boolean; payload: unknown }>("/api/upa/simulate", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, scenario: "ana_relatorios", slot }),
    }),

  injectRaw: (userId: number, slot: string, payload: unknown) =>
    request<{ payload_id: number; core_o_recusaria: boolean; erros_do_core: string[] }>(
      "/api/upa/inject-raw",
      { method: "POST", body: JSON.stringify({ user_id: userId, slot, payload }) },
    ),
};

export function formatarData(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "há 5 min", "há 3 h", "ontem" - para listas, onde a data exata é ruído. */
export function haQuantoTempo(iso: string): string {
  const segundos = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (segundos < 60) return "agora";
  const minutos = Math.floor(segundos / 60);
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `há ${horas} h`;
  const dias = Math.floor(horas / 24);
  if (dias === 1) return "ontem";
  if (dias < 30) return `há ${dias} dias`;
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

export function milhar(n: number): string {
  return n.toLocaleString("pt-BR");
}

// --------------------------------------------------------------------------- //
// Tarefas, descartes e incidentes (SPEC-06 §2, §3 e §4)
// --------------------------------------------------------------------------- //

export interface TaskRow {
  id: number;
  title: string;
  status: string;
  module: string;
  output_type: string;
  impact: number;
  complexity: number;
  confidence: number;
  uncertainty: boolean;
  risk_tier: "baixo" | "medio" | "alto";
  urgency_score: number;
  alert: "none" | "retries" | "budget" | "merge_conflict" | "ci_develop";
  waiting_on_task_id: number | null;
  final_outcome: string | null;
  priority_score: number;
  change_type: string;
  branch_name: string | null;
  merge_commit: string | null;
  pr_url: string | null;
  budget_cap_tokens: number | null;
  parent_task_id: number | null;
  stage: "develop" | "release" | "producao" | null;
  release_id: number | null;
  tested_ok: boolean;
  plan_approval_required: boolean;
  archived_at: string | null;
  updated_at: string;
}

export interface RunRow {
  id: number;
  attempt: number;
  trigger: string;
  status: string;
  failure_reason: string | null;
  deviation_files: string[];
  tokens_real: number;
  duration_ms: number;
  created_at: string;
  review: Parecer | null;
}

export interface Citacao {
  arquivo: string;
  trecho: string;
}

export interface CriterioRevisado {
  id: string;
  criterio: string;
  atendido: boolean;
  explicacao: string;
  evidencia: Citacao | null;
  teste: Citacao | null;
  verificacao_manual: string | null;
  /** Por que o código anulou o "atendido" do revisor, quando anulou. */
  anulado_por: string | null;
}

export interface Parecer {
  aprovado: boolean;
  criterios: CriterioRevisado[];
  colaterais: { arquivo?: string; trecho?: string; motivo?: string }[];
  /** Colaterais cosméticos: não reprovam, vão para quem homologa ver. */
  avisos?: { arquivo?: string; trecho?: string; motivo?: string }[];
  resumo: string;
  modelo: string;
  /** Quem escreveu o código - para mostrar se o revisor foi de fato outro modelo. */
  modelo_do_codigo?: string;
  mesmo_modelo?: boolean;
}

export interface CriterioDeAceite {
  id: string;
  criterio: string;
  como_verificar: string;
}

export type AcaoNoArquivo = "modificar" | "criar" | "excluir";

export interface Plano {
  acceptance_criteria: CriterioDeAceite[];
  affected_files: string[];
  roadmap: string;
  tokens_estimated: number;
  /** Mapeamento de impacto: caminho → ação. Ausente vale `modificar`. */
  file_actions?: Record<string, AcaoNoArquivo>;
  minutes_estimated?: number | null;
  technical_risk?: "baixo" | "medio" | "alto" | null;
  technical_risk_reason?: string | null;
}

export interface Orcamento {
  teto: number;
  gasto: number;
  restante: number;
  manual: boolean;
}

export interface TaskDetail {
  task: TaskRow;
  orcamento: Orcamento;
  description: string;
  branch_name: string | null;
  parent_task_id: number | null;
  redo_feedback: string | null;
  plan_approval_required: boolean;
  plan_approved: boolean;
  tested_note: string | null;
  archive_note: string | null;
  history: Transicao[];
  planning: Plano | null;
  runs: RunRow[];
}

export interface Transicao {
  from: string | null;
  to: string;
  note: string | null;
  at: string;
}

export interface EntregaTarefa {
  id: number;
  title: string;
  module: string;
  change_type: string;
  risk_tier: string;
  branch: string | null;
  stage: "develop" | "release" | "producao" | null;
  tested_ok: boolean;
  tested_note: string | null;
  release_id: number | null;
  merge_commit: string | null;
  alert: string;
  updated_at: string;
}

export interface ReleaseRow {
  id: number;
  version: string;
  branch: string;
  status: "aberta" | "validando" | "validada" | "pr_aberto" | "publicada" | "cancelada";
  changelog: string;
  validation_ok: boolean | null;
  pr_number: number | null;
  pr_url: string | null;
  pr_body: string | null;
  approval_note: string | null;
  tag: string | null;
  publish_commit: string | null;
  created_at: string;
  published_at: string | null;
  tasks: EntregaTarefa[];
}

export interface EventoDePipeline {
  id: number;
  branch: string;
  kind: string;
  ok: boolean;
  task_id: number | null;
  release_id: number | null;
  commit: string | null;
  detail: string;
  at: string;
}

export interface Entrega {
  principal: string;
  versao_atual: string | null;
  versao_sugerida: string;
  github: boolean;
  develop: {
    tarefas: EntregaTarefa[];
    ultimo_ci: { ok: boolean; at: string; detail: string } | null;
  };
  releases: ReleaseRow[];
  eventos: EventoDePipeline[];
  regras: { origem: string; destino: string; metodo: string }[];
}

export interface DiscardRow {
  id: number;
  reason_type: "duplicata" | "incoerente" | "recusa_humana";
  reason_text: string;
  matched_ref: string | null;
  duplicate_count: number;
  task_id: number | null;
  title: string | null;
  origin: string | null;
  created_at: string;
}

export interface IncidentRow {
  id: number;
  title: string;
  description: string;
  severity: "baixo" | "medio" | "alto";
  module: string | null;
  source: string;
  resolved: boolean;
  created_at: string;
}

export interface DocumentoResumo {
  slug: string;
  folder: string | null;
  title: string;
  version: number;
  updated_by: string;
  updated_at: string;
  chars: number;
}

export interface DocumentoCompleto extends DocumentoResumo {
  content: string;
  readers: { key: string; etapa: string; prompts: string[] }[];
}

export interface LeituraDeContexto {
  key: string;
  etapa: string;
  descricao: string;
  prompts: string[];
  documentos: string[];
  chars: number;
}

export interface VersaoDeDocumento {
  version: number;
  note: string;
  author: string;
  created_at: string;
  chars: number;
}

export interface SugestaoDeContexto {
  id: number;
  task_id: number | null;
  slug: string;
  base_version: number;
  summary: string;
  reasoning: string;
  diff: string;
  created_at: string;
}

export interface PropostaDeContexto {
  aplicavel: boolean;
  reasoning: string;
  summary: string;
  content: string;
  diff: string;
}

export interface GraphNode {
  id: number;
  title: string;
  status: string;
  final_outcome: string | null;
  module: string;
  risk_tier: "baixo" | "medio" | "alto";
  change_type: string;
  alert: string;
  uncertainty: boolean;
  priority_score: number;
}

export interface GraphEdge {
  from: number;
  to: number;
  kind: "arquivo" | "semantica" | "manual";
  reason: string | null;
}

export interface Grafo {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Verbete {
  termo: string;
  significado: string;
  quem_atribui: string;
  efeito: string;
}

export interface MemoriaTipo {
  kind: string;
  tabela: string;
  total: number;
  com_embedding: number;
  sem_embedding: number;
}

export interface Envelope {
  proposal_id: number | null;
  outcome: string;
  detail: string;
  task_id: number | null;
}

export const pase = {
  tasks: (status?: string) =>
    request<TaskRow[]>(`/api/tasks${status ? `?status=${status}` : ""}`),
  task: (id: number) => request<TaskDetail>(`/api/tasks/${id}`),
  archivedTasks: () => request<TaskRow[]>("/api/tasks?archived=true"),
  archive: (id: number, reason?: string) =>
    request<unknown>(`/api/tasks/${id}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  unarchive: (id: number) => request<unknown>(`/api/tasks/${id}/unarchive`, { method: "POST" }),
  discards: () => request<DiscardRow[]>("/api/discards"),
  /** `{task_id: pedidos}` das tarefas cuja proposta reúne mais de um pedido. */
  occurrences: () => request<Record<string, number>>("/api/proposals/occurrences"),
  incidents: () => request<IncidentRow[]>("/api/incidents"),
  context: () =>
    request<{ documentos: DocumentoResumo[]; leituras: LeituraDeContexto[] }>("/api/context"),
  contextSuggestions: () => request<SugestaoDeContexto[]>("/api/context/suggestions"),
  acceptSuggestion: (id: number) =>
    request<unknown>(`/api/context/suggestions/${id}/accept`, { method: "POST" }),
  dismissSuggestion: (id: number) =>
    request<unknown>(`/api/context/suggestions/${id}/dismiss`, { method: "POST" }),
  contextDoc: (slug: string) => request<DocumentoCompleto>(`/api/context/doc/${slug}`),
  contextHistory: (slug: string) =>
    request<VersaoDeDocumento[]>(`/api/context/doc/${slug}/history`),
  contextVersion: (slug: string, version: number) =>
    request<{ version: number; content: string; note: string }>(
      `/api/context/doc/${slug}/version/${version}`,
    ),
  saveContextDoc: (slug: string, content: string, note: string) =>
    request<DocumentoResumo & { salvo: boolean; diff: string }>(`/api/context/doc/${slug}`, {
      method: "PUT",
      body: JSON.stringify({ content, note }),
    }),
  restoreContextDoc: (slug: string, version: number) =>
    request<unknown>(`/api/context/doc/${slug}/restore`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  proposeContextDoc: (slug: string, pedido: string) =>
    request<PropostaDeContexto>(`/api/context/doc/${slug}/propose`, {
      method: "POST",
      body: JSON.stringify({ request: pedido }),
    }),
  createContextDoc: (slug: string, content: string) =>
    request<DocumentoResumo>("/api/context", {
      method: "POST",
      body: JSON.stringify({ slug, content }),
    }),
  graph: () => request<Grafo>("/api/graph"),
  glossary: () => request<{ grupos: Record<string, Verbete[]> }>("/api/system/glossary"),
  systemPrompts: () => request<{ prompts: Record<string, unknown>[]; pasta: string }>(
    "/api/system/prompts",
  ),
  systemMemory: () =>
    request<{ tipos: MemoriaTipo[]; modelo: string; dimensoes: number; limiar_de_similaridade: number }>(
      "/api/system/memory",
    ),
  promptSource: async (id: string) => {
    const r = await fetch(`${CORE_URL}/api/system/prompts/${id}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    return r.text();
  },
  systemCost: () => request<Record<string, unknown>>("/api/system/cost"),
  systemHealth: () => request<Record<string, unknown>>("/api/system/health"),
  /** Última rodada de cada loop de manutenção (Auditoria P10, Reavaliação P9). */
  jobs: () =>
    request<
      Record<
        "auditoria" | "reavaliacao",
        {
          job: string;
          nome: string;
          rodando: boolean;
          iniciado_em: string | null;
          terminado_em: string | null;
          resultado: Record<string, unknown> | null;
          erro: string | null;
        }
      >
    >("/api/jobs"),
  runJob: (job: "auditoria" | "reavaliacao") =>
    request<{ job: string; status: string; detail: string }>(`/api/jobs/${job}`, {
      method: "POST",
    }),
  linkTasks: (id: number, dependsOn: number, reason?: string) =>
    request<unknown>(`/api/tasks/${id}/dependencies`, {
      method: "POST",
      body: JSON.stringify({ depends_on: dependsOn, reason }),
    }),
  unlinkTasks: (id: number, dependsOn: number) =>
    request<unknown>(`/api/tasks/${id}/dependencies/${dependsOn}`, { method: "DELETE" }),
  editTask: (id: number, campos: Record<string, unknown>) =>
    request<unknown>(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(campos) }),
  replan: (id: number) => request<unknown>(`/api/tasks/${id}/replan`, { method: "POST" }),
  cancelTask: (id: number, reason: string, remember = true) =>
    request<unknown>(`/api/tasks/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason, remember }),
    }),
  redo: (id: number, feedback: string) =>
    request<{ task_id: number; parent_task_id: number; status: string }>(
      `/api/tasks/${id}/redo`,
      { method: "POST", body: JSON.stringify({ feedback }) },
    ),
  revert: (id: number, reason: string) =>
    request<unknown>(`/api/tasks/${id}/revert`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  approve: (id: number, revisarPlano?: boolean) =>
    request<{ plan_approval_required: boolean }>(`/api/tasks/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(revisarPlano === undefined ? {} : { review_plan: revisarPlano }),
    }),
  approvePlan: (id: number, comment?: string) =>
    request<unknown>(`/api/tasks/${id}/plan/approve`, {
      method: "POST",
      body: JSON.stringify({ comment: comment ?? null }),
    }),
  revisePlan: (id: number, feedback: string) =>
    request<unknown>(`/api/tasks/${id}/plan/revise`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  editPlan: (
    id: number,
    campos: { acceptance_criteria?: { id?: string; criterio: string; como_verificar?: string }[]; affected_files?: string[]; roadmap?: string },
  ) => request<unknown>(`/api/tasks/${id}/plan`, { method: "PATCH", body: JSON.stringify(campos) }),

  delivery: () => request<Entrega>("/api/delivery"),
  testApprove: (taskId: number, note: string) =>
    request<unknown>(`/api/delivery/tasks/${taskId}/test-approve`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
  createRelease: (version?: string) =>
    request<ReleaseRow>("/api/delivery/releases", {
      method: "POST",
      body: JSON.stringify({ version: version ?? null }),
    }),
  includeInRelease: (releaseId: number, taskId: number) =>
    request<{ incluida: boolean; detail?: string }>(
      `/api/delivery/releases/${releaseId}/tasks`,
      { method: "POST", body: JSON.stringify({ task_id: taskId }) },
    ),
  removeFromRelease: (releaseId: number, taskId: number) =>
    request<unknown>(`/api/delivery/releases/${releaseId}/tasks/${taskId}`, {
      method: "DELETE",
    }),
  editChangelog: (releaseId: number, changelog: string) =>
    request<unknown>(`/api/delivery/releases/${releaseId}/changelog`, {
      method: "PUT",
      body: JSON.stringify({ changelog }),
    }),
  validateRelease: (releaseId: number) =>
    request<unknown>(`/api/delivery/releases/${releaseId}/validate`, { method: "POST" }),
  openPullRequest: (releaseId: number) =>
    request<unknown>(`/api/delivery/releases/${releaseId}/pull-request`, { method: "POST" }),
  publishRelease: (releaseId: number, note: string) =>
    request<{ publicada: boolean; detail?: string }>(
      `/api/delivery/releases/${releaseId}/publish`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),
  cancelRelease: (releaseId: number, note: string) =>
    request<unknown>(`/api/delivery/releases/${releaseId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
  reject: (id: number, reason: string) =>
    request<unknown>(`/api/tasks/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  resume: (id: number, instruction?: string, updatePlan = true) =>
    request<unknown>(`/api/tasks/${id}/resume`, {
      method: "POST",
      body: JSON.stringify({ instruction: instruction || null, update_plan: updatePlan }),
    }),
  homologate: (id: number, decision: string, comment: string | null) =>
    request<unknown>(`/api/tasks/${id}/homologation`, {
      method: "POST",
      body: JSON.stringify({ decision, comment }),
    }),

  createIncident: (body: {
    title: string;
    description: string;
    severity: string;
    module: string | null;
  }) => request<unknown>("/api/incidents", { method: "POST", body: JSON.stringify(body) }),

  proposeInternal: (type: string, author: string, text: string) =>
    request<Envelope>("/api/proposals/internal", {
      method: "POST",
      body: JSON.stringify({ type, author, text }),
    }),
  proposeAI: (mode: string) =>
    request<Envelope>("/api/proposals/ai-generate", {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),

  artifact: (runId: number, tipo: "diff" | "logs" | "transcript" | "review") =>
    fetch(`${CORE_URL}/api/runs/${runId}/artifact/${tipo}`, { cache: "no-store" }).then((r) =>
      r.ok ? r.text() : Promise.reject(new Error(`${r.status}`)),
    ),
};

export const CORE = CORE_URL;
