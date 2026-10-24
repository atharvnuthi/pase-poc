# Princípios de Arquitetura

Regras de projeto que valem para qualquer mudança, acima de gosto pessoal.

1. **Reuse antes de criar.** Antes de escrever algo novo, procure se já existe: helper,
   primitiva de UI, validação, formatador. Um paralelo ao que existe é dívida.
2. **Falhe de forma suave.** Se a personalização, o tema ou um dado opcional falhar, a tela
   normal continua funcionando. Nenhum recurso opcional pode derrubar uma tela.
3. **Contrato primeiro.** Tudo que cruza uma fronteira (API, zona dinâmica) tem um formato
   definido e validado nas duas pontas. A validação do lado de quem consome é a decisiva.
4. **A verdade mora em um lugar.** Cores em tokens, dinheiro em `Decimal`, rótulos em um
   cliente. Duplicar a fonte de verdade é o começo da divergência.
5. **Estado do usuário não mora na memória do processo.** Preferência e sessão que precisam
   sobreviver a um reinício ficam em armazenamento durável.
6. **O que é medido não escreve a régua.** Teste que protege o produto não é alterado por
   quem está entregando a mudança.
7. **Simples agora, extensível depois.** Uma zona, três widgets: o catálogo cresce por
   decisão, com contrato e testes, nunca por improviso.
8. **Acessível por construção.** Rótulo associado, nome acessível, foco visível. Se a
   acessibilidade quebra, a suíte de testes quebra.
9. **Nada de segurança por aparência.** Não se acrescenta autenticação, criptografia ou
   permissão que o contexto do produto não exige: elas dão uma falsa sensação de proteção.
10. **Decisão registrada.** Mudança de rumo vira um registro em `adrs/`, com o porquê.
