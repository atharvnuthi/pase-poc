# Escopo e Restrições

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

O que este projeto **não** faz, e por quê. Nada nesta página é esquecimento: cada item foi
deixado de fora por decisão, e a decisão está registrada.

Em caso de conflito entre esta página e qualquer outro documento do repositório, esta
vence - exceto quanto ao escopo do *produto*, que vive em
o documento `project-context` (no banco, editável no painel) e é lido pelo próprio sistema em tempo de
execução.

---

## 1. Regras invioláveis

Estas não são preferências. São o que impede o sistema de virar um gerador de código sem
freio, e valem acima de qualquer decisão local.

**1. Rastreabilidade integral.** Toda decisão relevante produz uma linha em tabela. O que
existe só em log não é rastreável, e rastreabilidade é um dos princípios do modelo.

**2. O gate humano é um registro, nunca um bloqueio silencioso.** Tarefa esperando decisão
é um status explícito. Nenhum processo fica travado esperando input, e o sistema continua
trabalhando em outras tarefas.

**3. Contenção da generatividade.** Todo componente que usa LLM declara onde a
imprevisibilidade é permitida e onde é bloqueada, e tem teto de tentativas e teto de custo.
Os tetos são código que impede a ação - nunca um prompt pedindo cautela ao modelo.

**4. Verificação em duas camadas.** Nenhum artefato chega a uma pessoa sem ter passado por
verificação automática. O humano é a última linha de defesa, jamais a primeira.

**5. Uma Zona Dinâmica nunca executa código arbitrário.** Sem exceção neste projeto. O
modelo escolhe um widget de um catálogo fixo e preenche propriedades validadas contra
contrato. Qualquer violação cai no componente nativo.

**6. O Executor trabalha isolado.** Clone próprio, branch própria, e nada entra na branch
principal sem aprovação humana explícita. Ele pode tocar arquivos correlacionados fora do
plano, mas todo desvio é reportado para revisão.

**7. O PASE não se modifica.** O `pase-core` nunca é alvo do Executor.

**8. `client-frontend/dynamic-zones/` é somente leitura para o Executor.** É onde mora a
validação que protege o usuário de payload malicioso - a garantia da regra 5 não pode
depender do julgamento do modelo que ela limita. Verificado por código antes da escrita.

**9. Sem rede dentro do sandbox do Executor**, além do provedor de LLM.

## 2. Restrições da prova de conceito

Decisões conscientes de escopo, coerentes com o objetivo: provar que as três camadas do
modelo funcionam de ponta a ponta com rastreabilidade e gates humanos.

| Restrição | Consequência |
|---|---|
| **Sem autenticação real** | usuário é escolhido por persona; sem login, sem sessão, sem papéis |
| **Ambiente estritamente local** | CORS liberado só para as portas do painel e do app. **Nunca exposto publicamente** - e por isso não se adiciona autenticação "por precaução": ela daria a impressão errada de que o sistema está pronto para exposição |
| **Sem multi-tenancy** | duas personas fixas, um só produto-alvo |
| **Uma Zona Dinâmica por tela** | seis zonas, uma em cada tela do FinTrack; nunca duas na mesma tela |
| **Catálogo de três widgets** | `shortcut_list`, `summary_card`, `alert_banner` |
| **Jobs de manutenção por comando** | sem agendador; rodam quando alguém pede |
| **Merge local** | sem `GITHUB_TOKEN`, o PASE faz o papel do Pull Request da release: mesmas exigências, merge na principal feito localmente. Com o token, o PR é real ([`entrega-no-pase.md`](entrega-no-pase.md)) |
| **Hot reload no lugar de deploy** | um merge aprovado aparece no app rodando; não há pipeline de build |
| **Reset zera o banco** | o esquema é versionado (Alembic), mas `make reset` recomeça do zero e não desfaz código já integrado nas branches |

## 3. Do modelo PASE, ainda não construído

Partes do modelo teórico que a base não implementa:

- **Sub-DAGs** - decompor tarefa complexa em subgrafos com falha isolada.
- **Replanejamento automático** de tarefas dependentes quando uma predecessora muda de
  escopo.
- **Prospecção Competitiva** - captação por observação de concorrentes.
- **Zonas Dinâmicas sob demanda por conversa** - hoje o pedido escrito numa sugestão chega à
  zona que o cobre; um diálogo livre de co-criação continua fora.
- **Event bus entre zonas** e **fluxos declarativos** (uma zona controlando uma máquina de
  estados multi-tela, não só um widget).
- **Várias zonas na mesma tela.** Hoje são seis zonas, mas uma por tela.
- **RBAC real** para autorizar Sugestões de Engenharia - hoje é uma lista fixa em variável
  de ambiente.
- **SLA e decaimento temporal** no fator de urgência - hoje é soma simples por severidade.
- **Integração real de incidentes** - hoje são inseridos pelo painel.

## 4. De infraestrutura, deliberadamente ausente

- **CI real** - a verificação acontece dentro do container do Executor, sem pipeline
  separado.
- **Proteção de branches no remoto** - o guia a recomenda (§9); é configuração do GitHub, fora do código.
- **Observabilidade dedicada de LLM** - as chamadas são registradas em banco e em log
  estruturado, sem painel próprio.
- **Ambiente de produção separado.**
- **LangGraph como dependência formal** - as etapas são funções Python encadeadas, o que é
  mais simples de depurar e suficiente para provar o modelo. Adotá-lo seria melhoria de
  engenharia, não exigência do modelo.
- **Captação por áudio.**
- **Teste de carga e paralelismo real** de execuções.

## 5. Fora de escopo por decisão de **produto**

Diferente das seções acima: isto não é limite técnico, é o que o FinTrack não quer ser. É
a régua que a Coerência Sistêmica aplica, e vive em
o contexto do produto (no banco), porque o sistema o lê em tempo de execução -
editar aquele arquivo muda o julgamento da próxima proposta.

Hoje inclui investimentos e múltiplas moedas, integração bancária real, qualquer forma de
rede social entre usuários, gamificação, e metas de orçamento por categoria.

## 6. Por que nada disso foi feito

Nenhum item acima é necessário para demonstrar que as três camadas funcionam de ponta a
ponta com rastreabilidade e gates humanos - que é o que a defesa precisa mostrar.
Adicionar qualquer um antes de a base estar inteira é risco de prazo sem ganho de
argumento.

## 7. Dívida conhecida

Diferente de "fora de escopo": isto **deveria** funcionar e não funciona. Registrado para
não ser confundido com decisão.

- **Modo escuro no FinTrack.** Uma tarefa foi aprovada e homologada, mas entregou apenas
  dois endpoints de preferência no backend e nenhuma mudança de tela. É o mesmo defeito
  que motivou ampliar o alvo do Executor para o frontend; os tokens de cor já existem, a
  tarefa precisa ser refeita.
- **Recusar uma tarefa não atualiza a memória de curto prazo do funil.** O embedding da
  proposta de origem continua marcado como candidata, então reenviar a mesma demanda volta
  barrada com "já existe uma sugestão equivalente aguardando avaliação" - o que é falso.

## 8. Regra para quem for implementar

Nada listado nas seções 3 e 4 deve ser implementado sem pedido explícito, **mesmo que
pareça uma melhoria óbvia**. A lista existe justamente para que "óbvio" não seja
argumento suficiente.
