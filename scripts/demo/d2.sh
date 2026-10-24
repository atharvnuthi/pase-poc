#!/usr/bin/env bash
# D2 - Memória Histórica (SPEC-03 §8.1-8.3).
#
# Prova que o sistema não trabalha duas vezes: reconhece o que já existe, recusa
# o que não cabe no produto, e lembra do que recusou.
source "$(dirname "$0")/_comum.sh"

titulo "D2 · o funil barrando trabalho repetido e fora de escopo"

passo "1. Pedido de algo que o FinTrack já faz"
espera "descartada_duplicata, batendo com 'Relatórios mensais'"
E=$(post "$CORE/api/proposals/external" '{"user_id":1,"text":"Quero ver um relatório dos meus gastos por mês"}')
obteve "$(campo "$E" outcome) - $(campo "$E" detail)"
checar "reconhecida como duplicata" "$(campo "$E" outcome)" "descartada_duplicata"
MATCH=$(printf '%s' "$E" | python -c "import sys,json;d=json.load(sys.stdin)['matched_ref'];print(f\"{d['kind']}#{d['ref_id']} sim={d['similarity']}\")" 2>/dev/null)
nota "bateu com: $MATCH"
nota "duplicate_count agora: $(campo "$E" duplicate_count)"

passo "2. Pedido que viola o escopo do produto"
espera "descartada_incoerente, com o motivo escrito e guardado"
E=$(post "$CORE/api/proposals/external" '{"user_id":1,"text":"Adicionar um minigame de corrida de carros dentro do app para relaxar"}')
obteve "$(campo "$E" outcome)"
checar "recusada por incoerência" "$(campo "$E" outcome)" "descartada_incoerente"
nota "motivo: $(campo "$E" detail)"

passo "3. A mesma ideia, com outras palavras"
espera "descartada_duplicata - a memória de descartes barra a reincidência"
E=$(post "$CORE/api/proposals/external" '{"user_id":1,"text":"Colocar um joguinho de corrida no aplicativo pra distrair enquanto olho as contas"}')
obteve "$(campo "$E" outcome) · duplicate_count=$(campo "$E" duplicate_count)"
checar "barrada pela memória" "$(campo "$E" outcome)" "descartada_duplicata"
checar "contador do descarte anterior subiu" "$(campo "$E" duplicate_count)" "2"
nota "sem isso o mesmo pedido seria reavaliado - e recusado - toda vez que aparecesse"

fim "D2"
