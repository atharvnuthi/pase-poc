# Interface e Experiência do FinTrack

## 1. Princípios

- **Claro e cotidiano.** É um app de uso diário: espaçoso, legível, sem ruído.
- **O número importa mais.** O saldo é a informação principal e tem o maior destaque.
- **Honestidade de interface.** Tudo que foi escolhido para a pessoa leva o selo
  "personalizado".
- **A tela nunca quebra.** Falha de dado opcional vira estado vazio ou componente nativo.

## 2. Rotas

| Rota | Conteúdo |
|---|---|
| `/` | Escolha de persona, em tela dividida |
| `/dashboard` | Saldo em destaque, gastos por categoria e a zona dinâmica |
| `/transacoes` | Formulário de lançamento, filtros e lista, com edição de data na linha |
| `/orcamentos` | Limite por categoria, progresso do mês e formulário para definir limites |
| `/metas` | Metas com progresso, ritmo mensal, aporte inline e formulário de nova meta |
| `/relatorios` | Totais por mês |
| `/suporte` | Canal de tickets |

Um botão flutuante em todas as telas abre "Sugerir melhoria".

## 3. Padrões de interação

- Erro de validação aparece **no campo** que o causou.
- Ação destrutiva fica sempre visível, nunca atrás de hover.
- Formulários usam rótulo que envolve o controle (`<label><span>Nome</span><input/></label>`).
- Estados vazios explicam o que aparece ali e como preencher.
- Valores monetários usam número de largura fixa para a coluna não "dançar".
- Estado de orçamento nunca é só cor: a barra muda de cor e o texto diz "perto do limite" ou
  "limite estourado".
- Barra de progresso tem `role="progressbar"` e nome acessível; o gráfico mensal tem uma tabela
  escondida para leitor de tela.

## 4. Tema

Hoje há um único tema, o claro. Um tema é uma troca de valores dos tokens de cor; nenhum
componente cita uma cor fixa, então um tema novo é um bloco novo de valores, não uma varredura
pelas telas. Se a pessoa puder trocar de tema, o rótulo do botão diz a **ação** ("Usar tema
escuro"), não o estado, e a preferência vale por persona e sobrevive a recarregar a página.

`color-scheme` acompanha o tema, para campos nativos não ficarem com cores do sistema.

## 5. Acessibilidade

- Campos achados pelo rótulo e botões pelo nome acessível: a suíte de testes depende disso.
- Foco visível em todo elemento interativo.
- `aria-current` na rota ativa; `aria-label` onde o texto visível não basta.
- Contraste suficiente entre texto e fundo, nos dois temas.

## 6. Zonas dinâmicas na tela

Em ordem: o widget personalizado, se houver payload válido; senão, o componente nativo.
Três widgets: lista de atalhos, cartão de resumo e faixa de aviso. Nenhum aceita HTML
dinâmico, e links só apontam para rotas internas.

O sistema visual completo está em `design-systems/fintrack-ledger`.
