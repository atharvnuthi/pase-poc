# Relatório da Monografia e Prompts das Imagens

Documento de trabalho dos autores. Não faz parte da monografia. Acompanha o arquivo `MONOGRAFIA_PASE.md`, que é a versão final do texto em Markdown, pronta para ser transposta ao modelo LaTeX (`ModeloTCC_Monografia_CC_Latex`).

---

## Parte 1 - Relatório

### 1.1 O que foi feito

1. **Texto completo da monografia** em `MONOGRAFIA_PASE.md` (cerca de 23 mil palavras), na estrutura de `estrutura.jpeg`, com duas adaptações combinadas: o Capítulo 2 é "Software na Era da IA Agêntica: Impactos e Lacunas" no lugar da Fundamentação Teórica, e Implementação e Validação formam um único capítulo (5).
2. **Pré-textuais**: capa e folha de rosto com o título novo, declaração ética, declaração de uso de IA generativa (exigida pelo `etica.tex` do modelo), Resumo e Abstract em parágrafo único, palavras-chave, listas de ilustrações, quadros, tabelas e siglas, e sumário.
3. **Pós-textuais**: referências em ABNT NBR 6023, três apêndices (prompts da PoC, contrato das Zonas Dinâmicas e reprodução da PoC) e a seção de anexos, com a justificativa de por que não há anexos.
4. **Verificação de todas as citações** contra os 22 PDFs de `Pesquisa-Artigos`. Cada artigo foi lido por inteiro e cada afirmação foi conferida com página e trecho literal. Os quatro trabalhos relacionados do Rascunho foram conferidos nas fontes originais (arXiv, Crossref).
5. **Dados reais da PoC** levantados do banco do PASE e do histórico do git: tarefas, execuções, *tokens*, descartes, violações, eventos de entrega da versão 1.0.0 e *commits* do agente. Todos os números do Capítulo 5 saem desses registros.
6. **Checagem automática de estilo** segundo o Tutorial de TCC: nenhuma frase passa de cerca de três linhas, nenhum parágrafo passa de dez linhas ou fica com menos de três, nenhum parágrafo tem uma só frase, e o texto não tem nenhum travessão (nem longo nem curto).

### 1.2 Como cada comentário do professor foi resolvido

| Comentário do professor | Como foi resolvido |
|---|---|
| Formatação geral, linha em branco entre parágrafos, "siga o modelo" | O texto vai para o modelo LaTeX da UFF, que controla margens, espaçamento e recuo. No Markdown não há formatação manual. |
| Lista de tabelas: uma lista por página | O LaTeX gera cada lista em página própria. Há listas separadas de figuras, de quadros e de tabelas. |
| Legendas "Título" nas figuras | Todas as 20 figuras têm título e fonte, e todas são citadas no texto. |
| Figura ilegível em 100%, sem legenda e sem citação | A imagem grande foi dividida em duas figuras (3 e 4), e há prompts de refinamento abaixo para gerar versões legíveis. |
| Termos em inglês em itálico (*internet-based*, *Task Layer*) | Todo termo estrangeiro está em itálico no Markdown (`*termo*`), inclusive nos títulos das seções. |
| DORA em maiúsculas? | Explicado como sigla na primeira menção: programa DORA (*DevOps Research and Assessment*). Entrou na lista de siglas. |
| Referência cruzada | No LaTeX, cada citação vira `\cite{chave}`. O mapa de chaves está na seção 1.6. |
| Resumo sem parágrafos e respondendo às cinco perguntas | O Resumo é um parágrafo único que cobre contexto, problema, proposta, método, resultados e contribuições. O Abstract segue o mesmo. |
| Introdução com contexto, motivação, objetivos, metodologia e organização | Seções 1.1 a 1.4, como no modelo. |
| Questões de pesquisa como pergunta deixam o texto informal | QP1 e QP2 foram reescritas de forma declarativa ("consiste em investigar se..."). |
| "Quais são as questões de pesquisa?" | QP1 e QP2 são explicitadas na Seção 1.2 e respondidas uma a uma na abertura do Capítulo 6. |
| "Explicite a dualidade" | O texto não usa mais "essa dualidade". A tensão é descrita diretamente (capacidade técnica contra confiabilidade). |
| Critérios de busca, inclusão e exclusão; bases SCOPUS/IEEE/ACM | Seção 1.3 descreve critérios, bases e composição do corpus. Ver pendência 1.5.1. |
| "Cite" (GitHub, Stack Overflow, ferramentas, estudos, experimentos, casos) | Toda afirmação sem fonte foi removida ou substituída por uma verificada. Os números sem fonte encontrada saíram (ver 1.3). |
| Casos Palantir, GE, TELUS, Fountain, Duck Creek sem citação | Ficaram só os casos que existem nas fontes, com número e citação: Rakuten, Zapier, Fountain e TELUS (Anthropic), Duck Creek (Vista). Palantir, GE Aerospace e energia nuclear saíram (nenhuma fonte os menciona). |
| "Lacunas importantes": enumere | Cada dimensão termina nomeando sua lacuna, e o Quadro 1 enumera as cinco com o requisito derivado. |
| "Concepção": enumere (i), (ii) | Enumerações explícitas em todo o texto: princípios, camadas, blocos, decisões e objetivos. |
| Cada um dos 4 princípios em parágrafo próprio | Feito na Seção 4.2. |
| "Três camadas": enumere | Feito em 4.2 e no Resumo. |
| "A PASE é uma IA que decide como se estrutura?" | Seção 4.1 esclarece que a PASE é uma especificação arquitetural definida pelos autores, e não uma entidade inteligente. O texto evita personificá-la. |
| Evite 3.2.1.1 (no máximo X.Y.Z) | A hierarquia vai no máximo a X.Y.Z (ex.: 4.3.4). O antigo nível X.Y.Z.W virou parágrafos com enumeração. |
| Evite bullets | Não há listas com marcadores no texto. Listas viraram enumerações em prosa ou quadros. |
| "Para um mesmo problema": qual? | Trecho reescrito. Todo o texto foi revisto para não deixar referentes vagos. |
| Síntese sem citação é interpretação dos autores | A Seção 2.6 é síntese dos autores, sem citações. Tudo antes dela tem fonte. |
| Validação: "se vocês propõem algo, precisam validar" | Capítulo 5 inteiro: PoC implementada, dois fluxos de ponta a ponta, 533 testes, oito roteiros, métricas e resultados reais. |
| "É tudo muito teórico"; "protótipo funcional deveria existir" | Resolvido pelo Capítulo 5. A limitação "não foi validada empiricamente" saiu da conclusão. |
| Conclusão informal ("partiu de uma constatação e de uma tensão") | Conclusão reescrita em registro formal. |
| Conclusão com 3 seções: contribuições, limitações e trabalhos futuros, e limitações do estudo da revisão | Seções 6.1, 6.2 e 6.3. A 6.2 inclui as limitações da revisão (narrativa, com versões preliminares e relatórios de indústria). |
| Banca sugerida pelo título | Não tratado no texto. Fica com os autores e o orientador. |

### 1.3 Correções de conteúdo encontradas na verificação das citações

Estas afirmações estavam na versão anterior e **não se sustentam** nas fontes. Todas foram removidas ou corrigidas no texto novo.

1. **Mukti e Trisilia (2025)** é uma análise bibliométrica de 20 mil documentos e não tem participantes. A afirmação "usuários são mais rápidos, mas confiam menos, com erro equivalente" não está no artigo. O artigo agora sustenta apenas a periodização em três fases e a recomendação de explicar cada recomendação.
2. **Jamali et al. (2025)** não mediu retenção, autonomia, confiança nem sinais de frustração (cliques repetidos, tempo e erros). O artigo agora sustenta o compromisso entre eficiência e engajamento e o problema da "IA invisível".
3. **"Hiper-adaptativo", "user experience reversion"**, serendipidade, comoditização de contadores e descrições estigmatizantes de pessoas com deficiência não estão em nenhuma fonte. Saíram. "Hiper-personalização" passou a ser apresentada como termo deste trabalho.
4. **Vista** não usa a tríade *internet-based*, *AI-based* e *agent-based*. Sua tríade é "software como produto, como serviço, como trabalhador", e o texto usa essa.
5. **Fountain** está no relatório da Anthropic, não no da Vista. **Palantir, GE Aerospace e energia nuclear** não estão em nenhuma fonte.
6. **"395 artigos e 112 tarefas"** misturava dois trabalhos: são 395 artigos e 85 tarefas em Hou et al. (2024), e 926 estudos e 112 tarefas em Zhang et al. (2026). O texto separa os dois e traz os percentuais de requisitos (3,9%) e projeto (0,92%).
7. **Stack Overflow 92% e GitHub 25 a 30% de rejeição** não estão em nenhuma fonte. Saíram.
8. **"Architectural Mimicry"** aparece só como expressão em minúsculas em Kravchuk-Kirilyuk, Graciolli e Amin (2025). O texto a apresenta como "mimetismo arquitetural", descrito pelos autores.
9. **Shen e Tamkin (2026)**: os 17% são o efeito médio do grupo com IA, e não de quem delegou muito. Quem delegou ficou entre 24% e 39%, e quem usou a IA para entender ficou entre 65% e 86%. O texto agora diz isso.
10. **Chhabra et al. (2026)**: os percentuais de vulnerabilidade de agentes (94,4%, 83,3% e 100%) são de Lupinacci et al. (2025), citados por Chhabra. Agora estão como "apud".
11. **Mercado de trabalho**: "dezenas de milhões de empregos", desigualdade geográfica, reconversão por idade, *call centers* e "geração perdida" não estão em nenhuma fonte. A Seção 2.5 foi reescrita com dados verificados de Anthropic, SPARK, WEF, DORA e Shen e Tamkin.
12. **GDPR, AI Act e viés em contratação ou crédito** não estão em nenhuma fonte. Saíram da Seção 2.4. A LGPD aparece só na declaração ética.
13. **Gartner e McKinsey** não estão na pasta de artigos e as páginas não puderam ser conferidas (acesso bloqueado). Foram trocados por ISG, SPARK e WEF, que sustentam os mesmos argumentos com dados verificados.
14. **LLM-Cure** foi publicado em 2026 (TOSEM v. 35, n. 4), e não em 2025 como no Rascunho.
15. **"Revisão sistemática"** passou a ser chamada de revisão narrativa estruturada, que é o que foi feito. Isso é mais honesto e responde ao comentário do professor sobre critérios. Ver pendência 1.5.1.

### 1.4 Decisões de projeto do texto

1. **Título novo** em todo o texto. "Topologia PASE" virou "Arquitetura PASE".
2. **Quadros e tabelas**: segundo a ABNT, quadro tem conteúdo textual e tabela tem dados numéricos. São 6 quadros e 2 tabelas. No abnTeX2, quadro usa o ambiente `quadro` e a lista `\listofquadros`.
3. **Capítulo 2 reescrito como contexto que leva à PASE**: cada dimensão termina na sua lacuna, e a Seção 2.6 converte as lacunas em cinco requisitos (R1 a R5), que o Capítulo 4 retoma um a um na Seção 4.6.
4. **Proposta atualizada com o que a implementação ensinou**, mantendo o texto revisado e sem detalhes de implementação:
   - aprovação humana do plano por risco;
   - critérios de aceite no planejamento;
   - revisão independente com evidência conferida por código;
   - entrega em estágios (integração, versão candidata e produção);
   - trava de custo preditiva;
   - agrupamento de tickets na captação passiva;
   - encaminhamento de pedidos ao UPA quando a zona já existe;
   - atualização do contexto aceita por pessoa;
   - reversão simétrica;
   - regra geral "o modelo aponta a evidência e o código confere".
5. **Rascunho incorporado e corrigido**:
   - figuras renumeradas de 7 a 20;
   - a referência à "Seção 5.2" passou a ser 6.2;
   - o capítulo das camadas passou a ser o 4;
   - "cerca de 450 testes" passou a ser 533 (433 + 53 + 47, contados nas suítes);
   - foram acrescentados a linha do tempo real da tarefa nº 6, a Tabela 1, as métricas e o Quadro 6 de lições.

### 1.5 O que falta fazer (pendências dos autores)

#### 1.5.1 Confirmações no texto

1. **Seção 1.3 (bases e critérios)**: o texto descreve as bases e os critérios de forma compatível com o corpus, mas não inventa *strings* de busca nem números de triagem. Se vocês tiverem as *strings* e quantos trabalhos foram encontrados e descartados, acrescentem. Isso responde melhor ao comentário do professor.
2. **Declaração de uso de IA generativa**: confirmar as versões do Claude usadas e acrescentar outras ferramentas (corretor, tradutor).
3. **Apêndice C**: decidir como a banca acessa o repositório, que hoje é privado no GitHub.
4. **Dedicatória e agradecimentos**: opcionais, a redigir.
5. **Ficha catalográfica**: gerar no sistema da biblioteca da UFF na versão final.

#### 1.5.2 Referências a completar

1. **BURTE (2025)**: o PDF não traz volume, número, ano nem DOI. Conferir no site da revista *AI Systems Engineering*.
2. **ABSHER e KUPRIYANOVA (2025)**, relatório da ISG: inserir a URL oficial. Só foi encontrada uma cópia em site de terceiros.
3. **SPARK (2026)**: o editor é ambíguo no PDF ("SPARK Intelligence" ou "JLL Spark"). Confirmar a autoria.
4. **HE, TREUDE e LO (2025)**: foi citada a versão do arXiv lida. Se quiserem, troquem pela versão publicada na TOSEM, conferindo o DOI.
5. **ARORA et al. (2025)**: o relatório não imprime o ano. Está "[2025]", entre colchetes, como manda a ABNT.

#### 1.5.3 Capturas de tela do Capítulo 5 (14 figuras)

As capturas devem ser legíveis com zoom de 100%. Uma janela de cerca de 1280 px de largura funciona bem.

| Figura | O que capturar |
|---|---|
| 7 | Painel > Tarefas > aba Descartadas |
| 8 | Painel > Dependências |
| 9 | Painel > Sistema |
| 10 | Painel > Contexto |
| 11 | FinTrack em `/dashboard` no estado do *commit* `09dff0d` (antes do modo escuro) |
| 12 | Painel > Nova demanda e aba Candidatas |
| 13 | Tarefa nº 6, aba Planejamento |
| 14 | Tarefa nº 6, aba Execuções |
| 15 | Tarefa nº 6, aba Homologação |
| 16 | Painel > Entrega, com a release 1.0.0 |
| 17 | FinTrack em `/dashboard`, estado atual, tema escuro, mesmo enquadramento da Figura 11 |
| 18 | Painel > Zonas > Simulador, com o payload ativo e o JSON expandido |
| 19 | FinTrack em `/dashboard` como Ana e como Clara, lado a lado |
| 20 | Painel > Zonas > Injetor e lista de Violações |

#### 1.5.4 Figuras dos Capítulos 2 e 4

1. **Figura 1**: recortar o gráfico da Bain da p. 11 do PDF da Vista.
2. **Figuras 2 a 6**: gerar com os prompts da Parte 2.

#### 1.5.5 Transposição para o LaTeX

Fazer só depois de vocês aprovarem este Markdown. Vai em `capitulo1.tex` a `capitulo6.tex`, `resumos.tex`, `siglas.tex`, `etica.tex`, `capa.tex`, `monografia.bib` e `apendices.tex`. A pasta de anexos fica vazia ou é removida do `principal.tex`. É preciso também acrescentar `\listofquadros` ao `principal.tex`.

### 1.6 Mapa de chaves BibTeX (para o `monografia.bib`)

| Citação no texto | Chave sugerida |
|---|---|
| ABOU ALI; DORNAIKA, 2025 | `abouali2025agentic` |
| ABSHER; KUPRIYANOVA, 2025 | `isg2025agentic` |
| ANTHROPIC, 2026 | `anthropic2026trends` |
| ARORA et al., 2025 | `arora2025selfevolving` |
| ASSI; HASSAN; ZOU, 2026 | `assi2026llmcure` |
| BIENIEK; RAHOUTI; VERMA, 2024 | `bieniek2024generative` |
| BURTE, 2025 | `burte2025sdlc` |
| CAO; JIANG; XIA, 2025 | `cao2025malleable` |
| CHHABRA et al., 2026 | `chhabra2026security` |
| CROWDSTRIKE, 2026 | `crowdstrike2026threat` |
| GOOGLE CLOUD, 2025 | `dora2025` |
| HE; TREUDE; LO, 2025 | `he2025lma` |
| HONG et al., 2024 | `hong2024metagpt` |
| HOU et al., 2024 | `hou2024llm4se` |
| JAMALI et al., 2025 | `jamali2025adaptive` |
| JIMENEZ et al., 2024 | `jimenez2024swebench` |
| KIM et al., 2026 | `kim2026scaling` |
| KRAVCHUK-KIRILYUK; GRACIOLLI; AMIN, 2025 | `kravchuk2025modular` |
| MUKTI; TRISILIA, 2025 | `mukti2025adaptive` |
| SAROYA; MACNEILL, 2026 | `vista2026outlook` |
| SHEN; TAMKIN, 2026 | `shen2026skill` |
| SPARK, 2026 | `spark2026cio` |
| TAKERNGSAKSIRI et al., 2025 | `takerngsaksiri2025hula` |
| TAN et al., 2025 | `tan2025alp` |
| WORLD ECONOMIC FORUM; ACCENTURE, 2026 | `wef2026organizational` |
| ZHANG et al., 2026 | `zhang2026survey` |

As citações com "apud" (Bain & Company, Menlo Ventures e Lupinacci et al.) não entram na lista de referências, como manda a NBR 10520. Se o orientador preferir, podem entrar em nota de rodapé.

---

## Parte 2 - Prompts de refinamento das imagens

### Regras comuns a todas as figuras

O professor reclamou que a figura antiga só era legível com zoom de quase 200%. Use estas regras em todos os prompts:

1. **Tamanho e formato**: a figura precisa ser legível impressa em uma página A4 retrato, a 100% de zoom. Isso dá largura útil de cerca de 16 cm. Use proporção retrato ou quadrada, nunca uma faixa horizontal muito larga.
2. **Fonte**: no mínimo equivalente a 10 pt na página impressa. Sem sombras nem gradientes.
3. **Estilo**: fundo branco, sans-serif, linhas finas, estilo acadêmico. Ícones mínimos, sem logotipos e sem decoração.
4. **Idioma**: todos os rótulos em português, exatamente como estão escritos abaixo.
5. **Cores de seta, com legenda pequena no canto**:
   - azul para fluxo de tarefas;
   - verde para aprovação humana;
   - vermelho para recusa ou descarte;
   - roxo para leitura e escrita nas bases de conhecimento.
6. **Pessoa**: marcar com um pequeno ícone de pessoa cada ponto em que uma pessoa decide.

### Prompt da Figura 2 - Visão geral da Arquitetura PASE (refina `model-image-1.png`)

```
Create a clean academic architecture diagram, white background, portrait-friendly (aspect ratio about 4:3), readable when printed at 16 cm width. All labels in Portuguese exactly as written.

Top band: three database cylinders side by side labeled "Contexto geral do projeto", "Histórico de tarefas" and "Histórico de descartes" (the last one with a light red outline).

Middle: three large rounded rectangles left to right, each with a small header tag:
1. "Camada de Tarefas" containing, in sequence with blue arrows: "Formação de Requisitos" (with three small icons labeled "Usuários", "Equipe", "IA"), "Normalização", "Avaliador de Zonas Dinâmicas", "Motor de Filtragem". Output arrow to a cylinder "Tarefas candidatas" placed between layers 1 and 2.
2. "Camada de Orquestração" containing "Motor de Orquestração" connected below to a small cylinder "Grafo de dependências (DAG)". Mark a person icon labeled "Decisão humana" on the arrow coming from "Tarefas candidatas".
3. "Camada de Execução" containing "Executor de Tarefas" (connected below to a small cylinder "Planejamentos técnicos") and, separately, an octagon "User Personalization Agent (UPA)".

Right side: a box "Código em produção" with an attached orange sub-box "Zonas Dinâmicas". Arrow from the UPA (green, dashed) into "Zonas Dinâmicas" labeled "personalização em tempo de execução".

Between Orchestration and production: two small hexagons "Tarefa APROVADA" (green) and "Tarefa RECUSADA" (red), each with a person icon. Green arrow from APROVADA to "Código em produção" passing through three small pills in sequence: "Integração", "Versão candidata", "Produção", with a person icon on the last pill labeled "Publicação". Red arrow from RECUSADA up to "Histórico de descartes".

Purple arrows: the three cylinders feed "Camada de Tarefas"; APROVADA writes to "Histórico de tarefas" and, through a small person icon labeled "aceite", to "Contexto geral do projeto".
A yellow chevron "Reavaliação Cíclica" reads from "Histórico de descartes" and points back into "Tarefas candidatas".

Small legend in the bottom-right corner explaining arrow colors and the person icon.
```

### Prompt da Figura 3 - Camada de Tarefas (refina a metade esquerda de `model-image-2.png`)

```
Academic flow diagram, white background, portrait orientation, readable at 16 cm width, Portuguese labels exactly as written, minimum font equivalent to 10 pt.

Top section, a wide box titled "Formação de Requisitos" with three dashed columns:
- "Agentes Externos": sub-box "Captação Ativa" with "Sugestões do usuário" → "Avaliação de baixa latência"; sub-box "Captação Passiva" with "Tickets e interações" → "Agrupamento por tema" → "Extração de intenção".
- "Agentes Internos": "Sugestões Funcionais"; "Sugestões de Engenharia" → "Etapa de Autorização".
- "Inteligência Artificial": "Geração Exploratória", "Análise de Lacunas", "Prospecção Competitiva" (draw the last one with a dashed border and a tiny note "fora da PoC").

Below: "Normalização" (gray box) → "Avaliador de Zonas Dinâmicas" with two outputs: "Funcionalidade nativa" and "Tarefa de parametrização", plus a third green arrow "Zona já existe → UPA".

Bottom: a box "Motor de Filtragem de Tarefas" containing three blue boxes in sequence: "Memória Histórica" → "Coerência Sistêmica" → "Qualificação e Metadados". A loop arrow from "Coerência Sistêmica" back to "Memória Histórica" labeled "revalida após ajuste". Red arrows from the first two boxes to a red-outlined cylinder "Histórico de descartes". A lilac box "Reavaliação Cíclica" reads the descartes cylinder and points back into the filter.
Output arrow from "Qualificação e Metadados" to a cylinder "Tarefas candidatas" annotated "impacto · complexidade · confiança · risco".
The "Sugestões de Engenharia" path bypasses "Memória Histórica" and "Coerência Sistêmica" with a dashed arrow straight to "Qualificação e Metadados", labeled "desvio autorizado".
Top-right: three small cylinders "Contexto geral do projeto", "Histórico de tarefas", "Histórico de descartes" feeding the filter (purple arrows).
```

### Prompt da Figura 4 - Camadas de Orquestração e Execução (refina a metade direita de `model-image-2.png`)

```
Academic flow diagram, white background, portrait orientation, readable at 16 cm width, Portuguese labels exactly as written.

Left column, box "Motor de Orquestração":
"Tarefas candidatas" (cylinder) → "Priorização" (with a self-loop labeled "fator de urgência") → person icon "Aprovar / Recusar / Editar".
Approved → "Executor: Fase de Planejamento" (in the Execution column) → "Documento de Planejamento Técnico" (pink box listing: arquivos afetados, roteiro, critérios de aceite, estimativas).
→ diamond "Risco médio ou alto?" → yes: person icon "Aprovação do plano" ; no: direct.
→ "Grafo de dependências (DAG)" → "Pronta para despacho".

Right column, box "Camada de Execução":
"Executor: Fase de Execução" inside a dashed boundary labeled "ambiente isolado (clone e ramo exclusivo, sem rede)" containing a small loop: "Gerar código" → "Verificação automática" (tipos, testes, build de produção, rede de regressão, teste novo, cobertura) → back to "Gerar código" labeled "correção local".
→ "Revisão independente" (separate agent icon) with note "evidência conferida por código".
→ "Pacote de homologação" (diff, verificações, parecer, transcrição, custo).

Back in Orchestration: "Em homologação" → person icon with three outputs: "Aprovar" (green) → pills "Integração" → "Versão candidata" → person icon "Publicação" → "Produção"; "Ajustar" (blue loop back to the Execution box); "Recusar" (red) → cylinder "Histórico de descartes".

Failure handling: from the Execution box a red dashed arrow "falha" → "Tratamento de falhas" → "Reexecução" (back) or, labeled "limite de tentativas ou trava de custo", → "Suspensa" → person icon "Retomar / Replanejar / Cancelar".

Top right: a teal box "Ciclo de Auditoria" pointing into "Tarefas candidatas" labeled "sugestão de engenharia".
Bottom: two cylinders "Contexto geral do projeto" and "Histórico de tarefas" receiving purple arrows from "Aprovar", the context one through a small person icon labeled "aceite da atualização".
```

### Prompt da Figura 5 - Ciclo de vida de uma tarefa (figura nova)

```
UML-style state diagram, white background, landscape but compact (fits 16 cm width), Portuguese labels exactly as written, rounded state boxes, initial black dot.

States: "Candidata", "Em Planejamento", "Aguardando Aprovação do Plano" (dashed border, note "quando exigida"), "Pronta para Despacho", "Em Execução", "Suspensa", "Em Homologação", "Finalizada".
Transitions (label each):
Candidata → Em Planejamento: "aprovada (pessoa)"
Candidata → Finalizada: "recusada (pessoa)"
Em Planejamento → Aguardando Aprovação do Plano: "risco médio/alto"
Em Planejamento → Pronta para Despacho: "risco baixo"
Aguardando Aprovação do Plano → Pronta para Despacho: "plano aprovado (pessoa)"
Aguardando Aprovação do Plano → Em Planejamento: "devolvido com orientação"
Pronta para Despacho → Em Execução: "dependências resolvidas"
Em Execução → Em Homologação: "verificada e revisada"
Em Execução → Suspensa: "limite de tentativas ou trava de custo"
Suspensa → Em Execução: "retomada (pessoa)"
Suspensa → Finalizada: "cancelada (pessoa)"
Em Homologação → Em Execução: "ajuste solicitado (pessoa)"
Em Homologação → Finalizada: "aprovada ou recusada (pessoa)"

Inside "Finalizada" show a small sub-strip with three pills for the approved path: "Integração" → "Versão candidata" → "Produção".
Mark every transition decided by a person with a small person icon. Legend: "toda transição gera registro (origem, destino, momento, motivo)".
```

### Prompt da Figura 6 - Contrato rígido de uma Zona Dinâmica (refina o exemplo do banner)

```
Two-panel explanatory diagram, white background, portrait, readable at 16 cm width, Portuguese labels exactly as written.

Center top: a box "Contrato da zona (Hard Constraints)" listing: "componente: shortcut_list | summary_card | alert_banner", "rótulo: até 40 caracteres", "até 3 itens", "links: apenas rotas internas".

Left panel titled "Payload válido": a small JSON card {"widget": "alert_banner", "label": "Gastos acima da média", "tone": "atencao"} → green check "validação no servidor" → green check "validação no cliente" → a mock app screen showing a small banner with a tag "personalizado".

Right panel titled "Payload recusado": a JSON card with a 500-character label and "href": "https://site-externo.com" → (dashed arrow labeled "injetado sem passar pelo servidor") → red X "validação no cliente" → the same mock screen showing the native default component (no tag) and a small log card "violação registrada: motivo + conteúdo bruto".

Footer note: "A IA nunca gera código executável: o payload só preenche propriedades de componentes já existentes."
```
