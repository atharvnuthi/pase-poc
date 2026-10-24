#!/usr/bin/env bash
# D5 - Defesa em profundidade (SPEC-05 §8, SPEC-00 §6).
#
# Mesmo com a validação do core contornada, o cliente recusa. Uma Zona Dinâmica
# nunca executa código arbitrário - e a regra não tem exceção neste projeto.
source "$(dirname "$0")/_comum.sh"
SLOT=resumo_financeiro

titulo "D5 · três payloads maliciosos, três recusas"
nota "O injetor grava PULANDO a validação do core. É o pior caso possível."

injetar() {
  R=$(post "$CORE/api/upa/inject-raw" "{\"user_id\":1,\"slot\":\"$SLOT\",\"payload\":$2}")
  nota "$1"
  nota "  gravado como payload #$(campo "$R" payload_id), origin=injetado"
  printf '%s' "$R" | python -c "import sys,json;print('    o core recusaria por:', '; '.join(json.load(sys.stdin)['erros_do_core'])[:160])" 2>/dev/null
  REC=$(campo "$R" core_o_recusaria)
  checar "  o core o consideraria inválido" "$REC" "True"
}

passo "1. Label com 500 caracteres (estouro de layout)"
injetar "label gigante" "{\"widget\":\"alert_banner\",\"label\":\"$(python -c 'print("x"*500)')\",\"tone\":\"atencao\"}"

passo "2. Link externo (tentativa de phishing)"
injetar "href externo" '{"widget":"shortcut_list","label":"Oferta imperdivel","maxItems":1,"items":[{"label":"Clique aqui","href":"https://site-externo.example/phishing"}]}'

passo "3. Widget fora do catálogo (tentativa de injetar componente)"
injetar "widget desconhecido" '{"widget":"iframe_injector","label":"Um iframe","tone":"neutral"}'

passo "4. A validação do cliente, que é a definitiva"
espera "o mesmo schema Zod que roda no navegador recusa os três"
$COMPOSE exec -T client-frontend sh -c "cat > /tmp/d5.ts <<'TS'
import { zonePayloadSchema, descreverErro } from '/app/dynamic-zones/schema.ts';
const casos: [string, unknown][] = [
  ['label gigante', { widget: 'alert_banner', label: 'x'.repeat(500), tone: 'atencao' }],
  ['href externo', { widget: 'shortcut_list', label: 'Oferta', maxItems: 1, items: [{ label: 'Clique', href: 'https://site-externo.example/phishing' }] }],
  ['widget desconhecido', { widget: 'iframe_injector', label: 'iframe', tone: 'neutral' }],
];
for (const [nome, p] of casos) {
  const r = zonePayloadSchema.safeParse(p);
  console.log(r.success ? 'ACEITO ' + nome : 'RECUSADO ' + nome + ' -> ' + descreverErro(r.error));
}
TS
node --experimental-strip-types /tmp/d5.ts 2>/dev/null" | sed 's/^/    /'

RECUSAS=$($COMPOSE exec -T client-frontend sh -c "node --experimental-strip-types /tmp/d5.ts 2>/dev/null" | grep -c RECUSADO)
checar "os três recusados pelo cliente" "$(printf '%s' "$RECUSAS" | tr -d '[:space:]')" "3"

passo "5. O SDK avisa o core de cada recusa"
espera "três violações registradas, com motivos distintos"
nota "é o POST que o <DynamicZone> dispara ao cair no fallback (SPEC-05 §5.4)"
$COMPOSE exec -T client-frontend sh -c "node --experimental-strip-types /tmp/d5.ts 2>/dev/null"   | python -c "
import json, sys, urllib.request
enviadas = 0
for linha in sys.stdin:
    if not linha.startswith('RECUSADO'):
        continue
    motivo = linha.split('->', 1)[-1].strip()
    corpo = json.dumps({'user_id': 1, 'slot': '$SLOT', 'reason': motivo}).encode()
    req = urllib.request.Request(
        '$CORE/api/upa/violations', data=corpo,
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=20)
    enviadas += 1
print(f'    {enviadas} violação(ões) reportadas ao core')
"
MOTIVOS=$(get "$CORE/api/upa/violations" | python -c "
import sys,json
d=json.load(sys.stdin)
print(len({v['reason'] for v in d}))")
obteve "$MOTIVOS motivo(s) distinto(s) registrado(s)"
checar "três violações com motivos diferentes" "$MOTIVOS" "3"

passo "6. O que o usuário vê"
nota "abra http://localhost:3001 como Ana: o dashboard mostra o resumo NATIVO."
nota "cada recusa vira uma linha em http://localhost:3000/zonas, com o motivo e o payload bruto."

fim "D5"
