# ADR-0003: Cores só por tokens semânticos

**Estado:** aceita

## Contexto
Cores espalhadas pelos componentes (`bg-white`, `text-slate-900`) fazem qualquer mudança de
tema virar uma varredura por todas as telas, e uma tentativa de tema escuro entregou uma
classe `dark` sem nenhuma cor escura definida.

## Decisão
Toda cor vem de uma variável CSS (`--surface`, `--ink`, `--brand`...) exposta ao Tailwind por
um nome semântico. Um tema é um conjunto novo de valores para essas variáveis.

## Consequências
- Mudar o visual ou criar um tema é editar um lugar.
- Cor cravada em componente é erro de revisão.
- Os valores de cada tema precisam existir para **todos** os tokens.

## Alternativas descartadas
- Variante `dark:` do Tailwind em cada componente: espalha a decisão por todo o código.
