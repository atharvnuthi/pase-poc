# SPEC-08 - Contrato do `llm_client` e Mapeamento com o SDLC

## 1. `llm_client` (módulo comum)

```python
chat(messages, *, json_schema=None, temperature=0.2, model=None, tags={}) -> (content, usage)
# loga tokens com tags {task_id?, proposal_id?, prompt_id, fase}
# model=None usa LLM_MODEL do env; passar LLM_MODEL_EXPLORATORY explicitamente para P3

embed(text) -> list[float]
# dimensão EMBEDDING_DIM
```

Saídas JSON: parse estrito; 1 retentativa automática com mensagem de correção em caso de JSON inválido. Se a retentativa também falhar, a chamada levanta exceção - quem chamou decide o que fazer (normalmente: descartar a proposta com um motivo técnico, nunca travar o pipeline).

Toda chamada registra `trace_id` (gerado por chamada) para permitir religar qualquer decisão do sistema à conversa exata que a produziu - é o que SPEC-00 chama de rastreabilidade integral.

## 2. Onde cada estágio do SDLC vive no PASE

Esta tabela existe para deixar explícito, para quem ler a monografia, que o PASE não é um apêndice do SDLC - ele *é* uma implementação do SDLC, com a IA fazendo o trabalho mecânico e o humano nos pontos de decisão.

| Estágio SDLC | Componente PASE | Gate humano | Artefato produzido | Ferramenta |
|---|---|---|---|---|
| Requisitos | Task Layer completo (SPEC-03) | Aprovar tarefa candidata | `tasks` (status=candidata) | Postgres + pgvector |
| Design | Execução, Fase de Planejamento (SPEC-04 §4.1) | Implícito: humano vê o plano na Homologação se pedir ajuste | `planning_documents` | LangGraph* |
| Implementação | Execução, Fase de Execução (SPEC-04 §6) | Nenhum durante a escrita - verificação automática primeiro | `execution_runs` + diff | Docker + Claude Code (headless) |
| Testes | Ciclo de correção local (SPEC-04 §6.5-6.6) | Automático (bloqueia antes do humano ver) | `lint_test.log` | ruff, eslint, tsc, pytest |
| Deploy | Homologação (SPEC-04 §5) | Aprovar merge | commit na main, `implemented_items` | Git (merge local) |
| Manutenção | Ciclo de Auditoria (SPEC-04 §8) | Aprovar tarefas geradas pela auditoria (mesmo fluxo de sempre) | `proposals(origin=auditoria)` | job periódico |
| Monitoramento | Captação Passiva (SPEC-03 §2), Incidentes (SPEC-04 §2) | Nenhum na captação; aprovar task se virar candidata | `proposals(origin=passiva)`, `incidents` | tickets do client-backend |

\* Nesta PoC, "LangGraph" descreve a orquestração dos nós de prompt (P1 → P1b → L1 → P2a → P2b), não necessariamente uma dependência de biblioteca obrigatória - ver SPEC-10 sobre a decisão em aberto de usar LangGraph de fato vs. funções Python encadeadas simples. Para o TCC, a Fase de Planejamento e a Fase de Execução podem ser implementadas como chamadas sequenciais diretas ao `llm_client`, o que é mais simples de depurar e suficiente para provar o modelo; adotar LangGraph formalmente é uma melhoria de engenharia, não uma exigência do modelo PASE em si.

## 3. Boas práticas do AI-Native SDLC Playbook aplicadas neste projeto

O curso da Claude Academy (academy.claude.com/courses/ai-native-sdlc-playbook) descreve práticas para equipes usando Claude Code no dia a dia. As que se aplicam diretamente aqui:

- **Todo estágio termina committando um artefato versionado que o próximo estágio lê.** É exatamente a cadeia `proposals → tasks → planning_documents → execution_runs → implemented_items` já definida no SPEC-00 Seção 2. Não é um adendo, é a mesma ideia com nomes diferentes.
- **CLAUDE.md como memória institucional**, lido no início de toda sessão, atualizado quando um erro se repete. Ver `CLAUDE.md` na raiz do repo.
- **Plan mode antes de código.** A Fase de Planejamento (SPEC-04 §4.1) é exatamente isso - nunca se escreve código sem um plano registrado e, se rejeitado, revisável primeiro.
- **Verificação em contexto isolado antes do humano.** SPEC-00 Seção 5 - lint e testes rodam antes de qualquer artefato chegar à Homologação.
- **Hooks como gate determinístico**, não como sugestão. O guardrail de budget e o limite de retries (SPEC-04 §6-7) são exatamente isso: código que impede uma ação, não um prompt pedindo cautela ao modelo.
- **Prompts versionados fora do código**, um arquivo por prompt. Já é a convenção do CLAUDE.md.

## 4. Critério de aceite

1. `llm_client.chat` loga `trace_id`, `tokens_in`, `tokens_out`, `tags` em toda chamada, verificável via `SELECT` simples ou log estruturado.
2. Retentativa automática de JSON inválido testada com um mock que retorna JSON quebrado na primeira chamada e válido na segunda.
