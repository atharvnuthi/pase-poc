# Requisitos do FinTrack

Requisitos numerados para que tarefas e revisões possam citá-los. Quem aceita uma entrega
confere contra estes itens.

## Funcionais

| Id | Requisito |
|---|---|
| RF-01 | A pessoa escolhe uma persona na entrada e vê só os dados dela |
| RF-02 | O dashboard mostra o saldo (receitas menos despesas) e os gastos por categoria |
| RF-03 | A pessoa lança, edita e exclui transações; cada transação tem tipo, categoria, valor, data e descrição |
| RF-04 | A data de uma transação pode ser corrigida direto na lista |
| RF-05 | A pessoa exporta as próprias transações em CSV |
| RF-06 | O relatório mostra receitas, despesas e saldo por mês |
| RF-07 | A pessoa envia um pedido de ajuda pelo canal de suporte |
| RF-08 | A pessoa sugere uma melhoria por um botão disponível em todas as telas |
| RF-09 | A interface se personaliza por pessoa em áreas designadas (zonas dinâmicas), com selo "personalizado" |
| RF-10 | A pessoa define um limite mensal de gasto por categoria de despesa e vê quanto já usou no mês, com aviso ao se aproximar do limite (80%) e ao estourá-lo |
| RF-11 | A pessoa cria metas de economia com valor-alvo e prazo opcional, registra quanto guardou e vê o progresso e o valor mensal necessário para chegar no prazo |
| RF-12 | A pessoa busca transações pela descrição e filtra por categoria, tipo e mês |
| RF-13 | O dashboard mostra o orçamento do mês, as últimas transações e a evolução de receitas e despesas dos últimos meses |
| RF-14 | Os relatórios comparam as despesas de cada mês com as do mês anterior |

## Não funcionais

| Id | Requisito |
|---|---|
| RNF-01 | Erro de validação aparece no campo que o causou, com mensagem em português |
| RNF-02 | Valores monetários usam `Decimal` e largura fixa de número na tela |
| RNF-03 | Todo controle de formulário tem rótulo associado, e todo botão tem nome acessível |
| RNF-04 | Foco visível em todo elemento interativo |
| RNF-05 | Se a personalização falhar, a tela normal aparece, sem erro visível |
| RNF-06 | Nenhuma ação destrutiva fica escondida atrás de hover |
| RNF-07 | Toda cor vem de um token semântico, para o tema mudar em um lugar só |
| RNF-08 | Bloco opcional de uma tela (painel do dashboard, zona dinâmica) que falhar some sem afetar o resto da tela |
| RNF-09 | O estado de um orçamento é decidido pelos valores exatos, não por um percentual arredondado |

## Como estes requisitos são usados

- O **planejamento** escreve critérios de aceite que cobrem os requisitos tocados pela tarefa.
- A **revisão independente** confere cada critério e pode citar o requisito (ex.: RNF-03).
- Requisito novo entra aqui antes de virar tarefa.
