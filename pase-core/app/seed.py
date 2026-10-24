"""Baseline do PASE (`make seed`) - SPEC-06 §6.2 e §6.3.

Sem isto o Motor de Filtragem não tem contra o que comparar: toda proposta
passaria como novidade e a Memória Histórica nunca barraria nada.

São duas memórias:
- **implementadas**: o que o FinTrack já faz. Bate contra propostas que pedem
  algo existente (critério 1 do SPEC-03).
- **descartes históricos**: o que já foi recusado e por quê. Barra reincidência
  (critério 3) e é o insumo da Reavaliação Cíclica (critério 8).

Idempotente: limpa e regrava. Gera embeddings de verdade - custa alguns
centavos de dólar a cada `make seed` e é o que faz a busca vetorial funcionar.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text

from app.common.db import init_db, session_scope
from app.common.vector_store import save_embedding
from app.task_layer.models import DiscardedProposal, ImplementedItem, Proposal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("pase.seed")

# SPEC-06 §6.2 - o que o FinTrack já faz hoje
IMPLEMENTADAS = [
    (
        "Cadastro de transações",
        "Usuário registra uma transação de receita ou despesa informando valor, "
        "data, categoria e descrição.",
    ),
    (
        "Edição e exclusão de transações",
        "Usuário altera ou remove uma transação já registrada.",
    ),
    (
        "Resumo de saldo",
        "O dashboard mostra o saldo do usuário, calculado como receitas menos despesas.",
    ),
    (
        "Gastos por categoria",
        "O dashboard agrupa as despesas do usuário por categoria e mostra o total de cada uma.",
    ),
    (
        "Relatórios mensais",
        "A tela de relatórios mostra os totais de receitas, despesas e saldo agregados "
        "por mês, permitindo comparar um mês com outro.",
    ),
    (
        "Seletor de persona",
        "A tela inicial permite escolher entre os usuários cadastrados; não há login real.",
    ),
    (
        "Categorias fixas",
        "As categorias disponíveis são definidas pelo sistema e não podem ser criadas "
        "ou editadas pelo usuário final.",
    ),
    (
        "Validações do formulário de transação",
        "O formulário recusa valor menor ou igual a zero, data futura e categoria "
        "inexistente, exibindo a mensagem no campo correspondente.",
    ),
    (
        "Edição da data de uma transação na lista",
        "Usuário corrige a data de uma transação já lançada direto na linha da lista.",
    ),
    (
        "Exportação das transações em CSV",
        "Usuário baixa as próprias transações em um arquivo CSV.",
    ),
    (
        "Orçamento mensal por categoria",
        "Usuário define um limite de gasto por categoria e acompanha quanto do limite já "
        "foi consumido no mês, com aviso ao chegar perto do teto ou estourá-lo.",
    ),
    (
        "Metas de economia",
        "Usuário cria metas com valor-alvo e prazo opcional, registra quanto já guardou e "
        "vê o progresso e quanto guardar por mês para chegar no prazo.",
    ),
    (
        "Busca e filtros nas transações",
        "Usuário busca transações pela descrição e filtra por categoria, tipo e mês.",
    ),
    (
        "Evolução mensal no dashboard",
        "O dashboard mostra o orçamento do mês, as últimas transações e um gráfico de "
        "receitas e despesas dos últimos meses.",
    ),
    (
        "Variação das despesas nos relatórios",
        "A tela de relatórios compara as despesas de cada mês com as do mês anterior.",
    ),
]

# SPEC-06 §6.3 - descartes históricos, com motivos escritos como o P2a escreveria.
# O quarto é deliberadamente reversível: o D8 edita os documentos de contexto para
# remover a restrição citada e a Reavaliação Cíclica deve reintroduzir a proposta.
DESCARTES = [
    (
        "Minerar criptomoedas no app",
        "Usar o computador do usuário para minerar criptomoedas enquanto o FinTrack "
        "estiver aberto, gerando renda extra.",
        "O contexto do projeto lista, em 'Fora de escopo por decisão de produto', a linha "
        "'Investimentos, câmbio, múltiplas moedas.'. Minerar criptomoedas é atividade de "
        "geração de receita, não acompanhamento de gastos, e cai exatamente no que essa "
        "linha exclui.",
    ),
    (
        "Editor de vídeo integrado",
        "Incluir um editor de vídeo dentro do FinTrack para o usuário montar vídeos "
        "sobre sua vida financeira.",
        "Nada no contexto do projeto sustenta edição de mídia. O produto tem quatro "
        "módulos - dashboard, transações, relatórios e suporte - e um editor de vídeo "
        "não se conecta a nenhum deles nem às regras de negócio centrais.",
    ),
    (
        "Rede social entre usuários",
        "Permitir que usuários sigam uns aos outros, comentem e comparem seus gastos "
        "publicamente dentro do app.",
        "O contexto do projeto lista explicitamente 'qualquer forma de rede social ou "
        "compartilhamento entre usuários' como fora de escopo por decisão de produto. "
        "Além disso, a regra central diz que toda transação pertence a exatamente um "
        "usuário, o que é incompatível com exposição pública de dados financeiros.",
    ),
    # Este quarto descarte é deliberadamente reversível (SPEC-06 §6.3): o D8 remove
    # do contexto a linha que ele cita, e a Reavaliação Cíclica deve
    # reintroduzir a proposta. O tema é gamificação: orçamentos e metas entraram no escopo
    # (eram o tema deste descarte) e exportar CSV é o que o critério 4 do SPEC-03 e o D1
    # do SPEC-04 pedem que passe pelo funil, então nenhum dos dois pode ser a restrição.
    (
        "Medalhas e conquistas por economizar",
        "Dar medalhas e conquistas ao usuário quando ele cumprir metas e economizar, "
        "com um placar do progresso dele.",
        "O contexto do projeto lista, em 'Fora de escopo por decisão de produto', a linha "
        "'Gamificação.'. A proposta pede exatamente o que essa linha exclui: medalhas, "
        "conquistas e placar são mecânica de jogo.",
    ),
]


#: TRUNCATE em vez de DELETE linha a linha: o ORM decidia sozinho a ordem dos
#: deletes e esbarrava na FK de `tasks` para `proposals`. CASCADE resolve a ordem
#: e RESTART IDENTITY faz os ids recomeçarem do 1, o que deixa as demos
#: reproduzíveis - o mesmo roteiro cita sempre os mesmos números.
#:
#: `llm_calls` NÃO entra aqui. Além de ser trilha de auditoria de custo, que faz
#: sentido preservar entre seeds, truncá-la causaria deadlock: o TRUNCATE segura
#: um lock exclusivo na tabela e cada `embed()` seguinte tenta registrar a chamada
#: por uma conexão separada, que ficaria esperando a transação que a espera.
TABELAS = (
    "task_state_history",
    "tasks",
    "discarded_proposals",
    "proposals",
    "implemented_items",
    "telemetry_events",
)


def wipe() -> None:
    """Zera em transação própria, fechada antes de qualquer chamada de LLM."""
    alvos = ", ".join(TABELAS)
    with session_scope() as session:
        session.execute(text(f"TRUNCATE {alvos} RESTART IDENTITY CASCADE"))


def run() -> None:
    init_db()

    wipe()

    with session_scope() as session:
        for title, description in IMPLEMENTADAS:
            item = ImplementedItem(title=title, description=description)
            session.add(item)
            session.flush()
            save_embedding("implemented", item.id, f"{title}\n{description}", session=session)

        for title, description, motivo in DESCARTES:
            proposta = Proposal(
                origin="internal",
                type="funcional",
                author="PASE Seed",
                raw_text=description,
                title=title,
                description=description,
                module="geral",
                outcome="descartada_incoerente",
            )
            session.add(proposta)
            session.flush()

            descarte = DiscardedProposal(
                proposal_id=proposta.id,
                reason_type="incoerente",
                reason_text=motivo,
                duplicate_count=1,
            )
            session.add(descarte)
            session.flush()
            save_embedding(
                "discarded", descarte.id, f"{title}\n{description}", session=session
            )

        implementadas = len(session.execute(select(ImplementedItem)).scalars().all())
        descartes = len(session.execute(select(DiscardedProposal)).scalars().all())

    print(
        f"[pase-core] baseline ok: {implementadas} itens implementados e "
        f"{descartes} descartes históricos, todos com embedding."
    )


if __name__ == "__main__":
    run()
