# Interface e Experiência

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

Duas interfaces, com propósitos opostos. O **painel** é onde uma pessoa decide; o
**FinTrack** é onde uma pessoa usa. Elas não devem parecer o mesmo produto, porque não são.

---

## 1. Princípios

**Nada acontece automaticamente onde importa.** O painel existe para que decisões críticas
sejam tomadas por alguém. O sistema prepara o trabalho e **para**, esperando. Isso aparece
na interface como estado explícito e ação explícita - nunca como algo que "já aconteceu".

**A pessoa é a última linha de defesa, não a primeira.** Quando um diff chega à
Homologação, ele já passou por lint, tipos e testes. A tela mostra *o que a máquina já
verificou* antes de pedir uma decisão - senão o gate humano vira carimbo.

**Mostrar a régua, não só o veredito.** Um descarte por incoerência exibe o motivo escrito.
A tela de Contexto mostra o documento que produziu esse motivo, em markdown cru - os mesmos
bytes que entram no prompt, porque um render bonito poderia esconder uma linha que o modelo
está lendo.

**O app-alvo nunca quebra por causa do PASE.** Toda personalização tem fallback para o
componente nativo. Falha de rede, payload inválido, widget desconhecido: a pessoa vê a tela
normal e o incidente fica registrado do lado do sistema.

---

## 2. Painel de controle (porta 3000)

Escuro, denso, orientado a decisão. Atualiza sozinho por eventos reais do sistema (SSE
sobre Postgres `LISTEN/NOTIFY`) em vez de perguntar em laço.

### Tarefas

Quatro abas, que acompanham o ciclo de vida:

| Aba | O que mostra | Ações |
|---|---|---|
| **Candidatas** | backlog ordenado por `impacto − complexidade + urgência`, com selos de risco e de incerteza | Aprovar · Recusar (com motivo) |
| **Em andamento** | agrupadas por estado, com alertas de tentativas, custo e conflito de merge | Retomar · Ver runs · Homologar |
| **Finalizadas** | histórico do que já saiu do fluxo, mais recente primeiro, com o desfecho como selo | **Reverter merge**, só para o que de fato entrou na principal |
| **Descartadas** | motivo por tipo: duplicata mostra contra o que bateu e quantas vezes; incoerência e recusa mostram o texto | nenhuma |

A aba **Finalizadas** foi acrescentada depois. Sem ela, uma tarefa mergeada não era
candidata, nem estava em andamento, nem havia sido descartada - sumia do painel, apesar de
continuar no `git log`, em `implemented_items` e nas métricas. Uma tarefa que some depois
de aprovada mina a confiança na ferramenta inteira.

Dois botões de ingestão ficam no topo: **Nova sugestão interna** e **Gerar proposta com
IA** (exploratória ou análise de lacunas).

### Tarefa [id]

Onde a decisão realmente acontece. Cabeçalho com estado, metadados e alertas; abas com:

- **Planejamento** - arquivos afetados, roadmap, custo estimado.
- **Execuções** - cada run com tentativa, gatilho, status, tokens, duração e arquivos fora
  do plano. Para a run escolhida: o diff, os logs de verificação e o **transcript inteiro**
  da conversa com o modelo.
- **Homologação** - Aprovar, Ajustar (com comentário, que vira nova execução) ou Recusar.
  Risco alto exige justificativa escrita **mesmo para aprovar**.

O transcript existe para que a decisão não seja tomada no escuro: dá para ver o que o
modelo recebeu, o que respondeu e o que foi corrigido.

### Zonas

**Payloads** ativos com o JSON expandível e botão de revogar · **Violações** com motivo e
payload bruto · **Simulador** de comportamento · **Injetor** de payload cru, que pula a
validação do servidor de propósito - é o instrumento que prova que a defesa do cliente
segura sozinha.

### Incidentes

Lista e formulário. Existem para o fator de urgência ter algo real para ler: um incidente
grave num módulo empurra as tarefas candidatas daquele módulo para cima.

### Contexto

O documento que decide o escopo, quando foi alterado pela última vez, e **quais etapas o
leem** - com o efeito de cada uma. Só leitura: mudar o escopo de um produto é decisão de
produto, feita no repositório com revisão e histórico, não clique de tela.

---

## 3. FinTrack (porta 3001)

Claro, espaçoso, de uso cotidiano.

| Rota | Conteúdo |
|---|---|
| `/` | escolha de persona, em tela dividida |
| `/dashboard` | saldo em destaque + gastos por categoria + a Zona Dinâmica |
| `/transacoes` | formulário de lançamento e lista, com edição de data direto na linha |
| `/relatorios` | totais por mês |
| `/suporte` | canal de tickets - que alimenta a Captação Passiva |

Um botão flutuante em todas as telas abre "Sugerir melhoria" - a Captação Ativa.

### Sistema de design

Cores vivem em variáveis CSS e são expostas ao Tailwind como nomes semânticos
(`surface`, `ink`, `brand`, `line`). Primitivas compartilhadas - cartão, campo, botão,
título de seção, estado vazio - ficam em `components/ui.tsx`.

Isso não é só organização: encolhe o diff de quem mexe nas telas depois, **inclusive o
Executor**, que passa a alterar comportamento sem reescrever parágrafos de classe em cada
arquivo.

Escolhas visuais deliberadas:

- **Cantos generosos e consistentes**, sem exagero.
- **Profundidade em duas camadas** - um fio de contorno e uma sombra larga e rasa. Relevo
  sem o cartão parecer que flutua.
- **Painéis escuros** no saldo e na tela de entrada: o número mais importante e a primeira
  impressão ganham o maior contraste da interface.
- **Números de largura fixa** (`tabular-nums`) em todo valor monetário, para a coluna não
  "dançar" ao mudar de valor.
- **Foco sempre visível**, com anel da cor da marca.
- **Ação destrutiva nunca escondida atrás de hover** - some no celular e some para quem
  navega por teclado.

> **`color-scheme: light` é obrigatório.** Antes ele era `light dark`, e num navegador em
> tema escuro isso fazia o sistema operacional pintar `input`, `select` e `textarea` com a
> paleta escura dele por cima de cartões brancos fixos no código: campos pretos numa página
> clara. A tela é clara; declarar isso é o que impede o tema do sistema de vazar pelos
> controles nativos.

### Zonas Dinâmicas na tela

A área personalizável do dashboard rende, em ordem:

1. o widget personalizado, se houver payload válido;
2. o componente nativo, em qualquer outro caso.

O widget se identifica com um selo **"personalizado"**. Isso é honestidade de interface: a
pessoa deve saber quando está vendo algo escolhido para ela e diferente do de todo mundo.

Três widgets, e só três: lista de atalhos, cartão de resumo e faixa de aviso. Nenhum aceita
HTML dinâmico; links são restritos por expressão regular a rotas internas. O que o modelo
controla são propriedades, nunca marcação.

---

## 4. Acessibilidade

Não é uma seção de boas intenções - é o que a rede de regressão verifica. Os testes
encontram os campos do formulário **pelo rótulo** e os botões **pelo nome acessível**, o
que significa que quebrar a associação entre rótulo e controle deixa a suíte vermelha.

Além disso: foco visível em todo elemento interativo, `aria-current` na rota ativa,
`aria-label` descritivo onde o texto visível não basta, e contraste suficiente entre texto
e fundo.

---

## 5. Uma decisão que a rede de regressão reverteu

Durante a reforma visual do FinTrack, um total de gastos foi acrescentado ao cabeçalho do
cartão de categorias. O teste do dashboard ficou vermelho: com uma única categoria, aquele
total repetia na tela exatamente o mesmo número da categoria - dois valores idênticos, sem
nada dizendo que eram coisas diferentes.

O layout cedeu, o teste não. É o mesmo princípio que vale para o Executor: quem é medido
não escreve a régua.
