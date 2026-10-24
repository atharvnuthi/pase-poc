#!/usr/bin/env bash
# D8 - Os dois jobs de manutenção (SPEC-04 §8 e SPEC-03 §5).
#
# Um lê CÓDIGO procurando o que melhorar. O outro lê DECISÕES PASSADAS
# perguntando se ainda valem. São insumos diferentes e jobs separados.
source "$(dirname "$0")/_comum.sh"
BACKUP="${TMPDIR:-/tmp}/d8-contexto.json"
PY="$(dirname "$0")/_contexto.py"
RESTRICAO="Gamificação"

titulo "D8 · auditoria de código e reavaliação de descartes"

passo "1. Ciclo de Auditoria: o sistema lendo o próprio alvo"
espera "um achado concreto vira proposta com origin=auditoria"
SAIDA=$($COMPOSE exec -T pase-core python -m app.jobs.audit 2>&1 | grep -v '^INFO')
printf '%s\n' "$SAIDA" | sed 's/^/    /'
contem "produziu um achado" "$SAIDA" "achado:"
N=$($COMPOSE exec -T db psql -U pase -d pase -t -A -c \
  "SELECT count(*) FROM proposals WHERE origin='auditoria';" 2>/dev/null | tr -d '[:space:]')
if [ "${N:-0}" -ge 1 ]; then ok "proposta de auditoria registrada ($N)"; else falha "nenhuma proposta origin=auditoria"; fi

passo "2. Reavaliação antes da mudança de contexto"
espera "a recusa de 'medalhas e conquistas' continua de pé"
nota "a asserção olha este descarte específico, não um contador global: descartes"
nota "criados por outras demos podem ser legitimamente revertidos na mesma rodada"
ANTES=$($COMPOSE exec -T pase-core python -m app.jobs.reevaluation 2>&1 | grep -v '^INFO')
VEREDITO=$(printf '%s
' "$ANTES" | grep -A1 "Medalhas e conquistas" | grep -o 'recusa ainda válida: [A-Za-z]*' | head -1)
obteve "${VEREDITO:-(descarte não encontrado)}"
contem "a recusa se sustenta enquanto a linha existe" "$VEREDITO" "válida: True"

passo "3. O humano muda a decisão de produto"
nota "removendo dos documentos de contexto a linha: \"$RESTRICAO\""
REMOVIDOS=$(python "$PY" remover "$RESTRICAO" "$BACKUP")
if [ "${REMOVIDOS:-0}" -ge 1 ]; then ok "restrição removida de $REMOVIDOS documento(s) do contexto"; else falha "a linha não estava em nenhum documento"; fi

passo "4. Reavaliação depois da mudança"
espera "o descarte que se apoiava naquela linha reentra no funil"
DEPOIS=$($COMPOSE exec -T pase-core python -m app.jobs.reevaluation 2>&1 | grep -v '^INFO')
printf '%s\n' "$DEPOIS" | grep -E '^  #|recusa|evidência|reinserida|task|reavaliação' | sed 's/^/    /'
if printf '%s' "$DEPOIS" | grep -q "reinserida"; then
  ok "proposta reintroduzida pela mudança de contexto"
else
  falha "nada foi reintroduzido"
fi
nota "o veredito não é do modelo: ele aponta a linha e o código confere se ela existe"

passo "5. Restaurando o contexto para a demo ser repetível"
python "$PY" restaurar "$BACKUP" >/dev/null && nota "documentos de contexto restaurados" || nota "restaure o contexto pela tela Contexto do painel"

fim "D8"
