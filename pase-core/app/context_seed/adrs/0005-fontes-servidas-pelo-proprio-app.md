# ADR-0005: Fontes servidas pelo próprio app

**Estado:** aceita

## Contexto
O `next build` do ambiente de verificação roda sem acesso à internet. Fonte carregada de um
serviço externo falha o build, não só a estética.

## Decisão
As fontes (IBM Plex Sans e Instrument Serif) ficam em `public/fonts` e são declaradas por
`@font-face` em `globals.css`. Sem CDN e sem dependência nova.

## Consequências
- O build funciona offline.
- Trocar uma fonte é trocar arquivos e uma declaração.
- Os arquivos entram no repositório (cerca de 20 KB cada).
