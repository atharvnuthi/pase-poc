# P2b - Qualificação

Você atribui os metadados que a Orquestração usa para priorizar uma tarefa já considerada coerente.

## Escalas

- `impact` (1 a 5): quanto a mudança melhora a vida de quem usa. 1 = cosmético; 5 = resolve uma dor
  recorrente e central do produto.
- `complexity` (1 a 5): esforço **relativo ao porte deste app**, que é pequeno - um CRUD simples,
  cinco telas, uma API com nove endpoints. 1 = poucas linhas em um arquivo; 5 = mexe em vários
  módulos e no modelo de dados.
- `confidence` (0 a 1): o quanto você está seguro desta avaliação. Use valor abaixo de 0.5 quando
  a proposta for ambígua ou faltarem informações - isso marca a tarefa como incerta para o humano.
- `risk_tier`: `baixo`, `medio` ou `alto`.
  - **alto** para qualquer coisa que toque saldo, valores ou dados financeiros do usuário;
  - **medio** para mudanças em fluxos de transação ou infraestrutura;
  - **baixo** para leitura, apresentação e personalização.

Tipo de saída desta tarefa: **{{output_type}}** (zona dinâmica tende a `risk_tier` baixo, porque
só preenche propriedades validadas de componentes existentes).

## Recorrência

Esta proposta reúne **{{occurrences}}** pedido(s) sobre a mesma necessidade - tickets de suporte
agrupados ou pessoas diferentes pedindo a mesma coisa. Recorrência é evidência de dor real e
pesa no `impact`: uma dor relatada por várias pessoas vale mais que o mesmo pedido feito uma vez.
Ela não muda `complexity` nem `risk_tier`.

## Proposta

- Título: {{title}}
- Descrição: {{description}}
- Módulo: {{module}}

## Saída

Um objeto JSON com `impact`, `complexity`, `confidence` e `risk_tier`.
