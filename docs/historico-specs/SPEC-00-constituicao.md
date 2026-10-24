# SPEC-00 - Constituição do Projeto

**Papel:** este documento não descreve um componente. Ele define as regras que todo SPEC e toda linha de código devem respeitar. Em caso de conflito entre um SPEC e este documento, este documento vence.

**Baseado em:** modelo PASE (capítulo 3 da monografia) e nas práticas do AI-Native SDLC Playbook (Anthropic, 2026) - artefatos versionados que disparam a etapa seguinte, plan mode antes de código, hooks como gate determinístico antes do humano, verificação em contexto isolado, CLAUDE.md como memória institucional.

## 1. Os três loops do sistema

O PASE opera em três loops concêntricos, e é essencial não confundir os três ao ler qualquer SPEC:

1. **Loop lento - evolução de código:** Task Layer → Orchestration → Execution. Produz mudanças permanentes no código-fonte, sempre com aprovação humana, sempre via PR. Latência: minutos a horas.
2. **Loop rápido - personalização:** UPA preenche propriedades de componentes já existentes e aprovados. Nunca gera código, nunca toca o repositório. Latência: segundos, sem gate humano por padrão (a validação de schema é o gate).
3. **Loop de manutenção - auditoria e reavaliação:** jobs periódicos que revisitam o código já escrito (auditoria) e as propostas já descartadas (reavaliação cíclica), reinjetando trabalho nos loops 1 e 2.

Todo componente novo pertence a exatamente um desses loops. Se não pertencer a nenhum, não faz parte do PASE.

## 2. Artefatos versionados (regra do playbook)

Toda decisão relevante do sistema produz um artefato persistido, nunca apenas um efeito colateral em memória. Isso vale tanto para os humanos quanto para os agentes:

| Estágio | Artefato | Onde vive |
|---|---|---|
| Ideia bruta capturada | `proposals` (linha) | Postgres |
| Ideia qualificada | `tasks` (linha, status=candidata) | Postgres |
| Plano técnico aprovado | `planning_documents` (linha) | Postgres |
| Execução de código | `execution_runs` + diff + transcript | Postgres + filesystem |
| Decisão humana | `task_state_history` (linha) | Postgres |
| Configuração de zona | `zone_payloads` (linha) | Postgres |

Nenhuma decisão do PASE deve existir apenas nos logs. Se não está em uma tabela, não é rastreável, e rastreabilidade integral é um dos quatro princípios do modelo.

## 3. Gate humano é sempre um registro, nunca um bloqueio silencioso

Toda vez que uma tarefa espera aprovação humana, isso é um status explícito na tabela (`candidata`, `em_homologacao`, `suspensa`), nunca um processo travado esperando input. O sistema continua rodando outras tarefas enquanto uma espera.

## 4. Contenção da generatividade

Todo componente que usa um LLM define explicitamente:
- **Onde a imprevisibilidade é permitida** (ex: Geração Exploratória, temperatura alta) e **onde é bloqueada** (ex: geração de payload de zona, sempre validado contra schema rígido antes de persistir).
- **Um limite de tentativas.** Nenhum loop de correção roda indefinidamente. Todo ciclo (correção local do Executor, ajuste de coerência, retry de execução) tem um teto configurável.
- **Um teto de custo.** Todo processo que chama LLM em loop tem um budget guardrail.

## 5. Verificação em duas camadas (regra do playbook)

Antes de qualquer artefato chegar a um humano para aprovação, ele passa por verificação automática (lint, testes, validação de schema). O humano revisa o que já passou pela máquina - nunca é a primeira linha de defesa. Isso vale para código gerado pelo Executor e para payloads gerados pelo UPA.

## 6. Zona Dinâmica nunca executa código arbitrário

Uma Zona Dinâmica é um contrato: um componente nativo pré-testado que aceita propriedades validadas. O LLM nunca escreve o componente em runtime - apenas preenche as propriedades dentro do schema. Qualquer violação de schema cai automaticamente no componente nativo padrão (fallback seguro). Esta regra não tem exceção neste projeto.

## 7. Isolamento do Executor

O código gerado autonomamente nunca é escrito diretamente na branch principal. Todo trabalho do Executor acontece em um ambiente isolado (container), em uma branch própria (`pase/task-{id}`), e só entra na branch principal após aprovação humana explícita na Homologação.

O Executor tem liberdade para tocar arquivos correlacionados além do previsto no plano (não há allowlist rígida de caminho), mas qualquer arquivo fora do previsto deve ser reportado como desvio no pacote de retorno, permitindo que a Orquestração e o humano revisem a diferença entre o planejado e o executado.

## 8. Terminologia canônica (usar em todo lugar, sem sinônimos)

| Termo canônico | Não usar |
|---|---|
| Backlog de Tarefas Candidatas | "backlog de tarefas", "fila de tarefas" |
| Histórico de Descartes | "propostas recusadas", "banco de rejeições" |
| Documento de Planejamento Técnico | "plano", "roadmap" (isolado) |
| Zona Dinâmica | "componente dinâmico", "área customizável" |
| Motor de Filtragem | "pipeline de filtragem", "funil" |

## 9. O que está fora de escopo por decisão de projeto (não por esquecimento)

Ver `docs/specs/SPEC-10-escopo-futuro.md` para a lista completa e justificativa de cada item. Nenhum agente deve implementar algo dessa lista sem instrução explícita, mesmo que pareça uma melhoria óbvia.
