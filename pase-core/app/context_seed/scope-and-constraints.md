# Escopo e Restrições do FinTrack

Este documento diz o que o produto **não** faz e quais limites ele respeita. Cada item foi
deixado de fora por decisão, e a decisão está aqui. Em caso de conflito com outro documento
de contexto, este vence.

## 1. Escopo de produto

**Dentro do escopo:** controle de receitas e despesas de uma pessoa, saldo, gastos por
categoria, relatórios mensais, orçamento mensal por categoria, metas de economia, busca e
filtros, suporte e personalização da interface por pessoa.

**Fora do escopo por decisão de produto:**
- Investimentos, câmbio e múltiplas moedas.
- Integração bancária real (open finance).
- Rede social ou compartilhamento de dados entre usuários.
- Gamificação.

## 2. Restrições técnicas

| Restrição | Motivo |
|---|---|
| Sem autenticação real | É uma prova de conceito local. Autenticação "por precaução" daria a impressão errada de que o app está pronto para exposição pública |
| Ambiente estritamente local | CORS liberado só para as portas do app; nunca exposto publicamente |
| Categorias fixas | O usuário final não cria nem apaga categorias |
| Dinheiro sem float | Valores em `Decimal`; no JSON trafegam como string |
| Uma zona dinâmica por tela | A personalização preenche propriedades de componentes que existem; nunca gera código. Hoje são seis zonas, uma em cada tela |
| Sem dependência nova sem pedido humano | Reduz superfície de ataque e custo de manutenção |

## 3. Limites da personalização

- O sistema só **preenche propriedades** de widgets do catálogo. Nunca escreve componente.
- Todo payload é validado duas vezes (servidor e app). Inválido cai no componente nativo.
- Links de widget só apontam para rotas internas.

## 4. Decisões de escopo registradas

- **Orçamento por categoria e metas de economia entraram no escopo** (outubro de 2026). Eram
  "fora de escopo por ora"; a decisão de produto os trouxe, e o escopo mudou antes do código.
  A tela de Orçamentos limita só categorias de despesa.

## 5. Quando algo parece fora do escopo

Se uma demanda toca um item da seção 1, ela é descartada por incoerência com o motivo citando
a linha violada. Mudar o escopo é decisão de produto: edite este documento, e o sistema passa
a julgar pelo texto novo, sem reiniciar nada.
