# Design System: FinTrack Ledger

Identidade de livro-razão: papel quente, tinta quase preta, um verde de contabilidade e fios
finos no lugar de sombras. Dinheiro é assunto sério, e o visual diz isso sem pedir desculpas.

## Cores (tokens)

| Token | Claro | Uso |
|---|---|---|
| `canvas` | papel quente | fundo da página |
| `surface` | quase branco | cartões e campos |
| `surface-sunken` | papel mais escuro | áreas rebaixadas, contadores |
| `line`, `line-strong` | tons de papel | contornos e divisórias |
| `ink`, `ink-muted`, `ink-subtle` | tinta | texto principal, secundário e auxiliar |
| `brand`, `brand-strong`, `brand-ink` | verde de contabilidade | ação principal e entradas |
| `danger`, `danger-soft` | vermelho tijolo | erro e saldo negativo |
| `warning`, `warning-soft` | âmbar | alerta |
| `inverse`, `on-inverse` | verde-grafite e papel | painéis invertidos (saldo, entrada) |
| `on-ink` | quase branco | texto sobre fundo de tinta |

Um tema novo, como um escuro, redefine os mesmos tokens; nenhum componente muda.

## Tipografia

| Papel | Fonte |
|---|---|
| Títulos, saldo, marca | Instrument Serif |
| Interface e texto | IBM Plex Sans (400, 500, 600) |

Valores monetários usam números tabulares (`tnum`).

## Forma e profundidade

- Cantos discretos (6 a 12 px). Sem cantos de "pílula" em cartões.
- **Fios de 1 px**, sem sombra de cartão. A única elevação é a do modal.
- Painéis invertidos usam **papel pautado**: linhas finas a cada 2 rem.

## Componentes base (`components/ui.tsx`)

| Componente | Regra |
|---|---|
| `Cartao` | contorno fino, fundo `surface` |
| `TituloSecao` | título em serifa, apoio em texto secundário |
| `Campo` | rótulo envolve o controle; erro em `danger` abaixo do campo |
| `Botao` | `primario`, `marca`, `neutro`, `fantasma`, `perigo`; altura 32 ou 40 px |
| `Vazio` | frase em serifa itálica que explica o que aparece ali |
| `Marca` | monograma "F" itálico sobre verde e o nome em serifa |

## Navegação

Links de texto com sublinhado no item ativo (`aria-current="page"`), sem pílulas.

## Movimento

Transições curtas só em cor e posição. Nada que atrase a leitura.
