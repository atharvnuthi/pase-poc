# ADR-0001: Dinheiro é sempre Decimal

**Estado:** aceita

## Contexto
O SQLite guarda números decimais como ponto flutuante, e `float` acumula erro de
arredondamento. Um saldo que difere por um centavo destrói a confiança em um app financeiro.

## Decisão
Valores monetários usam `Decimal` com 2 casas no backend, trafegam como **string** em JSON, e
toda agregação é feita em Python, nunca com `SUM()` em SQL.

## Consequências
- Somas e saldos são exatos.
- O frontend recebe string e formata por `formatMoney`.
- Agregar em SQL é proibido, mesmo quando seria mais rápido.

## Alternativas descartadas
- `float`: erro de arredondamento.
- Inteiros em centavos: exigiria converter em toda fronteira e mudar o contrato da API.
