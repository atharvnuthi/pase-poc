# Guia de execução dos fluxos e das capturas de tela

Roteiro para produzir as figuras dos Capítulos 5 e 6 a partir de um estado limpo.
A numeração das figuras segue a sequência corrigida da monografia (Capítulo 2: Figuras 1 a 3;
Capítulo 4: Figuras 4 a 8; Capítulo 5: Figuras 9 a 12; Capítulo 6: Figuras 13 a 23).

## 0. Antes de começar

- Serviços no ar: painel do PASE em <http://localhost:3000>, FinTrack em <http://localhost:3001>.
- Estado limpo: banco recriado (`make reset-all`), nenhuma branch `develop`, `release/*` ou
  tag no repositório, FinTrack sem tema escuro.
- **Não edite nem salve arquivos do repositório durante a sessão.** A publicação faz `merge`
  na `master` da sua árvore de trabalho; arquivos rastreados modificados podem impedir o merge.
- Navegador: janela de 1440 × 900, zoom 100%, sem barras de favoritos. Para a Figura 22 você vai
  precisar de **duas janelas com armazenamento separado** (uma normal e uma anônima), porque a
  persona do FinTrack fica no `localStorage` do navegador.
- Para as capturas, prefira recortar a área útil (sem a barra do sistema operacional). No
  Windows: `Win + Shift + S`.
- Tempo total estimado: 40 a 70 minutos. A execução da tarefa leva de 5 a 20 minutos e gasta
  tokens reais (ordem de 100 a 300 mil).

---

## FLUXO 1 — da demanda ao código em produção

### Passo 1 · FinTrack antes da solicitação → **Figura 13**

1. Abra <http://localhost:3001>, escolha **Ana**.
2. Vá ao **Dashboard**.
3. Capture a tela inteira, com o cabeçalho visível (sem nenhum botão de tema).

> **Figura 13 - FinTrack antes da solicitação: interface apenas em tema claro, sem controle de tema**

### Passo 2 · O funil barrando propostas → **Figura 9** (Capítulo 5)

No painel, **Tarefas → Nova demanda**. Envie, uma de cada vez (autor: o seu nome):

| Texto da demanda | Resultado esperado |
|---|---|
| `Quero acompanhar minha carteira de ações e meus investimentos dentro do FinTrack.` | descartada por incoerência, citando a linha "Investimentos, câmbio e múltiplas moedas." |
| `Seria ótimo baixar minhas transações numa planilha CSV para abrir no Excel.` | descartada por duplicidade com a funcionalidade já implementada "Exportação das transações em CSV" |
| `Que tal o app minerar bitcoin enquanto fica aberto, para eu ganhar um dinheiro extra?` | descartada por duplicidade com o descarte histórico "Minerar criptomoedas no app" |

Depois abra **Tarefas → aba Descartadas** e capture a lista com os motivos visíveis (se der,
expanda a da carteira de ações, que mostra o trecho citado).

> **Figura 9 - Descartadas: propostas barradas pelo funil por duplicidade ou incoerência, com o motivo de cada descarte**

Se alguma das três tiver um desfecho diferente do esperado, anote-o: o texto da monografia
descreve o desfecho que de fato aparecer.

### Passo 3 · A demanda em linguagem natural → **Figura 14**

A demanda entra pelo canal do usuário (captação ativa), como prevê a Seção 4.3.1:

1. No FinTrack, ainda como **Ana**, clique em **Sugerir melhoria** e escreva:
   `À noite o FinTrack fica muito claro e cansa a vista. Queria poder trocar para um tema escuro.`
2. Envie. O próprio modal mostra o resultado do funil.
3. Capture o modal com a resposta (**Figura 14a**).
4. No painel, **Tarefas → aba Candidatas**: a nova tarefa aparece com impacto, complexidade,
   confiança e risco. Capture a linha da candidata (**Figura 14b**).

> **Figura 14 - A solicitação: (a) demanda em linguagem natural enviada pela usuária no FinTrack; (b) tarefa candidata qualificada no painel do PASE, aguardando decisão**

Se a sugestão for encaminhada a uma zona em vez de virar candidata, envie o mesmo texto pelo
painel (**Tarefas → Nova demanda**) e use essa captura na Figura 14b.

### Passo 4 · Aprovar a candidata e o plano → **Figura 15**

1. Na linha da candidata, **marque "revisar o plano"** e clique em **Aprovar**. A tarefa vai a
   *em planejamento* e, em 1 a 3 minutos, para em *aguardando aprovação do plano*.
2. Abra a tarefa (clique no título). Na aba **Planejamento** aparecem o trilho do ciclo de vida,
   os critérios de aceite (C1, C2…), o mapeamento de impacto (arquivo e ação), o tempo, o custo e
   o risco técnico estimados.
3. Capture a página com o trilho, os critérios e o documento de planejamento (**Figura 15**).
4. Leia os critérios. Se fizerem sentido, clique em **Aprovar plano**.

> **Figura 15 - Documento de Planejamento Técnico: arquivos previstos e ação sobre cada um, critérios de aceite, estimativas e trilho do ciclo de vida**

Anote: número da tarefa, quantidade de arquivos previstos, quantidade de critérios.

### Passo 5 · Execução e verificação → **Figura 16**

1. A tarefa passa a *em execução*. Espere até *em homologação* (5 a 20 minutos). O painel
   atualiza sozinho.
2. Se ela for **suspensa**, abra-a, leia o motivo e use **Retomar** (com uma orientação, se o
   problema for claro). Anote o ocorrido; ele também é resultado.
3. Na aba **Execuções**, abra a última execução: diferenças de código, registro das verificações
   (ruff, tsc, vitest, next build, cobertura, rede de regressão) e transcrição da interação com o
   modelo (que começa pelo planejamento e termina na revisão).
4. Capture o diff com a lista de verificações aprovadas (**Figura 16**). Uma segunda captura da
   transcrição, se couber, pode virar 16b.

> **Figura 16 - Execução registrada: diferenças de código, verificações automáticas e transcrição integral da interação com os modelos**

Anote: tokens consumidos e duração da execução (aparecem na linha da execução).

### Passo 6 · Homologação → **Figura 17**

1. Aba **Homologação**: parecer da revisão independente, critério a critério, com o trecho de
   código e o trecho de teste citados, o modelo revisor e eventuais avisos.
2. Capture o parecer e os botões de decisão (**Figura 17**).
3. Clique em **Aprovar e integrar** e escreva a justificativa, por exemplo:
   `Critérios C1 a C5 conferidos no parecer; diff restrito ao tema; verificações verdes.`

> **Figura 17 - Homologação: parecer da revisão independente por critério de aceite e decisão do gestor**

A aprovação integra a tarefa na `develop`, e o CI da `develop` roda em segundo plano.

### Passo 7 · Entrega em estágios → **Figuras 18 e 19**

Tela **Entrega** do painel:

1. Em **Develop**, espere o CI passar e clique em **Aprovar nos testes**. Nota:
   `CI da develop verde; comportamento conferido pelos critérios da revisão.`
2. Em **Releases**, clique em **Nova release** e confirme a versão **1.0.0**.
3. Volte à tarefa na Develop e clique em **Incluir na 1.0.0**.
4. No changelog, escreva `- Tema escuro por persona, com botão em todas as telas.` e
   **Salvar changelog**.
5. **Validar release** (roda as suítes completas; alguns minutos).
6. **Abrir Pull Request**. O PASE envia a `master` e a `release/1.0.0` ao GitHub e abre o PR.
7. Capture a tela Entrega com a release validada, o PR aberto e o rastro do pipeline (**Figura 18**).
8. Abra o link do PR no GitHub e capture a página do PR, com o corpo gerado pelo PASE (**Figura 19**).
9. De volta ao painel, **Publicar**, com a aprovação por escrito, por exemplo:
   `Aprovo a publicação da 1.0.0: tarefa homologada, aprovada nos testes e validada.`

> **Figura 18 - Tela Entrega: tarefa no ramo de integração, versão 1.0.0 validada e publicação sob aprovação humana**
>
> **Figura 19 - Pull request da versão 1.0.0 aberto pelo PASE no GitHub, com o corpo exigido pelo guia de fluxo de ramos**

Anote: número do PR, e rode depois `git log --oneline -5` para registrar os commits da tarefa,
da integração e da release.

### Passo 8 · O produto depois → **Figura 20**

1. Recarregue o FinTrack como **Ana** no **Dashboard**. O botão **Usar tema escuro** está no
   cabeçalho.
2. Clique nele e capture a tela no mesmo enquadramento da Figura 13 (**Figura 20**).
3. Opcional: clique em **Sugerir melhoria → Minhas sugestões**; a sugestão do Passo 3 aparece
   como publicada. Capture como **Figura 20b** (mostra a devolutiva ao usuário, Seção 4.3.1).
4. Volte ao tema claro antes do Fluxo 2 (a preferência é por persona).

> **Figura 20 - FinTrack após a entrega: botão "Usar tema escuro" e paleta escura aplicada a todas as telas**

### Figuras do painel para o Capítulo 5 (tirar agora)

- **Figura 10 · Dependências.** Menu **Dependências**: o grafo com os nós coloridos por estado.
  Fica mais informativo com duas tarefas ou mais. Opcional: antes do Passo 5 terminar, envie e
  aprove uma segunda demanda que mexa no cabeçalho, como
  `Mostrar no rodapé de todas as telas a data da última atualização dos dados.`, e capture o
  grafo com a aresta de arquivo entre as duas. Essa segunda tarefa pode ser **recusada** na
  homologação com justificativa, o que mostra a recusa indo ao histórico de descartes.
- **Figura 11 · Sistema.** Menu **Sistema**: fila, memória vetorial, modelos e custo,
  guardrails, prompts versionados e manutenção.
- **Figura 12 · Contexto.** Menu **Contexto**: abra o documento `scope-and-constraints` e capture
  o texto com a indicação das etapas que o leem.

> **Figura 10 - Dependências: grafo das tarefas, com nós coloridos por estado e arestas de dependência**
>
> **Figura 11 - Sistema: fila de execução, memória vetorial, consumo acumulado, travas e prompts versionados**
>
> **Figura 12 - Contexto: documentos do produto versionados no banco e as etapas do ciclo que leem cada um**

---

## FLUXO 2 — personalização em tempo de execução

### Passo 9 · O UPA personaliza a zona de Ana → **Figura 21**

1. Painel, **Zonas dinâmicas → Simulador**: zona `resumo_financeiro`, persona **Ana**,
   **Simular uso intenso**. O simulador registra cinco acessos a `/relatorios` e roda a regra
   da zona.
2. Na lista de payloads, expanda o JSON do payload ativo de Ana. Em **Avaliações**, a avaliação
   registrada mostra a decisão e o motivo do agente.
3. Capture o simulador e o payload expandido (**Figura 21**).

> **Figura 21 - Simulador do painel: o uso intenso de relatórios pela persona Ana aciona a zona do painel inicial e o UPA gera um payload declarativo**

Se o agente decidir **não** personalizar (ele pode concluir que não há o que fazer), rode o
simulador de novo: ele ignora o intervalo mínimo entre avaliações. A decisão negativa fica
registrada em **Avaliações** e também é evidência.

### Passo 10 · Ana personalizada, Clara nativa → **Figura 22**

1. Janela normal: FinTrack como **Ana**, **Dashboard**. O bloco personalizado aparece com o selo
   "personalizado" e a ação "voltar ao padrão".
2. Janela anônima: FinTrack como **Clara**, **Dashboard**. O mesmo lugar mostra o componente
   nativo.
3. Ponha as duas lado a lado e capture (**Figura 22**). **Não** clique em "voltar ao padrão"
   antes da captura.

> **Figura 22 - Personalização em execução: Ana vê o componente gerado pelo UPA, com o selo "personalizado", enquanto Clara mantém o componente nativo**

### Passo 11 · Defesa em profundidade → **Figura 23**

No painel, **Zonas dinâmicas → Injetor**, zona `resumo_financeiro`, persona **Clara**. Injete os
três payloads abaixo, **um de cada vez**. Depois de cada injeção, recarregue o Dashboard da Clara
na janela anônima: o componente nativo continua lá.

Rótulo acima do limite:

```json
{"widget": "alert_banner", "label": "Este aviso tem um texto muito maior que o limite de quarenta caracteres", "tone": "atencao"}
```

Link externo:

```json
{"widget": "shortcut_list", "label": "Atalhos", "maxItems": 1, "items": [{"label": "Ganhe dinheiro", "href": "https://exemplo-malicioso.com"}]}
```

Componente fora do catálogo:

```json
{"widget": "iframe_injector", "label": "Conteúdo externo", "src": "https://exemplo-malicioso.com"}
```

Em seguida, role até **Violações**: as três aparecem como "recusado no cliente", com o motivo e o
conteúdo bruto. Capture o injetor e a lista (**Figura 23**).

> **Figura 23 - Defesa em profundidade: payloads maliciosos injetados sem validação do servidor, recusados pelo cliente e registrados como violação**

### Passo 12 · Opcional: o usuário volta ao padrão

Como Ana, clique em **voltar ao padrão** no bloco personalizado. O componente nativo volta, e a
personalização automática dessa zona não volta mais para ela (a revogação é durável). Não é
figura obrigatória; é a evidência do "reversível ao padrão" do requisito R3.

---

## Depois das capturas: o que me mandar

Para eu fechar o texto dos Capítulos 5 e 6 com os números reais:

1. Número da tarefa do modo escuro e quantidades de arquivos previstos e de critérios.
2. Tokens e duração da execução; tokens estimados no plano; se houve suspensão ou retomada.
3. Número do PR e a saída de `git log --oneline -6`.
4. Desfecho das três propostas do Passo 2.
5. A data em que rodou.
