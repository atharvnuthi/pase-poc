#!/usr/bin/env bash
# D6 - Captação Passiva → Zona Dinâmica (SPEC-03 §8.7).
#
# A origem de demanda que ninguém digitou: o sistema lê reclamações de suporte e
# percebe que três pessoas querem coisas diferentes no mesmo lugar.
source "$(dirname "$0")/_comum.sh"

titulo "D6 · da reclamação de suporte à decisão de personalizar"

passo "1. Os tickets que o FinTrack recebeu"
get "$CLIENT/tickets" | python -c "
import sys,json
for t in json.load(sys.stdin):
    print(f\"    #{t['id']}: {t['text'][:110]}\")"
nota "os três primeiros esbarram no mesmo limite - mas cada um quer uma saída diferente"

passo "2. O job de captação passiva lê os tickets"
espera "os tickets do mesmo tema são agrupados e viram UMA proposta"
espera "o P1b enxerga cauda longa e marca output_type=zona_dinamica"
SAIDA=$($COMPOSE exec -T pase-core python -m app.jobs.passive_capture 2>&1 | grep -v '^INFO')
printf '%s\n' "$SAIDA" | sed 's/^/    /'

contem "agrupou por tema" "$SAIDA" "tema:"
if printf '%s' "$SAIDA" | grep -q "zona_dinamica"; then
  ok "ao menos uma proposta virou zona dinâmica"
else
  falha "nenhuma proposta recebeu output_type=zona_dinamica"
fi

passo "3. A tarefa resultante"
$COMPOSE exec -T db psql -U pase -d pase -c \
  "SELECT id, left(title,52) AS titulo, module, output_type, status FROM tasks WHERE output_type='zona_dinamica' ORDER BY id DESC LIMIT 3;" 2>/dev/null
nota "demanda homogênea vira código fixo; demanda divergente vira área configurável"

fim "D6"
