# Elementos pré-textuais (versão alinhada)

Tudo entre as linhas `=====` abaixo é o texto para colar no `.docx`, na ordem. As notas de
alteração e as pendências ficam no fim e não entram no documento.

=====

## Capa e Folha de Rosto

UNIVERSIDADE FEDERAL FLUMINENSE
INSTITUTO DE COMPUTAÇÃO
DEPARTAMENTO DE CIÊNCIA DA COMPUTAÇÃO

ATHARV NUTHI
FELIPE VAHIA MALLIAGROS

**ARQUITETURA PASE: AUTONOMIA SUPERVISIONADA COM AGENTES DE IA NO CICLO DE VIDA DE SOFTWARE, A PARTIR DE UMA ANÁLISE MULTIDIMENSIONAL DO ECOSSISTEMA**

Trabalho de Conclusão de Curso submetido ao Departamento de Ciência da Computação da Universidade Federal Fluminense como requisito parcial para a obtenção do título de Bacharel em Ciência da Computação.

Orientador: Prof. Troy Costa Kohwalter

Niterói
2026

## Ficha Catalográfica

[A ser gerada no Sistema de Geração Automática de Fichas Catalográficas da UFF: https://bibliotecas.uff.br/bee/fichacatalografica]

## Folha de Aprovação

[Modelo do abnTeX2: título, autores, preâmbulo, data de aprovação e assinaturas da banca examinadora.]

## Dedicatória

[Opcional. A redigir pelos autores.]

## Agradecimentos

[Opcional. A redigir pelos autores.]

## Declaração de Considerações Éticas

Não há considerações éticas a declarar: a pesquisa não envolveu seres humanos nem dados pessoais ou sensíveis, pois o produto-alvo opera apenas com personas fictícias e dados sintéticos.

## Declaração de Uso de IA Generativa

Ferramentas de IA generativa foram utilizadas neste trabalho em duas condições distintas, declaradas a seguir.

Como objeto de estudo, modelos de linguagem integram a própria prova de conceito descrita no Capítulo 5. São eles o *gpt-4.1-mini*, na filtragem de demandas e na personalização da interface; o *gpt-4.1*, na geração exploratória de propostas; o *gpt-5.3-codex*, no planejamento e na escrita de código; o *gpt-5.5*, na revisão independente das entregas; e o *text-embedding-3-small*, na busca semântica. Todos são acessados pela interface de programação da OpenAI, e suas saídas são registradas e auditáveis.

Como ferramenta de apoio aos autores, foi utilizado o assistente Claude Code, da Anthropic, com os modelos Claude Opus 5.5 e Claude Sonnet 5.5 [confirmar se outras versões foram usadas em sessões anteriores]. Ele apoiou o desenvolvimento do código da prova de conceito, a organização e a revisão do texto, a verificação das citações contra os documentos de referência e a formatação do manuscrito. [Confirmar e completar com outras ferramentas eventualmente utilizadas, como corretores gramaticais ou tradutores.] Todo o conteúdo produzido com esse apoio foi revisado, verificado e assumido pelos autores, que são responsáveis pelas ideias, pelas decisões de projeto, pela análise e pelas conclusões apresentadas.

## Resumo

A inteligência artificial agêntica está mudando o papel do software: de ferramenta que apoia o trabalho humano, ele passa a ser um sistema capaz de executar esse trabalho. Para as empresas que desenvolvem software, isso abre a possibilidade de automatizar grande parte do ciclo de desenvolvimento, desde a identificação do que deve ser construído até a entrega em produção. Na prática, porém, os ganhos obtidos por desenvolvedores individuais ainda não se convertem em entregas mais rápidas e estáveis para a organização, e os agentes continuam sujeitos a erros, a manipulação e a custos difíceis de controlar. Este trabalho propõe a Arquitetura PASE (*Personalized Adaptive Software Ecosystem*), que estrutura o ciclo de vida do software com agentes de IA para automatizá-lo ao máximo, mantendo com pessoas as decisões que geram consequência. Os requisitos da arquitetura derivam de uma revisão narrativa estruturada da literatura sobre cinco dimensões do ecossistema de software: indústria, desenvolvimento, experiência do usuário, segurança e governança, e mercado de trabalho. A PASE organiza-se em três camadas. A Camada de Tarefas gera demandas a partir de usuários, da equipe e da própria IA e as filtra com base no que já foi implementado ou recusado. A Camada de Orquestração prioriza as tarefas, organiza suas dependências e reserva a pessoas a aprovação da tarefa, do plano, da entrega e da publicação. A Camada de Execução produz código em ambiente isolado, verificado por testes e revisado por um agente independente, e limita a personalização da interface a áreas com contratos verificáveis. Uma prova de conceito, aplicada a um painel financeiro pessoal, levou uma demanda escrita em linguagem natural até uma versão publicada do produto e personalizou a interface por usuário, recusando conteúdos maliciosos. Os dois fluxos demonstraram as três camadas operando em conjunto, com decisão humana nos pontos críticos e registro de cada decisão. Como contribuições, o trabalho oferece a análise multidimensional e seus requisitos, a arquitetura como modelo de referência aplicável a diferentes produtos de software, a prova de conceito e um princípio de projeto: garantias baseadas apenas em instruções ao modelo não são garantias, e precisam ser verificadas por código ou decididas por uma pessoa.

**Palavras-chave**: Inteligência Artificial Agêntica. Engenharia de Software. Autonomia Supervisionada. Ciclo de Vida de Software. Interfaces Adaptativas. Governança de IA.

## Abstract

Agentic artificial intelligence is changing the role of software: from a tool that supports human work, it becomes a system capable of performing that work. For companies that develop software, this opens the possibility of automating a large part of the development cycle, from identifying what should be built to delivering it to production. In practice, however, the gains obtained by individual developers do not yet translate into faster and more stable deliveries for the organization, and agents remain subject to errors, manipulation and costs that are hard to control. This work proposes the PASE Architecture (Personalized Adaptive Software Ecosystem), which structures the software life cycle with AI agents in order to automate it as much as possible, while keeping the decisions that carry consequences with people. The architecture's requirements derive from a structured narrative review of the literature on five dimensions of the software ecosystem: industry, development, user experience, security and governance, and the labor market. PASE is organized into three layers. The Task Layer generates demands from users, the team and the AI itself and filters them based on what has already been implemented or rejected. The Orchestration Layer prioritizes tasks, organizes their dependencies and reserves to people the approval of the task, the plan, the delivery and the release. The Execution Layer produces code in an isolated environment, verified by tests and reviewed by an independent agent, and limits interface personalization to areas with verifiable contracts. A proof of concept, applied to a personal finance dashboard, took a request written in natural language to a released version of the product and personalized the interface per user, rejecting malicious content. The two flows showed the three layers operating together, with human decisions at the critical points and a record of every decision. The contributions of this work are the multidimensional analysis and its requirements, the architecture as a reference model applicable to different software products, the proof of concept, and a design principle: guarantees based only on instructions to the model are not guarantees, and must be verified by code or decided by a person.

**Keywords**: Agentic Artificial Intelligence. Software Engineering. Supervised Autonomy. Software Life Cycle. Adaptive Interfaces. AI Governance.

## Lista de Ilustrações

Figura 1 - Criação de valor acumulado projetada impulsionada por IA
Figura 2 - Efeito estimado da adoção de IA sobre os principais resultados do desenvolvimento de software
Figura 3 - Correção sintática e segurança do código gerado por IA ao longo do tempo
Figura 4 - Visão geral da Arquitetura PASE
Figura 5 - Camada de Tarefas da Arquitetura PASE
Figura 6 - Camadas de Orquestração e de Execução da Arquitetura PASE
Figura 7 - Ciclo de vida de uma tarefa na Arquitetura PASE
Figura 8 - Contrato rígido de uma Zona Dinâmica: payload válido e payload recusado
Figura 9 - Descartadas: propostas barradas pelo funil por duplicidade ou incoerência, com o motivo de cada descarte
Figura 10 - Dependências: grafo das tarefas, com nós coloridos por estado e arestas de dependência
Figura 11 - Sistema: fila de execução, memória vetorial, consumo acumulado, travas e prompts versionados
Figura 12 - Contexto: documentos do produto versionados no banco e as etapas do ciclo que leem cada um
Figura 13 - FinTrack antes da solicitação: interface apenas em tema claro, sem controle de tema
Figura 14 - A solicitação: (a) demanda em linguagem natural enviada pela usuária no FinTrack; (b) tarefa candidata qualificada no painel do PASE, aguardando decisão
Figura 15 - Documento de Planejamento Técnico: arquivos previstos e ação sobre cada um, critérios de aceite, estimativas e trilho do ciclo de vida
Figura 16 - Execução registrada: diferenças de código, verificações automáticas e transcrição integral da interação com os modelos
Figura 17 - Homologação: parecer da revisão independente por critério de aceite e decisão do gestor
Figura 18 - Tela Entrega: tarefa no ramo de integração, versão 1.0.0 validada e publicação sob aprovação humana
Figura 19 - Pull request da versão 1.0.0 aberto pelo PASE no GitHub, com o corpo exigido pelo guia de fluxo de ramos
Figura 20 - FinTrack após a entrega: botão "Usar tema escuro" e paleta escura aplicada a todas as telas
Figura 21 - Simulador do painel: o uso intenso de relatórios pela persona Ana aciona a zona do painel inicial e o UPA gera um payload declarativo
Figura 22 - Personalização em execução: Ana vê o componente gerado pelo UPA, com o selo "personalizado", enquanto Clara mantém o componente nativo
Figura 23 - Defesa em profundidade: payloads maliciosos injetados sem validação do servidor, recusados pelo cliente e registrados como violação

## Lista de Quadros

Quadro 1 - Lacunas por dimensão e requisitos derivados para uma arquitetura de software agêntico
Quadro 2 - Comparação entre os trabalhos relacionados e a Arquitetura PASE
Quadro 3 - Componentes implementados na prova de conceito e escopo remanescente
Quadro 4 - Percurso do Fluxo 1 pelos componentes da Arquitetura PASE
Quadro 5 - Percurso do Fluxo 2 pelos componentes da Arquitetura PASE
Quadro 6 - Requisitos da arquitetura e evidências da validação

## Lista de Abreviaturas e Siglas

CHI - *Conference on Human Factors in Computing Systems*
CSV - *Comma-Separated Values*
DAG - *Directed Acyclic Graph* (grafo acíclico direcionado)
DORA - *DevOps Research and Assessment*
HULA - *Human-in-the-Loop LLM-based Agents*
IA - Inteligência Artificial
ICLR - *International Conference on Learning Representations*
JSON - *JavaScript Object Notation*
LLM - *Large Language Model* (modelo de linguagem de grande escala)
NIST - *National Institute of Standards and Technology*
OWASP - *Open Worldwide Application Security Project*
PASE - *Personalized Adaptive Software Ecosystem*
PL - Projeto de Lei
PoC - *Proof of Concept* (prova de conceito)
QP - Questão de Pesquisa
RAG - *Retrieval-Augmented Generation* (geração aumentada por recuperação)
SOP - *Standard Operating Procedure* (procedimento operacional padronizado)
UFF - Universidade Federal Fluminense
UPA - *User Personalization Agent*
XSS - *Cross-Site Scripting*

## Sumário

Campo automático do Word (Referências > Atualizar Tabela), sem a "lista em texto" que o modelo
traz logo abaixo. Ao final, ele deve produzir exatamente esta estrutura:

```
ELEMENTOS PRÉ-TEXTUAIS
  Capa e Folha de Rosto
  Ficha Catalográfica
  Folha de Aprovação
  Dedicatória
  Agradecimentos
  Declaração de Considerações Éticas
  Declaração de Uso de IA Generativa
  Resumo
  Abstract
  Lista de Ilustrações
  Lista de Quadros
  Lista de Abreviaturas e Siglas
  Sumário
ELEMENTOS TEXTUAIS
1 INTRODUÇÃO
  1.1 Contexto
  1.2 Objetivos
  1.3 Metodologia
  1.4 Organização do Texto
2 SOFTWARE NA ERA DA IA AGÊNTICA: IMPACTOS E LACUNAS
  2.1 a 2.6
3 TRABALHOS RELACIONADOS
  3.1 a 3.6
4 PROPOSTA: A ARQUITETURA PASE
  4.1 a 4.6 (com 4.3.1 a 4.3.5, 4.4.1 a 4.4.6, 4.5.1 a 4.5.6)
5 IMPLEMENTAÇÃO
  5.1 Visão Geral e Tecnologias
  5.2 Implementação das Camadas
  5.3 Painel de Controle
6 VALIDAÇÃO
  6.1 Método de Validação
  6.2 Fluxo 1: da Demanda ao Código em Produção
  6.3 Fluxo 2: Personalização em Tempo de Execução
  6.4 Síntese dos Resultados
7 CONCLUSÃO
  7.1 Contribuições
  7.2 Limitações
  7.3 Trabalhos Futuros
REFERÊNCIAS
APÊNDICE A - PROMPTS VERSIONADOS DA PROVA DE CONCEITO
APÊNDICE B - CONTRATO CANÔNICO DAS ZONAS DINÂMICAS
APÊNDICE C - REPRODUÇÃO DA PROVA DE CONCEITO
```

=====

# Notas (não colar no documento)

## O que mudou em relação à versão anterior

| Elemento | Mudança |
|---|---|
| Declaração de Considerações Éticas | Reduzida a uma frase ("Não há considerações éticas a declarar…"). Saíram o parágrafo dos riscos de projeto, que já está no Capítulo 4, e a frase sobre rede, que contradizia o Capítulo 5 |
| Declaração de Uso de IA Generativa | Entrou o *gpt-4.1* (geração exploratória). Os papéis dos modelos agora batem com a Seção 5.1: o *gpt-4.1-mini* também faz a personalização, e o *gpt-5.3-codex* também faz o planejamento. As versões do Claude passam a ser Opus 5.5 e Sonnet 5.5 |
| Resumo e Abstract | Substituídos pelo Resumo novo (versão dos autores) e sua tradução. Não citam mais números de validação nem "22 trabalhos". A palavra-chave "Sistemas Multiagente" virou "Ciclo de Vida de Software" (*Software Life Cycle*, no Abstract) |
| Lista de Ilustrações | A Figura 14 ganhou as partes (a) e (b), igual à legenda do corpo. O resto já estava correto |
| Lista de Quadros | Sem mudança |
| Lista de Abreviaturas | Saiu a sigla **API** (só aparece escrita por extenso ou dentro de "FastAPI") |
| Sumário | Mantido como campo automático. O Sumário já está certo no PDF novo; o que sobrou errado é a "lista em texto" logo abaixo dele |

## Pendências nos elementos pré-textuais

1. **Apague a "lista em texto" que vem depois do Sumário**, junto com a linha "(Clique com o botão
   direito e escolha 'Atualizar campo'...)". É instrução do modelo, não conteúdo. Ela ainda tem
   "5 IMPLEMENTAÇÃO E VALIDAÇÃO", "6 CONCLUSÃO", "Material e Métodos" e "ANEXOS", que não existem mais.
2. **Resumo e Abstract** dizem que a prova de conceito "levou uma demanda … até uma versão publicada" e "recusou conteúdos maliciosos". Se algum fluxo sair diferente na execução, ajuste essas duas frases.
3. **Referências**: o PDF mandado tem várias obras citadas no texto que não estão na lista (Becker, Brynjolfsson, Deng, DORA 2026, Eltahier, Leviathan, McKinsey, METR, NIST, OWASP, Scale AI, Stack Overflow, União Europeia, Veracode). Isso independe do Resumo, que não cita mais o número de trabalhos revisados.
4. **Marcadores que continuam em aberto**: Ficha Catalográfica, Folha de Aprovação, Dedicatória,
   Agradecimentos, "[confirmar versões utilizadas]" e "[Confirmar e completar com outras
   ferramentas...]". São de vocês.
5. **Quadro A.1** (Apêndice A) não está na Lista de Quadros. Se a norma da UFF pedir os quadros
   dos apêndices, acrescente "Quadro A.1 - Prompts da prova de conceito e componentes
   correspondentes" depois do Quadro 6.
6. **Depois de tudo corrigido**, atualize todos os campos do Word (Ctrl+A, F9) para a Lista de
   Ilustrações, a Lista de Quadros e o Sumário saírem com os números de página certos.
