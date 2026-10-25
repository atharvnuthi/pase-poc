#!/usr/bin/env bash
# D2 - Geração por IA (SPEC-03 §8.9).
#
# A única etapa do sistema onde a imprevisibilidade é permitida - e é contida
# logo depois: o texto gerado entra no mesmo funil de qualquer outra proposta.
source "$(dirname "$0")/_comum.sh"

titulo "D2 · o sistema propondo melhorias sozinho"

passo "1. Geração Exploratória (temperatura 0.9)"
espera "uma candidata coerente, ou um descarte legítimo do próprio funil"
E=$(post "$CORE/api/proposals/ai-generate" '{"mode":"exploratoria"}')
OUT=$(campo "$E" outcome)
obteve "$OUT - $(campo "$E" detail)"
case "$OUT" in
  candidata|descartada_duplicata|descartada_incoerente|redirecionada_zona)
    ok "desfecho legítimo do funil ($OUT)" ;;
  *) falha "desfecho inesperado: $OUT" ;;
esac
nota "a proposta passou pelo mesmo filtro das demais - inclusive para ser recusada"

passo "2. Análise de Lacunas (temperatura baixa: é análise, não brainstorm)"
espera "uma integração ainda não feita entre módulos existentes, ou nada"
E=$(post "$CORE/api/proposals/ai-generate" '{"mode":"lacunas"}')
OUT=$(campo "$E" outcome)
obteve "$OUT - $(campo "$E" detail)"
case "$OUT" in
  candidata|descartada_duplicata|descartada_incoerente|redirecionada_zona|sem_proposta)
    ok "desfecho legítimo ($OUT)" ;;
  *) falha "desfecho inesperado: $OUT" ;;
esac

fim "D2"
