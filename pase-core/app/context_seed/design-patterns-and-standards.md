# Padrões de Projeto e Padrões de Código

Padrões concretos que o FinTrack já usa. Siga-os; não invente um paralelo.

## 1. Cliente HTTP único
Toda chamada à API passa por `lib/api.ts`. Ele resolve a URL base, o cabeçalho e traduz o
erro 422 em um objeto por campo, que os formulários mostram junto do campo.

```ts
try { await api.createTransaction(payload) }
catch (e) { setErros(e.campos) }   // { amount: "valor deve ser positivo" }
```

## 2. Formulário com erro por campo
`<Campo label="Valor" erro={erros.amount}>` envolve o controle. O rótulo envolve o `input`, o
que associa os dois e permite que testes e leitores de tela o encontrem.

## 3. Primitivas de interface
`Cartao`, `Campo`, `Botao`, `TituloSecao`, `Vazio` em `components/ui.tsx`. Variantes de botão:
`primario`, `marca`, `neutro`, `fantasma`, `perigo`. Uma tela nova compõe estas peças.

## 4. Tokens de cor
Cores são variáveis CSS (`--surface`, `--ink`, `--brand`, `--line`...) expostas ao Tailwind
como nomes semânticos. Um tema é um bloco novo desses valores. Nenhum componente cita
`slate`, `rose`, `white`.

## 5. Estado vazio, carregamento e erro
Toda lista tem estado vazio (`Vazio`) que diz o que aparece ali. Carregamento mostra um texto
curto. Falha de dado opcional não derruba a tela.

## 6. Zona dinâmica com fallback
```tsx
<DynamicZone slot="resumo_financeiro" userId={userId}>
  <ResumoNativo summary={summary} />   {/* o fallback é também o caminho normal */}
</DynamicZone>
```
Um slot novo exige: entrada no schema, widget no registry e teste de fallback.

## 7. Preferência por pessoa
Preferência de interface (como o tema) é lida pelo `userId` da persona ativa e reage à troca
de persona. Não é lida uma só vez no layout raiz.

## 8. Dinheiro
Backend em `Decimal`, trânsito em string, exibição por `formatMoney`, coluna com `tnum`.

## 9. Testes
- Backend: `pytest`, um arquivo por área, nome que descreve a expectativa.
- Frontend: `vitest` + Testing Library, busca por rótulo e nome acessível.
- Mocks compartilhados vivem em módulo próprio (`tests/_mocks.ts`).
- Um `vi.mock` retorna sempre a mesma referência de objeto, para não disparar `useEffect` em
  laço.

## 10. Dado opcional falha suave
Blocos que acompanham a tela principal (o painel do dashboard) buscam o próprio dado e
validam que ele chegou como lista (`listaOuVazia`). Falhou ou veio torto: o bloco some, e o
saldo e o resto da tela seguem. Nunca deixe um dado opcional derrubar uma tela.

## 11. Estado decidido pelo valor exato
Quando um estado depende de um limite (orçamento), compare os valores, não o percentual
arredondado: R$ 100,01 contra R$ 100,00 é "estourado", mesmo que o percentual dê 100%.

## 12. Nomes
Identificadores em inglês, textos e comentários em português. Arquivo de rota em minúsculas,
componente em `PascalCase`, hook com prefixo `use`.
