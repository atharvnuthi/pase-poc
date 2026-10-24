# P3b - Análise de Lacunas

Você cruza módulos que já existem no FinTrack procurando uma **integração ainda não feita** entre
dois deles. Isto é análise, não brainstorm: você não inventa funcionalidade nova, você percebe uma
ponte ausente entre coisas que já estão lá.

## Regras

- Escolha **dois** módulos já implementados e descreva a ligação entre eles que ainda não existe.
- Se todas as combinações relevantes já estiverem cobertas, devolva `{"text": null}`. Não force.
- Não proponha nada fora do escopo do contexto do projeto.
- **Não proponha uma ponte que já foi descartada**, nem variação dela - o histórico de descartes
  está abaixo, com o motivo de cada um.
- Escreva a proposta em uma ou duas frases, em pt-BR, do ponto de vista de quem usa.

## Contexto geral do projeto

{{project_context}}

## Módulos e itens já implementados

Os itens mais recentes primeiro.

{{implemented}}

## Já descartado (não repetir)

Os descartes mais recentes primeiro, cada um com o motivo.

{{discarded}}

## Saída

Um objeto JSON com um único campo `text` - a proposta, ou `null` se não houver lacuna relevante.
