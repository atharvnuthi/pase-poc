# P1b - Avaliação de Zona Dinâmica

Você decide se uma demanda deve virar **funcionalidade fixa no código** ou **Zona Dinâmica**
(uma área da interface que o sistema personaliza por usuário, dentro de um contrato validado).

## O critério, e só ele

- `requires_zone = false` - a demanda tem **solução homogênea**: todo usuário quer a mesma coisa,
  do mesmo jeito. Vira código permanente.
- `requires_zone = true` - a demanda é **cauda longa**: usuários diferentes querem recortes
  diferentes da mesma necessidade, e uma solução única atenderia mal a maioria. Vira Zona Dinâmica.

Não decida por complexidade, por esforço nem por quanto a ideia é boa. O único eixo é
homogêneo versus divergente entre usuários.

## O que uma Zona Dinâmica consegue fazer

Uma zona só preenche **rótulos, atalhos para telas que já existem e avisos**, em três
componentes prontos (lista de atalhos, cartão de resumo, faixa de aviso). Ela não cria dado,
tela nem comportamento novo. Se atender ao pedido exige uma funcionalidade nova, ou algo que
esses componentes não expressam, `requires_zone = false`, mesmo que o módulo já tenha uma zona.

## Como ler o histórico do módulo

Abaixo estão os pedidos passados **mais parecidos com este, no mesmo módulo**, recuperados por
similaridade. Cada um traz o que aconteceu com ele e quantos pedidos ele reúne.

- O mesmo problema reaparecendo com **pedidos de saída diferentes** é o sinal mais forte de cauda
  longa: compare o que cada um pede.
- Pedidos anteriores encaminhados à Zona Dinâmica do módulo mostram que demandas desse tipo já
  foram tratadas como personalização.
- Recorrência com a **mesma** saída pedida por todos é sinal de demanda homogênea, não de cauda
  longa: muita gente querendo a mesma coisa continua sendo uma coisa só.
- Similaridade baixa quer dizer que o item é só vizinho de assunto. Não force relação.

Esta proposta reúne **{{occurrences}}** pedido(s).

### Pedidos parecidos no módulo

{{historico}}

## Proposta

- Título: {{title}}
- Descrição: {{description}}
- Módulo: {{module}}

## Saída

Um objeto JSON com `requires_zone` (booleano) e `reasoning` (uma frase em pt-BR justificando,
citando o eixo homogêneo/divergente e, se houver, o pedido do histórico que pesou na decisão).
