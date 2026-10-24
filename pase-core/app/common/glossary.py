"""O vocabulário do sistema, explicado.

O painel é cheio de etiqueta: `risco alto`, `incerteza`, `zona dinâmica`,
`budget`, `duplicata`, `em_homologacao`. Cada uma significa algo preciso e muda
o comportamento do sistema, mas para quem olha de fora são só palavras
coloridas - e uma decisão tomada sem entender a etiqueta é uma decisão tomada no
escuro, que é exatamente o que o gate humano deveria evitar.

Fica no servidor, e não no front, por um motivo: é aqui que os valores são
produzidos. Um glossário escrito do outro lado da API vira ficção assim que
alguém acrescenta um estado e esquece de atualizar o texto - e existe um teste
que confere que todo valor conhecido pelo código tem verbete.
"""

from __future__ import annotations

from app.common import conventions
from app.orchestration import states
from app.orchestration.models import ORIGENS_DE_DEPENDENCIA, SEVERIDADES
from app.task_layer.models import Task  # noqa: F401  (documenta a origem dos campos)


def _verbete(termo: str, significado: str, quem: str, efeito: str) -> dict:
    return {"termo": termo, "significado": significado, "quem_atribui": quem, "efeito": efeito}


ESTADOS = [
    _verbete(
        states.CANDIDATA,
        "Passou pelo funil e está no backlog, esperando alguém aprovar.",
        "o Task Layer, no fim da qualificação",
        "Nada acontece sozinho aqui. É o primeiro gate humano.",
    ),
    _verbete(
        states.EM_PLANEJAMENTO,
        "Aprovada; o sistema está lendo o código e decidindo o que mudar.",
        "a Orquestração, ao receber a aprovação",
        "Produz o Documento de Planejamento: arquivos afetados, roadmap e custo estimado.",
    ),
    _verbete(
        states.AGUARDANDO_PLANO,
        "O plano está pronto e espera uma pessoa aprová-lo, editá-lo ou devolvê-lo.",
        "a Orquestração, quando a tarefa exige aprovação do plano",
        "Nenhum código é escrito antes daqui. É o gate que decide, olhando como o sistema "
        "pretende fazer, se vale gastar a execução.",
    ),
    _verbete(
        states.PRONTA_PARA_DESPACHO,
        "Tem plano, mas ainda não começou a escrever.",
        "a Orquestração, ao terminar o planejamento",
        "Fica aqui enquanto houver dependência pendente - veja a aba de dependências.",
    ),
    _verbete(
        states.EM_EXECUCAO,
        "O Executor está escrevendo código num clone isolado.",
        "a Orquestração, ao despachar",
        "Segura os arquivos do plano: outra tarefa que os dispute espera.",
    ),
    _verbete(
        states.EM_HOMOLOGACAO,
        "O código está pronto e já passou por lint, tipos, testes e build.",
        "o Executor, ao terminar com sucesso",
        "Segundo gate humano. Nada entra na branch principal antes daqui.",
    ),
    _verbete(
        states.SUSPENSA,
        "Parou antes de terminar: falhou demais, estourou o custo, ou foi cancelada.",
        "a política de falhas, o guardrail de budget, ou uma pessoa",
        "Espera decisão: retomar ou recusar. Não consome mais nada enquanto espera.",
    ),
    _verbete(
        states.FINALIZADA,
        "Saiu do fluxo. O desfecho diz como.",
        "a Homologação, a triagem ou o cancelamento",
        "Estado terminal: a tarefa não volta a andar. Reverter muda o desfecho, não o estado.",
    ),
]

DESFECHOS = [
    _verbete(
        "aprovada",
        "Mergeada na branch principal.",
        "você, na Homologação",
        "Entra em `implemented_items`: pedir a mesma coisa de novo vira duplicata.",
    ),
    _verbete(
        "recusada",
        "Rejeitada por uma pessoa, antes ou depois de executar.",
        "você, na triagem ou na Homologação",
        "Entra no Histórico de Descartes com embedding - a memória passa a barrar variações.",
    ),
    _verbete(
        "revertida",
        "Tinha sido mergeada, e o merge foi desfeito.",
        "você, na aba Finalizadas",
        "Sai de `implemented_items`: pedir de novo volta a ser um pedido legítimo.",
    ),
    _verbete(
        "cancelada",
        "Interrompida antes de produzir código aproveitável.",
        "você",
        "Libera quem estava esperando por ela.",
    ),
]

ALERTAS = [
    _verbete(
        "retries",
        "Falhou e as tentativas acabaram.",
        "a política de falhas, após MAX_RETRIES",
        "A tarefa fica suspensa. Retomar zera a contagem.",
    ),
    _verbete(
        "budget",
        "Ia passar do teto de tokens e foi interrompida antes de gastar.",
        "o guardrail de budget, antes da chamada",
        "Contenção da generatividade: é código que impede, não recomendação ao modelo.",
    ),
    _verbete(
        "merge_conflict",
        "O merge na develop não aplicou limpo.",
        "a Homologação",
        "A tarefa continua em homologação até alguém resolver o conflito.",
    ),
    _verbete(
        "ci_develop",
        "O CI da develop reprovou depois do merge e a integração foi desfeita.",
        "a Entrega, ao rodar lint, tipos, testes e build na develop",
        "A tarefa vira revertida. Refazer leva o log da falha ao próximo planejamento.",
    ),
    _verbete(
        "predecessora",
        "Uma tarefa de que esta depende foi suspensa.",
        "a Orquestração, em cascata pelo grafo",
        "Fica suspensa sem gastar nada; volta sozinha ao estado anterior quando a predecessora "
        "for retomada, replanejada ou cancelada.",
    ),
]

RISCOS = [
    _verbete(
        "baixo",
        "Mudança contida, longe de dado financeiro.",
        "a Qualificação (P2b)",
        "Nenhuma exigência extra.",
    ),
    _verbete(
        "medio",
        "Mexe em fluxo relevante ou em infraestrutura.",
        "a Qualificação (P2b); toda Sugestão de Engenharia entra com no mínimo isto",
        "Nenhuma exigência extra, mas pesa na priorização.",
    ),
    _verbete(
        "alto",
        "Toca saldo, valores ou dados financeiros.",
        "a Qualificação (P2b)",
        "Exige justificativa por escrito **mesmo para aprovar**.",
    ),
]

SELOS = [
    _verbete(
        "incerteza",
        "O modelo tem pouca confiança na própria qualificação (abaixo de 0,5).",
        "a Qualificação (P2b)",
        "Não bloqueia nada. É um pedido de atenção extra antes de aprovar.",
    ),
    _verbete(
        "zona dinâmica",
        "A demanda vira configuração de uma Zona Dinâmica, não código permanente.",
        "a Avaliação de Zona (P1b), quando o padrão é de cauda longa",
        "A Execução abre um contrato de zona em vez de escrever funcionalidade fixa.",
    ),
    _verbete(
        "desvio",
        "O Executor tocou arquivo que o plano não previa.",
        "o Executor, comparando o que escreveu com o plano",
        "Não bloqueia (ele tem liberdade), mas aparece destacado para revisão. "
        "Arquivo de teste não conta: acrescentar teste é obrigatório.",
    ),
]

DESCARTES = [
    _verbete(
        "duplicata",
        "Já existe algo equivalente - implementado, na fila, ou já descartado.",
        "a Memória Histórica, por similaridade de cosseno acima de 0,72",
        "Não cria linha nova: incrementa o contador da existente. A frequência é sinal "
        "que a Avaliação de Zona usa.",
    ),
    _verbete(
        "incoerente",
        "Viola o escopo ou uma regra de negócio do produto.",
        "a Coerência Sistêmica (P2a), comparando com o contexto do projeto",
        "Entra na memória com embedding. A Reavaliação Cíclica relê depois, caso o "
        "contexto mude.",
    ),
    _verbete(
        "recusa_humana",
        "Uma pessoa disse não.",
        "você",
        "Entra na memória com embedding, como qualquer outro descarte.",
    ),
]

DEPENDENCIAS = [
    _verbete(
        "arquivo",
        "As duas tarefas mexem nos mesmos arquivos.",
        "a Orquestração, a cada despacho",
        "Recalculada automaticamente: some quando a sobreposição some.",
    ),
    _verbete(
        "semantica",
        "As duas tratam de temas próximos.",
        "a Orquestração, por similaridade das propostas, quando a tarefa fica pronta",
        "Não bloqueia: só informa quem decide, no grafo.",
    ),
    _verbete(
        "manual",
        "Você ligou as duas.",
        "você, no painel",
        "**Nenhum recálculo a remove**: decisão humana não é desfeita por rotina.",
    ),
]

TIPOS_DE_MUDANCA = [
    _verbete(
        tipo,
        {
            "feature": "Funcionalidade nova para quem usa o produto.",
            "fix": "Correção de comportamento errado.",
            "refactor": "Melhora interna sem mudar o que o usuário vê.",
            "docs": "Documentação.",
            "test": "Testes.",
            "chore": "Manutenção, dependências, infraestrutura.",
        }[tipo],
        "o Task Layer, a partir da origem da proposta; editável no painel",
        "Define o prefixo da branch e da mensagem de commit do Executor.",
    )
    for tipo in conventions.TIPOS
]

GLOSSARIO = {
    "Estados da tarefa": ESTADOS,
    "Desfechos": DESFECHOS,
    "Alertas": ALERTAS,
    "Faixas de risco": RISCOS,
    "Selos": SELOS,
    "Motivos de descarte": DESCARTES,
    "Origens de dependência": DEPENDENCIAS,
    "Tipos de mudança": TIPOS_DE_MUDANCA,
}


def termos_cobertos() -> set[str]:
    """Todo termo com verbete. Usado pelo teste que impede o glossário de envelhecer."""
    return {verbete["termo"] for grupo in GLOSSARIO.values() for verbete in grupo}


#: Vocabulários que o código define e o glossário precisa acompanhar.
VOCABULARIOS = {
    "estados": set(states.TRANSICOES),
    "alertas": set(states.ALERTAS) - {"none"},
    "severidades": set(SEVERIDADES),
    "dependencias": set(ORIGENS_DE_DEPENDENCIA),
    "tipos": set(conventions.TIPOS),
}
