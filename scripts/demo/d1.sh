#!/usr/bin/env bash
# D1 - Evolução de código de ponta a ponta (SPEC-04 §10).
#
# Prova o loop lento inteiro: uma frase de usuário vira código no repositório,
# passando por um gate humano que aqui é automatizado para a demo rodar sozinha.
source "$(dirname "$0")/_comum.sh"

titulo "D1 · do pedido ao merge, com aprovação humana"
nota "Pré: 'make reset && make seed' e o seu trabalho commitado."

passo "1. Uma sugestão interna entra pelo funil"
espera "a proposta é aceita e vira tarefa candidata"
ENV=$(post "$CORE/api/proposals/internal" \
  '{"type":"funcional","author":"Atharv","text":"Exportar minhas transacoes em CSV"}')
OUTCOME=$(campo "$ENV" outcome); TASK=$(campo "$ENV" task_id)
obteve "$OUTCOME (task #$TASK)"
checar "virou candidata" "$OUTCOME" "candidata"
[ -n "$TASK" ] || fim "D1"

passo "2. O gestor aprova - a cadeia autônoma começa"
espera "planejamento → despacho → execução, e parada em homologação"
post "$CORE/api/tasks/$TASK/approve" '{}' > /dev/null
nota "acompanhando (pode levar alguns minutos)…"
ESTADO=$(esperar_estado "$TASK" "em_homologacao|suspensa|finalizada" 900)
obteve "$ESTADO"
checar "parou para o humano decidir" "$ESTADO" "em_homologacao"

passo "3. O que a máquina já verificou antes de chamar você"
DET=$(get "$CORE/api/tasks/$TASK")
RUN=$(printf '%s' "$DET" | python -c "import sys,json;r=json.load(sys.stdin)['runs'];print(r[-1]['id'] if r else '')")
ARQ=$(printf '%s' "$DET" | python -c "import sys,json;print(', '.join(json.load(sys.stdin)['planning']['affected_files']))")
nota "planejou: $ARQ"
LOG=$(get "$CORE/api/runs/$RUN/artifact/logs")
contem "ruff passou" "$LOG" "All checks passed"
contem "pytest rodou" "$LOG" "pytest"
DIFF=$(get "$CORE/api/runs/$RUN/artifact/diff")
if [ -z "$(printf '%s' "$DIFF" | tr -d '[:space:]')" ]; then
  falha "o diff saiu VAZIO - o Executor não teve o que escrever"
  nota "provável causa: o endpoint já existe no repositório, de uma execução anterior."
  nota "'make reset' zera a memória do PASE, mas não o código do alvo. Para repetir a d1:"
  nota "  git revert -m 1 \$(git log --grep='pase: integra' --format=%H -1) && make reset"
  fim "D1"
fi
nota "diff com $(printf '%s' "$DIFF" | grep -c '^+') linhas adicionadas"
TRANS=$(get "$CORE/api/runs/$RUN/artifact/transcript")
nota "transcript com $(printf '%s' "$TRANS" | wc -l) mensagens registradas"

passo "4. Homologação: o humano aprova e o código entra na branch principal"
espera "merge feito e tarefa finalizada como aprovada"
HOM=$(post "$CORE/api/tasks/$TASK/homologation" \
  '{"decision":"aprovar","comment":"Revisado na demo: testes verdes, sem desvios."}')
obteve "merged=$(campo "$HOM" merged) commit=$(campo "$HOM" commit)"
checar "merge realizado" "$(campo "$HOM" merged)" "True"
sleep 3
checar "tarefa finalizada" "$(get "$CORE/api/tasks/$TASK" | python -c "import sys,json;print(json.load(sys.stdin)['task']['final_outcome'])")" "aprovada"

passo "5. O endpoint novo responde no app que está rodando"
espera "HTTP 200 com CSV de verdade"
nota "aguardando o hot reload do client-backend…"
sleep 12
# só as linhas adicionadas: uma linha de contexto traria uma rota que já existia
ROTA=$(printf '%s' "$DIFF" | python "$(dirname "$0")/_rota.py")
if [ -z "$ROTA" ]; then falha "o diff não acrescentou nenhuma rota GET"; ROTA=/transactions/export; fi
nota "rota que o PASE escreveu: $ROTA"
CODE=$(curl -s -o /tmp/d1.csv -w '%{http_code}' "$CLIENT$ROTA?user_id=1")
obteve "HTTP $CODE"
checar "endpoint no ar" "$CODE" "200"
nota "primeiras linhas:"; head -3 /tmp/d1.csv | sed 's/^/    /'

passo "6. A memória do sistema cresceu"
espera "o item aparece em implemented_items - pedir de novo vira duplicata"
IMPL=$($COMPOSE exec -T db psql -U pase -d pase -t -A -c \
  "SELECT count(*) FROM implemented_items WHERE task_id = $TASK;" 2>/dev/null | tr -d '[:space:]')
checar "registrado como implementado" "$IMPL" "1"

fim "D1"
