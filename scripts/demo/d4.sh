#!/usr/bin/env bash
# D4 - Personalização em runtime (SPEC-05 §8).
#
# O loop rápido: segundos, sem gate humano, sem tocar o repositório. O que
# substitui a aprovação humana é a validação de contrato.
source "$(dirname "$0")/_comum.sh"
SLOT=resumo_financeiro

titulo "D4 · a interface se adaptando ao comportamento de cada usuário"

passo "1. Estado inicial: ninguém tem personalização"
for U in 1 2; do
  C=$(curl -s -o /dev/null -w '%{http_code}' "$CORE/api/upa/zones/$SLOT/payload?user_id=$U")
  nota "user $U → HTTP $C"
done

passo "2. A Ana usa relatórios intensamente"
espera "a regra dispara (5 acessos em 7 dias) e o modelo propõe uma personalização"
R=$(post "$CORE/api/upa/simulate" '{"user_id":1,"scenario":"ana_relatorios"}')
obteve "personalizado=$(campo "$R" personalizado)"
checar "zona configurada" "$(campo "$R" personalizado)" "True"
printf '%s' "$R" | python -c "import sys,json;print('    payload:',json.dumps(json.load(sys.stdin)['payload'],ensure_ascii=False))" 2>/dev/null

passo "3. Ana tem widget; Clara continua no componente nativo"
espera "user 1 → 200 · user 2 → 204"
A=$(curl -s -o /dev/null -w '%{http_code}' "$CORE/api/upa/zones/$SLOT/payload?user_id=1")
C=$(curl -s -o /dev/null -w '%{http_code}' "$CORE/api/upa/zones/$SLOT/payload?user_id=2")
obteve "Ana → HTTP $A · Clara → HTTP $C"
checar "Ana personalizada" "$A" "200"
checar "Clara no nativo" "$C" "204"
nota "abra http://localhost:3001 como Ana e como Clara para ver a diferença na tela"

passo "4. Revogar devolve a Ana ao componente nativo"
espera "204 depois da revogação"
PID=$(get "$CORE/api/upa/payloads" | python -c "import sys,json;d=[p for p in json.load(sys.stdin) if p['user_id']==1 and p['status']=='ativo'];print(d[0]['id'] if d else '')")
post "$CORE/api/upa/payloads/$PID/revoke" '{}' > /dev/null
A=$(curl -s -o /dev/null -w '%{http_code}' "$CORE/api/upa/zones/$SLOT/payload?user_id=1")
obteve "HTTP $A"
checar "voltou ao nativo" "$A" "204"

fim "D4"
