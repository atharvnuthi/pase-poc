# Funcionalidades do FinTrack

O que o produto faz, do ponto de vista de quem usa.

## Entrada (`/`)
Seleção de persona (Ana ou Clara). Não é login: é uma seleção, e a tela diz isso.

## Dashboard (`/dashboard`)
- Saldo em destaque, com o número maior da tela.
- Gastos por categoria, com a proporção de cada uma.
- Orçamento do mês (as três categorias mais perto do limite), últimas transações e um gráfico
  de receitas e despesas dos últimos seis meses. Cada bloco é opcional: se o dado falhar, ele
  some e o saldo continua aparecendo.
- **Zona dinâmica `resumo_financeiro`:** um bloco que o sistema personaliza por pessoa (lista de
  atalhos, cartão de resumo ou faixa de aviso). Sem personalização, aparece o resumo nativo.

## Transações (`/transacoes`)
- Formulário de lançamento: tipo, categoria, valor, data e descrição, com erro por campo.
- Lista com edição da data direto na linha e exclusão sempre visível.
- Busca pela descrição (ignora caixa e acento) e filtros por categoria, tipo e mês.
- Exportação das transações em CSV.

## Orçamentos (`/orcamentos`)
- Um limite mensal por categoria de despesa, com barra de progresso, quanto resta (ou quanto
  passou do limite) e um aviso em texto: "perto do limite" a partir de 80%, "limite estourado"
  acima de 100%.
- Seletor de mês para ver os meses anteriores; alterar e remover limites.

## Metas (`/metas`)
- Metas de economia com valor-alvo e prazo opcional.
- Guardar um valor atualiza o progresso; com prazo, mostra quanto guardar por mês para chegar
  lá. Passar do alvo é permitido: a meta é um piso.

## Relatórios (`/relatorios`)
Totais de receitas, despesas e saldo por mês, e a variação das despesas contra o mês anterior.

## Suporte (`/suporte`)
Canal de tickets. Os tickets alimentam o sistema que evolui o produto.

## Em todas as telas
- Botão "Sugerir melhoria", que envia uma ideia ao sistema que evolui o produto.
- Selo "personalizado" em qualquer bloco escolhido para a pessoa.

## Zonas dinâmicas

| Zona | Tela | Dispara com |
|---|---|---|
| `resumo_financeiro` | dashboard | 5 visitas a relatórios |
| `transacoes_atalhos` | transações | 5 visitas a transações |
| `relatorios_destaque` | relatórios | 3 visitas a relatórios |
| `orcamentos_aviso` | orçamentos | 3 visitas a orçamentos |
| `metas_incentivo` | metas | 3 visitas a metas |
| `suporte_ajuda` | suporte | 2 visitas a suporte |

Uma sugestão escrita que uma zona já cobre ajusta a zona da pessoa na hora, em vez de virar
tarefa de código.

Catálogo de widgets: `shortcut_list`, `summary_card`, `alert_banner`.
