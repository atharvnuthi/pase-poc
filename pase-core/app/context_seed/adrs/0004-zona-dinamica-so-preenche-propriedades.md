# ADR-0004: Zona dinâmica só preenche propriedades

**Estado:** aceita

## Contexto
A interface precisa se adaptar a cada pessoa. Deixar um modelo de linguagem gerar componentes
React em tempo de execução criaria código arbitrário rodando no navegador.

## Decisão
Uma zona dinâmica é um espaço da tela que o sistema preenche escolhendo um widget de um
**catálogo fechado** (lista de atalhos, cartão de resumo, faixa de aviso) e preenchendo
**propriedades** validadas por um schema. O modelo nunca escreve marcação nem código.

## Consequências
- O payload é validado no servidor e, de forma decisiva, no app.
- Qualquer falha cai no componente nativo, e a violação é registrada.
- Links só apontam para rotas internas (expressão regular).
- Acrescentar um widget ou um slot exige contrato, registry e teste de fallback.

## Alternativas descartadas
- Gerar JSX em tempo de execução: inseguro e impossível de revisar.
- HTML dinâmico: abre caminho para injeção.
