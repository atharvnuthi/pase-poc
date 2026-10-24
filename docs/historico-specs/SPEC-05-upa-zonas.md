# SPEC-05 - UPA + Zonas Dinâmicas

**Fase:** F2–F3 · **Depende de:** SPEC-01 (llm_client), SPEC-02 · **Demos:** D4, D5

## 1. Registro de zonas

O slot e seu contrato vivem em código (`SLOTS = {"resumo_financeiro": schema}`) e em `docs/contracts/resumo_financeiro.schema.json` - fonte canônica. Não há tabela de zonas nesta fase (uma única zona é suficiente para provar o modelo; múltiplas zonas é extensão direta, ver SPEC-10).

## 2. Tabelas (módulo `upa/`)

- `telemetry_events(id, user_id, event, path, at)`
- `zone_payloads(id, user_id, slot, payload jsonb, origin autonoma|injetado, status ativo|revogado, created_at)`
- `zone_violations(id, user_id, slot, reason, raw_payload jsonb, at)`

## 3. Endpoints

| Endpoint | Semântica |
|---|---|
| `POST /api/upa/telemetry {user_id, event, path}` | persiste e dispara avaliação da regra (Seção 4) |
| `GET /api/upa/zones/{slot}/payload?user_id=` | payload `ativo` mais recente → 200 `{payload}`; senão 204 |
| `POST /api/upa/violations {user_id, slot, reason, raw_payload}` | registrado pelo SDK do cliente |
| `POST /api/upa/simulate {user_id, scenario: "ana_relatorios"}` | insere 5 `page_view /relatorios` e dispara avaliação (demo repetível) |
| `POST /api/upa/inject-raw {user_id, slot, payload}` | grava `zone_payloads` pulando a validação do core (`origin=injetado`) - instrumento do D5 |
| `GET /api/upa/payloads` · `GET /api/upa/violations` | listas para a tela Zonas |
| `POST /api/upa/payloads/{id}/revoke` | `status=revogado` |

## 4. Regra e geração (fluxo autônomo)

**Regra:** `count(page_view, path=/relatorios, últimos 7 dias) ≥ 5` **e** não existe payload `ativo` para `(user, resumo_financeiro)` → avaliar.

**P6 - Payload do UPA:** entrada = resumo do comportamento (contagens de `page_view` por rota), finalidade do slot, contrato JSON Schema → saída `{personalize: bool, payload?}`. Diretrizes: personalizar só com benefício claro (Soft Constraint); respeitar o contrato à risca; `href` apenas rotas internas.

**Defesa em profundidade:** o core valida o payload contra o JSON Schema (`jsonschema`) antes de persistir (`origin=autonoma`). Inválido → loga e descarta, não persiste. A validação definitiva é sempre a do cliente (Hard Constraint, Seção 5).

## 5. SDK `<DynamicZone>` (client-frontend, `dynamic-zones/`)

```tsx
<DynamicZone slot="resumo_financeiro" userId={userId}>
  <ResumoNativo />   {/* fallback = children */}
</DynamicZone>
```

Comportamento:
1. `GET .../payload`; 204 ou erro de rede → renderiza children.
2. `zodSchema.safeParse(payload)` - espelho exato do JSON Schema canônico.
3. `payload.widget` deve existir no registry local: `shortcut_list` (título + até 3 links internos), `summary_card` (card de destaque com label + até 3 itens), `alert_banner` (aviso curto de até 60 caracteres com tom neutro/atenção). Nada de HTML dinâmico, `dangerouslySetInnerHTML` proibido; `href` restrito por regex do schema.
4. Qualquer falha (schema, widget desconhecido, exceção de render) → children + `POST /api/upa/violations` com motivo e payload bruto.

## 6. Contrato do slot `resumo_financeiro`

```json
{ "widget": "shortcut_list | summary_card | alert_banner",
  "label": "string, máx 40",
  "maxItems": "inteiro 1–3, obrigatório apenas para shortcut_list e summary_card",
  "tone": "neutral | atencao, obrigatório apenas para alert_banner",
  "items": [ { "label": "string, máx 40", "href": "regex ^/(dashboard|transacoes|relatorios)$" } ] }
```
`additionalProperties: false`. Espelhado em Zod (cliente) e JSON Schema (core) - divergência entre os dois é bug.

## 7. Tela Zonas (pase-panel)

Seções: **Payloads** (user, slot, origin, status, JSON expandível, botão revogar) · **Violações** (motivo + payload bruto) · **Simulador** (select de persona + botão "Simular uso intenso de relatórios") · **Injetor** (textarea JSON + user + slot → `inject-raw`).

## 8. Critérios de aceite

- **D4:** `simulate(ana)` → payload `autonoma` criado e válido → dashboard da Ana exibe o widget; dashboard da Clara exibe só o nativo; `revoke` restaura o estado.
- **D5:** três injeções inválidas - `label` com 500 chars · `href` externo (`https://…`) · `widget: "iframe_injector"` - dashboard da Ana permanece no fallback nativo, com 3 violações listadas com motivos distintos.
- Telemetria real (navegar 5× em `/relatorios` logado como Ana) também dispara a regra.
