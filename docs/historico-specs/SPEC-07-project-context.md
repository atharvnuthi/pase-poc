# SPEC-07 - `project_context.md` (Contexto Geral do Projeto)

**Fase:** F0, escrito à mão no kickoff, depois editado pelo humano ao longo do projeto (nunca pela IA).

## 1. Papel no modelo

`project_context.md` é o insumo que a Camada de Coerência Sistêmica usa para julgar se uma proposta faz sentido (SPEC-03 P2a), que a Geração Exploratória usa como guia (SPEC-03 P3), e que a Fase de Planejamento consulta antes de mapear arquivos (SPEC-04 P4). É lido, nunca escrito, pelos agentes. Só um humano edita este arquivo.

Distinção importante (ver SPEC-00 Seção 8): este arquivo descreve **o que o produto é** (escopo, regras de negócio, módulos). Ele não é uma lista de regras de segurança absolutas - isso, se o projeto crescer, mereceria um arquivo de política separado (ver SPEC-10). Nesta fase, um único arquivo é suficiente.

## 2. Conteúdo mínimo obrigatório

```markdown
# Contexto Geral do Projeto - FinTrack

## O que é
Dashboard financeiro pessoal. Usuário cadastra transações (receita/despesa),
vê saldo e gastos por categoria, consulta relatórios mensais.

## Módulos existentes
- dashboard: saldo + resumo de gastos por categoria
- transacoes: CRUD de transações
- relatorios: totais agregados por mês
- suporte: canal de tickets de suporte

## Regras de negócio centrais (violação = descarte por incoerência)
- Toda transação pertence a exatamente um usuário e uma categoria.
- Valores são sempre positivos; o tipo (receita/despesa) determina o sinal no cálculo de saldo.
- Categorias são fixas nesta fase (não há CRUD de categoria pelo usuário final).
- Não há autenticação real - usuário é selecionado por persona (PoC).

## Fora de escopo por decisão de produto (não confundir com "fora de escopo técnico", SPEC-10)
- Investimentos, câmbio, múltiplas moedas.
- Integração bancária real (open finance).
- Qualquer forma de rede social ou compartilhamento entre usuários.
- Gamificação.

## Zonas Dinâmicas ativas
(atualizado conforme homologadas - ver SPEC-05)
- resumo_financeiro (dashboard)
```

## 3. Regra de atualização

Toda vez que uma task com `output_type=codigo_permanente` é homologada com aprovação, o humano deve revisar se `project_context.md` precisa de uma linha nova em "Módulos existentes" ou "Regras de negócio". Isso não é automatizado nesta fase - é uma responsabilidade humana explícita, porque automatizar a escrita do próprio contexto que julga coerência criaria um ciclo onde o sistema valida suas decisões contra um documento que ele mesmo reescreveu sem supervisão.

## 4. Critério de aceite

1. Arquivo existe e cobre as quatro seções acima antes do início da F1.
2. Toda alteração no arquivo é um commit próprio, nunca misturado com commits de código.
