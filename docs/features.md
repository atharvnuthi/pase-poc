# Funcionalidades

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

O que o sistema faz, do ponto de vista de quem usa. A arquitetura está em
[`architecture-and-design.md`](architecture-and-design.md); o estado de cada item, em
[`STATUS.md`](STATUS.md).

---

## 1. Captação de demanda

O PASE recebe pedidos por quatro caminhos, e todos desaguam no mesmo funil.

### Captação Ativa
Um botão flutuante em toda tela do FinTrack abre "Sugerir melhoria". A pessoa escreve o
que quiser, em linguagem natural, e recebe de volta o que o funil decidiu - se virou
tarefa, se já existia, ou por que não cabe no produto.

### Captação Passiva
Um job lê os tickets de suporte do FinTrack. Reclamação não é pedido de funcionalidade:
o prompt P0 converte "não acho onde ver quanto gastei em transporte" numa proposta
estruturada. Antes disso, P0a agrupa tickets que falam da mesma dor - porque três pessoas
reclamando da mesma coisa é um sinal diferente de três reclamações distintas.

### Sugestões internas
Pelo painel, com autor e tipo:

- **Funcional** - passa pelo funil inteiro.
- **Engenharia** - exige autor autorizado e **pula** Memória Histórica e Coerência. A
  autorização já transferiu o julgamento para uma pessoa qualificada; o que resta é
  qualificar para priorizar. Entra com risco mínimo `medio`, porque mexer em
  infraestrutura é o que essas tarefas fazem.

### Geração por IA
Dois modos, ambos disparados do painel:

- **Exploratória** - inventa uma melhoria plausível a partir do contexto do produto, do
  que já foi implementado e do que já foi descartado. É a única chamada do sistema com
  temperatura alta (0.9).
- **Análise de Lacunas** - cruza módulos existentes procurando integração que ninguém fez
  ainda. Temperatura baixa: é análise, não brainstorm.

## 2. O funil de filtragem

Toda proposta passa pelas mesmas etapas, e **todo desfecho é explícito e persistido** -
nada some em silêncio.

1. **Normalização** - extrai título, descrição e módulo do texto cru.
2. **Avaliação de Zona Dinâmica** - a demanda tem solução homogênea para todo mundo, ou é
   um padrão de cauda longa em que cada usuário quer algo diferente? A resposta decide se
   a tarefa vira código permanente ou configuração de zona.
3. **Memória Histórica** - busca vetorial contra o que já foi implementado, o que está na
   fila e o que já foi descartado. Duplicata não cria linha nova: incrementa o contador na
   linha existente, porque a frequência de um pedido é sinal que a avaliação de zona
   precisa.
4. **Coerência Sistêmica** - compara a proposta com os documentos de contexto (escopo, requisitos, funcionalidades). O que viola o
   escopo ou uma regra de negócio vira descarte com o motivo escrito, citando o trecho
   violado. Quando dá para salvar a essência com um recorte menor, a proposta é ajustada e
   **revalidada** contra a memória.
5. **Qualificação** - impacto, complexidade, confiança e faixa de risco. Confiança baixa
   marca a tarefa como incerta, e isso aparece no painel.

O resultado é uma tarefa candidata no backlog, ou um descarte com motivo.

## 3. Aprovação e execução autônoma

Aprovar uma tarefa candidata libera a cadeia autônoma. Ela roda sozinha e **para** no
próximo ponto que exige uma pessoa.

**Planejamento.** O sistema lê o código-fonte dos alvos por inteiro, decide quais arquivos
mudar e estima o custo. O plano fica registrado e é revisável.

**Despacho.** Se os arquivos do plano colidem com uma tarefa em andamento, a nova espera -
e o painel mostra em quem ela está esperando.

**Execução.** Num clone isolado, em branch própria. O agente escreve os arquivos, e então a
máquina verifica: lint e testes no backend, checagem de tipos e testes no frontend. Se
reprovar, ele corrige e tenta de novo, até um teto. Se estourar tentativas ou custo, a
tarefa fica suspensa com o alerta correspondente, esperando decisão.

**Homologação.** A pessoa vê o diff, os logs de verificação e o transcript inteiro da
conversa com o modelo, e decide: aprovar (merge), ajustar (nova execução com o comentário)
ou recusar. Tarefa de risco alto exige justificativa por escrito **mesmo para aprovar**.

## 4. Personalização em runtime

Enquanto o loop lento escreve código, o rápido ajusta a interface para cada pessoa - sem
escrever uma linha.

O sistema observa a navegação. Quando um padrão aparece (por exemplo: cinco visitas a
relatórios em sete dias), ele avalia se vale personalizar aquele espaço do dashboard. Se
valer, escolhe um widget do catálogo e preenche as propriedades.

A garantia central: **uma Zona Dinâmica nunca executa código arbitrário.** O que o modelo
produz é um objeto de propriedades, validado duas vezes - no servidor antes de guardar, e
no cliente antes de renderizar. Qualquer coisa fora do contrato - rótulo longo demais,
link apontando para fora, widget que não existe, propriedade a mais - cai no componente
nativo e registra a violação com o payload bruto. O usuário nunca vê o app quebrado.

## 5. Manutenção contínua

**Auditoria** lê o código e propõe refatoração. O achado entra como sugestão de
engenharia, assinada pelo próprio sistema, e segue o mesmo fluxo de qualquer outra.

**Reavaliação Cíclica** relê descartes antigos contra o contexto de hoje. Se a restrição
que justificou o descarte não consta mais do documento, a proposta volta para a fila. O
modelo aponta onde está a evidência; quem confere se ela realmente existe no texto é o
código.

## 6. Painel de controle

Tudo que exige uma pessoa acontece num lugar só, e nada acontece automaticamente:

- **Tarefas** - candidatas ordenadas por prioridade, o que está em andamento agrupado por
  estado, o histórico das finalizadas e os descartes com motivo.
- **Tarefa [id]** - planejamento, execuções, diff, logs, transcript e os botões de
  homologação.
- **Zonas** - payloads ativos, violações registradas, um simulador de comportamento e um
  injetor de payload cru para testar a defesa.
- **Incidentes** - alimentam o fator de urgência, que reordena o backlog.
- **Contexto** - o documento que decide o escopo do produto, e a lista de quais etapas o
  leem.

As listas se atualizam sozinhas por eventos reais do sistema, não por polling.

## 7. O FinTrack

O produto-alvo é um app de verdade, não uma maquete: seleção de persona, dashboard com
saldo e gastos por categoria, cadastro e edição de transações com validação por campo,
relatórios mensais e canal de suporte.

## 8. Roteiros de demonstração

Oito roteiros executáveis, cada um provando uma propriedade do modelo:

| # | O que prova |
|---|---|
| d1 | uma frase vira código mergeado, passando por gate humano |
| d2 | duplicata e incoerência são barradas, com motivo e contagem |
| d3 | a IA gera proposta própria, nos dois modos |
| d4 | personalização autônoma aparece para uma persona e não para a outra |
| d5 | payload malicioso não passa: fallback nativo e violação registrada |
| d6 | teto de tentativas e teto de custo interrompem de verdade |
| d7 | tickets repetidos viram uma demanda de zona dinâmica |
| d8 | auditoria propõe refatoração; reavaliação reabre descarte obsoleto |

## 9. Métricas

Três CSVs sustentam a validação: tarefas, descartes e violações. Deles saem a taxa de
intervenção humana, a densidade de retrabalho e a incidência de regressões.
