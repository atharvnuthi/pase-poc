# SPEC-11 - Ampliação do Alvo do Executor para o client-frontend

**Fase:** F5 · **Depende de:** SPEC-02, SPEC-04, SPEC-05 · **Altera:** SPEC-04 §4.1 e §9

## 1. Por que este SPEC existe

A tarefa #5 ("Permitir edição da data em transações lançadas") percorreu o loop lento inteiro e
foi integrada na branch principal - e o usuário continuou sem conseguir corrigir a data pela tela.

A causa não foi falha de nenhum gate. O `PUT /transactions/{id}` já aceitava o campo `date` desde
o SPEC-02, então não havia o que mudar no backend; o que faltava era o botão de editar na
interface. E o P4 proibia explicitamente o Executor de propor qualquer coisa fora do
`client-backend/`.

O funil aceitou a proposta, o planejamento não registrou que a entrega exigia frontend, o Executor
fez o possível dentro do seu limite, o teste que ele escreveu é legítimo e passou, e o humano
aprovou um diff coerente. **A tarefa saiu pela metade e nenhuma etapa tinha como perceber.**

Este SPEC amplia o alcance do Executor para cobrir a interface - e, na mesma medida, estende a
rede de regressão para cobri-la também.

## 2. O princípio que governa esta mudança

> A verificação automática é o que torna a autonomia aceitável (SPEC-00 §5). Logo, **a rede de
> regressão precisa cobrir tudo que o agente pode tocar.**

Ampliar o alcance sem estender a rede transferiria o gate automático para o humano, invertendo a
ordem que o SPEC-00 §5 estabelece - o humano revisa o que a máquina já verificou, nunca o
contrário. Por isso os dois movimentos são um só SPEC, e a rede vem primeiro na ordem de
implementação.

## 3. Alvos do Executor

| Alvo | Verificação automática | Pode escrever? |
|---|---|---|
| `client-backend/` | `ruff check --fix` + `ruff check` + `pytest` | sim |
| `client-frontend/` | `tsc --noEmit` + `vitest run` | sim, **exceto** `dynamic-zones/` |
| `pase-panel/` | - | não |
| `pase-core/` | - | não. O sistema não se modifica |
| `docs/`, infraestrutura | - | não |

## 4. A fronteira do `dynamic-zones/`

`client-frontend/dynamic-zones/` está **fora do alcance do Executor**, e a proibição é verificada
por código antes do commit: uma run que escreva qualquer arquivo ali é reprovada, com o motivo
registrado na `execution_runs`.

A razão é específica. Essa pasta contém a validação Zod e o SDK `<DynamicZone>` que recusam
payloads maliciosos - é o código que materializa o SPEC-00 §6 ("uma Zona Dinâmica nunca executa
código arbitrário", regra declarada sem exceção), e é o que o D5 demonstra. Um Executor capaz de
reescrever esse arquivo poderia enfraquecer a própria defesa que o sistema afirma ter, seja por
erro, seja por uma proposta construída para isso.

Note a diferença em relação ao SPEC-00 §7, que diz não haver allowlist rígida de caminho: aquilo
vale para arquivos **correlacionados ao trabalho**, e a liberdade é contida pelo registro de
desvios. Aqui não se trata de liberdade de escopo, e sim de uma superfície de segurança que não
deve depender do julgamento do modelo. A fronteira é declarada, é estreita, e é auditável.

## 5. Rede de regressão do frontend

Obrigatória, escrita à mão, nunca pelo PASE - pelo mesmo motivo dos 9 testes do SPEC-02: quem é
medido não escreve a régua.

Stack: **Vitest + Testing Library + jsdom**, com `npm test` no `client-frontend`.

Cobertura mínima exigida:

1. seleção de persona guarda o `userId` e redireciona ao dashboard;
2. dashboard exibe saldo e gastos por categoria vindos do `/summary`;
3. formulário de transação exibe o erro 422 no campo correspondente;
4. exclusão remove a transação da listagem;
5. relatórios agregam os totais por mês corretamente;
6. suporte envia o ticket;
7. `<DynamicZone>` renderiza o conteúdo nativo quando a resposta é 204;
8. `<DynamicZone>` recusa payload fora do contrato, mantém o nativo e reporta a violação.

Os itens 7 e 8 são o D5 convertido em teste automatizado: a partir deste SPEC, a garantia do
SPEC-00 §6 deixa de depender de uma demonstração manual e passa a ser verificada a cada execução.

## 6. Ambiente de verificação

O `pase-core` passa a incluir Node e as dependências do `client-frontend` na imagem, exatamente
como o SPEC-01 §3 já fazia com o `requirements.txt` do `client-backend`: é o Executor quem roda a
verificação do alvo, dentro do próprio container.

## 7. Custo

O contexto enviado a cada chamada do P5 passa de aproximadamente 8.900 para 20.700 tokens, porque
o Executor recebe o código integral dos dois alvos. `BUDGET_MIN_TOKENS` sobe de 60.000 para
**150.000**, cobrindo uma geração, duas correções locais e um retry.

A estimativa do P4 continua sendo apenas artefato de planejamento, nunca teto isolado - pelo
motivo registrado no CLAUDE.md.

## 8. Critérios de aceite

1. `npm test` no `client-frontend` verde, com os 8 comportamentos da Seção 5 cobertos.
2. Uma run que escreva em `dynamic-zones/` é reprovada antes do commit, com motivo registrado.
3. O inventário da rede de regressão detecta remoção de teste tanto em `.py` quanto em `.tsx`.
4. **Ponta a ponta:** a proposta "corrigir a data de uma transação pela tela" é planejada e
   executada com mudança no `client-frontend`, passa em `tsc` e `vitest`, e depois da homologação
   a edição funciona em `localhost:3001/transacoes`.
5. As oito demos do SPEC-06 continuam verdes.

## 9. Fora deste SPEC

Testes de acessibilidade, testes visuais, end-to-end com navegador (Playwright), e o `pase-panel`
como terceiro alvo. O `pase-core` permanece fora do alcance em definitivo: um sistema que reescreve
a si mesmo sairia do escopo do que esta PoC se propõe a demonstrar, e retiraria o significado dos
gates - o código que aplica o gate poderia ser o código alterado.
