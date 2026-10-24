# Histórico - as especificações originais

**Estes documentos não descrevem o sistema atual.** Eles descrevem o que foi *planejado*
antes de a primeira linha ser escrita. A documentação em vigor está um nível acima:

| Para saber | Leia |
|---|---|
| o que existe hoje, e o que não existe | [`../STATUS.md`](../STATUS.md) |
| o que o sistema faz | [`../features.md`](../features.md) |
| como está montado | [`../architecture-and-design.md`](../architecture-and-design.md) |
| o que ele deliberadamente não faz | [`../scope-and-constraints.md`](../scope-and-constraints.md) |
| tabelas e colunas | [`../database.md`](../database.md) |
| as duas interfaces | [`../ui-ux.md`](../ui-ux.md) |

## Por que ficaram no repositório

Por duas razões, nenhuma delas nostalgia.

A primeira é que a monografia argumenta sobre um método - planejar por escrito antes de
escrever código, e só implementar o que está especificado. Estes doze arquivos são a
evidência de que o método foi seguido, com data e histórico de commit.

A segunda é mais interessante: **a distância entre o que está aqui e o que está em
`STATUS.md` é um resultado do trabalho, não um defeito dele.** Nove decisões mudaram depois
de medir - o limiar de similaridade, o agrupamento de tickets, o veredito de deriva, a
defesa da rede de regressão, o alvo do Executor. Cada uma dessas mudanças só é
demonstrável porque existe o registro do que se acreditava antes.

## O que NÃO fazer com eles

Não implemente nada com base nestes arquivos, e não os cite como descrição do sistema. Onde
eles divergem da documentação em vigor, quem está certo é a documentação em vigor - ela foi
conferida contra o código em execução.

## O que há aqui

| Arquivo | Assunto |
|---|---|
| `SPEC-00-constituicao.md` | as regras que venciam qualquer conflito |
| `SPEC-01-infra.md` | monorepo, compose, módulos comuns |
| `SPEC-02-fintrack.md` | o produto-alvo |
| `SPEC-03-task-layer.md` | captação e funil de filtragem |
| `SPEC-04-orquestracao-execucao.md` | estados, gates, Executor |
| `SPEC-05-upa-zonas.md` | personalização em runtime |
| `SPEC-06-painel-seeds-demos.md` | painel, seeds, demos, métricas |
| `SPEC-07-project-context.md` | o documento de contexto do produto |
| `SPEC-08-llm-client-e-sdlc.md` | contrato do cliente de LLM e mapa do SDLC |
| `SPEC-09-divisao-cronograma.md` | divisão do trabalho e cronograma |
| `SPEC-10-escopo-futuro.md` | o que ficou de fora, e por quê |
| `SPEC-11-alvo-frontend.md` | ampliação do alvo do Executor para o frontend |
