#!/usr/bin/env bash
# Helpers dos roteiros de demonstração (SPEC-06 §7).
#
# As demos são roteiro de defesa, não teste automatizado: cada passo anuncia o
# que espera antes de acontecer, para poder ser lido em voz alta enquanto roda.
set -uo pipefail

CORE="${CORE_URL:-http://localhost:8000}"
CLIENT="${CLIENT_API_URL:-http://localhost:8001}"
COMPOSE="${COMPOSE:-docker compose}"

AZUL=$'\e[1;34m'; VERDE=$'\e[1;32m'; VERM=$'\e[1;31m'; CINZA=$'\e[0;90m'; FIM=$'\e[0m'
FALHAS=0

titulo()   { printf '\n%s━━━ %s ━━━%s\n' "$AZUL" "$1" "$FIM"; }
passo()    { printf '\n%s▸ %s%s\n' "$AZUL" "$1" "$FIM"; }
espera()   { printf '  %sesperado:%s %s\n' "$CINZA" "$FIM" "$1"; }
obteve()   { printf '  %sobtido:  %s %s\n' "$CINZA" "$FIM" "$1"; }
nota()     { printf '  %s%s%s\n' "$CINZA" "$1" "$FIM"; }

ok()    { printf '  %s✓ %s%s\n' "$VERDE" "$1" "$FIM"; }
falha() { printf '  %s✗ %s%s\n' "$VERM" "$1" "$FIM"; FALHAS=$((FALHAS+1)); }

# checar "<descrição>" "<obtido>" "<esperado>"
checar() {
  if [ "$2" = "$3" ]; then ok "$1 ($2)"; else falha "$1: esperava '$3', veio '$2'"; fi
}

# contem "<descrição>" "<texto>" "<trecho>"
contem() {
  case "$2" in *"$3"*) ok "$1" ;; *) falha "$1: '$3' não aparece na saída" ;; esac
}

# O corpo vai por stdin, não por argumento: o curl do Windows corrompe acentos
# passados em `-d`, e metade dos textos das demos tem acento.
post() {
  printf '%s' "$2" | curl -s -X POST "$1"     -H 'Content-Type: application/json; charset=utf-8' --data-binary @-
}

patch_() {
  printf '%s' "$2" | curl -s -X PATCH "$1"     -H 'Content-Type: application/json; charset=utf-8' --data-binary @-
}
get()  { curl -s "$1"; }
jqv()  { python -c "import sys,json;d=json.load(sys.stdin);print(eval('d'+'$1') if d else '')" 2>/dev/null; }

# campo <json> <chave>   →  valor simples de um objeto JSON
campo() { printf '%s' "$1" | python -c "import sys,json;print(json.load(sys.stdin).get('$2',''))" 2>/dev/null; }

# esperar_estado <task_id> <estados separados por |> [segundos]
esperar_estado() {
  local id="$1" alvos="$2" limite="${3:-600}" t=0 estado=''
  while [ "$t" -lt "$limite" ]; do
    estado=$(get "$CORE/api/tasks/$id" | python -c "import sys,json;print(json.load(sys.stdin)['task']['status'])" 2>/dev/null)
    case "|$alvos|" in *"|$estado|"*) printf '%s' "$estado"; return 0 ;; esac
    sleep 5; t=$((t+5))
  done
  printf '%s' "${estado:-timeout}"
}

fim() {
  printf '\n'
  if [ "$FALHAS" -eq 0 ]; then
    printf '%s✓ %s: tudo conforme o esperado%s\n\n' "$VERDE" "$1" "$FIM"; exit 0
  fi
  printf '%s✗ %s: %s verificação(ões) falharam%s\n\n' "$VERM" "$1" "$FALHAS" "$FIM"; exit 1
}
