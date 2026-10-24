# Sobre este projeto, e o que ele demonstrou

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

---

## 1. A pergunta

Uma IA pode evoluir um software de produção sozinha?

A resposta honesta é: **não sozinha - e essa não é a pergunta certa.** A pergunta útil é
*quanta* autonomia é aceitável, e o que precisa existir para que ela seja aceitável.

O PASE é uma resposta a isso, construída e medida. A tese que ele sustenta cabe numa frase:

> **A autonomia só é aceitável na medida da verificação automática.** Onde a máquina
> consegue provar que não quebrou nada, ela pode agir sem pedir licença. Onde não consegue,
> uma pessoa decide - e a pessoa precisa ver o que a máquina já verificou, senão o gate
> humano vira carimbo.

## 2. O que foi construído

Dois sistemas que não se confundem:

- **PASE** - o motor. Recebe demandas de quatro origens, filtra com IA, prioriza, escreve
  código sob aprovação humana e personaliza a interface em runtime.
- **FinTrack** - um dashboard financeiro pessoal, real e usável. É o *paciente*: o produto
  que o PASE observa e evolui.

O modelo opera em três loops concêntricos:

| Loop | O que faz | Latência | Gate |
|---|---|---|---|
| **Lento** | uma frase vira código mergeado | minutos | aprovação humana, sempre |
| **Rápido** | a interface se adapta a quem usa | segundos | validação de contrato |
| **Manutenção** | audita o código e relê descartes antigos | job | reinjeta nos outros dois |

## 3. O que foi demonstrado

Cada item abaixo foi executado e observado, não apenas implementado.

### Uma frase vira código na branch principal

Uma pessoa escreveu *"lancei uma transação com a data errada e não consigo corrigir pela
tela"*. O sistema normalizou, verificou que não era duplicata, julgou coerente com o
produto, qualificou, esperou aprovação, planejou, escreveu código em um clone isolado,
rodou lint, tipos, testes e build, e parou para a decisão humana. Aprovado, o merge entrou
na branch principal - e a data passou a ser editável na tela.

### A memória barra o que já existe, e diz por quê

Pedir de novo algo já implementado vira `descartada_duplicata` com a referência do item
correspondente. Pedir algo fora do escopo do produto vira `descartada_incoerente` com o
motivo escrito, citando o trecho violado do contexto. Reescrever a mesma ideia com outras
palavras é barrado pela memória de descartes.

### A defesa da personalização segura sozinha

Payloads maliciosos gravados **pulando** a validação do servidor - widget fora do catálogo,
propriedade a mais, link externo, rótulo gigante - são recusados pelo cliente, que cai no
componente nativo e registra a violação. O usuário nunca vê o app quebrado. A garantia de
que uma Zona Dinâmica não executa código arbitrário não depende de boa vontade: ela é
validação em duas camadas, e a decisiva é a do lado de quem renderiza.

### A contenção interrompe de verdade

Duas falhas seguidas levam a tarefa a `suspensa`, sem terceira tentativa. Um teto de tokens
estourado interrompe a execução **antes** da chamada - sem gastar. Não são pedidos de
cautela ao modelo: são código que impede a ação.

---

## 4. O resultado mais interessante: onde o modelo errou

Um projeto que só confirma o que planejou não aprendeu nada. Estas são as decisões que
**mudaram depois de medir** - e são, provavelmente, a contribuição mais forte do trabalho.

### O padrão que se repetiu doze vezes

Toda vez que uma garantia foi escrita como instrução no prompt, ela falhou. Toda vez que
virou código que impede, funcionou.

| O que se pediu ao modelo | O que aconteceu | O que resolveu |
|---|---|---|
| "não altere os testes existentes" | sobrescreveu um teste, e a verificação passou porque rodou a suíte adulterada | inventário tirado do clone intacto, conferido por código |
| "acrescente testes para o comportamento novo" | não acrescentou, por muitas execuções | o inventário tem de crescer, ou a run é reprovada |
| "isto ainda consta no documento?" | confabulou: leu a citação dentro do próprio texto sob julgamento | o modelo aponta a evidência, o código confere se ela existe |
| "não toque na validação das zonas" | - | caminho protegido, verificado antes de o arquivo tocar o disco |

A generalização: **uma regra que o agente pode desobedecer sem consequência não é uma
regra.** É uma sugestão com aparência de regra, e a aparência é pior que a ausência, porque
gera confiança sem base.

### Verificação que não verifica

Uma entrega de modo escuro passou por `ruff`, `pytest`, `tsc` e catorze testes de
interface, todos com saída zero. Foi homologada, mergeada - e quebrou o aplicativo inteiro
na primeira tela que alguém abriu.

O motivo: `tsc` não conhece a fronteira de componentes do Next, e os testes renderizam
páginas sem passar pelo roteador, de modo que o arquivo que quebrou não era coberto por
nenhum deles. Quem pegava era `next build`, que não estava no gate.

A lição não é sobre Next: **uma rede de verificação tem exatamente o tamanho do que ela
executa.** Somar ferramentas não amplia a cobertura; executar caminhos diferentes amplia.

### Números que contradizem a intuição

- **O limiar de similaridade de 0,85**, escolhido por parecer razoável, ficava acima de
  *todos* os positivos medidos. Com ele, a memória nunca barraria nada. O valor real,
  medido, é 0,72.
- **Embeddings não separam tema em texto curto e coloquial.** Tickets sobre a mesma dor
  ficaram entre 0,47 e 0,61 - *abaixo* de pares sobre temas diferentes. Agrupar tickets
  passou a ser trabalho de um prompt, não de distância vetorial.
- **A estimativa de custo do modelo erra por ordem de grandeza.** Estimou 1.200 tokens para
  uma tarefa que consumiu 114.000. Serve como artefato de planejamento; nunca como teto.

### O custo de não poder desfazer

Quando a entrega de modo escuro quebrou o app, reverter o merge à mão consertou o código -
mas **não o sistema**: a tarefa seguia `aprovada` e o item seguia na memória de
implementados, então pedir a mesma coisa de novo voltava barrado como duplicata.

Desfazer é uma operação de primeira classe, não um `git revert`. E ela tem três efeitos que
precisam acontecer juntos: o código sai, a memória esquece, e o registro mostra que entrou
**e** que foi desfeito.

---

## 5. As três métricas

Saem dos CSVs que `make metrics` baixa.

| Medida | Como se calcula | O que revela |
|---|---|---|
| **Taxa de intervenção humana** | `ajustar` + `recusar` sobre o total homologado | quanto da autonomia é aproveitável sem correção |
| **Densidade de retrabalho** | média de execuções por tarefa finalizada | quantas tentativas uma entrega custa |
| **Incidência de regressões** | tarefas cujos testes falharam numa execução após terem passado em outra | se o agente quebra o que já funcionava |

A terceira precisa de uma ressalva honesta: o CSV guarda o agregado, não o estado de cada
execução. Para afirmar "passou numa run e falhou na seguinte" é preciso olhar a tabela de
execuções, que o painel exibe por tarefa.

---

## 6. O que este trabalho não afirma

- **Não afirma que a IA substitui o desenvolvedor.** Afirma que ela absorve o trabalho
  mecânico quando existe uma rede que a segure, e que construir essa rede é trabalho de
  engenharia humana.
- **Não afirma que o modelo entende o produto.** Ele compara textos com um documento de
  contexto que uma pessoa escreveu e mantém.
- **Não é um sistema de produção.** É uma prova de conceito local, sem autenticação,
  deliberadamente jamais exposta. Os limites estão listados em
  [`scope-and-constraints.md`](scope-and-constraints.md), com a justificativa de cada um.

---

## 7. Onde olhar

| Para | Documento |
|---|---|
| o que existe e o que não existe | [`STATUS.md`](STATUS.md) |
| o que o sistema faz | [`features.md`](features.md) |
| como está montado | [`architecture-and-design.md`](architecture-and-design.md) |
| os limites, e por quê | [`scope-and-constraints.md`](scope-and-constraints.md) |
| para onde vai | [`roadmap.md`](roadmap.md) |
| como se escreve código aqui | documento `engineering-guidelines` (contexto, tela Contexto do painel) |
