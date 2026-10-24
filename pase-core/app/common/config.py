"""Settings do pase-core, lidas do ambiente (SPEC-01 §6).

Fonte única de configuração: nenhum módulo deve ler os.environ diretamente.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["anthropic", "openai", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    llm_provider: Provider = "mock"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    # usado apenas pelo P3 (Geração Exploratória), temperatura 0.9 - ver SPEC-01 §4
    llm_model_exploratory: str = "claude-sonnet-4-6"

    # --- Modelos do Executor ---
    # O funil classifica texto curto: modelo pequeno basta e a temperatura importa
    # (o P3 depende dela). Escrever e revisar código é outro trabalho. Medido na
    # tarefa #4: com o modelo do funil, a entrega passou em todos os gates e não
    # fazia nada - o botão existia, a paleta escura não.
    #
    # Vazio = usa `llm_model`, para que um ambiente sem estes campos continue
    # funcionando exatamente como antes.
    llm_model_code: str = ""
    llm_model_review: str = ""
    # Esforço de raciocínio por etapa. Planejar e revisar decidem o que vale; a
    # geração é a chamada maior e se repete no ciclo de correção.
    reasoning_effort_planning: str = "high"
    reasoning_effort_code: str = "medium"
    reasoning_effort_review: str = "high"

    # --- Embeddings ---
    embedding_provider: Provider = "openai"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- Infra ---
    database_url: str = "postgresql+psycopg://pase:pase@db:5432/pase"
    # A Captação Passiva lê GET /tickets do FinTrack; dentro da rede do compose
    # o host é o nome do serviço, não localhost.
    client_api_url: str = "http://client-backend:8001"
    db_connect_timeout: int = 5  # segundos; evita processo pendurado com banco fora do ar
    repo_path: str = "/workspace/repo"
    artifacts_path: str = "/data/artifacts"

    # --- Guardrails do modelo (SPEC-00 §4) ---
    similarity_threshold: float = 0.85
    #: Similaridade mínima entre as propostas de duas tarefas abertas para ligá-las
    #: por uma aresta semântica no grafo (§4.4.2). Abaixo do limiar de duplicata
    #: (0.72 calibrado): acima dele a segunda demanda nem teria virado tarefa.
    #: Os negativos medidos ficaram em ≤0.65; 0.60 aceita alguns falsos positivos,
    #: e pode, porque a aresta semântica não bloqueia nada - só informa.
    semantic_dependency_threshold: float = 0.60
    budget_tolerance: float = 0.3
    # Piso do teto de custo. Medido: o P4 estimou 1200 tokens para uma execução cujo
    # prompt sozinho tem ~8800 - a estimativa do modelo erra por ordem de grandeza e,
    # sem piso, o guardrail barra toda tarefa honesta em vez de barrar loop desgovernado.
    # 60k cobre uma execução completa deste alvo (1 geração + 2 correções) com folga.
    # Subiu no SPEC-11 §7: com os dois alvos no contexto, cada chamada do P5 leva
    # ~20.700 tokens em vez de ~8.900. O piso antigo estourava na primeira execução honesta.
    # Subiu de novo com os modelos de raciocínio: o "pensar" é cobrado como saída,
    # a chamada de geração passou de ~37k, e entrou a revisão independente (P12),
    # que lê o diff inteiro. Com 150k, a tarefa #3 parou sem folga para uma chamada.
    budget_min_tokens: int = 800_000
    max_retries: int = 1
    # Duas correções não bastavam: a revisão independente devolve trabalho que os
    # gates mecânicos não pegam, e cada devolução consome uma rodada.
    #: Riscos que exigem aprovação do plano antes de qualquer código. Quem aprova a
    #: candidata pode ligar ou desligar isto por tarefa; este é o padrão.
    plan_approval_tiers: str = "medio,alto"
    #: Roda lint, tipos, testes e build na develop e na release depois de cada
    #: integração. É o "pipeline" do guia; desligar só faz sentido em teste.
    delivery_ci_enabled: bool = True
    #: Depois de aprovar uma tarefa, o P11 sugere atualizações dos documentos de contexto.
    #: Custa uma chamada por documento consultado; desligue para não gastar.
    context_suggestions_enabled: bool = True
    #: Intervalo mínimo entre duas avaliações da mesma zona para a mesma pessoa. Sem ele, uma
    #: zona que o modelo recusa seria reavaliada, e paga, a cada visita.
    zone_reevaluation_hours: int = 24
    max_local_fix: int = 4
    coherence_max_adjustments: int = 2

    # --- GitHub (Fase 5; desligado sem token) ---
    # Vazio de propósito: com token, o Executor passa a abrir PR de verdade e a
    # Homologação mergeia pelo PR. Sem ele, tudo segue local, como sempre foi.
    github_token: str = ""
    github_repo: str = ""  # "dono/repositorio"

    demo_mode: bool = True

    # Autores com papel para abrir Sugestão de Engenharia (SPEC-03 §4).
    # Lista fixa em env nesta fase; RBAC real está no SPEC-10.
    engineering_authors: str = "PASE Audit"

    # CORS: PoC local, sem autenticação (ver CLAUDE.md)
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:3001",
    )

    @property
    def planos_que_exigem_aprovacao(self) -> set[str]:
        return {t.strip() for t in self.plan_approval_tiers.split(",") if t.strip()}


    @property
    def modelo_de_codigo(self) -> str:
        """Quem planeja e escreve: P4 e P5."""
        return self.llm_model_code or self.llm_model

    @property
    def modelo_de_revisao(self) -> str:
        """Quem revisa: P12. Diferente de quem escreveu, de propósito.

        Um revisor do mesmo modelo que implementou tende a ter os mesmos pontos
        cegos - foi assim que testes escritos para a própria implementação
        aprovaram um modo escuro sem paleta escura.
        """
        return self.llm_model_review or self.modelo_de_codigo

    @property
    def authorized_authors(self) -> set[str]:
        return {name.strip() for name in self.engineering_authors.split(",") if name.strip()}

    @property
    def embedding_key(self) -> str:
        """Chave do provider de embeddings, com fallback para a chave de chat."""
        if self.embedding_api_key:
            return self.embedding_api_key
        if self.embedding_provider == self.llm_provider:
            return self.llm_api_key
        return ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
