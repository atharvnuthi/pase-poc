# Contexto Geral do Projeto - FinTrack

## O que é
Dashboard financeiro pessoal. Usuário cadastra transações (receita/despesa),
vê saldo e gastos por categoria, consulta relatórios mensais.

## Módulos existentes
- dashboard: saldo, resumo de gastos por categoria, orçamento do mês, últimas transações e
  gráfico de receitas e despesas dos últimos meses
- transacoes: CRUD de transações, edição de data direto na lista, exportação em CSV, busca e
  filtros por categoria, tipo e mês
- orcamentos: limite mensal de gasto por categoria e o quanto dele já foi usado
- metas: metas de economia, com valor-alvo, prazo opcional e progresso
- relatorios: totais agregados por mês, com a variação das despesas contra o mês anterior
- suporte: canal de tickets de suporte

## Regras de negócio centrais (violação = descarte por incoerência)
- Toda transação pertence a exatamente um usuário e uma categoria.
- Valores são sempre positivos; o tipo (receita/despesa) determina o sinal no cálculo de saldo.
- Categorias são fixas nesta fase (não há CRUD de categoria pelo usuário final).
- Não há autenticação real - usuário é selecionado por persona (PoC).

## Fora de escopo por decisão de produto (não confundir com "fora de escopo técnico")
- Investimentos, câmbio, múltiplas moedas.
- Integração bancária real (open finance).
- Qualquer forma de rede social ou compartilhamento entre usuários.
- Gamificação.

## Zonas Dinâmicas ativas
(uma por tela; cada uma preenche propriedades de widgets que já existem)
- resumo_financeiro (dashboard)
- transacoes_atalhos (transações)
- relatorios_destaque (relatórios)
- orcamentos_aviso (orçamentos)
- metas_incentivo (metas)
- suporte_ajuda (suporte)
