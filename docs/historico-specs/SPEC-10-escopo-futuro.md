# SPEC-10 - Escopo Futuro (fora da base, por decisão, não por esquecimento)

Ver a tabela na resposta de acompanhamento para a checklist completa com prioridade e esforço estimado. Este arquivo é a versão que vive no repo, para o agente Claude Code nunca implementar nada daqui sem instrução explícita.

## Itens do próprio modelo PASE ainda não implementados nesta base

- **Sub-DAGs**: decomposição de tarefas complexas em subgrafos com falha isolada.
- **Replanejamento automático de tarefas dependentes** quando uma predecessora muda de escopo.
- **Prospecção Competitiva** via web scraping de concorrentes.
- **Zonas Dinâmicas Sob Demanda** (usuário como co-criador via linguagem natural).
- **Event Bus entre zonas** (comunicação cross-zone).
- **Fluxos declarativos completos** (zona controlando uma máquina de estados multi-tela, não só um widget).
- **Múltiplas zonas simultâneas** (a base tem uma só, `resumo_financeiro`).
- **RBAC real** para a Etapa de Autorização das Sugestões de Engenharia (hoje é uma lista fixa em env).
- **SLA e decaimento temporal** no Fator de Urgência (hoje é soma simples por severidade).
- **Integração real com Sentry** para incidentes (hoje é inserção manual no painel).

## Itens de infraestrutura/SDLC mencionados na conversa mas não incluídos na base

- **Alembic** (migrações versionadas) - a base usa `create_all` no boot.
- **GitHub Actions / CI real** - a base valida localmente dentro do container do Executor, sem pipeline de CI separado.
- **PR real no GitHub** - a base faz merge local via GitPython, sem abrir PR em um repositório remoto.
- **Langfuse** (observabilidade de LLM) - a base loga via `common/llm_client.py` em banco/log estruturado, sem dashboard dedicado.
- **Autenticação e multi-tenancy** - a base usa seleção de persona sem login real.
- **Deploy real / ambiente de produção separado** - a base usa hot reload como "deploy".
- **LangGraph como dependência formal** - a base encadeia chamadas Python diretas ao `llm_client` (ver SPEC-08 §2, nota de rodapé).
- **Normalização de áudio** como origem de captação ativa.
- **Zona Dinâmica com múltiplos widgets simultâneos por slot** ou catálogo maior que 3 widgets.
- **Testes de carga / múltiplos usuários simultâneos** no Executor (paralelismo real de tarefas).

## Por que ficaram de fora

Cada item acima exige esforço não trivial e nenhum é necessário para provar que as três camadas do modelo funcionam de ponta a ponta com rastreabilidade e gates humanos - que é o que a defesa precisa demonstrar. Adicionar qualquer um deles antes da base estar 100% funcional (8 demos verdes) é risco puro para o prazo de três meses.
