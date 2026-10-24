# Capítulos 5 e 6 revisados

Texto para substituir os Capítulos 5 e 6 do arquivo `MONOGRAFIA_PASE_revisao.docx`, conferido contra
o código. Os trechos marcados com «» dependem da execução dos fluxos e devem ser preenchidos com os
números anotados no guia de capturas (`guia-capturas-fluxos.md`). As figuras seguem a numeração
corrigida: Capítulo 5, Figuras 9 a 12; Capítulo 6, Figuras 13 a 23.

---

# 5 IMPLEMENTAÇÃO

Para demonstrar que a Arquitetura PASE pode ser construída, foi implementada uma prova de conceito
(*Proof of Concept*, PoC) com o núcleo das três camadas descritas no Capítulo 4. Cada componente da
implementação corresponde a um componente da arquitetura, e as garantias que a arquitetura atribui a
código ou a pessoas foram implementadas dessa forma. Este capítulo apresenta as tecnologias usadas, a
implementação de cada camada, o que ficou fora do escopo e o painel de controle.

## 5.1 Visão Geral e Tecnologias

A **prova de conceito separa dois sistemas**. O FinTrack é o produto-alvo, um painel financeiro
pessoal construído para o estudo, com interface em Next.js, interface de programação em FastAPI, seis
telas (painel inicial, transações, orçamentos, metas, relatórios e suporte) e duas personas fictícias,
Ana e Clara, com dados sintéticos. O PASE é o motor que evolui o FinTrack, com núcleo em FastAPI sobre
o banco de dados PostgreSQL, com a extensão pgvector para busca vetorial, organizado nas três camadas e
acompanhado de um painel de controle. Os cinco serviços executam localmente em contêineres, e o
FinTrack só é alterado pelo fluxo governado pelo PASE.

A **rastreabilidade foi garantida por três decisões**. Toda chamada a modelo passa por um cliente
único, que registra modelo, consumo, duração e identificador de rastreio. Cada uma das quinze
instruções enviadas aos modelos (*prompts*) fica em um arquivo próprio, com histórico de versões
(Apêndice A). E cada decisão, da proposta bruta à publicação, gera um registro em banco. Cada etapa usa
o modelo adequado à sua natureza, acessado pela interface da OpenAI: o *gpt-4.1-mini* na filtragem e na
personalização, o *gpt-4.1* na geração exploratória, o *gpt-5.3-codex* no planejamento e na escrita de
código, o *gpt-5.5* na revisão independente e o *text-embedding-3-small* na busca semântica.

## 5.2 Implementação das Camadas

A prova de conceito implementa o núcleo necessário para percorrer as três camadas de ponta a ponta,
conforme resume o Quadro 3. Os componentes que ampliam a arquitetura sem alterar seu modelo de
governança ficaram fora do escopo. Os parágrafos seguintes destacam, em cada camada, as escolhas
próprias da implementação.

**Quadro 3 - Componentes implementados na prova de conceito e escopo remanescente**

| Camada | Implementado na PoC | Fora do escopo da PoC |
|---|---|---|
| Tarefas | Seis origens de demanda; agrupamento de tickets por tema, com peso de ocorrências; normalização; Avaliador de Zonas Dinâmicas com recuperação dos pedidos semelhantes do módulo; Memória Histórica com contagem de ocorrências; Coerência Sistêmica com citação conferida por código; Qualificação; desvio autorizado para sugestões de engenharia; Módulo de Reavaliação Cíclica por comando; devolutiva da decisão ao usuário | Prospecção competitiva; recompensa por contribuição; alternância periódica de modelos |
| Orquestração | Priorização com fator de urgência e marcador de incerteza; ciclo de vida por estados; pontos de decisão humana sobre tarefa, plano, entrega e publicação; grafo de dependências com três origens de aresta e recusa de ciclos; despacho paralelo; suspensão em cascata; reexecução e trava de custo preditiva; homologação; entrega em estágios com *pull request*; refazer e reverter tarefas; auditoria de código por comando | Pesos e limiares automáticos no grafo; resolução automática de conflitos de integração; subgrafos; replanejamento automático de dependentes; agendamento periódico dos ciclos de manutenção |
| Execução | Planejamento e execução separados; mapeamento de impacto com ação por arquivo; estimativas de custo, tempo e risco técnico; critérios de aceite; roteiro como insumo principal da execução; isolamento por clone, ramo exclusivo e ambiente sem credenciais; verificação automática; preservação da rede de regressão; fronteira de escrita verificada por código; revisão independente com evidência conferida | Contêiner efêmero com rede bloqueada; ambiente temporário de visualização |
| UPA e Zonas Dinâmicas | Seis zonas autônomas; *payload* declarativo; catálogo fechado de três componentes; contrato canônico espelhado e conferido campo a campo; validação em duas camadas; retorno ao componente nativo e registro de violação; selo de personalização; revogação pelo próprio usuário; registro de cada avaliação; encaminhamento de pedidos escritos à zona correspondente | Gatilhos de frustração (cliques repetidos, tempo excessivo, erros de validação); zonas sob demanda conversacionais; barramento de eventos entre zonas; fluxos declarativos de múltiplas etapas; filtro dedicado de injeção de *prompt* |

Fonte: elaborado pelos autores (2026).

Na **Camada de Tarefas**, as seis origens de demanda cobrem os três fluxos de originação: a sugestão
do usuário em qualquer tela do FinTrack e a leitura dos tickets de suporte (agentes externos), as
sugestões funcionais e de engenharia da equipe (agentes internos), e a geração exploratória e a
análise de lacunas (inteligência artificial). A captação passiva agrupa por tema os tickets que relatam
a mesma dor, e a demanda resultante carrega o número de ocorrências, que a Qualificação considera ao
estimar o impacto. A Memória Histórica usa busca vetorial sobre o pgvector, e uma duplicata não cria
registro novo na base vetorial: ela soma suas ocorrências ao item existente, seja ele implementado,
descartado ou em andamento. O Avaliador de Zonas Dinâmicas e a Coerência Sistêmica recebem apenas os
itens mais semelhantes recuperados da base (os cinco pedidos mais semelhantes do mesmo módulo e os cinco descartes mais semelhantes),
e não o histórico inteiro. A Coerência Sistêmica confronta cada proposta com os documentos de contexto
do produto, versionados no banco, e o descarte só é automático quando o trecho citado pelo modelo
existe literalmente nesses documentos; quando a citação não confere, a proposta segue como candidata,
marcada com incerteza, para que uma pessoa decida. No Módulo de Reavaliação Cíclica, o modelo aponta o
trecho que sustentaria o descarte, e o código confere se ele existe. Quem sugeriu acompanha, no próprio
FinTrack, a situação da sugestão, da análise à publicação.

Na **Camada de Orquestração**, os estados do ciclo de vida e os pontos de decisão humana são
persistidos em banco, com registro de origem, destino, momento e motivo de cada transição. O marcador
de incerteza é calculado por regra fixa, e não pelo modelo: confiança abaixo de 0,5, ou impacto baixo
combinado com complexidade alta, e é recalculado quando uma pessoa edita as estimativas. O grafo de
dependências recebe arestas de três origens. As de sobreposição de arquivos e as manuais bloqueiam o
despacho; as de proximidade semântica, criadas quando a similaridade entre as propostas chega a 0,60,
são registradas e exibidas, mas não bloqueiam, porque o cálculo de limiares a partir dos pesos ficou
fora do escopo. Tarefas independentes são despachadas em paralelo, cada uma em sua própria linha de
execução. Quando uma tarefa é suspensa, as que dependem dela são suspensas em cascata e voltam ao estado
anterior quando a predecessora é retomada, replanejada ou cancelada. A trava de custo é preditiva:
antes de cada chamada, compara a folga do orçamento com o maior valor entre o tamanho da chamada que
vai ser feita e a chamada mais cara já feita pela mesma tarefa. O orçamento parte da estimativa do
planejamento com 30% de tolerância, tem um piso fixo e pode ser ajustado pelo gestor. A entrega foi
implementada em estágios: a aprovação integra a tarefa a um ramo de integração, as tarefas aprovadas
nos testes compõem uma versão candidata validada pelas suítes completas, a versão é proposta por um
*pull request* no GitHub, e a publicação no ramo principal exige nova aprovação humana por escrito.
Auditoria de código e reavaliação de descartes são acionadas por uma pessoa, no painel.

Na **Camada de Execução**, o planejamento lê o código completo dos dois alvos e produz o documento de
planejamento, com o mapeamento de impacto (arquivos a modificar, criar ou excluir), o roteiro, os
critérios de aceite e as estimativas de *tokens*, de tempo e de risco técnico. A execução parte do
roteiro e recebe apenas os arquivos planejados, suas importações diretas, os testes que os usam, a
infraestrutura de testes e a lista de caminhos do repositório, sem o conteúdo dos demais arquivos. O
Executor trabalha em um clone do repositório e em um ramo exclusivo, e todo caminho de escrita ou
exclusão é normalizado e conferido antes de tocar o disco: só os dois alvos são graváveis, e o código
que implementa as Zonas Dinâmicas, o contrato canônico e o próprio PASE são inalcançáveis. As
verificações rodam em um ambiente sem credenciais, sem endereços de serviços e com os gerenciadores de
pacotes desligados da rede, de modo que o código gerado não herda segredo algum para vazar. Esse
ambiente não é um isolamento de rede em sentido estrito, que exigiria o contêiner efêmero deixado fora
do escopo. A verificação automática inclui análise estática, checagem de tipos, testes, um teste de
fumaça do *backend* e a construção completa do *frontend* para produção. O código confere, contra o
ramo principal, a preservação dos testes existentes, tanto pelo nome quanto pelo número de asserções,
a presença de teste novo e a cobertura dos módulos alterados. Na revisão independente, conduzida por um
modelo diferente do que escreveu o código, cada critério de aceite atendido precisa citar o código e um
teste correspondentes, e o critério é anulado se a citação não existir nos arquivos ou se o trecho de
teste não estiver em um arquivo de teste.

No **plano de personalização**, o FinTrack recebeu seis Zonas Dinâmicas autônomas, uma por tela, que
aceitam três componentes de um catálogo fechado: lista de atalhos, cartão de resumo e faixa de aviso. A
telemetria implementada é a de navegação, e cada zona é avaliada quando a pessoa visita com frequência
a tela que a zona observa, no máximo uma vez a cada 24 horas por pessoa e zona. O contrato de cada zona
é um documento canônico espelhado no cliente, e um teste automatizado converte o esquema do cliente e o
compara campo a campo com o canônico; esse teste encontrou e eliminou duas divergências reais, em que o
servidor aceitava o que o cliente recusava. O *payload* é validado no servidor e no cliente, e a recusa
em qualquer das duas camadas é registrada como violação, com a camada que recusou. A personalização
aplicada exibe um selo que a identifica e uma ação para voltar ao padrão; a revogação pelo próprio
usuário é durável, e a zona não é personalizada automaticamente de novo para ele. Cada avaliação
registra os sinais enviados ao agente, a decisão, o motivo e o *payload* resultante.

Duas escolhas de implementação merecem registro. O isolamento foi feito por clone, ramo exclusivo e
ambiente sem credenciais, e não por contêiner efêmero. E a integração com o GitHub foi exercitada na
validação: a versão é proposta por um *pull request* real e publicada pelo seu *merge*. A
implementação conta ainda com 694 testes automatizados (586 do núcleo do PASE, 53 da interface de programação e 55 da interface de usuário do FinTrack) e com oito roteiros de demonstração executáveis
(Apêndice C).

## 5.3 Painel de Controle

O painel de controle concentra a supervisão humana. Nele estão as tarefas candidatas por prioridade,
as tarefas em andamento por estado, o histórico das finalizadas e os descartes com seus motivos, a tela
de entrega, as zonas dinâmicas, o contexto do produto e o estado do sistema, atualizados pelos eventos
do próprio sistema. A Figura 9 mostra os descartes do funil, a Figura 10, o grafo de dependências, a
Figura 11, a fila de execução, a memória vetorial, o consumo, as travas e os *prompts* versionados, e a
Figura 12, os documentos de contexto e as etapas que os leem.

**Figura 9 - Descartadas: propostas barradas pelo funil por duplicidade ou incoerência, com o motivo de cada descarte**

[Captura: Tarefas > Descartadas]

Fonte: elaborado pelos autores (2026).

**Figura 10 - Dependências: grafo das tarefas, com nós coloridos por estado e arestas de dependência**

[Captura: Dependências]

Fonte: elaborado pelos autores (2026).

**Figura 11 - Sistema: fila de execução, memória vetorial, consumo acumulado, travas e prompts versionados**

[Captura: Sistema]

Fonte: elaborado pelos autores (2026).

**Figura 12 - Contexto: documentos do produto versionados no banco e as etapas do ciclo que leem cada um**

[Captura: Contexto]

Fonte: elaborado pelos autores (2026).

---

# 6 VALIDAÇÃO

Este capítulo valida a Arquitetura PASE em dois fluxos de ponta a ponta, executados na prova de
conceito com modelos de linguagem reais. Para cada fluxo, descrevem-se as etapas percorridas, o
componente da PASE responsável por cada uma e a evidência registrada pelo sistema.

## 6.1 Método de Validação

A validação segue a estratégia de estudo de caso demonstrativo, aplicado ao FinTrack em «data». O
objetivo não é medir produtividade, mas demonstrar que os componentes especificados operam em conjunto,
com decisão humana nos pontos definidos e registro de cada decisão. O Fluxo 1 cobre o regime de
evolução do código, da demanda à publicação, e o Fluxo 2 cobre o regime de personalização em tempo de
execução.

Uma etapa é considerada validada quando é executada pelo componente que a arquitetura designa e deixa o
registro exigido, conferido nos registros do PASE, no histórico do repositório e nas capturas de tela.
Os componentes que não participam dos fluxos, como a trava de custo, a suspensão em cascata, o Ciclo de
Auditoria e a reavaliação de descartes, são cobertos pelos testes e pelos roteiros de demonstração da
implementação.

## 6.2 Fluxo 1: da Demanda ao Código em Produção

O Fluxo 1 acompanha o modo escuro do FinTrack, registrado como tarefa nº «n» do PASE, da demanda em
linguagem natural à publicação na versão 1.0.0. A funcionalidade altera todas as telas e vários
arquivos, o que exercita o planejamento, a verificação e a entrega em estágios. A Figura 13 mostra o
produto antes da solicitação.

**Figura 13 - FinTrack antes da solicitação: interface apenas em tema claro, sem controle de tema**

[Captura: FinTrack em /dashboard, persona Ana]

Fonte: elaborado pelos autores (2026).

A demanda foi escrita pela persona Ana no próprio FinTrack, pelo botão de sugestão disponível em todas
as telas. Ela foi normalizada, comparada com a memória de itens implementados, em andamento e
descartados, confrontada com o contexto do produto e qualificada, tornando-se uma tarefa candidata à
espera do gestor (Figura 14). Na mesma sessão, o funil barrou uma proposta de acompanhar investimentos,
citando a linha do escopo que a exclui, e duas propostas repetidas, uma de algo já implementado e outra
de algo já descartado (Figura 9). «Ajustar se os desfechos forem outros.»

**Figura 14 - A solicitação: (a) demanda em linguagem natural enviada pela usuária no FinTrack; (b) tarefa candidata qualificada no painel do PASE, aguardando decisão**

[Captura: modal "Sugerir melhoria" no FinTrack e aba Candidatas no painel]

Fonte: elaborado pelos autores (2026).

O gestor aprovou a candidata exigindo a revisão do plano, e o Executor produziu o Documento de
Planejamento Técnico, com «a» arquivos e a ação prevista para cada um, «c» critérios de aceite e as
estimativas de custo, tempo e risco, antes de escrever qualquer código. Os critérios descreviam o efeito
esperado pelo usuário, e não o mecanismo técnico. O plano passou pelo ponto de decisão humana próprio e
só foi liberado após aprovação (Figura 15), com cada mudança de estado registrada.

**Figura 15 - Documento de Planejamento Técnico: arquivos previstos e ação sobre cada um, critérios de aceite, estimativas e trilho do ciclo de vida**

[Captura: tarefa nº «n», aba Planejamento]

Fonte: elaborado pelos autores (2026).

O Executor trabalhou em clone isolado e ramo exclusivo e entregou a paleta escura, o botão de
alternância e a persistência da preferência de cada persona, com testes para os critérios. A entrega
passou pela verificação automática completa (Figura 16), e um agente revisor, executado por um modelo
distinto do que escreveu o código, conferiu cada critério com citações de código e de teste verificadas
pelo sistema. A execução consumiu «t» *tokens* em «d» minutos, contra «e» estimados no planejamento.

**Figura 16 - Execução registrada: diferenças de código, verificações automáticas e transcrição integral da interação com os modelos**

[Captura: tarefa nº «n», aba Execuções]

Fonte: elaborado pelos autores (2026).

Com o parecer da revisão, o gestor aprovou a entrega (Figura 17), que foi integrada ao ramo de
integração e aprovada pela verificação contínua desse ramo. Após a aprovação funcional, a tarefa entrou
na versão candidata 1.0.0, validada pelas suítes completas, e a versão foi proposta ao ramo principal
por um *pull request* aberto pelo próprio PASE no GitHub (Figuras 18 e 19). A publicação exigiu nova
aprovação humana por escrito e foi feita pelo *merge* desse *pull request*. O histórico do repositório
preserva essa cadeia nos *commits* «hash da tarefa», «hash da integração» e «hash da release», e a
funcionalidade passou a valer no produto (Figura 20). O Quadro 4 resume o percurso, indicando em cada
etapa o componente responsável e a evidência.

**Figura 17 - Homologação: parecer da revisão independente por critério de aceite e decisão do gestor**

[Captura: tarefa nº «n», aba Homologação]

Fonte: elaborado pelos autores (2026).

**Figura 18 - Tela Entrega: tarefa no ramo de integração, versão 1.0.0 validada e publicação sob aprovação humana**

[Captura: Entrega, com a release 1.0.0 e o PR aberto]

Fonte: elaborado pelos autores (2026).

**Figura 19 - Pull request da versão 1.0.0 aberto pelo PASE no GitHub, com o corpo exigido pelo guia de fluxo de ramos**

[Captura: página do PR nº «p» no GitHub]

Fonte: elaborado pelos autores (2026).

**Figura 20 - FinTrack após a entrega: botão "Usar tema escuro" e paleta escura aplicada a todas as telas**

[Captura: FinTrack em /dashboard, persona Ana, tema escuro, mesmo enquadramento da Figura 13]

Fonte: elaborado pelos autores (2026).

**Quadro 4 - Percurso do Fluxo 1 pelos componentes da Arquitetura PASE**

| Etapa | Componente da PASE | Responsável | Evidência |
|---|---|---|---|
| Demanda escrita pela usuária no produto | Camada de Tarefas: captação ativa | Pessoa (usuária) | Figura 14a |
| Demanda normalizada, filtrada e qualificada | Camada de Tarefas: Normalização e Motor de Filtragem | Sistema | Figura 14b |
| Tarefa candidata aprovada | Orquestração: priorização e decisão humana | Pessoa | Figura 14b e registro de transição |
| Plano com «a» arquivos e «c» critérios de aceite | Execução: Planejamento Técnico | Agente | Figura 15 |
| Plano aprovado | Orquestração: decisão humana sobre o plano | Pessoa | Figura 15 e registro de transição |
| Código escrito em ambiente isolado e verificado | Execução: Execução e Verificação | Agente e código | Figura 16 |
| Critérios conferidos com evidência citada | Execução: Revisão Independente | Agente e código | Figura 17 |
| Entrega aprovada e integrada | Orquestração: Homologação | Pessoa | Figura 17 |
| Versão candidata validada, proposta e publicada | Orquestração: entrega em estágios | Pessoa | Figuras 18 e 19 e *commits* da versão 1.0.0 |
| Funcionalidade em produção | Produto-alvo | - | Figura 20 |

Fonte: elaborado pelos autores (2026), a partir dos registros do PASE e do histórico do repositório.

O Fluxo 1 valida o funcionamento encadeado das três camadas: uma demanda informal tornou-se uma versão
publicada sem que nenhuma etapa saísse do componente designado. As decisões humanas ocorreram nos pontos
previstos, sobre a tarefa, o plano, a entrega e a publicação, e cada passo deixou um registro que
permite reconstruir quem decidiu o quê. A própria usuária que fez o pedido passou a ver, no FinTrack,
que ele foi publicado.

## 6.3 Fluxo 2: Personalização em Tempo de Execução

O Fluxo 2 valida o UPA e as Zonas Dinâmicas. O uso frequente da tela de relatórios pela persona Ana
acionou a regra da zona do painel inicial, e o UPA gerou um *payload* declarativo, validado pelo
servidor antes de ser persistido (Figura 21). A avaliação ficou registrada com os sinais enviados ao
agente, a decisão e o motivo. No navegador, uma segunda validação confrontou o *payload* com o
contrato, e a personalização apareceu apenas para Ana, com o selo de identificação e a ação de voltar
ao padrão, enquanto Clara manteve o componente nativo (Figura 22).

**Figura 21 - Simulador do painel: o uso intenso de relatórios pela persona Ana aciona a zona do painel inicial e o UPA gera um payload declarativo**

[Captura: Zonas > Simulador e payload ativo com o JSON expandido]

Fonte: elaborado pelos autores (2026).

**Figura 22 - Personalização em execução: Ana vê o componente gerado pelo UPA, com o selo "personalizado", enquanto Clara mantém o componente nativo**

[Captura: FinTrack em /dashboard como Ana e como Clara, lado a lado]

Fonte: elaborado pelos autores (2026).

A defesa foi testada no pior caso, com três conteúdos maliciosos gravados diretamente no banco,
contornando o servidor: um rótulo acima do limite, um *link* externo e um componente fora do catálogo,
nomeado *iframe_injector*. O cliente recusou os três, manteve o componente nativo e registrou cada
violação com o motivo, o conteúdo bruto e a camada que a recusou (Figura 23). O Quadro 5 resume o
percurso, que não depende de nenhuma decisão humana.

**Figura 23 - Defesa em profundidade: payloads maliciosos injetados sem validação do servidor, recusados pelo cliente e registrados como violação**

[Captura: Zonas > Injetor e lista de Violações]

Fonte: elaborado pelos autores (2026).

**Quadro 5 - Percurso do Fluxo 2 pelos componentes da Arquitetura PASE**

| Etapa | Componente da PASE | Evidência |
|---|---|---|
| Uso intenso de relatórios aciona a regra da zona | Telemetria e regra da Zona Dinâmica | Figura 21 |
| UPA decide personalizar e gera *payload* declarativo com componente do catálogo | UPA, no nível das restrições abstratas | Figura 21 e registro da avaliação |
| Servidor valida o *payload* antes de persisti-lo | Contrato rígido, primeira camada de validação | Registro do *payload* ativo |
| Cliente valida e exibe a personalização apenas para Ana | Contrato rígido, segunda camada, e selo de personalização | Figura 22 |
| Conteúdos maliciosos recusados e registrados | Contrato rígido no cliente e registro de violações | Figura 23 |

Fonte: elaborado pelos autores (2026), a partir dos registros do PASE.

O Fluxo 2 valida a hiper-personalização governada: a interface adaptou-se a uma pessoa sem que a IA
gerasse código e sem mudar o produto para os demais usuários. O UPA decidiu o que mostrar, e o código
decidiu o que podia ser mostrado, mesmo com a primeira camada de validação contornada. A personalização
continua reversível pela própria pessoa, que pode voltar ao componente nativo a qualquer momento.

## 6.4 Síntese dos Resultados

Os dois fluxos mostram a arquitetura operando como especificado nos seus dois regimes. Juntos, eles
cobrem as três camadas e os quatro princípios de projeto. O Quadro 6 relaciona cada requisito da Seção 2.6 à evidência que o valida.

**Quadro 6 - Requisitos da arquitetura e evidências da validação**

| Requisito | Evidência na validação | Fluxo |
|---|---|---|
| R1: plano de controle único, com custo observável e registro de cada decisão | A Orquestração conduziu a tarefa da candidatura à publicação, com cada transição e cada chamada ao modelo registradas e o consumo exibido no painel | 1 |
| R2: ciclo inteiro automatizado, da originação à entrega, com verificação do efeito | Uma demanda escrita pela usuária no produto tornou-se versão publicada, e os critérios de aceite foram conferidos pela revisão independente | 1 |
| R3: personalização delimitada, sem alterar o código, reversível e compreensível | A zona foi personalizada apenas para Ana, com selo e ação de voltar ao padrão, enquanto Clara manteve o padrão, sem alteração do repositório | 2 |
| R4: execução isolada e verificada, geração limitada por contratos e decisões com consequência reservadas a pessoas | Execução isolada e verificada, decisões humanas sobre tarefa, plano, entrega e publicação, e recusa de conteúdos maliciosos pelo contrato | 1 e 2 |
| R5: supervisão humana informada | A homologação apoiou-se nas diferenças de código, nas verificações, no parecer por critério e no histórico da interação com os modelos | 1 |

Fonte: elaborado pelos autores (2026).

A autonomia supervisionada apareceu no Fluxo 1, e a contenção da generatividade, na revisão com
evidência conferida, na citação conferida da Coerência Sistêmica e no contrato das zonas. A
rastreabilidade integral permitiu reconstruir cada etapa pelos registros, e o alinhamento entre
arquitetura e tarefa refletiu-se no uso de modelos distintos para filtrar, programar e revisar. A
validação é demonstrativa e não mede ganhos de produtividade, aspecto tratado nas limitações do
trabalho.

---

# 7 CONCLUSÃO

A IA deixou de ser apenas uma ferramenta de apoio e passou a atuar como agente capaz de planejar, decidir e executar trabalho de software. Este trabalho investigou o que essa mudança exige da arquitetura do software. A análise das cinco dimensões do ecossistema mostrou que, em todas elas, a capacidade técnica já demonstrada contrasta com a ausência de estruturas que a tornem ao mesmo tempo produtiva e confiável. Em resposta, o trabalho propôs a Arquitetura PASE, implementou uma prova de conceito e a validou em dois fluxos de ponta a ponta.

Quanto à primeira questão de pesquisa (QP1), a evidência analisada aponta para a via híbrida. Os desenvolvedores ainda delegam por completo uma parcela pequena de suas tarefas (ANTHROPIC, 2026), e poucos confiariam na IA para uma decisão importante (STACK OVERFLOW, 2026). Sistemas com vários agentes só melhoram quando há verificação central do que produzem (KIM et al., 2026), e os casos empresariais mais maduros combinam geração probabilística com execução determinística sob aprovações e auditoria (SAROYA; MACNEILL, 2026). A validação reforçou essa leitura: no Fluxo 1, o sistema avançou sozinho entre as decisões humanas, e no Fluxo 2, agiu sem decisão humana, mas dentro de contratos verificados por código. O cenário mais provável, e mais desejável, é o de ecossistemas em que a autonomia dos agentes é ampla e, ao mesmo tempo, subordinada a pontos de governança humana e a garantias verificáveis.

Quanto à segunda questão (QP2), a PASE responde com um desenho concreto, no qual supervisão, segurança e rastreabilidade não são requisitos difusos, mas mecanismos distribuídos pelas três camadas. A decisão humana ocupa pontos definidos, sobre a tarefa, o plano, a entrega e a publicação, e tudo o que pode ser conferido por código é conferido por código. A prova de conceito demonstrou que esse desenho é viável: uma demanda em linguagem natural chegou à produção passando por todas as camadas, e a interface foi personalizada por usuário sem que a IA gerasse código e sem que conteúdos maliciosos chegassem à tela.

Com isso, foram cumpridos o objetivo geral, propor e validar a Arquitetura PASE, e os seis objetivos específicos definidos na introdução. A análise das cinco dimensões e a derivação dos requisitos estão no Capítulo 2, e a especificação da arquitetura, no Capítulo 4. A implementação e a validação da prova de conceito estão nos Capítulos 5 e 6, e as limitações e os caminhos de evolução são discutidos a seguir.

## 7.1 Contribuições

A primeira contribuição é a análise multidimensional do software na era da IA agêntica. Ela reúne evidências de indústria, desenvolvimento, experiência do usuário, segurança e trabalho e as converte em cinco requisitos explícitos. Esses requisitos permitem avaliar arquiteturas de software agêntico por critérios declarados, e não apenas por sua capacidade técnica.

A segunda contribuição é a própria Arquitetura PASE, concebida como um modelo de referência. Ela é especificada em termos de responsabilidades, contratos entre camadas e pontos de decisão, e não em termos de tecnologias, modelos ou ferramentas específicas. Como seus requisitos derivam de dimensões comuns a qualquer software construído hoje, a arquitetura pode ser adotada por diferentes organizações, que constroem sua própria instância adaptando componentes, limiares e pontos de decisão ao seu contexto. A prova de conceito com o FinTrack é uma dessas instâncias, e a confirmação dessa aplicabilidade em outros produtos é um dos trabalhos futuros.

A terceira contribuição é a prova de conceito funcional e a validação que ela permitiu. A implementação, acompanhada de 694 testes automatizados e de roteiros de demonstração reproduzíveis, mostrou as três camadas operando de ponta a ponta e a personalização governada em tempo de execução. Ela oferece, além disso, um ponto de partida concreto para quem deseje implementar a arquitetura.

A quarta contribuição é um princípio de projeto que atravessa toda a arquitetura: garantias que dependem apenas de instruções ao modelo não são garantias. Onde uma garantia importa, ela precisa ser verificada por código ou decidida por uma pessoa, segundo a regra de que o modelo aponta a evidência e o código confere se ela existe. Esse princípio pode ser aplicado a outras arquiteturas que combinem componentes probabilísticos com responsabilidades críticas.

## 7.2 Limitações

As limitações começam pela revisão da literatura. Ela foi conduzida como revisão narrativa estruturada, e não como revisão sistemática com protocolo registrado, e parte do corpus é composta por versões preliminares e por relatórios de indústria. Vários desses relatórios são produzidos por empresas que comercializam as tecnologias analisadas, de modo que seus números foram tratados como indicativos de tendência, e não como medições independentes.

A validação tem caráter demonstrativo. O produto-alvo é de porte reduzido, foi construído para o estudo e opera com personas fictícias e dados sintéticos. Os operadores humanos foram os próprios autores, e os dois fluxos cobrem os cenários centrais da arquitetura, mas não a variedade de demandas de um produto real. Por isso, o trabalho não permite conclusões sobre ganhos de produtividade, custo, carga de supervisão ou efeito da personalização sobre usuários reais.

A prova de conceito implementa o núcleo da arquitetura, mas não sua totalidade. Na Camada de Tarefas, ficaram fora do escopo a prospecção competitiva, a recompensa por contribuição e a alternância periódica de modelos. Na Orquestração, não foram implementados os pesos e limiares automáticos do grafo de dependências, os subgrafos, o replanejamento automático de tarefas dependentes, a resolução automática de conflitos de integração e o agendamento periódico dos ciclos de manutenção. Na Camada de Execução, o isolamento é feito por clone, ramo exclusivo e um ambiente de verificação sem credenciais e sem acesso de rede por proxy, mas não bloqueia conexões diretas: isso exigiria o contêiner efêmero por tarefa, que também ficou fora, assim como o ambiente temporário de visualização. Na personalização, a telemetria cobre apenas a navegação, sem os gatilhos de frustração, e não foram implementados as zonas sob demanda conversacionais, o barramento de eventos entre zonas, os fluxos declarativos de múltiplas etapas e o filtro dedicado de injeção de *prompt*. Por fim, os modelos de linguagem evoluem rapidamente, e as escolhas concretas da implementação tendem a mudar, ainda que a arquitetura não dependa delas.

## 7.3 Trabalhos Futuros

O primeiro desdobramento é completar a implementação dos componentes que ficaram fora do escopo. Merecem prioridade o ambiente temporário de visualização, que permite testar a entrega na tela antes da homologação, a execução em contêineres efêmeros com a rede bloqueada e a resolução automática de conflitos de integração. As zonas sob demanda, o barramento de eventos e os gatilhos de telemetria além da navegação ampliariam a personalização para além de componentes isolados.

O segundo desdobramento é a aplicação da arquitetura em empresas e produtos reais. Estudos de caso com equipes que não participaram de sua concepção, em domínios diferentes, permitiriam verificar se a PASE se mantém aplicável como modelo de referência. Esses estudos poderiam incluir uma validação quantitativa, com métricas de produtividade, custo, intervenção humana e qualidade das entregas, e comparar o desenvolvimento com e sem os pontos de decisão humana. Na personalização, estudos com usuários reais avaliariam o efeito das Zonas Dinâmicas sobre a experiência, a transparência e a percepção de controle.

O terceiro desdobramento é a evolução do próprio modelo a partir desses estudos. Componentes e requisitos podem ser acrescentados, ajustados ou removidos conforme os resultados, e novas dimensões podem ser incorporadas à análise, como o custo computacional, a acessibilidade e as exigências regulatórias de cada setor. Também é relevante investigar se o pacote de homologação, com critérios de aceite e evidências conferidas, preserva o engajamento cognitivo de quem supervisiona, já que a formação de competências depende desse engajamento (SHEN; TAMKIN, 2026).

Com esses desdobramentos, a PASE pretende oferecer um vocabulário e uma estrutura para que produtividade e confiabilidade sejam tratadas como requisitos de projeto desde o início. A arquitetura foi pensada para ser geral e simples de adotar, considerando as dimensões analisadas, mas permanece aberta a novos aspectos que a prática venha a revelar.

---

# APÊNDICE A - PROMPTS VERSIONADOS DA PROVA DE CONCEITO

A prova de conceito delega a modelos de linguagem apenas decisões específicas, cada uma definida por um *prompt* próprio, mantido como arquivo versionado no repositório, e nunca como texto embutido no código. O Quadro A.1 relaciona os quinze *prompts* à camada e ao componente da Arquitetura PASE que cada um implementa.

**Quadro A.1 - Prompts da prova de conceito e componentes correspondentes**

| *Prompt* | Função | Camada e componente |
|---|---|---|
| P0 | Extração de intenção a partir de tickets de suporte | Tarefas: captação passiva |
| P0a | Agrupamento de tickets por tema | Tarefas: captação passiva |
| P1 | Normalização da demanda | Tarefas: *middleware* de normalização |
| P1b | Avaliação de Zona Dinâmica | Tarefas: Avaliador de Zonas Dinâmicas |
| P2a | Coerência sistêmica com o contexto do produto | Tarefas: Motor de Filtragem |
| P2b | Qualificação por impacto, complexidade, confiança e risco | Tarefas: Motor de Filtragem |
| P3 | Geração exploratória de propostas | Tarefas: fluxo da inteligência artificial |
| P3b | Análise de lacunas entre módulos | Tarefas: fluxo da inteligência artificial |
| P4 | Planejamento técnico, mapeamento de impacto, estimativas e critérios de aceite | Execução: fase de planejamento |
| P5 | Geração e correção de código | Execução: fase de execução |
| P6 | Geração de *payload* de Zona Dinâmica | Execução: UPA |
| P9 | Análise de deriva de contexto dos descartes | Tarefas: Reavaliação Cíclica |
| P10 | Varredura de auditoria do código | Orquestração: Ciclo de Auditoria |
| P11 | Proposta de atualização de um documento de contexto | Orquestração: homologação |
| P12 | Revisão independente da entrega | Execução: revisão independente |

Fonte: elaborado pelos autores (2026).

---

# APÊNDICE B - CONTRATO CANÔNICO DAS ZONAS DINÂMICAS

O contrato rígido (*Hard Constraint*) que as Zonas Dinâmicas aplicam é um único documento canônico em JSON Schema, validado no servidor antes de persistir cada *payload* e espelhado no cliente, onde ocorre a validação decisiva. Um teste automatizado compara os dois campo a campo. O contrato admite apenas três componentes nativos, rótulos de até quarenta caracteres, no máximo três itens e ligações restritas às rotas internas do produto. Qualquer propriedade não prevista invalida o *payload*. O trecho a seguir omite apenas os campos de descrição do arquivo original.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pase.local/contracts/zona.schema.json",
  "title": "Contrato das Zonas Dinâmicas",
  "type": "object",
  "additionalProperties": false,
  "required": ["widget", "label"],
  "properties": {
    "widget": { "type": "string", "enum": ["shortcut_list", "summary_card", "alert_banner"] },
    "label": { "type": "string", "minLength": 1, "maxLength": 40 },
    "maxItems": { "type": "integer", "minimum": 1, "maximum": 3 },
    "tone": { "type": "string", "enum": ["neutral", "atencao"] },
    "items": {
      "type": "array",
      "maxItems": 3,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "href"],
        "properties": {
          "label": { "type": "string", "minLength": 1, "maxLength": 40 },
          "href": {
            "type": "string",
            "pattern": "^/(dashboard|transacoes|relatorios|orcamentos|metas|suporte)$"
          }
        }
      }
    }
  },
  "allOf": [
    {
      "if": {
        "properties": { "widget": { "enum": ["shortcut_list", "summary_card"] } },
        "required": ["widget"]
      },
      "then": { "required": ["maxItems", "items"] }
    },
    {
      "if": {
        "properties": { "widget": { "const": "alert_banner" } },
        "required": ["widget"]
      },
      "then": { "required": ["tone"] }
    }
  ]
}
```

---

# APÊNDICE C - REPRODUÇÃO DA PROVA DE CONCEITO

A prova de conceito é composta por cinco serviços executados localmente em contêineres: o banco de dados do PASE, o núcleo do PASE, o painel de controle e os dois serviços do FinTrack. O repositório reúne o código dos dois sistemas, os roteiros de demonstração e as suítes de testes. O repositório está disponível em <https://github.com/atharvnuthi/pase-poc>. As chaves de acesso aos provedores de modelos não fazem parte dele: cada pessoa que reproduzir o experimento deve fornecer as suas, em um arquivo de ambiente local.

A partir de um ambiente com Docker e com as chaves de acesso ao provedor de modelos configuradas em um arquivo de ambiente local, a sequência de reprodução é a seguinte. O comando `make reset-all` recria o ambiente do zero e popula o FinTrack e a base inicial do PASE (o comando `make reset` faz o mesmo, preservando as edições dos documentos de contexto). Os comandos `make test-core` e `make test-client` executam as suítes do núcleo e da interface de programação do FinTrack, e a suíte da interface de usuário é executada no contêiner correspondente. O comando `make demos` executa os oito roteiros de demonstração (d1 a d8), e `make metrics` exporta os três arquivos CSV de tarefas, descartes e violações. Como os roteiros fazem chamadas reais a modelos de linguagem, sua execução tem custo e pode produzir resultados ligeiramente diferentes a cada vez.

---

# Ajustes no restante do documento

Itens que o texto acima pressupõe e que precisam mudar em outras partes do `.docx`.

## Numeração e listas

1. **Sumário.** Regenerar o campo: o corpo tem os capítulos 5 Implementação (5.1, 5.2, 5.3),
   6 Validação (6.1 a 6.4) e 7 Conclusão (7.1 a 7.3). A lista em texto ainda diz "5 IMPLEMENTAÇÃO E
   VALIDAÇÃO" e "6 CONCLUSÃO".
2. **Duas seções 5.2.** O texto atual tem "5.2 Implementação das Camadas" e "5.2 Painel de Controle";
   a segunda passa a 5.3.
3. **Figuras do Capítulo 4.** O corpo chama de Figura 2 a 6 o que a lista chama de Figura 4 a 8, e a
   numeração colide com as Figuras 2 e 3 do Capítulo 2. Renomear: Visão geral → Figura 4; Camada de
   Tarefas → 5; Orquestração e Execução → 6; Ciclo de vida → 7; Contrato rígido → 8, e as
   referências no texto ("apresentadas na Figura 2", "parte superior da Figura 2", "detalhados na
   Figura 3", "A Figura 4 detalha", "representado na Figura 5", "A Figura 6 ilustra").
4. **Seção 2.4.** "como mostra a Figura 4" deve ser "como mostra a Figura 3" (Veracode).
5. **Figura 2.** A lista diz "Efeito da adoção de IA sobre o volume e a estabilidade das entregas de
   software", e a legenda diz "Efeito estimado da adoção de IA sobre os principais resultados do
   desenvolvimento de software". Use a mesma nas duas.
6. **Lista de Ilustrações.** Substituir as Figuras 11 a 24 por:
   - Figura 9 - Descartadas: propostas barradas pelo funil por duplicidade ou incoerência, com o motivo de cada descarte
   - Figura 10 - Dependências: grafo das tarefas, com nós coloridos por estado e arestas de dependência
   - Figura 11 - Sistema: fila de execução, memória vetorial, consumo acumulado, travas e prompts versionados
   - Figura 12 - Contexto: documentos do produto versionados no banco e as etapas do ciclo que leem cada um
   - Figura 13 - FinTrack antes da solicitação: interface apenas em tema claro, sem controle de tema
   - Figura 14 - A solicitação: demanda em linguagem natural enviada pela usuária e tarefa candidata qualificada
   - Figura 15 - Documento de Planejamento Técnico: arquivos previstos e ação sobre cada um, critérios de aceite, estimativas e trilho do ciclo de vida
   - Figura 16 - Execução registrada: diferenças de código, verificações automáticas e transcrição integral da interação com os modelos
   - Figura 17 - Homologação: parecer da revisão independente por critério de aceite e decisão do gestor
   - Figura 18 - Tela Entrega: tarefa no ramo de integração, versão 1.0.0 validada e publicação sob aprovação humana
   - Figura 19 - Pull request da versão 1.0.0 aberto pelo PASE no GitHub
   - Figura 20 - FinTrack após a entrega: botão "Usar tema escuro" e paleta escura aplicada a todas as telas
   - Figura 21 - Simulador do painel: o uso intenso de relatórios aciona a zona do painel inicial e o UPA gera um payload
   - Figura 22 - Personalização em execução: Ana vê o componente gerado pelo UPA, Clara mantém o componente nativo
   - Figura 23 - Defesa em profundidade: payloads maliciosos injetados, recusados pelo cliente e registrados como violação
7. **Lista de Quadros.** Quadro 3 - Componentes implementados na prova de conceito e escopo
   remanescente; Quadro 4 - Percurso do Fluxo 1 pelos componentes da Arquitetura PASE; Quadro 5 -
   Percurso do Fluxo 2 pelos componentes da Arquitetura PASE; Quadro 6 - Requisitos da arquitetura e
   evidências da validação. Remover "Roteiros de demonstração", "Linha do tempo da tarefa nº 6" e
   "Ajustes motivados pela validação".
8. **Lista de Tabelas.** Remover a seção inteira (Tabelas 1 e 2): o capítulo 6 não tem mais tabelas.
9. **Resumo e Abstract.** Ambos afirmam que "metade das entregas aprovadas antes da introdução da
   revisão independente foi revertida", que "as estimativas de custo do planejamento erraram por mais
   de uma ordem de grandeza", que "cada falha foi absorvida pela arquitetura na forma de um mecanismo
   verificável" e que o princípio de projeto "emergiu da validação". Sem a seção de falhas, o corpo
   não sustenta essas frases (o Capítulo 7 revisado já não as usa): removê-las, ou manter a seção.
10. **Seção 4.4.4.** "serão exploradas ao final do capítulo 4.5.3" → "detalhadas na Seção 4.5.3".

## Coerência do Capítulo 4 com ele mesmo

A Seção 4.4.4 diz: "Ao mover a tarefa aprovada para o estado Finalizada, a Orquestração executa
automaticamente a incorporação (merge) das alterações ao ramo principal e sua publicação." Isso
contradiz as Seções 4.2, 4.4 e 4.6, que põem a publicação em produção entre os pontos de decisão
humana, e o código segue essas três. Sugestão de redação:

> Ao mover a tarefa aprovada para o estado Finalizada, a Orquestração incorpora automaticamente as
> alterações ao ramo de integração. A publicação no ramo principal é uma decisão posterior, tomada por
> uma pessoa sobre uma versão que reúne as tarefas aprovadas, validada pelas suítes completas e
> proposta por um *pull request*.

A mesma seção diz que "a validação funcional e os testes ocorrem durante a própria homologação,
apoiados pelo ambiente temporário de visualização", e o ambiente temporário ficou fora do escopo. Basta
acrescentar "quando disponível" ou remeter ao Quadro 3.

## Apêndices

Substituídos pelos textos acima (A, B e C). Mudanças: no A, o título do P4; no B, o JSON agora é o do
arquivo real (com `$id` e `required` nos dois `if`); no C, `make reset-all`, sem referência ao Quadro 4
e à Tabela 2, e o endereço do repositório.

## Capítulo 7

Substituído pelo texto revisado acima (7.1 a 7.3). Mudanças em relação à versão atual: a lista do
que ficou fora do escopo (7.2) passa a seguir o Quadro 3 e a dizer que o ambiente de verificação não
bloqueia conexões diretas; em 7.3, o contêiner efêmero com rede bloqueada substitui "a integração
exercitada com repositórios remotos" (o *pull request* real foi exercitado); em 7.1, a terceira
contribuição cita os 694 testes.

## Declaração de Uso de IA Generativa

Onde está "[confirmar versões utilizadas]": esta revisão do código e do texto foi feita com o Claude
Code usando o modelo Claude Opus 5.5. Confirme se outras sessões usaram outras versões.
