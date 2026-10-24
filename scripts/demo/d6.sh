#!/usr/bin/env bash
# D6 - Contenção da generatividade (SPEC-04 §10).
#
# Os dois guardrails do SPEC-00 §4 são código que impede a ação, não prompt
# pedindo cautela ao modelo. Aqui eles são forçados a atuar.
source "$(dirname "$0")/_comum.sh"

titulo "D6 · o que acontece quando o Executor falha ou gasta demais"

criar() {
  post "$CORE/api/proposals/internal" "{\"type\":\"funcional\",\"author\":\"Atharv\",\"text\":\"$1\"}" \
    | python -c "import sys,json;print(json.load(sys.stdin).get('task_id') or '')"
}

passo "1. Teto de tentativas: duas falhas seguidas"
espera "falha → retry → falha → suspensa com alerta 'retries'"
A=$(criar   "Demo de falha controlada: acrescentar um campo de observacao na transacao"   "Permitir anexar uma nota livre a cada transacao"   "Exibir a data de criacao de cada transacao na listagem")
[ -n "$A" ] || fim "D6"
nota "task #$A criada"
patch_ "$CORE/api/tasks/$A/demo" '{"force_fail_runs":2}' > /dev/null
post "$CORE/api/tasks/$A/approve" '{}' > /dev/null
ESTADO=$(esperar_estado "$A" "suspensa|em_homologacao|finalizada" 900)
DET=$(get "$CORE/api/tasks/$A")
ALERTA=$(printf '%s' "$DET" | python -c "import sys,json;print(json.load(sys.stdin)['task']['alert'])")
obteve "$ESTADO / alerta=$ALERTA"
checar "suspensa para decisão humana" "$ESTADO" "suspensa"
checar "alerta de tentativas" "$ALERTA" "retries"
printf '%s' "$DET" | python -c "
import sys,json
for r in json.load(sys.stdin)['runs']:
    print(f\"    tentativa {r['attempt']} [{r['trigger']}]: {r['status']} - {r['failure_reason']}\")"
nota "o sistema não insiste para sempre: ele para e devolve a decisão a uma pessoa"

passo "2. Teto de custo: budget de 100 tokens"
espera "interrompida_budget, sem nenhuma chamada ao modelo"
B=$(criar   "Permitir marcar uma transacao como favorita"   "Permitir arquivar uma transacao antiga sem excluir"   "Mostrar um contador de transacoes no rodape da listagem")
[ -n "$B" ] || fim "D6"
nota "task #$B criada"
patch_ "$CORE/api/tasks/$B/demo" '{"budget_cap_tokens":100}' > /dev/null
post "$CORE/api/tasks/$B/approve" '{}' > /dev/null
ESTADO=$(esperar_estado "$B" "suspensa|em_homologacao|finalizada" 900)
DET=$(get "$CORE/api/tasks/$B")
ALERTA=$(printf '%s' "$DET" | python -c "import sys,json;print(json.load(sys.stdin)['task']['alert'])")
obteve "$ESTADO / alerta=$ALERTA"
checar "suspensa" "$ESTADO" "suspensa"
checar "alerta de budget" "$ALERTA" "budget"
printf '%s' "$DET" | python -c "
import sys,json
for r in json.load(sys.stdin)['runs']:
    print(f\"    run: {r['status']}, {r['tokens_real']} tokens gastos - {r['failure_reason']}\")"
nota "a verificação é preditiva: cortou ANTES de enviar a chamada que não cabia"

fim "D6"
