# P0a - Agrupamento de Tickets por Tema

Você recebe mensagens de suporte do FinTrack e as separa pela **dificuldade de fundo**
que cada pessoa está relatando.

O SPEC-03 §2.2 fala em processar "um lote de tickets correlacionados". Este passo é
quem decide o que é correlacionado: similaridade vetorial não dá conta de texto curto
e coloquial, onde duas pessoas descrevem a mesma dificuldade com palavras
completamente diferentes.

## O critério de agrupamento

Agrupe por **necessidade compartilhada**, não por solução pedida.

Duas mensagens ficam no mesmo grupo quando as pessoas estão esbarrando no mesmo
limite do produto - a mesma tela que não entrega, a mesma informação difícil de
alcançar - **ainda que cada uma peça uma saída diferente**.

Isso é deliberado e importante: um grupo onde as pessoas convergem na dor e divergem
na solução é o sinal mais valioso que este sistema coleta. Ele indica que nenhuma
resposta única serviria bem a todas, e é isso que distingue uma área personalizável
de uma funcionalidade fixa. Separar essas mensagens em grupos de um destrói o sinal.

Não agrupe por assunto genérico ("é sobre dinheiro", "é sobre o dashboard"). O
vínculo tem que ser uma dificuldade concreta e comum.

## Demais regras

- Uma mensagem sozinha na sua dificuldade forma um grupo de um elemento. Isso é normal.
- Toda mensagem aparece em **exatamente um** grupo. Nenhuma de fora, nenhuma repetida.
- `theme` é um rótulo curto, em pt-BR, com no máximo 60 caracteres, que nomeia a
  dificuldade compartilhada - não a solução.

## Mensagens, com o identificador de cada uma

{{tickets}}

## Saída

Um objeto JSON com a chave `groups`, contendo uma lista. Cada item tem `theme`
(string) e `ticket_ids` (lista de números inteiros).
